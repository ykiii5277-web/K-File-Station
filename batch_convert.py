"""Sequential same-format batch conversion with a downloadable result bundle."""
from pathlib import Path
import re,shutil,zipfile
import converter


def safe_stem(name):
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',Path(name).stem).strip(' .')[:90]
    return '转换结果' if not stem or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',stem,re.I) else stem


def convert_batch(item,target,directory,options,progress):
    from image_converter import images_to_pdf
    directory.mkdir(parents=True,exist_ok=True)
    if item['ext'] in ('jpg','png') and target=='pdf' and options.get('merge_pdf',True):
        return images_to_pdf(item['paths'],directory,progress)
    bundle=directory/'batch'; bundle.mkdir(); succeeded=0; errors=[]; notes=[]
    count=len(item['paths'])
    for index,(path,name) in enumerate(zip(item['paths'],item['names'])):
        def report(value,message):progress(min(96,int(96*(index+value/100)/count)),f'批量 {index+1}/{count} · '+message)
        try:
            result,warnings=converter.convert(path,target,directory/f'work-{index:03d}',options,report)
            shutil.copy2(result,bundle/f'{index+1:03d}_{safe_stem(name)}{result.suffix}')
            notes.extend(name+'：'+message for message in warnings); succeeded+=1
        except Exception as exc:
            errors.append(name+'：'+(str(exc) if isinstance(exc,converter.ConversionError) else '转换失败，文件内容可能不兼容。'))
        finally:
            shutil.rmtree(directory/f'work-{index:03d}',ignore_errors=True)
            progress(min(96,int(96*(index+1)/count)),f'已处理 {index+1}/{count} 个文件')
    if not succeeded:raise converter.ConversionError('本批文件均未转换成功。\n'+'\n'.join(errors[:10]))
    if errors:(bundle/'失败说明.txt').write_text('\n'.join(errors),'utf-8-sig')
    if notes:(bundle/'转换说明.txt').write_text('\n'.join(notes),'utf-8-sig')
    progress(98,'正在打包批量转换结果')
    output=directory/'result.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
        for path in bundle.iterdir():archive.write(path,path.name)
    return output,[f'批量处理完成：成功 {succeeded}/{count}；结果已打包ZIP。']+(['部分失败，原因见ZIP内的失败说明.txt。'] if errors else [])
