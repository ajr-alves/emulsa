# PyInstaller build for Windows:  pyinstaller packaging/emulsa.spec
# Produces dist/Emulsa/Emulsa.exe (a folder build, which starts faster than a single-file exe).
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "run_emulsa.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "emulsa", "assets"), os.path.join("emulsa", "assets"))],
    hiddenimports=["rawpy", "rawpy._rawpy"],
    excludes=["tkinter", "matplotlib", "scipy", "skimage", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore",
               "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Emulsa",
    icon=os.path.join(ROOT, "emulsa", "assets", "emulsa.ico"),
    console=False,
    version=os.path.join(SPECPATH, "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Emulsa", strip=False, upx=False)
