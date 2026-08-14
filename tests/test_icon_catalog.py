"""Tests for the file-based, UI-only EVEL icon catalogue."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QIcon, qAlpha
from qgis.PyQt.QtWidgets import QDialogButtonBox

from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.ui.icon_catalog import (
    ICON_ADD_DUCT,
    ICON_CONFIGURE_NODE,
    ICON_FILES,
    ICON_REVERSE_FLOW,
    ICON_SAVE,
    ICON_STATUS_WARNING,
    ICONS_DIRECTORY,
    apply_standard_button_icons,
    available_icon_names,
    catalog_icon,
    icon_path,
    is_available,
)


start_qgis()


class IconCatalogTest(unittest.TestCase):
    def test_catalog_contains_one_existing_png_per_semantic_name(self) -> None:
        self.assertTrue(ICONS_DIRECTORY.is_dir())
        self.assertTrue(is_available())
        self.assertEqual(set(ICON_FILES), set(available_icon_names()))

        for name, filename in ICON_FILES.items():
            with self.subTest(name=name):
                path = icon_path(name)
                self.assertEqual(filename, path.name)
                self.assertEqual(".png", path.suffix.lower())
                self.assertTrue(path.is_file())
                self.assertEqual(
                    b"\x89PNG\r\n\x1a\n",
                    path.read_bytes()[:8],
                )
                self.assertGreater(path.stat().st_size, 300)

    def test_png_renders_as_a_visible_multistate_icon(self) -> None:
        for name in available_icon_names():
            icon = catalog_icon(name)
            self.assertFalse(icon.isNull(), name)
            for size in (18, 20, 24):
                with self.subTest(name=name, size=size):
                    image = icon.pixmap(
                        QSize(size, size), QIcon.Normal, QIcon.Off
                    ).toImage()
                    visible_pixels = sum(
                        qAlpha(image.pixel(x, y)) > 0
                        for y in range(image.height())
                        for x in range(image.width())
                    )
                    self.assertGreater(visible_pixels, 20)

        icon = catalog_icon(ICON_SAVE)
        checked = icon.pixmap(
            QSize(24, 24),
            QIcon.Normal,
            QIcon.On,
        ).toImage()
        self.assertGreater(
            sum(
                qAlpha(checked.pixel(x, y)) > 0
                for y in range(checked.height())
                for x in range(checked.width())
            ),
            20,
        )

    def test_main_actions_have_independent_semantic_variables(self) -> None:
        names = available_icon_names()
        self.assertIn(ICON_ADD_DUCT, names)
        self.assertIn(ICON_CONFIGURE_NODE, names)
        self.assertIn(ICON_REVERSE_FLOW, names)
        self.assertIn(ICON_STATUS_WARNING, names)
        self.assertEqual("save.png", ICON_FILES[ICON_SAVE])
        with self.assertRaisesRegex(ValueError, "Unknown EVEL icon"):
            catalog_icon("map_layer_symbol")

    def test_standard_dialog_buttons_receive_shared_icons(self) -> None:
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        apply_standard_button_icons(buttons)

        self.assertFalse(buttons.button(QDialogButtonBox.Save).icon().isNull())
        self.assertFalse(
            buttons.button(QDialogButtonBox.Cancel).icon().isNull()
        )


if __name__ == "__main__":
    unittest.main()
