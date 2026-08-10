"""Map tool for viewing and editing an existing EVEL duct."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QInputDialog
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgsMapTool, QgsMapToolEmitPoint

from ..layers import DuctLayerOption, DuctWorkflow
from ..ui import DuctEditorDialog, DuctEditorProfile
from .editing_session import PluginEditingSession


MESSAGE_TAG = "EVEL Võrgutööriistad"


@dataclass(frozen=True)
class DuctEditCandidate:
    option: DuctLayerOption
    feature_id: int
    mslink: object
    identification: str
    distance: float

    @property
    def label(self) -> str:
        identity = f" · {self.identification}" if self.identification else ""
        return f"{self.option.label} · MSLINK {self.mslink}{identity}"


class EditDuctController:
    """Identify a supported duct and open the shared EVEL duct dialog."""

    COMMAND_TEXT = "Muuda EVEL-i toru andmeid"

    def __init__(
        self,
        iface,
        action,
        finished,
        *,
        dialog_class=DuctEditorDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self.dialog_class = dialog_class
        self._options: tuple[DuctLayerOption, ...] = ()
        self._tool: QgsMapToolEmitPoint | None = None
        self._previous_tool: QgsMapTool | None = None
        self._finishing = False

    @property
    def is_active(self) -> bool:
        return self._tool is not None

    def activate(self, options: tuple[DuctLayerOption, ...]) -> bool:
        usable = tuple(
            option
            for option in options
            if option.layer is not None and option.layer.isValid()
        )
        if not usable:
            return False
        if self.is_active:
            self._options = usable
            return True

        canvas = self.iface.mapCanvas()
        tool = QgsMapToolEmitPoint(canvas)
        tool.setAction(self.action)
        tool.canvasClicked.connect(self._clicked)
        tool.deactivated.connect(self._tool_deactivated)
        self._options = usable
        self._previous_tool = canvas.mapTool()
        self._tool = tool
        canvas.setMapTool(tool)
        self.action.setChecked(True)
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            "Klõpsa kaardil torul, mille andmeid soovid vaadata või muuta.",
            level=Qgis.MessageLevel.Info,
            duration=5,
        )
        return True

    def cancel(self, *_args) -> None:
        self._finish(restore_previous=True)

    def _clicked(self, point: QgsPointXY, button=Qt.LeftButton) -> None:
        if button != Qt.LeftButton:
            return
        candidates = self._candidates(point)
        if not candidates:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Klõpsu lähedal ei leitud toetatud EVEL-i toru.",
                level=Qgis.MessageLevel.Warning,
                duration=5,
            )
            return
        candidate = self._choose_candidate(candidates)
        if candidate is not None:
            self._open_candidate(candidate)

    def _candidates(self, map_point: QgsPointXY) -> tuple[DuctEditCandidate, ...]:
        canvas = self.iface.mapCanvas()
        visible_ids = {layer.id() for layer in canvas.layers()}
        active_layer = self.iface.activeLayer()
        found = []
        for option in self._options:
            layer = option.layer
            if visible_ids and layer.id() not in visible_ids:
                continue
            layer_point = self._tool.toLayerCoordinates(layer, map_point)
            map_offset = QgsPointXY(
                map_point.x() + QgsMapTool.searchRadiusMU(canvas),
                map_point.y(),
            )
            layer_offset = self._tool.toLayerCoordinates(layer, map_offset)
            tolerance = max(layer_point.distance(layer_offset), 0.001)
            request = QgsFeatureRequest().setFilterRect(
                QgsRectangle(
                    layer_point.x() - tolerance,
                    layer_point.y() - tolerance,
                    layer_point.x() + tolerance,
                    layer_point.y() + tolerance,
                )
            )
            point_geometry = QgsGeometry.fromPointXY(layer_point)
            mslink_index = layer.fields().lookupField("MSLINK")
            identification_index = layer.fields().lookupField("IDENTIFICATION")
            for feature in layer.getFeatures(request):
                if not feature.hasGeometry():
                    continue
                distance = feature.geometry().distance(point_geometry)
                if distance > tolerance:
                    continue
                found.append(
                    (
                        0 if layer is active_layer else 1,
                        DuctEditCandidate(
                            option=option,
                            feature_id=feature.id(),
                            mslink=(
                                feature.attribute(mslink_index)
                                if mslink_index >= 0
                                else feature.id()
                            ),
                            identification=(
                                str(feature.attribute(identification_index) or "")
                                if identification_index >= 0
                                else ""
                            ),
                            distance=distance,
                        ),
                    )
                )
        found.sort(
            key=lambda item: (
                item[0],
                item[1].distance,
                item[1].option.label.casefold(),
            )
        )
        unique = {}
        for _active_priority, candidate in found:
            table = str(
                candidate.option.layer.customProperty(
                    "evel_project_table",
                    candidate.option.workflow.value,
                )
            ).casefold()
            unique.setdefault((table, candidate.mslink), candidate)
        return tuple(unique.values())

    def _choose_candidate(
        self,
        candidates: tuple[DuctEditCandidate, ...],
    ) -> DuctEditCandidate | None:
        if len(candidates) == 1:
            return candidates[0]
        labels = [candidate.label for candidate in candidates]
        selected, accepted = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Vali toru",
            "Klõpsu lähedal on mitu toru:",
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        return candidates[labels.index(selected)]

    def _open_candidate(self, candidate: DuctEditCandidate) -> None:
        layer: QgsVectorLayer = candidate.option.layer
        self.iface.setActiveLayer(layer)
        layer.selectByIds([candidate.feature_id])

        edit_session = PluginEditingSession((layer,))
        read_only = layer.readOnly()
        if not read_only and not layer.isEditable():
            layer_tools = self.iface.vectorLayerTools()
            read_only = (
                layer_tools is None
                or not layer_tools.startEditing(layer)
            )
        feature: QgsFeature = layer.getFeature(candidate.feature_id)
        if not feature.isValid():
            self._show_error("Valitud toru ei ole enam projektikihis.")
            return

        profile = (
            DuctEditorProfile.WATER
            if candidate.option.workflow is DuctWorkflow.WATER_TOPOLOGY
            else DuctEditorProfile.GRAVITY
        )
        command_started = False
        try:
            if not read_only:
                layer.beginEditCommand(self.COMMAND_TEXT)
                command_started = True
            dialog = self.dialog_class(
                layer,
                feature,
                profile,
                self.iface.mainWindow(),
                read_only=read_only,
            )
            accepted = dialog.exec_() == QDialog.Accepted
            if command_started:
                if accepted:
                    layer.endEditCommand()
                else:
                    layer.destroyEditCommand()
            if not accepted:
                edit_session.rollback()
            elif not read_only:
                commit_result = edit_session.commit()
                layer.triggerRepaint()
                if commit_result.errors:
                    self._show_error(
                        f"Toru {candidate.mslink} muudeti, kuid andmebaasi "
                        "salvestamine ebaõnnestus. Muudatused jäid "
                        "redigeerimispuhvrisse: "
                        + "; ".join(commit_result.errors)
                    )
                elif commit_result.left_in_existing_session:
                    self.iface.messageBar().pushMessage(
                        MESSAGE_TAG,
                        f"Toru {candidate.mslink} muudatused jäid "
                        "redigeerimispuhvrisse, sest kiht oli varem juba "
                        "redigeerimisel.",
                        level=Qgis.MessageLevel.Warning,
                        duration=8,
                    )
                else:
                    self.iface.messageBar().pushMessage(
                        MESSAGE_TAG,
                        f"Toru {candidate.mslink} salvestati andmebaasi ja "
                        "redigeerimine lõpetati.",
                        level=Qgis.MessageLevel.Success,
                        duration=7,
                    )
        except Exception as error:
            if command_started:
                layer.destroyEditCommand()
            edit_session.rollback()
            self._show_error(f"Toru vormi avamine ebaõnnestus: {error}")

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
            self._options = ()
            try:
                tool.canvasClicked.disconnect(self._clicked)
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
            duration=8,
        )
