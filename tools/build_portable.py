"""Create a complete Windows x64 folder and ZIP; no installer is required."""
from pathlib import Path
import hashlib
import importlib.metadata
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import converter
from public_files import public_files

if not all(converter.capabilities().values()):
    raise SystemExit('All required engines must be available before packaging.')

spec = '''# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files
rapid_data, rapid_bins, rapid_hidden = collect_all('rapidocr')
onnx_data, onnx_bins, onnx_hidden = collect_all('onnxruntime')
mupdf_data, mupdf_bins, mupdf_hidden = collect_all('pymupdf')
heif_data, heif_bins, heif_hidden = collect_all('pillow_heif')
raw_data, raw_bins, raw_hidden = collect_all('rawpy')
ffmpeg_data, ffmpeg_bins, ffmpeg_hidden = collect_all('imageio_ffmpeg')
a = Analysis(['app.py'], pathex=[],
    binaries=rapid_bins+onnx_bins+mupdf_bins+heif_bins+raw_bins+ffmpeg_bins,
    datas=[('web','web')]+rapid_data+onnx_data+mupdf_data+heif_data+raw_data+ffmpeg_data,
    hiddenimports=rapid_hidden+onnx_hidden+mupdf_hidden+heif_hidden+raw_hidden+ffmpeg_hidden+collect_submodules('uvicorn'),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest','playwright','pptx','pymupdf4llm','pymupdf.layout','tkinter','IPython','matplotlib','scipy','torch','tensorflow','pandas'])
# Qt uses the Windows ICU API. A Poppler directory on the build host PATH has
# an incompatible, version-suffixed icuuc.dll; it must never shadow the OS DLL.
a.binaries = [entry for entry in a.binaries if entry[0].lower() not in ('icuuc.dll','icudt78.dll')]
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='K文件处理台',debug=False,icon='web/app.ico',
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,version='tools/windows_version.txt')
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='K文件处理台')
'''
(ROOT / 'portable.spec').write_text(spec, 'utf-8')
# Build into a managed staging directory. Updating the release must preserve
# users' saved results and widget settings in dist/K文件处理台/data.
staging = (ROOT / 'build/staging').resolve()
assert staging.is_relative_to(ROOT.resolve())
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', str(staging), str(ROOT / 'portable.spec')], cwd=ROOT, check=True)
folder = ROOT / 'dist/K文件处理台'
shutil.copytree(staging / 'K文件处理台', folder, dirs_exist_ok=True)
for name in ('pandoc', 'libreoffice', 'msvc','archive'):
    print('Copying engine:', name, flush=True)
    shutil.copytree(ROOT / 'engines' / name, folder / 'engines' / name, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('data','cache','*.pid','*.outfiles','*.restore','*.restore.new','*.potfile') if name=='archive' else None)

# Keep the C++ runtime components at one version in both DLL search locations.
for runtime in (ROOT / 'engines/msvc').glob('*.dll'):
    shutil.copy2(runtime, folder / '_internal' / runtime.name)
    shutil.copy2(runtime, folder / '_internal/PySide6' / runtime.name)

# Administrative MSI extraction places redistributable runtime files in System64.
# Place those beside soffice too so a clean PC does not depend on an installed VC runtime.
for runtime in (folder / 'engines/libreoffice/System64').glob('*.dll'):
    dest = folder / 'engines/libreoffice/program' / runtime.name
    if not dest.exists():
        shutil.copy2(runtime, dest)

for name in ('README.md', 'THIRD_PARTY_NOTICES.md', 'requirements.txt', 'requirements-lock.txt', 'LICENSE.txt'):
    shutil.copy2(ROOT / name, folder / name)
source = folder / 'source'
source.mkdir(exist_ok=True)
for name in ('app.py', 'version.py', 'desktop.py', 'help_dialog.py', 'user_guide.py', 'office_extra.py','tar_extract.py','search_help.py','extended_check.py','file_policy.py','batch_convert.py','archive_bridge.py','archive_ui.py','archive_check.py','image_converter.py', 'data_converter.py', 'media_converter.py', 'progress_visual.py', 'widget_check.py', 'converter.py', 'portable.spec', 'pytest.ini', 'requirements.txt', 'requirements-lock.txt', 'README.md', 'THIRD_PARTY_NOTICES.md', 'LICENSE.txt'):
    shutil.copy2(ROOT / name, source / name)
for relative in public_files(ROOT):
    file=ROOT/relative
    target=source/relative; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(file,target)
    if relative.startswith('docs/'):
        target=folder/relative; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(file,target)

licenses = folder / 'licenses'
licenses.mkdir(exist_ok=True)
for dist in importlib.metadata.distributions():
    for file in dist.files or []:
        if any(p.lower().startswith(('license', 'copying', 'notice')) for p in file.parts):
            path = Path(dist.locate_file(file))
            if path.is_file():
                target = licenses / dist.metadata['Name'] / path.name
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(path, target)

# Retain the bundled encoder's own build configuration and GPL license as well
# as the BSD license of its Python wrapper.
import imageio_ffmpeg
import urllib.request
ffmpeg_licenses=licenses/'FFmpeg'; ffmpeg_licenses.mkdir(exist_ok=True)
for option,name in (('-version','build-configuration.txt'),('-L','license-notice.txt')):
    detail=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),option],capture_output=True,text=True,creationflags=0x08000000)
    (ffmpeg_licenses/name).write_text(detail.stdout+detail.stderr,'utf-8')
if not (ffmpeg_licenses/'GPL-3.0.txt').exists():
    with urllib.request.urlopen('https://www.gnu.org/licenses/gpl-3.0.txt',timeout=30) as response:
        license_text=response.read()
    assert b'GNU GENERAL PUBLIC LICENSE' in license_text
    (ffmpeg_licenses/'GPL-3.0.txt').write_bytes(license_text)

if '--no-zip' not in sys.argv:
    from package_release import package
    package(ROOT)
