from PyInstaller.utils.hooks import collect_all
import sys

datas, binaries, hiddenimports = [('frm/assets', 'frm/assets'), ('build/legal', 'legal')], [], []
for package in ['OpenImageIO', 'PyOpenColorIO', 'av']:
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden

a = Analysis(['run_frm.py'], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
                                         'PySide6.QtPdf', 'PySide6.QtPdfWidgets'], noarchive=False)
pyz = PYZ(a.pure)
if sys.platform == 'darwin':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FRM', debug=False,
              bootloader_ignore_signals=False, strip=False, upx=False, console=False)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FRM')
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='FRM-Portable',
              debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
              version='packaging/windows-version.txt' if sys.platform == 'win32' else None)
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='FRM.app', bundle_identifier='org.frm.player',
                 info_plist={'CFBundleShortVersionString': '0.3.1',
                             'NSHumanReadableCopyright': 'Copyright © 2026 Luca Auletta — https://github.com/lucaauletta/frm',
                             'NSHighResolutionCapable': True})
