"""Validate the public release boundary and developer runtime bootstrap."""
import zipfile
import pytest
from tools.public_files import public_files
from tools.prepare_engines import restore


def test_public_allowlist_excludes_local_data(tmp_path):
    for name in ('app.py','private_notes.py','README.md','data/passwords.txt','.env','docs/清理记录-v1.json','docs/release-validation.json','web/index.html','tools/.env'):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('test','utf-8')
    assert public_files(tmp_path)==['README.md','app.py','docs/release-validation.json','web/index.html']


def test_restore_release_engines_only(tmp_path):
    archive=tmp_path/'runtime.zip'
    required=('pandoc/pandoc.exe','libreoffice/program/soffice.com','archive/7-Zip/7z.exe','archive/bytecode/recovery.bin')
    with zipfile.ZipFile(archive,'w') as bundle:
        for name in required:bundle.writestr('K文件处理台/engines/'+name,'synthetic engine')
        bundle.writestr('K文件处理台/data/passwords.txt','never import')
    restore(archive,tmp_path)
    assert all((tmp_path/'engines'/name).read_text()=='synthetic engine' for name in required)
    assert not (tmp_path/'data').exists()


def test_restore_rejects_unsafe_engine_path(tmp_path):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('K文件处理台/engines/../../escape.txt','unsafe')
    with pytest.raises(ValueError,match='Unsafe'):restore(archive,tmp_path)
    assert not (tmp_path/'escape.txt').exists() and not (tmp_path/'engines').exists()


def test_api_release_version():
    from app import config
    from version import VERSION
    assert VERSION=='1.0.0' and config()['version']==VERSION
