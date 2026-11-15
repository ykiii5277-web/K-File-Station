# Third-party components

This application bundles open-source conversion engines. Their original license files are retained in the engines and licenses directories. This file is an index, not a replacement for the original terms.

The archive recovery component was supplied by the user as a compiled application. Its existing recovery modules are retained as compiled Python 3.13 components, with an adapter and a new Qt interface. The original 7-Zip, Hashcat, John metadata extractors, wordlists and notices are retained under engines/archive/. No personal archives, search data or recovered passwords from that project are included in the distribution. Bytecode provenance is recorded in engines/archive/provenance.json.

- Pandoc 3.14 — GPL-2.0-or-later. Source: https://github.com/jgm/pandoc/tree/3.14
- LibreOffice 26.2.7 — MPL-2.0 / LGPL-3.0-or-later and included third-party licenses. Source: https://download.documentfoundation.org/libreoffice/src/26.2.7/
- PyMuPDF 1.26.7 / MuPDF — AGPL-3.0. Source: https://github.com/pymupdf/PyMuPDF/tree/1.26.7 and https://mupdf.com/releases/
- pdf2docx — MIT. Source: https://github.com/ArtifexSoftware/pdf2docx
- RapidOCR — Apache-2.0. Source: https://github.com/RapidAI/RapidOCR
- ONNX Runtime — MIT. Source: https://github.com/microsoft/onnxruntime
- olefile — BSD-2-Clause. Source: https://github.com/decalage2/olefile
- xlrd — BSD-3-Clause. Source: https://github.com/python-excel/xlrd
- PyYAML 6.0.3 — MIT. Source: https://github.com/yaml/pyyaml
- pillow-heif 1.8.1 — BSD-3-Clause, including libheif and its separately licensed codecs. Source: https://github.com/bigcat88/pillow_heif
- rawpy 0.28.0 — MIT; LibRaw is LGPL-2.1 / CDDL-1.0. Source: https://github.com/letmaik/rawpy and https://www.libraw.org/download
- tifffile — BSD-3-Clause. Source: https://github.com/cgohlke/tifffile
- imageio-ffmpeg 0.8.1 — BSD-2-Clause. Bundled FFmpeg 9.0 binary and enabled codecs have their own GPL terms; build configuration and license are recorded in docs/图片引擎来源.md. Source: https://github.com/imageio/imageio-ffmpeg and https://ffmpeg.org/download.html
- FastAPI, Uvicorn, Starlette, python-docx, openpyxl, pdfplumber, Beautiful Soup, NumPy, Pillow, OpenCV and their dependencies are included under their respective original licenses.
- Python runtime — PSF License. Source: https://www.python.org/downloads/source/

The application and adapter source is included under source/ in the portable distribution. The archive recovery modules are supplied as compiled Python 3.13 components, rather than editable Python source; rebuilding that component itself requires its original source. The prepared runtime can be obtained from the version-matched portable release. The application code in source/ is distributed under AGPL-3.0-or-later to accompany the bundled AGPL PDF engine.

- PySide6 / Qt 6.12 — LGPL-3.0 / GPL-3.0 / commercial options; distributed here using the open-source LGPL option. Original DLLs remain dynamically linked. Source and notices: https://code.qt.io/cgit/pyside/pyside-setup.git/ and https://download.qt.io/archive/qt/6.12/ ; license texts are retained in licenses/ and _internal/PySide6/.
