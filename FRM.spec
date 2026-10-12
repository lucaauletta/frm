from PyInstaller.utils.hooks import collect_all
import sys

datas, binaries, hiddenimports = [('frm/assets', 'frm/assets')], [], []
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
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FRM', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FRM')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='FRM.app', bundle_identifier='org.frm.player',
                 info_plist={'CFBundleShortVersionString': '0.1.0',
                             'NSHighResolutionCapable': True})
