import io,json,threading,tarfile,zipfile
from pathlib import Path
import pytest
import converter,archive_bridge
from extended_check import NEW,samples,verify_output


@pytest.fixture(scope='session')
def extra_samples(tmp_path_factory):return samples(tmp_path_factory.mktemp('new-formats'))


@pytest.mark.parametrize('ext,target',[(ext,t) for ext,targets in NEW.items() for t in targets])
def test_new_directions(extra_samples,tmp_path,ext,target):
    path=extra_samples/('sample.'+ext);converter.validate(path,ext)
    output,_=converter.convert(path,target,tmp_path/'out',{'sheet':'第二张'},lambda *v:None)
    verify_output(output,target,ext)


@pytest.mark.parametrize('name,mode',[('test.tar','w'),('test.tar.gz','w:gz'),('test.tar.xz','w:xz'),('test.tgz','w:gz'),('test.txz','w:xz')])
def test_tar_complete_extract(tmp_path,name,mode):
    path=tmp_path/name
    with tarfile.open(path,mode) as archive:
        entry=tarfile.TarInfo('nested/中文.txt');entry.size=5;archive.addfile(entry,io.BytesIO(b'hello'))
    before=path.read_bytes();events=[]
    assert not archive_bridge.inspect_archive(path,threading.Event())['encrypted']
    one=archive_bridge.recover_archive(path,{},False,True,tmp_path/'out',threading.Event(),lambda *v:events.append(v),lambda *v:None)
    two=archive_bridge.recover_archive(path,{},False,True,tmp_path/'out',threading.Event(),lambda *v:None,lambda *v:None)
    assert one['destination']!=two['destination'] and path.read_bytes()==before
    assert (one['destination']/'nested/中文.txt').read_bytes()==b'hello' and events[-1][1]['tested']==5


@pytest.mark.parametrize('name,type',[('../escape.txt',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('C:/drive',tarfile.REGTYPE),('file:stream',tarfile.REGTYPE),('CON.txt',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('hard',tarfile.LNKTYPE),('device',tarfile.CHRTYPE)])
def test_tar_reject_unsafe(tmp_path,name,type):
    path=tmp_path/'unsafe.tar'
    with tarfile.open(path,'w') as archive:
        entry=tarfile.TarInfo(name);entry.type=type;entry.linkname='../escape';archive.addfile(entry)
    with pytest.raises(converter.ConversionError):archive_bridge.inspect_archive(path,threading.Event())
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('content',['{"a":1}\n\n{"a":2}','{"a":1,"a":2}','{"a":NaN}','[broken]'])
def test_bad_jsonl(tmp_path,content):
    path=tmp_path/'a.jsonl';path.write_text(content,'utf-8')
    with pytest.raises(converter.ConversionError,match='JSONL'):converter.validate(path,'jsonl')


def test_excel_nested_large_numbers_and_limits(tmp_path):
    from openpyxl import load_workbook
    path=tmp_path/'data.json';path.write_text(json.dumps({'data':[{'id':1234567890123456789,'nested':{'x':1},'literal':'=1+1'}]}))
    output,_=converter.convert(path,'xlsx',tmp_path/'out',{'records_path':'data'},lambda *v:None)
    book=load_workbook(output);assert book.active['A2'].value=='1234567890123456789' and book.active['C2'].data_type=='s';book.close()
    with pytest.raises(converter.ConversionError,match='嵌套'):converter.convert(path,'xlsx',tmp_path/'reject',{'records_path':'data','nested_csv':'reject'},lambda *v:None)
    path.write_text(json.dumps([{'long':'a'*32768}]))
    with pytest.raises(converter.ConversionError,match='过长'):converter.convert(path,'xlsx',tmp_path/'long',{},lambda *v:None)


def test_excel_header_validation(tmp_path):
    from openpyxl import Workbook
    path=tmp_path/'bad.xlsx';book=Workbook();book.active.append(['id','id']);book.active.append([1,2]);book.save(path);book.close()
    with pytest.raises(converter.ConversionError,match='表头'):converter.convert(path,'json',tmp_path/'out',{},lambda *v:None)


@pytest.mark.parametrize('reference',['../../outside.xhtml','file:///secret.xhtml','https://example.invalid/a.xhtml'])
def test_epub_reject_external_spine(extra_samples,tmp_path,reference):
    path=tmp_path/'unsafe.epub'
    with zipfile.ZipFile(extra_samples/'sample.epub') as original,zipfile.ZipFile(path,'w') as archive:
        for name in original.namelist():archive.writestr(name,original.read(name).replace(b'one.xhtml',reference.encode()) if name.endswith('.opf') else original.read(name))
    with pytest.raises(converter.ConversionError):converter.validate(path,'epub')


def test_epub_reject_encryption(extra_samples,tmp_path):
    import shutil
    path=tmp_path/'locked.epub';shutil.copy2(extra_samples/'sample.epub',path)
    with zipfile.ZipFile(path,'a') as archive:archive.writestr('META-INF/encryption.xml','<encryption/>')
    with pytest.raises(converter.ConversionError,match='加密'):converter.validate(path,'epub')


def test_animated_avif_roundtrip(tmp_path):
    from PIL import Image
    path=tmp_path/'animated.png';frames=[Image.new('RGBA',(64,48),color) for color in ('red','blue')]
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=[120,280],loop=2)
    output,_=converter.convert(path,'avif',tmp_path/'avif',{},lambda *v:None)
    info=converter.validate(output,'avif');assert info['frames']==2 and abs(info['duration_ms']-400)<30
    output,_=converter.convert(output,'png',tmp_path/'png',{},lambda *v:None)
    with zipfile.ZipFile(output) as archive:assert len(archive.namelist())==2


def test_documented_graph_and_search():
    from search_help import search_description,SEARCH_COMMON
    assert sum(map(len,converter.GRAPH.values()))==92
    quick=search_description('quick');deep=search_description('deep')
    assert quick.index('1–6位')<quick.index('1–4位')<quick.index('1–3位')
    assert '1,828,598' in quick and '1–12位' in deep and '预计较短' in deep and '本次执行快速搜索' in SEARCH_COMMON
