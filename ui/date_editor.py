"""Reusable EVEL date editor with a fully controlled calendar popup."""

from __future__ import annotations

from datetime import date as python_date, datetime as python_datetime
from typing import Callable

from qgis.PyQt.QtCore import QDate, QDateTime, QEvent, QLocale, QPoint, Qt
from qgis.PyQt.QtGui import QColor, QTextCharFormat
from qgis.PyQt.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QComboBox,
    QDateTimeEdit,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsVariantUtils

from .icon_catalog import (
    ICON_CONTROL_CHEVRON_LEFT,
    ICON_CONTROL_CHEVRON_RIGHT,
    ICON_FIELD_DATE,
    set_catalog_icon,
)


DATE_DISPLAY_FORMAT = "dd.MM.yyyy"


DATE_EDITOR_STYLE = """
QLineEdit#evelDateLineEdit {
    background: #ffffff;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 5px 34px 5px 8px;
    min-height: 24px;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}
QLineEdit#evelDateLineEdit:hover {
    border-color: #2188ff;
}
QLineEdit#evelDateLineEdit:focus {
    border: 2px solid #0078d4;
    padding: 4px 33px 4px 7px;
}
QLineEdit#evelDateLineEdit[invalidDate="true"] {
    border-color: #cf222e;
    background: #fff8f8;
}
QLineEdit#evelDateLineEdit:disabled {
    background: #f0f2f4;
    color: #7d8790;
}
QToolButton#evelDatePopupButton {
    background: transparent;
    border: none;
    border-left: 1px solid #e1e7ec;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    padding: 5px;
}
QToolButton#evelDatePopupButton:hover {
    background: #edf6ff;
}
QToolButton#evelDatePopupButton:pressed {
    background: #dcecf8;
}
"""


CALENDAR_POPUP_STYLE = """
QFrame#evelCalendarPopup {
    background: #ffffff;
    border: 1px solid #b8c8d6;
    border-radius: 9px;
}
QFrame#evelCalendarHeader,
QFrame#evelCalendarFooter {
    background: #f7f9fb;
    border: none;
}
QFrame#evelCalendarHeader {
    border-bottom: 1px solid #e1e7ec;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QFrame#evelCalendarFooter {
    border-top: 1px solid #e1e7ec;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}
QToolButton#evelCalendarNavButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px;
}
QToolButton#evelCalendarNavButton:hover {
    background: #e8f3ff;
    border-color: #b8d8f0;
}
QComboBox#evelCalendarMonth,
QSpinBox#evelCalendarYear {
    background: #ffffff;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    padding: 4px 7px;
    min-height: 22px;
}
QComboBox#evelCalendarMonth:hover,
QSpinBox#evelCalendarYear:hover,
QComboBox#evelCalendarMonth:focus,
QSpinBox#evelCalendarYear:focus {
    border-color: #2188ff;
}
QCalendarWidget#evelCalendar {
    background: #ffffff;
    border: none;
}
QCalendarWidget#evelCalendar QTableView {
    background: #ffffff;
    alternate-background-color: #ffffff;
    color: #334155;
    border: none;
    outline: 0;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}
QCalendarWidget#evelCalendar QTableView::item {
    border-radius: 5px;
    padding: 4px;
}
QCalendarWidget#evelCalendar QTableView::item:hover {
    background: #edf6ff;
    color: #075a9c;
}
QCalendarWidget#evelCalendar QHeaderView::section {
    background: #f7f9fb;
    color: #64748b;
    border: none;
    border-bottom: 1px solid #e7edf2;
    padding: 5px 2px;
    font-weight: 600;
}
QPushButton#evelCalendarClear,
QPushButton#evelCalendarToday {
    background: transparent;
    color: #075a9c;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 9px;
    font-weight: 600;
}
QPushButton#evelCalendarClear:hover,
QPushButton#evelCalendarToday:hover {
    background: #e8f3ff;
    border-color: #b8d8f0;
}
"""


