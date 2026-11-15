"""Explicit, safe mappings between JSON, YAML, XML and CSV."""
import csv
import io
import json
import math
import re
from lxml import etree
import yaml
from converter import ConversionError,read_text


def unique_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ConversionError('存在重复键：'+str(key))
        result[key]=value
    return result


def check_value(value):
    stack=[(value,0)]; count=0
    while stack:
        item,depth=stack.pop(); count+=1
        if depth>80 or count>100000: raise ConversionError('数据嵌套或元素数量过多（最多 80 层、10 万项）。')
        if isinstance(item,dict):
            if any(not isinstance(k,str) for k in item): raise ConversionError('映射键必须是字符串。')
            stack.extend((v,depth+1) for v in item.values())
        elif isinstance(item,list): stack.extend((v,depth+1) for v in item)
        elif isinstance(item,float) and not math.isfinite(item): raise ConversionError('不支持 NaN 或无穷大。')
        elif item is not None and not isinstance(item,(str,int,float,bool)): raise ConversionError('存在不兼容 JSON 的数据类型。')
    return value


class JsonYamlLoader(yaml.SafeLoader):
    def compose_node(self,parent,index):
        if self.check_event(yaml.AliasEvent): raise ConversionError('不支持 YAML 别名，请先展开为普通数据。')
        self.depth=getattr(self,'depth',0)+1
        if self.depth>80: raise ConversionError('数据嵌套超过 80 层。')
        try: return super().compose_node(parent,index)
        finally: self.depth-=1


