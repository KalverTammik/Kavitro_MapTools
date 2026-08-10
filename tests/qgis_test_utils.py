"""Shared QGIS application bootstrap for unit and integration tests."""

from qgis.core import QgsApplication
from qgis.gui import QgsGui


_APP = None


def start_qgis() -> QgsApplication:
    """Return one initialized, headless QGIS application for this process."""

    global _APP
    if QgsApplication.instance() is not None:
        app = QgsApplication.instance()
        _init_editors()
        return app
    if _APP is None:
        _APP = QgsApplication([], False)
        _APP.initQgis()
    _init_editors()
    return _APP


def _init_editors() -> None:
    registry = QgsGui.editorWidgetRegistry()
    if not registry.factories():
        registry.initEditors()
