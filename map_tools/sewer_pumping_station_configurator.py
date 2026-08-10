"""Map-driven EVEL sewer pumping-station workflow."""

from __future__ import annotations

from collections.abc import Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QDialog
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsCsException,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgsMapTool, QgsMapToolEmitPoint

from ..layers import (
    SewerManholeContextError,
    SewerPumpingStationContext,
    SewerPumpingStationInspector,
)
from ..topology import (
    SewerManholeError,
    SewerPumpingStationReader,
    SewerPumpingStationState,
    SewerPumpingStationWriter,
)
from ..ui import SewerPumpingStationDialog


MESSAGE_TAG = "EVEL Võrgutööriistad"


class SewerPumpingStationConfiguratorController:
    """Create or edit a pumping station by clicking a sewer node or pipe."""

    def __init__(
        self,
        iface,
        action,
        finished: Callable[[], None],
        dialog_class=SewerPumpingStationDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self.dialog_class = dialog_class
        self._context: SewerPumpingStationContext | None = None
        self._tool: QgsMapToolEmitPoint | None = None
        self._previous_tool: QgsMapTool | None = None
        self._finishing = False

    @property
    def is_active(self) -> bool:
        return self._tool is not None

    def activate(self) -> bool:
        if self.is_active:
            return True
        try:
            context = SewerPumpingStationInspector().discover(
                QgsProject.instance()
            )
        except SewerManholeContextError as error:
            self._show_error(str(error))
            return False

        canvas = self.iface.mapCanvas()
        tool = QgsMapToolEmitPoint(canvas)
        tool.setAction(self.action)
        tool.canvasClicked.connect(self._canvas_clicked)
        tool.deactivated.connect(self._tool_deactivated)
        self._context = context
        self._previous_tool = canvas.mapTool()
        self._tool = tool
        canvas.setMapTool(tool)
        self.action.setChecked(True)
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            "Klõpsa reovee-, sademevee- või drenaažitorul või nende "
            "kanalisatsioonisõlmel. Avaneb eraldi pumpla parameetrite aken.",
            level=Qgis.MessageLevel.Info,
            duration=8,
        )
        return True

    def cancel(self, *_args) -> None:
        self._finish(restore_previous=True)

    def _canvas_clicked(self, canvas_point: QgsPointXY, button) -> None:
        if button != Qt.LeftButton:
            self.cancel()
            return
        context = self._context
        if context is None:
            self._show_error("Pumpla projektikihid ei ole enam saadaval.")
            self.cancel()
            return
        topology_context = context.topology_context
        try:
            point = self._to_layer_point(
                canvas_point,
                topology_context.duct_layers[0],
            )
            state = SewerPumpingStationReader(context).resolve(
                point,
                self._layer_tolerance(topology_context.duct_layers[0]),
            )
            dialog = self.dialog_class(
                state,
                context.options,
                parent=self.iface.mainWindow(),
            )
        except (SewerManholeContextError, SewerManholeError) as error:
            self._show_error(str(error))
            return
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            QgsMessageLog.logMessage(
                f"Kanalisatsioonipumpla rakendamine ebaõnnestus: {error!r}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
            self._show_error(
                "Kanalisatsioonipumpla rakendamine ebaõnnestus ootamatu "
                "vea tõttu. Üksikasjad on QGIS-i logis."
            )
            return

        while True:
            if dialog.exec() != QDialog.Accepted:
                dialog.deleteLater()
                self.cancel()
                return
            try:
                self._set_dialog_busy(
                    dialog,
                    True,
                    "Kontrollin sisestatud pumpla andmeid…",
                    10,
                )
                plan = dialog.plan()
                self._set_dialog_busy(
                    dialog,
                    True,
                    "Käivitan vajalike kihtide redigeerimise…",
                    30,
                )
                self._start_editing(context, state)
                self._set_dialog_busy(
                    dialog,
                    True,
                    "Loon või uuendan pumpla, pumpade ja toruühenduste "
                    "andmeid…",
                    60,
                )
                result = SewerPumpingStationWriter(context).write(plan)
            except (SewerManholeContextError, SewerManholeError) as error:
                self._set_dialog_busy(
                    dialog,
                    False,
                    f"Pumpla salvestamine ebaõnnestus: {error}",
                )
                self._show_error(
                    f"{error} Sisestatud andmed säilisid; paranda välju ja "
                    "proovi uuesti või vajuta „Tühista“."
                )
                continue
            except Exception as error:  # pragma: no cover - runtime guard
                QgsMessageLog.logMessage(
                    "Kanalisatsioonipumpla rakendamine ebaõnnestus: "
                    f"{error!r}",
                    MESSAGE_TAG,
                    Qgis.MessageLevel.Critical,
                )
                self._set_dialog_busy(
                    dialog,
                    False,
                    "Pumpla salvestamine ebaõnnestus ootamatu vea tõttu.",
                )
                self._show_error(
                    "Kanalisatsioonipumpla rakendamine ebaõnnestus "
                    "ootamatu vea tõttu. Sisestatud andmed säilisid ja "
                    "võid uuesti proovida. Üksikasjad on QGIS-i logis."
                )
                continue
            break

        self._set_dialog_busy(
            dialog,
            True,
            "Värskendan pumpla kihti ja kaardivaadet…",
            90,
        )
        action = "loodi" if result.created_node else "uuendati"
        split_text = " ja toru poolitati" if result.split_edge else ""
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            f"Kanalisatsioonipumpla {result.node_id} {action}{split_text}. "
            f"Pumpasid: {len(getattr(plan, 'pumps', ()))}. "
            "Muudatused lisati redigeerimispuhvrisse ja Pumplad kiht "
            "aktiveeriti.",
            level=Qgis.MessageLevel.Success,
            duration=8,
        )
        context.visible_layer.triggerRepaint()
        self.iface.setActiveLayer(context.visible_layer)
        self.iface.mapCanvas().refresh()
        self._set_dialog_busy(
            dialog,
            True,
            "Pumpla andmed ja kaardivaade on uuendatud.",
            100,
        )
        dialog.hide()
        dialog.deleteLater()
        self.cancel()

    @staticmethod
    def _set_dialog_busy(
        dialog: SewerPumpingStationDialog,
        busy: bool,
        message: str = "",
        progress: int | None = None,
    ) -> None:
        """Keep the accepted dialog visible while its plan is being written."""

        dialog.set_busy(busy, message, progress)
        if busy:
            dialog.show()
        QApplication.processEvents()

    def _start_editing(
        self,
        context: SewerPumpingStationContext,
        state: SewerPumpingStationState,
    ) -> None:
        layer_tools = self.iface.vectorLayerTools()
        if layer_tools is None:
            raise SewerManholeError(
                "QGIS-i redigeerimistööriistu ei õnnestunud avada."
            )
        topology = state.topology
        topology_context = context.topology_context
        candidates = [
            context.detail_layer,
            context.pump_layer,
            (
                topology.node_feature_layer
                if topology.node_id is not None
                else topology_context.node_layer
            ),
            topology.split_layer,
            *(
                connection.layer
                for connection in topology.endpoint_connections
            ),
            *(port.layer for port in topology.ports),
        ]
        seen: set[str] = set()
        for layer in candidates:
            if layer is None or layer.id() in seen:
                continue
            seen.add(layer.id())
            if not layer.isEditable() and not layer_tools.startEditing(layer):
                raise SewerManholeError(
                    f"Kihi „{layer.name()}“ redigeerimisrežiimi "
                    "käivitamine ebaõnnestus."
                )

    def _to_layer_point(self, point: QgsPointXY, layer) -> QgsPointXY:
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        if canvas_crs == layer.crs():
            return QgsPointXY(point)
        try:
            return QgsCoordinateTransform(
                canvas_crs,
                layer.crs(),
                QgsProject.instance(),
            ).transform(point)
        except QgsCsException as error:
            raise SewerManholeError(
                "Kaardi koordinaati ei õnnestunud torukihi CRS-i teisendada."
            ) from error

    def _layer_tolerance(self, layer) -> float:
        canvas = self.iface.mapCanvas()
        tolerance = float(QgsMapTool.searchRadiusMU(canvas))
        canvas_crs = canvas.mapSettings().destinationCrs()
        if canvas_crs == layer.crs():
            return max(tolerance, 0.001)
        center = canvas.extent().center()
        offset = QgsPointXY(center.x() + tolerance, center.y())
        try:
            transform = QgsCoordinateTransform(
                canvas_crs,
                layer.crs(),
                QgsProject.instance(),
            )
            return max(
                transform.transform(center).distance(
                    transform.transform(offset)
                ),
                0.001,
            )
        except QgsCsException:
            return 0.001

    def _tool_deactivated(self) -> None:
        self._finish(restore_previous=False)

    def _finish(self, *, restore_previous: bool) -> None:
        if self._finishing:
            return
        if self._tool is None:
            self.action.setChecked(False)
            return
        self._finishing = True
        try:
            tool = self._tool
            previous_tool = self._previous_tool
            self._tool = None
            self._previous_tool = None
            self._context = None
            try:
                tool.canvasClicked.disconnect(self._canvas_clicked)
                tool.deactivated.disconnect(self._tool_deactivated)
            except (RuntimeError, TypeError):
                pass
            canvas = self.iface.mapCanvas()
            if restore_previous and canvas.mapTool() is tool:
                if previous_tool is not None and previous_tool is not tool:
                    canvas.setMapTool(previous_tool)
                else:
                    canvas.unsetMapTool(tool)
            tool.deleteLater()
            self.action.setChecked(False)
            self.finished()
        finally:
            self._finishing = False

    def _show_error(self, message: str) -> None:
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            message,
            level=Qgis.MessageLevel.Critical,
            duration=9,
        )
