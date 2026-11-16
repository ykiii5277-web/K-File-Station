# K文件处理台 1.0.0 轻量版

Windows 10 / 11 x64 · 本地离线 · 解压即用

轻量版省去内置 LibreOffice 与 Pandoc，保留原版程序、图片引擎、音视频引擎、PDF/OCR、结构化数据、解压与密码恢复引擎，以及完整搜索字典。界面、上传限制和便携使用方式与完整版一致。

## 启动

将整个压缩包解压到可写目录，再双击 `K文件处理台.exe`。无需另装 Python。移动到其他电脑时复制整个文件夹；`data` 保存设置、输入副本、处理结果与搜索进度。

## 无需额外引擎即可使用

- 图片与图像：完整版中的全部图片转换方向，包括 RAW、HEIC、AVIF、SVG、动画、ICO 与图片转 PDF。
- 结构化数据：全部转换方向，包括 JSON、YAML、XML、CSV、TSV、JSONL 与 JSON/XLSX 互转。
- 音视频：全部转换方向，包括视频转码、音频提取、MP4 截取 GIF。
- PDF：转 DOCX、TXT、XLSX、PNG，保留扫描页中英文 OCR。
- 其他办公方向：DOCX → TXT；XLS → CSV；XLSX → CSV / JSON；TXT → DOCX；EPUB → HTML。
- 解压与破译：ZIP、RAR、7z、TAR、TAR.GZ、TAR.XZ 解压；ZIP / RAR / 7z 密码恢复。快速/深度搜索、GPU 后端与原有字典均保留。

以上共 **69 条直接转换方向**，另有 6 类压缩格式解压。格式别名与文件内容限制与完整版一致。

## 需要完整版的办公方向

未安装额外引擎时，下列 23 条方向不能在轻量版直接执行：

| 输入 | 需额外办公引擎的输出 |
| --- | --- |
| DOC | DOCX、MD、PDF、TXT |
| DOCX | DOC、MD、PDF |
| MD | DOCX、HTML、PDF |
| HTML | MD、EPUB、PDF |
| XLS | XLSX、PDF |
| XLSX | XLS、PDF |
| PPT | PPTX、PDF |
| PPTX | PPT、PDF |
| TXT | PDF |
| EPUB | DOCX |

程序沿用完整版界面，目标格式环仍会列出完整转换关系；执行依赖缺失引擎的方向时，会提示缺少 LibreOffice 或 Pandoc。需要这些方向时，推荐下载完整版。也可将同版本完整版中的 `engines/libreoffice` 与 `engines/pandoc` 文件夹复制到轻量版同名位置；程序也会尝试识别系统安装的 LibreOffice 和 PATH 中的 Pandoc。

不要混用不同版本的 `_internal`、EXE 或恢复组件；补齐上述两项引擎即可恢复全部 92 条转换方向。

## 校验与许可

下载页的 `SHA256-Lite.txt` 对应轻量版；`SHA256.txt` 对应完整版。两种便携包独立解压使用。

轻量版复用已验证的 v1.0.0 EXE 与保留组件，未修改程序逻辑。原版源码和完整使用说明在 `source` 中，`lite-manifest.json` 记录精简范围与基包校验值。应用许可为 AGPL-3.0-or-later，第三方组件许可见 `licenses` 与 `THIRD_PARTY_NOTICES.md`。

项目与完整版下载：https://github.com/ykiii5277-web/K-File-Station/releases/tag/v1.0.0
