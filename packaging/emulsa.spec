# PyInstaller build for every platform:  pyinstaller packaging/emulsa.spec
#   Windows -> dist/Emulsa/Emulsa.exe          (then packaging/installer.iss makes the installer)
#   macOS   -> dist/Emulsa.app                 (then packaging/make_dmg.sh makes the .dmg)
#   Linux   -> dist/Emulsa/Emulsa              (then packaging/make_appimage.sh makes the AppImage)
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ASSETS = os.path.join(ROOT, "emulsa", "assets")
with open(os.path.join(ROOT, "emulsa", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'__version__ = "([^"]+)"', fh.read()).group(1)

a = Analysis(
    [os.path.join(ROOT, "run_emulsa.py")],
    pathex=[ROOT],
    datas=[(ASSETS, os.path.join("emulsa", "assets"))],
    hiddenimports=["rawpy", "rawpy._rawpy"],
    excludes=["tkinter", "matplotlib", "scipy", "skimage", "IPython",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "win32":
    icon = os.path.join(ASSETS, "emulsa.ico")
elif sys.platform == "darwin":
    icon = os.path.join(ASSETS, "emulsa.icns")
else:
    icon = None

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Emulsa",
    icon=icon,
    console=False,
    version=os.path.join(SPECPATH, "version_info.txt") if sys.platform == "win32" else None,
    target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Emulsa", strip=False, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Emulsa.app",
        icon=icon,
        bundle_identifier="io.github.ajr-alves.emulsa",
        version=VERSION,
        info_plist={
            "CFBundleName": "Emulsa",
            "CFBundleDisplayName": "Emulsa",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,   # follow light/dark mode
            "LSApplicationCategoryType": "public.app-category.photography",
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Image",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["public.jpeg", "public.png", "public.tiff", "public.camera-raw-image"],
            }],
        },
    )
