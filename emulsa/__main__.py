"""Start Emulsa:  python -m emulsa [folder or photo]

``--self-test`` starts the app without showing a window, grades a test image with every look, writes a
JPEG and a .cube file to a temporary folder, then exits with 0 on success. The release builds run it
on each platform to prove the packaged app really works.
"""
import os
import sys


def _self_test() -> int:
    import tempfile

    import numpy as np
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from emulsa import imageio
    from emulsa.engine import render, write_cube
    from emulsa.looks import BUILTIN

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EMULSA_HOME"] = tmp
        app = QApplication(sys.argv[:1])
        from emulsa.ui.main_window import MainWindow
        img = np.random.default_rng(3).random((120, 160, 3)).astype(np.float32)
        for look in BUILTIN:
            out = render(img, look["params"], scale=0.5)
            if not np.isfinite(out).all():
                print(f"self-test: {look['name']} produced invalid pixels")
                return 1
        imageio.save(os.path.join(tmp, "test.jpg"), out, "JPEG", 90)
        write_cube(os.path.join(tmp, "test.cube"), BUILTIN[0]["params"], "test", size=9)
        win = MainWindow()
        win.set_files([os.path.join(tmp, "test.jpg")])
        app.processEvents()
        win.close()
        print(f"self-test: ok ({len(BUILTIN)} looks, rawpy {'available' if imageio.rawpy else 'MISSING'})")
        return 0 if imageio.rawpy is not None else 1


def main():
    if "--self-test" in sys.argv:
        sys.exit(_self_test())

    from PySide6.QtGui import QColor, QIcon, QPalette
    from PySide6.QtWidgets import QApplication

    from emulsa.ui import theme
    from emulsa.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Emulsa")
    app.setOrganizationName("Emulsa")
    app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(QPalette.Highlight, QColor(theme.RAISED))
    pal.setColor(QPalette.HighlightedText, QColor(theme.TEXT))
    app.setPalette(pal)
    app.setStyleSheet(theme.STYLESHEET)
    here = os.path.dirname(os.path.abspath(__file__))
    icon = os.path.join(here, "assets", "emulsa.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    win = MainWindow()
    win.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.exists(args[0]):
        target = args[0]
        if os.path.isdir(target):
            win.open_folder(target)
        else:
            win.set_files([target])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
