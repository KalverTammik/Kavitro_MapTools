"""Map-driven EVEL connection-point workflow."""

from __future__ import annotations

from collections.abc import Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QInputDialog
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsCsException,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgsMapTool, QgsMapToolEmitPoint

from ..layers.connection_point import (
    ConnectionPointContext,
    ConnectionPointContextError,
    ConnectionPointInspector,
)
from ..topology.connection_point import (
    ConnectionNodeCandidate,
    ConnectionPointError,
    ConnectionPointReader,
    ConnectionPointWriter,
)
from ..ui.connection_point_dialog import ConnectionPointDialog
from .editing_session import PluginEditingSession


MESSAGE_TAG = "EVEL Võrgutööriistad"


class ConnectionPointConfiguratorController:
    """Create or edit a connection point by clicking a point or node."""

    def __init__(
        self,
        iface,
        action,
        finished: Callable[[], None],
        dialog_class=ConnectionPointDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self.dialog_class = dialog_class
        self._context: ConnectionPointContext | None = None
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
            context = ConnectionPointInspector().discover(
                QgsProject.instance()
            )
        except ConnectionPointContextError as error:
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
            "Klõpsa olemasoleval liitumispunktil andmete muutmiseks või "
            "vee-/kanalisatsioonisõlmel uue liitumispunkti loomiseks.",
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
            self._show_error("Liitumispunktide projektikihid ei ole saadaval.")
            self.cancel()
            return

        edit_session = None
        dialog = None
        try:
            point = self._to_layer_point(canvas_point, context.point_layer)
            tolerance = self._layer_tolerance(context.point_layer)
            reader = ConnectionPointReader(context)
            state = reader.existing(point, tolerance)
            if state is None:
                candidates = reader.node_candidates(point, tolerance)
                candidate = self._choose_candidate(candidates)
                if candidate is None:
                    return
                state = reader.new_state(candidate)

            edit_session = PluginEditingSession((context.point_layer,))
            self._start_editing(context.point_layer)
            dialog = self.dialog_class(
                context,
                state,
                parent=self.iface.mainWindow(),
            )
            if dialog.exec() != QDialog.Accepted:
                dialog.deleteLater()
                dialog = None
                edit_session.rollback()
                self.cancel()
                return
            plan = dialog.plan()
            dialog.deleteLater()
            dialog = None
            result = ConnectionPointWriter(context).write(plan)
            commit_result = edit_session.commit()
        except (ConnectionPointContextError, ConnectionPointError) as error:
            if edit_session is not None:
                edit_session.rollback()
            self._show_error(str(error))
            return
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            if edit_session is not None:
                edit_session.rollback()
            QgsMessageLog.logMessage(
                f"Liitumispunkti rakendamine ebaõnnestus: {error!r}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
            self._show_error(
                "Liitumispunkti rakendamine ebaõnnestus ootamatu vea tõttu. "
                "Üksikasjad on QGIS-i logis."
            )
            return
        finally:
            if dialog is not None:
                dialog.deleteLater()

        if commit_result.errors:
            self._show_error(
                "Liitumispunkti salvestamine andmebaasi ebaõnnestus: "
                + "; ".join(commit_result.errors)
            )
            self.cancel()
            return
        if commit_result.left_in_existing_session:
            message = (
                f"Liitumispunkti {result.point_id} muudatused lisati "
                "olemasolevasse redigeerimispuhvrisse."
            )
            level = Qgis.MessageLevel.Warning
        else:
            action = "loodi" if result.created else "uuendati"
            message = (
                f"Liitumispunkt {result.point_id} {action}, salvestati "
                "andmebaasi ja redigeerimine lõpetati."
            )
            level = Qgis.MessageLevel.Success
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            message,
            level=level,
            duration=8,
        )
        context.point_layer.triggerRepaint()
        self.iface.setActiveLayer(context.point_layer)
        self.iface.mapCanvas().refresh()
        self.cancel()

    def _choose_candidate(
        self,
        candidates: tuple[ConnectionNodeCandidate, ...],
    ) -> ConnectionNodeCandidate | None:
        if not candidates:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Klõpsu lähedalt ei leitud liitumispunkti ega "
                "vee-/kanalisatsioonisõlme.",
                level=Qgis.MessageLevel.Warning,
                duration=6,
            )
            return None
        if len(candidates) == 1:
            return candidates[0]
        labels = [candidate.label for candidate in candidates]
        selected, accepted = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Vali võrguseos",
            "Samas kohas on mitu võimalikku võrku või sõlme:",
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        return candidates[labels.index(selected)]

    def _start_editing(self, layer) -> None:
        layer_tools = self.iface.vectorLayerTools()
        if layer_tools is None or (
            not layer.isEditable()
            and not layer_tools.startEditing(layer)
        ):
            raise ConnectionPointError(
                "Liitumispunktide kihi redigeerimisrežiimi käivitamine "
                "ebaõnnestus."
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
            raise ConnectionPointError(
                "Kaardi koordinaati ei õnnestunud liitumispunktide kihi "
                "CRS-i teisendada."
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