class EvelCalendarPopup(QFrame):
    """Compact calendar with EVEL-owned navigation and footer actions."""

    def __init__(self, editor: "EvelDateEditor") -> None:
        super().__init__(editor, Qt.Popup | Qt.FramelessWindowHint)
        self.editor = editor
        self._syncing_header = False
        self.setObjectName("evelCalendarPopup")
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(CALENDAR_POPUP_STYLE)
        self.setMinimumWidth(318)

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("evelCalendarHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 7, 8, 7)
        header_layout.setSpacing(6)

        self.previous_button = self._nav_button(
            ICON_CONTROL_CHEVRON_LEFT,
            "Eelmine kuu",
            header,
        )
        self.next_button = self._nav_button(
            ICON_CONTROL_CHEVRON_RIGHT,
            "Järgmine kuu",
            header,
        )
        self.month_combo = QComboBox(header)
        self.month_combo.setObjectName("evelCalendarMonth")
        self.month_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        locale = QLocale(QLocale.Estonian, QLocale.Estonia)
        for month in range(1, 13):
            month_name = locale.monthName(month, QLocale.LongFormat)
            self.month_combo.addItem(month_name.capitalize(), month)
        self.year_spin = QSpinBox(header)
        self.year_spin.setObjectName("evelCalendarYear")
        self.year_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.year_spin.setRange(1, 9999)
        self.year_spin.setFixedWidth(68)

        header_layout.addWidget(self.previous_button)
        header_layout.addWidget(self.month_combo, 1)
        header_layout.addWidget(self.year_spin)
        header_layout.addWidget(self.next_button)
        root.addWidget(header)

        self.calendar = QCalendarWidget(self)
        self.calendar.setObjectName("evelCalendar")
        self.calendar.setLocale(locale)
        self.calendar.setNavigationBarVisible(False)
        self.calendar.setGridVisible(False)
        self.calendar.setFirstDayOfWeek(Qt.Monday)
        self.calendar.setHorizontalHeaderFormat(
            QCalendarWidget.SingleLetterDayNames
        )
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setDateEditEnabled(False)
        self.calendar.setMinimumSize(316, 224)
        self._apply_day_formats()
        root.addWidget(self.calendar)

        footer = QFrame(self)
        footer.setObjectName("evelCalendarFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 5, 8, 5)
        footer_layout.setSpacing(4)
        self.clear_button = QPushButton("Tühjenda", footer)
        self.clear_button.setObjectName("evelCalendarClear")
        self.clear_button.setVisible(editor.allow_clear)
        self.today_button = QPushButton("Täna", footer)
        self.today_button.setObjectName("evelCalendarToday")
        footer_layout.addWidget(self.clear_button)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.today_button)
        root.addWidget(footer)

        self.previous_button.clicked.connect(self.calendar.showPreviousMonth)
        self.next_button.clicked.connect(self.calendar.showNextMonth)
        self.month_combo.currentIndexChanged.connect(self._header_changed)
        self.year_spin.valueChanged.connect(self._header_changed)
        self.calendar.currentPageChanged.connect(self._page_changed)
        self.calendar.clicked.connect(self._select_date)
        self.calendar.activated.connect(self._select_date)
        self.clear_button.clicked.connect(self._clear_date)
        self.today_button.clicked.connect(self._select_today)

    @staticmethod
    def _nav_button(icon_name: str, tooltip: str, parent: QWidget) -> QToolButton:
        button = QToolButton(parent)
        button.setObjectName("evelCalendarNavButton")
        button.setToolTip(tooltip)
        button.setFixedSize(30, 30)
        set_catalog_icon(button, icon_name, size=16)
        return button

    def _apply_day_formats(self) -> None:
        weekday = QTextCharFormat()
        weekday.setForeground(QColor("#334155"))
        weekend = QTextCharFormat()
        weekend.setForeground(QColor("#b42318"))
        for day in range(1, 6):
            self.calendar.setWeekdayTextFormat(Qt.DayOfWeek(day), weekday)
        self.calendar.setWeekdayTextFormat(Qt.Saturday, weekend)
        self.calendar.setWeekdayTextFormat(Qt.Sunday, weekend)

    def open_for(self, anchor: QWidget, selected: QDate | None) -> None:
        current = selected if selected is not None and selected.isValid() else QDate.currentDate()
        self.calendar.setSelectedDate(current)
        self.calendar.setCurrentPage(current.year(), current.month())
        self._page_changed(current.year(), current.month())
        self.adjustSize()

        position = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = QApplication.screenAt(position)
        if screen is not None:
            available = screen.availableGeometry()
            popup_size = self.sizeHint()
            x = min(position.x(), available.right() - popup_size.width() + 1)
            y = position.y()
            if y + popup_size.height() > available.bottom():
                y = anchor.mapToGlobal(QPoint(0, -popup_size.height() - 4)).y()
            position = QPoint(max(available.left(), x), max(available.top(), y))
        self.move(position)
        self.show()
        self.raise_()
        self.calendar.setFocus(Qt.PopupFocusReason)

    def _page_changed(self, year: int, month: int) -> None:
        self._syncing_header = True
        try:
            self.month_combo.setCurrentIndex(max(0, month - 1))
            self.year_spin.setValue(year)
        finally:
            self._syncing_header = False

    def _header_changed(self, _value: int) -> None:
        if self._syncing_header:
            return
        month = int(self.month_combo.currentData() or 1)
        self.calendar.setCurrentPage(self.year_spin.value(), month)

    def _select_date(self, selected: QDate) -> None:
        self.editor.set_date(selected)
        self.hide()

    def _select_today(self) -> None:
        self._select_date(QDate.currentDate())

    def _clear_date(self) -> None:
        self.editor.clear_date()
        self.hide()


class EvelDateEditor(QWidget):
    """Presentation adapter around a QGIS-owned ``QDateTimeEdit``."""

    def __init__(
        self,
        source_editor,
        value_getter: Callable[[], object] | None = None,
        values_changed_signal=None,
        parent: QWidget | None = None,
        *,
        allow_clear: bool = True,
        on_date_selected: Callable[[QDate], None] | None = None,
        on_cleared: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_editor = source_editor
        self.value_getter = value_getter or self.source_editor.date
        self.allow_clear = bool(allow_clear)
        self.on_date_selected = on_date_selected
        self.on_cleared = on_cleared
        self.setObjectName("evelDateEditor")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumWidth(170)
        self.setMaximumWidth(190)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(DATE_EDITOR_STYLE)

        self.line_edit = QLineEdit(self)
        self.line_edit.setObjectName("evelDateLineEdit")
        self.line_edit.setPlaceholderText("Pole määratud")
        self.line_edit.setClearButtonEnabled(False)
        self.line_edit.setInputMethodHints(Qt.ImhDate)
        self.setFocusProxy(self.line_edit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.line_edit)

        self.calendar_button = QToolButton(self.line_edit)
        self.calendar_button.setObjectName("evelDatePopupButton")
        self.calendar_button.setToolTip("Vali kuupäev")
        self.calendar_button.setCursor(Qt.PointingHandCursor)
        set_catalog_icon(self.calendar_button, ICON_FIELD_DATE, size=16)

        self.popup = EvelCalendarPopup(self)
        self.source_editor.setCalendarPopup(False)
        self.source_editor.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.source_editor.hide()
        self.source_editor.installEventFilter(self)
        self.line_edit.installEventFilter(self)

        self.calendar_button.clicked.connect(self.show_calendar)
        self.line_edit.editingFinished.connect(self._commit_text)
        if values_changed_signal is not None:
            values_changed_signal.connect(self._source_value_changed)
        else:
            self.source_editor.dateChanged.connect(
                self._source_editor_date_changed
            )
        self.sync_value(self.value_getter())
        self._sync_enabled()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.line_edit and event.type() in {
            QEvent.Resize,
            QEvent.Show,
            QEvent.StyleChange,
        }:
            self._position_calendar_button()
        elif watched is self.source_editor and event.type() == QEvent.EnabledChange:
            self._sync_enabled()
        return False

    def _position_calendar_button(self) -> None:
        height = max(24, self.line_edit.height() - 2)
        self.calendar_button.setGeometry(
            max(0, self.line_edit.width() - 31),
            1,
            30,
            height,
        )
        self.calendar_button.raise_()

    def _sync_enabled(self) -> None:
        enabled = self.source_editor.isEnabled()
        self.line_edit.setEnabled(enabled)
        self.calendar_button.setEnabled(enabled)

    def _source_value_changed(self, value, _extra_values) -> None:
        self.sync_value(value)

    def _source_editor_date_changed(self, _selected: QDate) -> None:
        self.sync_value(self.value_getter())

    def sync_value(self, value) -> None:
        selected = self._to_qdate(value)
        text = selected.toString(DATE_DISPLAY_FORMAT) if selected is not None else ""
        if self.line_edit.text() != text:
            self.line_edit.setText(text)
        self._set_invalid(False)

    def show_calendar(self) -> None:
        selected = self._to_qdate(self.value_getter())
        self.popup.open_for(self, selected)

    def set_date(self, selected: QDate) -> None:
        if not selected.isValid():
            return
        self.source_editor.setDate(selected)
        if self.on_date_selected is not None:
            self.on_date_selected(selected)
        self.sync_value(selected)

    def clear_date(self) -> None:
        if not self.allow_clear:
            return
        self.source_editor.clear()
        if self.on_cleared is not None:
            self.on_cleared()
        self.sync_value(None)

    def has_invalid_input(self) -> bool:
        return bool(self.line_edit.property("invalidDate"))

    def _commit_text(self) -> None:
        text = self.line_edit.text().strip()
        if not text:
            self.clear_date()
            return
        selected = QDate.fromString(text, DATE_DISPLAY_FORMAT)
        if selected.isValid() and selected.toString(DATE_DISPLAY_FORMAT) == text:
            self.set_date(selected)
            return
        self._set_invalid(True)
        self.line_edit.setToolTip(
            "Sisesta kuupäev kujul pp.kk.aaaa või vali see kalendrist."
        )

    def _set_invalid(self, invalid: bool) -> None:
        self.line_edit.setProperty("invalidDate", bool(invalid))
        self.line_edit.style().unpolish(self.line_edit)
        self.line_edit.style().polish(self.line_edit)
        if not invalid:
            self.line_edit.setToolTip("")

    @staticmethod
    def _to_qdate(value) -> QDate | None:
        if value is None or QgsVariantUtils.isNull(value):
            return None
        if isinstance(value, QDateTime):
            result = value.date()
        elif isinstance(value, QDate):
            result = value
        elif isinstance(value, python_datetime):
            result = QDate(value.year, value.month, value.day)
        elif isinstance(value, python_date):
            result = QDate(value.year, value.month, value.day)
        else:
            result = QDate.fromString(str(value), Qt.ISODate)
        return result if result.isValid() else None


def evel_date_editor_for_binding(binding, parent: QWidget) -> EvelDateEditor | None:
    """Build the shared presentation for a QGIS date field binding."""

    source = binding.widget
    if not isinstance(source, QDateTimeEdit):
        source = binding.widget.findChild(QDateTimeEdit)
    if source is None:
        return None
    source.setDisplayFormat(DATE_DISPLAY_FORMAT)
    return EvelDateEditor(
        source,
        binding.value,
        binding.wrapper.valuesChanged,
        parent,
    )