JsonYamlLoader.yaml_implicit_resolvers={k:[(tag,pattern) for tag,pattern in v if tag not in ('tag:yaml.org,2002:bool','tag:yaml.org,2002:timestamp','tag:yaml.org,2002:int')] for k,v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
JsonYamlLoader.add_implicit_resolver('tag:yaml.org,2002:bool',re.compile(r'^(true|false|True|False|TRUE|FALSE)$'),list('tTfF'))
JsonYamlLoader.add_implicit_resolver('tag:yaml.org,2002:int',re.compile(r'^[-+]?(0|[1-9][0-9]*)$'),list('-+0123456789'))
def yaml_mapping(loader,node):
    pairs=[]
    for key,value in node.value:
        k=loader.construct_object(key,deep=True)
        if not isinstance(k,str): raise ConversionError('YAML 映射键必须是字符串。')
        pairs.append((k,loader.construct_object(value,deep=True)))
    return unique_pairs(pairs)
JsonYamlLoader.add_constructor('tag:yaml.org,2002:map',yaml_mapping)


def xml_value(node,mode):
    children=[n for n in node if isinstance(n.tag,str)]
    if children and ((node.text or '').strip() or any((n.tail or '').strip() for n in children)):
        raise ConversionError('XML 含元素与文本交错的混合内容，请先整理为纯元素结构。')
    result={'@'+k:v for k,v in node.attrib.items()} if mode=='preserve' else {}
    for child in children:
        value=xml_value(child,mode); key=child.tag
        if key in result:
            if not isinstance(result[key],list): result[key]=[result[key]]
            result[key].append(value)
        else: result[key]=value
    if not children:
        text=node.text or ''
        if not result: return text
        if text: result['#text']=text
    return result


def load_data(path,ext,options=None):
    options=options or {}; content=read_text(path)
    try:
        if ext=='json':
            def bad_constant(v): raise ConversionError('JSON 不允许 '+v)
            value=json.loads(content,object_pairs_hook=unique_pairs,parse_constant=bad_constant)
        elif ext=='jsonl':
            def bad_constant(v):raise ConversionError('JSONL 不允许 '+v)
            value=[]
            for number,line in enumerate(content.splitlines(),1):
                if not line.strip():raise ConversionError(f'JSONL 第 {number} 行为空；每行须为一个 JSON 值。')
                try:value.append(json.loads(line,object_pairs_hook=unique_pairs,parse_constant=bad_constant))
                except (ValueError,ConversionError) as exc:raise ConversionError(f'JSONL 第 {number} 行：{exc}') from None
                if len(value)>100000:raise ConversionError('JSONL 最多处理10万条记录。')
        elif ext=='yaml': value=yaml.load(content,Loader=JsonYamlLoader)
        elif ext=='xml':
            if re.search(r'<!\s*(DOCTYPE|ENTITY)',content,re.I): raise ConversionError('XML 不支持 DTD 或实体声明。')
            content=re.sub(r'^\s*<\?xml[^>]*\?>','',content)
            tree=etree.fromstring(content.encode('utf-8'),etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
            # Re-encode after removing a declaration that may name another encoding.
            value={tree.tag:xml_value(tree,options.get('xml_mode','preserve'))}
        else:
            try: dialect=csv.excel_tab if ext=='tsv' else csv.Sniffer().sniff(content[:8192],delimiters=',;\t|')
            except csv.Error: dialect=csv.excel
            rows=csv.reader(io.StringIO(content),dialect)
            header=next(rows,None)
            if not header or any(not h.strip() for h in header) or len(set(header))!=len(header):
                raise ConversionError('CSV 需要非空且不重复的表头。')
            value=[]
            for number,row in enumerate(rows,2):
                if not row: continue
                if len(row)!=len(header): raise ConversionError(f'CSV 第 {number} 行列数与表头不一致。')
                value.append(dict(zip(header,row)))
                if len(value)>100000: raise ConversionError('CSV 最多处理 10 万条记录。')
        return check_value(value)
    except ConversionError: raise
    except Exception as exc: raise ConversionError('无法读取 '+ext.upper()+'：'+str(exc)[:180]) from None


def validate_data(path,ext):
    value=load_data(path,ext)
    return {'records':len(value) if isinstance(value,(dict,list)) else 1}


def to_xml(tag,value):
    try: node=etree.Element(tag)
    except (ValueError,TypeError): raise ConversionError('XML 元素名称不合法：'+str(tag)) from None
    if isinstance(value,dict):
        for key,item in value.items():
            if key.startswith('@'):
                if isinstance(item,(dict,list)): raise ConversionError('XML 属性必须是标量。')
                try: node.set(key[1:],scalar(item))
                except ValueError: raise ConversionError('XML 属性名称不合法：'+key) from None
            elif key=='#text':
                if isinstance(item,(dict,list)): raise ConversionError('#text 必须是标量。')
                node.text=scalar(item)
            else:
                for entry in item if isinstance(item,list) else [item]: node.append(to_xml(key,entry))
    elif isinstance(value,list):
        for item in value: node.append(to_xml('item',item))
    else: node.text=scalar(value)
    return node


def scalar(value):
    return '' if value is None else 'true' if value is True else 'false' if value is False else str(value)


def convert_data(source,ext,target,directory,options,progress):
    value=load_data(source,ext,options); progress(45,'正在映射数据结构')
    output=directory/('result.'+target); notes=[]
    if target=='json': output.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),'utf-8')
    elif target=='xlsx':return json_to_excel(value,directory,options,progress)
    elif target=='jsonl':
        value=record_value(value,options)
        if not isinstance(value,list) or not value:raise ConversionError('JSONL 需要非空数组，每个数组元素写入一行。')
        with output.open('w',encoding='utf-8',newline='\n') as stream:
            for row in value:stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
    elif target=='tsv' or ext=='tsv':
        content=read_text(source)
        try:dialect=csv.excel_tab if ext=='tsv' else csv.Sniffer().sniff(content[:8192],delimiters=',;\t|')
        except csv.Error:dialect=csv.excel
        with output.open('w',encoding='utf-8-sig',newline='') as stream:
            csv.writer(stream,delimiter='\t' if target=='tsv' else ',').writerows(csv.reader(io.StringIO(content),dialect))
        notes.append('保留字段文本与引用规则，不将数字、前导零或公式文本改成其他类型。')
    elif target=='yaml': output.write_text(yaml.safe_dump(value,allow_unicode=True,sort_keys=False),'utf-8')
    elif target=='xml':
        root=options.get('xml_root','root').strip() or 'root'
        node=to_xml(next(iter(value)),next(iter(value.values()))) if isinstance(value,dict) and len(value)==1 and not next(iter(value)).startswith(('@','#')) else to_xml(root,value)
        output.write_bytes(etree.tostring(node,encoding='utf-8',xml_declaration=True,pretty_print=True))
        notes.append('XML 标量按文本保存；空值变为空元素。属性使用 @、文本使用 #text，未保留 JSON 标量类型。')
    elif target=='csv':
        for key in filter(None,options.get('records_path','').strip().split('.')):
            try: value=value[int(key)] if isinstance(value,list) else value[key]
            except (KeyError,ValueError,IndexError,TypeError): raise ConversionError('记录路径不存在：'+options['records_path']) from None
        rows=[value] if isinstance(value,dict) else value
        if not isinstance(rows,list) or not rows or any(not isinstance(row,dict) for row in rows):
            raise ConversionError('CSV 需要对象或非空对象数组；嵌套数组请填写记录路径。')
        fields=list(dict.fromkeys(k for row in rows for k in row))
        if not fields or any(not k.strip() for k in fields): raise ConversionError('CSV 字段名不能为空。')
        with output.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
            for row in rows:
                out={}
                for key,item in row.items():
                    if isinstance(item,(dict,list)):
                        if options.get('nested_csv','json')=='reject': raise ConversionError('存在嵌套字段，请选择「JSON 文本」或整理为扁平记录。')
                        out[key]=json.dumps(item,ensure_ascii=False,separators=(',',':'))
                    else: out[key]=scalar(item)
                writer.writerow(out)
        notes.append('CSV 不保存类型、层次或样式；缺失键与空值均为空单元格，嵌套字段默认保存为 JSON 文本。')
    if ext=='xml': notes.append('XML 映射不保留注释、排版空白及不同标签的交错次序。'+('已按选项忽略属性。' if options.get('xml_mode')=='elements' else '属性以 @ 前缀保存。'))
    progress(98,'正在保存数据文件'); return output,notes


