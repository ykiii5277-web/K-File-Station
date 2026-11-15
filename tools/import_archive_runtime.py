"""Copy the user's compiled recovery engine; never copy archives or personal data."""
from pathlib import Path
import argparse,hashlib,json,marshal,shutil
from PyInstaller.archive.readers import CArchiveReader

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(); parser.add_argument('--source',required=True,help='Existing compiled archive tool directory')
source=Path(parser.parse_args().source); target=root/'engines/archive'
exe=source/'压缩包破解工具.exe'
archive=CArchiveReader(str(exe)); pyz=archive.open_embedded_archive('PYZ.pyz')
code_dir=target/'bytecode'; code_dir.mkdir(parents=True,exist_ok=True)
names=('runtime_paths','recovery','gpu_search','archive_targets','opencl_aes','search_tasks','mask_range')
for name in names: (code_dir/(name+'.bin')).write_bytes(marshal.dumps(pyz.extract(name)))
for name in ('7-Zip','hashcat','extractors','wordlists','licenses'):
    shutil.copytree(source/name,target/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('data','cache','*.pid','*.restore','*.restore.new','*.potfile','*.outfiles'))
shutil.copy2(source/'详细使用说明.md',target/'原引擎说明.md')
fixtures=root/'tests/fixtures/archive'; fixtures.mkdir(parents=True,exist_ok=True)
shutil.copy2(source/'selftest/fixture.rar',fixtures/'fixture.rar')
(target/'provenance.json').write_text(json.dumps({'source_exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
    'modules':{n:hashlib.sha256((code_dir/(n+'.bin')).read_bytes()).hexdigest() for n in names},
    'python':'3.13','personal_data_copied':False},ensure_ascii=False,indent=2),'utf-8')
print('Copied compiled archive engine and resources, excluding all personal archives and data.')
