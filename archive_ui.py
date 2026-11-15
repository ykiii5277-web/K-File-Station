"""Blue native interface for the imported archive engine."""
from pathlib import Path
import threading
from PySide6.QtCore import QThread,Signal,Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QWidget,QLabel,
    QPushButton,QComboBox,QSpinBox,QLineEdit,QPlainTextEdit,QCheckBox,QFileDialog,QTextBrowser,QProgressBar,QApplication,QScrollArea,QSizeGrip)
import archive_bridge
from search_help import search_description,SEARCH_COMMON


class ArchiveInspectTask(QThread):
    loaded=Signal(dict); failed=Signal(str); progress=Signal(int,str)
    def __init__(self,path):
        super().__init__(); self.paths=[Path(p) for p in path] if isinstance(path,(list,tuple)) else [Path(path)]; self.stop=threading.Event()
    def run(self):
        try:
            import file_policy
            file_policy.validate_selection(self.paths); items=[]
            for i,path in enumerate(self.paths):
                self.progress.emit(int(98*i/len(self.paths)),f'正在读取压缩包 {i+1}/{len(self.paths)} · {path.name}')
                items.append(archive_bridge.inspect_archive(path,self.stop))
            self.progress.emit(98,'压缩包识别完成，直接读取原包，无需复制')
            self.loaded.emit(items[0] if len(items)==1 else {'archive_items':items})
        except Exception as exc: self.failed.emit(str(exc))


class ArchiveTask(QThread):
    snapshot=Signal(object); backend=Signal(str); completed=Signal(dict); failed=Signal(str); stopped=Signal()
    def __init__(self,path,request,resume,auto_extract,output):
        super().__init__(); self.path=path; self.request=request; self.resume=resume
        self.auto_extract=auto_extract; self.output=output; self.stop=threading.Event()
    def run(self):
        try:
            result=archive_bridge.recover_archive(self.path,self.request,self.resume,self.auto_extract,self.output,self.stop,
                lambda *v:self.snapshot.emit(v[0] if len(v)==1 else v),lambda *v:self.backend.emit(' '.join(map(str,v))))
            self.completed.emit(result)
        except Exception as exc:
            recovery,_,_=archive_bridge.initialize()
            if isinstance(exc,recovery.Cancelled): self.stopped.emit()
            else: self.failed.emit(str(exc))


EXAMPLES='''<h2>已知长度</h2><p>1. 四位数字：?d?d?d?d<br>2. 四位小写：?l?l?l?l<br>
3. 固定前缀：abc?d?d?d?d<br>4. 首位大写：?u?l?l2024<br>5. 固定位置：?d?aX?a?d<br>6. 字面问号：abc??</p>
<h2>长度不确定</h2><p>勾选长度范围并选择补齐类型和定位方向。<br>
7. 第三位是a：?a?aa，从左起，3–6位<br>8. 第三位数字：?a?a?d，从左起，3–6位<br>
9. 第三位小写：?a?a?l，从左起，3–6位<br>10. 以abc开头：abc，从左起，3–6位<br>
11. 以xyz结尾：xyz，从右起，3–6位<br>12. 倒数第三位a：a?a?a，从右起，3–6位<br>
13. 末位数字：?d，从右起，1–6位</p><h2>符号说明</h2><p>?d 数字；?l 小写；?u 大写；?s 英文标点和空格；?a 全部可打印ASCII；?? 字面问号。普通文字原样匹配。</p>'''


class ArchiveCaption(QLabel):
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle():self.window().windowHandle().startSystemMove()
        else:super().mousePressEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.window().toggle_fullscreen()