def record_value(value,options):
    for key in filter(None,options.get('records_path','').strip().split('.')):
        try:value=value[int(key)] if isinstance(value,list) else value[key]
        except (KeyError,IndexError,TypeError,ValueError):raise ConversionError('记录路径不存在：'+options['records_path']) from None
    return value


def json_to_excel(value,directory,options,progress):
    from openpyxl import Workbook
    from converter import text_cell
    value=record_value(value,options)
    if not isinstance(value,list) or not value or any(not isinstance(row,dict) for row in value):
        raise ConversionError('Excel 需要非空对象记录数组；嵌套数组请填写记录路径。')
    fields=list(dict.fromkeys(key for row in value for key in row))
    if not fields or any(not key.strip() for key in fields):raise ConversionError('Excel 字段名不能为空。')
    if len(fields)>16384 or len(value)>1048575:raise ConversionError('记录数量超出Excel行列范围。')
    book=Workbook(); sheet=book.active; sheet.title='数据'; sheet.freeze_panes='A2'
    def cell_value(cell,item):
        if isinstance(item,(dict,list)):
            if options.get('nested_csv')=='reject':raise ConversionError('存在嵌套字段，请选择「JSON 文本」或整理为扁平记录。')
            item=json.dumps(item,ensure_ascii=False,separators=(',',':'))
        if isinstance(item,int) and not isinstance(item,bool) and abs(item)>=10**15:item=str(item)
        if isinstance(item,str):
            if len(item)>32767 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',item):raise ConversionError('Excel 单元格含过长文本或不支持的控制字符。')
            text_cell(cell,item)
        else:cell.value=item
    try:
        for col,key in enumerate(fields,1):cell_value(sheet.cell(1,col),key)
        for number,row in enumerate(value,2):
            for col,key in enumerate(fields,1):cell_value(sheet.cell(number,col),row.get(key))
            if number%500==0:progress(45+int(45*number/(len(value)+1)),'正在写入Excel记录')
        output=directory/'result.xlsx';book.save(output)
    finally:book.close()
    progress(98,'正在保存Excel')
    return output,['使用字段并集作为表头；字符串按文本保存，15位以上整数转文本，嵌套值默认保存为JSON文本。空值和缺失键均为空单元格。']


def excel_to_json(source,directory,options,progress):
    from openpyxl import load_workbook
    from datetime import date,datetime,time
    book=load_workbook(source,read_only=True,data_only=True,keep_links=False)
    try:
        name=options.get('sheet') or book.sheetnames[0]
        if name not in book.sheetnames:raise ConversionError('所选工作表不存在。')
        sheet=book[name]
        if sheet.max_column>10000 or sheet.max_row>100001:raise ConversionError('表格过大，最多10万条记录、1万列。')
        rows=sheet.iter_rows(values_only=True); header=list(next(rows,()))
        while header and header[-1] is None:header.pop()
        keys=[str(v) if v is not None else '' for v in header]
        if not keys or any(not k.strip() for k in keys) or len(set(keys))!=len(keys):raise ConversionError('工作表第一行须为非空且不重复的表头。')
        value=[]
        for number,row in enumerate(rows,2):
            if number>100001:raise ConversionError('Excel转JSON最多10万条记录。')
            if any(v is not None for v in row[len(keys):]):raise ConversionError('存在无表头的数据列，请补齐表头。')
            if not any(v is not None for v in row):continue
            record={}
            for key,item in zip(keys,row):
                if isinstance(item,(datetime,date,time)):item=item.isoformat()
                record[key]=item
            value.append(record)
            if number%500==0:progress(15+min(75,int(75*number/max(1,sheet.max_row))),'正在读取工作表')
        check_value(value); output=directory/'result.json';output.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),'utf-8')
    finally:book.close()
    progress(98,'正在保存JSON')
    return output,['仅导出所选工作表；首行为表头，保留单元格值类型，日期/时间转ISO文本。公式使用缓存值；不保存样式、合并关系或其他工作表。']
