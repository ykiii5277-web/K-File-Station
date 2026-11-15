from pathlib import Path
import shutil
import zipfile
import io

import pytest
import numpy as np
import pymupdf
import tifffile
from PIL import Image

import converter
from image_converter import images_to_pdf


@pytest.fixture(scope='session')
def images(tmp_path_factory):
    folder=tmp_path_factory.mktemp('images')
    image=Image.new('RGBA',(96,64),(30,130,230,255)); image.putpixel((0,0),(255,0,0,0))
    for ext,fmt in [('png','PNG'),('tiff','TIFF'),('webp','WEBP'),('avif','AVIF')]: image.save(folder/('sample.'+ext),format=fmt)
    image.convert('RGB').save(folder/'sample.jpg',quality=95)
    (folder/'sample.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64"><rect x="8" y="8" width="80" height="48" fill="#1e82e6"/></svg>','utf-8')
    frames=[Image.new('RGB',(95,63),color) for color in ('red','green','blue')]
    frames[0].save(folder/'sample.gif',save_all=True,append_images=frames[1:],duration=[100,400,300],loop=0)
    for name in ('sample.dng','sample.heic'): shutil.copy2(Path(__file__).parent/'fixtures/images'/name,folder/name)
    return folder


EDGES=[(ext,target) for ext in converter.IMAGE_EXTENSIONS for target in converter.GRAPH[ext]]


@pytest.mark.parametrize('ext,target',EDGES)
def test_image_edges(images,tmp_path,ext,target):
    source=images/('sample.dng' if ext=='raw' else 'sample.'+ext)
    info=converter.validate(source,ext); assert info['width']>0
    events=[]
    output,notes=converter.convert(source,target,tmp_path/'result',{},lambda p,m:events.append(p))
    assert output.stat().st_size>10 and events[-1]==98
    if target=='pdf':
        with pymupdf.open(output) as doc:
            assert len(doc)==1 and doc[0].get_images()
    elif target=='mp4':
        import imageio_ffmpeg
        reader=imageio_ffmpeg.read_frames(str(output))
        metadata=next(reader); frames=list(reader)
        assert metadata['size']==(96,64) and len(frames)>=3
        assert .65<=metadata['duration']<=1.0
    else:
        with Image.open(output) as image:
            image.load(); assert min(image.size)>0
            if target=='ico': assert (16,16) in image.ico.sizes() and (256,256) in image.ico.sizes()
            elif target=='tiff' and ext=='raw':
                pixels=tifffile.imread(output); assert pixels.dtype==np.uint16 and pixels.shape[2]==3
            else:
                assert image.width>=96 and image.height>=64
                if target in ('png','webp') and ext in ('png','webp','tiff','svg'):
                    assert image.convert('RGBA').getpixel((0,0))[3]==0


def test_multipage_tiff_and_animated_webp(tmp_path):
    frames=[Image.new('RGBA',(64,48),color) for color in ('red','blue')]
    for ext,fmt in [('tiff','TIFF'),('webp','WEBP'),('avif','AVIF')]:
        source=tmp_path/('multi.'+ext)
        frames[0].save(source,format=fmt,save_all=True,append_images=frames[1:],duration=150)
        output,_=converter.convert(source,'png',tmp_path/ext,{},lambda *a:None)
        with zipfile.ZipFile(output) as archive:
            assert len(archive.namelist())==2
            with Image.open(io.BytesIO(archive.read(archive.namelist()[1]))) as image:
                assert image.convert('RGB').getpixel((10,10))[2]>200


def test_png_animation_preserved_in_webp(tmp_path):
    source=tmp_path/'animated.png'
    frames=[Image.new('RGBA',(48,32),color) for color in ('red','blue')]
    frames[0].save(source,save_all=True,append_images=frames[1:],duration=[100,300],loop=2)
    output,_=converter.convert(source,'webp',tmp_path/'webp',{},lambda *a:None)
    with Image.open(output) as image:
        assert image.n_frames==2 and image.info['loop']==2
        durations=[]
        for i in range(2): image.seek(i); image.load(); durations.append(image.info['duration'])
        assert durations==[100,300]


def test_jpeg_transparency_and_orientation(tmp_path):
    source=tmp_path/'alpha.png'; Image.new('RGBA',(64,48),(20,40,60,0)).save(source)
    output,_=converter.convert(source,'jpg',tmp_path/'jpg',{},lambda *a:None)
    with Image.open(output) as image: assert min(image.getpixel((10,10)))>245
    source=tmp_path/'oriented.jpg'; image=Image.new('RGB',(64,48),'red')
    exif=Image.Exif(); exif[274]=6; image.save(source,exif=exif)
    output,_=converter.convert(source,'png',tmp_path/'png',{},lambda *a:None)
    with Image.open(output) as image: assert image.size==(48,64)


def test_batch_pdf_order(images,tmp_path):
    first=tmp_path/'first.jpg'; Image.new('RGB',(96,64),'red').save(first)
    second=tmp_path/'second.png'; image=Image.new('RGBA',(96,64),'blue'); image.paste((0,0,0,0),(0,0,16,16)); image.save(second)
    output,_=images_to_pdf([first,second],tmp_path/'out',lambda *a:None)
    with pymupdf.open(output) as document:
        assert len(document)==2
        assert document[1].get_pixmap().pixel(0,0)==(255,255,255)
        assert document[0].get_pixmap().pixel(10,10)[0]>240
        assert document[1].get_pixmap().pixel(20,20)[2]>240


@pytest.mark.parametrize('ext',sorted(converter.IMAGE_EXTENSIONS))
def test_reject_renamed_text(tmp_path,ext):
    source=tmp_path/('broken.'+ext); source.write_text('not an image','utf-8')
    with pytest.raises(converter.ConversionError): converter.validate(source,ext)


@pytest.mark.parametrize('body',[
    '<image href="file:///secret.png"/>',
    '<style>@import "https://example.org/font.css";</style>',
    '<script>alert(1)</script>',
    '<rect style="fill:url(https://example.org/image.png)"/>',
])
def test_svg_external_resources_rejected(tmp_path,body):
    source=tmp_path/'external.svg'; source.write_text('<svg xmlns="http://www.w3.org/2000/svg">'+body+'</svg>','utf-8')
    with pytest.raises(converter.ConversionError): converter.validate(source,'svg')


def test_api_image_alias(images,tmp_path,monkeypatch):
    import app as server
    from fastapi.testclient import TestClient
    data=tmp_path/'data'; (data/'uploads').mkdir(parents=True)
    monkeypatch.setattr(server,'DATA',data)
    client=TestClient(server.app); client.headers['Authorization']='Bearer '+server.TOKEN
    result=client.post('/api/files',files={'file':('photo.JPEG',(images/'sample.jpg').read_bytes())})
    assert result.status_code==200 and result.json()['ext']=='jpg' and result.json()['targets']==['png','pdf','avif']
