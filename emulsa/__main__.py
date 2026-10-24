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
        from emulsa.ui import theme
        from emulsa.ui.main_window import MainWindow
        theme.apply("system")
        img = np.random.default_rng(3).random((120, 160, 3)).astype(np.float32)
        for look in BUILTIN:
            out = render(img, look["params"], scale=0.5)
            if not np.isfinite(out).all():
                print(f"self-test: {look['name']} produced invalid pixels")
                return 1
        imageio.save(os.path.join(tmp, "test.jpg"), out, "JPEG", 90)
        write_cube(os.path.join(tmp, "test.cube"), BUILTIN[0]["params"], "test", size=9)
        import anthropic  # noqa: F401  (proves the assistant's SDK is bundled)
        from emulsa import assistant
        assistant.KeyStore().get()
        from emulsa.ui.splash import Splash
        sp = Splash()
        sp.start()
        sp.t = 1.0
        sp.grab()             # draws a mid-animation frame
        sp.skip()
        win = MainWindow()
        win.chat.show()
        win.set_files([os.path.join(tmp, "test.jpg")])
        app.processEvents()
        win.close()
        print(f"self-test: ok ({len(BUILTIN)} looks, rawpy {'available' if imageio.rawpy else 'MISSING'})")
        return 0 if imageio.rawpy is not None else 1


def app_icon():
    """All the icon sizes, so the taskbar and title bar get the crisp small e, not a shrunk big one."""
    from PySide6.QtGui import QIcon
    assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    icon = QIcon()
    ico = os.path.join(assets, "emulsa.ico")       # 16-256 px, simplified at 16-32
    if os.path.exists(ico):
        icon.addFile(ico)
    for name in ("emulsa-small.png", "emulsa-512.png"):
        path = os.path.join(assets, name)
        if os.path.exists(path):
            icon.addFile(path)
    return icon


def main():
    if "--self-test" in sys.argv:
        sys.exit(_self_test())

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from emulsa.store import Store
    from emulsa.ui import theme
    from emulsa.ui.main_window import MainWindow

    if sys.platform == "win32":
        # an explicit app ID makes the taskbar use Emulsa's own icon and group its windows,
        # and matches the ID on the Start menu shortcut the installer creates
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ajr-alves.Emulsa")
        except Exception:  # nosec B110 - cosmetic only
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Emulsa")
    app.setOrganizationName("Emulsa")
    app.setStyle("Fusion")
    store = Store()
    theme.apply(store.get("appearance", "system"))
    app.setWindowIcon(app_icon())
    from emulsa.ui.splash import Splash
    animate = store.get("startup_animation", True) and "--no-splash" not in sys.argv
    splash = None
    if animate:
        splash = Splash()
        splash.show()
        app.processEvents()   # paint the empty card right away, so the launch feels instant
    win = MainWindow(store)

    def show_main():
        win.show()
        win.raise_()
        win.activateWindow()
        if splash is not None:
            splash.raise_()   # keep fading out on top

    if splash is not None:
        splash.handover.connect(show_main)
        splash.start()        # starts only now that the window is built, so it never stutters
    else:
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
