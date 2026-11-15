"""Local conversion engines. The graph deliberately follows 转化示意图.png."""
from __future__ import annotations

import csv
import html
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from typing import Callable

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
HOME = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
GRAPH = {
    'doc': ['docx', 'pdf', 'md', 'txt'],
    'docx': ['doc', 'md', 'pdf', 'txt'],
    'md': ['docx', 'html', 'pdf'],
    'html': ['md', 'epub', 'pdf'],
    'pdf': ['docx', 'txt', 'xlsx', 'png'],
    'xls': ['xlsx', 'pdf', 'csv'],
    'xlsx': ['xls', 'pdf', 'csv', 'json'],
    'ppt': ['pptx', 'pdf'],
    'pptx': ['ppt', 'pdf'],
    'csv': ['xlsx','json','tsv'],
    'json':['yaml','xml','csv','xlsx','jsonl'],
    'yaml':['json'],
    'xml':['json'],
    'mp4':['webm','mkv','mov','m4a','aac','mp3','wav','gif'],
    'webm':['mp4','mp3','wav'],
    'mkv':['mp4','mp3','wav'],
    'mov':['mp4','mp3','wav'],
    'wav':['m4a','aac','mp3','flac'],
    'flac':['wav'],
    'txt': ['docx','pdf'],
    'epub': ['docx','html'],
    'jpg': ['png', 'pdf', 'avif'],
    'png': ['jpg', 'tiff', 'webp', 'ico', 'pdf', 'avif'],
    'tiff': ['png'],
    'webp': ['png','jpg'],
    'raw': ['jpg', 'tiff'],
    'heic': ['jpg','png'],
    'svg': ['png'],
    'gif': ['mp4'],
    'avif':['jpg','png'],
    'mp3':['wav'], 'm4a':['mp3','wav'], 'aac':['mp3','wav'],
    'jsonl':['json'], 'tsv':['csv'],
}
IMAGE_EXTENSIONS = frozenset(('jpg','png','tiff','webp','raw','heic','svg','gif','avif'))
DATA_EXTENSIONS=frozenset(('json','yaml','xml','csv','jsonl','tsv'))
MEDIA_EXTENSIONS=frozenset(('mp4','webm','mkv','mov','wav','flac','mp3','m4a','aac'))
RAW_EXTENSIONS = ('raw','dng','cr2','cr3','nef','nrw','arw','srf','sr2','raf','orf','rw2','pef','srw','3fr','fff','rwl','iiq','kdc','mos','mrw')
EXTENSION_ALIASES = {'ndjson':'jsonl','yml':'yaml','htm':'html','jpeg':'jpg','jpe':'jpg','tif':'tiff','heif':'heic',**{ext:'raw' for ext in RAW_EXTENSIONS}}


def normalize_extension(extension):
    extension=extension.lower().lstrip('.')
    return EXTENSION_ALIASES.get(extension,extension)


def module_for(extension):
    ext=normalize_extension(extension)
    return 1 if ext in IMAGE_EXTENSIONS else 2 if ext in DATA_EXTENSIONS else 3 if ext in MEDIA_EXTENSIONS else 0


def targets_for(ext,info):
    targets=list(GRAPH.get(ext,[]))
    if ext in MEDIA_EXTENSIONS and not info.get('has_audio',True):
        targets=[t for t in targets if t not in ('m4a','aac','mp3','wav','flac')]
    return targets


