"""Light and dark themes in a quiet, Notion/Apple-like style, following the system appearance.

Colours are looked up at paint time through ``c(name)``, so switching theme repaints everything.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#ffffff",          # main window
    "canvas": "#f4f4f2",      # behind the photo
    "sidebar": "#f8f8f7",     # side panels
    "hover": "#efefed",
    "selected": "#e8e7e4",
    "line": "#e8e8e6",
    "field": "#ffffff",
    "text": "#2f2e2b",
    "muted": "#86857f",
    "faint": "#b5b4ae",
    "accent": "#d9822b",      # warm amber, Emulsa's mark
    "accent_text": "#ffffff",
    "accent_soft": "#fbefe2",
    "bubble_user": "#f1f0ee",
    "danger": "#c4442f",
    "shadow": "#22000000",
}
DARK = {
    "bg": "#1c1c1b",
    "canvas": "#151514",
    "sidebar": "#202020",
    "hover": "#2a2a29",
    "selected": "#31312f",
    "line": "#2e2e2c",
    "field": "#262625",
    "text": "#e9e8e4",
    "muted": "#9c9a94",
    "faint": "#5f5e5a",
    "accent": "#e8a04a",
    "accent_text": "#1d1408",
    "accent_soft": "#3a2c1b",
    "bubble_user": "#2c2c2a",
    "danger": "#e0705c",
    "shadow": "#66000000",
}

_mode = "system"     # "system", "light" or "dark"
_colors = LIGHT
DISPLAY_FONT = "Bricolage Grotesque 96pt"   # Emulsa's wordmark face (SIL Open Font License, bundled)


def load_fonts() -> None:
    """Register the bundled display font. Falls back to the system font if it can't load."""
    global DISPLAY_FONT
    import os
    from PySide6.QtGui import QFontDatabase
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "BricolageGrotesque-Bold.ttf")
    fid = QFontDatabase.addApplicationFont(path) if os.path.exists(path) else -1
    families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    DISPLAY_FONT = families[0] if families else ""


def is_dark() -> bool:
    return _colors is DARK


def c(name: str) -> str:
    return _colors[name]


def qc(name: str) -> QColor:
    return QColor(_colors[name])


def system_is_dark() -> bool:
    app = QApplication.instance()
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return app.palette().color(QPalette.Window).lightness() < 128


def apply(mode: str | None = None) -> None:
    """Pick light or dark and restyle the whole app."""
    global _mode, _colors
    if mode:
        _mode = mode
    dark = system_is_dark() if _mode == "system" else _mode == "dark"
    _colors = DARK if dark else LIGHT
    app = QApplication.instance()
    if DISPLAY_FONT == "Bricolage Grotesque 96pt" and not getattr(apply, "_fonts_loaded", False):
        load_fonts()
        apply._fonts_loaded = True
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "field"), (QPalette.AlternateBase, "sidebar"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.ButtonText, "text"),
                      (QPalette.Button, "field"), (QPalette.Highlight, "selected"),
                      (QPalette.HighlightedText, "text"), (QPalette.ToolTipBase, "field"),
                      (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "faint"),
                      (QPalette.Link, "accent")):
        pal.setColor(role, qc(key))
    app.setPalette(pal)
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 10.0))
    app.setFont(font)
    app.setStyleSheet(stylesheet())


def mode() -> str:
    return _mode


