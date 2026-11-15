"""Native widget acceptance runner; also used against the frozen release EXE."""
from pathlib import Path
import json
import time


def run_checks(folder):
    from PySide6.QtCore import QMimeData, QPoint, QPointF, QEvent, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeyEvent, QMouseEvent
    from PySide6.QtWidgets import QApplication
    import desktop
    import archive_bridge
    from docx import Document
    from openpyxl import load_workbook
    import pymupdf

    folder=Path(folder).resolve(); folder.mkdir(parents=True,exist_ok=True)
    desktop.DATA=folder/'working'; desktop.DATA.mkdir(exist_ok=True)
    archive_bridge.DATA_ROOT=desktop.DATA/'archive-engine'
    app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    checks=[]
    w=desktop.DesktopWidget(tray=False)

    def wait(predicate, timeout=30):
        deadline=time.monotonic()+timeout
        while not predicate():
            app.processEvents()
            if time.monotonic()>deadline: raise AssertionError('Native widget operation timed out: '+w.status.text())
            time.sleep(.01)
        app.processEvents()

    def mouse(widget,event_type,local,global_point,buttons):
        event=QMouseEvent(event_type,QPointF(local),QPointF(global_point),Qt.MouseButton.LeftButton,buttons,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget,event)

    def click(widget,point):
        global_point=widget.mapToGlobal(point)
        mouse(widget,QEvent.Type.MouseButtonPress,point,global_point,Qt.MouseButton.LeftButton)
        mouse(widget,QEvent.Type.MouseButtonRelease,point,global_point,Qt.MouseButton.NoButton)
        app.processEvents()

    def snapshot(name):
        app.processEvents(); assert w.grab().save(str(folder/name))

    def pump(milliseconds):
        end=time.monotonic()+milliseconds/1000
        while time.monotonic()<end:
            app.processEvents(); time.sleep(.008)

    def wheel_point(wheel,radius,degrees):
        return wheel.from_scene(desktop.polar(radius,degrees)).toPoint()

    def drop_file(widget,path,point):
        mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path))])
        enter=QDragEnterEvent(point,Qt.DropAction.CopyAction,mime,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget,enter); assert enter.isAccepted()
        drop=QDropEvent(QPointF(point),Qt.DropAction.CopyAction,mime,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget,drop); assert drop.isAccepted()

    def circle_drag(delta):
        circle=w.radial_wheel; start=w.pos(); local=wheel_point(circle,0,0); origin=circle.mapToGlobal(local)
        mouse(circle,QEvent.Type.MouseButtonPress,local,origin,Qt.MouseButton.LeftButton)
        pump(120); assert not circle.radial_dragging
        wait(lambda:circle.radial_dragging)
        mouse(circle,QEvent.Type.MouseMove,local+delta,origin+delta,Qt.MouseButton.LeftButton)
        mouse(circle,QEvent.Type.MouseButtonRelease,local,origin+delta,Qt.MouseButton.NoButton)
        assert w.radial and w.pos()==start+delta and not circle.radial_dragging

    try:
        for damaged in ([],{'x':None},{'x':'invalid'},{'x':2**100}):
            w.settings_file.write_text(json.dumps(damaged),'utf-8')
            probe=desktop.DesktopWidget(tray=False)
            assert probe.width()==96 and probe.pos().x()>=0
            probe.quitting=True;probe.close();probe.deleteLater()
        w.save_position()
        checks.append('异常位置配置的数组、空值、非数字和超大坐标均恢复默认位置并可启动')
        w.show(); w.move(160,140); app.processEvents()
        assert not w.expanded and w.size().width()==96
        assert w.mask().contains(QPoint(48,48)) and not w.mask().contains(QPoint(0,0))
        assert w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        snapshot('K挂件-圆形Logo.png')
        start=w.pos(); local=QPoint(48,48); origin=w.mapToGlobal(local); delta=QPoint(85,42)
        mouse(w,QEvent.Type.MouseButtonPress,local,origin,Qt.MouseButton.LeftButton)
        mouse(w,QEvent.Type.MouseMove,local+delta,origin+delta,Qt.MouseButton.LeftButton)
        mouse(w,QEvent.Type.MouseButtonRelease,local,origin+delta,Qt.MouseButton.NoButton)
        assert not w.expanded and w.pos()==start+delta
        assert json.loads(w.settings_file.read_text('utf-8'))['x']==w.pos().x()
        checks.append('圆形透明边界、初始收起、置顶、拖动不误展开、位置保存')
        click(w,QPoint(48,48)); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        assert w.radial and not w.expanded and not w.panel.isVisible() and w.width()<450
        w.expand(); assert w.expanded and w.panel.isVisible()
        assert w.width()>600
        snapshot('K挂件-工作台.png')
        title=w.findChild(desktop.QLabel,'dragtitle'); start=w.pos(); local=QPoint(8,10); origin=title.mapToGlobal(local); delta=QPoint(22,18)
        mouse(title,QEvent.Type.MouseButtonPress,local,origin,Qt.MouseButton.LeftButton)
        mouse(title,QEvent.Type.MouseMove,local+delta,origin+delta,Qt.MouseButton.LeftButton)
        mouse(title,QEvent.Type.MouseButtonRelease,local,origin+delta,Qt.MouseButton.NoButton)
        assert w.pos()!=start, 'Titlebar must drag through child labels'
        w.close(); assert w.isVisible() and not w.expanded
        w.expand(); assert w.expanded
        w.toggle_pin(); assert not w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        w.toggle_pin(); assert w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        checks.append('点按圆盘、矩形标题栏拖动、关闭收起、可切换置顶')
        csv=folder/'挂件体验表格.csv'; csv.write_text('项目,数量\n苹果,12\n=1+1,34\n','utf-8-sig')
        w.load_file(csv); wait(lambda:not w.loading)
        wait(lambda:w.wheel.ring_progress>.99)
        assert w.item['ext']=='csv' and w.wheel.targets==['xlsx','json','tsv']
        point=desktop.polar(259,0); side=min(w.wheel.width(),w.wheel.height())
        loc=QPoint(round((w.wheel.width()-side)/2+point.x()*side/700),round((w.wheel.height()-side)/2+point.y()*side/700))
        click(w.wheel,loc); wait(lambda:not w.converting)
        assert w.result and w.result['path'].is_file(),w.status.text()
        book=load_workbook(w.result['path']); assert book.active['B2'].value=='12'
        assert book.active['A3'].data_type=='s'; book.close()
        checks.append('CSV双目标外环真实点击、CSV→XLSX、公式文本安全、结果自动保存')
        md=folder/'K工作台体验.md'; md.write_text('# K文件处理台\n\n这是一个本地悬浮文件处理工具。Hello 12345','utf-8')
        w.load_file(md); wait(lambda:not w.loading); assert len(w.wheel.targets)==3
        wait(lambda:w.wheel.ring_progress>.99)
        w.wheel.setFocus(); app.processEvents()
        QApplication.sendEvent(w.wheel,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Right,Qt.KeyboardModifier.NoModifier))
        QApplication.sendEvent(w.wheel,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Return,Qt.KeyboardModifier.NoModifier))
        wait(lambda:not w.converting)
        assert w.result and w.result['path'].suffix=='.html'
        assert '12345' in w.result['path'].read_text('utf-8')
        snapshot('K挂件-转换完成.png')
        checks.append('两段外环、键盘选择、Markdown→HTML、中文内容完整')
        pdf_path=folder/'PDF体验文件.pdf'; pdf=pymupdf.open(); pdf.new_page().insert_text((60,60),'Native Widget Test 12345'); pdf.save(pdf_path); pdf.close()
        w.load_file(pdf_path); wait(lambda:not w.loading); assert len(w.wheel.targets)==4
        wait(lambda:w.wheel.ring_progress>.99)
        assert w.ocr_check.isVisible() and w.dpi_row.isVisible()
        snapshot('K挂件-PDF外环.png')
        w.begin_conversion('png'); wait(lambda:not w.converting)
        assert w.result and w.result['path'].read_bytes().startswith(b'\x89PNG')
        doc_path=folder/'Word体验文件.docx'; doc=Document(); doc.add_paragraph('Three target formats 123'); doc.save(doc_path)
        w.load_file(doc_path); wait(lambda:not w.loading); assert len(w.wheel.targets)==4
        bad=folder/'损坏文件.docx'; bad.write_bytes(b'broken')
        previous=w.item; w.load_file(bad); wait(lambda:not w.loading)
        assert w.item==previous and '损坏' in w.status.text()
        checks.append('四段与三段外环、PDF→PNG、OCR选项、损坏文件保留已选文档')
        assert desktop.MODULES[4][0]=='解压与破译'
        w.collapse(); assert not w.expanded and w.width()==96
        remembered=w.pos(); second=desktop.DesktopWidget(tray=False)
        assert second.pos()==remembered; second.quitting=True; second.close(); second.deleteLater()
        checks.append('待开发板块提示、收起恢复Logo、重新创建时位置恢复')

        # Logo gestures are swapped: short click -> compact circle; hold -> rectangle.
        w.remove_file(); w.move(180,170); app.processEvents()
        local=QPoint(48,48); origin=w.mapToGlobal(local); delta=QPoint(35,20)
        mouse(w,QEvent.Type.MouseButtonPress,local,origin,Qt.MouseButton.LeftButton)
        mouse(w,QEvent.Type.MouseMove,local+delta,origin+delta,Qt.MouseButton.LeftButton)
        pump(620)
        assert not w.radial and not w.expanded
        mouse(w,QEvent.Type.MouseButtonRelease,local,origin+delta,Qt.MouseButton.NoButton)
        origin=w.mapToGlobal(local)
        mouse(w,QEvent.Type.MouseButtonPress,local,origin,Qt.MouseButton.LeftButton)
        pump(250); assert not w.radial and not w.expanded
        wait(lambda:w.expanded)
        assert not w.radial and w.panel.isVisible() and w.width()>w.height()
        mouse(w,QEvent.Type.MouseButtonRelease,local,origin,Qt.MouseButton.NoButton)
        snapshot('K挂件-长按矩形窗口.png')
        w.collapse(); click(w,QPoint(48,48))
        wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        assert w.radial and not w.expanded and w.width()==w.height() and 425<w.width()<500
        compact_size=w.width()
        assert not w.mask().contains(QPoint(0,0))
        snapshot('K挂件-紧凑圆盘弧形提示.png')
        checks.append('手势交换、点按紧凑圆盘、长按矩形窗口、拖动取消Logo长按、背景匹配五板块范围')

        circle_drag(QPoint(32,22))

        circle=w.radial_wheel; loc=wheel_point(circle,140,-90)
        mouse(circle,QEvent.Type.MouseMove,loc,circle.mapToGlobal(loc),Qt.MouseButton.NoButton)
        pump(70); assert .05<circle.hover_amounts[0]<1
        wait(lambda:circle.hover_amounts[0]>.99)
        protruding=wheel_point(circle,208,-90)
        assert circle.hit(protruding)==('module',0)
        snapshot('K挂件-悬停突出.png')
        original_picker=desktop.QFileDialog.getOpenFileNames
        try:
            desktop.QFileDialog.getOpenFileNames=lambda *args,**kwargs:([str(csv)],'')
            click(circle,protruding)
        finally:
            desktop.QFileDialog.getOpenFileNames=original_picker
        wait(lambda:not w.loading)
        assert w.radial and not w.panel.isVisible() and circle.targets==['xlsx','json','tsv']
        assert circle.ring_progress<1
        snapshot('K挂件-外环展开中.png')
        wait(lambda:circle.ring_progress>.99 and circle.hover_amounts[0]<.01 and w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        assert w.width()>compact_size*1.35 and abs(circle.view_radius-desktop.FULL_RADIUS)<1
        snapshot('K挂件-上传后板块复原.png')
        click(circle,wheel_point(circle,259,0)); wait(lambda:not w.converting)
        assert w.result and w.result['path'].suffix=='.xlsx' and w.radial
        menu=w.make_menu(); labels=[action.text() for action in menu.actions()]
        assert '另存转换结果' in labels and '打开本次结果文件夹' in labels and '展开工作台' in labels
        menu.deleteLater()
        checks.append('悬停插值动画、突出区域可点击、板块触发文件选择、选中文件后缩回、外环渐显、纯圆盘内真实转换与结果菜单')

        previous=w.item
        circle_drag(QPoint(25,18)); assert w.item is previous and w.result
        snapshot('K挂件-拖动后保持圆盘.png')
        checks.append('紧凑与全展开圆盘均可长按拖动、拖动不误触中心或板块、位置保存')

        w.remove_file(); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        assert w.width()==compact_size
        scale_before=circle.from_scene(desktop.polar(193,-90)).y()-circle.height()/2
        drop_file(circle,pdf_path,wheel_point(circle,0,0)); wait(lambda:not w.loading)
        wait(lambda:circle.ring_progress>.99 and w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        assert w.radial and not w.expanded and w.item['ext']=='pdf' and circle.selected and len(circle.targets)==4
        assert '已选择文档与办公' in w.status.text()
        scale_after=circle.from_scene(desktop.polar(193,-90)).y()-circle.height()/2
        assert abs(scale_before-scale_after)<1, 'Inner wheel must keep its size when the background expands'
        snapshot('K挂件-中心拖入自动识别PDF.png')
        checks.append('真实Qt文件拖放、中心识别PDF并自动选择办公板块、背景与格式环动态全展开、五板块物理大小不变')

        previous=w.item
        for filename in ('无后续方向.ico','不支持的格式.bin'):
            invalid=folder/filename; invalid.write_text('This file has no available conversion route.','utf-8')
            drop_file(circle,invalid,wheel_point(circle,0,0)); wait(lambda:not w.loading)
            assert '文件不符合转化格式要求' in w.status.text()
            assert w.item is previous and len(circle.targets)==4
        snapshot('K挂件-无可转换格式提示.png')
        checks.append('无后续转换方向与不支持格式均给出指定提示、拒绝后保留当前有效文件')

        w.remove_file(); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        w.collapse(); drop_file(w,csv,QPoint(48,48)); wait(lambda:not w.loading)
        wait(lambda:circle.ring_progress>.99 and w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        assert w.radial and not w.expanded and w.item['ext']=='csv' and circle.targets==['xlsx','json','tsv']
        checks.append('直接拖入收起Logo中心也能识别格式、选择板块并打开格式圆环')

        item=w.item; w.expand()
        assert w.expanded and not w.radial and w.item is item and w.wheel.targets==circle.targets
        snapshot('K挂件-提亮矩形工作台.png')
        w.collapse(); click(w,QPoint(48,48)); assert w.radial and not w.expanded
        w.collapse(); w.show_radial(); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        click(circle,wheel_point(circle,0,0)); assert not w.radial and w.width()==96
        checks.append('圆盘与矩形共享文件状态、点按仍按新手势打开圆盘、中心点击收起')

        # UI cleanup, wording and readable guidance.
        assert w.pin_button.toolTip()=='窗口置顶'
        menu=w.make_menu(); labels=[action.text() for action in menu.actions()]
        assert labels[0]=='移除当前文件' and '窗口置顶' in labels and '保持最前' not in labels
        menu.deleteLater()
        texts=[label.text() for label in w.findChildren(desktop.QLabel)]
        assert not any(text in texts for text in ['●  本机离线处理','原文件保留 · 转换结果另存','K  /  LOCAL WORKSPACE','拖动顶部移动  ·  Esc 收起  ·  右键更多'])
        assert w.note.font().bold() and w.note.font().pixelSize()>=14
        assert w.status.font().bold() and w.status.font().pixelSize()>=14
        checks.append('窗口置顶更名、移除文件置于首项、删除四处冗余文字、关键说明加粗增大')

        mode=(w.expanded,w.radial,w.status.text(),w.geometry())
        w.show_help(); pump(100)
        assert w.help_window.isWindow() and w.help_window.isVisible()
        assert [w.help_window.tabs.tabText(i) for i in range(2)]==['简略说明','详细说明']
        assert (w.expanded,w.radial,w.status.text(),w.geometry())==mode
        w.help_window.grab().save(str(folder/'使用说明-简略.png'))
        w.help_window.tabs.setCurrentIndex(1); pump(80)
        from help_dialog import detailed
        from PySide6.QtCore import QUrl
        guide=w.help_window.guide
        text=guide.toPlainText()
        assert str(sum(map(len,desktop.converter.GRAPH.values()))) in text
        assert len(guide.sections)==6 and not guide.expanded_sections and not guide.expanded_topics
        assert all(title in text for title,_ in guide.sections) and '1.1 三种界面' not in text
        w.help_window.grab().save(str(folder/'使用说明-详细.png'))
        def click_heading(label):
            cursor=guide.document().find(label); assert not cursor.isNull(),label
            guide.setTextCursor(cursor); guide.ensureCursorVisible(); pump(35)
            cursor.setPosition(cursor.selectionStart()+2)
            point=guide.cursorRect(cursor).center()
            assert guide.anchorAt(point).startswith('guide:'),label
            click(guide.viewport(),point); pump(35)
        click_heading(guide.sections[0][0])
        assert guide.expanded_sections=={0} and not guide.expanded_topics
        assert '1.1 三种界面' in guide.toPlainText() and '启动后显示圆形 K 图标' not in guide.toPlainText()
        click_heading(guide.sections[0][1][0][0])
        assert '启动后显示圆形 K 图标' in guide.toPlainText()
        w.help_window.grab().save(str(folder/'使用说明-二级展开.png'))
        click_heading(guide.sections[0][1][0][0])
        assert '启动后显示圆形 K 图标' not in guide.toPlainText()
        click_heading(guide.sections[0][0]); assert not guide.expanded_sections
        # Every topic must be reachable and fold independently, including long tables.
        for index,(_,topics) in enumerate(guide.sections):
            guide.toggle(QUrl(f'guide:{index}'))
            assert all(topic in guide.toPlainText() for topic,_ in topics)
            for subindex,(topic,_) in enumerate(topics):
                click_heading(topic)
                assert (index,subindex) in guide.expanded_topics
                assert guide.horizontalScrollBar().maximum()==0,topic
                click_heading(topic)
                assert (index,subindex) not in guide.expanded_topics
            click_heading(guide.sections[index][0])
        assert not guide.expanded_sections and not guide.expanded_topics
        text=detailed()
        assert 'DOC / XLS / PPT' in text and 'F11' in text and '1,828,598' in text
        assert '新增格式' not in text and '原项目' not in text
        w.toggle_pin(); pump(30)
        assert not w.pinned and not w.help_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint and w.help_window.isVisible()
        w.toggle_pin(); pump(30)
        assert w.help_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        w.help_window.close()
        checks.append('独立说明窗口、简略与详细双页、包含全部转换关系、不改变工作台状态')
        checks.append('六个一级目录和24个二级目录默认折叠、真实点击逐一展开收起、长表格无横向溢出')

        w.expand(); app.processEvents(); before=w.size()
        handle=next(h for h in w.resize_handles if h.edges==desktop.Qt.Edge.RightEdge|desktop.Qt.Edge.BottomEdge)
        local=QPoint(7,7); origin=handle.mapToGlobal(local); delta=QPoint(70,30)
        mouse(handle,QEvent.Type.MouseButtonPress,local,origin,Qt.MouseButton.LeftButton)
        mouse(handle,QEvent.Type.MouseMove,local+delta,origin+delta,Qt.MouseButton.LeftButton)
        mouse(handle,QEvent.Type.MouseButtonRelease,local,origin+delta,Qt.MouseButton.NoButton)
        assert w.width()==before.width()+70 and w.height()==before.height()+30
        assert w.panel.width()==w.width()-10
        snapshot('矩形工作台-自由调整大小.png')
        normal=w.geometry(); w.toggle_fullscreen(); pump(100)
        assert w.isFullScreen() and not w.size_grip.isVisible()
        snapshot('矩形工作台-全屏.png')
        QApplication.sendEvent(w,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Escape,Qt.KeyboardModifier.NoModifier)); pump(100)
        assert not w.isFullScreen() and w.geometry()==normal and w.expanded
        w.collapse(); assert w.width()==96
        checks.append('鼠标拖动边角调整窗口、布局同步变化、全屏切换、Esc恢复原窗口尺寸')

        fixture=Path(__file__).resolve().parent/'tests/fixtures/legacy'
        if not fixture.is_dir(): fixture=desktop.converter.HOME/'source/tests/fixtures/legacy'
        w.load_file(fixture/'sample.xls'); wait(lambda:not w.loading)
        assert w.item['ext']=='xls' and w.sheets.count()==2 and w.radial_wheel.targets==['xlsx','pdf','csv']
        w.sheets.setCurrentIndex(1); w.begin_conversion('csv'); wait(lambda:not w.converting)
        assert w.result and '选中此表,34' in w.result['path'].read_text('utf-8-sig')
        for ext in ('doc','ppt'):
            w.load_file(fixture/('sample.'+ext)); wait(lambda:not w.loading)
            assert w.item['ext']==ext and w.radial_wheel.targets==desktop.converter.GRAPH[ext]
        wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        snapshot('旧版PPT-可转换格式.png')
        checks.append('真实DOC/XLS/PPT输入识别、XLS工作表选择、原生旧版Excel转CSV')

        # Use a real animated PNG encoder job so screenshots show actual progress.
        from PIL import Image
        import numpy as np
        from progress_visual import TaskProgress,draw_halo
        from PySide6.QtGui import QImage,QPainter
        rng=np.random.default_rng(20261114)
        frames=[Image.fromarray(rng.integers(0,256,(800,1200,3),dtype=np.uint8)) for _ in range(5)]
        animated=folder/'动画体验.png'
        frames[0].save(animated,save_all=True,append_images=frames[1:],duration=[100,200,300,200,100],loop=2)
        w.expand(); pump(60)
        assert w.minimize_button.x()<w.fullscreen_button.x()
        w.load_file(animated); wait(lambda:not w.loading)
        assert w.active_module==1 and w.wheel.active_module==1 and w.module_title.text()=='图片与图像'
        assert w.item['targets']==['jpg','tiff','webp','ico','pdf','avif']
        w.begin_conversion('webp')
        wait(lambda:w.task_progress.value>10)
        assert w.wheel.progress_visible and w.wheel.conversion_progress<100
        snapshot('矩形工作台-科技百分比.png')
        w.show_radial(); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        assert circle.halo_opacity>0
        snapshot('圆形工作台-转换光圈.png')
        wait(lambda:not w.converting,60)
        assert w.result and w.result['path'].suffix=='.webp'
        wait(lambda:w.task_progress.state=='done')
        assert w.task_progress.value==100 and circle.halo_opacity==0
        snapshot('圆形工作台-光圈完成消失.png')
        checks.append('全屏与收起按钮交换位置、真实图片转换科技百分比、圆形工作台共享进度并完成后光圈消失')

        tracker=TaskProgress(); tracker.start(); tracker.report(70); pump(100); before=tracker.value
        assert 0<before<100
        tracker.report(10); pump(100); assert tracker.value>=before
        assert tracker.value<100
        tracker.complete(); wait(lambda:tracker.state=='done')
        assert tracker.value==100 and tracker.opacity==0
        tracker.start(); tracker.report(80); pump(50); tracker.reset()
        assert tracker.value==0 and tracker.opacity==0 and not tracker.visible
        pixels=QImage(700,700,QImage.Format.Format_RGBA8888); pixels.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pixels); draw_halo(painter,300,25,1); painter.end()
        assert pixels.pixelColor(350,50).alpha()>0 and pixels.pixelColor(650,350).alpha()>0
        assert pixels.pixelColor(350,650).alpha()==0 and pixels.pixelColor(50,350).alpha()==0
        checks.append('进度单调不倒退、成功前不报100%、失败清除光圈、顶部起点顺时针准确覆盖四分之一圆')

        first=folder/'第一张.png'; second=folder/'第二张.png'
        Image.new('RGB',(160,100),'red').save(first)
        Image.new('RGBA',(160,100),(20,120,240,0)).save(second)
        w.handle_dropped_paths([str(first),str(second)]); wait(lambda:not w.loading)
        assert w.item['count']==2 and 'pdf' in w.item['targets'] and w.active_module==1
        w.begin_conversion('pdf'); wait(lambda:not w.converting)
        assert w.result
        with pymupdf.open(w.result['path']) as pdf:
            assert len(pdf)==2 and pdf[0].get_pixmap().pixel(10,10)[0]>240
            assert pdf[1].get_pixmap().pixel(10,10)==(255,255,255)
        wait(lambda:w.task_progress.state=='done')
        snapshot('图片与图像-多图合并PDF.png')
        previous=w.item; w.handle_dropped_paths([str(first),str(fixture/'sample.doc')]); wait(lambda:not w.loading)
        assert w.item is previous and '同一格式' in w.status.text()
        checks.append('同格式PNG多文件真实拖入、自动选择图片板块、按添加顺序合并PDF、拒绝混入文档且保留原文件')

        # Reading uses byte counts and shares the conversion display in both views.
        import threading
        released=threading.Event(); original_validate=desktop.converter.validate
        def paused_validate(path,ext):
            released.wait(10)
            return original_validate(path,ext)
        desktop.converter.validate=paused_validate
        try:
            w.expand(); w.load_file(second); wait(lambda:w.loading and w.task_progress.value>30)
            assert w.wheel.progress_visible and w.wheel.conversion_progress<100
            snapshot('矩形工作台-读取百分比.png')
            w.show_radial(); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
            assert circle.halo_opacity>0 and w.loading
            snapshot('圆形工作台-读取光圈.png')
        finally:
            released.set(); wait(lambda:not w.loading); desktop.converter.validate=original_validate
        wait(lambda:w.task_progress.state=='done'); assert w.task_progress.value==100
        checks.append('读取过程共享科技百分比与激光光圈、实际复制和内容识别阶段、成功后100%并淡出')

        second_csv=folder/'批量第二个.csv'; second_csv.write_text('编号,值\n001,12\n','utf-8-sig')
        w.load_file([csv,second_csv]); wait(lambda:not w.loading)
        assert w.item['count']==2 and w.active_module==2 and w.item['targets']==['xlsx','json','tsv']
        w.begin_conversion('json'); wait(lambda:not w.converting)
        import zipfile
        with zipfile.ZipFile(w.result['path']) as bundle:
            assert len(bundle.namelist())==2
            assert json.loads(bundle.read('002_批量第二个.json'))[0]['编号']=='001'
        mixed=folder/'不同格式.jpg'; Image.new('RGB',(20,20)).save(mixed)
        previous=w.item; w.load_file([first,mixed]); assert w.item is previous and '同一格式' in w.status.text()
        checks.append('办公同格式多选保留全部共同目标、真实批量CSV转JSON及ZIP、拒绝混合图片格式且保留上次输入')

        image_fixtures=fixture.parent/'images'
        svg=folder/'矢量体验.svg'; svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"><rect x="10" y="10" width="80" height="60" fill="#00bfff"/></svg>','utf-8')
        gif=folder/'动画体验.gif'
        Image.new('RGB',(95,63),'red').save(gif,save_all=True,append_images=[Image.new('RGB',(95,63),'blue')],duration=[200,300],loop=0)
        for path,target in [(image_fixtures/'sample.heic','jpg'),(image_fixtures/'sample.dng','tiff'),(svg,'png'),(gif,'mp4')]:
            w.load_file(path); wait(lambda:not w.loading)
            assert w.active_module==1 and circle.active_module==1
            w.begin_conversion(target); wait(lambda:not w.converting,60)
            assert w.result and w.result['path'].suffix=='.'+target
            wait(lambda:w.task_progress.state=='done')
        snapshot('图片与图像-GIF转MP4完成.png')
        checks.append('HEIC解码、DNG/RAW显影为16位TIFF、SVG栅格化、GIF转MP4均通过真实原生任务执行')

        original_picker=desktop.QFileDialog.getOpenFileNames
        desktop.QFileDialog.getOpenFileNames=lambda *a,**k:([str(second)],'')
        try: w.select_module(1); wait(lambda:not w.loading)
        finally: desktop.QFileDialog.getOpenFileNames=original_picker
        assert w.item['ext']=='png' and circle.active_module==1 and circle.suppressed_module==1
        assert 'RAW' in w.format_list.text()
        invalid=folder/'损坏图片.png'; invalid.write_text('not an image','utf-8'); previous=w.item
        drop_file(circle,invalid,wheel_point(circle,0,0)); wait(lambda:not w.loading)
        assert w.item is previous and w.active_module==1
        w.expand(); pump(60); snapshot('图片与图像-矩形工作台.png')
        checks.append('图片板块点击上传、选中图片板块缩回、五种PNG目标格式、损坏图片拒绝且保留已选有效文件')

        w.remove_file(); w.show_radial(); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped)
        # Pixel colors must follow the mouse, independently of the selected module.
        def sector_color(index):
            point=wheel_point(circle,160,-90+index*72+25)
            return circle.grab().toImage().pixelColor(point).lightness()
        baseline=sector_color(3); office_before=sector_color(0)
        point=wheel_point(circle,140,126)
        mouse(circle,QEvent.Type.MouseMove,point,circle.mapToGlobal(point),Qt.MouseButton.NoButton); pump(230)
        assert circle.hover==('module',3) and sector_color(3)>baseline+10
        snapshot('圆盘-音视频悬停点亮.png')
        point=wheel_point(circle,0,0); mouse(circle,QEvent.Type.MouseMove,point,circle.mapToGlobal(point),Qt.MouseButton.NoButton); pump(230)
        assert abs(sector_color(3)-baseline)<5
        assert abs(sector_color(0)-office_before)<5
        # The thick laser band and the outermost hint glyphs have a radial gap.
        assert desktop.FULL_RADIUS-10-12 > desktop.FULL_RADIUS-34+8
        checks.append('悬停即时点亮音视频、移开熄灭、选择板块不造成常亮、加粗激光与弧形文字径向留白')

        data_path=folder/'结构体验.json'; data_path.write_text('{"data":{"items":[{"编号":"001","数量":12},{"编号":"002","数量":34}]}}','utf-8')
        drop_file(circle,data_path,wheel_point(circle,0,0)); wait(lambda:not w.loading)
        assert w.active_module==2 and circle.targets==['yaml','xml','csv','xlsx','jsonl']
        w.records_path.setText('data.items'); w.begin_conversion('csv'); wait(lambda:not w.converting)
        assert w.result and '001,12' in w.result['path'].read_text('utf-8-sig')
        w.expand(); pump(60); snapshot('结构化数据-记录路径与CSV结果.png')
        yaml_path=folder/'结构体验.yaml'; yaml_path.write_text('编号: "001"\n数量: 12\n有效: true','utf-8')
        w.load_file(yaml_path); wait(lambda:not w.loading); assert w.wheel.targets==['json']
        w.begin_conversion('json'); wait(lambda:not w.converting)
        assert json.loads(w.result['path'].read_text('utf-8'))['有效'] is True
        checks.append('JSON自动选择结构化板块、记录路径导出CSV保持前导零、YAML单目标环与布尔数字类型保持')

        import subprocess
        from media_converter import binary
        video=folder/'音视频体验.mp4'
        p=subprocess.run([binary(),'-v','error','-y','-f','lavfi','-i','testsrc2=size=160x120:rate=10','-f','lavfi','-i','sine=frequency=440','-t','1','-c:v','libx264','-c:a','aac',str(video)],capture_output=True,creationflags=0x08000000)
        assert p.returncode==0,p.stderr
        w.load_file(video); wait(lambda:not w.loading); assert w.active_module==3 and len(circle.targets)==8
        w.clip_start.setValue(.1); w.clip_duration.setValue(.5); w.gif_width.setValue(160); w.gif_fps.setValue(10)
        w.begin_conversion('gif'); wait(lambda:not w.converting)
        assert w.result
        with Image.open(w.result['path']) as image: assert image.n_frames>=3 and image.width==160
        w.expand(); pump(60); snapshot('音视频-GIF截取设置与结果.png')
        w.begin_conversion('mp3'); wait(lambda:not w.converting); assert w.result and w.result['path'].suffix=='.mp3'
        silent=folder/'无音轨.mp4'
        p=subprocess.run([binary(),'-v','error','-y','-i',str(video),'-an','-c:v','copy',str(silent)],capture_output=True,creationflags=0x08000000)
        assert p.returncode==0
        w.load_file(silent); wait(lambda:not w.loading); assert 'mp3' not in circle.targets and 'gif' in circle.targets
        checks.append('音视频识别、GIF起始时长帧率宽度生效、原生音轨提取、无音轨自动隐藏音频目标')

        # Focus alone must not highlight target zero; keyboard navigation is explicit.
        w.show_radial(); wait(lambda:w.geometry_animation.state()==desktop.QPropertyAnimation.State.Stopped and circle.ring_progress>.99)
        wait(lambda:w.task_progress.state in ('idle','done'))
        QApplication.sendEvent(circle,QEvent(QEvent.Type.Leave)); circle.setFocus(); pump(80)
        assert not circle.keyboard_navigation and circle.hover is None
        neutral=circle.grab().toImage()
        QApplication.sendEvent(circle,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Right,Qt.KeyboardModifier.NoModifier)); pump(80)
        assert circle.keyboard_navigation and circle.grab().toImage()!=neutral
        point=wheel_point(circle,0,0); mouse(circle,QEvent.Type.MouseMove,point,circle.mapToGlobal(point),Qt.MouseButton.NoButton); pump(80)
        assert not circle.keyboard_navigation and circle.grab().toImage()==neutral
        snapshot('圆盘-上传后格式环无自动点亮.png')
        checks.append('文件上传与自动聚焦不点亮首项、真实方向键仍可选择、鼠标移动退出键盘选择状态')

        import ctypes
        from ctypes import wintypes
        modal_seen=[]
        def check_modal():
            dialog=QApplication.activeModalWidget(); assert dialog and dialog.parentWidget() is w
            assert dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
            user32=ctypes.windll.user32
            user32.WindowFromPoint.argtypes=[wintypes.POINT]; user32.WindowFromPoint.restype=wintypes.HWND
            user32.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]; user32.GetAncestor.restype=wintypes.HWND
            center=dialog.mapToGlobal(dialog.rect().center())
            front=user32.WindowFromPoint(wintypes.POINT(center.x(),center.y()))
            assert user32.GetAncestor(front,2)==int(dialog.winId()),'Modal options must be above the pinned station'
            for spin in dialog.findChildren(desktop.QDoubleSpinBox):spin.setValue(.3)
            for spin in dialog.findChildren(desktop.QSpinBox):spin.setValue(120 if spin.maximum()>100 else 15)
            dialog.grab().save(str(folder/'GIF选项-置顶可见.png')); modal_seen.append(True); dialog.accept()
        desktop.QTimer.singleShot(150,check_modal); w.edit_gif_options()
        assert modal_seen and w.gif_width.value()==120 and w.gif_fps.value()==15
        old_root=w.xml_root.text()
        def cancel_modal():
            dialog=QApplication.activeModalWidget(); dialog.findChildren(desktop.QLineEdit)[0].setText('cancelled'); dialog.reject()
        desktop.QTimer.singleShot(100,cancel_modal); w.edit_data_options(); assert w.xml_root.text()==old_root
        checks.append('真实Windows窗口层级验证GIF选项位于置顶工作台上方、整组保存、取消数据选项不改原值')

        import zipfile
        fixture_dir=folder/'archive-fixtures'; fixture_dir.mkdir(exist_ok=True)
        plain=fixture_dir/'无密码.zip'
        with zipfile.ZipFile(plain,'w') as zipped:zipped.writestr('known.txt','known synthetic data')
        original=plain.read_bytes(); sibling=fixture_dir/'keep.txt'; sibling.write_text('keep','utf-8')
        drop_file(circle,plain,wheel_point(circle,0,0))
        wait(lambda:not w.loading and not w.converting and w.result and w.result['path'].is_dir(),60)
        assert w.active_module==4 and w.archive_dialog is None and (w.result['path']/'known.txt').read_text()=='known synthetic data'
        snapshot('解压与破译-无密码自动解压.png')
        w.remove_file(); assert plain.read_bytes()==original and sibling.is_file()
        checks.append('压缩包中心拖入自动选择第五板块、无密码直接解压、移除输入不删除原压缩包或同目录文件')

        recovery,_,_=archive_bridge.initialize(); known=fixture_dir/'known.txt'; known.write_text('only synthetic data','utf-8')
        locked=fixture_dir/'加密.zip'
        result=subprocess.run([str(recovery.find_7zip()),'a','-tzip','-mem=AES256','-pKWidget123!',str(locked),str(known)],capture_output=True,creationflags=0x08000000)
        assert result.returncode==0
        drop_file(circle,locked,wheel_point(circle,0,0)); wait(lambda:not w.loading and w.archive_dialog and w.archive_dialog.isVisible())
        dialog=w.archive_dialog; assert dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        dialog.profile.setCurrentIndex(1); pump(60)
        assert '1,828,598' in dialog.profile_help.toPlainText() and '固定四阶段' in dialog.profile_help.toPlainText()
        dialog.grab().save(str(folder/'解压与破译-快速搜索范围.png'))
        dialog.profile.setCurrentIndex(0); pump(60)
        assert '1–12位' in dialog.profile_help.toPlainText() and '预计较短' in dialog.profile_help.toPlainText()
        dialog.grab().save(str(folder/'解压与破译-深度搜索范围.png'))
        checks.append('快速深度简介随选择即时切换、显示固定顺序与动态调度区别、完整字符范围和CPU回退说明')
        assert dialog.show_password.isChecked() and dialog.password.echoMode()==desktop.QLineEdit.EchoMode.Normal
        assert dialog.minimize_button.x()<dialog.fullscreen_button.x()<dialog.close_button.x()
        normal=dialog.geometry(); dialog.fullscreen_button.click(); pump(100); assert dialog.isFullScreen()
        dialog.grab().save(str(folder/'解压与破译-全屏.png'))
        QApplication.sendEvent(dialog,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Escape,Qt.KeyboardModifier.NoModifier)); pump(100)
        assert not dialog.isFullScreen() and dialog.geometry()==normal
        dialog.minimize_button.click(); pump(100); assert dialog.isMinimized()
        w.toggle_pin(); pump(30)
        assert dialog.isMinimized() and not dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        w.toggle_pin(); pump(30)
        assert dialog.isMinimized() and dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        w.start_archive(); pump(100); assert not dialog.isMinimized() and dialog.isVisible()
        checks.append('破译窗口按钮顺序、最小化后恢复、全屏与Esc恢复尺寸、密码默认勾选显示')
        checks.append('窗口置顶同步已打开说明和密码窗口、切换时保留可见性及最小化状态')
        dialog.tabs.setCurrentIndex(3); dialog.lines.setPlainText('wrong\nKWidget123!'); dialog.resume.setChecked(False)
        dialog.update_snapshot(('合成进度',{'tested':5,'total':10,'time_estimate':{'remaining_seconds':100}})); assert dialog.progress.value()==50
        dialog.grab().save(str(folder/'解压与破译-科技风破译窗口.png'))
        dialog.begin(); wait(lambda:dialog.task is None and not w.converting,120)
        assert dialog.password.text()=='KWidget123!' and w.result and w.result['path'].is_dir()
        assert (w.result['path']/'known.txt').read_text('utf-8')=='only synthetic data'
        from types import SimpleNamespace
        import threading
        simulated_stop=threading.Event(); dialog.task=SimpleNamespace(stop=simulated_stop)
        QApplication.sendEvent(dialog,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Escape,Qt.KeyboardModifier.NoModifier))
        assert simulated_stop.is_set() and dialog.isVisible() and dialog.close_pending
        dialog.task=None; dialog.close_pending=False; dialog.close(); w.remove_file(); assert locked.is_file()
        checks.append('加密压缩包自动弹出置顶科技窗口、手动候选调用原GPU/CPU引擎、恢复密码并解压、原包保留')
        third=fixture_dir/'第三个.zip'
        with zipfile.ZipFile(third,'w') as bundle:bundle.writestr('third.txt','third synthetic data')
        count=len(w.history); w.load_file([plain,locked,third])
        wait(lambda:not w.loading and len(w.history)==count+1 and w.archive_dialog and w.archive_dialog.isVisible(),60)
        dialog=w.archive_dialog; assert len(w.archive_queue)==1
        dialog.tabs.setCurrentIndex(3); dialog.lines.setPlainText('KWidget123!'); dialog.resume.setChecked(False); dialog.begin()
        wait(lambda:dialog.task is None and len(w.history)==count+2,120)
        assert dialog.next_button.isEnabled() and dialog.password.text()=='KWidget123!' and len(w.archive_queue)==1
        dialog.next_button.click()
        wait(lambda:not w.converting and len(w.history)==count+3,60)
        assert not w.archive_queue and w.archive_dialog is None and (w.result['path']/'third.txt').is_file()
        assert plain.read_bytes()==original and locked.is_file() and third.is_file()
        checks.append('批量压缩包原地读取、无密码自动解压、加密包暂停显示结果、下一个继续队列、原包完整保留')
        text_path=desktop.DATA/'新增纯文本.txt'; text_path.write_text('中文 123\n普通文字','utf-8')
        w.load_file(text_path); wait(lambda:not w.loading); assert w.active_module==0 and circle.targets==['docx','pdf']
        w.begin_conversion('docx'); wait(lambda:not w.converting)
        assert '123' in '\n'.join(p.text for p in Document(w.result['path']).paragraphs)
        avif_path,_=desktop.converter.convert(first,'avif',desktop.DATA/'avif-fixture',{},lambda *v:None)
        w.load_file(avif_path); wait(lambda:not w.loading); assert w.active_module==1 and circle.targets==['jpg','png']
        w.begin_conversion('png'); wait(lambda:not w.converting); assert w.result['path'].suffix=='.png'
        snapshot('新增格式-TXT与AVIF自动识别.png')
        checks.append('TXT输入选择办公板块并转DOCX、AVIF输入选择图片板块并转PNG、目标环反映新增方向')
        w.load_file(data_path); wait(lambda:not w.loading); w.records_path.setText('data.items')
        w.begin_conversion('xlsx'); wait(lambda:not w.converting); xlsx_result=w.result['path']
        book=load_workbook(xlsx_result); assert book.active['A2'].value=='001' and book.active['B2'].value==12;book.close()
        w.load_file(xlsx_result); wait(lambda:not w.loading); assert 'json' in circle.targets and w.sheets.currentData()=='数据'
        w.begin_conversion('json');wait(lambda:not w.converting)
        assert json.loads(w.result['path'].read_text('utf-8'))[0]['编号']=='001'
        snapshot('新增格式-JSON与Excel互转.png')
        checks.append('JSON记录路径转Excel保留前导零与数字类型、Excel工作表选择与JSON目标、真实来回转换')
        import tarfile,io
        tar_path=fixture_dir/'界面合成.tar.gz'
        with tarfile.open(tar_path,'w:gz') as archive:
            entry=tarfile.TarInfo('nested/check.txt'); entry.size=5;archive.addfile(entry,io.BytesIO(b'hello'))
        drop_file(circle,tar_path,wheel_point(circle,0,0))
        wait(lambda:not w.loading and not w.converting and w.result and w.result['path'].is_dir())
        assert w.active_module==4 and w.item['ext']=='tar.gz' and (w.result['path']/'nested/check.txt').read_bytes()==b'hello'
        snapshot('新增格式-TAR-GZ直接解压.png')
        checks.append('TAR.GZ中心拖入自动分到解压板块、直接得到最终文件、原包保留')
        w.collapse()
        (folder/'native-widget-check.json').write_text(json.dumps({'status':'passed','checks':checks},ensure_ascii=False,indent=2),'utf-8')
        print('Native widget checks passed: '+str(len(checks))+' acceptance groups',flush=True)
        return checks
    finally:
        wait(lambda:not w.loading and not w.converting,60)
        w.quitting=True; w.close(); w.deleteLater()
        QApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__=='__main__':
    import sys
    run_checks(Path(sys.argv[1]) if len(sys.argv)>1 else Path('docs/native-check'))