LABELS_EXTRA={'json':'JSON 数据','yaml':'YAML 数据','xml':'XML 数据','webm':'WebM 视频','mkv':'Matroska 视频','mov':'QuickTime 视频','wav':'WAV PCM 音频','flac':'FLAC 无损音频','m4a':'M4A AAC 音频','aac':'AAC 音频','mp3':'MP3 音频'}
LABELS = {'docx': 'Word 文档', 'md': 'Markdown', 'html': 'HTML 网页', 'pdf': 'PDF 文档',
          'doc': 'Word 97–2003', 'xls': 'Excel 97–2003', 'ppt': 'PowerPoint 97–2003',
          'xlsx': 'Excel 工作簿', 'pptx': 'PowerPoint', 'csv': 'CSV 表格', 'txt': '纯文本',
          'epub': 'EPUB 电子书', 'png': 'PNG 图片', 'jpg':'JPEG 图片', 'tiff':'TIFF 图像',
          'webp':'WebP 图片', 'raw':'相机 RAW', 'heic':'HEIC / HEIF 图片', 'svg':'SVG 矢量图',
          'gif':'GIF 动画', 'ico':'ICO 图标', 'mp4':'MP4 视频'}
NOTES = {
    'docx:md': '转换标题、列表、表格等文档结构；复杂排版可能简化。含图片时打包为 ZIP。',
    'md:docx': '保留标题、列表和表格等结构；独立文件中的本地及网络图片链接不读取。',
    'md:html': '生成可独立打开的 HTML 网页；不读取外部资源。',
    'html:md': '提取网页内容和结构，移除脚本与外部资源。',
    'html:epub': '生成可重排的电子书；移除脚本与外部资源。',
    'html:pdf': '将网页内容打印为 PDF；移除脚本与外部资源。',
    'pdf:docx': '尽量重建可编辑版面。扫描页使用中英文 OCR，识别文字按阅读顺序输出，复杂版式可能变化。',
    'pdf:txt': '提取文字；扫描页自动使用中英文 OCR。',
    'pdf:xlsx': '提取可识别的表格，每张表单独一个工作表；扫描表格使用 OCR 估计行列，请核对结果。',
    'pdf:png': '按页渲染为 PNG；多页文件自动打包为 ZIP。',
    'xlsx:csv': '仅导出选定工作表的值，不包含样式；公式使用文件中已缓存的计算结果。',
    'csv:xlsx': '自动识别 UTF-8 / GB18030 编码与常用分隔符，单元格按文本导入。',
    'jpg:png':'无损解码为 PNG，不会恢复 JPEG 已丢失的细节。',
    'jpg:pdf':'图片作为完整页面保存；可同时选择或拖入多张 JPG / PNG 合并 PDF。',
    'png:pdf':'透明区域以白色铺底，图片作为完整页面保存；支持多图合并。',
    'png:jpg':'以白色填充透明区域，按 95% JPEG 质量保存。',
    'png:tiff':'保存为 TIFF；多帧 PNG 会保存为多页 TIFF。',
    'png:webp':'无损 WebP 编码，保留透明度与动画帧。',
    'png:ico':'生成 16–256 像素的多尺寸图标，保持比例并透明补边。',
    'tiff:png':'多页 TIFF 按页转换 PNG 并打包 ZIP。',
    'webp:png':'保留透明度；动画 WebP 按帧输出 PNG 并打包 ZIP。',
    'raw:jpg':'使用离线 RAW 引擎与相机白平衡显影为 sRGB JPEG。',
    'raw:tiff':'显影为 16 位 RGB TIFF；不会保留相机原始马赛克数据。',
    'heic:jpg':'离线解码 HEIC / HEIF；多图文件按图导出并打包。',
    'svg:png':'将 SVG 栅格化为透明 PNG；仅使用文件内的矢量和内嵌位图。',
    'gif:mp4':'保留动画时长，编码为无音轨 MP4；透明区域在视频中显示为黑色。',
}
LABELS_EXTRA.update({'avif':'AVIF 图片','jsonl':'JSON Lines','tsv':'制表符分隔表格'})
LABELS.update(LABELS_EXTRA)
NOTES.update({'csv:json':'表头映射为对象键，记录保存为数组；所有 CSV 值保留为文本，避免丢失前导零。',
 'json:csv':'导出对象记录数组；可指定记录路径，嵌套字段可保存为 JSON 文本或拒绝转换。',
 'json:yaml':'转换为兼容 JSON 类型的 YAML，保留中文、数字、布尔值和空值。',
 'yaml:json':'只接受安全、兼容 JSON 的数据；拒绝重复键、别名及自定义标签。',
 'xml:json':'属性使用 @ 前缀、文本使用 #text，同名元素映射为数组；可选择仅保留元素。',
 'json:xml':'按 @属性 / #text 约定映射为 XML；可设置根元素名。',
 'mp4:gif':'按起始秒数和时长截取动图，可设置帧率和宽度；GIF 不含声音。'})
