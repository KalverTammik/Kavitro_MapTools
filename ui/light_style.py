"""Permanent Kavitro-aligned light styling for EVEL tool dialogs."""

from __future__ import annotations

from qgis.PyQt.QtCore import QSize, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QComboBox, QTabWidget, QWidget

from .icon_catalog import (
    ICON_CONTROL_CHECK,
    ICON_CONTROL_CHEVRON_DOWN,
    ICON_CONTROL_CHEVRON_RIGHT,
    ICON_CONTROL_CHEVRON_UP,
    ICON_FIELD_DATE,
    icon_path,
)


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
    width: 27px;
    background: transparent;
    border: none;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}
QDialog QComboBox::drop-down:hover {
    background: #edf6ff;
}
QDialog QComboBox::down-arrow {
    image: url("__EVEL_CHEVRON_DOWN__");
    width: 11px;
    height: 11px;
}
QDialog QComboBox:on {
    background: #ffffff;
    border-color: #2188ff;
}
QDialog QSpinBox,
QDialog QDoubleSpinBox,
QDialog QDateEdit,
QDialog QDateTimeEdit {
    padding-right: 0;
}
QDialog QSpinBox::up-button,
QDialog QDoubleSpinBox::up-button,
QDialog QDateEdit::up-button,
QDialog QDateTimeEdit::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    background: #f8fafc;
    border: none;
    border-left: 1px solid #e1e7ec;
    border-bottom: 1px solid #edf1f4;
    border-top-right-radius: 5px;
}
QDialog QSpinBox::down-button,
QDialog QDoubleSpinBox::down-button,
QDialog QDateEdit::down-button,
QDialog QDateTimeEdit::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    background: #f8fafc;
    border: none;
    border-left: 1px solid #e1e7ec;
    border-top: 1px solid #edf1f4;
    border-bottom-right-radius: 5px;
}
QDialog QSpinBox::up-button:hover,
QDialog QDoubleSpinBox::up-button:hover,
QDialog QDateEdit::up-button:hover,
QDialog QDateTimeEdit::up-button:hover,
QDialog QSpinBox::down-button:hover,
QDialog QDoubleSpinBox::down-button:hover,
QDialog QDateEdit::down-button:hover,
QDialog QDateTimeEdit::down-button:hover {
    background: #edf6ff;
}
QDialog QSpinBox::up-arrow,
QDialog QDoubleSpinBox::up-arrow,
QDialog QDateEdit::up-arrow,
QDialog QDateTimeEdit::up-arrow {
    image: url("__EVEL_CHEVRON_UP__");
    width: 10px;
    height: 10px;
}
QDialog QSpinBox::down-arrow,
QDialog QDoubleSpinBox::down-arrow,
QDialog QDateEdit::down-arrow,
QDialog QDateTimeEdit::down-arrow {
    image: url("__EVEL_CHEVRON_DOWN__");
    width: 10px;
    height: 10px;
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
QDialog QLineEdit QToolButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 0;
    margin: 0;
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
}
QDialog QLineEdit QToolButton:hover {
    background: #edf6ff;
    border: none;
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
    image: url("__EVEL_CHECK__");
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
QDialog QGroupBox::indicator {
    width: 16px;
    height: 16px;
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 3px;
}
QDialog QGroupBox::indicator:checked {
    background: #0078d4;
    border-color: #005a9e;
    image: url("__EVEL_CHECK__");
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
    padding: 7px 14px;
    min-width: 90px;
    min-height: 24px;
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
    background: #f4f7f9;
    width: 9px;
    margin: 2px 1px;
    border-radius: 4px;
}
QDialog QScrollBar::handle:vertical {
    background: #a8b7c4;
    border: none;
    border-radius: 4px;
    min-height: 28px;
}
QDialog QScrollBar::handle:vertical:hover {
    background: #7f95a8;
}
QDialog QScrollBar:horizontal {
    background: #f4f7f9;
    height: 9px;
    margin: 1px 2px;
    border-radius: 4px;
}
QDialog QScrollBar::handle:horizontal {
    background: #a8b7c4;
    border: none;
    border-radius: 4px;
    min-width: 28px;
}
QDialog QScrollBar::handle:horizontal:hover {
    background: #7f95a8;
}
QDialog QScrollBar::add-line,
QDialog QScrollBar::sub-line,
QDialog QScrollBar::add-page,
QDialog QScrollBar::sub-page {
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
QDialog#evelDuctEditorDialog QWidget#ductSectionHeader,
QDialog#evelDuctEditorDialog QWidget#ductFieldRow,
QDialog#evelDuctEditorDialog QWidget#responsiveFieldGrid {
    background: transparent;
}
QDialog#evelDuctEditorDialog QLabel#ductSectionIcon,
QDialog#evelDuctEditorDialog QLabel#ductFieldIcon {
    background: transparent;
}
QDialog#evelDuctEditorDialog QFrame#ductInfoCard {
    background: #f4f8ff;
    border: 1px solid #bdd7f4;
    border-radius: 8px;
}
QDialog#evelDuctEditorDialog QLabel#ductInfoIcon {
    color: #0969da;
    font-size: 15px;
    font-weight: 700;
}
QDialog#evelDuctEditorDialog QLabel#ductInfoText {
    color: #435b78;
    font-size: 11px;
}
QDialog#evelDuctEditorDialog QLabel#ductFieldUnit {
    color: #667085;
    font-size: 11px;
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
QDialog#evelDuctEditorDialog QPushButton#ductEndpointButton {
    background: rgba(255, 255, 255, 235);
    color: #005a9e;
    border: 1px solid #9db8cc;
    border-radius: 7px;
    padding: 2px 5px;
    font-size: 11px;
    font-weight: 600;
}
QDialog#evelDuctEditorDialog QPushButton#ductEndpointButton:hover {
    background: #edf6ff;
    border-color: #0078d4;
}
QDialog#evelDuctEditorDialog QPushButton#ductEndpointButton:focus {
    border: 2px solid #0078d4;
}
QDialog#evelDuctEditorDialog QPushButton#ductEndpointButton:disabled {
    background: rgba(246, 247, 248, 235);
    color: #57606a;
    border-color: #d0d7de;
}
QDialog#evelDuctEditorDialog QPushButton#ductFlowDirectionButton {
    background: rgba(255, 255, 255, 240);
    color: #005a9e;
    border: 1px solid #9db8cc;
    border-radius: 7px;
    padding: 3px 8px;
    font-weight: 600;
}
QDialog#evelDuctEditorDialog QPushButton#ductFlowDirectionButton:hover {
    background: #edf6ff;
    border-color: #0078d4;
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
QDialog#evelDuctEditorDialog QGroupBox {
    background: #ffffff;
    border: 1px solid #dce4ea;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 6px;
}
QDialog#evelDuctEditorDialog QGroupBox::title {
    color: #334155;
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 1px 5px;
    font-weight: 600;
    background: #ffffff;
}
QDialog#evelDuctEditorDialog QGroupBox#ductAdvancedGroup::indicator {
    width: 16px;
    height: 16px;
    background: transparent;
    border: none;
}
QDialog#evelDuctEditorDialog QGroupBox#ductAdvancedGroup::indicator:unchecked {
    image: url("__EVEL_CHEVRON_RIGHT__");
}
QDialog#evelDuctEditorDialog QGroupBox#ductAdvancedGroup::indicator:checked {
    image: url("__EVEL_CHEVRON_DOWN__");
}
QDialog#evelDuctEditorDialog QDateEdit::drop-down,
QDialog#evelDuctEditorDialog QDateTimeEdit::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 28px;
    background: transparent;
    border: none;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}
