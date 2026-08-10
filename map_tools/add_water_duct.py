"""Interactive one-shot map workflow for adding an EVEL water duct."""

from __future__ import annotations

from collections.abc import Callable

from qgis.PyQt.QtWidgets import QDialog
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeature,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgsMapTool, QgsMapToolCapture, QgsMapToolDigitizeFeature

from ..layers import ProjectInspection
from ..ui import (
    DuctEditorDialog,
    DuctEditorProfile,
    GuidedFeatureEditorError,
)
from ..topology import (
    EndpointResolutionError,
    WaterDuctWriteCanceled,
    WaterDuctWriteError,
    WaterDuctWriter,
    WaterEndpointResolver,
)
from .editing_session import EditingSessionResult, PluginEditingSession


MESSAGE_TAG = "EVEL Võrgutööriistad"


class AddWaterDuctController:
    """Coordinate capture, endpoint planning and the configured QGIS form."""

    def __init__(
        self,
        iface,
        action,
        finished: Callable[[], None],
        *,
        form_opener: Callable[[object, QgsFeature], bool] | None = None,
        dialog_class=DuctEditorDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self._form_opener = form_opener
        self._dialog_class = dialog_class
        self._inspection: ProjectInspection | None = None
        self._tool: QgsMapToolDigitizeFeature | None = None
        self._previous_tool: QgsMapTool | None = None
        self._edit_session: PluginEditingSession | None = None
        self._finishing = False

    @property
    def is_active(self) -> bool:
        return self._tool is not None

    def activate(self, inspection: ProjectInspection) -> bool:
        """Start line capture after putting both topology layers in edit mode."""

        if self.is_active:
            return True
        if not inspection.can_add_water_duct:
            return False

        edge_layer = inspection.edge_layer
        node_layer = inspection.node_layer
        if edge_layer is None or node_layer is None:
            return False
        self._edit_session = PluginEditingSession(
            (node_layer, edge_layer)
        )

        layer_tools = self.iface.vectorLayerTools()
        if layer_tools is None:
            self._rollback_owned_session()
            self._show_error("QGIS-i redigeerimistööriistu ei õnnestunud avada.")
            return False

        if not edge_layer.isEditable() and not layer_tools.startEditing(edge_layer):
            self._rollback_owned_session()
            self._show_error(
                f"Torukihi „{edge_layer.name()}“ redigeerimisrežiimi "
                "käivitamine ebaõnnestus."
            )
            return False
        if not node_layer.isEditable() and not layer_tools.startEditing(node_layer):
            self._rollback_owned_session()
            self._show_error(
                f"Sõlmekihi „{node_layer.name()}“ redigeerimisrežiimi "
                "käivitamine ebaõnnestus."
            )
            return False

        canvas = self.iface.mapCanvas()
        tool = QgsMapToolDigitizeFeature(
            canvas,
            self.iface.cadDockWidget(),
            QgsMapToolCapture.CaptureLine,
        )
        tool.setLayer(edge_layer)
        tool.setAction(self.action)
        tool.digitizingCompleted.connect(self._digitizing_completed)
        tool.digitizingCanceled.connect(self.cancel)
        tool.deactivated.connect(self._tool_deactivated)

        self._inspection = inspection
        self._previous_tool = canvas.mapTool()
        self._tool = tool
        canvas.setMapTool(tool)
        self.action.setChecked(True)
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            "Joonesta veetoru kaardil. Lõpetamiseks tee paremklõps.",
            level=Qgis.MessageLevel.Info,
            duration=5,
        )
        return True

    def cancel(self, *_args) -> None:
        """Stop the one-shot workflow and restore the preceding map tool."""

        self._finish(restore_previous=True)

    def _digitizing_completed(self, captured: QgsFeature) -> None:
        inspection = self._inspection
        if inspection is None:
            self._show_error("Toru lisamise töövoo kihid ei ole enam saadaval.")
            self.cancel()
            return

        edge_layer = inspection.edge_layer
        node_layer = inspection.node_layer
        if edge_layer is None or node_layer is None:
            self._show_error("Toru- või sõlmekiht ei ole enam saadaval.")
            self.cancel()
            return

        try:
            plan = WaterEndpointResolver(
                edge_layer,
                node_layer,
                self._layer_tolerance(edge_layer),
            ).resolve(captured.geometry())
            result = WaterDuctWriter(edge_layer, node_layer).write(
                plan,
                network_id=self._positive_property(
                    edge_layer, "evel_topology_node_network_id"
                ),
                nettype_id=self._positive_property(
                    edge_layer, "evel_topology_node_nettype_id"
                ),
                open_form=self._open_feature_form,
            )
        except WaterDuctWriteCanceled as error:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                str(error),
                level=Qgis.MessageLevel.Info,
                duration=5,
            )
            self.cancel()
            return
        except (
            EndpointResolutionError,
            GuidedFeatureEditorError,
            WaterDuctWriteError,
        ) as error:
            self._show_error(str(error))
            return
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            QgsMessageLog.logMessage(
                f"Toru lisamine ebaõnnestus: {error!r}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
            self._show_error(
                "Toru lisamine ebaõnnestus ootamatu vea tõttu. "
                "Üksikasjad on QGIS-i logis."
            )
            return

        commit_result = self._commit_owned_session()
        if commit_result.errors:
            self._show_error(
                "Veetoru loodi, kuid andmebaasi salvestamine ebaõnnestus. "
                "Muudatused jäid redigeerimispuhvrisse: "
                + "; ".join(commit_result.errors)
            )
        elif commit_result.left_in_existing_session:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Veetoru muudatused jäid redigeerimispuhvrisse, sest "
                "kiht oli redigeerimisel juba enne tööriista käivitamist.",
                level=Qgis.MessageLevel.Warning,
                duration=8,
            )
        else:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Veetoru salvestati andmebaasi ja redigeerimine lõpetati "
                f"(sõlmed {result.begin_node_id} → {result.end_node_id}).",
                level=Qgis.MessageLevel.Success,
                duration=7,
            )
        self.cancel()

    def _open_feature_form(self, layer, feature: QgsFeature) -> bool:
        if self._form_opener is not None:
            return bool(self._form_opener(layer, feature))
        parent = (
            self.iface.mainWindow()
            if hasattr(self.iface, "mainWindow")
            else None
        )
        dialog = self._dialog_class(
            layer,
            feature,
            DuctEditorProfile.WATER,
            parent,
        )
        return dialog.exec_() == QDialog.Accepted

    def _layer_tolerance(self, edge_layer) -> float:
        canvas = self.iface.mapCanvas()
        tolerance = float(QgsMapTool.searchRadiusMU(canvas))
        canvas_crs = canvas.mapSettings().destinationCrs()
        if canvas_crs == edge_layer.crs():
            return max(tolerance, 0.001)

        center = canvas.extent().center()
        offset = QgsPointXY(center.x() + tolerance, center.y())
        try:
            transform = QgsCoordinateTransform(
                canvas_crs, edge_layer.crs(), QgsProject.instance()
            )
            transformed_center = transform.transform(center)
            transformed_offset = transform.transform(offset)
            return max(transformed_center.distance(transformed_offset), 0.001)
        except QgsCsException:
            return 0.001

    @staticmethod
    def _positive_property(layer, key: str) -> int:
        value = int(layer.customProperty(key, ""))
        if value <= 0:
            raise WaterDuctWriteError(
                f"Torukihi tehniline omadus {key} ei ole kehtiv."
            )
        return value

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
            self._rollback_owned_session()
            tool = self._tool
            previous_tool = self._previous_tool
            self._tool = None
            self._previous_tool = None
            self._inspection = None

            if tool is not None:
                self._disconnect_tool(tool)
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

    def _commit_owned_session(self):
        session = self._edit_session
        self._edit_session = None
        if session is None:
            return EditingSessionResult(committed=True)
        return session.commit()

    def _rollback_owned_session(self) -> None:
        session = self._edit_session
        self._edit_session = None
        if session is not None:
            session.rollback()

    def _disconnect_tool(self, tool: QgsMapToolDigitizeFeature) -> None:
        for signal, slot in (
            (tool.digitizingCompleted, self._digitizing_completed),
            (tool.digitizingCanceled, self.cancel),
            (tool.deactivated, self._tool_deactivated),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _show_error(self, message: str) -> None:
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            message,
            level=Qgis.MessageLevel.Critical,
            duration=8,
        )
