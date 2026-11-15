from pathlib import Path
import zipfile
import json
import pytest
import converter
import file_policy
from batch_convert import convert_batch


@pytest.mark.parametrize('extension,module,limit',[('docx',0,500*1024**2),('png',1,500*1024**2),('json',2,500*1024**2),('mp4',3,2*1024**3),('zip',4,5*1024**3)])
def test_selection_size_boundaries(tmp_path,extension,module,limit,monkeypatch):
    # Mock only stat size so Windows never allocates real multi-gigabyte files.
    import os
    path=tmp_path/('boundary.'+extension)
    path.write_bytes(b'x'); reported={path:limit}; original=Path.stat
    def stat(candidate,*args,**kwargs):
        result=original(candidate,*args,**kwargs)
        if candidate in reported:
            values=list(result); values[6]=reported[candidate]; return os.stat_result(values)
        return result
    monkeypatch.setattr(Path,'stat',stat)
    selection=file_policy.validate_selection([path])
    assert selection['total']==limit and selection['module']==module
    other=tmp_path/('second.'+extension); other.write_bytes(b'x')
    with pytest.raises(converter.ConversionError,match='合计不能超过'):file_policy.validate_selection([path,other])
    reported[path]=limit+1
    with pytest.raises(converter.ConversionError,match='合计不能超过'):file_policy.validate_selection([path])


@pytest.mark.parametrize('names,valid',[(('a.JPG','b.JPEG'),True),(('a.tif','b.TIFF'),True),(('a.yml','b.yaml'),True),(('a.zip','b.zip.001'),True),(('a.png','b.jpg'),False),(('a.dng','b.nef'),False),(('a.zip','b.7z'),False)])
def test_same_format_policy(tmp_path,names,valid):
    paths=[tmp_path/name for name in names]
    for path in paths:path.write_bytes(b'x')
    if valid:assert file_policy.validate_selection(paths)['total']==2
    else:
        with pytest.raises(converter.ConversionError,match='同一格式'):file_policy.validate_selection(paths)


def test_loader_byte_progress_and_atomic_rejection(tmp_path,monkeypatch):
    import desktop
    monkeypatch.setattr(desktop,'DATA',tmp_path/'data')
    source=tmp_path/'large.md'; source.write_bytes(b'# Hello\n'+b'a'*12*1024**2)
    task=desktop.LoadTask(source); reports=[]; loaded=[]; failed=[]
    task.progress.connect(lambda value,message:reports.append(value))
    task.loaded.connect(loaded.append); task.failed.connect(failed.append); task.run()
    assert not failed and loaded and reports[-1]==98
    assert any(0<v<90 for v in reports) and reports==sorted(reports)
    assert loaded[0]['path'].read_bytes()==source.read_bytes()
    other=tmp_path/'other.json'; other.write_text('{}')
    task=desktop.LoadTask([source,other]); task.failed.connect(failed.append); task.run()
    assert failed and len(list((desktop.DATA/'uploads').iterdir()))==1


def test_batch_duplicate_names_and_partial_failure(tmp_path):
    sources=[]
    for index in range(3):
        path=tmp_path/str(index)/'same.csv'; path.parent.mkdir(); path.write_text('id,value\n001,12\n' if index!=1 else '"broken\n','utf-8'); sources.append(path)
    # Simulate a per-file converter failure after successful upload to verify partial results survive.
    original=converter.convert
    def selective(source,*args):
        if source==sources[1]:raise converter.ConversionError('expected failure')
        return original(source,*args)
    from unittest.mock import patch
    progress=[]
    with patch.object(converter,'convert',selective):
        result,notes=convert_batch({'ext':'csv','paths':sources,'names':['same.csv']*3},'json',tmp_path/'result',{},lambda value,message:progress.append(value))
    with zipfile.ZipFile(result) as bundle:
        assert set(bundle.namelist())=={'001_same.json','003_same.json','失败说明.txt'}
        assert json.loads(bundle.read('003_same.json'))[0]['id']=='001'
        assert 'expected failure' in bundle.read('失败说明.txt').decode('utf-8-sig')
    assert progress==sorted(progress) and notes and not list(result.parent.glob('work-*'))


def test_batch_images_can_be_separate_pdf(tmp_path):
    from PIL import Image
    import pymupdf
    paths=[tmp_path/f'{index}.png' for index in range(2)]
    for path in paths:Image.new('RGB',(20,20),'red').save(path)
    item={'ext':'png','paths':paths,'names':[p.name for p in paths]}
    output,_=convert_batch(item,'pdf',tmp_path/'merged',{},lambda *v:None)
    with pymupdf.open(output) as pdf:assert len(pdf)==2
    output,_=convert_batch(item,'pdf',tmp_path/'separate',{'merge_pdf':False},lambda *v:None)
    with zipfile.ZipFile(output) as bundle:assert len(bundle.namelist())==2 and all(n.endswith('.pdf') for n in bundle.namelist())


def test_batch_excel_without_common_sheet(tmp_path,monkeypatch):
    import desktop
    from openpyxl import Workbook
    monkeypatch.setattr(desktop,'DATA',tmp_path/'data'); paths=[]; loaded=[]
    for index in range(2):
        path=tmp_path/f'{index}.xlsx'; book=Workbook(); book.active.title=f'Sheet{index}'; book.active.append(['ID',str(index)]); book.save(path); book.close(); paths.append(path)
    task=desktop.LoadTask(paths); task.loaded.connect(loaded.append); task.run()
    assert loaded and loaded[0]['sheets']==[]
    output,_=convert_batch(loaded[0],'csv',tmp_path/'result',{'sheet':None},lambda *v:None)
    with zipfile.ZipFile(output) as bundle:assert len([n for n in bundle.namelist() if n.endswith('.csv')])==2


def test_media_batch_targets_are_intersection(tmp_path,monkeypatch):
    import desktop
    import subprocess
    from media_converter import binary
    monkeypatch.setattr(desktop,'DATA',tmp_path/'data'); paths=[]
    for name,audio in [('sound',True),('silent',False)]:
        path=tmp_path/(name+'.mp4'); paths.append(path)
        args=[binary(),'-v','error','-y','-f','lavfi','-i','color=size=64x64:rate=4']
        if audio:args+=['-f','lavfi','-i','sine=frequency=440']
        result=subprocess.run(args+['-t','0.5','-c:v','libx264',str(path)],capture_output=True,creationflags=0x08000000)
        assert result.returncode==0,result.stderr
    loaded=[]; task=desktop.LoadTask(paths); task.loaded.connect(loaded.append); task.run()
    assert loaded and 'gif' in loaded[0]['targets'] and 'mp3' not in loaded[0]['targets']
    output,_=convert_batch(loaded[0],'gif',tmp_path/'result',{'clip_duration':.2,'gif_width':64,'gif_fps':4},lambda *v:None)
    with zipfile.ZipFile(output) as bundle:assert len([n for n in bundle.namelist() if n.endswith('.gif')])==2
