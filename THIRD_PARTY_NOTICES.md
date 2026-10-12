# Third-party components

FRM source is GPL-3.0-only. Bundled libraries remain under their own licenses. Portable builds collect available license, copyright and notice files from installed distributions into `licenses/` and record versions in `dependency-versions.json`.

| Component | Purpose | Upstream license/source |
| --- | --- | --- |
| Qt / PySide6 / Shiboken | Desktop UI | LGPL-3.0 / GPL alternatives; [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html), [Qt sources](https://download.qt.io/archive/qt/), [PySide sources](https://code.qt.io/cgit/pyside/pyside-setup.git/) |
| OpenImageIO | Image decoding | Apache-2.0; [source](https://github.com/AcademySoftwareFoundation/OpenImageIO) |
| OpenColorIO and built-in ACES configs | Viewing color | BSD-3-Clause and config-specific notices; [OCIO source](https://github.com/AcademySoftwareFoundation/OpenColorIO), [config source](https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES) |
| PyAV | FFmpeg bindings | BSD-3-Clause; [source](https://github.com/PyAV-Org/PyAV) |
| FFmpeg and codec libraries | Video decoding | Build-dependent LGPL/GPL and component licenses; [FFmpeg licensing](https://ffmpeg.org/legal.html), [PyAV wheel build sources](https://github.com/PyAV-Org/pyav-wheels) |
| NumPy | Pixel arrays | BSD-3-Clause and bundled component notices; [source](https://github.com/numpy/numpy) |
| Inter | Interface font | SIL Open Font License 1.1; license included in `frm/assets/OFL.txt`; [source](https://github.com/rsms/inter) |
| ReportLab | Review PDF generation | BSD-style license; [source](https://hg.reportlab.com/hg-public/reportlab/) |
| Pillow | PDF image embedding | HPND/Pillow license; [source](https://github.com/python-pillow/Pillow) |
| charset-normalizer | ReportLab dependency | MIT; [source](https://github.com/jawah/charset_normalizer) |
| Python | Runtime | PSF license and bundled notices; [source](https://www.python.org/downloads/source/) |
| PyInstaller | Packaging/bootloader | GPL with bootloader exception; [license](https://pyinstaller.org/en/stable/license.html), [source](https://github.com/pyinstaller/pyinstaller) |

The application uses dynamically loaded Qt libraries in a directory/app bundle. Do not strip the dependency notices when redistributing. FRM's GPL does not replace dependency obligations. Codec patent permissions are not supplied by this project.

Before redistributing modified binary bundles, audit the exact wheel contents and FFmpeg build configuration: dependency source links alone are not a substitute for any corresponding-source delivery obligations. The included `source/` directory contains FRM's corresponding application source and build scripts; it does not claim to contain the complete source of every third-party binary.

ACES is a project of the Academy of Motion Picture Arts and Sciences. FRM is an independent project and is not certified or endorsed by the Academy or the listed dependencies.
