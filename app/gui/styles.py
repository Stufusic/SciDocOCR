"""Modern Dark & Light Theme Stylesheets (QSS) for SciDoc OCR."""

DARK_THEME_QSS = """
/* Global Window & Typography */
QMainWindow, QDialog, QWidget {
    background-color: #0f172a; /* Slate 900 */
    color: #f8fafc; /* Slate 50 */
    font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
    font-size: 10pt;
}

/* Toolbars & Menubars */
QMenuBar {
    background-color: #1e293b;
    color: #f8fafc;
    border-bottom: 1px solid #334155;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #3b82f6;
    border-radius: 4px;
}
QMenu {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #2563eb;
    border-radius: 4px;
}

QToolBar {
    background-color: #1e293b;
    border-bottom: 1px solid #334155;
    spacing: 8px;
    padding: 6px;
}

/* Push Buttons */
QPushButton {
    background-color: #2563eb; /* Blue 600 */
    color: #ffffff;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    padding: 7px 14px;
    min-height: 18px;
}
QPushButton:hover {
    background-color: #3b82f6; /* Blue 500 */
}
QPushButton:pressed {
    background-color: #1d4ed8; /* Blue 700 */
}
QPushButton:disabled {
    background-color: #334155;
    color: #94a3b8;
}

QPushButton#secondaryBtn {
    background-color: #334155;
    color: #f8fafc;
    border: 1px solid #475569;
}
QPushButton#secondaryBtn:hover {
    background-color: #475569;
}

QPushButton#accentBtn {
    background-color: #10b981; /* Emerald 500 */
    color: #ffffff;
}
QPushButton#accentBtn:hover {
    background-color: #059669;
}

/* Segmented Pill Slider Switcher (Thanh trượt chuyển chế độ) */
QFrame#segmentedSlider {
    background-color: #0b1329;
    border: 1px solid #334155;
    border-radius: 9px;
    padding: 2px;
}

QPushButton#segmentBtn {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 11px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton#segmentBtn:hover {
    color: #f8fafc;
    background-color: #1e293b;
}

QPushButton#segmentBtn:checked {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #3b82f6;
}

/* Line Edit & Text Edit */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #3b82f6;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #60a5fa;
}

/* Combo Box */
QComboBox {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 20px;
}
QComboBox:hover {
    border: 1px solid #60a5fa;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    selection-background-color: #2563eb;
    border-radius: 6px;
}

/* Splitter */
QSplitter::handle {
    background-color: #1e293b;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #334155;
    background-color: #0f172a;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #0f172a;
    color: #60a5fa;
    border-bottom: 2px solid #3b82f6;
    font-weight: 600;
}

/* List View / Tree View */
QListWidget, QTreeWidget {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #f8fafc;
    padding: 4px;
}
QListWidget::item {
    border-radius: 4px;
    padding: 6px 8px;
    margin-bottom: 2px;
}
QListWidget::item:hover {
    background-color: #334155;
}
QListWidget::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}

/* Progress Bar */
QProgressBar {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #f8fafc;
    font-weight: bold;
    height: 16px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #10b981);
    border-radius: 5px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background-color: #0f172a;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background-color: #334155;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background-color: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Status Bar */
QStatusBar {
    background-color: #1e293b;
    color: #94a3b8;
    border-top: 1px solid #334155;
    font-size: 9pt;
}
"""
