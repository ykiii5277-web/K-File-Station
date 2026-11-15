"""Synthetic end-to-end coverage of all v0.10 conversion directions, also frozen."""
from pathlib import Path
import io,json,shutil,subprocess,tempfile,zipfile
import converter

NEW={'mp3':['wav'],'m4a':['mp3','wav'],'aac':['mp3','wav'],
     'mov':['mp3','wav'],'mkv':['mp3','wav'],'webm':['mp3','wav'],
     'webp':['jpg'],'heic':['png'],'avif':['jpg','png'],'jpg':['avif'],'png':['avif'],
     'txt':['docx','pdf'],'md':['pdf'],'epub':['docx','html'],
     'json':['xlsx','jsonl'],'xlsx':['json'],'jsonl':['json'],'csv':['tsv'],'tsv':['csv']}


def samples(folder):
    from PIL import Image
    from openpyxl import Workbook
    from media_converter import binary
    folder.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGBA',(96,64),(30,120,210,255));image.paste((10,20,30,0),(0,0,16,16))
    for ext,fmt in [('png','PNG'),('webp','WEBP'),('avif','AVIF')]:image.save(folder/('sample.'+ext),format=fmt)
    image.convert('RGB').save(folder/'sample.jpg')
    from pillow_heif import from_pillow
    from_pillow(image).save(folder/'sample.heic')
    (folder/'sample.txt').write_text('中文文字 123\n第二段 <hello> =1+1','utf-8')
    (folder/'sample.md').write_text('# 中文标题 123\n\n- 苹果\n- 第二项\n','utf-8')
    records=[{'编号':'001','值':12,'有效':True,'空':None,'公式':'=1+1'},{'编号':'002','值':34,'有效':False,'空':None,'公式':'text'}]
    (folder/'sample.json').write_text(json.dumps(records,ensure_ascii=False),'utf-8')
    (folder/'sample.jsonl').write_text('\n'.join(json.dumps(v,ensure_ascii=False) for v in records)+'\n','utf-8')
    for ext,separator in [('csv',','),('tsv','\t')]:
        import csv
        with (folder/('sample.'+ext)).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream,delimiter=separator);writer.writerow(['编号','值']);writer.writerow(['001','12'])
    book=Workbook();sheet=book.active;sheet.title='第一张';sheet.append(['编号','值']);sheet.append(['wrong',0])
    sheet=book.create_sheet('第二张');sheet.append(['编号','值']);sheet.append(['001',12]);book.save(folder/'sample.xlsx');book.close()
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    with zipfile.ZipFile(folder/'sample.epub','w') as archive:
        archive.writestr('mimetype','application/epub+zip')
        archive.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        archive.writestr('OEBPS/content.opf','<package><metadata><title>测试123</title></metadata><manifest><item id="b" href="two.xhtml"/><item id="a" href="one.xhtml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
        archive.writestr('OEBPS/one.xhtml','<html><body><h1>第一章 123</h1><p>中文内容</p><img src="images/picture.png"/><img src="https://example.invalid/no.png"/><script>bad()</script></body></html>')
        archive.writestr('OEBPS/two.xhtml','<html><body><h1>第二章 456</h1></body></html>')
        archive.writestr('OEBPS/images/picture.png',buffer.getvalue())
    def ff(args):
        result=subprocess.run([binary(),'-v','error','-y',*args],capture_output=True,creationflags=0x08000000)
        assert result.returncode==0,result.stderr
    ff(['-f','lavfi','-i','testsrc2=size=96x64:rate=10','-f','lavfi','-i','sine=frequency=440','-t','0.6','-c:v','libx264','-c:a','aac',str(folder/'seed.mp4')])
    for ext,codec in [('mp3','libmp3lame'),('m4a','aac'),('aac','aac')]:ff(['-i',str(folder/'seed.mp4'),'-vn','-c:a',codec,str(folder/('sample.'+ext))])
    for ext,args in [('mov',['-c','copy']),('mkv',['-c','copy']),('webm',['-c:v','libvpx-vp9','-c:a','libopus'])]:ff(['-i',str(folder/'seed.mp4'),*args,str(folder/('sample.'+ext))])
    return folder


def verify_output(path,target,ext):
    from PIL import Image
    from docx import Document
    from openpyxl import load_workbook
    assert path.stat().st_size>10
    if target in ('jpg','png','avif'):
        with Image.open(path) as image:
            image.load();assert image.size==(96,64)
            if target=='jpg' and ext=='webp':assert min(image.getpixel((0,0)))>220
            if target=='png':assert image.convert('RGBA').getpixel((0,0))[3]<5
    elif target in ('mp3','wav'):
        from media_converter import probe
        info=probe(path);assert info['has_audio'] and not info['has_video']
    elif target=='docx':
        doc=Document(path);text='\n'.join(p.text for p in doc.paragraphs);assert '123' in text
        if ext=='epub':assert text.index('第一章')<text.index('第二章') and len(doc.inline_shapes)==1
    elif target=='pdf':
        import pymupdf
        with pymupdf.open(path) as document:assert '123' in ''.join(p.get_text() for p in document)
    elif target=='html':
        text=path.read_text('utf-8');assert text.index('第一章')<text.index('第二章') and 'data:image/png;base64,' in text and 'bad()' not in text and 'https://example.invalid/' not in text
    elif target=='xlsx':
        book=load_workbook(path);sheet=book.active
        assert sheet['A2'].value=='001' and sheet['B2'].value==12 and sheet['C2'].value is True and sheet['E2'].data_type=='s';book.close()
    elif target=='json':
        value=json.loads(path.read_text('utf-8'));assert value[0]['编号']=='001' and value[0]['值']==12
    elif target=='jsonl':assert json.loads(path.read_text('utf-8').splitlines()[0])['编号']=='001'
    else:
        import csv
        with path.open(encoding='utf-8-sig',newline='') as stream:assert list(csv.reader(stream,delimiter='\t' if target=='tsv' else ','))[1]==['001','12']


def run_checks(report):
    report=Path(report);report.mkdir(parents=True,exist_ok=True);records=[]
    with tempfile.TemporaryDirectory(prefix='K 扩展转换 ') as temporary:
        root=Path(temporary);folder=samples(root/'fixtures')
        for ext,targets in NEW.items():
            for target in targets:
                source=folder/('sample.'+ext);converter.validate(source,ext)
                output,notes=converter.convert(source,target,root/(ext+'-'+target),{'sheet':'第二张'},lambda *v:None)
                verify_output(output,target,ext);records.append({'source':ext,'target':target,'bytes':output.stat().st_size});print(ext+' -> '+target+': PASS',flush=True)
        from PIL import Image
        frames=[Image.new('RGBA',(64,48),color) for color in ('red','blue')];animated=root/'animated.png'
        frames[0].save(animated,save_all=True,append_images=frames[1:],duration=[120,280],loop=2)
        avif,_=converter.convert(animated,'avif',root/'animated-avif',{},lambda *v:None)
        info=converter.validate(avif,'avif');assert info['frames']==2 and abs(info['duration_ms']-400)<30
        png,_=converter.convert(avif,'png',root/'animated-png',{},lambda *v:None)
        with zipfile.ZipFile(png) as archive:assert len(archive.namelist())==2
    assert len(records)==28
    (report/'extra-check.json').write_text(json.dumps({'status':'passed','checks':records,'animated_avif':True},ensure_ascii=False,indent=2),'utf-8')
    return records


if __name__=='__main__':run_checks(Path('docs/extra-portable-v10'))
