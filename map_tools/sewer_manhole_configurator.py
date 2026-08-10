"""Map-driven EVEL sewer manhole clock workflow."""

from __future__ import annotations

from collections.abc import Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog
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
    SewerManholeContext,
    SewerManholeContextError,
    SewerManholeInspector,
)
from ..topology import (
    DETAIL_KIND_CONNECTION,
    DETAIL_KIND_MANHOLE,
    SewerManholeError,
    SewerManholeReader,
    SewerManholeState,
    SewerManholeWriter,
)
from ..ui import SewerManholeClockDialog


MESSAGE_TAG = "EVEL Võrgutööriistad"


class SewerManholeConfiguratorController:
    """Create or edit a sewer manhole by clicking a node or gravity duct."""

    def __init__(
        self,
        iface,
        action,
        finished: Callable[[], None],
        dialog_class=SewerManholeClockDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self.dialog_class = dialog_class
        self._context: SewerManholeContext | None = None
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
            context = SewerManholeInspector().discover(QgsProject.instance())
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
            "Klõpsa kanalisatsioonisõlmel või isevoolsel torul. "
            "Sõlmpunkti toruotsad koondatakse üheks tervikuks. Toru "
            "lõigul või murdepunktil klõpsates jagatakse toru ning saad "
            "valida kaevu või põlve/ühenduskoha.",
            level=Qgis.MessageLevel.Info,
            duration=9,
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
            self._show_error(
                "Kanalisatsioonisõlme projektikihid ei ole enam saadaval."
            )
            self.cancel()
            return
        try:
            point = self._to_layer_point(
                canvas_point,
                context.duct_layers[0],
            )
            state = SewerManholeReader(context).resolve(
                point,
                self._layer_tolerance(context.duct_layers[0]),
            )
            if state.pumping_station_detail_feature_id is not None:
                raise SewerManholeError(
                    "Valitud sõlm on kanalisatsioonipumpla. Selle muutmiseks "
                    "kasuta eraldi „Pumpla” tööriista."
                )
            dialog = self.dialog_class(
                state,
                context.options,
                parent=self.iface.mainWindow(),
            )
            if dialog.exec() != QDialog.Accepted:
                dialog.deleteLater()
                self.cancel()
                return
            plan = dialog.plan()
            dialog.deleteLater()
            self._start_editing(context, state)
            result = SewerManholeWriter(context).write(plan)
        except (SewerManholeContextError, SewerManholeError) as error:
            self._show_error(str(error))
            return
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            QgsMessageLog.logMessage(
                f"Kanalisatsioonisõlme rakendamine ebaõnnestus: {error!r}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
            self._show_error(
                "Kanalisatsioonisõlme rakendamine ebaõnnestus ootamatu "
                "vea tõttu. Üksikasjad on QGIS-i logis."
            )
            return

        action = "loodi" if result.created_node else "uuendati"
        split_text = " ja toru poolitati" if result.split_edge else ""
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            f"Kanalisatsioonisõlm {result.node_id} {action}{split_text}. "
            "Muudatused lisati redigeerimispuhvrisse ja tulemuskiht "
            "aktiveeriti.",
            level=Qgis.MessageLevel.Success,
            duration=8,
        )
        self.cancel()
        self._present_result(context, plan)

    def _present_result(
        self,
        context: SewerManholeContext,
        plan,
    ) -> None:
        """Activate and repaint the visible layer matching the created detail."""

        detail_kind = plan.configuration.detail_kind
        if detail_kind == DETAIL_KIND_MANHOLE:
            result_layer = context.visible_manhole_layer
        elif detail_kind == DETAIL_KIND_CONNECTION:
            result_layer = context.visible_branch_layer
        else:  # guarded by the writer; keep the UI helper defensive
            result_layer = None

        if result_layer is not None:
            result_layer.triggerRepaint()
            self.iface.setActiveLayer(result_layer)
        self.iface.mapCanvas().refresh()

    def _start_editing(
        self,
        context: SewerManholeContext,
        state: SewerManholeState,
    ) -> None:
        layer_tools = self.iface.vectorLayerTools()
        if layer_tools is None:
            raise SewerManholeError(
                "QGIS-i redigeerimistööriistu ei õnnestunud avada."
            )
        candidates = [
            context.manhole_layer,
            context.branch_layer,
            (
                state.node_feature_layer
                if state.node_id is not None
                else context.node_layer
            ),
            state.split_layer,
            *(
                connection.layer
                for connection in state.endpoint_connections
            ),
            *(port.layer for port in state.ports),
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
