"""Record real Qt frames: compact circle, hover, center drop, expanded ring."""
from pathlib import Path
import sys
import tempfile
import time

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication
from PIL import Image
import numpy as np
import json
import desktop

output=root/'build/圆盘动态预览.gif'
output.parent.mkdir(parents=True,exist_ok=True)
app=QApplication([]); app.setQuitOnLastWindowClosed(False)
frames=[]

def mouse(widget,kind,point,buttons):
    event=QMouseEvent(kind,QPointF(point),QPointF(widget.mapToGlobal(point)),Qt.MouseButton.LeftButton,buttons,Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget,event)

with tempfile.TemporaryDirectory(prefix='k-radial-preview-') as temp:
    desktop.DATA=Path(temp)/'working'; desktop.DATA.mkdir()
    sample=Path(temp)/'图片转换演示.png'
    rng=np.random.default_rng(20261114)
    sequence=[Image.fromarray(rng.integers(0,256,(800,1200,3),dtype=np.uint8)) for _ in range(5)]
    sequence[0].save(sample,save_all=True,append_images=sequence[1:],duration=150,loop=0)
    w=desktop.DesktopWidget(tray=False); w.move(350,350); w.show(); app.processEvents()
    screen=w.screen().availableGeometry(); size=min(640,screen.width()-24,screen.height()-24)
    target=w.bounded(w.pos()+QPoint(48-size//2,48-size//2),size,size)
    start=time.monotonic(); pressed=False; hovered=False; uploaded=False; converting=False; done_at=None; records=[]
    try:
        while time.monotonic()-start<25:
            t=time.monotonic()-start
            if t>.15 and not pressed:
                mouse(w,QEvent.Type.MouseButtonPress,QPoint(48,48),Qt.MouseButton.LeftButton)
                mouse(w,QEvent.Type.MouseButtonRelease,QPoint(48,48),Qt.MouseButton.NoButton); released=True
                pressed=True
            if t>.85 and w.radial and not hovered:
                circle=w.radial_wheel
                point=circle.from_scene(desktop.polar(140,-18)).toPoint()
                mouse(circle,QEvent.Type.MouseMove,point,Qt.MouseButton.NoButton)
                hovered=True
            if t>1.65 and hovered and not uploaded:
                mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(sample))])
                center=circle.from_scene(QPointF(350,350)).toPoint()
                enter=QDragEnterEvent(center,Qt.DropAction.CopyAction,mime,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
                QApplication.sendEvent(circle,enter)
                drop=QDropEvent(QPointF(center),Qt.DropAction.CopyAction,mime,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
                QApplication.sendEvent(circle,drop); uploaded=True
            if t>2.5 and w.item and not w.loading and not converting:
                w.begin_conversion('webp'); converting=True
            app.processEvents()
            canvas=QImage(size,size,QImage.Format.Format_RGBA8888); canvas.fill(Qt.GlobalColor.transparent)
            painter=QPainter(canvas); painter.drawPixmap(w.pos()-target,w.grab()); painter.end()
            rgba=Image.frombytes('RGBA',(size,size),bytes(canvas.bits()))
            palette=rgba.convert('RGB').quantize(colors=255)
            colors=palette.getpalette(); indexed=palette.point(lambda x:x+1)
            indexed.putpalette([0,0,0]+colors[:765])
            indexed.paste(0,(0,0),rgba.getchannel('A').point(lambda x:255 if x<128 else 0))
            frames.append(indexed)
            records.append({'time':round(t,3),'progress':round(w.task_progress.value,3),'halo':round(w.task_progress.opacity,3),'state':w.task_progress.state})
            if w.task_progress.state=='done':
                if done_at is None: done_at=time.monotonic()
                if time.monotonic()-done_at>.55: break
            time.sleep(.045)
        assert uploaded and w.result and len(circle.targets)==6 and w.task_progress.state=='done'
        frames[0].save(output,save_all=True,append_images=frames[1:],duration=65,loop=0,transparency=0,disposal=2,optimize=False)
        print('Recorded real animation frames:',len(frames),'GIF bytes:',output.stat().st_size,flush=True)
        (root/'build/光圈动画记录.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
    finally:
        while w.loading: app.processEvents(); time.sleep(.01)
        w.quitting=True; w.close(); w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete); app.processEvents()
