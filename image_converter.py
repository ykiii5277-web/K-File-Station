"""Offline image conversion, including camera files and animated GIF export."""
from pathlib import Path
import base64
import io
import math
import queue
import re
import subprocess
import threading
import time
import warnings
import zipfile

from PIL import Image, ImageOps, UnidentifiedImageError
from converter import ConversionError

MAX_PIXELS=80_000_000
MAX_TOTAL_PIXELS=320_000_000


def check_size(width,height):
    if width<=0 or height<=0 or width*height>MAX_PIXELS or max(width,height)>32768:
        raise ConversionError('图片尺寸过大：单帧最多 8000 万像素，单边不超过 32768 像素。')


def svg_document(path):
    from lxml import etree
    import pymupdf
    data=path.read_bytes()
    if re.search(br'<!\s*(DOCTYPE|ENTITY)',data,re.I):
        raise ConversionError('SVG 含外部实体或文档声明，请另存为独立 SVG 后重试。')
    try:
        root=etree.fromstring(data,parser=etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
        if etree.QName(root).localname!='svg': raise ValueError('not svg')
        for node in root.iter():
            if not isinstance(node.tag,str): continue
            tag=etree.QName(node).localname
            if tag in ('script','foreignObject'):
                raise ConversionError('SVG 含脚本或外嵌网页，请先移除后重试。')
            values=list(node.attrib.values())+([node.text] if tag=='style' and node.text else [])
            for key,value in node.attrib.items():
                local=etree.QName(key).localname.lower()
                if local.startswith('on'): raise ConversionError('SVG 含脚本事件，请先移除后重试。')
                if local in ('href','src') and not value.startswith(('#','data:image/png;base64,','data:image/jpeg;base64,')):
                    raise ConversionError('SVG 含外部资源，请先将图片和字体嵌入文件。')
            for value in values:
                if '@import' in value.lower() or '\\' in value:
                    raise ConversionError('SVG 含外部样式或不支持的资源引用。')
                for match in re.finditer(r'url\(\s*[\"\']?(.*?)[\"\']?\s*\)',value,re.I):
                    if not match[1].startswith('#'): raise ConversionError('SVG 含外部资源，请先嵌入后重试。')
            if tag=='image':
                for value in node.attrib.values():
                    if value.startswith('data:image/'):
                        with Image.open(io.BytesIO(base64.b64decode(value.split(',',1)[1],validate=True))) as image:
                            check_size(*image.size)
        document=pymupdf.open(stream=etree.tostring(root),filetype='svg')
        rect=document[0].rect
        try: check_size(math.ceil(rect.width),math.ceil(rect.height))
        except Exception: document.close(); raise
        return document
    except ConversionError: raise
    except Exception as exc:
        raise ConversionError('无法读取 SVG，请检查矢量图是否完整。') from exc


def open_image(path,ext):
    if ext=='heic':
        from pillow_heif import register_heif_opener
        register_heif_opener(thumbnails=False)
    return Image.open(path)


def validate_image(path,ext):
    try:
        if ext=='svg':
            with svg_document(path) as document:
                return {'width':round(document[0].rect.width),'height':round(document[0].rect.height),'frames':1}
        if ext=='raw':
            import rawpy
            with rawpy.imread(str(path)) as raw:
                check_size(raw.sizes.width,raw.sizes.height)
                return {'width':raw.sizes.width,'height':raw.sizes.height,'frames':1}
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with open_image(path,ext) as image:
                actual={'jpg':'JPEG','png':'PNG','tiff':'TIFF','webp':'WEBP','heic':'HEIF','gif':'GIF','avif':'AVIF'}[ext]
                if image.format!=actual: raise ConversionError('图片内容与扩展名不符，请选择真实的 '+ext.upper()+' 文件。')
                frames=getattr(image,'n_frames',1)
                if frames>5000: raise ConversionError('图片帧数超过 5000，暂不支持此文件。')
                width,height=image.size; total=0; duration=0
                for i in range(frames):
                    image.seek(i); check_size(*image.size)
                    if ext=='avif':image.load()  # AVIF duration metadata is populated by the decoder.
                    total+=image.width*image.height
                    duration+=max(20,image.info.get('duration',100) or 100)
                    if total>MAX_TOTAL_PIXELS: raise ConversionError('多页或动画图片的总像素过多，最多支持 3.2 亿像素。')
                if ext=='gif' and duration>3_600_000: raise ConversionError('GIF 时长超过一小时，请先截取片段。')
                return {'width':width,'height':height,'frames':frames,'duration_ms':duration}
    except ConversionError: raise
    except Exception as exc:
        raise ConversionError('无法解码此图片，请确认文件完整且相机型号或编码受支持。') from exc


def rgb_on_white(image):
    rgba=image.convert('RGBA')
    result=Image.new('RGB',rgba.size,'white'); result.paste(rgba,mask=rgba.getchannel('A'))
    return result


def bundle_images(paths,directory):
    if len(paths)==1: return paths[0]
    output=directory/'result.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in paths: archive.write(path,path.name)
    return output


def images_to_pdf(paths,directory,progress):
    import pymupdf
    from converter import normalize_extension
    directory.mkdir(parents=True,exist_ok=True)
    output=directory/'result.pdf'; notes=[]
    with pymupdf.open() as document:
        for i,path in enumerate(paths):
            ext=normalize_extension(path.suffix)
            if ext not in ('jpg','png'): raise ConversionError('多图合并 PDF 仅支持 JPG / JPEG 和 PNG。')
            info=validate_image(path,ext)
            if len(document)+info['frames']>500: raise ConversionError('合并 PDF 最多支持 500 页。')
            with open_image(path,ext) as image:
                for frame in range(info['frames']):
                    image.seek(frame); rgb=rgb_on_white(ImageOps.exif_transpose(image))
                    stream=io.BytesIO(); rgb.save(stream,format='PNG')
                    page=document.new_page(width=rgb.width*72/150,height=rgb.height*72/150)
                    page.insert_image(page.rect,stream=stream.getvalue())
                    progress(15+int(78*(i+(frame+1)/info['frames'])/len(paths)),f'正在合并第 {i+1} / {len(paths)} 张图片')
            if info['frames']>1: notes.append('多帧 PNG 已按帧拆分为 PDF 页面。')
        document.save(output,deflate=True)
    progress(98,'正在保存 PDF')
    return output,notes


def gif_to_mp4(source,output,duration_ms,progress):
    import imageio_ffmpeg
    # Prefer the wheel's bundled binary, independently of machine PATH settings.
    binaries=Path(imageio_ffmpeg.__file__).parent/'binaries'
    binary=next(binaries.glob('ffmpeg*.exe'),None) or Path(imageio_ffmpeg.get_ffmpeg_exe())
    args=[str(binary),'-hide_banner','-loglevel','error','-nostdin','-y','-ignore_loop','1','-i',str(source),
          '-an','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-pix_fmt','yuv420p',
          '-fps_mode','vfr','-movflags','+faststart','-progress','pipe:1','-nostats',str(output)]
    lines=queue.Queue()
    with (output.parent/'ffmpeg-errors.txt').open('w',encoding='utf-8') as errors:
        process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors,text=True,
                                 creationflags=0x08000000 if __import__('os').name=='nt' else 0)
        def read_lines():
            for line in process.stdout: lines.put(line.strip())
            lines.put(None)
        reader=threading.Thread(target=read_lines,daemon=True); reader.start()
        deadline=time.monotonic()+240
        try:
            while True:
                if time.monotonic()>deadline: raise ConversionError('GIF 转换超时，请缩短动画后重试。')
                try: line=lines.get(timeout=.25)
                except queue.Empty: continue
                if line is None: break
                if line.startswith('out_time_us='):
                    try: percent=15+int(78*min(1,int(line.split('=',1)[1])/(duration_ms*1000)))
                    except ValueError: continue
                    progress(percent,'正在编码 GIF 动画为 MP4')
            if process.wait(timeout=10): raise ConversionError('GIF 视频编码失败，请检查动画内容。')
        finally:
            if process.poll() is None: process.kill(); process.wait()
            reader.join(timeout=2); process.stdout.close()


