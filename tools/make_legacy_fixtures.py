"""Generate real Office 97–2003 test inputs using the bundled office engine."""
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
import converter

out=root/'tests/fixtures/legacy'; out.mkdir(parents=True,exist_ok=True)
work=root/'build/legacy-fixtures'; work.mkdir(parents=True,exist_ok=True)
doc=Document();doc.add_heading('中文转换测试',0);doc.add_paragraph('Hello 文件转换，保留内容 123。')
table=doc.add_table(rows=3,cols=2)
for row,values in zip(table.rows,[('项目','数量'),('苹果','12'),('梨','34')]):
    for cell,value in zip(row.cells,values):cell.text=value
doc.save(work/'sample.docx')
book=Workbook();book.active.title='销售数据';book.active.append(['项目','数量']);book.active.append(['苹果',12]);book.create_sheet('第二张表').append(['选中此表',34]);book.save(work/'sample.xlsx')
deck=Presentation();slide=deck.slides.add_slide(deck.slide_layouts[1]);slide.shapes.title.text='中文转换测试';slide.placeholders[1].text='Hello 文件转换 123';deck.save(work/'sample.pptx')
def generate(pair):
    modern,legacy=pair
    directory=work/legacy;directory.mkdir(exist_ok=True)
    result=directory/('sample.'+legacy)
    converter.office_convert(work/('sample.'+modern),result)
    converter.validate(result,legacy)
    import shutil
    shutil.copy2(result,out/result.name)
    print('Generated genuine '+legacy.upper()+': '+str(result.stat().st_size)+' bytes',flush=True)
with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(generate,[('docx','doc'),('xlsx','xls'),('pptx','ppt')]))
