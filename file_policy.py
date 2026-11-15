"""Shared per-selection size and format policy for local file ingestion."""
from pathlib import Path
import converter

MIB=1024**2
GIB=1024**3
LIMITS={0:500*MIB,1:500*MIB,2:500*MIB,3:2*GIB,4:5*GIB}
MAX_FILES=100


def archive_type(path):
    name=Path(path).name.lower()
    for suffix,kind in (('.tar.gz','tar.gz'),('.tgz','tar.gz'),('.tar.xz','tar.xz'),('.txz','tar.xz'),('.tar','tar')):
        if name.endswith(suffix):return kind
    if name.endswith('.zip.001'):return 'zip'
    if name.endswith('.001'):return '7z'
    suffix=Path(path).suffix.lower().lstrip('.')
    return suffix if suffix in ('zip','rar','7z') else None


def format_key(path):
    archive=archive_type(path)
    if archive:return archive
    suffix=Path(path).suffix.lower().lstrip('.')
    return suffix if suffix in converter.RAW_EXTENSIONS else converter.normalize_extension(suffix)


def module_for(path):
    return 4 if archive_type(path) else converter.module_for(Path(path).suffix)


def limit_text(module):
    return '2 GB' if module==3 else '5 GB' if module==4 else '500 MB'


def validate_selection(paths):
    paths=[Path(path) for path in paths]
    if not 1<=len(paths)<=MAX_FILES:raise converter.ConversionError('一次请选择 1–100 个同格式文件。')
    if len({format_key(p) for p in paths})!=1:raise converter.ConversionError('多选文件必须为同一格式，请分开添加不同格式的文件。')
    module=module_for(paths[0]); total=0; sizes=[]
    if module!=4 and not converter.GRAPH.get(converter.normalize_extension(paths[0].suffix)):
        raise converter.ConversionError('文件不符合转化格式要求：本版暂不能将此文件转换为其他格式。')
    for path in paths:
        if not path.is_file():raise converter.ConversionError('文件不存在或不是普通文件：'+path.name)
        size=path.stat().st_size
        if not size:raise converter.ConversionError('不能添加空文件：'+path.name)
        total+=size; sizes.append(size)
        if total>LIMITS[module]:raise converter.ConversionError('本次所选文件合计不能超过 '+limit_text(module)+'。')
    return {'paths':paths,'sizes':sizes,'total':total,'module':module,'ext':converter.normalize_extension(paths[0].suffix)}
