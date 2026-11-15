"""One monotonic visual progress value shared by the readout and orbit halo."""
import math
import time
from PySide6.QtCore import QObject,QTimer,Signal
from PySide6.QtGui import QColor,QFont,QPainterPath,QPen
from PySide6.QtCore import QPointF,QRectF,Qt


class TaskProgress(QObject):
    changed=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.timer=QTimer(self); self.timer.setInterval(25); self.timer.timeout.connect(self.tick)
        self.value=0.; self.opacity=0.; self.visible=False; self.state='idle'

    def start(self,estimated=True):
        self.estimated=estimated
        self.value=0.; self.opacity=1.; self.visible=True; self.state='running'
        self.reported=0.; self.anchor=time.monotonic(); self.last=self.anchor
        self.timer.start(); self.changed.emit()

    def report(self,value):
        if self.state!='running': return
        self.reported=max(self.reported,min(98.,float(value)),self.value)
        self.anchor=time.monotonic()

    def complete(self):
        if self.state!='running': return
        self.state='finishing'; self.finish_from=self.value; self.finished_at=time.monotonic()

    def reset(self):
        self.timer.stop(); self.state='idle'; self.value=0.; self.opacity=0.; self.visible=False; self.changed.emit()

    def tick(self):
        now=time.monotonic()
        if self.state=='running':
            # Coarse engine stages are estimated between callbacks, capped below 100%.
            desired=self.reported+(95-self.reported)*(1-math.exp(-(now-self.anchor)/40)) if self.estimated and self.reported<95 else self.reported
            self.value=max(self.value,self.value+(desired-self.value)*min(1,(now-self.last)/.13))
        elif self.state=='finishing':
            elapsed=now-self.finished_at
            fraction=min(1,elapsed/.24)
            self.value=self.finish_from+(100-self.finish_from)*(1-(1-fraction)**3)
            if fraction==1: self.value=100.
            if elapsed>.32: self.opacity=max(0.,1-(elapsed-.32)/.24)
            if elapsed>=.56: self.opacity=0.; self.state='done'; self.timer.stop()
        self.last=now; self.changed.emit()


def draw_percentage(painter,rect,value):
    """Draw a small seven-segment display without requiring an installed font."""
    painter.save(); painter.translate(rect.topLeft())
    painter.setPen(QPen(QColor('#28648b'),1)); painter.drawLine(0,0,int(rect.width()),0)
    label=QFont('Bahnschrift'); label.setPixelSize(9); label.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,1.5)
    painter.setFont(label); painter.setPen(QColor('#80bcdb')); painter.drawText(QPointF(0,12),'PROGRESS')
    numbers=str(min(100,int(value)))
    segments={'0':'abcdef','1':'bc','2':'abged','3':'abgcd','4':'fgbc','5':'afgcd','6':'afgecd','7':'abc','8':'abcdefg','9':'abfgcd'}
    bars={'a':(3,0,12,3),'b':(15,3,3,10),'c':(15,16,3,10),'d':(3,26,12,3),'e':(0,16,3,10),'f':(0,3,3,10),'g':(3,13,12,3)}
    painter.translate(0,19); painter.setPen(Qt.PenStyle.NoPen)
    for digit in numbers.rjust(3):
        if digit==' ': painter.translate(23,0); continue
        for name,(x,y,w,h) in bars.items():
            painter.setBrush(QColor('#8eeaff' if name in segments.get(digit,'') else '#163d58'))
            painter.drawRoundedRect(QRectF(x,y,w,h),.65,.65)
        painter.translate(23,0)
    label.setPixelSize(19); label.setBold(True); painter.setFont(label); painter.setPen(QColor('#8eeaff'))
    painter.drawText(QPointF(0,25),'%'); painter.restore()


def draw_halo(painter,radius,value,opacity):
    if opacity<=0 or value<=0: return
    painter.save(); painter.setBrush(Qt.BrushStyle.NoBrush)
    rect=QRectF(350-radius,350-radius,2*radius,2*radius)
    for width,alpha in ((24,22),(18,45),(12,95),(7,245),(1.8,255)):
        pen=QPen(QColor(220 if width<2 else 80,249 if width<2 else 215,255,round(alpha*opacity)),width); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen); painter.drawArc(rect,90*16,-round(360*16*value/100))
    angle=math.radians(-90+360*value/100)
    point=QPointF(350+radius*math.cos(angle),350+radius*math.sin(angle))
    painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(225,253,255,round(245*opacity))); painter.drawEllipse(point,3.8,3.8)
    painter.restore()