QDialog#evelDuctEditorDialog QDateEdit::drop-down:hover,
QDialog#evelDuctEditorDialog QDateTimeEdit::drop-down:hover {
    background: #edf6ff;
}
QDialog#evelDuctEditorDialog QDateEdit::down-arrow,
QDialog#evelDuctEditorDialog QDateTimeEdit::down-arrow {
    image: url("__EVEL_CALENDAR__");
    width: 14px;
    height: 14px;
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

DIAGNOSTICS_LIGHT_STYLE = """
QDialog#evelDiagnosticsDialog QFrame#diagnosticsHeroFrame {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 9px;
}
QDialog#evelDiagnosticsDialog QLabel#diagnosticsTitle {
    color: #111416;
    font-size: 17px;
    font-weight: 700;
}
QDialog#evelDiagnosticsDialog QLabel#diagnosticsStatus {
    color: #57606a;
    font-weight: 600;
}
QDialog#evelDiagnosticsDialog QLabel#diagnosticsStatus[severity="error"] {
    color: #c53030;
}
QDialog#evelDiagnosticsDialog QLabel#diagnosticsStatus[severity="warning"] {
    color: #8a6100;
}
QDialog#evelDiagnosticsDialog QLabel#diagnosticsStatus[severity="success"] {
    color: #0f766e;
}
QDialog#evelDiagnosticsDialog QLabel#diagnosticsHint {
    color: #57606a;
}
QDialog#evelDiagnosticsDialog QPlainTextEdit#diagnosticsReport {
    background: #ffffff;
    color: #1f2933;
    border: 1px solid #c8d2dc;
    border-radius: 8px;
    padding: 9px;
    font-family: Consolas, "Courier New", monospace;
}
QDialog#evelDiagnosticsDialog QLabel#diagnosticsCopyFeedback {
    color: #0f766e;
    font-weight: 600;
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
    border: 1px solid #9fc5ea;
    border-radius: 5px;
    selection-background-color: #e8f3ff;
    selection-color: #075a9c;
    outline: 0;
}
QAbstractItemView::item,
QListView::item {
    min-height: 25px;
    padding: 3px 9px;
}
QScrollBar:vertical {
    background: #f4f7f9;
    width: 9px;
    margin: 2px 1px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #a8b7c4;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #7f95a8;
}
QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {
    width: 0;
    height: 0;
    background: transparent;
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
QToolBar#EVELNetworkToolsToolbar QToolButton#EVELStatusToolButton {
    background: #ffffff;
    color: #1f2933;
    border: 1px solid #c8d2dc;
    padding: 2px 7px;
    font-weight: 600;
}
QToolBar#EVELNetworkToolsToolbar QToolButton#EVELStatusToolButton:hover {
    background: #edf6ff;
    border-color: #2188ff;
}
QToolBar#EVELNetworkToolsToolbar::separator {
    background: #d0d7de;
    width: 1px;
    margin: 3px 2px;
}
"""

