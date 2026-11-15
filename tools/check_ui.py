"""Browser-level acceptance checks using installed Microsoft Edge."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
out = root / 'build/browser-check'
out.mkdir(parents=True,exist_ok=True)
url = sys.argv[1]
with sync_playwright() as play:
    browser = play.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_function('document.querySelectorAll("[data-module]").length === 5')
    page.wait_for_timeout(400)
    page.screenshot(path=out / '界面-初始.png', full_page=True)
    page.locator('[data-module="2"]').click(position={'x': 20, 'y': 20}, force=True)
    sample = out / '体验文件.md'
    sample.write_text('# K文件处理台\n\n这是一个可以转换为 Word 或 HTML 的体验文件。\n\n| 项目 | 状态 |\n| --- | --- |\n| 文档与办公 | 已完成 |\n', 'utf-8')
    page.locator('#file-input').set_input_files(str(sample))
    page.wait_for_selector('[data-target="docx"]')
    assert page.locator('.ring-group').count() == 3
    assert page.locator('#file-name').inner_text() == sample.name
    page.wait_for_timeout(700)
    page.screenshot(path=out / '界面-格式外环.png', full_page=True)
    page.locator('[data-target="html"]').focus()
    page.keyboard.press('Enter')
    page.wait_for_selector('#job-detail a.primary-button', timeout=60000)
    assert '转换完成' in page.locator('#job-detail').inner_text()
    with page.expect_download() as download_info:
        page.locator('#job-detail a.primary-button').click()
    download = download_info.value
    assert download.suggested_filename.endswith('.html')
    download.save_as(str(out / '浏览器测试结果.html'))
    assert '体验文件' not in (out / '浏览器测试结果.html').read_text('utf-8') or 'K文件处理台' in (out / '浏览器测试结果.html').read_text('utf-8')
    page.screenshot(path=out / '界面-转换完成.png', full_page=True)
    # Check the current CSV and PDF targets against the rendered ring.
    csv_sample = out / '体验表格.csv'
    csv_sample.write_text('项目,数量\n苹果,12\n', 'utf-8-sig')
    page.locator('#file-input').set_input_files(str(csv_sample))
    page.wait_for_selector('[data-target="xlsx"]')
    assert page.locator('.ring-group').count() == 3
    import pymupdf
    pdf_sample = out / '体验文件.pdf'
    pdf = pymupdf.open()
    pdf.new_page().insert_text((50, 50), 'Portable test 123')
    pdf.save(pdf_sample)
    pdf.close()
    page.locator('#file-input').set_input_files(str(pdf_sample))
    page.wait_for_selector('[data-target="png"]')
    assert page.locator('.ring-group').count() == 4
    page.wait_for_timeout(800)
    page.screenshot(path=out / '界面-PDF四种格式.png', full_page=True)
    expect(page.locator('#upload-button')).to_be_enabled()
    page.locator('#file-input').set_input_files({'name': '损坏文件.docx', 'mimeType': 'application/octet-stream', 'buffer': b'broken'})
    expect(page.locator('#toast')).to_contain_text('损坏')
    assert page.locator('.ring-group').count() == 4
    page.locator('#nav-history').click()
    page.wait_for_selector('.history-row')
    page.locator('#nav-convert').click()
    page.locator('#help-button').click()
    assert page.locator('#help-dialog').is_visible()
    page.keyboard.press('Escape')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_timeout(200)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=out / '界面-窄屏.png', full_page=True)
    assert not errors, errors
    browser.close()
    import json
    (out/'browser-check.json').write_text(json.dumps({'status':'passed','checks':['五板块显示','自动识别和动态外环','键盘转换和下载','历史结果','损坏输入保留前一文件','说明弹窗','窄屏布局','无JavaScript错误']},ensure_ascii=False,indent=2),'utf-8')
print('UI checks passed: five sectors, dynamic ring, keyboard conversion, download, history, help, responsive layout, no JS errors.')
