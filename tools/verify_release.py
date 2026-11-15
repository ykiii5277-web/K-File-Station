"""Verify the public portable archive, tested executable, source and privacy boundary."""
from pathlib import Path
import hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from version import VERSION
from public_files import public_files

path=ROOT/f'release/K-File-Station-v{VERSION}-Windows-x64.zip'
base='K文件处理台/'
record=json.loads((ROOT/'docs/release-validation.json').read_text('utf-8'))
assert record['status']=='passed' and record['version']==VERSION
assert record['native_groups']==40 and record['archive_groups']==18 and record['extended_directions']==28
assert record['baseline']['regression_tests']==194 and record['baseline']['conversion_cases']==96
assert record['publication_tests']==22 and record['animated_avif']
with zipfile.ZipFile(path) as bundle:
    assert bundle.testzip() is None,'ZIP CRC failed'
    names=bundle.namelist();assert len(names)==len(set(names))
    assert not any(name.startswith(base+'data/') or '/清理记录-' in name or name.endswith(('.potfile','.restore','.restore.new','.log','.pid')) for name in names),'Private/local files included'
    assert hashlib.sha256(bundle.read(base+'K文件处理台.exe')).hexdigest()==record['exe_sha256'],'EXE differs from tested build'
    expected=set(public_files(ROOT))
    actual={name[len(base+'source/'):] for name in names if name.startswith(base+'source/')}
    assert actual==expected,'Public source allowlist differs from package'
    for name in expected:assert bundle.read(base+'source/'+name)==(ROOT/name).read_bytes(),'Source differs: '+name
    for name,digest in record['baseline']['unchanged_core'].items():
        assert hashlib.sha256(bundle.read(base+'source/'+name)).hexdigest()==digest,'Previously tested core changed'
    provenance=json.loads(bundle.read(base+'engines/archive/provenance.json'))
    assert provenance['personal_data_copied'] is False
    for module,digest in provenance['modules'].items():
        assert hashlib.sha256(bundle.read(base+'engines/archive/bytecode/'+module+'.bin')).hexdigest()==digest
    for name in ('engines/pandoc/pandoc.exe','engines/libreoffice/program/soffice.com','engines/archive/7-Zip/7z.exe','_internal/PySide6/plugins/platforms/qwindows.dll'):
        assert base+name in names
    assert base+'_internal/icuuc.dll' not in names
expected=(ROOT/'release/SHA256.txt').read_text('utf-8').split()[0]
with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==expected
print(f'PASS: v{VERSION}, CRC/SHA256, tested EXE, {len(actual)} public source files, unchanged tested core, native/archive/conversion evidence and personal-data exclusion.')
print(f'ZIP: {path.stat().st_size/1024**2:.1f} MB')