NOTES.update({'txt:docx':'按原文段落导入，符号与标记作为普通文字保存。','txt:pdf':'将纯文字按段落排版为PDF。',
 'md:pdf':'按Markdown结构排版导出PDF，不加载外部图片和网络资源。',
 'epub:html':'按书籍阅读顺序合并正文和书内插图，生成独立HTML。','epub:docx':'按阅读顺序转换章节和书内插图，复杂样式可能简化。',
 'webp:jpg':'透明区域铺白；动画按帧导出并打包ZIP。','heic:png':'解码HEIC/HEIF并保留透明度，多图按图打包。',
 'json:xlsx':'对象记录数组转Excel；可指定记录路径，字符串按文本保存，嵌套值默认保存JSON文本。',
 'xlsx:json':'首行为表头，导出所选工作表，公式使用缓存值，日期转ISO文本。',
 'json:jsonl':'数组每个元素输出为一行JSON，可指定记录路径。','jsonl:json':'每行一个JSON值，合并为数组；拒绝空白行与重复键。',
 'csv:tsv':'保留字段文本、前导零和引用规则，输出制表符分隔表格。','tsv:csv':'制表符分隔表格转逗号分隔表格，字段按文本保留。'})
for _source in ('jpg','png'):NOTES[_source+':avif']='8位有损AVIF编码，保留透明度与多帧时长，不保留HDR或高位深。'
for _target in ('jpg','png'):NOTES['avif:'+_target]='解码AVIF，多帧按帧输出ZIP；JPG透明区域铺白。'
for _source in ('mp3','m4a','aac','mov','mkv','webm'):
    for _target in ('mp3','wav'):
        if _target in GRAPH[_source]:NOTES[_source+':'+_target]='导出首条音轨；MP3采用有损编码，WAV采用16位PCM，不会恢复源文件已丢失的信息。'


class ConversionError(Exception):
    pass


def executable(name: str) -> Path | None:
    candidates = {
        'pandoc': [HOME / 'engines/pandoc/pandoc.exe', ROOT / 'engines/pandoc/pandoc.exe'],
        'office': [HOME / 'engines/libreoffice/program/soffice.com', HOME / 'engines/libreoffice/program/soffice.exe',
                   ROOT / 'engines/libreoffice/program/soffice.com',
                   Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'LibreOffice/program/soffice.com'],
    }[name]
    for path in candidates:
        if path.is_file():
            return path
    found = shutil.which('pandoc' if name == 'pandoc' else 'soffice')
    return Path(found) if found else None


def capabilities() -> dict:
    from importlib.util import find_spec
    return {'pandoc': bool(executable('pandoc')), 'office': bool(executable('office')),
            'ocr':find_spec('rapidocr') is not None, 'heic':find_spec('pillow_heif') is not None,
            'raw':find_spec('rawpy') is not None, 'gif_video':find_spec('imageio_ffmpeg') is not None}


def run(args: list, cwd: Path, timeout: int = 180):
    try:
        result = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True,
                                timeout=timeout, creationflags=0x08000000 if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired:
        raise ConversionError('转换超时，请尝试较小的文件或减少页数。') from None
    if result.returncode:
        raise ConversionError('转换引擎无法处理此文件，请检查文件是否完整、加密或含有不兼容内容。')


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ('utf-8-sig', 'utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8', 'gb18030'):
        try:
            return data.decode(encoding)
        except UnicodeError:
            pass
    raise ConversionError('无法识别文本编码，请将文件另存为 UTF-8 后重试。')


