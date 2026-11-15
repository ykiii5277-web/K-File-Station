"""Bounded metadata reading and path-checked TAR/GZip/XZ extraction."""
from pathlib import Path,PureWindowsPath
import re,shutil,tarfile
from converter import ConversionError


def entries(path,stop):
    result=[]
    try:
        with tarfile.open(path,'r:*') as archive:
            for index,member in enumerate(archive):
                if stop.is_set():raise ConversionError('已停止读取压缩包。')
                if index>=100000:raise ConversionError('TAR最多包含10万个条目。')
                windows=PureWindowsPath(member.name)
                if windows.drive or windows.root or '..' in windows.parts or ':' in member.name:
                    raise ConversionError('压缩包含不安全的路径，已停止解压。')
                for part in windows.parts:
                    if part.endswith((' ','.')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part,re.I):raise ConversionError('压缩包含Windows不支持的条目名称。')
                if not (member.isfile() or member.isdir()):raise ConversionError('暂不自动解压含链接、设备或其他特殊条目的TAR。')
                result.append(member)
        if not result:raise ConversionError('压缩包没有可解压的条目。')
        return result
    except (tarfile.TarError,EOFError,OSError) as exc:raise ConversionError('无法读取TAR压缩包，文件可能损坏或内容与扩展名不符。') from exc


def extract(path,parent,stop,progress,backend):
    members=entries(path,stop);parent=Path(parent);parent.mkdir(parents=True,exist_ok=True)
    stem=re.sub(r'(?i)\.(tar\.gz|tar\.xz|tgz|txz|tar)$','',Path(path).name)
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',stem).strip(' .')[:80] or '解压结果'
    # Prefix prevents reserved device names such as CON.
    stem='解压_'+stem;number=0
    while True:
        destination=parent/(stem if not number else f'{stem}_{number}')
        try:destination.mkdir();break
        except FileExistsError:number+=1
    total=sum(member.size for member in members if member.isfile());done=0
    try:
        with tarfile.open(path,'r:*') as archive:
            for member in members:
                if stop.is_set():raise ConversionError('已停止解压。')
                target=destination.joinpath(*PureWindowsPath(member.name).parts)
                if not target.resolve().is_relative_to(destination.resolve()):raise ConversionError('压缩包含不安全路径。')
                if member.isdir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                backend('正在解压 · '+member.name)
                with archive.extractfile(member) as source,target.open('xb') as output:
                    while chunk:=source.read(4*1024**2):
                        if stop.is_set():raise ConversionError('已停止解压。')
                        output.write(chunk);done+=len(chunk)
                        progress('正在解压TAR',{'tested':done,'total':max(1,total)})
        return {'found':True,'password':None,'destination':destination,'message':'解压完成。'}
    except Exception:
        shutil.rmtree(destination,ignore_errors=True);raise
