"""Restore bundled conversion engines from a version-matched portable release."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import shutil
import stat
import tempfile
import urllib.request
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import VERSION


def restore(archive, root=ROOT):
    root=Path(root).resolve(); build=root/'build'; build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='engine-import-',dir=build) as temporary:
        staging=Path(temporary).resolve(); count=0
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                path=PurePosixPath(entry.filename.replace('\\','/'))
                if len(path.parts)<3 or path.parts[1]!='engines':continue
                if path.is_absolute() or '..' in path.parts or ':' in entry.filename or stat.S_ISLNK(entry.external_attr>>16):
                    raise ValueError('Unsafe engine archive entry')
                target=(staging/Path(*path.parts[2:])).resolve()
                if not target.is_relative_to(staging):raise ValueError('Engine path escapes staging directory')
                if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with bundle.open(entry) as source,target.open('wb') as output:shutil.copyfileobj(source,output,1024*1024)
                count+=1
        for required in ('pandoc/pandoc.exe','libreoffice/program/soffice.com','archive/7-Zip/7z.exe','archive/bytecode/recovery.bin'):
            if not (staging/required).is_file():raise ValueError('Incomplete engine bundle: '+required)
        shutil.copytree(staging,root/'engines',dirs_exist_ok=True)
    print('Restored engine files:',count)


def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive',type=Path,help='Path to the portable release ZIP')
    group.add_argument('--download',action='store_true',help='Download the version-matched public release and verify SHA256')
    args=parser.parse_args()
    if args.archive:restore(args.archive);return
    name=f'K-File-Station-v{VERSION}-Windows-x64.zip'
    base=f'https://github.com/ykiii5277-web/K-File-Station/releases/download/v{VERSION}/'
    folder=ROOT/'build/engine-download';folder.mkdir(parents=True,exist_ok=True)
    archive=folder/name
    print('Downloading portable runtime:',name,flush=True)
    with urllib.request.urlopen(base+name,timeout=90) as source,archive.open('wb') as output:shutil.copyfileobj(source,output,1024*1024)
    with urllib.request.urlopen(base+'SHA256.txt',timeout=30) as source:lines=source.read().decode('utf-8').splitlines()
    expected=next(line.split()[0] for line in lines if line.split()[-1]==name)
    with archive.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=expected:raise ValueError('Downloaded portable runtime SHA256 mismatch')
    restore(archive)


if __name__=='__main__':main()
