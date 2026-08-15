"""Tests for the copyable EVEL diagnostics popup."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtWidgets import QApplication

from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.ui.diagnostics_dialog import DiagnosticsDialog
from EVEL_network_tools.ui.icon_catalog import ICON_STATUS_OK, catalog_icon


start_qgis()


class DiagnosticsDialogTest(unittest.TestCase):
    def test_report_is_read_only_selectable_and_copyable(self) -> None:
        report = (
            "EVEL VÕRGUTÖÖRIISTADE DIAGNOSTIKA\n"
            "Olek: VALMIS\n"
            "[VALMIS] Lisa toru\n"
        )
        dialog = DiagnosticsDialog(
            report,
            "EVEL on valmis",
            catalog_icon(ICON_STATUS_OK),
        )

        self.assertEqual("evelDiagnosticsDialog", dialog.objectName())
        self.assertTrue(dialog.property("evelLightTheme"))
        self.assertTrue(dialog.report_edit.isReadOnly())
        self.assertEqual(report, dialog.report)
        self.assertFalse(dialog.copy_button.icon().isNull())
        self.assertFalse(dialog.close_button.icon().isNull())
        self.assertGreaterEqual(dialog.copy_button.minimumWidth(), 122)
        self.assertEqual("EVEL on valmis", dialog.status_label.text())
        self.assertEqual("success", dialog.status_label.property("severity"))

        QApplication.clipboard().clear()
        dialog.copy_report()

        self.assertEqual(report, QApplication.clipboard().text())
        self.assertEqual(
            "Diagnostika kopeeriti lõikelauale.",
            dialog.copy_feedback.text(),
        )
        dialog.close()

    def test_open_dialog_can_receive_a_fresh_report(self) -> None:
        dialog = DiagnosticsDialog(
            "Esialgne raport",
            "EVEL vajab tähelepanu",
            catalog_icon(ICON_STATUS_OK),
        )

        dialog.set_report(
            "Uuendatud raport",
            "EVEL on valmis",
            catalog_icon(ICON_STATUS_OK),
        )

        self.assertEqual("Uuendatud raport", dialog.report)
        self.assertEqual("EVEL on valmis", dialog.status_label.text())
        self.assertEqual("success", dialog.status_label.property("severity"))
        self.assertFalse(dialog.status_icon_label.pixmap().isNull())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
