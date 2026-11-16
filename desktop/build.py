"""在隔离的 DLL 搜索路径下构建，防止工具链 PATH 中的同名库污染软件。"""
import os
import sys
import tempfile
from pathlib import Path
import PyInstaller.__main__

source = Path(__file__).resolve().parent
windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
os.environ['PATH'] = os.pathsep.join(map(str, [windows / 'System32', windows,
    Path(sys.executable).parent, Path(sys.base_prefix)]))
with tempfile.TemporaryDirectory(prefix='merchant-build-') as scratch:
    PyInstaller.__main__.run(['--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', '商家联合筛选器', '--distpath', str(source.parent),
        '--workpath', str(Path(scratch) / 'work'), '--specpath', scratch,
        '--exclude-module', 'PySide6.QtQml', '--exclude-module', 'PySide6.QtQuick', '--icon', str(source / 'icon.ico'), '--add-data', f'{source / "icon.ico"}{os.pathsep}.',
        str(source / 'app.py')])