class ArchiveDialog(QDialog):
    def __init__(self,station,item):
        super().__init__(station); self.station=station; self.item=item; self.task=None; self.close_pending=False; self.advancing=False; self.normal_geometry=None
        station.prepare_dialog(self); self.setWindowTitle('K文件处理台 · 解压与破译')
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint|(Qt.WindowType.WindowStaysOnTopHint if station.pinned else Qt.WindowType.Widget))
        self.setWindowModality(Qt.WindowModality.NonModal)
        available=station.screen().availableGeometry(); self.resize(min(730,available.width()-32),min(760,available.height()-70))
        self.setMinimumSize(min(620,available.width()-32),min(600,available.height()-70))
        layout=QVBoxLayout(self); header=QHBoxLayout(); title=ArchiveCaption('解压与破译  /  ARCHIVE RECOVERY'); title.setObjectName('section'); header.addWidget(title,1)
        self.minimize_button=QPushButton('−'); self.minimize_button.setToolTip('最小化'); self.minimize_button.clicked.connect(self.showMinimized)
        self.fullscreen_button=QPushButton('⛶'); self.fullscreen_button.setToolTip('全屏 / 恢复（F11）'); self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.close_button=QPushButton('×'); self.close_button.setToolTip('关闭；运行时先停止并保存进度'); self.close_button.clicked.connect(self.close)
        for button in (self.minimize_button,self.fullscreen_button,self.close_button):
            button.setObjectName('control'); button.setFixedSize(32,30); button.setAutoDefault(False); header.addWidget(button)
        layout.addLayout(header)
        info=QLabel(item['name']+'\n检测到密码保护，请选择搜索方式。'); info.setWordWrap(True); layout.addWidget(info)
        self.tabs=QTabWidget(); layout.addWidget(self.tabs,1)
        auto=QWidget(); form=QFormLayout(auto); self.profile=QComboBox(); self.profile.addItems(['深度搜索','快速搜索']); form.addRow('自动搜索',self.profile)
        note=QLabel('复用原项目的字典、日期、文件名、中文与拼音、变体及完整搜索阶段。支持时自动使用GPU，否则显示CPU回退原因。'); note.setWordWrap(True); form.addRow(note)
        self.profile_help=QTextBrowser(); self.profile_help.setMinimumHeight(270); self.profile_help.setOpenExternalLinks(False)
        self.profile.currentIndexChanged.connect(self.update_profile_help); form.addRow(self.profile_help); self.update_profile_help()
        self.tabs.addTab(auto,'自动搜索')
        combo=QWidget(); form=QFormLayout(combo); self.types={}
        for key,text in [('digits','阿拉伯数字'),('lowercase','英文小写'),('uppercase','英文大写'),('symbols','特殊符号'),('space','空格')]:
            box=QCheckBox(text); box.setChecked(key=='digits'); self.types[key]=box; form.addRow(box)
        self.combo_max=QSpinBox(); self.combo_max.setRange(1,6); self.combo_max.setValue(4); form.addRow('最大位数（从1位开始）',self.combo_max); self.tabs.addTab(combo,'字符组合')
        custom=QWidget(); form=QFormLayout(custom); self.alphabet=QComboBox()
        recovery,_,_=archive_bridge.initialize()
        for text,value in recovery.AUTO_ALPHABETS.items():
            if value:self.alphabet.addItem(text,value)
        self.custom_max=QSpinBox(); self.custom_max.setRange(1,16); self.custom_max.setValue(4)
        form.addRow('自定义字符集',self.alphabet); form.addRow('最大位数',self.custom_max); self.tabs.addTab(custom,'自定义字符集')
        manual=QWidget(); form=QFormLayout(manual); self.lines=QPlainTextEdit(); self.lines.setPlaceholderText('每行一个候选密码；保留两端空格'); self.lines.setMaximumHeight(110); form.addRow('手动候选',self.lines)
        row=QHBoxLayout(); self.dictionary=QLineEdit(); row.addWidget(self.dictionary); pick=QPushButton('选择TXT'); pick.clicked.connect(self.pick_dictionary); row.addWidget(pick); form.addRow('TXT 字典',row)
        row=QHBoxLayout(); self.mask=QLineEdit(); self.mask.setPlaceholderText('如 abc?d?d?d?d'); row.addWidget(self.mask); examples=QPushButton('查看示例'); examples.clicked.connect(self.show_examples); row.addWidget(examples); form.addRow('密码规律',row)
        self.uncertain=QCheckBox('密码长度不确定'); form.addRow(self.uncertain)
        row=QHBoxLayout(); self.minimum=QSpinBox(); self.maximum=QSpinBox()
        for spin in (self.minimum,self.maximum): spin.setRange(1,16)
        self.minimum.setValue(3); self.maximum.setValue(6); row.addWidget(self.minimum); row.addWidget(QLabel('至')); row.addWidget(self.maximum); form.addRow('长度范围',row)
        self.padding=QComboBox()
        for text,key in [('任意ASCII','?a'),('数字','?d'),('小写','?l'),('大写','?u'),('符号','?s')]: self.padding.addItem(text,key)
        self.anchor=QComboBox(); self.anchor.addItem('从左起','start'); self.anchor.addItem('从右起','end'); form.addRow('补齐类型',self.padding); form.addRow('规律定位',self.anchor); self.tabs.addTab(manual,'手动候选')
        pages=[(self.tabs.widget(i),self.tabs.tabText(i)) for i in range(self.tabs.count())]
        while self.tabs.count():self.tabs.removeTab(0)
        for page,text in pages:
            scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); self.tabs.addTab(scroll,text)
        self.scope=QLabel(); self.scope.setWordWrap(True); layout.addWidget(self.scope)
        self.resume=QCheckBox('续接未完成搜索'); self.resume.setChecked(True); layout.addWidget(self.resume)
        self.auto_extract=QCheckBox('找到密码后自动解压'); self.auto_extract.setChecked(True); layout.addWidget(self.auto_extract)
        row=QHBoxLayout(); self.output=QLineEdit(str(station.archive_output)); row.addWidget(self.output); choose=QPushButton('输出目录'); choose.clicked.connect(self.pick_output); row.addWidget(choose); layout.addLayout(row)
        self.backend_label=QLabel('GPU / CPU：等待开始'); self.backend_label.setWordWrap(True); layout.addWidget(self.backend_label)
        self.progress_label=QLabel('请选择范围后开始。'); self.progress_label.setWordWrap(True); layout.addWidget(self.progress_label)
        self.eta=QLabel('预计最长剩余用时：等待测速'); self.eta.setWordWrap(True); layout.addWidget(self.eta)
        self.progress=QProgressBar(); self.progress.setRange(0,100); layout.addWidget(self.progress)
        row=QHBoxLayout(); self.password=QLineEdit(); self.password.setReadOnly(True); self.password.setPlaceholderText('恢复结果仅在本窗口显示'); row.addWidget(self.password)
        self.show_password=QCheckBox('显示'); self.show_password.toggled.connect(lambda v:self.password.setEchoMode(QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password)); self.show_password.setChecked(True); row.addWidget(self.show_password)
        copy=QPushButton('复制'); copy.clicked.connect(lambda:QApplication.clipboard().setText(self.password.text())); row.addWidget(copy); layout.addLayout(row)
        row=QHBoxLayout(); self.start=QPushButton('开始破译'); self.start.setObjectName('primary'); self.start.clicked.connect(self.begin); row.addWidget(self.start)
        self.stop=QPushButton('停止并保存进度'); self.stop.setEnabled(False); self.stop.clicked.connect(self.cancel); row.addWidget(self.stop)
        self.next_button=QPushButton(f'下一个（{len(station.archive_queue)}）'); self.next_button.setEnabled(False); self.next_button.setVisible(bool(station.archive_queue)); self.next_button.clicked.connect(station.advance_archive_queue); row.addWidget(self.next_button)
        close=QPushButton('关闭'); close.clicked.connect(self.close); row.addWidget(close); row.addWidget(QSizeGrip(self)); layout.addLayout(row)
        for combo in (self.profile,self.tabs,self.alphabet,self.padding,self.anchor):
            (combo.currentChanged if isinstance(combo,QTabWidget) else combo.currentIndexChanged).connect(self.update_scope)
        for spin in (self.combo_max,self.custom_max,self.minimum,self.maximum):spin.valueChanged.connect(self.update_scope)
        for box in (*self.types.values(),self.uncertain):box.toggled.connect(self.update_scope)
        self.lines.textChanged.connect(self.update_scope); self.mask.textChanged.connect(self.update_scope); self.dictionary.textChanged.connect(self.update_scope)
        self.update_scope()

    def pick_dictionary(self):
        path,_=QFileDialog.getOpenFileName(self,'选择 TXT 字典','','TXT (*.txt)')
        if path:self.dictionary.setText(path)
    def update_profile_help(self,*unused):
        self.profile_help.setHtml(search_description('deep' if self.profile.currentIndex()==0 else 'quick')+SEARCH_COMMON)
    def pick_output(self):
        path=QFileDialog.getExistingDirectory(self,'解压输出目录',self.output.text())
        if path:self.output.setText(path)
    def show_examples(self):
        dialog=self.station.prepare_dialog(QDialog(self)); dialog.setWindowTitle('密码规律示例'); dialog.resize(660,600)
        layout=QVBoxLayout(dialog); browser=QTextBrowser(); browser.setHtml(EXAMPLES); layout.addWidget(browser); dialog.exec(); dialog.deleteLater()
    def request(self):
        recovery,_,masks=archive_bridge.initialize(); index=self.tabs.currentIndex()
        if index==0:return {'kind':'deep' if self.profile.currentIndex()==0 else 'quick'}
        if index==1:
            types=[key for key,box in self.types.items() if box.isChecked()]; recovery.combination_alphabet(types,self.combo_max.value())
            return {'kind':'combination','types':types,'max_length':self.combo_max.value()}
        if index==2:
            return {'kind':'charset','alphabet':self.alphabet.currentData(),'max_length':self.custom_max.value()}
        lines=tuple(self.lines.toPlainText().splitlines()); dictionary=self.dictionary.text().strip(); mask=self.mask.text()
        if not any(lines) and not dictionary and not mask: raise ValueError('请填写候选密码、字典或密码规律。')
        if dictionary and not Path(dictionary).is_file():raise ValueError('TXT 字典不存在。')
        recovery.parse_mask(mask)
        request={'kind':'manual','lines':lines,'dictionary':dictionary or None,'mask':mask}
        if self.uncertain.isChecked():
            request['mask_length_range']={'minimum':self.minimum.value(),'maximum':self.maximum.value(),'padding':self.padding.currentData(),'anchor':self.anchor.currentData()}; masks.options(request)
        return request
    def update_scope(self,*unused):
        try:
            recovery,_,masks=archive_bridge.initialize(); request=self.request(); kind=request['kind']
            if kind in ('deep','quick'):self.scope.setText('搜索范围：沿用原项目的'+('深度' if kind=='deep' else '快速')+'阶段；运行后显示速度和估时。'); return
            if kind=='combination':
                alphabet,length=recovery.combination_alphabet(request['types'],request['max_length']); total=recovery.brute_force_count(alphabet,length)
            elif kind=='charset':total=recovery.brute_force_count(request['alphabet'],request['max_length'])
            else:
                total=sum(bool(line) for line in request['lines'])
                if request['mask']:
                    config=request.get('mask_length_range')
                    total+=masks.count(masks.masks(request['mask'],config['minimum'],config['maximum'],config['padding'],config['anchor'])) if config else recovery.candidate_count((),recovery.parse_mask(request['mask']))
            self.scope.setText(f'所选范围：{total:,} 个候选'+('，另含TXT字典（开始时计数）' if request.get('dictionary') else ''))
        except Exception as exc:self.scope.setText(str(exc))
    def begin(self):
        if self.task:return
        self.close_pending=False
        try: request=self.request()
        except Exception as exc:self.progress_label.setText(str(exc)); return
        self.password.clear(); self.next_button.setEnabled(False); self.start.setEnabled(False); self.tabs.setEnabled(False); self.stop.setEnabled(True); self.resume.setEnabled(False); self.auto_extract.setEnabled(False)
        self.station.archive_search_started(); self.progress_label.setText('正在准备搜索…')
        self.station.archive_output=Path(self.output.text())
        task=ArchiveTask(self.item['path'],request,self.resume.isChecked(),self.auto_extract.isChecked(),self.output.text()); task.setParent(self); self.task=task
        task.snapshot.connect(self.update_snapshot); task.backend.connect(self.backend_label.setText); task.completed.connect(self.done_result)
        task.failed.connect(self.error_result); task.stopped.connect(lambda:self.error_result('已停止，进度已保存。')); task.finished.connect(self.finished_task); task.start()
    def update_snapshot(self,snapshot):
        label='正在搜索'
        if isinstance(snapshot,(tuple,list)) and len(snapshot)==2:
            label,snapshot=snapshot
            if snapshot is None:self.progress_label.setText(str(label)); return
        if not isinstance(snapshot,dict):return
        tested=snapshot.get('tested',0); total=snapshot.get('total'); label=snapshot.get('label',label)
        if isinstance(snapshot.get('progress'),(tuple,list)):
            tested,total=snapshot['progress'][:2]
        self.progress_label.setText(f'{label}\n已尝试 {tested:,}'+(f' / {total:,}' if total else ''))
        if isinstance(snapshot.get('speed'),(int,float)):self.progress_label.setText(self.progress_label.text()+f' · {snapshot["speed"]:,.0f} 个/秒')
        if total:self.progress.setRange(0,100); self.progress.setValue(min(99,int(100*tested/max(1,total))))
        else:self.progress.setRange(0,0)
        estimate=snapshot.get('time_estimate',{}); seconds=estimate.get('remaining_seconds')
        if seconds is not None:
            recovery,_,_=archive_bridge.initialize(); self.eta.setText('预计最长剩余用时：'+recovery.format_search_duration(seconds)+('（粗估）' if estimate.get('approximate') else ''))
    def cancel(self):
        if self.task:self.task.stop.set(); self.progress_label.setText('正在停止并保存进度…')
    def done_result(self,result):
        self.progress.setRange(0,100); self.progress.setValue(100 if result.get('found') else 0)
        self.progress_label.setText(result['message']); self.password.setText(result.get('password') or '')
        self.station.archive_completed(result)
    def error_result(self,message):
        self.progress.setRange(0,100); self.progress.setValue(0); self.progress_label.setText(message); self.station.archive_failed(message)
    def finished_task(self):
        task=self.task; task.wait(); self.task=None; task.deleteLater()
        self.start.setEnabled(True); self.tabs.setEnabled(True); self.stop.setEnabled(False); self.resume.setEnabled(True); self.auto_extract.setEnabled(True); self.station.archive_search_finished()
        self.next_button.setEnabled(bool(self.station.archive_queue))
        if self.close_pending:self.close()
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            if self.normal_geometry:self.setGeometry(self.normal_geometry)
        else:self.normal_geometry=self.geometry(); self.showFullScreen()
        self.fullscreen_button.setText('❐' if self.isFullScreen() else '⛶')
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_F11:self.toggle_fullscreen(); event.accept()
        elif event.key()==Qt.Key.Key_Escape:
            if self.isFullScreen():self.toggle_fullscreen()
            else:self.close()
            event.accept()
        else:super().keyPressEvent(event)
    def closeEvent(self,event):
        if self.task:
            self.close_pending=True; self.cancel(); event.ignore()
        else:
            if not self.advancing:self.station.archive_queue=[]
            event.accept()