def convert_image(source,ext,target,directory,options,progress):
    info=validate_image(source,ext); output=directory/('result.'+target); notes=[]
    if target=='pdf': return images_to_pdf([source],directory,progress)
    if ext=='gif':
        gif_to_mp4(source,output,info['duration_ms'],progress)
        return output,['视频无音轨；透明区域显示为黑色，GIF 循环次数不写入视频。']
    if ext=='svg':
        import pymupdf
        scale=options.get('svg_scale',2)
        if scale not in (1,2,3): raise ConversionError('SVG 栅格化倍率只能为 1、2 或 3。')
        with svg_document(source) as document:
            rect=document[0].rect; check_size(math.ceil(rect.width*scale),math.ceil(rect.height*scale))
            progress(40,'正在栅格化 SVG')
            document[0].get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=True).save(output)
        return output,['SVG 已栅格化，输出 PNG 不再包含可编辑的矢量路径。']
    if ext=='raw':
        import rawpy
        progress(30,'正在显影相机 RAW')
        with rawpy.imread(str(source)) as raw:
            rgb=raw.postprocess(use_camera_wb=True,output_bps=16 if target=='tiff' else 8)
        progress(85,'正在编码显影结果')
        if target=='tiff':
            import tifffile
            tifffile.imwrite(output,rgb,photometric='rgb',metadata=None)
        else: Image.fromarray(rgb).save(output,format='JPEG',quality=95,subsampling=0)
        return output,['已使用相机白平衡显影为 sRGB；RAW 原始传感器数据未写入输出。']
    frames=[]; durations=[]
    with open_image(source,ext) as image:
        loop=image.info.get('loop',0)
        count=1 if target=='ico' else info['frames']
        for i in range(count):
            image.seek(i)
            frames.append(ImageOps.exif_transpose(image).copy())
            durations.append(max(20,image.info.get('duration',100) or 100))
            progress(15+int(45*(i+1)/count),f'正在读取第 {i+1} / {count} 帧')
    if target=='ico':
        progress(65,'正在生成多尺寸 ICO 图标')
        rgba=frames[0].convert('RGBA'); rgba.thumbnail((256,256),Image.Resampling.LANCZOS)
        square=Image.new('RGBA',(256,256)); square.paste(rgba,((256-rgba.width)//2,(256-rgba.height)//2))
        square.save(output,format='ICO',sizes=[(n,n) for n in (16,24,32,48,64,128,256)])
        if info['frames']>1: notes.append('ICO 为静态图标，仅使用第一帧。')
    elif target in ('tiff','webp','avif'):
        progress(65,'正在编码 '+target.upper()+' 图片')
        frames=[frame.convert('RGBA') for frame in frames]
        kwargs={'format':'TIFF','compression':'tiff_deflate'} if target=='tiff' else {'format':'WEBP','lossless':True,'duration':durations,'loop':loop}
        if target=='avif':kwargs={'format':'AVIF','quality':85,'speed':6,'max_threads':4,'duration':[round(v) for v in durations],'loop':loop}
        frames[0].save(output,save_all=len(frames)>1,append_images=frames[1:],**kwargs)
        if target=='avif':notes.append('AVIF 以8位有损编码保存，保留透明度与多帧时长；不保留HDR或更高位深。')
    else:
        paths=[]
        for i,frame in enumerate(frames):
            path=output if len(frames)==1 else directory/f'frame-{i+1:04d}.{target}'
            if target=='jpg': rgb_on_white(frame).save(path,format='JPEG',quality=95,subsampling=0)
            else:
                if frame.mode not in ('1','L','LA','P','RGB','RGBA','I','I;16'): frame=frame.convert('RGBA')
                frame.save(path,format='PNG')
            paths.append(path); progress(60+int(33*(i+1)/len(frames)),f'正在保存第 {i+1} / {len(frames)} 帧')
        output=bundle_images(paths,directory)
        if len(paths)>1: notes.append(f'{len(paths)} 帧 / 页已分别导出并打包 ZIP，不保留动画播放时序。')
    return output,notes
