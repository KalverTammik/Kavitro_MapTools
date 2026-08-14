"""Interactive one-shot map workflow for adding an EVEL gravity duct."""

from __future__ import annotations

from collections.abc import Callable

from qgis.PyQt.QtWidgets import QDialog
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsMessageLog,
    QgsVectorLayer,
)
from qgis.gui import QgsMapTool, QgsMapToolCapture, QgsMapToolDigitizeFeature

from ..topology import (
    GravityDuctWriteCanceled,
    GravityDuctWriteError,
    GravityDuctWriter,
)
from ..ui import (
    DuctEditorDialog,
    DuctEditorProfile,
    GuidedFeatureEditorError,
)
from .editing_session import EditingSessionResult, PluginEditingSession


MESSAGE_TAG = "EVEL Võrgutööriistad"


class AddGravityDuctController:
    """Coordinate line capture and the configured sewer-duct form."""

    def __init__(
        self,
        iface,
        action,
        finished: Callable[[], None],
        *,
        form_opener: Callable[
            [QgsVectorLayer, QgsFeature],
            bool,
        ]
        | None = None,
        dialog_class=DuctEditorDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self._form_opener = form_opener
        self._dialog_class = dialog_class
        self._layer: QgsVectorLayer | None = None
        self._tool: QgsMapToolDigitizeFeature | None = None
        self._previous_tool: QgsMapTool | None = None
        self._edit_session: PluginEditingSession | None = None
        self._finishing = False

    @property
    def is_active(self) -> bool:
        return self._tool is not None

    def activate(self, layer: QgsVectorLayer) -> bool:
        """Start line capture on the selected gravity-duct layer."""

        if self.is_active and self._layer is layer:
            return True
        if self.is_active:
            self.cancel()

        if not self._start_editing(layer):
            return False

        canvas = self.iface.mapCanvas()
        tool = QgsMapToolDigitizeFeature(
            canvas,
            self.iface.cadDockWidget(),
            QgsMapToolCapture.CaptureLine,
        )
        tool.setLayer(layer)
        tool.setAction(self.action)
        tool.digitizingCompleted.connect(self._digitizing_completed)
        tool.digitizingCanceled.connect(self.cancel)
        tool.deactivated.connect(self._tool_deactivated)

        self._layer = layer
        self._previous_tool = canvas.mapTool()
        self._tool = tool
        canvas.setMapTool(tool)
        self.action.setChecked(True)
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            f"Joonesta „{layer.name()}“ toru kaardil. "
            "Lõpetamiseks tee paremklõps.",
            level=Qgis.MessageLevel.Info,
            duration=5,
        )
        return True

    def add_geometry(
        self,
        layer: QgsVectorLayer,
        geometry: QgsGeometry,
    ) -> bool:
        """Create one gravity duct from an already constructed geometry."""

        if self.is_active:
            self.cancel()
        if not self._start_editing(layer):
            return False

        self._layer = layer
        try:
            outcome = self._write_geometry(geometry)
            return outcome == "success"
        finally:
            self._rollback_owned_session()
            self._layer = None
            self.action.setChecked(False)
            self.finished()

    def cancel(self, *_args) -> None:
        """Stop the one-shot workflow and restore the preceding map tool."""

        self._finish(restore_previous=True)

    def _digitizing_completed(self, captured: QgsFeature) -> None:
        layer = self._layer
        if layer is None:
            self._show_error("Isevoolse toru kiht ei ole enam saadaval.")
            self.cancel()
            return

        outcome = self._write_geometry(captured.geometry())
        if outcome in {"success", "canceled"}:
            self.cancel()

    def _write_geometry(self, geometry: QgsGeometry) -> str:
        layer = self._layer
        if layer is None:
            self._show_error("Isevoolse toru kiht ei ole enam saadaval.")
            return "error"

        try:
            result = GravityDuctWriter(layer).write(
                geometry,
                open_form=self._open_feature_form,
            )
        except GravityDuctWriteCanceled as error:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                str(error),
                level=Qgis.MessageLevel.Info,
                duration=5,
            )
            return "canceled"
        except (GravityDuctWriteError, GuidedFeatureEditorError) as error:
            self._show_error(str(error))
            return "error"
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            QgsMessageLog.logMessage(
                f"Isevoolse toru lisamine ebaõnnestus: {error!r}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
            self._show_error(
                "Isevoolse toru lisamine ebaõnnestus ootamatu vea tõttu. "
                "Üksikasjad on QGIS-i logis."
            )
            return "error"

        commit_result = self._commit_owned_session()
        if commit_result.errors:
            self._show_error(
                "Toru loodi, kuid andmebaasi salvestamine ebaõnnestus. "
                "Muudatused jäid redigeerimispuhvrisse: "
                + "; ".join(commit_result.errors)
            )
        elif commit_result.left_in_existing_session:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Toru muudatused jäid redigeerimispuhvrisse, sest kiht "
                "oli varem juba redigeerimisel.",
                level=Qgis.MessageLevel.Warning,
                duration=8,
            )
        else:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                f"Isevoolne toru {result.mslink} salvestati andmebaasi ja "
                "redigeerimine lõpetati.",
                level=Qgis.MessageLevel.Success,
                duration=7,
            )
        return "success"

    def _start_editing(self, layer: QgsVectorLayer) -> bool:
        self._edit_session = PluginEditingSession((layer,))
        layer_tools = self.iface.vectorLayerTools()
        if layer_tools is None:
            self._rollback_owned_session()
            self._show_error(
                "QGIS-i redigeerimistööriistu ei õnnestunud avada."
            )
            return False
        if not layer.isEditable() and not layer_tools.startEditing(layer):
            self._rollback_owned_session()
            self._show_error(
                f"Torukihi „{layer.name()}“ redigeerimisrežiimi "
                "käivitamine ebaõnnestus."
            )
            return False
        return True

    def _open_feature_form(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
    ) -> bool:
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
            DuctEditorProfile.GRAVITY,
            parent,
        )
        return dialog.exec_() == QDialog.Accepted

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
            self._layer = None

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
