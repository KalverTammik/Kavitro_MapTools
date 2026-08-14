"""File-based semantic icon catalogue for EVEL user-interface controls.

Every public ``ICON_*`` constant identifies one user-interface meaning.  The
``ICON_FILES`` mapping is the single place where that meaning is assigned to
an image file under ``resources/icons/actions``.  Replacing a shared file such
as ``save.png`` therefore updates every place that uses ``ICON_SAVE``.

This module is deliberately UI-only.  Map layers and their renderers continue
to use the QGIS project's existing symbology.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import QDialogButtonBox


ICON_ADD = "add"
ICON_ADD_DUCT = "add_duct"
ICON_BACK = "back"
ICON_CANCEL = "cancel"
ICON_CHECK = "check"
ICON_CHECK_NETWORK = "check_network"
ICON_CLEAR_DATA = "clear_data"
ICON_CLOSE = "close"
ICON_CONFIGURE = "configure"
ICON_CONFIGURE_NODE = "configure_node"
ICON_CONNECTION_POINT = "connection_point"
ICON_COORDINATE_DUCT = "coordinate_duct"
ICON_COPY = "copy"
ICON_EDIT_DUCT = "edit_duct"
ICON_ERROR = "error"
ICON_FOLDER_OPEN = "folder_open"
ICON_HYDRANT = "hydrant"
ICON_IMPORT = "import"
ICON_NEXT = "next"
ICON_PASTE = "paste"
ICON_PREVIEW_HIDE = "preview_hide"
ICON_PREVIEW_SHOW = "preview_show"
ICON_PUMPING_STATION = "pumping_station"
ICON_REFRESH = "refresh"
ICON_REMOVE = "remove"
ICON_REPAIR_NETWORK = "repair_network"
ICON_REVERSE_FLOW = "reverse_flow"
ICON_SAVE = "save"
ICON_SEWER_MANHOLE = "sewer_manhole"
ICON_STATUS_OK = "status_ok"
ICON_STATUS_WARNING = "status_warning"


ICONS_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "resources" / "icons" / "actions"
)

# Keep filenames explicit even though they currently match their semantic
# names.  This is the one list to edit when an action should use another file.
ICON_FILES = {
    ICON_ADD: "add.png",
    ICON_ADD_DUCT: "add_duct.png",
    ICON_BACK: "back.png",
    ICON_CANCEL: "cancel.png",
    ICON_CHECK: "check.png",
    ICON_CHECK_NETWORK: "check_network.png",
    ICON_CLEAR_DATA: "clear_data.png",
    ICON_CLOSE: "close.png",
    ICON_CONFIGURE: "configure.png",
    ICON_CONFIGURE_NODE: "configure_node.png",
    ICON_CONNECTION_POINT: "connection_point.png",
    ICON_COORDINATE_DUCT: "coordinate_duct.png",
    ICON_COPY: "copy.png",
    ICON_EDIT_DUCT: "edit_duct.png",
    ICON_ERROR: "error.png",
    ICON_FOLDER_OPEN: "folder_open.png",
    ICON_HYDRANT: "hydrant.png",
    ICON_IMPORT: "import.png",
    ICON_NEXT: "next.png",
    ICON_PASTE: "paste.png",
    ICON_PREVIEW_HIDE: "preview_hide.png",
    ICON_PREVIEW_SHOW: "preview_show.png",
    ICON_PUMPING_STATION: "pumping_station.png",
    ICON_REFRESH: "refresh.png",
    ICON_REMOVE: "remove.png",
    ICON_REPAIR_NETWORK: "repair_network.png",
    ICON_REVERSE_FLOW: "reverse_flow.png",
    ICON_SAVE: "save.png",
    ICON_SEWER_MANHOLE: "sewer_manhole.png",
    ICON_STATUS_OK: "status_ok.png",
    ICON_STATUS_WARNING: "status_warning.png",
}

CHECKED_ICON_COLOR = "#ffffff"
_RENDER_SIZES = (16, 20, 24, 32, 48)


def available_icon_names() -> tuple[str, ...]:
    """Return stable semantic names supported by the icon catalogue."""

    return tuple(sorted(ICON_FILES))


def icon_path(name: str) -> Path:
    """Return the configured image path for one semantic icon name."""

    try:
        filename = ICON_FILES[name]
    except KeyError as error:
        raise ValueError(f"Unknown EVEL icon name: {name}") from error
    return ICONS_DIRECTORY / filename


def is_available(name: str | None = None) -> bool:
    """Return whether one icon, or the complete catalogue, exists on disk."""

    if name is not None:
        return icon_path(name).is_file()
    return all(icon_path(icon_name).is_file() for icon_name in ICON_FILES)


def _tinted_pixmap(pixmap: QPixmap, color: str) -> QPixmap:
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return tinted


@lru_cache(maxsize=128)
def catalog_icon(
    name: str,
    checked_color: str = CHECKED_ICON_COLOR,
) -> QIcon:
    """Load a multi-size icon from the image assigned to ``name``."""

    path = icon_path(name)
    if not path.is_file():
        return QIcon()

    source = QIcon(str(path))
    if source.isNull():
        return QIcon()

    icon = QIcon()
    for size in _RENDER_SIZES:
        pixmap = source.pixmap(QSize(size, size), QIcon.Normal, QIcon.Off)
        icon.addPixmap(pixmap, QIcon.Normal, QIcon.Off)
        icon.addPixmap(
            _tinted_pixmap(pixmap, checked_color),
            QIcon.Normal,
            QIcon.On,
        )
    return icon


def set_catalog_icon(target, name: str, *, size: int = 18) -> bool:
    """Set a catalogue icon on a QAction or button."""

    icon = catalog_icon(name)
    target.setIcon(icon)
    if hasattr(target, "setIconSize"):
        target.setIconSize(QSize(size, size))
    return not icon.isNull()


def apply_standard_button_icons(buttons: QDialogButtonBox) -> None:
    """Apply shared save and cancel icons to a standard button box."""

    save_button = buttons.button(QDialogButtonBox.Save)
    if save_button is not None:
        set_catalog_icon(save_button, ICON_SAVE)
    cancel_button = buttons.button(QDialogButtonBox.Cancel)
    if cancel_button is not None:
        set_catalog_icon(cancel_button, ICON_CANCEL)
