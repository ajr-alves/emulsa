"""Start Emulsa:  python -m emulsa [folder or photo]"""
import os
import sys


def main():
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
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        target = sys.argv[1]
        if os.path.isdir(target):
            win.open_folder(target)
        else:
            win.set_files([target])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