def validate(path: Path, ext: str) -> dict:
    """Validate containers before any conversion engine opens them."""
    info = {}
    ext=normalize_extension(ext)
    if ext in DATA_EXTENSIONS:
        from data_converter import validate_data
        return validate_data(path,ext)
    if ext in MEDIA_EXTENSIONS:
        from media_converter import validate_media
        return validate_media(path,ext)
    if ext in IMAGE_EXTENSIONS:
        from image_converter import validate_image
        return validate_image(path,ext)
    if ext in ('doc','xls','ppt'):
        import olefile
        if not olefile.isOleFile(str(path)):
            raise ConversionError('文件内容与旧版 Office 格式不符，请选择有效的 DOC、XLS 或 PPT 文件。')
        with olefile.OleFileIO(str(path)) as document:
            names=document.listdir()
            streams={entry[-1] for entry in names}
            expected={'doc':{'WordDocument'},'xls':{'Workbook','Book'},'ppt':{'PowerPoint Document'}}[ext]
            if streams & {'EncryptedPackage','EncryptionInfo'}:
                raise ConversionError('文件受到密码保护，请先解除密码。')
            if not streams & expected:
                raise ConversionError('文件内容与扩展名不符，请重新保存为正确的 Office 文件。')
            if any(part.upper()=='VBA' for name in names for part in name):
                raise ConversionError('暂不处理包含宏的旧版文档，请先移除宏后重试。')
        if ext=='xls':
            import xlrd
            try:
                book=xlrd.open_workbook(str(path),on_demand=True)
                try: info['sheets']=book.sheet_names()
                finally: book.release_resources()
            except xlrd.XLRDError:
                raise ConversionError('无法读取 XLS，文件可能已损坏或受到密码保护。') from None
    elif ext in ('docx', 'xlsx', 'pptx', 'epub'):
        expected = {'docx': 'word/document.xml', 'xlsx': 'xl/workbook.xml',
                    'pptx': 'ppt/presentation.xml', 'epub': 'META-INF/container.xml'}[ext]
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(e.file_size for e in entries) > 300 * 1024**2:
                    raise ConversionError('文档解压后的内容过大，暂不支持此文件。')
                if expected not in archive.namelist():
                    raise ConversionError('文件内容与扩展名不符，请选择有效的文档。')
                for entry in entries:
                    if '..' in Path(entry.filename).parts or entry.filename.startswith(('/', '\\')):
                        raise ConversionError('文件包含不安全的内部路径。')
                    # Office external relationships can load local or network content.
                    if entry.filename.endswith('.rels'):
                        from lxml import etree
                        tree = etree.fromstring(archive.read(entry), parser=etree.XMLParser(resolve_entities=False, no_network=True))
                        for rel in tree:
                            if rel.get('TargetMode') == 'External' and not rel.get('Type', '').endswith('/hyperlink'):
                                raise ConversionError('此文档含外部链接资源，请先在原软件中嵌入图片或断开外部数据链接。')
        except zipfile.BadZipFile:
            raise ConversionError('文件损坏或受到密码保护，无法读取。') from None
        if ext == 'xlsx':
            from openpyxl import load_workbook
            book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
            info['sheets'] = book.sheetnames
            book.close()
        if ext=='epub':
            from office_extra import validate_epub
            info.update(validate_epub(path))
    elif ext == 'pdf':
        import pymupdf
        try:
            with pymupdf.open(path) as doc:
                if doc.needs_pass:
                    raise ConversionError('此 PDF 受密码保护，请先解除密码后再上传。')
                if not len(doc):
                    raise ConversionError('PDF 没有可转换的页面。')
                if len(doc) > 500:
                    raise ConversionError('当前版本最多处理 500 页 PDF，请先拆分文件。')
                info['pages'] = len(doc)
        except (pymupdf.FileDataError, pymupdf.EmptyFileError):
            raise ConversionError('无法读取 PDF，请检查文件是否完整。') from None
    else:
        if '\x00' in read_text(path)[:10000]:
            raise ConversionError('文件内容不是有效的文本。')
    return info


