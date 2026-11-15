"""Independent, tabbed user guide generated from the current conversion graph."""
import html
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTabWidget, QTextBrowser, QVBoxLayout
import converter
from user_guide import manual_sections, conversion_table


SHORT='''<h1>从一个文件开始</h1>
<ol><li><b>点按 K Logo</b> 打开圆形工作台，<b>长按约半秒</b>打开矩形窗口。</li>
<li>将文件拖入中心，或点击办公、图片、数据、音视频板块选择文件；多张 JPG / PNG 可合并 PDF。</li>
<li>点击外环的目标格式，开始转换。结果会自动保存。</li>
<li>通过右键菜单另存结果、打开结果文件夹，或移除当前文件。</li></ol>
<p><b>解压与破译：</b>点击第五板块或拖入 ZIP / RAR / 7z / TAR / TAR.GZ / TAR.XZ / 第一分卷。无密码直接解压；有密码弹出搜索窗口，自行选择搜索方式后开始。停止或关闭搜索窗口会保存未完成进度。</p>
<h2>移动与收起</h2><p>Logo 按下后直接拖动；圆盘按住约三分之一秒后拖动；矩形窗口拖动顶部移动。点按圆盘中心、按 Esc 或点击「− / ×」可收回 Logo。</p>
<h2>窗口操作</h2><p>「窗口置顶」让窗口显示在其他普通窗口之上。矩形窗口可拖动边缘或右下角调整大小；点击「⛶」或按 F11 切换全屏，Esc 先退出全屏。</p>
<p><b>彻底退出：</b>右键菜单选择「退出工具」。「×」仅收起挂件。</p>
<p>矩形圆盘右下角以科技数字显示百分比；圆形工作台的边缘光圈从顶部顺时针推进，成功完成一圈后淡出。完整格式关系见「详细说明」。</p>'''


STYLE = '<style>body{font-family:Microsoft YaHei UI;font-size:15px;color:#e3f2ff}h1{font-size:24px;color:#9de6ff}h2{font-size:19px;color:#9de6ff}h3{font-size:17px;color:#9de6ff}p,li{margin-bottom:12px}td,th{border-bottom:1px solid #38698b}th{background:#1b4f74}a{color:#a4e9ff;text-decoration:none}b{color:#eefaff}</style>'


def detailed():
    """Full printable guide; the interactive view uses the same content."""
    return '<h1>K文件处理台 · 详细说明</h1>'+''.join(
        '<h2>'+html.escape(title)+'</h2>'+''.join('<h3>'+html.escape(topic)+'</h3>'+body for topic,body in topics)
        for title,topics in manual_sections()
    )


class DetailedGuide(QTextBrowser):
    """Two levels of folding, with native rich-text links and keyboard navigation."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.sections=manual_sections()
        self.expanded_sections=set()
        self.expanded_topics=set()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setAccessibleName('详细说明，两级折叠目录')
        self.anchorClicked.connect(self.toggle)
        self.render()

    def toggle(self,url):
        if url.scheme()!='guide': return
        try: indices=tuple(int(value) for value in url.path().split('/'))
        except ValueError: return
        if len(indices) not in (1,2) or not 0<=indices[0]<len(self.sections): return
        if len(indices)==2 and not 0<=indices[1]<len(self.sections[indices[0]][1]): return
        state,key=(self.expanded_sections,indices[0]) if len(indices)==1 else (self.expanded_topics,indices)
        if key in state: state.remove(key)
        else: state.add(key)
        title,topics=self.sections[indices[0]]
        heading=title if len(indices)==1 else topics[indices[1]][0]
        cursor=self.document().find(heading)
        old_y=self.cursorRect(cursor).top() if not cursor.isNull() else 0
        self.render()
        self.scrollToAnchor('topic-'+'-'.join(map(str,indices)))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value()-max(0,old_y))

    def render(self):
        count=sum(map(len,converter.GRAPH.values()))
        blocks=['<h1>K文件处理台 · 详细说明</h1>',
                f'<p>本地运行的便携式文件处理工具，包含五个板块，提供 {count} 条直接转换方向及压缩包解压与密码恢复。</p>',
                '<p>点击标题或三角展开；一级与二级目录可分别收起。</p>']
        for index,(title,topics) in enumerate(self.sections):
            opened=index in self.expanded_sections
            blocks.append(self.row((index,),title,opened))
            if opened:
                for subindex,(topic,body) in enumerate(topics):
                    subopened=(index,subindex) in self.expanded_topics
                    blocks.append(self.row((index,subindex),topic,subopened))
                    if subopened: blocks.append(body)
        self.setHtml(STYLE+''.join(blocks))

    @staticmethod
    def row(indices,title,opened):
        path='/'.join(map(str,indices)); anchor='topic-'+'-'.join(map(str,indices))
        size,background=('18','#1c5377') if len(indices)==1 else ('16','#143e5e')
        arrow='▼' if opened else '▶'
        return (f'<p><a name="{anchor}"></a></p><table width="100%" cellspacing="0" cellpadding="12">'
                f'<tr><td bgcolor="{background}"><a href="guide:{path}" style="font-size:{size}px">'
                f'<b>{arrow}　{html.escape(title)}</b></a></td></tr></table>')



class HelpDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent,Qt.WindowType.Window)
        self.setWindowTitle('K文件处理台 · 使用说明')
        self.resize(850,700); self.setMinimumSize(620,450)
        self.setStyleSheet('QDialog{background:#123553;color:#e4f2ff;} QTabWidget::pane{border:1px solid #3b7196;} QTabBar::tab{background:#174267;color:#badbf5;padding:12px 24px;font-weight:600;} QTabBar::tab:selected{background:#267cb1;color:white;} QTextBrowser{background:#0e2944;color:#dcefff;border:0;padding:18px;} QPushButton{background:#19567f;color:white;padding:9px 24px;border:1px solid #468ab6;border-radius:5px;}')
        layout=QVBoxLayout(self)
        self.tabs=QTabWidget(); layout.addWidget(self.tabs,1)
        brief=QTextBrowser(); brief.setOpenExternalLinks(False); brief.setHtml(STYLE+SHORT)
        self.tabs.addTab(brief,'简略说明')
        self.guide=DetailedGuide(); self.tabs.addTab(self.guide,'详细说明')
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('关闭')
        buttons.rejected.connect(self.close); layout.addWidget(buttons)
