"""Permanent Kavitro-aligned light styling for EVEL tool dialogs."""

from __future__ import annotations

from qgis.PyQt.QtCore import QSize, QTimer
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QComboBox, QWidget


EVEL_LIGHT_STYLE = """
QDialog {
    background: #f6f7f8;
    color: #24292e;
}
QDialog QLabel {
    background: transparent;
    color: #24292e;
}
QDialog QFrame {
    background: transparent;
    border: none;
}
QDialog QLineEdit,
QDialog QTextEdit,
QDialog QPlainTextEdit,
QDialog QSpinBox,
QDialog QDoubleSpinBox,
QDialog QDateEdit,
QDialog QDateTimeEdit,
QDialog QComboBox {
    background: #ffffff;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 24px;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}
QDialog QLineEdit:hover,
QDialog QTextEdit:hover,
QDialog QPlainTextEdit:hover,
QDialog QSpinBox:hover,
QDialog QDoubleSpinBox:hover,
QDialog QDateEdit:hover,
QDialog QDateTimeEdit:hover,
QDialog QComboBox:hover {
    border-color: #2188ff;
}
QDialog QLineEdit:focus,
QDialog QTextEdit:focus,
QDialog QPlainTextEdit:focus,
QDialog QSpinBox:focus,
QDialog QDoubleSpinBox:focus,
QDialog QDateEdit:focus,
QDialog QDateTimeEdit:focus,
QDialog QComboBox:focus {
    background: #ffffff;
    border: 1px solid #2188ff;
}
QDialog QLineEdit:disabled,
QDialog QTextEdit:disabled,
QDialog QPlainTextEdit:disabled,
QDialog QSpinBox:disabled,
QDialog QDoubleSpinBox:disabled,
QDialog QDateEdit:disabled,
QDialog QDateTimeEdit:disabled,
QDialog QComboBox:disabled {
    background: #f0f2f4;
    color: rgba(36, 41, 46, 130);
    border: 1px dashed #d1d7de;
}
QDialog QComboBox::drop-down {
    width: 22px;
    background: #ffffff;
    border: none;
    border-left: 1px solid #e1e4e8;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}
QDialog QComboBox::drop-down:hover {
    background: #f0f4f8;
}
QDialog QComboBox QAbstractItemView,
QDialog QAbstractItemView {
    background: #ffffff;
    alternate-background-color: #f6f8fa;
    color: #24292e;
    border: 1px solid #2188ff;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
    outline: 0;
}
QDialog QPushButton {
    background: #f7f9fb;
    color: #1f2933;
    border: 1px solid #d5d8df;
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 24px;
}
QDialog QPushButton:hover {
    background: #edf2f6;
    border-color: #c8cdd6;
}
QDialog QPushButton:pressed {
    background: #e3e8ef;
    border-color: #b7beca;
}
QDialog QPushButton:focus {
    border: 1px solid #2188ff;
}
QDialog QPushButton:default {
    background: #0078d4;
    color: #ffffff;
    border: 1px solid #005a9e;
    font-weight: 600;
}
QDialog QPushButton:default:hover {
    background: #2188ff;
    border-color: #0366d6;
}
QDialog QPushButton:default:pressed {
    background: #0366d6;
}
QDialog QPushButton:disabled {
    background: #edf1f5;
    color: rgba(31, 41, 51, 120);
    border: 1px dashed #d5d8df;
}
QDialog QToolButton {
    background: #f7f9fb;
    color: #1f2933;
    border: 1px solid #d5d8df;
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 24px;
}
QDialog QToolButton:hover {
    background: #edf2f6;
    border-color: #2188ff;
}
QDialog QToolButton:checked {
    background: #0078d4;
    color: #ffffff;
    border: 1px solid #005a9e;
}
QDialog QCheckBox {
    color: #24292e;
    spacing: 6px;
}
QDialog QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 3px;
}
QDialog QCheckBox::indicator:checked {
    background: #0078d4;
    border-color: #005a9e;
}
QDialog QGroupBox {
    background: #ffffff;
    color: #24292e;
    border: 1px solid #e1e4e8;
    border-radius: 8px;
    margin-top: 18px;
    padding-top: 8px;
}
QDialog QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 2px 6px;
    color: #111416;
    font-weight: 600;
    background: #f6f7f8;
    border-radius: 4px;
}
QDialog QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 8px;
    top: -1px;
}
QDialog QTabWidget QStackedWidget > QWidget {
    background: #ffffff;
    color: #24292e;
}
QDialog QTabBar::tab {
    background: #f6f8fa;
    color: #4a5568;
    border: 1px solid #d0d7de;
    border-bottom: none;
    padding: 7px 12px;
    min-width: 90px;
}
QDialog QTabBar::tab:hover {
    background: #edf4fb;
    color: #005a9e;
}
QDialog QTabBar::tab:selected {
    background: #0078d4;
    color: #ffffff;
    border-color: #005a9e;
    font-weight: 600;
}
QDialog QListWidget,
QDialog QTreeView,
QDialog QTableView,
QDialog QTableWidget {
    background: #ffffff;
    alternate-background-color: #f6f8fa;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 8px;
    gridline-color: #e1e4e8;
    outline: 0;
}
QDialog QListWidget::item,
QDialog QTreeView::item {
    padding: 5px 7px;
    border-radius: 4px;
}
QDialog QListWidget::item:hover,
QDialog QTreeView::item:hover {
    background: #f0f4f8;
}
QDialog QListWidget::item:selected,
QDialog QTreeView::item:selected {
    background: #0078d4;
    color: #ffffff;
}
QDialog QHeaderView::section {
    background: rgba(15, 118, 110, 185);
    color: #ffffff;
    border: none;
    border-right: 1px solid rgba(31, 41, 55, 80);
    border-bottom: 2px solid #0f766e;
    padding: 4px 6px;
    font-weight: 600;
}
QDialog QProgressBar {
    background: #e7edf2;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    text-align: center;
    min-height: 18px;
}
QDialog QProgressBar::chunk {
    background: #0f766e;
    border-radius: 4px;
}
QDialog QScrollArea {
    background: #ffffff;
    border: none;
}
QDialog QWidget#lightSurface,
QDialog QWidget#tabContent {
    background: #ffffff;
    color: #24292e;
}
QDialog QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 1px;
}
QDialog QScrollBar::handle:vertical {
    background: rgba(15, 118, 110, 105);
    border: 1px solid rgba(15, 118, 110, 60);
    border-radius: 4px;
    min-height: 24px;
}
QDialog QScrollBar::handle:vertical:hover {
    background: rgba(15, 118, 110, 150);
}
QDialog QScrollBar::add-line,
QDialog QScrollBar::sub-line {
    width: 0;
    height: 0;
    background: transparent;
}
QDialog QSplitter::handle {
    background: #d1d5db;
}
QDialog QSplitter::handle:hover {
    background: #0f766e;
}
QToolTip {
    background: #ffffff;
    color: #24292e;
    border: 1px solid #d0d7de;
    padding: 5px 7px;
}
"""