def safe_html(source: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(source, 'html.parser')
    for tag in soup(['script', 'iframe', 'object', 'embed', 'link', 'base', 'meta', 'form', 'svg']):
        tag.decompose()
    for tag in soup.find_all(True):
        for key in list(tag.attrs):
            if key.lower().startswith('on') or key in ('srcset', 'background', 'action'):
                del tag[key]
        if tag.has_attr('src') and not str(tag['src']).startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/gif;base64,')):
            del tag['src']
        if tag.has_attr('href') and not str(tag['href']).startswith(('#', 'https://', 'http://', 'mailto:')):
            del tag['href']
        if tag.has_attr('style') and (chr(92) in str(tag['style']) or re.search(r'url\s*\(|@|expression', str(tag['style']), re.I)):
            del tag['style']
    for tag in soup.find_all('style'):
        if chr(92) in tag.get_text() or re.search(r'url\s*\(|@|expression', tag.get_text(), re.I):
            tag.decompose()
    return str(soup)


def pandoc(source: Path, target: str, output: Path):
    binary = executable('pandoc')
    if not binary:
        raise ConversionError('缺少 Pandoc 引擎，请使用包含 engines 文件夹的完整便携版。')
    ext = source.suffix[1:]
    args = [binary, source, '--from', {'md': 'gfm', 'html': 'html', 'docx': 'docx'}[ext],
            '--to', {'md': 'gfm', 'html': 'html5', 'docx': 'docx', 'epub': 'epub3'}[target],
            '--output', output, '--sandbox', '--wrap=none']
    if ext == 'docx' and target == 'md':
        args += ['--extract-media=media']
    if target in ('html', 'epub'):
        args += ['--standalone', '--metadata', 'title=' + source.stem]
    run(args, output.parent)


def office_convert(source: Path, output: Path):
    binary = executable('office')
    if not binary:
        raise ConversionError('缺少 LibreOffice 引擎，请使用包含 engines 文件夹的完整便携版。')
    profile = output.parent / 'office-profile'
    settings=profile/'user/registrymodifications.xcu'
    settings.parent.mkdir(parents=True,exist_ok=True)
    settings.write_text('<?xml version="1.0" encoding="UTF-8"?><oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item></oor:items>','utf-8')
    filters={'doc':'MS Word 97','docx':'Office Open XML Text','xls':'MS Excel 97',
             'xlsx':'Calc Office Open XML','ppt':'MS PowerPoint 97','pptx':'Impress Office Open XML'}
    target=output.suffix[1:].lower()
    out_format=target+(':'+filters[target] if target in filters else '')
    run([binary, '-env:UserInstallation=' + profile.as_uri(), '--headless', '--nologo', '--nodefault',
         '--nofirststartwizard', '--convert-to', out_format, '--outdir', output.parent, source], output.parent)
    generated = output.parent / (source.stem + '.'+target)
    if not generated.is_file() or generated.stat().st_size == 0:
        raise ConversionError('未能生成 '+target.upper()+'，请检查文件是否受到保护或已损坏。')
    if generated != output:
        generated.replace(output)


def office_pdf(source: Path, output: Path):
    office_convert(source,output)


_ocr = None
_ocr_lock = threading.Lock()


def ocr_page(page):
    global _ocr
    import numpy as np
    try:
        from rapidocr import RapidOCR
        with _ocr_lock:
            if _ocr is None:
                _ocr = RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                                        'EngineConfig.onnxruntime.inter_op_num_threads': 2})
            scale = min(2, 2600 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=__import__('pymupdf').Matrix(scale, scale), alpha=False)
            result = _ocr(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3))
            if result.txts is None:
                return []
            return [(box.tolist(), text) for box, text in zip(result.boxes, result.txts)]
    except Exception as exc:
        raise ConversionError('扫描页 OCR 识别失败，请确认完整便携版包含离线模型。') from exc


