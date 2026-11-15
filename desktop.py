"""Native, frameless desktop widget for K文件处理台. No browser is required."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
                           Qt, QThread, QTimer, QUrl, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QIcon, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient, QRegion, QTransform)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton, QScrollArea, QSizeGrip,
    QSystemTrayIcon, QVBoxLayout, QWidget, QLineEdit, QDoubleSpinBox, QSpinBox, QInputDialog,
    QDialog, QDialogButtonBox, QFormLayout)

import converter
import archive_bridge
import file_policy
from version import VERSION
import time
from progress_visual import TaskProgress,draw_halo,draw_percentage

NAME = 'K文件处理台'
DATA = converter.HOME / 'data'
BLUE = QColor('#43c9ff')
COMPACT_RADIUS=244.0
FULL_RADIUS=350.0
MODULES = [('文档与办公', 'DOCUMENTS', 'doc'), ('图片与图像', 'IMAGES', 'image'),
           ('结构化数据', 'DATA', 'data'), ('音视频', 'MEDIA', 'media'), ('解压与破译', 'ARCHIVES', 'archive')]

STYLE = '''
QWidget { color: #d6e8fa; font-family: "Microsoft YaHei UI"; font-size: 13px; }
QLabel { background: transparent; }
QPushButton { background: #174267; border: 1px solid #437b9f; border-radius: 8px; padding: 10px 13px; color: #9fd5f6; }
QPushButton:hover { background: #164568; border-color: #44b8f0; color: #e2f6ff; }
QPushButton:pressed { background: #0b2946; }
QPushButton:disabled { color: #496783; border-color: #18304a; background: #0d1c2e; }
QPushButton#primary { background: #1376cc; color: #fff; border-color: #389de8; font-weight: 600; }
QPushButton#primary:hover { background: #208fe2; }
QPushButton#upload { background: #123656; border: 1px dashed #2c6a98; color: #74caff; text-align: center; line-height: 28px; }
QPushButton#upload:hover { background: #103452; border-color: #42c8ff; }
QPushButton#control { background: #153d5d; border-color: #1a3956; padding: 0; border-radius: 7px; color: #b2d5f0; }
QPushButton#control:hover { border-color: #38b6ed; color: #61d4ff; }
QPushButton#control:checked { color: #65d2ff; background: #164063; border-color: #27618c; }
QFrame#card { background: #123652; border: 1px solid #35678c; border-radius: 10px; }
QLabel#muted { color: #b4d2eb; font-size: 12px; }
QLabel#guidance { color: #d0e9fc; font-size: 14px; font-weight: 600; }
QLabel#formatList { color: #d0e9fc; font-size: 12px; font-weight: 600; }
QLabel#cyan { color: #45c8ff; }
QLabel#warning { color: #c7ad7c; font-size: 12px; }
QLabel#section { color: #c7e4fb; font-size: 14px; font-weight: 600; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: #112c46; width: 5px; border-radius: 2px; }
QScrollBar::handle:vertical { background: #264a6d; min-height: 35px; border-radius: 2px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox { background: #123656; border: 1px solid #234b6a; border-radius: 6px; padding: 5px 8px; color: #a9d7f7; }
QComboBox QAbstractItemView { background: #0c2138; color: #c2e6ff; selection-background-color: #1a527e; }
QCheckBox { color: #b6d7ef; spacing: 7px; font-size: 12px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #35618a; border-radius: 3px; background: #10283f; }
QCheckBox::indicator:checked { background: #259ddc; border: 3px solid #163c60; }
QProgressBar { border: none; background: #112e48; border-radius: 3px; height: 5px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #31b6f3; border-radius: 3px; }
QMenu { background: #123858; color: #b7dbf5; border: 1px solid #2b506f; padding: 6px; }
QMenu::item { padding: 9px 24px; border-radius: 4px; }
QMenu::item:selected { background: #1c4b71; }
QToolTip { background: #0d2942; color: #bfE7ff; border: 1px solid #28648a; padding: 8px; }
'''


def font(size, bold=False):
    value = QFont('Microsoft YaHei UI')
    value.setPixelSize(size)
    value.setBold(bold)
    return value


def logo(painter: QPainter, rect: QRectF):
    """A geometric K, shared by the orb, tray, titlebar and application icon."""
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(rect.width(), rect.height())
    grad = QLinearGradient(0, 0, 1, 1)
    grad.setColorAt(0, QColor('#e2faff'))
    grad.setColorAt(1, QColor('#3ebaff'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRoundedRect(QRectF(.13, .15, .15, .7), .025, .025)
    painter.drawPolygon(QPolygonF([QPointF(.34,.49), QPointF(.68,.15), QPointF(.89,.15), QPointF(.56,.49)]))
    painter.drawPolygon(QPolygonF([QPointF(.34,.52), QPointF(.56,.52), QPointF(.9,.85), QPointF(.68,.85)]))
    painter.restore()


def app_icon():
    pix = QPixmap(128, 128)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QRadialGradient(45, 30, 110)
    gradient.setColorAt(0, QColor('#2679b2'))
    gradient.setColorAt(1, QColor('#103454'))
    p.setBrush(gradient)
    p.setPen(QPen(QColor('#42c7ff'), 3))
    p.drawEllipse(QRectF(4,4,120,120))
    logo(p, QRectF(29,28,70,70))
    p.end()
    return QIcon(pix)


def polar(radius, degrees):
    angle = math.radians(degrees)
    return QPointF(350 + radius*math.cos(angle), 350 + radius*math.sin(angle))


def draw_arc_text(painter,text,radius,top=True):
    """Keep glyphs upright while following the upper or lower circumference."""
    painter.save(); painter.setFont(font(14,True))
    metrics=painter.fontMetrics()
    text=metrics.elidedText(text,Qt.TextElideMode.ElideMiddle if top else Qt.TextElideMode.ElideRight,int(radius*1.8))
    widths=[metrics.horizontalAdvance(char)+1.3 for char in text]
    total=sum(widths); offset=-total/2
    for char,width in zip(text,widths):
        delta=math.degrees((offset+width/2)/radius)
        angle=-90+delta if top else 90-delta
        point=polar(radius,angle)
        painter.save(); painter.translate(point)
        painter.rotate(angle+90 if top else angle-90)
        painter.drawText(QPointF(-(width-1.3)/2,(metrics.ascent()-metrics.descent())/2),char)
        painter.restore(); offset+=width
    painter.restore()


def wedge(outer, inner, start, end):
    path = QPainterPath()
    path.moveTo(polar(outer, start))
    path.arcTo(QRectF(350-outer,350-outer,outer*2,outer*2), -start, -(end-start))
    if inner:
        path.lineTo(polar(inner,end))
        path.arcTo(QRectF(350-inner,350-inner,inner*2,inner*2), -end, end-start)
    else:
        path.lineTo(350,350)
    path.closeSubpath()
    return path


def draw_symbol(p, name, x, y, color):
    p.save()
    p.translate(x-13, y-13)
    p.setPen(QPen(color, 1.65))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == 'doc':
        p.drawRoundedRect(QRectF(5,2,17,23),2,2)
        for line, width in ((9,10),(14,10),(19,6)): p.drawLine(9,line,9+width,line)
    elif name == 'image':
        p.drawRoundedRect(QRectF(2,2,24,23),4,4)
        p.drawEllipse(QPointF(9,9),2,2)
        p.drawPolyline(QPolygonF([QPointF(3,21),QPointF(11,13),QPointF(17,19),QPointF(21,15),QPointF(25,19)]))
    elif name == 'data':
        p.drawPolyline(QPolygonF([QPointF(8,5),QPointF(2,14),QPointF(8,23)]))
        p.drawPolyline(QPolygonF([QPointF(20,5),QPointF(26,14),QPointF(20,23)]))
        p.drawLine(17,2,11,26)
    elif name == 'media':
        p.drawRoundedRect(QRectF(2,4,24,20),4,4)
        p.drawPolygon(QPolygonF([QPointF(11,9),QPointF(19,14),QPointF(11,19)]))
    elif name == 'archive':
        p.drawRoundedRect(QRectF(2,3,24,6),2,2)
        p.drawRect(QRectF(5,9,18,16))
        p.drawLine(11,14,17,14)
    p.restore()


class OrbitCanvas(QWidget):
    moduleClicked = Signal(int)
    targetClicked = Signal(str)
    centerClicked = Signal()
    filesDropped=Signal(list)
    dragStarted=Signal(QPoint)
    dragMoved=Signal(QPoint)
    dragEnded=Signal()

    def __init__(self, parent=None, radial_mode=False):
        super().__init__(parent)
        self.radial_mode=radial_mode
        self.view_radius=COMPACT_RADIUS if radial_mode else FULL_RADIUS
        self.drop_hint=False
        self.radial_press=None
        self.radial_last=None
        self.radial_dragging=False
        self.press_moved=False
        self.drag_timer=QTimer(self)
        self.drag_timer.setSingleShot(True); self.drag_timer.setInterval(320)
        self.drag_timer.timeout.connect(self.start_radial_drag)
        self.targets = []
        self.selected = False
        self.active_module=0
        self.conversion_progress=0.
        self.progress_visible=False
        self.halo_opacity=0.
        self.busy = False
        self.hover = None
        self.key_index = 0
        self.keyboard_navigation=False
        self.source_ext = ''
        self.file_label=''
        self.status_message='选择板块后添加文件 · 点击中心收起'
        self.has_result=False
        self.hover_amounts=[0.0]*5
        self.suppressed_module=None
        self.module_animations=[]
        for index in range(5):
            animation=QVariantAnimation(self)
            animation.setDuration(190)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.valueChanged.connect(lambda value,i=index:self.set_hover_amount(i,value))
            self.module_animations.append(animation)
        self.ring_progress=0.0
        self.ring_animation=QVariantAnimation(self)
        self.ring_animation.setDuration(380)
        self.ring_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.ring_animation.valueChanged.connect(self.set_ring_progress)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('五板块圆盘与动态格式外环；方向键切换，回车选择')
        self.setMinimumSize(0 if radial_mode else 300,0 if radial_mode else 300)

    def set_hover_amount(self,index,value):
        self.hover_amounts[index]=float(value); self.update()

    def set_ring_progress(self,value):
        self.ring_progress=float(value); self.update()

    def animate_hover(self,index=None):
        if index==self.suppressed_module: index=None
        for i,animation in enumerate(self.module_animations):
            target=1.0 if i==index else 0.0
            if animation.endValue()==target and animation.state()==QVariantAnimation.State.Running: continue
            animation.stop()
            animation.setStartValue(self.hover_amounts[i]); animation.setEndValue(target)
            animation.start()

    def set_targets(self,targets,source_ext='',reset_hover=True):
        self.targets=list(targets); self.source_ext=source_ext; self.key_index=0
        self.keyboard_navigation=False; self.hover=None; self.setToolTip('')
        if reset_hover:
            self.suppressed_module=self.active_module
            self.animate_hover()
        self.ring_animation.stop(); self.ring_progress=0.0
        if targets:
            self.ring_animation.setStartValue(0.0); self.ring_animation.setEndValue(1.0); self.ring_animation.start()
        self.update()

    def sector_transform(self,index):
        amount=self.hover_amounts[index]
        angle=math.radians(-90+index*72)
        transform=QTransform()
        transform.translate(350+10*amount*math.cos(angle),350+10*amount*math.sin(angle))
        transform.scale(1+.055*amount,1+.055*amount)
        transform.translate(-350,-350)
        return transform

    def position(self, point):
        side = min(self.width(), self.height())
        return QPointF(350+(point.x()-self.width()/2)*2*self.view_radius/side,
                       350+(point.y()-self.height()/2)*2*self.view_radius/side)

    def from_scene(self,point):
        scale=min(self.width(),self.height())/(2*self.view_radius)
        return QPointF(self.width()/2+(point.x()-350)*scale,self.height()/2+(point.y()-350)*scale)

    def hit(self, point):
        loc = self.position(point)
        radius = math.hypot(loc.x()-350,loc.y()-350)
        degrees = math.degrees(math.atan2(loc.y()-350,loc.x()-350))
        if 224 <= radius <= 294 and self.targets and self.ring_progress>.85:
            index = int(((degrees+90) % 360)/ (360/len(self.targets)))
            return ('target', index)
        # Match the painted, displaced shape, including the protruding outer edge.
        for index in sorted(range(5),key=lambda i:self.hover_amounts[i],reverse=True):
            if self.hover_amounts[index]>.01 and self.sector_transform(index).map(wedge(193,76,-125+index*72,-55+index*72)).contains(loc):
                return ('module',index)
        if 74 <= radius <= 193:
            return ('module', int(((degrees+126)%360)/72))
        if radius<73 and self.radial_mode: return ('center',0)
        return None

    def mouseMoveEvent(self, event):
        if self.radial_mode and self.radial_press is not None:
            self.radial_last=event.globalPosition().toPoint()
            if (self.radial_last-self.radial_press).manhattanLength()>QApplication.startDragDistance(): self.press_moved=True
            if self.radial_dragging:
                self.dragMoved.emit(self.radial_last); return
        self.update_hover(event.position())

    def mousePressEvent(self,event):
        if self.radial_mode and event.button()==Qt.MouseButton.LeftButton:
            self.radial_press=event.globalPosition().toPoint(); self.radial_last=self.radial_press
            self.radial_dragging=False; self.press_moved=False; self.drag_timer.start()
            event.accept(); return
        super().mousePressEvent(event)

    def start_radial_drag(self):
        if self.radial_press is None: return
        self.radial_dragging=True; self.hover=None; self.animate_hover()
        self.grabMouse()
        self.dragStarted.emit(self.radial_press); self.dragMoved.emit(self.radial_last)

    def hideEvent(self,event):
        self.drag_timer.stop(); self.radial_press=None; self.radial_dragging=False
        if QWidget.mouseGrabber() is self: self.releaseMouse()
        super().hideEvent(event)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            self.drop_hint=True; self.update(); event.acceptProposedAction()

    def dragMoveEvent(self,event):
        if event.mimeData().hasUrls():
            self.drop_hint=self.hit(event.position())==('center',0)
            self.update(); event.acceptProposedAction()

    def dragLeaveEvent(self,event):
        self.drop_hint=False; self.update(); event.accept()

    def dropEvent(self,event):
        self.drop_hint=False; self.update()
        paths=[url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.filesDropped.emit(paths); event.acceptProposedAction()

    def update_hover(self,position):
        self.keyboard_navigation=False
        hit = self.hit(position)
        if self.busy:hit=None
        if self.suppressed_module is not None and hit!=('module',self.suppressed_module):
            self.suppressed_module=None
        if hit != self.hover:
            self.hover = hit
            self.animate_hover(hit[1] if hit and hit[0]=='module' else None)
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            if hit and hit[0] == 'target':
                target = self.targets[hit[1]]
                self.setToolTip(converter.NOTES.get(self.source_ext+':'+target,'转换为 '+target.upper()))
            elif hit and hit[0] == 'module':
                self.setToolTip('点击添加'+MODULES[hit[1]][0]+'文件')
            elif hit and hit[0]=='center':
                self.setToolTip('点击收回圆形挂件；右键可另存结果、查看文件或打开完整窗口。')
            else:
                self.setToolTip('')
            self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.animate_hover()
        self.update()

    def mouseReleaseEvent(self,event):
        if event.button() != Qt.MouseButton.LeftButton: return
        if self.radial_mode:
            self.drag_timer.stop(); self.radial_press=None
            if QWidget.mouseGrabber() is self: self.releaseMouse()
            if self.radial_dragging:
                self.radial_dragging=False; self.dragEnded.emit(); return
            if self.press_moved: return
        hit = self.hit(event.position())
        if hit:
            if hit[0] == 'target' and not self.busy: self.targetClicked.emit(self.targets[hit[1]])
            elif hit[0] == 'module': self.moduleClicked.emit(hit[1])
            elif hit[0]=='center': self.centerClicked.emit()

    def keyPressEvent(self,event):
        count = len(self.targets) if self.targets else 5
        if event.key() in (Qt.Key.Key_Right,Qt.Key.Key_Down,Qt.Key.Key_Left,Qt.Key.Key_Up):
            self.keyboard_navigation=True
            self.key_index = (self.key_index + (1 if event.key() in (Qt.Key.Key_Right,Qt.Key.Key_Down) else -1)) % count
            self.animate_hover(self.key_index if not self.targets else None)
            self.update()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):
            if self.targets and not self.busy: self.targetClicked.emit(self.targets[self.key_index % count])
            elif not self.targets: self.moduleClicked.emit(self.key_index)
        else: super().keyPressEvent(event)

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(),self.height())
        if self.radial_mode:
            clip=QPainterPath()
            clip.addEllipse(QRectF((self.width()-side)/2+4,(self.height()-side)/2+4,side-8,side-8))
            p.setClipPath(clip)
        p.translate(self.width()/2,self.height()/2)
        p.scale(side/(2*self.view_radius),side/(2*self.view_radius))
        p.translate(-350,-350)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r in (211,308,330):
            p.setPen(QPen(QColor('#275c83'),1,Qt.PenStyle.DotLine if r==330 else Qt.PenStyle.SolidLine))
            p.drawEllipse(QPointF(350,350),r,r)
        p.setPen(QPen(QColor('#427ca6'),2))
        for start in range(0,360,45):
            p.drawArc(QRectF(23,23,654,654),start*16,12*16)
        for i in range(60):
            p.setPen(QPen(QColor('#4b86ad' if i%5==0 else '#255575'),1))
            p.drawLine(polar(313,i*6),polar(319 if i%5==0 else 316,i*6))
        for i in sorted(range(5),key=lambda i:self.hover_amounts[i]):
            title,caption,symbol=MODULES[i]
            p.save()
            p.setWorldTransform(self.sector_transform(i),True)
            active = self.hover==('module',i)
            focused = self.hover==('module',i) or (self.keyboard_navigation and self.hasFocus() and not self.targets and i==self.key_index)
            grad = QLinearGradient(350,150,350,550)
            grad.setColorAt(0,QColor('#247eb6' if active else '#1c496f'))
            grad.setColorAt(1,QColor('#18537d' if active else '#123554'))
            p.setBrush(grad)
            p.setPen(QPen(QColor('#49c8ff' if active and (self.selected or focused) else '#3b7fa9' if active else '#396789'),1.5))
            p.drawPath(wedge(193,76,-126+i*72+1,-54+i*72-1))
            location = polar(134,-90+i*72)
            tint = QColor('#77daff' if active else '#b8e0fb' if focused else '#96c5e6')
            draw_symbol(p,symbol,location.x(),location.y()-27,tint)
            p.setPen(QColor('#ddf6ff' if active else '#c3def2'))
            p.setFont(font(17,active))
            p.drawText(QRectF(location.x()-78,location.y()+3,156,25),Qt.AlignmentFlag.AlignCenter,title)
            p.setPen(QColor('#a3e6ff' if active else '#9bc8e9'))
            p.setFont(font(11))
            p.drawText(QRectF(location.x()-78,location.y()+29,156,18),Qt.AlignmentFlag.AlignCenter,caption)
            p.restore()
        for i,target in enumerate(self.targets):
            progress=self.ring_progress
            if progress<.001: continue
            p.save()
            p.translate(350,350); p.scale(.78+.22*progress,.78+.22*progress); p.translate(-350,-350)
            focused = self.hover==('target',i) or (self.keyboard_navigation and self.hasFocus() and i==self.key_index%len(self.targets))
            p.setOpacity(progress*(.75 if self.busy else 1))
            grad = QRadialGradient(350,350,300)
            grad.setColorAt(.7,QColor('#19567f'))
            grad.setColorAt(1,QColor('#298dc2' if focused else '#216d9d'))
            p.setBrush(grad)
            p.setPen(QPen(QColor('#56d5ff' if focused else '#5498c1'),1.5))
            start = -90+i*360/len(self.targets)+1
            end = -90+(i+1)*360/len(self.targets)-1
            p.drawPath(wedge(294,224,start,end))
            location = polar(259,(start+end)/2)
            p.setPen(QColor('#c2f0ff'))
            p.setFont(font(19,True))
            p.drawText(QRectF(location.x()-70,location.y()-18,140,27),Qt.AlignmentFlag.AlignCenter,'解压 / 破译' if target=='extract' else target.upper())
            p.setPen(QColor('#b8e9ff'))
            p.setFont(font(11))
            p.drawText(QRectF(location.x()-70,location.y()+13,140,20),Qt.AlignmentFlag.AlignCenter,('正在读取' if getattr(self,'reading',False) else '正在转换') if self.busy else '点击转换')
            p.restore()
        p.setBrush(QColor('#103653'))
        p.setPen(QPen(QColor('#83e8ff') if self.drop_hint else QColor('#28648b'),3 if self.drop_hint else 1.2))
        p.drawEllipse(QPointF(350,350),73,73)
        p.setPen(QPen(QColor('#38c1ff'),2))
        p.drawArc(QRectF(281,281,138,138),28*16,62*16)
        logo(p,QRectF(330,307,40,40))
        p.setFont(font(14,True))
        p.setPen(QColor('#c5ecff'))
        p.drawText(QRectF(277,351,146,25),Qt.AlignmentFlag.AlignCenter,NAME)
        p.setFont(font(11))
        p.setPen(QColor('#aacfe9'))
        p.drawText(QRectF(277,379,146,18),Qt.AlignmentFlag.AlignCenter,'松开以识别文件' if self.drop_hint else '点击收起 · 长按拖动' if self.radial_mode else '外环选择目标格式' if self.targets else '选择板块添加文件')
        if self.radial_mode:
            draw_halo(p,self.view_radius-10,self.conversion_progress,self.halo_opacity)
            hint_radius=self.view_radius-(34 if self.progress_visible else 18+16*max(0,min(1,(self.view_radius-COMPACT_RADIUS)/(FULL_RADIUS-COMPACT_RADIUS))))
            p.setPen(QColor('#e0f4ff'))
            title=self.file_label or '选择板块，或将文件拖入中心'
            draw_arc_text(p,title,hint_radius,True)
            text='转换完成 · 右键查看或另存结果' if self.has_result else self.status_message.replace('\n',' ')
            p.setPen(QColor('#d0eaff'))
            draw_arc_text(p,text,hint_radius,False)
        elif self.progress_visible:
            p.resetTransform()
            draw_percentage(p,QRectF(self.width()-116,self.height()-60,100,54),self.conversion_progress)
        p.end()


class StatusLabel(QLabel):
    textChanged=Signal(str)

    def setText(self,text):
        super().setText(text)
        self.textChanged.emit(text)


class LoadTask(QThread):
    loaded = Signal(dict)
    failed = Signal(str)
    progress = Signal(int,str)

    def __init__(self,path):
        super().__init__()
        self.paths=[Path(p) for p in path] if isinstance(path,(list,tuple)) else [Path(path)]

    def run(self):
        folder = DATA / 'uploads' / uuid.uuid4().hex
        try:
            selection=file_policy.validate_selection(self.paths)
            multiple=len(self.paths)>1; total=selection['total']; copies=[]; metadata=[]; copied=0; last_report=0
            folder.mkdir(parents=True)
            for i,path in enumerate(self.paths):
                ext=converter.normalize_extension(path.suffix)
                copy=folder/(f'input-{i:03d}.'+ext)
                with path.open('rb') as source,copy.open('wb') as destination:
                    while chunk:=source.read(4*1024**2):
                        copied+=len(chunk)
                        if copied>total:raise converter.ConversionError('读取期间文件大小发生变化，请重新选择。')
                        destination.write(chunk)
                        if time.monotonic()-last_report>.04:
                            self.progress.emit(min(90,int(90*copied/total)),f'正在读取 {i+1}/{len(self.paths)} · {path.name}'); last_report=time.monotonic()
                copies.append(copy)
            if copied!=total:raise converter.ConversionError('读取期间文件大小发生变化，请重新选择。')
            for i,copy in enumerate(copies):
                self.progress.emit(90+int(8*i/len(copies)),f'正在识别 {i+1}/{len(copies)} · {self.paths[i].name}')
                metadata.append(converter.validate(copy,selection['ext']))
            ext=converter.normalize_extension(self.paths[0].suffix)
            targets=[target for target in converter.targets_for(ext,metadata[0]) if all(target in converter.targets_for(ext,info) for info in metadata)]
            if not targets:raise converter.ConversionError('所选文件没有共同可转换的目标格式，请分开添加。')
            item={'path':copies[0],'name':f'{len(copies)} 个 {file_policy.format_key(self.paths[0]).upper()} 文件' if multiple else self.paths[0].name,
                  'size':total,'ext':ext,'targets':targets,**metadata[0]}
            if multiple:
                item.update(paths=copies,names=[p.name for p in self.paths],count=len(copies))
                item['sheets']=[name for name in metadata[0].get('sheets',[]) if all(name in info.get('sheets',[]) for info in metadata)]
            self.progress.emit(98,'文件读取与识别完成')
            self.loaded.emit(item)
        except Exception as exc:
            if not isinstance(exc,converter.ConversionError): logging.exception('Desktop file validation failed')
            if folder.exists(): shutil.rmtree(folder,ignore_errors=True)
            self.failed.emit(str(exc) if isinstance(exc,converter.ConversionError) else '无法读取此文件，请检查文件是否完整或受到保护。')


class ConvertTask(QThread):
    progress = Signal(int,str)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self,item,target,options):
        super().__init__()
        self.item,self.target,self.options=item,target,options

    def run(self):
        folder = DATA / 'outputs' / uuid.uuid4().hex
        result = None
        try:
            if 'paths' in self.item:
                from batch_convert import convert_batch
                output,warnings=convert_batch(self.item,self.target,folder,self.options,self.progress.emit)
            else: output,warnings = converter.convert(self.item['path'],self.target,folder,self.options,self.progress.emit)
            stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',Path(self.item['name']).stem).strip(' .')[:90]
            if not stem or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',stem,re.I): stem='转换结果'
            result=output.with_name(stem+output.suffix)
            output.replace(result)
            self.completed.emit({'path':result,'name':result.name,'target':self.target,'warnings':warnings})
        except Exception as exc:
            logging.exception('Desktop conversion failed')
            self.failed.emit(str(exc) if isinstance(exc,converter.ConversionError) else '转换失败，文件内容可能不兼容，请在原软件中重新保存后尝试。')
        finally:
            if folder.exists():
                for entry in folder.iterdir():
                    if entry==result: continue
                    if entry.is_dir(): shutil.rmtree(entry,ignore_errors=True)
                    else: entry.unlink(missing_ok=True)


class ResizeHandle(QWidget):
    def __init__(self,parent,edges):
        super().__init__(parent)
        self.edges=edges; self.origin=None; self.initial=None
        horizontal=bool(edges & (Qt.Edge.LeftEdge|Qt.Edge.RightEdge))
        vertical=bool(edges & (Qt.Edge.TopEdge|Qt.Edge.BottomEdge))
        cursor=Qt.CursorShape.SizeHorCursor if horizontal else Qt.CursorShape.SizeVerCursor
        if horizontal and vertical:
            cursor=Qt.CursorShape.SizeFDiagCursor if edges in (Qt.Edge.LeftEdge|Qt.Edge.TopEdge,Qt.Edge.RightEdge|Qt.Edge.BottomEdge) else Qt.CursorShape.SizeBDiagCursor
        self.setCursor(cursor); self.hide()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.origin=event.globalPosition().toPoint(); self.initial=self.parentWidget().geometry()
            self.grabMouse(); event.accept()

    def mouseMoveEvent(self,event):
        if self.origin is None or not event.buttons() & Qt.MouseButton.LeftButton: return
        delta=event.globalPosition().toPoint()-self.origin; rect=QRect(self.initial); parent=self.parentWidget()
        if self.edges & Qt.Edge.LeftEdge: rect.setLeft(min(rect.right()-parent.minimumWidth()+1,rect.left()+delta.x()))
        if self.edges & Qt.Edge.RightEdge: rect.setRight(max(rect.left()+parent.minimumWidth()-1,rect.right()+delta.x()))
        if self.edges & Qt.Edge.TopEdge: rect.setTop(min(rect.bottom()-parent.minimumHeight()+1,rect.top()+delta.y()))
        if self.edges & Qt.Edge.BottomEdge: rect.setBottom(max(rect.top()+parent.minimumHeight()-1,rect.bottom()+delta.y()))
        parent.setGeometry(rect); parent.rectangle_geometry=QRect(rect)

    def mouseReleaseEvent(self,event):
        self.origin=None
        if QWidget.mouseGrabber() is self: self.releaseMouse()


class DesktopWidget(QWidget):
    def __init__(self, tray=True):
        super().__init__()
        DATA.mkdir(exist_ok=True)
        for name in ('uploads','outputs','logs'): (DATA/name).mkdir(exist_ok=True)
        self.setWindowTitle(NAME)
        self.setWindowIcon(app_icon())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self.expanded=False
        self.resize_handles=[]
        self.size_grip=None
        self.help_window=None
        self.rectangle_geometry=None
        self.normal_geometry=None
        self.radial=False
        self.radial_opening=False
        self.radial_scale=640/700
        self.radial_extent=COMPACT_RADIUS
        self.radial_drag_origin=None
        self.radial_drag_position=None
        self.hold_opened=False
        self.hold_timer=QTimer(self)
        self.hold_timer.setSingleShot(True); self.hold_timer.setInterval(520)
        self.hold_timer.timeout.connect(self.long_press)
        self.geometry_animation=QPropertyAnimation(self,b'geometry',self)
        self.geometry_animation.setDuration(330)
        self.geometry_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.geometry_animation.finished.connect(self.radial_geometry_finished)
        self.item=None
        self.result=None
        self.load_task=None
        self.convert_task=None
        self.loading=False
        self.converting=False
        self.history=[]
        self.archive_dialog=None; self.archive_task=None; self.archive_pending=False; self.archive_inspected=False; self.archive_queue=[]; self.archive_success=False
        self.archive_output=DATA/'outputs'
        self.active_module=0
        self.task_progress=TaskProgress(self); self.task_progress.changed.connect(self.sync_visual_progress)
        self.pinned=True
        self.press_pos=None
        self.drag_start=None
        self.dragged=False
        self.quitting=False
        self.settings_file=DATA/'widget-settings.json'
        settings={}
        try: settings=json.loads(self.settings_file.read_text('utf-8'))
        except (OSError,ValueError): pass
        screen=QApplication.primaryScreen().availableGeometry()
        default_position=QPoint(screen.right()-114,screen.top()+180)
        try:
            if not isinstance(settings,dict): raise ValueError('Expected a position object')
            x=int(settings.get('x',default_position.x())); y=int(settings.get('y',default_position.y()))
            if not all(-2**31<=value<2**31 for value in (x,y)): raise OverflowError('Position outside native integer range')
            self.orb_pos=QPoint(x,y)
        except (TypeError,ValueError,OverflowError):
            self.orb_pos=default_position
        self.orb_pos=self.bounded(self.orb_pos,96,96)
        self.panel=QWidget(self)
        self.panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,False)
        self.make_panel()
        self.panel.hide()
        self.radial_wheel=OrbitCanvas(self,radial_mode=True)
        self.radial_wheel.moduleClicked.connect(self.select_module)
        self.radial_wheel.targetClicked.connect(self.begin_conversion)
        self.radial_wheel.centerClicked.connect(self.collapse)
        self.radial_wheel.dragStarted.connect(self.start_circle_drag)
        self.radial_wheel.dragMoved.connect(self.move_circle_drag)
        self.radial_wheel.dragEnded.connect(self.finish_circle_drag)
        self.radial_wheel.hide()
        self.canvases=(self.wheel,self.radial_wheel)
        for canvas in self.canvases: canvas.filesDropped.connect(self.handle_dropped_paths)
        self.status.textChanged.connect(self.update_radial_feedback)
        for edges in (Qt.Edge.LeftEdge,Qt.Edge.RightEdge,Qt.Edge.TopEdge,Qt.Edge.BottomEdge,
                      Qt.Edge.LeftEdge|Qt.Edge.TopEdge,Qt.Edge.RightEdge|Qt.Edge.TopEdge,
                      Qt.Edge.LeftEdge|Qt.Edge.BottomEdge,Qt.Edge.RightEdge|Qt.Edge.BottomEdge):
            self.resize_handles.append(ResizeHandle(self,edges))
        self.size_grip=QSizeGrip(self); self.size_grip.hide()
        self.resize(96,96)
        self.move(self.orb_pos)
        self.apply_mask()
        self.setToolTip(NAME+'\n单击打开圆盘 · 长按打开矩形窗口\n拖动移动 · 文件可直接拖入中心')
        self.tray=None
        if tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray=QSystemTrayIcon(app_icon(),self)
            self.tray.setToolTip(NAME)
            self.tray.setContextMenu(self.make_menu())
            self.tray.activated.connect(lambda reason: self.expand() if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick) else None)
            self.tray.show()

    def make_panel(self):
        layout=QVBoxLayout(self.panel)
        layout.setContentsMargins(24,14,24,18)
        layout.setSpacing(10)
        header=QHBoxLayout()
        icon=QLabel(); icon.setPixmap(app_icon().pixmap(30,30)); header.addWidget(icon)
        name=QLabel(NAME); name.setObjectName('dragtitle'); name.setStyleSheet('font-size:16px;font-weight:600;'); header.addWidget(name)
        sub=QLabel('DESKTOP FILE STATION'); sub.setObjectName('muted'); sub.setFont(font(9)); header.addWidget(sub)
        header.addStretch()
        self.pin_button=self.control('◇','窗口置顶',self.toggle_pin)
        self.pin_button.setCheckable(True); self.pin_button.setChecked(True)
        header.addWidget(self.pin_button)
        header.addWidget(self.control('⋯','更多操作',self.show_menu))
        self.fullscreen_button=self.control('⛶','全屏 / 恢复窗口（F11）',self.toggle_fullscreen)
        self.minimize_button=self.control('−','收回圆形挂件',self.collapse)
        header.addWidget(self.minimize_button)
        header.addWidget(self.fullscreen_button)
        header.addWidget(self.control('×','收回挂件；右键菜单可彻底退出',self.collapse))
        layout.addLayout(header)
        rule=QFrame(); rule.setFixedHeight(1); rule.setStyleSheet('background:#193951;'); layout.addWidget(rule)
        body=QHBoxLayout(); body.setSpacing(18)
        left=QVBoxLayout(); left.setSpacing(0)
        top=QHBoxLayout(); title=QLabel('转 换 工 作 台'); title.setFont(font(11)); title.setObjectName('cyan'); top.addWidget(title)
        top.addStretch()
        left.addLayout(top)
        self.wheel=OrbitCanvas(); self.wheel.moduleClicked.connect(self.select_module); self.wheel.targetClicked.connect(self.begin_conversion)
        left.addWidget(self.wheel,1)
        self.wheel_hint=QLabel('01  选择板块       /       02  添加文件       /       03  点击外环转换')
        self.wheel_hint.setObjectName('muted'); self.wheel_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.wheel_hint)
        body.addLayout(left,1)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFixedWidth(296)
        inspector=QWidget(); right=QVBoxLayout(inspector); right.setContentsMargins(2,8,7,8); right.setSpacing(14)
        heading=QHBoxLayout(); self.module_title=QLabel('文档与办公'); self.module_title.setObjectName('section'); heading.addWidget(self.module_title); heading.addStretch()
        self.module_number=QLabel('MODULE 01'); self.module_number.setFont(font(9)); self.module_number.setObjectName('cyan'); heading.addWidget(self.module_number); right.addLayout(heading)
        self.upload_button=QPushButton('＋\n选择或拖入同格式文件\n本次合计 ≤ 500 MB'); self.upload_button.setObjectName('upload'); self.upload_button.setMinimumHeight(110)
        self.upload_button.setAccessibleName('选择办公文件'); self.upload_button.clicked.connect(self.choose_file); right.addWidget(self.upload_button)
        self.format_list=QLabel('DOC / DOCX · XLS / XLSX · PPT / PPTX\nPDF · MD · HTML · CSV · TXT · EPUB'); self.format_list.setWordWrap(True); self.format_list.setObjectName('formatList'); right.addWidget(self.format_list)
        self.file_card=QFrame(); self.file_card.setObjectName('card'); row=QHBoxLayout(self.file_card)
        self.file_badge=QLabel('DOCX'); self.file_badge.setObjectName('cyan'); self.file_badge.setFont(font(10,True)); row.addWidget(self.file_badge)
        self.file_name=QLabel(); self.file_name.setWordWrap(True); row.addWidget(self.file_name,1)
        self.remove_button=QPushButton('×'); self.remove_button.setObjectName('control'); self.remove_button.setFixedSize(23,25); self.remove_button.clicked.connect(self.remove_file); row.addWidget(self.remove_button)
        self.file_card.hide(); right.addWidget(self.file_card)
        self.options_box=QWidget(); self.options_layout=QVBoxLayout(self.options_box); self.options_layout.setContentsMargins(0,0,0,0); self.options_layout.setSpacing(12)
        self.merge_pdf=QCheckBox('多图转 PDF 时合并为一个文件'); self.merge_pdf.setChecked(True); self.merge_pdf.hide(); self.options_layout.addWidget(self.merge_pdf)
        self.ocr_check=QCheckBox('扫描页自动 OCR'); self.ocr_check.setChecked(True); self.options_layout.addWidget(self.ocr_check)
        self.dpi=QComboBox()
        for value,text in [(96,'96 DPI · 较小'),(150,'150 DPI · 标准'),(200,'200 DPI · 清晰'),(300,'300 DPI · 高清')]: self.dpi.addItem(text,value)
        self.dpi.setCurrentIndex(1)
        self.dpi_row=self.option_row('PNG 清晰度',self.dpi); self.options_layout.addWidget(self.dpi_row)
        self.sheets=QComboBox(); self.sheet_row=self.option_row('导出工作表',self.sheets); self.options_layout.addWidget(self.sheet_row)
        self.data_options=QWidget(); data_layout=QVBoxLayout(self.data_options); data_layout.setContentsMargins(0,0,0,0)
        self.xml_mode=QComboBox(); self.xml_mode.addItem('属性 @ / 文本 #text','preserve'); self.xml_mode.addItem('仅元素（忽略属性）','elements')
        self.xml_root=QLineEdit('root'); self.records_path=QLineEdit(); self.records_path.setPlaceholderText('如 data.items；留空用顶层')
        self.nested_csv=QComboBox(); self.nested_csv.addItem('JSON 文本','json'); self.nested_csv.addItem('拒绝嵌套','reject')
        for title,widget in [('XML 映射',self.xml_mode),('XML 根名称',self.xml_root),('CSV 记录路径',self.records_path),('CSV 嵌套字段',self.nested_csv)]: data_layout.addWidget(self.option_row(title,widget))
        self.options_layout.addWidget(self.data_options)
        self.media_options=QWidget(); media_layout=QVBoxLayout(self.media_options); media_layout.setContentsMargins(0,0,0,0)
        self.clip_start=QDoubleSpinBox(); self.clip_start.setRange(0,86400); self.clip_start.setSuffix(' 秒')
        self.clip_duration=QDoubleSpinBox(); self.clip_duration.setRange(.1,30); self.clip_duration.setValue(5); self.clip_duration.setSuffix(' 秒')
        self.gif_fps=QSpinBox(); self.gif_fps.setRange(1,30); self.gif_fps.setValue(12)
        self.gif_width=QSpinBox(); self.gif_width.setRange(64,1280); self.gif_width.setValue(480)
        for title,widget in [('GIF 起始',self.clip_start),('GIF 时长',self.clip_duration),('GIF 帧率',self.gif_fps),('GIF 宽度',self.gif_width)]: media_layout.addWidget(self.option_row(title,widget))
        self.options_layout.addWidget(self.media_options)
        self.options_box.hide(); right.addWidget(self.options_box)
        self.targets_caption=QLabel('从一个文件开始'); self.targets_caption.setObjectName('cyan'); right.addWidget(self.targets_caption)
        self.targets_box=QWidget(); self.targets_layout=QGridLayout(self.targets_box); self.targets_layout.setContentsMargins(0,0,0,0); self.targets_layout.setSpacing(8); right.addWidget(self.targets_box)
        self.note=QLabel('点击圆盘「文档与办公」，添加文件后，外环会自动展开可转换的格式。'); self.note.setWordWrap(True); self.note.setObjectName('guidance'); right.addWidget(self.note)
        self.progress=QProgressBar(); self.progress.setTextVisible(False); self.progress.setFixedHeight(5); self.progress.hide(); right.addWidget(self.progress)
        self.status=StatusLabel('本地运行，无需上传至互联网。'); self.status.setObjectName('guidance'); self.status.setWordWrap(True); self.status.setMinimumHeight(40); right.addWidget(self.status)
        self.save_button=QPushButton('另存转换结果'); self.save_button.setObjectName('primary'); self.save_button.clicked.connect(self.save_result); self.save_button.hide(); right.addWidget(self.save_button)
        self.result_folder_button=QPushButton('打开本次结果文件夹'); self.result_folder_button.clicked.connect(self.open_result); self.result_folder_button.hide(); right.addWidget(self.result_folder_button)
        self.warning=QLabel(); self.warning.setObjectName('warning'); self.warning.setWordWrap(True); self.warning.hide(); right.addWidget(self.warning)
        right.addStretch()
        self.history_button=QPushButton('转换记录  /  结果文件夹'); self.history_button.clicked.connect(self.open_history); right.addWidget(self.history_button)
        scroll.setWidget(inspector); body.addWidget(scroll); layout.addLayout(body,1)

    def control(self,text,tip,callback):
        button=QPushButton(text); button.setObjectName('control'); button.setFixedSize(29,29); button.setToolTip(tip); button.setAccessibleName(tip); button.clicked.connect(callback)
        return button

    def option_row(self,title,widget):
        row=QWidget(); layout=QHBoxLayout(row); layout.setContentsMargins(0,0,0,0); label=QLabel(title); label.setObjectName('muted'); layout.addWidget(label); layout.addWidget(widget,1)
        return row

    def make_menu(self):
        menu=QMenu(self)
        if self.item:
            action=menu.addAction('移除当前文件',self.remove_file); action.setEnabled(not self.loading and not self.converting)
            menu.addSeparator()
        menu.addAction('展开工作台',self.expand)
        menu.addAction('展开圆形工作台',self.show_radial)
        menu.addAction('收回圆形挂件',self.collapse)
        menu.addSeparator()
        action=menu.addAction('窗口置顶'); action.setCheckable(True); action.setChecked(self.pinned); action.triggered.connect(self.toggle_pin)
        if self.expanded: menu.addAction('退出全屏' if self.isFullScreen() else '全屏',self.toggle_fullscreen)
        menu.addAction('打开结果文件夹',self.open_history)
        if self.archive_dialog:menu.addAction('显示破译窗口',self.start_archive)
        if self.archive_queue and not self.archive_dialog:
            action=menu.addAction(f'继续下一个压缩包（{len(self.archive_queue)}）',self.advance_archive_queue); action.setEnabled(not self.loading and not self.converting)
        if self.item:
            settings=menu.addMenu('转换选项')
            if self.item['ext']=='pdf':
                action=settings.addAction('扫描页自动 OCR'); action.setCheckable(True); action.setChecked(self.ocr_check.isChecked()); action.toggled.connect(self.ocr_check.setChecked)
                dpi=settings.addMenu('PNG 清晰度')
                for i in range(self.dpi.count()):
                    action=dpi.addAction(self.dpi.itemText(i)); action.setCheckable(True); action.setChecked(self.dpi.currentIndex()==i)
                    action.triggered.connect(lambda checked=False,index=i:self.dpi.setCurrentIndex(index))
            elif self.item['ext'] in ('xls','xlsx'):
                for i in range(self.sheets.count()):
                    action=settings.addAction('导出工作表：'+self.sheets.itemText(i)); action.setCheckable(True); action.setChecked(self.sheets.currentIndex()==i)
                    action.triggered.connect(lambda checked=False,index=i:self.sheets.setCurrentIndex(index))
            elif self.item['ext'] in ('json','xml'):
                settings.addAction('设置数据映射…',self.edit_data_options)
            elif self.item['ext']=='mp4': settings.addAction('设置 GIF 截取…',self.edit_gif_options)
            elif 'paths' in self.item and self.item['ext'] in ('jpg','png'):
                action=settings.addAction('多图转 PDF 时合并'); action.setCheckable(True); action.setChecked(self.merge_pdf.isChecked()); action.toggled.connect(self.merge_pdf.setChecked)
            else: settings.addAction('此文件无需额外设置').setEnabled(False)
            settings.setEnabled(not self.loading and not self.converting)
        if self.result:
            if self.result['path'].is_file():menu.addAction('另存转换结果',self.save_result)
            menu.addAction('打开本次结果文件夹',self.open_result)
        menu.addAction('使用说明',self.show_help)
        menu.addSeparator(); menu.addAction('退出工具',self.quit_app)
        return menu

    def show_menu(self):
        menu=self.make_menu(); menu.exec(self.mapToGlobal(QPoint(self.width()-145,50))); menu.deleteLater()

    def contextMenuEvent(self,event):
        menu=self.make_menu(); menu.exec(event.globalPos()); menu.deleteLater()

    def bounded(self,position,width,height):
        screen=QApplication.screenAt(position+QPoint(width//2,height//2)) or self.screen() or QApplication.primaryScreen()
        rect=screen.availableGeometry()
        return QPoint(max(rect.left(),min(position.x(),rect.right()-width+1)),max(rect.top(),min(position.y(),rect.bottom()-height+1)))

    def apply_mask(self):
        if self.expanded and self.isFullScreen(): self.clearMask()
        elif self.expanded:
            path=QPainterPath(); path.addRoundedRect(QRectF(3,3,self.width()-6,self.height()-6),19,19)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        elif self.radial:
            self.setMask(QRegion(4,4,max(1,self.width()-8),max(1,self.height()-8),QRegion.RegionType.Ellipse))
        else: self.setMask(QRegion(4,4,88,88,QRegion.RegionType.Ellipse))

    def resizeEvent(self,event):
        if self.expanded and hasattr(self,'panel'):
            self.panel.setGeometry(5,5,self.width()-10,self.height()-10)
            self.apply_mask()
        if self.radial and hasattr(self,'radial_wheel'):
            self.radial_wheel.setGeometry(self.rect())
            self.radial_wheel.view_radius=self.radial_extent if self.radial_opening else self.width()/(2*self.radial_scale)
            self.radial_wheel.update()
            self.apply_mask()
        super().resizeEvent(event)
        self.update_resize_handles()

    def update_resize_handles(self):
        visible=self.expanded and not self.isFullScreen()
        width,height=self.width(),self.height()
        for handle in self.resize_handles:
            left=bool(handle.edges & Qt.Edge.LeftEdge); right=bool(handle.edges & Qt.Edge.RightEdge)
            top=bool(handle.edges & Qt.Edge.TopEdge); bottom=bool(handle.edges & Qt.Edge.BottomEdge)
            if (left or right) and (top or bottom):
                rect=QRect(0 if left else width-16,0 if top else height-16,16,16)
            elif left or right: rect=QRect(0 if left else width-7,16,7,max(1,height-32))
            else: rect=QRect(16,0 if top else height-7,max(1,width-32),7)
            handle.setGeometry(rect); handle.setVisible(visible); handle.raise_()
        if self.size_grip:
            self.size_grip.setGeometry(width-26,height-26,20,20); self.size_grip.setVisible(visible); self.size_grip.raise_()

    def toggle_fullscreen(self):
        if not self.expanded: self.expand()
        if self.isFullScreen():
            self.showNormal()
            if self.normal_geometry: self.setGeometry(self.normal_geometry)
            self.fullscreen_button.setText('⛶')
        else:
            self.normal_geometry=QRect(self.geometry()); self.showFullScreen(); self.fullscreen_button.setText('❐')
        self.apply_mask(); self.update_resize_handles()

    def radial_geometry_finished(self):
        if self.radial:
            self.radial_opening=False
            self.radial_wheel.view_radius=self.width()/(2*self.radial_scale)
            self.radial_wheel.update()

    def resize_circle_for_file(self):
        if not self.radial: return
        self.geometry_animation.stop()
        self.radial_opening=False
        self.radial_extent=FULL_RADIUS if self.item and self.item['targets'] else COMPACT_RADIUS
        size=round(2*self.radial_extent*self.radial_scale)
        center=self.geometry().center()
        pos=self.bounded(center-QPoint(size//2,size//2),size,size)
        self.geometry_animation.setStartValue(self.geometry())
        self.geometry_animation.setEndValue(QRect(pos.x(),pos.y(),size,size))
        self.geometry_animation.start()

    def start_circle_drag(self,origin):
        self.geometry_animation.stop(); self.radial_opening=False
        self.radial_drag_origin=origin; self.radial_drag_position=self.pos()

    def move_circle_drag(self,point):
        if self.radial_drag_origin is not None:
            self.move(self.radial_drag_position+point-self.radial_drag_origin)

    def finish_circle_drag(self):
        self.radial_drag_origin=None
        self.move(self.bounded(self.pos(),self.width(),self.height()))
        self.orb_pos=self.bounded(self.geometry().center()-QPoint(48,48),96,96)
        self.save_position()
        size=round(2*(FULL_RADIUS if self.item else COMPACT_RADIUS)*self.radial_scale)
        if self.width()!=size: self.resize_circle_for_file()

    def long_press(self):
        if self.press_pos is not None and not self.dragged and not self.expanded and not self.radial:
            self.hold_opened=True
            self.expand()

    def show_radial(self):
        self.hold_timer.stop()
        if self.radial:
            self.show(); self.raise_(); return
        self.geometry_animation.stop()
        if self.isFullScreen(): self.showNormal()
        if self.expanded: self.rectangle_geometry=QRect(self.geometry())
        self.setMinimumSize(0,0)
        if not self.expanded: self.orb_pos=self.pos()
        self.expanded=False; self.radial=True; self.panel.hide()
        self.setToolTip('')
        screen=(QApplication.screenAt(self.orb_pos+QPoint(48,48)) or self.screen()).availableGeometry()
        self.radial_scale=min(640,screen.width()-24,screen.height()-24)/700
        self.radial_extent=FULL_RADIUS if self.item and self.item['targets'] else COMPACT_RADIUS
        self.radial_opening=True
        self.radial_wheel.view_radius=self.radial_extent
        size=round(2*self.radial_extent*self.radial_scale)
        pos=self.bounded(self.orb_pos+QPoint(48-size//2,48-size//2),size,size)
        start=QRect(self.orb_pos.x(),self.orb_pos.y(),96,96)
        self.setGeometry(start)
        self.radial_wheel.setGeometry(self.rect()); self.radial_wheel.show()
        self.radial_wheel.setFocus(); self.apply_mask()
        self.update_radial_feedback(self.status.text())
        self.show(); self.raise_(); self.activateWindow()
        self.geometry_animation.setStartValue(start)
        self.geometry_animation.setEndValue(QRect(pos.x(),pos.y(),size,size))
        self.geometry_animation.start()
        self.update_resize_handles()

    def expand(self):
        self.hold_timer.stop(); self.geometry_animation.stop()
        if self.expanded:
            self.show(); self.raise_(); self.activateWindow(); return
        if not self.radial: self.orb_pos=self.pos()
        self.radial=False; self.radial_wheel.hide()
        screen=(QApplication.screenAt(self.orb_pos+QPoint(48,48)) or self.screen()).availableGeometry()
        width=min(1040,screen.width()-24); height=min(750,screen.height()-24)
        self.expanded=True
        self.setMinimumSize(min(840,screen.width()-24),min(580,screen.height()-24))
        self.setToolTip('')
        self.resize(width,height)
        self.move(self.bounded(self.orb_pos+QPoint(48-width//2,48-height//2),width,height))
        self.panel.setGeometry(5,5,width-10,height-10); self.panel.show(); self.apply_mask()
        if self.rectangle_geometry:
            rect=self.rectangle_geometry
            size=rect.size().boundedTo(screen.size())
            pos=self.bounded(rect.topLeft(),size.width(),size.height())
            self.setGeometry(QRect(pos,size))
        self.update_resize_handles()
        self.show(); self.raise_(); self.activateWindow(); self.update()

    def collapse(self):
        self.hold_timer.stop(); self.geometry_animation.stop()
        if not self.expanded and not self.radial: return
        if self.isFullScreen(): self.showNormal()
        if self.expanded: self.rectangle_geometry=QRect(self.geometry())
        self.setMinimumSize(0,0)
        self.expanded=False; self.radial=False; self.radial_opening=False; self.panel.hide(); self.radial_wheel.hide(); self.resize(96,96)
        self.move(self.bounded(self.orb_pos,96,96)); self.apply_mask()
        self.setToolTip(NAME+'\n单击打开圆盘 · 长按打开矩形窗口\n拖动移动 · 文件可直接拖入中心'); self.update(); self.save_position()
        self.update_resize_handles()

    def toggle_pin(self,*args):
        self.pinned=not self.pinned
        windows=[self]+[window for window in (self.help_window,self.archive_dialog) if window is not None]
        states=[(window,window.isVisible(),window.windowState(),QRect(window.geometry())) for window in windows]
        for window,_,_,_ in states:
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,self.pinned)
        for window,visible,state,geometry in states:
            window.setWindowState(state)
            if not state & (Qt.WindowState.WindowFullScreen|Qt.WindowState.WindowMaximized):window.setGeometry(geometry)
            if visible:window.show()
        self.pin_button.setChecked(self.pinned); self.apply_mask()
        if self.tray: self.tray.setContextMenu(self.make_menu())

    def save_position(self):
        point=self.orb_pos if self.expanded or self.radial else self.pos()
        try: self.settings_file.write_text(json.dumps({'x':point.x(),'y':point.y()}),'utf-8')
        except OSError: logging.exception('Cannot save widget position')

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:
            self.hold_timer.stop()
        if event.button()==Qt.MouseButton.LeftButton and ((not self.expanded and not self.radial) or (self.expanded and event.position().y()<65)):
            self.press_pos=event.globalPosition().toPoint(); self.drag_start=self.pos(); self.dragged=False
            self.hold_opened=False
            if not self.expanded and not self.radial: self.hold_timer.start()

    def mouseMoveEvent(self,event):
        if self.press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if self.hold_opened:
                return
            delta=event.globalPosition().toPoint()-self.press_pos
            if delta.manhattanLength()>QApplication.startDragDistance():
                self.dragged=True; self.hold_timer.stop()
            if self.dragged: self.move(self.drag_start+delta)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.press_pos is not None:
            self.hold_timer.stop()
            clicked=not self.dragged
            self.press_pos=None
            if self.hold_opened:
                self.hold_opened=False
                return
            self.move(self.bounded(self.pos(),self.width(),self.height()))
            if not self.expanded and not self.radial:
                self.orb_pos=self.pos(); self.save_position()
                if clicked: self.show_radial()
            elif self.dragged:
                # Keep the orb near the panel after dragging the expanded workbench.
                self.orb_pos=self.bounded(self.pos()+QPoint(self.width()-104,8),96,96); self.save_position()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_F11: self.toggle_fullscreen()
        elif event.key()==Qt.Key.Key_Escape:
            if self.isFullScreen(): self.toggle_fullscreen()
            else: self.collapse()
        else: super().keyPressEvent(event)

    def closeEvent(self,event):
        if self.quitting: event.accept()
        else: event.ignore(); self.collapse()

    def quit_app(self):
        if self.loading or self.converting:
            if not self.radial: self.expand()
            self.status.setText('请等待当前文件处理完成后再退出。'); return
        self.hold_timer.stop(); self.geometry_animation.stop()
        self.save_position(); self.quitting=True
        if self.tray: self.tray.hide()
        self.close(); QApplication.instance().quit()

    def show_help(self):
        from help_dialog import HelpDialog
        if self.help_window is None: self.help_window=HelpDialog(self)
        self.help_window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,self.pinned)
        self.help_window.show(); self.help_window.raise_(); self.help_window.activateWindow()

    def select_module(self,index):
        if self.loading or self.converting: return
        previous=self.active_module
        self.set_module(index)
        for canvas in self.canvases: canvas.selected=True; canvas.update()
        if not self.choose_file() and self.item: self.set_module(previous)

    def set_module(self,index):
        self.active_module=index
        for canvas in self.canvases: canvas.active_module=index; canvas.update()
        self.module_title.setText(MODULES[index][0]); self.module_number.setText(f'MODULE {index+1:02d}')
        self.upload_button.setAccessibleName('选择'+MODULES[index][0]+'文件')
        self.upload_button.setText(('＋\n选择或拖入同格式压缩包\n' if index==4 else '＋\n选择或拖入同格式文件\n')+'本次合计 ≤ '+file_policy.limit_text(index))
        self.format_list.setText(['DOC / DOCX · XLS / XLSX · PPT / PPTX\nPDF · MD · HTML · CSV · TXT · EPUB','JPG / PNG · TIFF · WebP · HEIC · AVIF\nRAW · SVG · GIF · 多图合并 PDF','JSON / JSONL · YAML · XML · CSV / TSV\n记录数组 · Excel 连接','MP4 · WebM · MKV · MOV\nMP3 · M4A · AAC · WAV · FLAC','ZIP · RAR · 7z · TAR / TAR.GZ / TAR.XZ\n第一分卷 · 无密码自动解压'][index])

    def choose_file(self):
        if self.loading or self.converting: return
        if self.active_module==4:
            filters='压缩包 (*.zip *.rar *.7z *.001 *.tar *.tar.gz *.tgz *.tar.xz *.txz)'
        elif self.active_module==1:
            extensions=' '.join('*.'+ext for ext in (*converter.IMAGE_EXTENSIONS,'jpeg','jpe','tif','heif',*converter.RAW_EXTENSIONS))
            filters=f'图片与图像 ({extensions})'
        elif self.active_module in (2,3):
            filters='结构化数据 (*.json *.jsonl *.ndjson *.yaml *.yml *.xml *.csv *.tsv *.xlsx)' if self.active_module==2 else '音视频 (*.mp4 *.webm *.mkv *.mov *.wav *.flac *.mp3 *.m4a *.aac)'
        else:filters='办公文件 (*.doc *.docx *.pdf *.xls *.xlsx *.ppt *.pptx *.md *.html *.htm *.csv *.txt *.epub)'
        paths,_=QFileDialog.getOpenFileNames(self,'添加'+MODULES[self.active_module][0]+'（可多选同格式，本次合计 ≤ '+file_policy.limit_text(self.active_module)+'）','',filters)
        if paths: self.load_file(paths); return True
        return False

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self,event):
        paths=[url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.handle_dropped_paths(paths); event.acceptProposedAction()

    def handle_dropped_paths(self,paths):
        if not self.expanded and not self.radial: self.show_radial()
        if not paths: return
        self.load_file(paths if len(paths)>1 else paths[0])

    def load_file(self,path):
        if self.loading or self.converting:
            self.status.setText('当前文件正在处理，请稍候。'); return
        if not self.radial and not self.expanded: self.show_radial()
        try: selection=file_policy.validate_selection(path if isinstance(path,(list,tuple)) else [path])
        except (converter.ConversionError,OSError) as exc:self.status.setText(str(exc)); return
        self.archive_queue=[]
        if self.archive_dialog:self.archive_dialog.close(); self.archive_dialog.deleteLater(); self.archive_dialog=None
        self.loading=True; self.upload_button.setEnabled(False); self.task_progress.start(estimated=False)
        self.remove_button.setEnabled(False)
        for canvas in self.canvases:
            canvas.busy=True; canvas.reading=True; canvas.hover=None; canvas.animate_hover()
            canvas.file_label=selection['paths'][0].name if len(selection['paths'])==1 else f'{len(selection["paths"])} 个同格式文件'
            canvas.update()
        self.status.setText('正在读取文件…')
        self.archive_inspected=False
        self.archive_pending=selection['module']==4
        if self.archive_pending:
            from archive_ui import ArchiveInspectTask
            task=ArchiveInspectTask(selection['paths'])
        else:task=LoadTask(path)
        task.setParent(self); self.load_task=task
        task.progress.connect(self.update_progress)
        task.loaded.connect(self.file_loaded); task.failed.connect(self.operation_failed)
        task.finished.connect(self.load_finished); task.start()

    def load_finished(self):
        self.loading=False; self.upload_button.setEnabled(True); self.remove_button.setEnabled(True)
        if self.item: self.set_module(4 if self.item.get('managed') is False else converter.module_for(self.item['ext']))
        for canvas in self.canvases:
            canvas.busy=False; canvas.reading=False; canvas.file_label=self.item['name'] if self.item else ''; canvas.update()
        self.load_task.wait(); self.load_task.deleteLater(); self.load_task=None
        if self.archive_pending and self.archive_inspected and self.item and self.item.get('managed') is False:
            self.archive_pending=False; item=self.item
            QTimer.singleShot(0,lambda:self.start_archive() if self.item is item else None)

    def file_loaded(self,item):
        if 'archive_items' in item:
            self.archive_queue=list(item['archive_items'][1:]); item=item['archive_items'][0]
        self.archive_inspected=item.get('managed') is False
        previous=self.item; self.item=item
        if previous and previous.get('managed',True): shutil.rmtree(previous['path'].parent,ignore_errors=True)
        self.result=None; self.save_button.hide(); self.result_folder_button.hide(); self.warning.hide(); self.progress.hide()
        if self.loading:self.task_progress.complete()
        else:self.task_progress.reset()
        self.set_module(4 if item.get('managed') is False else converter.module_for(item['ext']))
        self.file_card.show(); self.file_badge.setText('批量' if 'paths' in item else item['ext'].upper()); self.file_name.setText(item['name']); self.file_name.setToolTip('\n'.join(item.get('names',[item['name']])))
        self.ocr_check.setVisible(item['ext']=='pdf'); self.dpi_row.setVisible(item['ext']=='pdf'); self.sheet_row.setVisible(item['ext'] in ('xls','xlsx'))
        self.sheets.clear()
        if 'paths' in item:self.sheets.addItem('每个文件的第一张工作表',None)
        for sheet in item.get('sheets',[]):self.sheets.addItem(sheet,sheet)
        self.data_options.setVisible(item['ext'] in ('json','xml')); self.media_options.setVisible(item['ext']=='mp4')
        merge='paths' in item and item['ext'] in ('jpg','png'); self.merge_pdf.setVisible(merge)
        self.options_box.setVisible(merge or item['ext'] in ('pdf','xls','xlsx','json','xml','mp4'))
        self.clip_start.setValue(0)
        for canvas in self.canvases:
            canvas.selected=True; canvas.file_label=item['name']
            canvas.set_targets(item['targets'],item['ext'])
        self.resize_circle_for_file()
        self.clear_target_buttons()
        for i,target in enumerate(item['targets']):
            button=QPushButton('解压 / 破译' if target=='extract' else target.upper()); button.setToolTip(converter.NOTES.get(item['ext']+':'+target,'点击开始转换')); button.clicked.connect(lambda checked=False,t=target:self.begin_conversion(t))
            self.targets_layout.addWidget(button,i//2,i%2)
        self.targets_caption.setText('可转换为  /  '+str(len(item['targets'])))
        self.note.setText('点击圆盘外环的目标格式，开始转换。' if item['targets'] else '原示意图中，此类型仅为输出格式，暂无后续转换方向。请更换文件。')
        self.status.setText(f'已添加 {item["count"]} 个同格式文件 · 顺序处理' if 'paths' in item else f'已识别 {item["ext"].upper()} · 已选择{MODULES[self.active_module][0]}'+(f' · 待处理 {len(self.archive_queue)} 个' if self.archive_queue else ''))
        if not item['targets']: self.status.setText(item['ext'].upper()+' 暂无转换方向，请更换文件。')

    def clear_target_buttons(self):
        while self.targets_layout.count():
            entry=self.targets_layout.takeAt(0)
            if entry.widget(): entry.widget().deleteLater()

    def remove_file(self):
        if self.loading or self.converting: return
        self.archive_queue=[]
        if self.archive_dialog:self.archive_dialog.close(); self.archive_dialog.deleteLater(); self.archive_dialog=None
        if self.item and self.item.get('managed',True): shutil.rmtree(self.item['path'].parent,ignore_errors=True)
        self.task_progress.reset()
        self.item=None; self.result=None; self.file_card.hide(); self.options_box.hide(); self.warning.hide(); self.progress.hide(); self.save_button.hide(); self.result_folder_button.hide()
        self.clear_target_buttons()
        for canvas in self.canvases:
            canvas.file_label=''; canvas.set_targets([])
            canvas.suppressed_module=None; canvas.animate_hover()
        self.resize_circle_for_file()
        self.targets_caption.setText('从一个文件开始'); self.note.setText('添加'+('图片' if self.active_module else '办公文档')+'，自动展开可转换格式。'); self.status.setText('本地处理 · 文件可直接拖入中心')

    def begin_conversion(self,target):
        if not self.item or self.loading or self.converting: return
        if target=='extract':self.start_archive(); return
        if target not in self.item['targets']: return
        self.converting=True; self.result=None
        self.task_progress.start()
        for canvas in self.canvases: canvas.busy=True; canvas.update()
        self.update()
        self.upload_button.setEnabled(False); self.remove_button.setEnabled(False); self.targets_box.setEnabled(False); self.options_box.setEnabled(False)
        self.note.setText(converter.NOTES.get(self.item['ext']+':'+target,'正在转换文档。'))
        self.progress.setValue(0); self.progress.show(); self.warning.hide(); self.save_button.hide(); self.result_folder_button.hide()
        self.status.setText('正在准备转换…')
        task=ConvertTask(self.item,target,self.conversion_options())
        task.setParent(self); self.convert_task=task; task.progress.connect(self.update_progress); task.completed.connect(self.conversion_done); task.failed.connect(self.operation_failed)
        task.finished.connect(self.conversion_finished); task.start()

    def conversion_options(self):
        return {'ocr':self.ocr_check.isChecked(),'dpi':self.dpi.currentData(),'sheet':self.sheets.currentData(), 'merge_pdf':self.merge_pdf.isChecked(),
                'xml_mode':self.xml_mode.currentData(),'xml_root':self.xml_root.text(),'records_path':self.records_path.text(),
                'nested_csv':self.nested_csv.currentData(),'clip_start':self.clip_start.value(),'clip_duration':self.clip_duration.value(),
                'gif_fps':self.gif_fps.value(),'gif_width':self.gif_width.value()}

    def edit_data_options(self):
        self.edit_options('数据映射',[('XML 根名称',self.xml_root),('CSV 记录路径',self.records_path),('XML 映射',self.xml_mode),('CSV 嵌套字段',self.nested_csv)])

    def edit_gif_options(self):
        self.edit_options('GIF 截取',[('起始秒数',self.clip_start),('时长（最多30秒）',self.clip_duration),('帧率',self.gif_fps),('宽度',self.gif_width)])

    def prepare_dialog(self,dialog):
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,self.pinned)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setStyleSheet(STYLE+'QDialog{background:#10324f;} QLineEdit,QTextEdit,QPlainTextEdit,QSpinBox,QDoubleSpinBox{background:#0c2843;color:#def3ff;border:1px solid #4c83aa;border-radius:5px;padding:7px;} QTabWidget::pane{border:1px solid #37698b;} QTabBar::tab{background:#174267;color:#d0eaff;padding:10px;} QTabBar::tab:selected{background:#237cab;}')
        QTimer.singleShot(0,lambda:(dialog.raise_(),dialog.activateWindow()))
        return dialog

    def edit_options(self,title,fields):
        dialog=self.prepare_dialog(QDialog(self)); dialog.setWindowTitle(NAME+' · '+title)
        dialog.setMinimumWidth(440); layout=QVBoxLayout(dialog); form=QFormLayout(); edits=[]
        for caption,original in fields:
            if isinstance(original,QComboBox):
                editor=QComboBox()
                for i in range(original.count()): editor.addItem(original.itemText(i),original.itemData(i))
                editor.setCurrentIndex(original.currentIndex())
            elif isinstance(original,QLineEdit): editor=QLineEdit(original.text())
            else:
                editor=QDoubleSpinBox() if isinstance(original,QDoubleSpinBox) else QSpinBox()
                editor.setRange(original.minimum(),original.maximum()); editor.setValue(original.value())
            form.addRow(caption,editor); edits.append((original,editor))
        layout.addLayout(form); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('保存设置'); buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            for original,editor in edits:
                if isinstance(original,QComboBox): original.setCurrentIndex(editor.currentIndex())
                elif isinstance(original,QLineEdit): original.setText(editor.text())
                else: original.setValue(editor.value())
        dialog.deleteLater()

    def update_progress(self,value,message):
        self.task_progress.report(value); self.status.setText(message)

    def start_archive(self):
        if self.archive_dialog and self.archive_dialog.item is self.item:
            dialog=self.archive_dialog
            if dialog.isMinimized():dialog.showNormal()
            dialog.show(); dialog.raise_(); dialog.activateWindow(); return
        if self.loading or self.converting or not self.item or self.item.get('managed') is not False:return
        from archive_ui import ArchiveDialog,ArchiveTask
        if self.item['encrypted']:
            if self.archive_dialog:self.archive_dialog.deleteLater()
            self.archive_dialog=ArchiveDialog(self,self.item); self.archive_dialog.show(); self.archive_dialog.raise_(); self.archive_dialog.activateWindow()
        else:
            self.archive_search_started(); self.status.setText('压缩包无密码，正在自动解压…')
            task=ArchiveTask(self.item['path'],{},True,True,self.archive_output); task.setParent(self); self.archive_task=task
            task.snapshot.connect(self.archive_snapshot); task.backend.connect(self.status.setText); task.completed.connect(self.archive_completed); task.failed.connect(self.archive_failed)
            task.stopped.connect(lambda:self.archive_failed('已停止解压。')); task.finished.connect(self.archive_extract_finished); task.start()

    def archive_snapshot(self,snapshot):
        if isinstance(snapshot,(tuple,list)) and len(snapshot)==2 and isinstance(snapshot[1],dict):
            values=snapshot[1]
            if values.get('total'):self.task_progress.report(min(98,100*values.get('tested',0)/values['total']))

    def archive_search_started(self):
        self.archive_success=False
        self.converting=True; self.task_progress.start(); self.upload_button.setEnabled(False); self.remove_button.setEnabled(False)
        for canvas in self.canvases:canvas.busy=True; canvas.update()

    def archive_completed(self,info):
        self.archive_success=bool(info.get('found'))
        self.status.setText(info['message'])
        if info.get('found'):self.task_progress.complete()
        else:self.task_progress.reset()
        destination=info.get('destination')
        if destination:
            self.result={'path':Path(destination),'name':Path(destination).name,'target':'extract','warnings':[]}
            self.history.append(self.result); self.history_button.setText(f'处理记录（{len(self.history)}） / 结果文件夹')
            self.result_folder_button.show(); self.save_button.hide()

    def archive_failed(self,message):
        self.task_progress.reset(); self.status.setText(message)

    def archive_search_finished(self):
        self.converting=False; self.upload_button.setEnabled(True); self.remove_button.setEnabled(True)
        for canvas in self.canvases:canvas.busy=False; canvas.update()

    def archive_extract_finished(self):
        task=self.archive_task; task.wait(); self.archive_task=None; task.deleteLater(); self.archive_search_finished()
        if self.archive_success and self.archive_queue:
            item=self.item; QTimer.singleShot(400,lambda:self.advance_archive_queue() if self.item is item else None)

    def advance_archive_queue(self):
        if self.converting or self.loading or not self.archive_queue:return
        if self.archive_dialog:
            dialog=self.archive_dialog; self.archive_dialog=None; dialog.advancing=True; dialog.close(); dialog.deleteLater()
        item=self.archive_queue.pop(0); self.file_loaded(item); self.start_archive()

    def sync_visual_progress(self):
        visual=self.task_progress
        self.progress.setValue(round(visual.value))
        for canvas in self.canvases:
            canvas.conversion_progress=visual.value; canvas.progress_visible=visual.visible
            canvas.halo_opacity=visual.opacity; canvas.update()

    def conversion_done(self,result):
        self.result=result; self.history.append(result); self.task_progress.complete()
        self.status.setText('转换完成 · '+result['name']+'\n已自动保存到结果文件夹。')
        self.save_button.show(); self.result_folder_button.show()
        self.warning.setText('\n'.join(result['warnings'])); self.warning.setVisible(bool(result['warnings']))
        self.history_button.setText(f'转换记录（{len(self.history)}） /  结果文件夹')
        if not self.expanded and self.tray: self.tray.showMessage(NAME,'转换完成：'+result['name'],QSystemTrayIcon.MessageIcon.Information,4000)

    def conversion_finished(self):
        self.converting=False
        for canvas in self.canvases: canvas.busy=False; canvas.update()
        self.update()
        self.upload_button.setEnabled(True); self.remove_button.setEnabled(True); self.targets_box.setEnabled(True); self.options_box.setEnabled(True)
        self.convert_task.wait(); self.convert_task.deleteLater(); self.convert_task=None

    def operation_failed(self,message):
        if self.converting or self.loading: self.task_progress.reset()
        self.status.setText(message); self.progress.hide()

    def update_radial_feedback(self,message):
        self.radial_wheel.status_message=message
        self.radial_wheel.has_result=self.result is not None and not self.loading and not self.converting
        self.radial_wheel.update()

    def save_result(self):
        if not self.result: return
        path,_=QFileDialog.getSaveFileName(self,'另存转换结果',str(Path.home()/'Desktop'/self.result['name']))
        if path:
            try:
                if Path(path).resolve()!=self.result['path'].resolve(): shutil.copy2(self.result['path'],path)
                self.status.setText('已保存到：'+path)
            except OSError: self.status.setText('无法保存到此位置，请选择一个可写的文件夹。')

    def open_result(self):
        if self.result: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result['path'] if self.result['path'].is_dir() else self.result['path'].parent)))

    def open_history(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA/'outputs')))

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.expanded and not self.radial:
            gradient=QRadialGradient(31,24,80)
            gradient.setColorAt(0,QColor('#2b85bc')); gradient.setColorAt(.65,QColor('#124773')); gradient.setColorAt(1,QColor('#0c2d50'))
            p.setBrush(gradient); p.setPen(QPen(QColor('#236791'),1.2)); p.drawEllipse(QRectF(5,5,86,86))
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor('#40caff'),2)); p.drawArc(QRectF(8,8,80,80),28*16,100*16)
            p.setPen(QPen(QColor('#2387c4'),1)); p.drawArc(QRectF(12,12,72,72),200*16,100*16)
            logo(p,QRectF(25,24,46,46))
            p.setBrush(QColor('#ffd17b' if self.converting else '#43caff')); p.setPen(QPen(QColor('#08213c'),2)); p.drawEllipse(QPointF(74,75),4,4)
        elif self.radial:
            gradient=QRadialGradient(self.width()*.38,self.height()*.28,self.width()*.8)
            gradient.setColorAt(0,QColor('#164f7d')); gradient.setColorAt(1,QColor('#0b2441'))
            p.setBrush(gradient); p.setPen(QPen(QColor('#5fcfff'),1.4))
            p.drawEllipse(QRectF(5,5,self.width()-10,self.height()-10))
        else:
            gradient=QLinearGradient(0,0,self.width(),self.height()); gradient.setColorAt(0,QColor('#123553')); gradient.setColorAt(1,QColor('#0b243e'))
            p.setBrush(gradient); p.setPen(QPen(QColor('#245275'),1))
            if self.isFullScreen(): p.drawRect(self.rect())
            else: p.drawRoundedRect(QRectF(4,4,self.width()-8,self.height()-8),19,19)
            p.setPen(QPen(QColor('#39bfff'),1.6)); p.drawLine(30,4,190,4)
            p.setPen(QPen(QColor('#2471a3'),1)); p.drawLine(self.width()-140,self.height()-5,self.width()-30,self.height()-5)
        p.end()


def run_desktop():
    qt=QApplication.instance() or QApplication(sys.argv[:1])
    qt.setApplicationName(NAME); qt.setApplicationVersion(VERSION); qt.setQuitOnLastWindowClosed(False); qt.setWindowIcon(app_icon())
    name='k-file-station-'+hashlib.sha256(str(converter.HOME).encode()).hexdigest()[:20]
    socket=QLocalSocket(); socket.connectToServer(name)
    if socket.waitForConnected(200):
        socket.write(b'activate'); socket.waitForBytesWritten(200); socket.disconnectFromServer(); return 0
    server=QLocalServer(); QLocalServer.removeServer(name)
    if not server.listen(name): raise RuntimeError('无法创建本地挂件会话。')
    widget=DesktopWidget()
    def activate():
        connection=server.nextPendingConnection()
        widget.expand()
        if connection: connection.disconnectFromServer(); connection.deleteLater()
    server.newConnection.connect(activate)
    widget.show()
    result=qt.exec(); server.close(); return result


if __name__=='__main__':
    raise SystemExit(run_desktop())
