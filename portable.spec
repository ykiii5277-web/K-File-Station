# -*- mode: python ; coding: utf-8 -*-
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