def page_text(page, ocr: bool):
    text = page.get_text(sort=True).strip()
    if ocr and len(re.sub(r'\s+', '', text)) < 12:
        lines = ocr_page(page)
        return '\n'.join(t for _, t in lines), lines
    return text, None


def ocr_table(lines):
    """Estimate rows and column anchors from OCR boxes, without claiming layout fidelity."""
    rows = []
    for box, text in sorted(lines, key=lambda item: (min(p[1] for p in item[0]), min(p[0] for p in item[0]))):
        x = min(p[0] for p in box)
        y = sum(p[1] for p in box) / 4
        h = max(p[1] for p in box) - min(p[1] for p in box)
        if not rows or abs(rows[-1][0] - y) > max(10, h * .6):
            rows.append((y, []))
        rows[-1][1].append((x, text))
    anchors = []
    for _, row in rows:
        for x, _ in row:
            if not any(abs(x - a) < 30 for a in anchors):
                anchors.append(x)
    anchors.sort()
    anchors = anchors[:100]
    table = []
    for _, row in rows:
        values = [''] * len(anchors)
        for x, text in row:
            col = min(range(len(anchors)), key=lambda n: abs(anchors[n] - x))
            values[col] = (values[col] + ' ' + text).strip()
        table.append(values)
    return table


def text_cell(cell, value):
    # A conversion must never turn untrusted text into a spreadsheet formula.
    cell.value = '' if value is None else str(value)
    cell.data_type = 's'