EVEL_MENU_LIGHT_STYLE = """
QMenu#EVELAddDuctMenu,
QMenu#EVELStatusMenu,
QMenu#EVELStatusToolsMenu {
    background: #ffffff;
    color: #24292e;
    border: 1px solid #d0d7de;
    padding: 4px;
}
QMenu#EVELAddDuctMenu::item,
QMenu#EVELStatusMenu::item,
QMenu#EVELStatusToolsMenu::item {
    background: transparent;
    color: #24292e;
    border-radius: 4px;
    padding: 6px 24px 6px 8px;
}
QMenu#EVELAddDuctMenu::item:selected,
QMenu#EVELStatusMenu::item:selected,
QMenu#EVELStatusToolsMenu::item:selected {
    background: #0078d4;
    color: #ffffff;
}
QMenu#EVELAddDuctMenu::item:disabled,
QMenu#EVELStatusMenu::item:disabled,
QMenu#EVELStatusToolsMenu::item:disabled {
    color: #7d8790;
}
QMenu#EVELAddDuctMenu::separator,
QMenu#EVELStatusMenu::separator,
QMenu#EVELStatusToolsMenu::separator {
    background: #e1e4e8;
    height: 1px;
    margin: 4px 6px;
}
"""


STYLE_ICON_TOKENS = {
    "__EVEL_CALENDAR__": ICON_FIELD_DATE,
    "__EVEL_CHECK__": ICON_CONTROL_CHECK,
    "__EVEL_CHEVRON_DOWN__": ICON_CONTROL_CHEVRON_DOWN,
    "__EVEL_CHEVRON_RIGHT__": ICON_CONTROL_CHEVRON_RIGHT,
    "__EVEL_CHEVRON_UP__": ICON_CONTROL_CHEVRON_UP,
}


def _resolve_style_icons(style: str) -> str:
    resolved = style
    for token, icon_name in STYLE_ICON_TOKENS.items():
        path = icon_path(icon_name).resolve().as_posix()
        resolved = resolved.replace(token, path)
    return resolved


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
                view.setMinimumWidth(max(combo.width(), 1))
                set_uniform = getattr(view, "setUniformItemSizes", None)
                if callable(set_uniform):
                    set_uniform(True)
                set_spacing = getattr(view, "setSpacing", None)
                if callable(set_spacing):
                    set_spacing(1)
                set_grid_size = getattr(view, "setGridSize", None)
                if callable(set_grid_size):
                    # QGIS ValueMap editors use a QListView whose native
                    # delegate can ignore QSS min-height in a combo popup.
                    # A fixed row grid keeps the popup comfortably readable
                    # without replacing QGIS' own item delegate.
                    set_grid_size(QSize(0, 28))
                popup = view.window()
                if popup is not None:
                    popup.setPalette(_light_palette(popup))
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


def configure_evel_tabs(tabs: QTabWidget) -> QTabWidget:
    """Apply the compact, icon-ready workflow tabs used by duct editors."""

    tabs.setProperty("evelWorkflowTabs", True)
    tabs.setDocumentMode(False)
    tabs.setIconSize(QSize(17, 17))
    bar = tabs.tabBar()
    bar.setDrawBase(False)
    bar.setExpanding(True)
    bar.setUsesScrollButtons(False)
    bar.setElideMode(Qt.ElideNone)
    return tabs


def apply_evel_light_style(
    widget,
    *,
    pumping_station: bool = False,
    duct_editor: bool = False,
    hydrant_editor: bool = False,
    diagnostics: bool = False,
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
    if diagnostics:
        style += DIAGNOSTICS_LIGHT_STYLE
    widget.setStyleSheet(_resolve_style_icons(style))
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
