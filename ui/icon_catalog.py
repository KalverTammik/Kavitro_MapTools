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
ICON_CONTROL_CHECK = "control_check"
ICON_CONTROL_CHEVRON_DOWN = "control_chevron_down"
ICON_CONTROL_CHEVRON_LEFT = "control_chevron_left"
ICON_CONTROL_CHEVRON_RIGHT = "control_chevron_right"
ICON_CONTROL_CHEVRON_UP = "control_chevron_up"
ICON_EDIT_DUCT = "edit_duct"
ICON_ERROR = "error"
ICON_DUCT_TAB = "duct_tab"
ICON_MANAGEMENT_TAB = "management_tab"
ICON_EPANET_TAB = "epanet_tab"
ICON_FIELD_PURPOSE = "field_purpose"
ICON_FIELD_MATERIAL = "field_material"
ICON_FIELD_DIAMETER = "field_diameter"
ICON_FIELD_PRESSURE = "field_pressure"
ICON_FIELD_FIRMNESS = "field_firmness"
ICON_FIELD_INSTALLATION = "field_installation"
ICON_FIELD_CONDITION = "field_condition"
ICON_FIELD_USAGE_STATE = "field_usage_state"
ICON_FIELD_ASSET = "field_asset"
ICON_FIELD_OWNER = "field_owner"
ICON_FIELD_TENANT = "field_tenant"
ICON_FIELD_DATE = "field_date"
ICON_FIELD_SERVICE_LIFE = "field_service_life"
ICON_FIELD_SOURCE = "field_source"
ICON_FIELD_NOTE = "field_note"
ICON_FIELD_PERMIT = "field_permit"
ICON_FIELD_ADDRESS = "field_address"
ICON_FIELD_LENGTH_3D = "field_length_3d"
ICON_FIELD_HYDRAULIC_STATUS = "field_hydraulic_status"
ICON_FOLDER_OPEN = "folder_open"
ICON_HYDRANT = "hydrant"
ICON_IMPORT = "import"
ICON_HEIGHT_ACCURACY = "height_accuracy"
ICON_LENGTH_2D = "length_2d"
ICON_LOCATION_ACCURACY = "location_accuracy"
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
    ICON_CONTROL_CHECK: "control_check.svg",
    ICON_CONTROL_CHEVRON_DOWN: "control_chevron_down.svg",
    ICON_CONTROL_CHEVRON_LEFT: "control_chevron_left.svg",
    ICON_CONTROL_CHEVRON_RIGHT: "control_chevron_right.svg",
    ICON_CONTROL_CHEVRON_UP: "control_chevron_up.svg",
    ICON_EDIT_DUCT: "edit_duct.png",
    ICON_ERROR: "error.png",
    ICON_DUCT_TAB: "form_pipe.svg",
    ICON_MANAGEMENT_TAB: "form_shield.svg",
    ICON_EPANET_TAB: "form_drop.svg",
    ICON_FIELD_PURPOSE: "form_target.svg",
    ICON_FIELD_MATERIAL: "form_material.svg",
    ICON_FIELD_DIAMETER: "form_diameter.svg",
    ICON_FIELD_PRESSURE: "form_gauge.svg",
    ICON_FIELD_FIRMNESS: "form_condition.svg",
    ICON_FIELD_INSTALLATION: "form_installation.svg",
    ICON_FIELD_CONDITION: "form_condition.svg",
    ICON_FIELD_USAGE_STATE: "form_status.svg",
    ICON_FIELD_ASSET: "form_tag.svg",
    ICON_FIELD_OWNER: "form_owner.svg",
    ICON_FIELD_TENANT: "form_user.svg",
    ICON_FIELD_DATE: "form_calendar.svg",
    ICON_FIELD_SERVICE_LIFE: "form_clock.svg",
    ICON_FIELD_SOURCE: "form_layers.svg",
    ICON_FIELD_NOTE: "form_note.svg",
    ICON_FIELD_PERMIT: "form_clipboard.svg",
    ICON_FIELD_ADDRESS: "form_map_pin.svg",
    ICON_FIELD_LENGTH_3D: "form_ruler.svg",
    ICON_FIELD_HYDRAULIC_STATUS: "form_status.svg",
    ICON_FOLDER_OPEN: "folder_open.png",
    ICON_HYDRANT: "hydrant.png",
    ICON_IMPORT: "import.png",
    ICON_HEIGHT_ACCURACY: "height_accuracy.svg",
    ICON_LENGTH_2D: "length_2d.svg",
    ICON_LOCATION_ACCURACY: "location_accuracy.svg",
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
        icon.addPixmap(
            _tinted_pixmap(pixmap, checked_color),
            QIcon.Selected,
            QIcon.Off,
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
