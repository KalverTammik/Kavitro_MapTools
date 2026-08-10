"""Tests for sewer manhole controller result-layer presentation."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import QgsPointXY

from EVEL_network_tools.map_tools import SewerManholeConfiguratorController
from EVEL_network_tools.map_tools.sewer_pumping_station_configurator import (
    SewerPumpingStationConfiguratorController,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    DETAIL_KIND_CONNECTION,
    DETAIL_KIND_MANHOLE,
    SewerManholeError,
)


start_qgis()


class _PumpingStationDialog:
    def __init__(self, results, plan) -> None:
        self.results = list(results)
        self.saved_plan = plan
        self.exec_calls = 0
        self.plan_calls = 0
        self.busy_calls = []
        self.show_calls = 0
        self.hide_calls = 0
        self.delete_calls = 0

    def exec(self) -> int:
        self.exec_calls += 1
        return self.results.pop(0)

    def plan(self):
        self.plan_calls += 1
        return self.saved_plan

    def set_busy(
        self,
        busy: bool,
        message: str = "",
        progress: int | None = None,
    ) -> None:
        self.busy_calls.append((busy, message, progress))

    def show(self) -> None:
        self.show_calls += 1

    def hide(self) -> None:
        self.hide_calls += 1

    def deleteLater(self) -> None:  # noqa: N802
        self.delete_calls += 1


class SewerManholeControllerTest(unittest.TestCase):
    def test_manhole_result_activates_visible_manhole_layer(self) -> None:
        iface = MagicMock()
        manhole_layer = MagicMock()
        branch_layer = MagicMock()
        context = SimpleNamespace(
            visible_manhole_layer=manhole_layer,
            visible_branch_layer=branch_layer,
        )
        plan = SimpleNamespace(
            configuration=SimpleNamespace(
                detail_kind=DETAIL_KIND_MANHOLE,
            )
        )
        controller = SewerManholeConfiguratorController(
            iface,
            MagicMock(),
            MagicMock(),
        )

        controller._present_result(context, plan)

        manhole_layer.triggerRepaint.assert_called_once_with()
        branch_layer.triggerRepaint.assert_not_called()
        iface.setActiveLayer.assert_called_once_with(manhole_layer)
        iface.mapCanvas.return_value.refresh.assert_called_once_with()

    def test_connection_result_activates_visible_branch_layer(self) -> None:
        iface = MagicMock()
        manhole_layer = MagicMock()
        branch_layer = MagicMock()
        context = SimpleNamespace(
            visible_manhole_layer=manhole_layer,
            visible_branch_layer=branch_layer,
        )
        plan = SimpleNamespace(
            configuration=SimpleNamespace(
                detail_kind=DETAIL_KIND_CONNECTION,
            )
        )
        controller = SewerManholeConfiguratorController(
            iface,
            MagicMock(),
            MagicMock(),
        )

        controller._present_result(context, plan)

        manhole_layer.triggerRepaint.assert_not_called()
        branch_layer.triggerRepaint.assert_called_once_with()
        iface.setActiveLayer.assert_called_once_with(branch_layer)
        iface.mapCanvas.return_value.refresh.assert_called_once_with()


class SewerPumpingStationControllerTest(unittest.TestCase):
    def _controller_context(self, dialog):
        iface = MagicMock()
        action = MagicMock()
        finished = MagicMock()
        layer = MagicMock()
        context = SimpleNamespace(
            topology_context=SimpleNamespace(duct_layers=[layer]),
            options=SimpleNamespace(),
            visible_layer=MagicMock(),
        )
        state = SimpleNamespace(topology=SimpleNamespace())
        controller = SewerPumpingStationConfiguratorController(
            iface,
            action,
            finished,
            dialog_class=lambda *_args, **_kwargs: dialog,
        )
        controller._context = context
        controller._to_layer_point = MagicMock(
            return_value=QgsPointXY(1, 2)
        )
        controller._layer_tolerance = MagicMock(return_value=0.1)
        return controller, context, state, iface

    @patch(
        "EVEL_network_tools.map_tools.sewer_pumping_station_configurator."
        "SewerPumpingStationWriter"
    )
    @patch(
        "EVEL_network_tools.map_tools.sewer_pumping_station_configurator."
        "SewerPumpingStationReader"
    )
    def test_writer_error_keeps_same_dialog_for_retry_or_cancel(
        self,
        reader_class,
        writer_class,
    ) -> None:
        plan = object()
        dialog = _PumpingStationDialog(
            [QDialog.Accepted, QDialog.Rejected],
            plan,
        )
        controller, context, state, _iface = self._controller_context(dialog)
        reader_class.return_value.resolve.return_value = state
        writer_class.return_value.write.side_effect = SewerManholeError(
            "Andmebaasi kirjutamine ebaõnnestus."
        )
        controller._start_editing = MagicMock()

        controller._canvas_clicked(QgsPointXY(1, 2), Qt.LeftButton)

        reader_class.assert_called_once_with(context)
        self.assertEqual(2, dialog.exec_calls)
        self.assertEqual(1, dialog.plan_calls)
        self.assertEqual(1, dialog.delete_calls)
        self.assertEqual(0, dialog.hide_calls)
        writer_class.return_value.write.assert_called_once_with(plan)
        self.assertEqual(
            [
                (True, "Kontrollin sisestatud pumpla andmeid…", 10),
                (True, "Käivitan vajalike kihtide redigeerimise…", 30),
                (
                    True,
                    "Loon või uuendan pumpla, pumpade ja toruühenduste "
                    "andmeid…",
                    60,
                ),
                (
                    False,
                    "Pumpla salvestamine ebaõnnestus: "
                    "Andmebaasi kirjutamine ebaõnnestus.",
                    None,
                ),
            ],
            dialog.busy_calls,
        )

    @patch(
        "EVEL_network_tools.map_tools.sewer_pumping_station_configurator."
        "SewerPumpingStationWriter"
    )
    @patch(
        "EVEL_network_tools.map_tools.sewer_pumping_station_configurator."
        "SewerPumpingStationReader"
    )
    def test_editing_error_can_retry_and_dialog_closes_after_success(
        self,
        reader_class,
        writer_class,
    ) -> None:
        plan = object()
        dialog = _PumpingStationDialog(
            [QDialog.Accepted, QDialog.Accepted],
            plan,
        )
        controller, context, state, iface = self._controller_context(dialog)
        reader_class.return_value.resolve.return_value = state
        controller._start_editing = MagicMock(
            side_effect=[
                SewerManholeError(
                    "Kihi redigeerimisrežiimi käivitamine ebaõnnestus."
                ),
                None,
            ]
        )
        writer_class.return_value.write.return_value = SimpleNamespace(
            node_id=44,
            created_node=False,
            split_edge=False,
        )

        controller._canvas_clicked(QgsPointXY(1, 2), Qt.LeftButton)

        self.assertEqual(2, dialog.exec_calls)
        self.assertEqual(2, dialog.plan_calls)
        writer_class.return_value.write.assert_called_once_with(plan)
        self.assertEqual(1, dialog.hide_calls)
        self.assertEqual(1, dialog.delete_calls)
        self.assertEqual(
            (
                False,
                "Pumpla salvestamine ebaõnnestus: "
                "Kihi redigeerimisrežiimi käivitamine ebaõnnestus.",
                None,
            ),
            dialog.busy_calls[2],
        )
        self.assertEqual(
            (
                True,
                "Pumpla andmed ja kaardivaade on uuendatud.",
                100,
            ),
            dialog.busy_calls[-1],
        )
        context.visible_layer.triggerRepaint.assert_called_once_with()
        iface.setActiveLayer.assert_called_once_with(context.visible_layer)
        iface.mapCanvas.return_value.refresh.assert_called_once_with()
