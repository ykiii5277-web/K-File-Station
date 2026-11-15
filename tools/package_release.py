"""Package the public release using the explicit source/document allowlist."""
from pathlib import Path
import hashlib,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from version import VERSION
from public_files import public_files


def package(root):
    root=Path(root).resolve();folder=root/'dist/K文件处理台'
    release=root/'release';release.mkdir(exist_ok=True)
    archive_path=release/f'K-File-Station-v{VERSION}-Windows-x64.zip'
    source_files=public_files(root);total=0
    print('Creating public portable ZIP',flush=True)
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
        for name in ('K文件处理台.exe','_internal','engines','licenses'):
            top=folder/name
            for path in ([top] if top.is_file() else top.rglob('*')):
                if not path.is_file():continue
                relative=path.relative_to(folder)
                if any(part=='cache' or part.endswith(('.outfiles','.pid','.restore','.restore.new','.potfile')) for part in relative.parts):continue
                archive.write(path,Path(folder.name)/relative);total+=1
        for relative in source_files:
            archive.write(root/relative,Path(folder.name)/'source'/relative);total+=1
            if relative.startswith('docs/'):
                archive.write(root/relative,Path(folder.name)/relative);total+=1
        for name in ('README.md','THIRD_PARTY_NOTICES.md','requirements.txt','requirements-lock.txt','LICENSE.txt'):
            archive.write(root/name,Path(folder.name)/name);total+=1
    with archive_path.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    (release/'SHA256.txt').write_text(checksum+'  '+archive_path.name+'\n','utf-8')
    print(f'Built {total} files: {archive_path.name} ({archive_path.stat().st_size/1024**2:.1f} MB)',flush=True)
    return archive_path


if __name__=='__main__':package(ROOT)