PUMPING_STATION_LIGHT_STYLE = """
QDialog#evelPumpingStationDialog QFrame#heroFrame {
    background: #f6f7f8;
    border-bottom: 1px solid rgba(0, 120, 212, 150);
}
QDialog#evelPumpingStationDialog QLineEdit#heroNameEdit {
    background: #ffffff;
    color: #111416;
    border: 1px solid #d0d7de;
    border-radius: 7px;
    padding: 4px 9px;
    font-size: 20px;
    font-weight: 700;
}
QDialog#evelPumpingStationDialog QLineEdit#heroNameEdit:focus {
    border: 1px solid #2188ff;
}
QDialog#evelPumpingStationDialog QFrame#editorFrame {
    background: #ffffff;
    border: 1px solid #e1e4e8;
    border-radius: 10px;
}
QDialog#evelPumpingStationDialog QWidget#tabContent {
    background: #ffffff;
}
QDialog#evelPumpingStationDialog QLabel#fieldLabel {
    color: #111416;
    font-weight: 600;
}
QDialog#evelPumpingStationDialog QPushButton#previewToggleButton {
    background: rgba(0, 120, 212, 18);
    color: #005a9e;
    border: 1px solid rgba(0, 120, 212, 110);
}
QDialog#evelPumpingStationDialog QPushButton#previewToggleButton:hover {
    background: rgba(0, 120, 212, 35);
    border-color: #2188ff;
}
QDialog#evelPumpingStationDialog QPushButton#cancelButton {
    background: transparent;
    border: none;
    color: #4a5568;
}
QDialog#evelPumpingStationDialog QPushButton#cancelButton:hover {
    color: #111416;
    text-decoration: underline;
}
QDialog#evelPumpingStationDialog QFrame#busyFrame {
    background: #edf6ff;
    border: 1px solid #8fc8f4;
    border-radius: 7px;
}
QDialog#evelPumpingStationDialog QFrame#busyFrame[status="error"] {
    background: #fff1f1;
    border-color: #d36f76;
}
"""

