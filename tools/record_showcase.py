"""Record actual Qt interactions on white, with generated public fixtures only.

Captures the application's own windows (never the user's desktop). Mouse and
file-drop events go through Qt; conversions and password recovery run normally.
Captions and the demonstration pointer are composited for readability.
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import (QColor, QDragEnterEvent, QDropEvent, QFont, QImage,
                          QMouseEvent, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QApplication, QToolTip
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import desktop
import archive_bridge

WIDTH, HEIGHT, FPS = 1280, 960, 20
ORIGIN = QPoint(100, 30)
BUILD = ROOT / 'build/showcase'
OUTPUT = ROOT / 'docs/demo'


def fixtures(folder):
    folder.mkdir(parents=True, exist_ok=True)
    import numpy as np
    rng = np.random.default_rng(5277)
    frames = []
    title_font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 90)
    small_font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 30)
    for index in range(6):
        yy, xx = np.mgrid[0:900, 0:1440]
        pixels = np.empty((900, 1440, 3), dtype=np.uint8)
        noise = rng.integers(0, 12, (900, 1440))
        pixels[:, :, 0] = 10 + noise
        pixels[:, :, 1] = 35 + xx // 25 + noise
        pixels[:, :, 2] = 72 + yy // 10 + noise
        image = Image.fromarray(pixels)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((100, 100, 1340, 800), radius=38, outline='#4bd4ff', width=3)
        draw.text((175, 225), 'K 文件处理台', font=title_font, fill='#e6faff')
        draw.text((183, 380), '离线处理  /  图片与图像  /  合成演示文件', font=small_font, fill='#85d7ff')
        draw.line((185, 490, 1250, 490), fill='#2c7ba8', width=2)
        for i in range(9):
            x = 200 + i * 115
            draw.rounded_rectangle((x, 600 - (i + index) % 5 * 28, x + 60, 700), radius=10, fill='#35bcf4')
        frames.append(image)
    image_path = folder / '蓝色科技演示.png'
    frames[0].save(image_path, save_all=True, append_images=frames[1:], duration=200, loop=0)
    records = [{'项目': '图片转换', '状态': '完成', '数量': 6},
               {'项目': '数据转换', '状态': '完成', '数量': 12}]
    data_path = folder / '演示项目清单.json'
    data_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), 'utf-8')
    note = folder / '演示说明.txt'
    note.write_text('K File Station synthetic demo. Public test password: password.\n', 'utf-8')
    engine = archive_bridge.initialize()[0].find_7zip()
    archive = folder / '合成加密演示.zip'
    result = subprocess.run([str(engine), 'a', '-tzip', '-mem=ZipCrypto', '-ppassword',
                             str(archive), str(note)], capture_output=True, creationflags=0x08000000)
    assert result.returncode == 0, result.stderr
    return image_path, data_path, archive, note


class Recorder:
    def __init__(self, app, station, target):
        self.app, self.station = app, station
        self.title = 'K 文件处理台'
        self.subtitle = '本地离线 · 悬浮挂件 · Windows 便携运行'
        self.pointer = QPointF(680, 530)
        self.file_name = None
        self.click_until = 0
        self.frames = 0
        self.markers = []
        self.next_frame = time.monotonic()
        self.process = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
            '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{WIDTH}x{HEIGHT}', '-r', str(FPS),
            '-i', '-', '-an', '-c:v', 'libx264', '-crf', '19', '-preset', 'fast', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', str(target)], stdin=subprocess.PIPE,
            stderr=(BUILD / 'encode.log').open('wb'), creationflags=0x08000000)

    def caption(self, title, subtitle):
        self.title, self.subtitle = title, subtitle
        self.markers.append({'frame': self.frames, 'seconds': round(self.frames / FPS, 2), 'title': title})
        print('Recording:', title, flush=True)

    def frame(self):
        while time.monotonic() < self.next_frame:
            self.app.processEvents()
            time.sleep(.002)
        self.app.processEvents()
        QToolTip.hideText()
        canvas = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB888)
        canvas.fill(Qt.GlobalColor.white)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Qt's own pixels, including all animations and progress readouts.
        for window in (self.station, self.station.archive_dialog):
            if window and window.isVisible() and not window.isMinimized():
                painter.drawPixmap(window.pos() - ORIGIN, window.grab())
        painter.setPen(QColor('#123958'))
        font = QFont('Microsoft YaHei UI', 23); font.setBold(True); painter.setFont(font)
        painter.drawText(QRectF(0, 12, WIDTH, 55), Qt.AlignmentFlag.AlignCenter, self.title)
        font.setPixelSize(17); font.setBold(False); painter.setFont(font)
        painter.setPen(QColor('#46667c'))
        painter.drawText(QRectF(30, 897, WIDTH - 60, 28), Qt.AlignmentFlag.AlignCenter, self.subtitle)
        font.setPixelSize(12); painter.setFont(font); painter.setPen(QColor('#6b8293'))
        painter.drawText(QRectF(0, 928, WIDTH, 20), Qt.AlignmentFlag.AlignCenter,
                         '真实界面与实际处理结果  ·  仅使用合成示例文件  ·  v1.0.0')
        if self.file_name:
            x, y = self.pointer.x() - 165, self.pointer.y() - 26
            painter.setBrush(QColor('#f1f9ff')); painter.setPen(QPen(QColor('#399acb'), 1.5))
            painter.drawRoundedRect(QRectF(x, y, 157, 51), 8, 8)
            font.setPixelSize(13); font.setBold(True); painter.setFont(font); painter.setPen(QColor('#16456a'))
            painter.drawText(QRectF(x + 8, y + 5, 141, 40), Qt.AlignmentFlag.AlignCenter, self.file_name)
        if time.monotonic() < self.click_until:
            painter.setBrush(QColor(75, 202, 255, 50)); painter.setPen(QPen(QColor('#32aee5'), 2))
            painter.drawEllipse(self.pointer, 19, 19)
        painter.save(); painter.translate(self.pointer)
        cursor = QPainterPath(); cursor.moveTo(0, 0); cursor.lineTo(0, 24); cursor.lineTo(6, 18)
        cursor.lineTo(12, 30); cursor.lineTo(17, 27); cursor.lineTo(11, 16); cursor.lineTo(21, 16); cursor.closeSubpath()
        painter.setPen(QPen(QColor('#123750'), 1.5)); painter.setBrush(QColor('white')); painter.drawPath(cursor)
        painter.restore(); painter.end()
        self.process.stdin.write(bytes(canvas.bits()))
        if self.frames % 20 == 0:  # Small contact sheet inputs, not a second full recording.
            canvas.scaled(640, 480).save(str(BUILD / f'frame-{self.frames:05d}.png'))
        self.frames += 1
        self.next_frame += 1 / FPS
        # Preserve real processing time if an unusually expensive frame runs late.
        if self.next_frame < time.monotonic() - .25: self.next_frame = time.monotonic()

    def hold(self, seconds):
        for _ in range(round(seconds * FPS)): self.frame()

    def wait(self, predicate, timeout=45):
        end = time.monotonic() + timeout
        while not predicate():
            self.frame()
            if time.monotonic() > end:
                raise AssertionError('Demo timed out: ' + self.station.status.text())
        self.frame()

    def move(self, canvas_point, seconds=.65, widget=None, local=None):
        start = QPointF(self.pointer); end = QPointF(canvas_point)
        for index in range(max(1, round(seconds * FPS))):
            f = (index + 1) / max(1, round(seconds * FPS)); f = f*f*(3-2*f)
            self.pointer = start + (end - start) * f
            if widget and local is not None and index == round(seconds * FPS) - 1:
                self.mouse(widget, QEvent.Type.MouseMove, local, Qt.MouseButton.NoButton)
            self.frame()

    def point(self, widget, local):
        return QPointF(widget.mapToGlobal(local) - ORIGIN)

    def mouse(self, widget, kind, local, buttons):
        event = QMouseEvent(kind, QPointF(local), QPointF(widget.mapToGlobal(local)),
                            Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, event)

    def click(self, widget, local, hold=.1):
        self.move(self.point(widget, local), widget=widget, local=local)
        self.click_until = time.monotonic() + .4
        self.mouse(widget, QEvent.Type.MouseButtonPress, local, Qt.MouseButton.LeftButton)
        self.hold(hold)
        self.mouse(widget, QEvent.Type.MouseButtonRelease, local, Qt.MouseButton.NoButton)
        self.frame()

    def drop(self, widget, path, local):
        self.move(QPointF(230, 480), .4)
        self.file_name = path.name
        self.hold(.6)
        mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path))])
        self.move(self.point(widget, local), 1.1)
        enter = QDragEnterEvent(local, Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, enter); assert enter.isAccepted()
        self.hold(.4)
        drop = QDropEvent(QPointF(local), Qt.DropAction.CopyAction, mime,
                          Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, drop); assert drop.isAccepted()
        self.file_name = None
        self.frame()

    def target(self, wheel, name):
        index = wheel.targets.index(name)
        point = wheel.from_scene(desktop.polar(259, -90 + (index + .5) * 360 / len(wheel.targets))).toPoint()
        assert wheel.hit(point) == ('target', index)
        self.click(wheel, point)

    def finish(self):
        self.process.stdin.close()
        assert self.process.wait(timeout=60) == 0


def main():
    BUILD.mkdir(parents=True, exist_ok=True); OUTPUT.mkdir(parents=True, exist_ok=True)
    fixture_dir = BUILD / ('fixtures-' + str(time.time_ns()))
    image, data, archive, note = fixtures(fixture_dir)
    session = BUILD / ('session-' + str(time.time_ns())); session.mkdir()
    desktop.DATA = session
    archive_bridge.DATA_ROOT = session / 'archive-engine'
    app = QApplication([]); app.setQuitOnLastWindowClosed(False)
    station = desktop.DesktopWidget(tray=False)
    station.orb_pos = ORIGIN + QPoint(592, 432); station.move(station.orb_pos)
    station.show(); app.processEvents()
    target = OUTPUT / 'k-file-station-demo.mp4'
    recorder = Recorder(app, station, target)
    evidence = []
    try:
        recorder.hold(1.7)
        recorder.caption('点按 Logo，展开圆形工作台', '鼠标经过板块时点亮并突出，移开后恢复')
        recorder.click(station, QPoint(48, 48))
        recorder.wait(lambda: not station.radial_opening)
        circle = station.radial_wheel
        for index in (1, 2, 3):
            p = circle.from_scene(desktop.polar(145, -90 + index*72)).toPoint()
            recorder.move(recorder.point(circle, p), .35, circle, p); recorder.hold(.35)
        QApplication.sendEvent(circle, QEvent(QEvent.Type.Leave))
        recorder.caption('拖入图片，自动识别并展开格式环', '合成动画 PNG → 无损 WebP；顶部和底部保留弧形提示')
        recorder.drop(circle, image, circle.rect().center())
        recorder.wait(lambda: not station.loading and bool(station.item))
        recorder.wait(lambda: circle.ring_progress > .99 and station.geometry_animation.state() == desktop.QPropertyAnimation.State.Stopped)
        recorder.hold(.8)
        recorder.caption('点击 WEBP，外围激光光圈显示转换进度', '转换在本机执行，结果自动保存在结果文件夹')
        recorder.target(circle, 'webp')
        recorder.move(QPointF(1010, 640), .35)
        recorder.wait(lambda: not station.converting)
        assert station.result, station.status.text()
        with Image.open(station.result['path']) as converted:
            assert converted.format == 'WEBP' and converted.n_frames == 6 and converted.size == (1440, 900)
        evidence.append({'case':'PNG → WEBP', 'passed':True, 'frames':6})
        recorder.wait(lambda: station.task_progress.state == 'done')
        recorder.caption('图片转换完成', '动画帧数、尺寸与生成文件均已核验')
        recorder.hold(1.8)
        recorder.click(circle, circle.rect().center()); station.remove_file(); recorder.hold(.5)
        recorder.caption('长按 Logo，打开矩形工作台', '矩形窗口支持缩放、全屏、批量文件及右侧转换选项')
        recorder.click(station, QPoint(48, 48), hold=.7)
        assert station.expanded
        recorder.hold(1.2)
        recorder.caption('拖入 JSON，自动切换到结构化数据', '选择 CSV，百分比显示读取和转换进度')
        recorder.drop(station.wheel, data, station.wheel.rect().center())
        recorder.wait(lambda: not station.loading and station.item['ext'] == 'json')
        recorder.wait(lambda: station.wheel.ring_progress > .99)
        recorder.hold(.8)
        recorder.target(station.wheel, 'csv')
        recorder.move(QPointF(1170, 820), .3)
        recorder.wait(lambda: not station.converting)
        assert station.result, station.status.text()
        with station.result['path'].open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        assert rows[0]['项目'] == '图片转换' and rows[1]['数量'] == '12'
        evidence.append({'case':'JSON → CSV','passed':True,'records':len(rows)})
        recorder.wait(lambda: station.task_progress.state == 'done')
        recorder.caption('数据转换完成，原文件保留', '生成的 CSV 已核对字段、中文内容与记录数量')
        recorder.hold(2)
        station.remove_file(); station.collapse(); recorder.hold(.4)
        recorder.click(station, QPoint(48, 48)); recorder.wait(lambda: not station.radial_opening)
        recorder.caption('拖入加密压缩包，打开「解压与破译」', '使用自行生成的弱密码测试包，密码为 password')
        recorder.drop(circle, archive, circle.rect().center())
        recorder.wait(lambda: bool(station.archive_dialog))
        dialog = station.archive_dialog
        dialog.move(ORIGIN + QPoint((WIDTH-dialog.width())//2, 100))
        dialog.output.setText('build/showcase/演示解压结果')
        # Use a real relative output directory, with no machine-specific path.
        dialog.output.setCursorPosition(len(dialog.output.text()))
        recorder.hold(.8)
        recorder.click(dialog.profile, dialog.profile.rect().center())
        # Select the actual quick-search entry with keyboard events.
        from PySide6.QtGui import QKeyEvent
        QApplication.sendEvent(dialog.profile, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))
        QApplication.sendEvent(dialog.profile, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
        assert dialog.profile.currentIndex() == 1
        recorder.hold(1)
        recorder.caption('快速搜索并自动解压', '这只是已知弱密码演示；复杂密码的耗时取决于范围和设备')
        recorder.click(dialog.start, dialog.start.rect().center())
        recorder.move(QPointF(1160, 820), .3)
        recorder.wait(lambda: dialog.task is None, timeout=90)
        assert dialog.password.text() == 'password' and station.result and station.result['path'].is_dir(), dialog.progress_label.text()
        extracted = station.result['path'] / note.name
        assert extracted.read_bytes() == note.read_bytes()
        evidence.append({'case':'ZIP quick password recovery + extraction','passed':True,
                         'synthetic_password':'password','content_sha256':hashlib.sha256(extracted.read_bytes()).hexdigest()})
        recorder.caption('密码恢复并解压完成', '密码默认显示；已核验解压内容与原始测试文件一致')
        recorder.hold(3)
        recorder.click(dialog.close_button, dialog.close_button.rect().center())
        station.remove_file(); station.collapse()
        recorder.caption('K 文件处理台', '五个板块 · 本地处理 · 便携运行')
        recorder.hold(1.6)
    finally:
        while station.loading or station.converting:
            app.processEvents(); time.sleep(.01)
        recorder.finish()
        station.quitting = True; station.close(); app.processEvents()
    manifest = {'status':'passed', 'recording':'real Qt application windows on white', 'fps':FPS,
                'frames':recorder.frames, 'duration_seconds':recorder.frames/FPS,
                'markers':recorder.markers, 'checks':evidence}
    (BUILD/'recording-validation.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
        '-i',str(target),'-filter_complex',
        '[0:v]fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle',
        '-loop','0',str(OUTPUT/'k-file-station-demo.gif')],check=True,creationflags=0x08000000)
    print('Recorded:',target.name,recorder.frames/FPS,'seconds',target.stat().st_size,'bytes',flush=True)


if __name__ == '__main__': main()
