from pathlib import Path
import io
import time
import zipfile
import shutil

import pytest
import pymupdf
from docx import Document
from openpyxl import Workbook, load_workbook
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation

import converter


@pytest.fixture(scope='session')
def samples(tmp_path_factory):
    folder = tmp_path_factory.mktemp('samples')
    doc = Document()
    doc.add_heading('中文转换测试', 0)
    doc.add_paragraph('Hello 文件转换，保留内容 123。')
    table = doc.add_table(rows=3, cols=2)
    for row, values in zip(table.rows, [('项目', '数量'), ('苹果', '12'), ('梨', '34')]):
        for cell, value in zip(row.cells, values): cell.text = value
    doc.save(folder / 'sample.docx')
    (folder / 'sample.md').write_text('# 中文转换测试\n\nHello 文件转换，保留内容 123。\n\n|项目|数量|\n|---|---|\n|苹果|12|\n', 'utf-8')
    (folder / 'sample.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>中文转换测试</title></head><body><h1>中文转换测试</h1><p>Hello 文件转换，保留内容 123。</p></body></html>', 'utf-8')
    book = Workbook()
    book.active.title = '销售数据'
    book.active.append(['项目', '数量'])
    book.active.append(['苹果', 12])
    other = book.create_sheet('第二张表')
    other.append(['选中此表', 34])
    book.save(folder / 'sample.xlsx')
    (folder / 'sample.csv').write_text('项目,数量\n苹果,12\n"=1+1",34\n', 'utf-8-sig')
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = '中文转换测试'
    slide.placeholders[1].text = 'Hello 文件转换 123'
    deck.save(folder / 'sample.pptx')
    for ext in ('doc','xls','ppt'):
        shutil.copy2(Path(__file__).parent/'fixtures/legacy'/('sample.'+ext),folder/('sample.'+ext))
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((50, 50), 'Conversion Test 123')
    for x in (50, 200, 350): page.draw_line((x, 100), (x, 220))
    for y in (100, 140, 180, 220): page.draw_line((50, y), (350, y))
    for row, values in enumerate([('Item', 'Count'), ('Apple', '12'), ('Pear', '34')]):
        for col, value in enumerate(values): page.insert_text((65 + col * 150, 125 + row * 40), value)
    pdf.save(folder / 'sample.pdf')
    pdf.new_page().insert_text((50, 50), 'Second page 456')
    pdf.save(folder / 'multi.pdf')
    pdf.close()
    image = Image.new('RGB', (1200, 600), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 48)
    draw.text((80, 60), '中文扫描识别测试', fill='black', font=font)
    draw.text((80, 150), 'Hello OCR 12345', fill='black', font=font)
    for y, values in enumerate([('项目', '数量'), ('苹果', '12'), ('梨', '34')]):
        draw.text((80, 260+y*85), values[0], fill='black', font=font)
        draw.text((650, 260+y*85), values[1], fill='black', font=font)
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    scanned = pymupdf.open()
    page = scanned.new_page(width=600, height=300)
    page.insert_image(page.rect, stream=stream.getvalue())
    scanned.save(folder / 'scan.pdf')
    scanned.close()
    return folder


from extended_check import NEW
EDGES = [(ext, target) for ext, targets in converter.GRAPH.items() if ext not in converter.IMAGE_EXTENSIONS|converter.MEDIA_EXTENSIONS|{'json','yaml','xml'} for target in targets if target!='json' and target not in NEW.get(ext,[])]


@pytest.mark.parametrize('ext,target', EDGES)
def test_all_diagram_edges(samples, tmp_path, ext, target):
    source = samples / ('sample.' + ext)
    converter.validate(source, ext)
    output, warnings = converter.convert(source, target, tmp_path / 'result', {'ocr': True, 'sheet': '第二张表'}, lambda *args: None)
    assert output.stat().st_size > 10
    if target == 'pdf':
        with pymupdf.open(output) as pdf:
            assert len(pdf) > 0
            text = ''.join(page.get_text() for page in pdf)
            assert '123' in text or '34' in text
    elif target == 'docx':
        assert '123' in '\n'.join(p.text for p in Document(output).paragraphs)
    elif target == 'txt':
        assert '123' in output.read_text('utf-8-sig')
    elif target == 'csv':
        assert '选中此表,34' in output.read_text('utf-8-sig')
    elif target == 'xlsx':
        book = load_workbook(output)
        values = [cell.value for sheet in book for row in sheet for cell in row]
        assert ('12' in values or 12 in values)
        if ext == 'csv':
            assert book.active['A3'].value == '=1+1'
            assert book.active['A3'].data_type == 's'
        book.close()
    elif target in ('md', 'html'):
        assert '123' in output.read_text('utf-8')
    elif target == 'epub':
        with zipfile.ZipFile(output) as archive:
            assert archive.read('mimetype') == b'application/epub+zip'
            assert any('123' in archive.read(name).decode('utf-8') for name in archive.namelist() if name.endswith('.xhtml'))
    elif target == 'png':
        with Image.open(output) as img: assert img.width > 500
    elif target in ('doc','xls','ppt'):
        converter.validate(output,target)
    elif target=='pptx':
        assert '123' in ' '.join(shape.text for slide in Presentation(output).slides for shape in slide.shapes if shape.has_text_frame)