DUCT_EDITOR_LIGHT_STYLE = """
QDialog#evelDuctEditorDialog QFrame#ductHeroFrame {
    background: #ffffff;
    border: 1px solid #e1e4e8;
    border-radius: 9px;
}
QDialog#evelDuctEditorDialog QLabel#ductTitle {
    color: #111416;
    font-size: 19px;
    font-weight: 700;
}
QDialog#evelDuctEditorDialog QLabel#ductContext,
QDialog#evelDuctEditorDialog QLabel#ductStepHint {
    color: #57606a;
}
QDialog#evelDuctEditorDialog QLabel#ductLayerBadge {
    background: #edf6ff;
    color: #005a9e;
    border: 1px solid #b8d8f0;
    border-radius: 8px;
    padding: 4px 9px;
    font-weight: 600;
}
QDialog#evelDuctEditorDialog QFrame#ductPreviewFrame,
QDialog#evelDuctEditorDialog QFrame#ductEditorFrame {
    background: #ffffff;
    border: 1px solid #e1e4e8;
    border-radius: 10px;
}
QDialog#evelDuctEditorDialog QFrame#ductTechnicalCard {
    background: #f9fafb;
    border: 1px solid #d0d7de;
    border-radius: 8px;
}
QDialog#evelDuctEditorDialog QLabel#ductTechnicalValue {
    color: #111416;
    font-weight: 600;
}
QDialog#evelDuctEditorDialog QLabel#ductStepHeading {
    color: #111416;
    font-size: 14px;
    font-weight: 700;
}
QDialog#evelDuctEditorDialog QLabel#fieldLabel {
    color: #111416;
    font-weight: 600;
}
QDialog#evelDuctEditorDialog QLabel#ductErrorLabel {
    background: #fff1f1;
    color: #c53030;
    border: 1px solid #d36f76;
    border-radius: 7px;
    padding: 7px 9px;
}
QDialog#evelDuctEditorDialog QLabel#ductNoticeLabel {
    background: #fff8dc;
    color: #6b4f00;
    border: 1px solid #e5bf45;
    border-radius: 7px;
    padding: 7px 9px;
}
QDialog#evelDuctEditorDialog QPushButton#cancelButton {
    background: transparent;
    border: none;
    color: #4a5568;
}
QDialog#evelDuctEditorDialog QPushButton#cancelButton:hover {
    color: #111416;
    text-decoration: underline;
}
"""

HYDRANT_EDITOR_LIGHT_STYLE = """
QDialog#evelHydrantDialog QFrame#hydrantHeroFrame {
    background: #ffffff;
    border: 1px solid #e1e4e8;
    border-radius: 9px;
}
QDialog#evelHydrantDialog QLabel#hydrantTitle {
    color: #111416;
    font-size: 19px;
    font-weight: 700;
}
QDialog#evelHydrantDialog QLabel#hydrantContext {
    color: #57606a;
}
QDialog#evelHydrantDialog QFrame#hydrantPreviewFrame,
QDialog#evelHydrantDialog QFrame#hydrantEditorFrame {
    background: #ffffff;
    border: 1px solid #e1e4e8;
    border-radius: 10px;
}
QDialog#evelHydrantDialog QComboBox {
    background-color: #ffffff;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 24px;
}
QDialog#evelHydrantDialog QComboBox::drop-down {
    width: 24px;
    background: #f7f9fb;
    border: none;
    border-left: 1px solid #e1e4e8;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}
QDialog#evelHydrantDialog QPushButton#hydrantSaveButton {
    background: #0078d4;
    color: #ffffff;
    border: 1px solid #005a9e;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 26px;
    font-weight: 600;
}
QDialog#evelHydrantDialog QPushButton#hydrantSaveButton:hover {
    background: #2188ff;
    border-color: #0366d6;
}
QDialog#evelHydrantDialog QPushButton#hydrantCancelButton {
    background: transparent;
    color: #4a5568;
    border: none;
    padding: 6px 10px;
}
QDialog#evelHydrantDialog QPushButton#hydrantCancelButton:hover {
    color: #111416;
    text-decoration: underline;
}
"""

COMBO_POPUP_LIGHT_STYLE = """
QAbstractItemView {
    background: #ffffff;
    alternate-background-color: #f6f8fa;
    color: #24292e;
    border: 1px solid #2188ff;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
    outline: 0;
}
QAbstractItemView::item {
    min-height: 22px;
    padding: 3px 7px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: rgba(15, 118, 110, 105);
    border-radius: 4px;
    min-height: 24px;
}
"""