def convert(source: Path, target: str, directory: Path, options: dict, progress: Callable):
    ext = normalize_extension(source.suffix)
    if target not in GRAPH.get(ext, []):
        raise ConversionError('本版不支持此转换方向。')
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / ('result.' + target)
    warnings = []
    progress(12, '正在读取文件')
    pairs={('doc','docx'),('docx','doc'),('xls','xlsx'),('xlsx','xls'),('ppt','pptx'),('pptx','ppt')}
    if ext in DATA_EXTENSIONS and (target!='xlsx' or ext=='json'):
        from data_converter import convert_data
        output,warnings=convert_data(source,ext,target,directory,options,progress)
    elif ext in MEDIA_EXTENSIONS:
        from media_converter import convert_media
        output,warnings=convert_media(source,ext,target,directory,options,progress)
    elif ext in IMAGE_EXTENSIONS:
        from image_converter import convert_image
        output, warnings=convert_image(source,ext,target,directory,options,progress)
    elif ext=='xlsx' and target=='json':
        from data_converter import excel_to_json
        output,warnings=excel_to_json(source,directory,options,progress)
    elif ext in ('txt','epub') or (ext=='md' and target=='pdf'):
        from office_extra import convert_office_extra
        output,warnings=convert_office_extra(source,ext,target,directory,options,progress)
    elif (ext,target) in pairs:
        if target=='xls':
            from openpyxl import load_workbook
            book=load_workbook(source,read_only=True,data_only=True,keep_links=False)
            try:
                if any(sheet.max_row>65536 or sheet.max_column>256 for sheet in book):
                    raise ConversionError('XLS 最多支持 65536 行、256 列；当前工作簿超出范围，无法完整保存。')
            finally: book.close()
        progress(30,'正在转换 Office 文档格式')
        office_convert(source,output)
        if target in ('doc','xls','ppt'):
            warnings.append('已导出为 Office 97–2003 格式，现代图形、样式或公式可能简化，请核对内容。')
    elif ext=='doc' and target in ('md','txt'):
        progress(20,'正在读取旧版 Word 文档')
        normalized=directory/'normalized.docx'
        office_convert(source,normalized)
        result,notes=convert(normalized,target,directory/'converted',options,progress)
        shutil.copy2(result,output.with_suffix(result.suffix))
        output=output.with_suffix(result.suffix)
        warnings.extend(notes)
    elif ext=='xls' and target=='csv':
        import xlrd
        book=xlrd.open_workbook(str(source),on_demand=True)
        try:
            name=options.get('sheet') or book.sheet_names()[0]
            if name not in book.sheet_names(): raise ConversionError('所选工作表不存在。')
            sheet=book.sheet_by_name(name)
            with output.open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream)
                for row in sheet.get_rows():
                    values=[]
                    for cell in row:
                        value=cell.value
                        if cell.ctype==xlrd.XL_CELL_DATE: value=xlrd.xldate_as_datetime(value,book.datemode).isoformat(sep=' ')
                        elif cell.ctype==xlrd.XL_CELL_NUMBER and value==int(value): value=int(value)
                        values.append(value)
                    writer.writerow(values)
        finally: book.release_resources()
        warnings.append('CSV 仅保存所选工作表的值，不保留格式或其他工作表。')
    elif (ext, target) in [('docx', 'md'), ('md', 'docx'), ('md', 'html'), ('html', 'md'), ('html', 'epub')]:
        work_source = source
        if ext in ('md', 'html'):
            value = read_text(source)
            if ext == 'md':
                # Parse markdown to HTML first: remove images/resources before the output writer reads them.
                binary = executable('pandoc')
                if not binary:
                    raise ConversionError('缺少 Pandoc 引擎。')
                normalized = directory / 'normalized.html'
                run([binary, source, '-f', 'gfm', '-t', 'html', '--sandbox', '-o', normalized], directory)
                value = normalized.read_text('utf-8')
            work_source = directory / 'content.html'
            work_source.write_text(safe_html(value), encoding='utf-8')
        progress(35, '正在转换文档结构')
        pandoc(work_source, target, output)
        if (directory / 'media').is_dir() and any((directory / 'media').rglob('*.*')):
            bundle = directory / 'result.zip'
            with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(output, '文档.md')
                for asset in (directory / 'media').rglob('*'):
                    if asset.is_file():
                        archive.write(asset, asset.relative_to(directory).as_posix())
            output = bundle
            warnings.append('文档包含图片，Markdown 与图片已一起打包。解压后请保持相对位置。')
    elif target == 'pdf':
        work_source = source
        if ext == 'html':
            work_source = directory / '网页.html'
            work_source.write_text('<meta charset="utf-8">' + safe_html(read_text(source)), 'utf-8')
        progress(30, '正在排版并导出 PDF')
        office_pdf(work_source, output)
    elif ext == 'docx' and target == 'txt':
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        doc = Document(source)
        lines = []
        for item in doc.element.body:
            if item.tag.endswith('}p'):
                lines.append(Paragraph(item, doc).text)
            elif item.tag.endswith('}tbl'):
                lines.extend('\t'.join(c.text for c in row.cells) for row in Table(item, doc).rows)
        output.write_text('\n'.join(lines), 'utf-8-sig')
    elif ext == 'xlsx' and target == 'csv':
        from openpyxl import load_workbook
        book = load_workbook(source, read_only=True, data_only=True, keep_links=False)
        try:
            sheet = options.get('sheet') or book.sheetnames[0]
            if sheet not in book.sheetnames:
                raise ConversionError('所选工作表不存在。')
            with output.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerows(book[sheet].values)
        finally:
            book.close()
        warnings.append('CSV 仅包含所选工作表的值。未缓存的公式值可能为空，请先在 Excel 中计算并保存。')
    elif ext == 'csv':
        from openpyxl import Workbook
        content = read_text(source)
        try:
            dialect = csv.Sniffer().sniff(content[:8192], delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel
        book = Workbook()
        sheet = book.active
        sheet.title = '导入数据'
        for number, row in enumerate(csv.reader(io.StringIO(content), dialect), 1):
            if number > 1048576 or len(row) > 16384:
                raise ConversionError('CSV 行数或列数超过 Excel 支持范围。')
            for col, value in enumerate(row, 1):
                text_cell(sheet.cell(number, col), value)
        book.save(output)
    elif ext == 'pdf':
        import pymupdf
        with pymupdf.open(source) as pdf:
            count = len(pdf)
            use_ocr = options.get('ocr', True)
            if target == 'png':
                images = []
                dpi = options.get('dpi', 150)
                if dpi not in (96, 150, 200, 300):
                    raise ConversionError('不支持的图片分辨率。')
                for n, page in enumerate(pdf):
                    progress(15 + int(75 * n / count), f'正在渲染第 {n+1} / {count} 页')
                    path = directory / f'page-{n+1:03d}.png'
                    scale = min(dpi / 72, 6000 / max(page.rect.width, page.rect.height))
                    page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(path)
                    images.append(path)
                if count == 1:
                    images[0].replace(output)
                else:
                    output = directory / 'result.zip'
                    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                        for path in images:
                            archive.write(path, path.name)
                    warnings.append(f'{count} 页 PNG 图片已打包为 ZIP。')
            elif target == 'txt':
                texts = []
                for n, page in enumerate(pdf):
                    progress(15 + int(75*n/count), f'正在提取第 {n+1} / {count} 页文字')
                    text, scanned = page_text(page, use_ocr)
                    texts.append(text)
                    if scanned is not None:
                        warnings.append(f'第 {n+1} 页使用 OCR，识别结果请核对。')
                if not any(texts):
                    raise ConversionError('未检测到可提取的文字。扫描文件请开启 OCR 后重试。')
                output.write_text('\n\n\f\n\n'.join(texts), 'utf-8-sig')
            elif target == 'docx':
                scans = [n for n, page in enumerate(pdf) if len(re.sub(r'\s+', '', page.get_text())) < 12]
                if scans and use_ocr:
                    from docx import Document
                    doc = Document()
                    for n, page in enumerate(pdf):
                        progress(15 + int(75*n/count), f'正在重建第 {n+1} / {count} 页')
                        text, _ = page_text(page, use_ocr)
                        if n:
                            doc.add_page_break()
                        for line in text.splitlines():
                            doc.add_paragraph(line)
                    doc.save(output)
                    warnings.append('此 PDF 含扫描页，已按阅读顺序重建文字；原版式和插图未保留，请核对识别结果。')
                else:
                    if scans:
                        warnings.append('已关闭 OCR，扫描页无法重建为可编辑文字。')
                    from pdf2docx import Converter
                    progress(30, '正在重建 Word 版面')
                    engine = Converter(str(source))
                    try:
                        engine.convert(str(output), multi_processing=False)
                    finally:
                        engine.close()
            elif target == 'xlsx':
                import pdfplumber
                from openpyxl import Workbook
                book = Workbook()
                book.remove(book.active)
                with pdfplumber.open(source) as parsed:
                    for n, page in enumerate(parsed.pages):
                        progress(15 + int(75*n/count), f'正在提取第 {n+1} / {count} 页表格')
                        tables = page.extract_tables()
                        if not tables:
                            tables = page.extract_tables({'vertical_strategy': 'text', 'horizontal_strategy': 'text', 'min_words_vertical': 2})
                        if not tables and use_ocr and len(pdf[n].get_text().strip()) < 12:
                            lines = ocr_page(pdf[n])
                            if lines:
                                tables = [ocr_table(lines)]
                                warnings.append(f'第 {n+1} 页通过 OCR 估计表格行列，请核对列对齐和数字。')
                        for t, table in enumerate(tables, 1):
                            sheet = book.create_sheet(f'第{n+1}页-表{t}')
                            for r, row in enumerate(table, 1):
                                for c, value in enumerate(row, 1):
                                    text_cell(sheet.cell(r, c), value)
                            sheet.freeze_panes = 'A2'
                            for col in sheet.columns:
                                sheet.column_dimensions[col[0].column_letter].width = 22
                if not book.sheetnames:
                    raise ConversionError('未检测到可识别的表格。扫描表格请开启 OCR，或尝试更清晰的文件。')
                book.save(output)
                warnings.append('表格提取会受合并单元格、无边框布局影响，请核对数据。')
    if not output.is_file() or output.stat().st_size == 0:
        raise ConversionError('未能生成有效的输出文件。')
    progress(98, '正在保存转换结果')
    return output, warnings
