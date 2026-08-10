"""Click-to-set and click-to-reverse EVEL duct flow direction."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QInputDialog,
    QProgressDialog,
)
from qgis.core import (
    Qgis,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsVariantUtils,
)
from qgis.gui import QgsMapTool, QgsMapToolEmitPoint

from ..layers import DuctLayerOption
from ..ui.light_style import apply_evel_light_style
from .editing_session import PluginEditingSession


MESSAGE_TAG = "EVEL Võrgutööriistad"
FLOW_DIRECTION_FIELD = "FLOWDIRECTION"


@dataclass(frozen=True)
class FlowDirectionCandidate:
    option: DuctLayerOption
    feature_id: int
    mslink: object
    distance: float

    @property
    def label(self) -> str:
        return f"{self.option.label} · MSLINK {self.mslink}"


class FlowDirectionController:
    """Set an unknown direction to +1 and reverse any known direction."""

    COMMAND_TEXT = "Määra või pööra EVEL-i toru suund"

    def __init__(
        self,
        iface,
        action,
        finished,
        *,
        progress_factory=None,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self.progress_factory = (
            progress_factory or self._create_progress_dialog
        )
        self._options: tuple[DuctLayerOption, ...] = ()
        self._tool: QgsMapToolEmitPoint | None = None
        self._previous_tool: QgsMapTool | None = None
        self._finishing = False

    @property
    def is_active(self) -> bool:
        return self._tool is not None

    @staticmethod
    def usable_options(
        options: tuple[DuctLayerOption, ...],
    ) -> tuple[DuctLayerOption, ...]:
        return tuple(
            option
            for option in options
            if option.layer is not None
            and option.layer.isValid()
            and not option.layer.readOnly()
            and option.layer.fields().lookupField(FLOW_DIRECTION_FIELD) >= 0
            and option.layer.dataProvider() is not None
            and bool(
                option.layer.dataProvider().capabilities()
                & Qgis.VectorProviderCapability.ChangeAttributeValues
            )
        )

    def activate(self, options: tuple[DuctLayerOption, ...]) -> bool:
        usable = self.usable_options(options)
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
            "Klõpsa torul. Määramata suunaks saab joone algusest lõppu; "
            "olemasolev suund pööratakse vastupidiseks.",
            level=Qgis.MessageLevel.Info,
            duration=7,
        )
        return True

    def cancel(self, *_args) -> None:
        self._finish(restore_previous=True)

    def _clicked(self, point: QgsPointXY, button=Qt.LeftButton) -> None:
        if button != Qt.LeftButton:
            self.cancel()
            return
        candidates = self._candidates(point)
        if not candidates:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Klõpsu lähedal ei leitud suunaväljaga EVEL-i toru.",
                level=Qgis.MessageLevel.Warning,
                duration=5,
            )
            return
        candidate = self._choose_candidate(candidates)
        if candidate is not None:
            self._apply(candidate)

    def _candidates(
        self,
        map_point: QgsPointXY,
    ) -> tuple[FlowDirectionCandidate, ...]:
        if self._tool is None:
            return ()
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
            for feature in layer.getFeatures(request):
                if not feature.hasGeometry():
                    continue
                distance = feature.geometry().distance(point_geometry)
                if distance > tolerance:
                    continue
                found.append(
                    (
                        0 if layer is active_layer else 1,
                        FlowDirectionCandidate(
                            option=option,
                            feature_id=int(feature.id()),
                            mslink=(
                                feature.attribute(mslink_index)
                                if mslink_index >= 0
                                else feature.id()
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
        for _priority, candidate in found:
            unique.setdefault(
                (candidate.option.layer.id(), candidate.feature_id),
                candidate,
            )
        return tuple(unique.values())

    def _choose_candidate(
        self,
        candidates: tuple[FlowDirectionCandidate, ...],
    ) -> FlowDirectionCandidate | None:
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

    def _apply(self, candidate: FlowDirectionCandidate) -> None:
        layer = candidate.option.layer
        feature = layer.getFeature(candidate.feature_id)
        if not feature.isValid():
            self._show_error("Valitud toru ei ole enam projektikihis.")
            return
        field_index = layer.fields().lookupField(FLOW_DIRECTION_FIELD)
        if field_index < 0:
            self._show_error(
                f"Kihil „{layer.name()}” puudub väli {FLOW_DIRECTION_FIELD}."
            )
            return
        try:
            new_value = self.reversed_value(feature.attribute(field_index))
        except ValueError as error:
            self._show_error(str(error))
            return

        edit_session = PluginEditingSession((layer,))
        layer_tools = self.iface.vectorLayerTools()
        progress = self.progress_factory(self.iface.mainWindow())
        self._show_progress(
            progress,
            f"Muudan toru {candidate.mslink} suunda…",
        )
        if not layer.isEditable() and (
            layer_tools is None or not layer_tools.startEditing(layer)
        ):
            progress.close()
            self._show_error(
                f"Kihi „{layer.name()}” redigeerimise käivitamine "
                "ebaõnnestus."
            )
            return

        layer.beginEditCommand(self.COMMAND_TEXT)
        try:
            old_value = feature.attribute(field_index)
            if not layer.changeAttributeValue(
                candidate.feature_id,
                field_index,
                new_value,
                old_value,
                False,
            ):
                raise RuntimeError("FLOWDIRECTION väärtuse muutmine ebaõnnestus.")
            layer.endEditCommand()
            self._show_progress(
                progress,
                "Salvestan muudatuse andmebaasi…",
            )
            commit_result = edit_session.commit()
        except Exception as error:
            layer.destroyEditCommand()
            edit_session.rollback()
            progress.close()
            self._show_error(str(error))
            return

        self._show_progress(
            progress,
            "Värskendan muudetud torukihti…",
        )
        layer.triggerRepaint()
        progress.close()
        direction_text = (
            "joone algusest lõppu"
            if new_value > 0
            else "joone lõpust algusesse"
        )
        if commit_result.errors:
            self._show_error(
                "Toru suuna salvestamine andmebaasi ebaõnnestus: "
                + "; ".join(commit_result.errors)
            )
        elif commit_result.left_in_existing_session:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                f"Toru {candidate.mslink} suund muudeti: {direction_text}. "
                "Muudatus jäi kasutaja olemasolevasse redigeerimispuhvrisse.",
                level=Qgis.MessageLevel.Warning,
                duration=8,
            )
        else:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                f"Toru {candidate.mslink} suund salvestati: {direction_text}.",
                level=Qgis.MessageLevel.Success,
                duration=6,
            )

    @staticmethod
    def _create_progress_dialog(parent) -> QProgressDialog:
        progress = QProgressDialog(
            "Valmistan suunamuudatust ette…",
            "",
            0,
            0,
            parent,
        )
        progress.setObjectName("evelFlowDirectionProgress")
        progress.setWindowTitle("Toru suund")
        progress.setCancelButton(None)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumWidth(360)
        apply_evel_light_style(progress)
        return progress

    @staticmethod
    def _show_progress(progress, text: str) -> None:
        progress.setLabelText(text)
        if not progress.isVisible():
            progress.show()
        QApplication.processEvents()

    @staticmethod
    def reversed_value(value) -> float:
        if QgsVariantUtils.isNull(value):
            return 1.0
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"FLOWDIRECTION väärtus „{value}” ei ole arvuline."
            ) from error
        if abs(number) <= 1e-12:
            return 1.0
        return -number

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
            duration=9,
        )
