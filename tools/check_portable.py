"""Run the frozen EXE from a different, non-ASCII folder with a minimal PATH."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, parse_qs

import httpx

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
source = root / 'dist/K文件处理台'
quick = '--quick' in sys.argv
legacy = '--legacy' in sys.argv
image_mode = '--images' in sys.argv
new_mode = '--new' in sys.argv
destination = root / ('build/图片格式 迁移验证/K文件处理台' if image_mode else 'build/旧版格式 迁移验证/K文件处理台' if legacy else 'build/最终 验证/K文件处理台' if quick else 'build/迁移 验证/K文件处理台')
destination.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns('data'))
env = dict(os.environ)
windows_root = os.environ.get('SystemRoot', 'C:/Windows')
env['PATH'] = os.path.join(windows_root, 'System32') + ';' + windows_root
(destination / 'data/_runtime.json').unlink(missing_ok=True)
process = subprocess.Popen([str(destination / 'K文件处理台.exe'), '--no-browser'], cwd=destination,
                           env=env, creationflags=0x08000000)
runtime = destination / 'data/_runtime.json'
try:
    for _ in range(200):
        if runtime.is_file(): break
        if process.poll() is not None: raise RuntimeError('Frozen launcher exited: ' + str(process.returncode))
        time.sleep(.1)
    details = json.loads(runtime.read_text('utf-8'))
    url = urlsplit(details['url'])
    token = parse_qs(url.query)['session'][0]
    client = httpx.Client(base_url=f'{url.scheme}://{url.netloc}', headers={'Authorization': 'Bearer ' + token}, timeout=60, trust_env=False)
    for _ in range(200):
        try:
            config = client.get('/api/config')
            if config.status_code == 200: break
        except httpx.TransportError:
            pass
        time.sleep(.1)
    assert all(config.json()['engines'].values()), config.text
    module_spec = importlib.util.spec_from_file_location('conversion_fixtures', root / 'tests/test_conversions.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    class Factory:
        def mktemp(self, name): return Path(tempfile.mkdtemp(prefix=name))
    samples = module.samples.__wrapped__(Factory())
    import converter
    image_spec=importlib.util.spec_from_file_location('image_fixtures',root/'tests/test_images.py')
    image_module=importlib.util.module_from_spec(image_spec); image_spec.loader.exec_module(image_module)
    image_samples=image_module.images.__wrapped__(Factory())
    for image_path in image_samples.iterdir(): shutil.copy2(image_path,samples/image_path.name)
    new_spec=importlib.util.spec_from_file_location('new_fixtures',root/'tests/test_data_media.py')
    new_module=importlib.util.module_from_spec(new_spec); new_spec.loader.exec_module(new_module)
    new_samples=new_module.samples_v07.__wrapped__(Factory())
    for new_path in new_samples.iterdir():
        if not (samples/new_path.name).exists():shutil.copy2(new_path,samples/new_path.name)
    from extended_check import samples as extra_samples
    extras=extra_samples(Path(tempfile.mkdtemp(prefix='full-portable-extras-')))
    for new_path in extras.iterdir():
        if not (samples/new_path.name).exists():shutil.copy2(new_path,samples/new_path.name)
    cases = [(ext, target, 'sample.dng' if ext=='raw' else 'sample.'+ext) for ext, targets in config.json()['graph'].items() for target in targets]
    cases += [('pdf', target, 'scan.pdf') for target in ('txt', 'docx', 'xlsx')]
    cases += [('pdf', 'png', 'multi.pdf')]
    if quick:
        cases = [case for case in cases if case in [('md', 'html', 'sample.md'), ('html', 'md', 'sample.html'), ('html', 'epub', 'sample.html'), ('csv', 'xlsx', 'sample.csv'), ('pdf', 'txt', 'scan.pdf')]]
    if legacy:
        cases = [case for case in cases if case[0] in ('doc','xls','ppt') or case[1] in ('doc','xls','ppt')]
    if image_mode:
        cases=[(ext,target,'sample.dng' if ext=='raw' else 'sample.'+ext) for ext in converter.IMAGE_EXTENSIONS for target in config.json()['graph'][ext]]
    if new_mode:
        cases=[(ext,target,'sample.'+ext) for ext,target in new_module.NEW_EDGES]
    records = []
    for ext, target, filename in cases:
        input_path=extras/'sample.xlsx' if ext=='xlsx' and target=='json' else samples/filename
        with input_path.open('rb') as stream:
            r = client.post('/api/files', files={'file': ('中文便携测试.' + ext, stream)})
        assert r.status_code == 200, r.text
        uploaded = r.json()
        r = client.post('/api/jobs', json={'fileId': uploaded['id'], 'target': target, 'options': {'ocr': True, 'sheet': ('第二张' if target=='json' else '第二张表') if ext == 'xlsx' else None,'clip_duration':.6,'gif_width':160}})
        assert r.status_code == 200, r.text
        job = r.json()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            job = client.get('/api/jobs/' + job['id']).json()
            if job['status'] in ('done', 'error'): break
            time.sleep(.3)
        assert job['status'] == 'done', job
        result = client.get('/api/download/' + job['id'])
        assert result.status_code == 200 and len(result.content) > 10
        output=extras/('verified-'+ext+'-'+job['outputName'])
        output.write_bytes(result.content)
        if output.suffix=='.zip':
            import zipfile
            with zipfile.ZipFile(output) as bundle:assert bundle.testzip() is None and bundle.namelist()
        elif target in converter.GRAPH:
            converter.validate(output,target)
        records.append({'source': ext, 'input': filename, 'target': target, 'bytes': len(result.content), 'warnings': job['warnings']})
        print(f'PASS {filename} -> {target} ({len(result.content)} bytes)', flush=True)
        client.delete('/api/files/' + uploaded['id'])
    report = 'conversions-portable.json'
    (root / 'build' / report).write_text(json.dumps(records, ensure_ascii=False, indent=2), 'utf-8')
    client.post('/api/shutdown')
    process.wait(timeout=20)
    assert process.returncode == 0
    print(f'Portable checks passed: {len(records)} conversions, minimal PATH, relocated non-ASCII folder, clean shutdown.', flush=True)
finally:
    if process.poll() is None: process.terminate()
