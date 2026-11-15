"""Plain text, Markdown PDF and safe, self-contained EPUB imports."""
from pathlib import PurePosixPath
import base64,html,io,posixpath,re,zipfile
from urllib.parse import urlsplit,unquote
from lxml import etree
from converter import ConversionError,read_text,safe_html,pandoc,office_pdf,validate


def book_path(base,reference):
    reference=unquote(reference)
    url=urlsplit(reference)
    if url.scheme or url.netloc or '\\' in reference:raise ConversionError('EPUB资源必须位于书籍内部。')
    path=posixpath.normpath(posixpath.join(posixpath.dirname(base),url.path))
    if path.startswith(('../','/')) or path=='..' or ':' in path:raise ConversionError('EPUB含越界资源路径。')
    return path


def xml_entry(archive,path):
    data=archive.read(path)
    if re.search(br'<!\s*(DOCTYPE|ENTITY)',data,re.I):raise ConversionError('EPUB目录声明不支持DTD或实体。')
    return etree.fromstring(data,etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))


def epub_layout(archive):
    if archive.read('mimetype').strip()!=b'application/epub+zip':raise ConversionError('EPUB的mimetype声明不正确。')
    if 'META-INF/encryption.xml' in archive.namelist():raise ConversionError('此EPUB含加密资源，请先在原软件中导出无加密版本。')
    root=xml_entry(archive,'META-INF/container.xml')
    paths=root.xpath('//*[local-name()="rootfile"]/@full-path')
    if not paths:raise ConversionError('EPUB缺少书籍目录。')
    opf=book_path('',paths[0]); package=xml_entry(archive,opf)
    manifest={node.get('id'):book_path(opf,node.get('href','')) for node in package.xpath('//*[local-name()="manifest"]/*[local-name()="item"]')}
    spine=[manifest[node.get('idref')] for node in package.xpath('//*[local-name()="spine"]/*[local-name()="itemref"]') if node.get('idref') in manifest and node.get('linear','yes')!='no']
    if not spine:raise ConversionError('EPUB缺少有效的阅读顺序。')
    names=set(archive.namelist())
    if any(path not in names for path in spine):raise ConversionError('EPUB章节缺失。')
    title=package.xpath('//*[local-name()="title"]/text()')
    return spine,title[0] if title else '电子书'


def validate_epub(path):
    try:
        with zipfile.ZipFile(path) as archive:spine,_=epub_layout(archive)
        return {'chapters':len(spine)}
    except ConversionError:raise
    except Exception as exc:raise ConversionError('无法读取EPUB目录或阅读顺序。') from exc


def epub_html(source,progress):
    from bs4 import BeautifulSoup
    from PIL import Image,ImageOps
    from image_converter import check_size
    parts=[]; pixels=0; image_bytes=0
    with zipfile.ZipFile(source) as archive:
        spine,title=epub_layout(archive)
        for index,path in enumerate(spine):
            soup=BeautifulSoup(archive.read(path),'html.parser')
            for image in soup.find_all('img'):
                src=image.get('src','')
                if not src or urlsplit(src).scheme or urlsplit(src).netloc:image.decompose();continue
                resource=book_path(path,src)
                if resource not in archive.namelist():image.decompose();continue
                try:
                    with Image.open(io.BytesIO(archive.read(resource))) as bitmap:
                        check_size(*bitmap.size);pixels+=bitmap.width*bitmap.height
                        if pixels>320_000_000:raise ConversionError('EPUB插图总像素超过3.2亿。')
                        buffer=io.BytesIO();ImageOps.exif_transpose(bitmap).convert('RGBA').save(buffer,format='PNG')
                    image_bytes+=buffer.tell()
                    if image_bytes>80*1024**2:raise ConversionError('EPUB嵌入插图超过80 MB，请缩小图片后重试。')
                    image['src']='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')
                except ConversionError:raise
                except Exception:raise ConversionError('EPUB包含无法解码的插图，请移除或转成PNG/JPG。') from None
            body=soup.body or soup
            parts.append('<section>'+safe_html(''.join(str(node) for node in body.contents))+'</section>')
            progress(15+int(45*(index+1)/len(spine)),f'正在导入EPUB章节 {index+1}/{len(spine)}')
    return '<!doctype html><html><head><meta charset="utf-8"><title>'+html.escape(title)+'</title></head><body>'+''.join(parts)+'</body></html>'


def convert_office_extra(source,ext,target,directory,options,progress):
    output=directory/('result.'+target)
    if ext=='txt':
        from docx import Document
        document=Document()
        for line in read_text(source).splitlines():document.add_paragraph(line)
        normalized=output if target=='docx' else directory/'plain.docx'
        document.save(normalized);progress(55,'正在保存纯文本文档')
        if target=='pdf':office_pdf(normalized,output)
        notes=['按原文段落导入，符号和Markdown标记作为普通文字保留。']
    elif ext=='md':
        from converter import convert
        normalized,_=convert(source,'docx',directory/'markdown',options,lambda n,t:progress(min(60,int(n*.6)),t))
        progress(65,'正在将Markdown排版为PDF');office_pdf(normalized,output)
        notes=['按Markdown结构排版，不读取文件外部图片或网络资源。']
    else:
        validate(source,'epub');content=epub_html(source,progress)
        normalized=directory/'content.html';normalized.write_text(content,'utf-8')
        if target=='html':output.write_text(content,'utf-8')
        else:progress(70,'正在转换电子书结构');pandoc(normalized,'docx',output)
        notes=['按EPUB阅读顺序合并正文并嵌入支持的插图；保留基本结构，复杂样式可能简化，不加载外部资源。']
    progress(98,'正在保存文档');return output,notes
