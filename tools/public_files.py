"""Explicit publication allowlist; local histories and data are never distributed."""
from pathlib import Path

DOCS = ('引擎来源.md', '图片引擎来源.md', '搜索范围与顺序.md',
        '版本说明-v1.0.0.md', '验证-v1.0.0.md', 'release-validation.json')
PYTHON_FILES = ('app.py', 'archive_bridge.py', 'archive_check.py', 'archive_ui.py',
                'batch_convert.py', 'converter.py', 'data_converter.py', 'desktop.py',
                'extended_check.py', 'file_policy.py', 'help_dialog.py', 'image_converter.py',
                'media_converter.py', 'office_extra.py', 'progress_visual.py', 'search_help.py',
                'tar_extract.py', 'user_guide.py', 'version.py', 'widget_check.py')


def public_files(root):
    root = Path(root).resolve()
    selected = [root/name for name in PYTHON_FILES]
    selected += [root/name for name in ('.gitignore', 'README.md', 'LICENSE.txt',
        'THIRD_PARTY_NOTICES.md', 'requirements.txt', 'requirements-lock.txt',
        'portable.spec', 'pytest.ini', '启动工具.cmd')]
    for directory in ('web', 'tools', 'tests'):
        selected += [path for path in (root/directory).rglob('*') if path.is_file()
                     and '__pycache__' not in path.parts and not path.name.startswith('.')
                     and path.suffix not in ('.pyc', '.log', '.tmp', '.pem', '.key', '.pfx')]
    selected += [root/'docs'/name for name in DOCS]
    selected += list((root/'docs/screenshots').glob('*.png'))
    return sorted({path.relative_to(root).as_posix() for path in selected if path.is_file()})
