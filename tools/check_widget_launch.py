"""Check the real default Windows launcher and its single-instance behavior."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication

root=Path(__file__).resolve().parents[1]
folder=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'dist/K文件处理台'
settings_file=folder/'data/widget-settings.json'
original_settings=settings_file.read_bytes() if settings_file.is_file() else None
env=dict(os.environ);env['PATH']='C:/Windows/System32;C:/Windows'
app=QApplication([])
process=subprocess.Popen([str(folder/'K文件处理台.exe')],cwd=folder,env=env,creationflags=0x08000000)
u=ctypes.windll.user32
CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
u.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
u.IsWindowVisible.argtypes=[wintypes.HWND]
u.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
u.EnumWindows.argtypes=[CALLBACK,wintypes.LPARAM]

def windows():
    found=[]
    @CALLBACK
    def callback(hwnd,arg):
        pid=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==process.pid and u.IsWindowVisible(hwnd):
            text=ctypes.create_unicode_buffer(200);u.GetWindowTextW(hwnd,text,200)
            rect=wintypes.RECT();u.GetWindowRect(hwnd,ctypes.byref(rect))
            found.append((hwnd,text.value,rect))
        return True
    u.EnumWindows(callback,0)
    return found

def wait(predicate,timeout=15):
    deadline=time.monotonic()+timeout
    while True:
        app.processEvents()
        result=predicate()
        if result:return result
        if time.monotonic()>deadline:raise AssertionError('Native launcher window state timed out')
        time.sleep(.05)

def main_window():
    return next((item for item in windows() if item[1]=='K文件处理台'),None)

try:
    hwnd,title,rect=wait(main_window)
    # Native dimensions can be scaled by Windows DPI settings.
    diameter=rect.right-rect.left
    assert diameter==rect.bottom-rect.top and diameter<=192
    second=subprocess.Popen([str(folder/'K文件处理台.exe')],cwd=folder,env=env,creationflags=0x08000000)
    assert second.wait(timeout=15)==0
    wait(lambda:main_window() and main_window()[2].right-main_window()[2].left>diameter*3)
    u.PostMessageW(hwnd,0x0010,0,0)  # WM_CLOSE must collapse, not exit.
    wait(lambda:main_window() and main_window()[2].right-main_window()[2].left==diameter)
    assert process.poll() is None
    u.PostMessageW(hwnd,0x0201,0x0001,(48<<16)|48)
    time.sleep(.08)
    u.PostMessageW(hwnd,0x0202,0,(48<<16)|48)
    wait(lambda:main_window() and main_window()[2].right-main_window()[2].left>diameter*3 and abs((main_window()[2].right-main_window()[2].left)-(main_window()[2].bottom-main_window()[2].top))<3)
    time.sleep(.4)
    assert abs((main_window()[2].right-main_window()[2].left)-(main_window()[2].bottom-main_window()[2].top))<3
    assert main_window()[2].right-main_window()[2].left<diameter*5
    # Hold the circle center, drag the native window, and ensure release does not collapse it.
    rect=main_window()[2]; cx=(rect.right-rect.left)//2; cy=(rect.bottom-rect.top)//2
    dx=-24 if rect.left>70 else 24; dy=18 if rect.top<300 else -18
    u.PostMessageW(hwnd,0x0201,0x0001,(cy<<16)|cx)
    time.sleep(.4)
    u.PostMessageW(hwnd,0x0200,0x0001,((cy+dy)<<16)|(cx+dx))
    wait(lambda:main_window() and main_window()[2].left!=rect.left)
    u.PostMessageW(hwnd,0x0202,0,(cy<<16)|cx)
    assert abs((main_window()[2].right-main_window()[2].left)-(main_window()[2].bottom-main_window()[2].top))<3
    u.PostMessageW(hwnd,0x0010,0,0)
    wait(lambda:main_window() and main_window()[2].right-main_window()[2].left==diameter)
    u.PostMessageW(hwnd,0x0201,0x0001,(48<<16)|48)
    wait(lambda:main_window() and main_window()[2].right-main_window()[2].left>1.2*(main_window()[2].bottom-main_window()[2].top))
    u.PostMessageW(hwnd,0x0202,0,(48<<16)|48)
    u.PostMessageW(hwnd,0x0010,0,0)
    wait(lambda:main_window() and main_window()[2].right-main_window()[2].left==diameter)
    position=(48<<16)|48
    u.PostMessageW(hwnd,0x0204,0x0002,position)  # WM_RBUTTONDOWN / UP on the orb.
    u.PostMessageW(hwnd,0x0205,0,position)
    menu=wait(lambda:next((item for item in windows() if item[0]!=hwnd and item[2].right-item[2].left>100),None))
    menu_height=menu[2].bottom-menu[2].top
    print('Context menu dimensions:',menu[2].right-menu[2].left,menu_height,flush=True)
    last_action=((menu_height-24)<<16)|70
    u.PostMessageW(menu[0],0x0200,0,last_action)
    u.PostMessageW(menu[0],0x0201,0x0001,last_action)
    u.PostMessageW(menu[0],0x0202,0,last_action)
    assert process.wait(timeout=15)==0
    report={'status':'passed','checks':['默认启动圆形悬浮窗口','重复启动唤出已有工作台','关闭窗口收回圆标','鼠标点按打开紧凑圆盘','真实原生窗口长按拖动圆盘且不误收起','鼠标长按打开矩形窗口','右键菜单退出并正常结束进程'],'exe_sha256':hashlib.sha256((folder/'K文件处理台.exe').read_bytes()).hexdigest()}
    (root/'build').mkdir(exist_ok=True)
    (root/'build/native-launch.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('Default native launch, single instance, collapse and context-menu exit: PASS',flush=True)
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=10)
    if original_settings is not None: settings_file.write_bytes(original_settings)
    else: settings_file.unlink(missing_ok=True)
