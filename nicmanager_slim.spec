# -*- mode: python ; coding: utf-8 -*-
_EXCLUDE_BIN_FRAGMENTS = [
    "Qt6Quick", "Qt6Qml", "Qt6QmlModels", "Qt6Pdf", "Qt6Network",
    "Qt6OpenGL", "Qt6OpenGLWidgets", "Qt6Multimedia", "Qt6DBus", "Qt6Sql",
    "Qt6Test", "Qt6Concurrent", "Qt6PrintSupport", "opengl32sw.dll",
    "libEGL.dll", "libGLESv2.dll", "d3dcompiler", "Qt6Designer",
    "Qt6UiTools", "Qt6QmlCompiler", "Qt6ShaderTools", "Qt6Quick3D", "Qt6Svg",
]

a = Analysis(
    ['main.py'], pathex=[], binaries=[], datas=[], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtPdf',
              'PySide6.QtNetwork', 'PySide6.QtMultimedia', 'PySide6.QtOpenGL',
              'PySide6.QtOpenGLWidgets', 'PySide6.QtSql',
              'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtSvg', 'PySide6.QtPrintSupport', 'PySide6.QtDBus',
              'PySide6.QtTest', 'PySide6.QtConcurrent', 'PySide6.QtDesigner',
              'PySide6.QtUiTools', 'PySide6.Qt3DCore', 'tkinter'],
    noarchive=False, optimize=0,
)
_keep = []
for item in a.binaries:
    base = item[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if any(frag.lower() in base for frag in _EXCLUDE_BIN_FRAGMENTS):
        print(f"[slim] exclude binary: {base}")
        continue
    _keep.append(item)
a.binaries = _keep

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='NetManagerTool', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, upx_exclude=[], runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
    uac_admin=True, icon=['icon.ico'],
)