def test_multiple_pdf_pages(samples, tmp_path):
    output, _ = converter.convert(samples / 'multi.pdf', 'png', tmp_path, {'dpi': 96}, lambda *args: None)
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ['page-001.png', 'page-002.png']


@pytest.mark.parametrize('target', ['txt', 'docx', 'xlsx'])
def test_scan_ocr_offline(samples, tmp_path, monkeypatch, target):
    import requests
    def blocked(*args, **kwargs): raise AssertionError('OCR must not download resources')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
    output, warnings = converter.convert(samples / 'scan.pdf', target, tmp_path, {'ocr': True}, lambda *args: None)
    if target == 'txt': text = output.read_text('utf-8-sig')
    elif target == 'docx': text = '\n'.join(p.text for p in Document(output).paragraphs)
    else:
        book = load_workbook(output)
        text = ' '.join(str(c.value) for s in book for row in s for c in row)
        book.close()
    assert '12345' in text
    assert '中文' in text
    assert warnings


def test_docx_images_bundle(tmp_path):
    pic = tmp_path / 'pic.png'
    Image.new('RGB', (100, 100), '#719162').save(pic)
    doc = Document()
    doc.add_paragraph('Embedded image')
    doc.add_picture(str(pic))
    source = tmp_path / 'images.docx'
    doc.save(source)
    output, _ = converter.convert(source, 'md', tmp_path / 'out', {}, lambda *args: None)
    assert output.suffix == '.zip'
    with zipfile.ZipFile(output) as archive:
        assert '文档.md' in archive.namelist()
        assert any(name.endswith('.png') for name in archive.namelist())


def test_api_validation_and_job(samples, monkeypatch, tmp_path):
    import app as server
    from fastapi.testclient import TestClient
    data = tmp_path / 'data'
    (data / 'uploads').mkdir(parents=True)
    (data / 'outputs').mkdir()
    monkeypatch.setattr(server, 'DATA', data)
    client = TestClient(server.app)
    assert client.get('/api/config').status_code == 401
    client.headers['Authorization'] = 'Bearer ' + server.TOKEN
    assert client.get('/api/config').status_code == 200
    assert client.post('/api/files', files={'file': ('fake.docx', b'broken')}).status_code == 400
    assert client.post('/api/files', files={'file': ('empty.md', b'')}).status_code == 400
    assert client.post('/api/files', headers={'origin': 'https://example.org'}, files={'file': ('a.md', b'hello')}).status_code == 403
    result = client.post('/api/files', files={'file': ('中文试验.csv', (samples / 'sample.csv').read_bytes())})
    assert result.status_code == 200
    uploaded = result.json()
    assert uploaded['targets'] == ['xlsx','json','tsv']
    assert client.post('/api/jobs', json={'fileId': uploaded['id'], 'target': 'pdf'}).status_code == 400
    job = client.post('/api/jobs', json={'fileId': uploaded['id'], 'target': 'xlsx'}).json()
    for _ in range(100):
        status = client.get('/api/jobs/' + job['id']).json()
        if status['status'] in ('done', 'error'): break
        time.sleep(.05)
    assert status['status'] == 'done', status
    result = client.get('/api/download/' + job['id'])
    assert result.status_code == 200
    assert zipfile.is_zipfile(io.BytesIO(result.content))


def test_html_external_resources_removed():
    result = converter.safe_html('<script>bad()</script><img src="file:///secret"><img src="https://example.org/track"><iframe src="http://example.org"></iframe><p onclick="bad()">safe</p><style>@import "http://example.org";</style>')
    assert 'secret' not in result and 'example.org' not in result
    assert 'onclick' not in result and '<script' not in result
    assert 'safe' in result


@pytest.mark.parametrize('ext',['doc','xls','ppt'])
def test_legacy_rejects_renamed_text(tmp_path,ext):
    path=tmp_path/('not-office.'+ext)
    path.write_text('This is a text file, not an Office binary.','utf-8')
    with pytest.raises(converter.ConversionError): converter.validate(path,ext)


def test_legacy_xls_size_limit(tmp_path):
    book=Workbook(); book.active.cell(65537,1,'must not be silently truncated')
    source=tmp_path/'oversized.xlsx'; book.save(source)
    with pytest.raises(converter.ConversionError,match='65536'):
        converter.convert(source,'xls',tmp_path/'out',{},lambda *args:None)
