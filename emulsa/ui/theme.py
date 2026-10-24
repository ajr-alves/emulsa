"""Dark darkroom theme: graphite panels so photos read true, with a safelight-amber accent."""

BG = "#18191b"        # behind the photo
PANEL = "#212225"     # side panels
RAISED = "#2a2b2f"    # inputs, buttons
BORDER = "#34363b"
TEXT = "#e7e4dd"
MUTED = "#9b978d"
ACCENT = "#e9a23b"    # safelight amber
ACCENT_SOFT = "rgba(233, 162, 59, 0.16)"

STYLESHEET = f"""
* {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, QWidget#central {{ background: {BG}; }}
QWidget#panel {{ background: {PANEL}; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{ background: {PANEL}; padding: 8px 12px; color: {MUTED};
    text-transform: uppercase; font-size: 11px; letter-spacing: 1px; }}
QLabel#section {{ color: {MUTED}; font-size: 11px; letter-spacing: 1px; padding-top: 10px; }}
QLabel#lookTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#lookBrand {{ color: {MUTED}; font-size: 12px; }}
QLabel#hint {{ color: {MUTED}; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 4px 6px; }}
QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px; spacing: 6px; }}
QToolButton, QPushButton {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 5px; padding: 6px 12px; }}
QToolButton:hover, QPushButton:hover {{ border-color: {MUTED}; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton#primary {{ background: {ACCENT}; color: #1a1408; border-color: {ACCENT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: #f2b55a; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5d5b56; }}
QToolButton:focus, QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit, QComboBox, QSpinBox {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 5px; padding: 5px 8px; }}
QComboBox QAbstractItemView {{ background: {RAISED}; selection-background-color: {ACCENT_SOFT}; }}
QTreeWidget, QListWidget {{ background: {PANEL}; border: none; outline: 0; }}
QTreeWidget::item {{ padding: 3px 2px; border-radius: 4px; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QTreeWidget::branch {{ background: transparent; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {RAISED}; }}
QListWidget#filmstrip {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
QListWidget#filmstrip::item {{ margin: 4px; border-radius: 4px; }}
QListWidget#filmstrip::item:selected {{ border: 2px solid {ACCENT}; }}
QSlider::groove:horizontal {{ height: 3px; background: {BORDER}; border-radius: 1px; }}
QSlider::sub-page:horizontal {{ background: {MUTED}; border-radius: 1px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {MUTED}; border-radius: 3px; background: {RAISED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QProgressBar {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 4px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QMenu {{ background: {RAISED}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
QDialog {{ background: {PANEL}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QSplitter::handle {{ background: {BORDER}; }}
"""
