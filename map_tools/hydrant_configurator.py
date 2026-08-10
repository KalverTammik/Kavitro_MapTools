"""Map-driven EVEL water hydrant workflow."""

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

from ..layers import HydrantContext, HydrantContextError, HydrantInspector
from ..topology import HydrantError, HydrantReader, HydrantWriter
from ..ui import HydrantDialog
from .editing_session import PluginEditingSession


MESSAGE_TAG = "EVEL Võrgutööriistad"


class HydrantConfiguratorController:
    """Create or edit a hydrant by clicking a water node or duct."""

    def __init__(
        self,
        iface,
        action,
        finished: Callable[[], None],
        dialog_class=HydrantDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self.dialog_class = dialog_class
        self._context: HydrantContext | None = None
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
            context = HydrantInspector().discover(QgsProject.instance())
        except HydrantContextError as error:
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
            "Klõpsa olemasoleval hüdrandil või veesõlmel, et andmeid "
            "muuta. Uue hüdrandi lisamiseks klõpsa veetorul; toru "
            "sisemuses luuakse sõlm ja toru poolitatakse.",
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
            self._show_error("Hüdrandi projektikihid ei ole enam saadaval.")
            self.cancel()
            return

        edit_session: PluginEditingSession | None = None
        dialog = None
        try:
            point = self._to_layer_point(canvas_point, context.node_layer)
            state = HydrantReader(context).resolve(
                point,
                self._layer_tolerance(context.node_layer),
            )
            layers = (
                context.node_layer,
                context.detail_layer,
                state.edge_layer,
            )
            edit_session = PluginEditingSession(layers)
            self._start_editing(layers)
            dialog = self.dialog_class(
                context,
                state,
                parent=self.iface.mainWindow(),
            )
            if dialog.exec() != QDialog.Accepted:
                dialog.deleteLater()
                edit_session.rollback()
                self.cancel()
                return
            plan = dialog.plan()
            dialog.deleteLater()
            dialog = None

            result = HydrantWriter(context).write(plan)
            commit_result = edit_session.commit()
        except (HydrantContextError, HydrantError) as error:
            if edit_session is not None:
                edit_session.rollback()
            self._show_error(str(error))
            return
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            if edit_session is not None:
                edit_session.rollback()
            QgsMessageLog.logMessage(
                f"Hüdrandi rakendamine ebaõnnestus: {error!r}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
            self._show_error(
                "Hüdrandi rakendamine ebaõnnestus ootamatu vea tõttu. "
                "Üksikasjad on QGIS-i logis."
            )
            return
        finally:
            if dialog is not None:
                dialog.deleteLater()

        if commit_result.errors:
            details = "; ".join(commit_result.errors)
            self._show_error(
                "Hüdrandi salvestamine andmebaasi ebaõnnestus. Muudatused "
                f"jäid redigeerimispuhvrisse. {details}"
            )
            self.cancel()
            return

        split_text = " ja veetoru poolitati" if result.split_edge else ""
        if commit_result.left_in_existing_session:
            message = (
                f"Hüdrandi {result.node_id} muudatused lisati olemasolevasse "
                "redigeerimispuhvrisse. Kiht oli varem juba redigeerimisel; "
                "plugin ei kinnitanud varasemaid muudatusi."
            )
            level = Qgis.MessageLevel.Warning
        else:
            action = "loodi" if result.created_node else "uuendati"
            message = (
                f"Hüdrant sõlmel {result.node_id} {action}{split_text}, "
                "salvestati andmebaasi ja redigeerimine lõpetati."
            )
            level = Qgis.MessageLevel.Success
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            message,
            level=level,
            duration=9,
        )
        context.visible_layer.triggerRepaint()
        self.iface.setActiveLayer(context.visible_layer)
        self.iface.mapCanvas().refresh()
        self.cancel()

    def _start_editing(self, layers) -> None:
        layer_tools = self.iface.vectorLayerTools()
        if layer_tools is None:
            raise HydrantError(
                "QGIS-i redigeerimistööriistu ei õnnestunud avada."
            )
        seen = set()
        for layer in layers:
            if layer is None or layer.id() in seen:
                continue
            seen.add(layer.id())
            if not layer.isEditable() and not layer_tools.startEditing(layer):
                raise HydrantError(
                    f"Kihi „{layer.name()}” redigeerimisrežiimi "
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
            raise HydrantError(
                "Kaardi koordinaati ei õnnestunud veesõlmekihi CRS-i "
                "teisendada."
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
            duration=10,
        )