EVEL_TOOLBAR_LIGHT_STYLE = """
QToolBar#EVELNetworkToolsToolbar {
    background: #f6f7f8;
    color: #24292e;
    border: 1px solid #e1e4e8;
    spacing: 2px;
    padding: 2px;
}
QToolBar#EVELNetworkToolsToolbar QToolButton {
    background: transparent;
    color: #24292e;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px 4px;
    min-height: 20px;
}
QToolBar#EVELNetworkToolsToolbar QToolButton:hover {
    background: #edf4fb;
    border-color: #b8d8f0;
}
QToolBar#EVELNetworkToolsToolbar QToolButton:pressed {
    background: #dcecf8;
    border-color: #2188ff;
}
QToolBar#EVELNetworkToolsToolbar QToolButton:checked {
    background: #0078d4;
    color: #ffffff;
    border-color: #005a9e;
}
QToolBar#EVELNetworkToolsToolbar QToolButton:disabled {
    background: transparent;
    color: #7d8790;
}
QToolBar#EVELNetworkToolsToolbar::separator {
    background: #d0d7de;
    width: 1px;
    margin: 3px 2px;
}
"""

EVEL_MENU_LIGHT_STYLE = """
QMenu#EVELAddDuctMenu {
    background: #ffffff;
    color: #24292e;
    border: 1px solid #d0d7de;
    padding: 4px;
}
QMenu#EVELAddDuctMenu::item {
    background: transparent;
    color: #24292e;
    border-radius: 4px;
    padding: 6px 24px 6px 8px;
}
QMenu#EVELAddDuctMenu::item:selected {
    background: #0078d4;
    color: #ffffff;
}
QMenu#EVELAddDuctMenu::item:disabled {
    color: #7d8790;
}
QMenu#EVELAddDuctMenu::separator {
    background: #e1e4e8;
    height: 1px;
    margin: 4px 6px;
}
"""


def _light_palette(widget) -> QPalette:
    palette = QPalette(widget.palette())
    roles = {
        QPalette.Window: "#f6f7f8",
        QPalette.WindowText: "#24292e",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f6f8fa",
        QPalette.Text: "#24292e",
        QPalette.Button: "#f7f9fb",
        QPalette.ButtonText: "#1f2933",
        QPalette.Highlight: "#0078d4",
        QPalette.HighlightedText: "#ffffff",
        QPalette.ToolTipBase: "#ffffff",
        QPalette.ToolTipText: "#24292e",
        QPalette.Light: "#ffffff",
        QPalette.Midlight: "#edf2f6",
        QPalette.Mid: "#b6c2cd",
        QPalette.Dark: "#57606a",
        QPalette.Shadow: "#24292e",
    }
    for role, color in roles.items():
        palette.setColor(QPalette.Active, role, QColor(color))
        palette.setColor(QPalette.Inactive, role, QColor(color))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#7d8790"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#7d8790"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#7d8790"))
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor("#f0f2f4"))
    return palette


def _style_combo_popups(widget) -> None:
    if widget is None:
        return
    try:
        combos = widget.findChildren(QComboBox)
    except RuntimeError:
        return
    for combo in combos:
        try:
            view = combo.view()
        except RuntimeError:
            continue
        if view is not None:
            try:
                view.setPalette(_light_palette(view))
                view.setStyleSheet(COMBO_POPUP_LIGHT_STYLE)
            except RuntimeError:
                continue


def _finish_light_style(widget) -> None:
    """Re-apply light roles after Qt has polished all child widgets."""

    if widget is None:
        return
    try:
        children = widget.findChildren(QWidget)
    except RuntimeError:
        return
    for child in (widget, *children):
        try:
            child.setPalette(_light_palette(child))
        except RuntimeError:
            continue
    _style_combo_popups(widget)


def apply_evel_light_style(
    widget,
    *,
    pumping_station: bool = False,
    duct_editor: bool = False,
    hydrant_editor: bool = False,
) -> None:
    """Apply the fixed light theme; EVEL intentionally has no theme toggle."""

    if widget is None:
        return
    widget.setProperty("evelLightTheme", True)
    widget.setPalette(_light_palette(widget))
    widget.setAutoFillBackground(True)
    style = EVEL_LIGHT_STYLE
    if pumping_station:
        style += PUMPING_STATION_LIGHT_STYLE
    if duct_editor:
        style += DUCT_EDITOR_LIGHT_STYLE
    if hydrant_editor:
        style += HYDRANT_EDITOR_LIGHT_STYLE
    widget.setStyleSheet(style)
    QTimer.singleShot(0, lambda root=widget: _finish_light_style(root))


def apply_evel_toolbar_light_style(toolbar, menu=None) -> None:
    """Style only the EVEL-owned toolbar and menu with the fixed light theme."""

    if toolbar is not None:
        toolbar.setProperty("evelLightTheme", True)
        toolbar.setPalette(_light_palette(toolbar))
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet(EVEL_TOOLBAR_LIGHT_STYLE)
    if menu is not None:
        menu.setProperty("evelLightTheme", True)
        menu.setPalette(_light_palette(menu))
        menu.setStyleSheet(EVEL_MENU_LIGHT_STYLE)