def stylesheet() -> str:
    k = _colors
    display = f"font-family: '{DISPLAY_FONT}';" if DISPLAY_FONT else ""
    return f"""
    QWidget {{ color: {k['text']}; }}
    QLabel#wordmark {{ {display} font-weight: 700; font-size: 19px; letter-spacing: -0.4px; }}
    QMainWindow, QWidget#root {{ background: {k['bg']}; }}
    QWidget#sidebar, QWidget#inspector {{ background: {k['sidebar']}; }}
    QWidget#sidebar {{ border-right: 1px solid {k['line']}; }}
    QWidget#inspector {{ border-left: 1px solid {k['line']}; }}
    QWidget#topbar {{ background: {k['bg']}; border-bottom: 1px solid {k['line']}; }}
    QLabel#appName {{ font-weight: 600; font-size: 14px; }}
    QLabel#title {{ {display} font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }}
    QLabel#subtle, QLabel#hint {{ color: {k['muted']}; }}
    QLabel#caption {{ color: {k['muted']}; font-size: 11px; font-weight: 600; letter-spacing: 0.4px; }}
    QLabel#photoName {{ color: {k['muted']}; }}

    QPushButton, QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 5px 9px; }}
    QPushButton:hover, QToolButton:hover {{ background: {k['hover']}; }}
    QPushButton:pressed, QToolButton:pressed, QToolButton:checked {{ background: {k['selected']}; }}
    QPushButton:focus, QToolButton:focus {{ outline: none; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {k['faint']}; }}
    QPushButton#primary {{ background: {k['accent']}; color: {k['accent_text']}; font-weight: 600; padding: 6px 14px; }}
    QPushButton#primary:hover {{ background: {k['accent']}; border: 1px solid {k['text']}; }}
    QPushButton#primary:disabled {{ background: {k['hover']}; color: {k['faint']}; }}
    QPushButton#secondary {{ border: 1px solid {k['line']}; padding: 6px 12px; }}
    QPushButton#link {{ color: {k['muted']}; padding: 4px 6px; }}
    QPushButton#link:hover {{ color: {k['text']}; background: transparent; }}
    QToolButton#section {{ font-weight: 600; color: {k['text']}; padding: 6px 2px; text-align: left; }}
    QToolButton#section:hover, QToolButton#section:checked, QToolButton#section:pressed {{ background: transparent; }}
    QToolButton#section:hover {{ color: {k['accent']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QToolButton#chip {{ color: {k['muted']}; border-radius: 12px; padding: 3px 10px; }}
    QToolButton#chip:checked {{ background: {k['selected']}; color: {k['text']}; }}

    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: {k['field']}; border: 1px solid {k['line']};
        border-radius: 7px; padding: 6px 9px; selection-background-color: {k['accent_soft']}; selection-color: {k['text']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {k['accent']}; }}
    QLineEdit#search {{ background: {k['hover']}; border: 1px solid transparent; }}
    QLineEdit#search:focus {{ background: {k['field']}; border: 1px solid {k['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{ background: {k['field']}; border: 1px solid {k['line']};
        selection-background-color: {k['hover']}; selection-color: {k['text']}; outline: 0; }}

    QListWidget, QTreeWidget, QScrollArea {{ background: transparent; border: none; outline: 0; }}
    QListWidget::item {{ border-radius: 6px; padding: 2px; }}
    QTreeWidget {{ show-decoration-selected: 1; }}
    QTreeWidget::item {{ padding: 2px; border: none; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {k['hover']}; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background: {k['selected']}; color: {k['text']}; }}
    QTreeWidget::branch {{ background: transparent; border-image: none; image: none; }}
    QWidget#kindbar {{ background: {k['bg']}; border-top: 1px solid {k['line']}; }}
    QListWidget#filmstrip {{ background: {k['bg']}; border-top: 1px solid {k['line']}; }}
    QListWidget#filmstrip[joined="true"] {{ border-top: none; }}
    QListWidget#filmstrip::item {{ margin: 3px; border-radius: 4px; border: 2px solid transparent; }}
    QListWidget#filmstrip::item:selected {{ background: transparent; border: 2px solid {k['accent']}; }}

    QSlider::groove:horizontal {{ height: 4px; background: {k['line']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {k['faint']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {k['field']}; border: 1px solid {k['faint']};
        width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }}
    QSlider::handle:horizontal:hover {{ border: 1px solid {k['accent']}; }}
    QSlider:focus {{ outline: none; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {k['faint']}; background: {k['field']}; }}
    QCheckBox::indicator:checked {{ background: {k['accent']}; border-color: {k['accent']}; }}
    QProgressBar {{ background: {k['hover']}; border: none; border-radius: 3px; height: 6px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background: {k['accent']}; border-radius: 3px; }}

    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {k['line']}; border-radius: 3px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {k['faint']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {k['line']}; border-radius: 3px; min-width: 28px; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}

    QMenu {{ background: {k['field']}; border: 1px solid {k['line']}; border-radius: 8px; padding: 5px; }}
    QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {k['hover']}; }}
    QMenu::separator {{ height: 1px; background: {k['line']}; margin: 4px 6px; }}
    QDialog {{ background: {k['bg']}; }}
    QToolTip {{ background: {k['text']}; color: {k['bg']}; border: none; padding: 5px 8px; border-radius: 5px; }}
    QStatusBar {{ background: {k['bg']}; color: {k['muted']}; }}
    QStatusBar::item {{ border: none; }}

    QFrame#chatPanel {{ background: {k['bg']}; border: 1px solid {k['line']}; border-radius: 14px; }}
    QLabel#bubbleUser {{ background: {k['bubble_user']}; border-radius: 12px; padding: 8px 11px; }}
    QLabel#bubbleBot {{ padding: 4px 2px; }}
    QLabel#bubbleError {{ color: {k['danger']}; padding: 4px 2px; }}
    QFrame#lookCard {{ background: {k['accent_soft']}; border-radius: 10px; }}
    QFrame#notice {{ background: {k['sidebar']}; border-radius: 10px; }}
    QFrame#updateCard {{ background: {k['accent_soft']}; border-radius: 10px; }}
    QLabel#updateTitle {{ {display} font-weight: 700; font-size: 14px; }}
    """
