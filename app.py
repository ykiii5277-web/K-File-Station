"""Portable, loopback-only file converter launcher and API."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import threading
import time
import uuid
import webbrowser

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import converter
import file_policy
from version import VERSION

DATA = converter.HOME / 'data'
DATA.mkdir(exist_ok=True)
for folder in ('uploads', 'outputs', 'logs'):
    (DATA / folder).mkdir(exist_ok=True)
logging.basicConfig(filename=DATA / 'logs/app.log', level=logging.INFO, encoding='utf-8',
                    format='%(asctime)s %(levelname)s %(message)s')
TOKEN = secrets.token_urlsafe(32)
FILES: dict = {}
JOBS: dict = {}
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='convert')
SERVER = None
LAST_ACTIVITY = time.monotonic()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def local_session(request: Request, call_next):
    global LAST_ACTIVITY
    LAST_ACTIVITY = time.monotonic()
    host = request.url.hostname
    if host not in ('127.0.0.1', 'localhost', 'testserver'):
        return JSONResponse({'detail': '仅允许本机访问。'}, 403)
    if request.url.path == '/' and secrets.compare_digest(request.query_params.get('session', ''), TOKEN):
        response = RedirectResponse('/', status_code=303)
        response.set_cookie('local_session', TOKEN, httponly=True, samesite='strict')
        return response
    if request.url.path.startswith('/api/'):
        supplied = request.cookies.get('local_session', '')
        bearer = request.headers.get('authorization', '').removeprefix('Bearer ')
        if not (secrets.compare_digest(supplied, TOKEN) or secrets.compare_digest(bearer, TOKEN)):
            return JSONResponse({'detail': '本地会话已失效，请重新启动工具。'}, 401)
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': '不允许跨站访问本地文件。'}, 403)
    try:
        response = await call_next(request)
    except Exception:
        logging.exception('Unhandled request error')
        return JSONResponse({'detail': '处理失败，请检查文件后重试。'}, 500)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/config')
def config():
    return {'graph': converter.GRAPH, 'labels': converter.LABELS, 'notes': converter.NOTES,
            'engines': converter.capabilities(), 'limitsMB':{key:value//file_policy.MIB for key,value in file_policy.LIMITS.items()}, 'version': VERSION,
            'imageSources': sorted(converter.IMAGE_EXTENSIONS),'aliases': converter.EXTENSION_ALIASES,
            'modules':{ext:converter.module_for(ext) for ext in converter.GRAPH},
            'outputDir': str(DATA / 'outputs')}


def public_job(job):
    return {k: v for k, v in job.items() if k not in ('path',)}


@app.post('/api/files')
def upload(file: UploadFile = File(...)):
    filename = (file.filename or '').replace('\\', '/').split('/')[-1]
    ext = converter.normalize_extension(Path(filename).suffix)
    if ext not in converter.GRAPH:
        raise HTTPException(400, '请选择当前板块支持的文件格式。')
    with LOCK:
        if len(FILES) >= 100:
            raise HTTPException(400, '当前会话文件数量已达上限，请重启工具后继续。')
    file_id = uuid.uuid4().hex
    folder = DATA / 'uploads' / file_id
    folder.mkdir()
    path = folder / ('input.' + ext)
    try:
        total = 0
        with path.open('wb') as stream:
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                module=converter.module_for(ext)
                if total > file_policy.LIMITS[module]:
                    raise HTTPException(413, '单个文件不能超过 '+file_policy.limit_text(module)+'。')
                stream.write(chunk)
        if total == 0:
            raise HTTPException(400, '不能上传空文件。')
        metadata = converter.validate(path, ext)
    except Exception as exc:
        shutil.rmtree(folder)
        if isinstance(exc, HTTPException):
            raise
        if not isinstance(exc, converter.ConversionError):
            logging.exception('Upload validation failed')
        raise HTTPException(400, str(exc) if isinstance(exc, converter.ConversionError) else '无法读取此文档，请检查文件是否完整或受到保护。') from None
    finally:
        file.file.close()
    item = {'id': file_id, 'name': filename, 'ext': ext, 'size': total,
            'targets': converter.targets_for(ext,metadata), **metadata}
    with LOCK:
        FILES[file_id] = {**item, 'path': path}
    return item


@app.delete('/api/files/{file_id}')
def remove_file(file_id: str):
    with LOCK:
        if any(j['fileId'] == file_id and j['status'] in ('queued', 'running') for j in JOBS.values()):
            raise HTTPException(409, '请等待此文件转换结束后再移除。')
        item = FILES.pop(file_id, None)
        if item:
            shutil.rmtree(item['path'].parent)
    return {'ok': True}


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ocr: bool = True
    sheet: str | None = None
    dpi: int = Field(default=150, ge=96, le=300)
    xml_mode: str = Field(default='preserve',pattern='^(preserve|elements)$')
    xml_root: str = Field(default='root',max_length=100)
    records_path: str = Field(default='',max_length=500)
    nested_csv: str = Field(default='json',pattern='^(json|reject)$')
    clip_start: float = Field(default=0,ge=0,le=86400,allow_inf_nan=False)
    clip_duration: float = Field(default=5,gt=0,le=30,allow_inf_nan=False)
    gif_fps: int = Field(default=12,ge=1,le=30)
    gif_width: int = Field(default=480,ge=64,le=1280)


class StartJob(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fileId: str
    target: str
    options: Options = Field(default_factory=Options)


def worker(job_id: str, source: Path, options: dict):
    def progress(percent, message):
        with LOCK:
            JOBS[job_id].update(progress=percent, message=message)
    with LOCK:
        job = JOBS[job_id]
        job['status'] = 'running'
    try:
        output, warnings = converter.convert(source, job['target'], DATA / 'outputs' / job_id, options, progress)
        stem = re_safe_stem(Path(job['sourceName']).stem)
        # Keep the readable name in the physical result folder, including relocated portable copies.
        final = output.with_name(stem + output.suffix)
        output.replace(final)
        with LOCK:
            job.update(status='done', progress=100, message='转换完成', path=final,
                       outputName=final.name, size=final.stat().st_size, warnings=warnings)
        logging.info('Job %s completed %s -> %s', job_id, source.suffix, job['target'])
    except Exception as exc:
        logging.exception('Job %s failed', job_id)
        with LOCK:
            job.update(status='error', progress=0,
                       message=str(exc) if isinstance(exc, converter.ConversionError) else '转换失败：文件内容可能不兼容。可尝试在原软件中重新保存后上传。')
    finally:
        # Engine profiles and input copies are transient; keep only the final deliverable.
        folder = DATA / 'outputs' / job_id
        if folder.exists():
            for entry in folder.iterdir():
                if job.get('path') == entry:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)


def re_safe_stem(value):
    import re
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:90]
    if not value or value.upper() in ('CON', 'PRN', 'AUX', 'NUL') or re.fullmatch(r'(COM|LPT)[1-9]', value, re.I):
        value = '转换结果'
    return value


@app.post('/api/jobs')
def start_job(body: StartJob):
    with LOCK:
        item = FILES.get(body.fileId)
        if not item:
            raise HTTPException(404, '文件已失效，请重新上传。')
        if body.target not in item['targets']:
            raise HTTPException(400, '不支持此转换方向。')
        existing = next((j for j in JOBS.values() if j['fileId'] == body.fileId and j['status'] in ('queued', 'running')), None)
        if existing:
            return public_job(existing)
        if sum(j['status'] in ('queued', 'running') for j in JOBS.values()) >= 10:
            raise HTTPException(429, '转换队列已满，请稍后重试。')
        job_id = uuid.uuid4().hex
        job = {'id': job_id, 'fileId': body.fileId, 'sourceName': item['name'], 'target': body.target,
               'status': 'queued', 'progress': 0, 'message': '正在等待转换', 'warnings': [],
               'createdAt': datetime.now().isoformat()}
        JOBS[job_id] = job
        POOL.submit(worker, job_id, item['path'], body.options.model_dump())
        return public_job(job)


@app.get('/api/jobs')
def jobs():
    with LOCK:
        return [public_job(j) for j in reversed(list(JOBS.values()))]


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    with LOCK:
        if job_id not in JOBS:
            raise HTTPException(404, '转换任务不存在。')
        return public_job(JOBS[job_id])


@app.get('/api/download/{job_id}')
def download(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
        if not job or job['status'] != 'done' or not job['path'].is_file():
            raise HTTPException(404, '结果尚未生成或已被移除。')
        return FileResponse(job['path'], filename=job['outputName'], media_type='application/octet-stream')


@app.post('/api/open-output')
def open_output():
    if os.name == 'nt':
        os.startfile(DATA / 'outputs')
    return {'ok': True}


@app.post('/api/shutdown')
def shutdown():
    with LOCK:
        if any(j['status'] in ('running', 'queued') for j in JOBS.values()):
            raise HTTPException(409, '仍有文件正在转换，请等待完成后退出。')
    if SERVER:
        SERVER.should_exit = True
    return {'ok': True}


app.mount('/', StaticFiles(directory=converter.ROOT / 'web', html=True), name='web')


def launch_browser(url):
    for base in (os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('PROGRAMFILES', ''), os.environ.get('LOCALAPPDATA', '')):
        edge = Path(base) / 'Microsoft/Edge/Application/msedge.exe'
        if edge.is_file():
            subprocess.Popen([str(edge), '--app=' + url, '--window-size=1440,980'],
                             creationflags=0x08000000 if os.name == 'nt' else 0)
            return
    webbrowser.open(url)


def main():
    global SERVER
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--browser', action='store_true', help='Use the optional browser interface')
    parser.add_argument('--check-widget', action='store_true', help='Run the native widget acceptance checks')
    parser.add_argument('--check-archives', action='store_true', help='Verify the imported archive engine on synthetic data')
    parser.add_argument('--check-extra', action='store_true', help='Verify all 28 newly added conversion directions')
    parser.add_argument('--report-dir', type=Path, default=DATA/'widget-check')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    if args.check_extra:
        from extended_check import run_checks
        run_checks(args.report_dir)
        return
    if args.check_archives:
        from archive_check import run_checks
        run_checks(args.report_dir)
        return
    if args.check_widget:
        from widget_check import run_checks
        run_checks(args.report_dir)
        return
    if not args.no_browser and not args.browser:
        from desktop import run_desktop
        return run_desktop()
    # Reclaim only our UUID-named upload folders; results persist until the user deletes them.
    for entry in (DATA / 'uploads').iterdir():
        if len(entry.name) == 32 and all(c in '0123456789abcdef' for c in entry.name) and entry.is_dir():
            if time.time() - entry.stat().st_mtime > 7 * 86400:
                shutil.rmtree(entry, ignore_errors=True)
    # Bind the listening socket before starting the server, avoiding a port allocation race.
    sock = socket.socket()
    sock.bind(('127.0.0.1', args.port))
    port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}/?session={TOKEN}'
    SERVER = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    def browser_when_ready():
        for _ in range(200):
            if SERVER.started:
                if not args.no_browser:
                    launch_browser(url)
                return
            time.sleep(.05)
    threading.Thread(target=browser_when_ready, daemon=True).start()
    def idle_shutdown():
        while not SERVER.should_exit:
            time.sleep(20)
            with LOCK:
                active = any(j['status'] in ('queued', 'running') for j in JOBS.values())
            if not active and time.monotonic() - LAST_ACTIVITY > 1800:
                SERVER.should_exit = True
    threading.Thread(target=idle_shutdown, daemon=True).start()
    if args.no_browser:
        print(url, flush=True)
    runtime_file = DATA / '_runtime.json'
    runtime_file.write_text(json.dumps({'pid': os.getpid(), 'url': url}), 'utf-8')
    try:
        SERVER.run(sockets=[sock])
    finally:
        POOL.shutdown(wait=True)
        try:
            if json.loads(runtime_file.read_text('utf-8')).get('pid') == os.getpid():
                runtime_file.unlink()
        except (OSError, ValueError):
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('Application startup failed')
        if not any(flag in __import__('sys').argv for flag in ('--check-widget','--check-archives','--check-extra')):
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'启动失败，请查看 data/logs/app.log。','K文件处理台',0x10)
        raise SystemExit(1)
