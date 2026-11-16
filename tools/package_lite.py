"""Derive Lite from the tested full ZIP, preserving every retained runtime byte."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import VERSION

LITE_NAME = f'K-File-Station-v{VERSION}-Lite-Windows-x64.zip'
OMITTED = ('engines/libreoffice/', 'engines/pandoc/')
PANDOC_PAIRS = {('docx','md'),('md','docx'),('md','html'),('md','pdf'),
               ('html','md'),('html','epub'),('epub','docx'),('doc','md')}
OFFICE_PAIRS = {('doc','docx'),('docx','doc'),('xls','xlsx'),('xlsx','xls'),
                ('ppt','pptx'),('pptx','ppt'),('doc','md'),('doc','txt')}


def stable_info(name):
    info=zipfile.ZipInfo(name,(1980,1,1,0,0,0))
    info.create_system=0
    info.external_attr=0o600 << 16
    info.compress_type=zipfile.ZIP_DEFLATED
    info.compress_level=6
    return info


def unavailable_pairs(graph, image_extensions):
    return PANDOC_PAIRS | OFFICE_PAIRS | {(s,t) for s,ts in graph.items()
        for t in ts if t == 'pdf' and s not in image_extensions}


def package(root=ROOT):
    root = Path(root).resolve()
    source = root / f'release/K-File-Station-v{VERSION}-Windows-x64.zip'
    target = root / 'release' / LITE_NAME
    readme = (root/'LITE-EDITION.md').read_bytes()
    manifest = {'version': VERSION, 'edition':'Lite', 'omitted_engine_directories':list(OMITTED),
                'base_archive':source.name, 'runtime_policy':'identical retained files; no code or search dictionary removed'}
    with source.open('rb') as stream: manifest['base_sha256'] = hashlib.file_digest(stream,'sha256').hexdigest()
    count = 0
    with zipfile.ZipFile(source) as full, zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as lite:
        for entry in full.infolist():
            path = PurePosixPath(entry.filename)
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if any(relative.startswith(prefix) for prefix in OMITTED): continue
            if relative == 'README.md':
                lite.writestr(entry,readme,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
                continue
            with full.open(entry) as reader, lite.open(stable_info(entry.filename),'w') as writer:
                import shutil
                shutil.copyfileobj(reader,writer,1024*1024)
            count += 1
        lite.writestr(stable_info('K文件处理台/LITE-EDITION.md'),readme)
        lite.writestr(stable_info('K文件处理台/source/tools/package_lite.py'),Path(__file__).read_bytes())
        lite.writestr(stable_info('K文件处理台/lite-manifest.json'),json.dumps(manifest,ensure_ascii=False,indent=2))
    with target.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    (root/'release/SHA256-Lite.txt').write_text(digest+'  '+target.name+'\n','utf-8')
    print(f'Lite: {target.stat().st_size/1024**2:.1f} MiB; {count} retained files; SHA256 {digest}',flush=True)
    return target


if __name__=='__main__': package()
