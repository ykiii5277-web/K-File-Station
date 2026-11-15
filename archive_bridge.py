"""Adapter around the user's existing compiled archive recovery modules."""
from pathlib import Path,PureWindowsPath
import calendar,contextlib,concurrent.futures,ctypes,ctypes.util,hashlib,hmac,importlib.abc,importlib.util
import itertools,json,marshal,math,msvcrt,os,queue,re,secrets,shutil,string,struct,subprocess,sys,tempfile,threading,time,uuid,zipfile
from urllib.parse import urlsplit
import converter

RUNTIME=converter.HOME/'engines/archive'
MODULES=('runtime_paths','recovery','gpu_search','archive_targets','opencl_aes','search_tasks','mask_range')
_lock=threading.Lock(); _ready=False
DATA_ROOT=None


class EngineLoader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in MODULES: return importlib.util.spec_from_loader(fullname,self)
    def create_module(self,spec): return None
    def exec_module(self,module):
        path=RUNTIME/'bytecode'/(module.__name__+'.bin'); module.__file__=str(path)
        exec(marshal.loads(path.read_bytes()),module.__dict__)


def initialize():
    global _ready
    with _lock:
        if not _ready:
            if not (RUNTIME/'bytecode/recovery.bin').is_file(): raise converter.ConversionError('缺少解压引擎，请使用完整便携文件夹。')
            sys.meta_path.insert(0,EngineLoader())
            import runtime_paths
            runtime_paths.application_directory=lambda:RUNTIME
            runtime_paths.portable_mode=lambda:True
            runtime_paths.data_directory=lambda:Path(DATA_ROOT) if DATA_ROOT else converter.HOME/'data/archive-engine'
            import recovery,search_tasks,mask_range
            _ready=True
    import recovery,search_tasks,mask_range
    return recovery,search_tasks,mask_range


def archive_extension(path):
    from file_policy import archive_type
    return archive_type(path)


def inspect_archive(path,stop):
    path=Path(path).resolve(strict=True)
    if not path.is_file(): raise converter.ConversionError('请选择压缩包文件。')
    if archive_extension(path) in ('tar','tar.gz','tar.xz'):
        from tar_extract import entries
        entries(path,stop);encrypted=False
    else:
        recovery,_,_=initialize(); engine=recovery.find_7zip()
        encrypted=recovery.is_encrypted(engine,path,stop)
    return {'path':path,'name':path.name,'ext':archive_extension(path),'size':path.stat().st_size,
            'targets':['extract'],'encrypted':encrypted,'managed':False}


def check_entries(engine,path,password,stop):
    recovery,_,_=initialize()
    code,listing,errors=recovery.run_7zip(engine,'l',path,stop,password,('-slt',))
    if code: raise recovery.RecoveryError('无法读取压缩包目录，请检查密码、文件完整性及分卷。')
    entries=listing.split('----------',1)[-1]
    for block in re.split(r'\r?\n\s*\r?\n',entries):
        match=re.search(r'^Path = (.*)$',block,re.M)
        if match:
            name=match[1].strip(); windows=PureWindowsPath(name)
            if windows.drive or windows.root or '..' in windows.parts or ':' in name or name.startswith(('/','\\')):
                raise recovery.RecoveryError('压缩包含不安全的路径，已停止解压。')
        for line in block.splitlines():
            if line.startswith(('Symbolic Link =','Hard Link =')) and line.partition('=')[2].strip():
                raise recovery.RecoveryError('暂不自动解压含符号链接或硬链接的压缩包。')


def recover_archive(path,request,resume,auto_extract,output_parent,stop,progress,backend):
    if archive_extension(path) in ('tar','tar.gz','tar.xz'):
        from tar_extract import extract
        return extract(path,output_parent,stop,progress,backend) if auto_extract else {'found':True,'message':'此格式无压缩包密码，无需破译。','password':None,'destination':None}
    recovery,search,mask_range=initialize(); engine=recovery.find_7zip(); path=Path(path)
    password=None
    if recovery.is_encrypted(engine,path,stop):
        if request.get('kind')=='manual' and request.get('mask_length_range'):
            mask_range.options(request)
        password=search.search(engine,path,request,resume,stop,progress,backend)
        if password is None: return {'found':False,'encrypted':True,'message':'已试完所选范围，未找到匹配密码。'}
    destination=None
    if auto_extract:
        backend('密码验证完成，正在解压…' if password is not None else '无密码，正在解压…')
        parent=Path(output_parent); parent.mkdir(parents=True,exist_ok=True)
        check_entries(engine,path,password,stop)
        destination=recovery.extract(engine,path,parent,password,stop)
    return {'found':True,'password':password,'destination':destination,'message':'解压完成。' if destination else '密码已恢复。'}
