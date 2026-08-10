"""Map-driven workflow for configuring one EVEL water-node assembly."""

from __future__ import annotations

from collections.abc import Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QInputDialog
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVariantUtils,
)
from qgis.gui import QgsMapTool, QgsMapToolEmitPoint

from ..layers import (
    NodeConfigurationContext,
    NodeConfigurationContextError,
    NodeConfigurationInspector,
    ProjectInspection,
)
from ..topology import (
    NodeAssemblyReader,
    NodeAssemblyWriter,
    NodeConfigurationError,
)
from ..ui import (
    NodeConfigurationProgressDialog,
    VisualNodeConfiguratorDialog,
)


MESSAGE_TAG = "EVEL Võrgutööriistad"


class NodeConfiguratorController:
    """Select a base node on the map and apply an assembly configuration."""

    def __init__(
        self,
        iface,
        action,
        finished: Callable[[], None],
        dialog_class=VisualNodeConfiguratorDialog,
    ) -> None:
        self.iface = iface
        self.action = action
        self.finished = finished
        self.dialog_class = dialog_class
        self._context: NodeConfigurationContext | None = None
        self._tool: QgsMapToolEmitPoint | None = None
        self._previous_tool: QgsMapTool | None = None
        self._finishing = False

    @property
    def is_active(self) -> bool:
        return self._tool is not None

    def activate(self, inspection: ProjectInspection) -> bool:
        if self.is_active:
            return True
        try:
            context = NodeConfigurationInspector().discover(
                QgsProject.instance(), inspection
            )
        except NodeConfigurationContextError as error:
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
            "Vali kaardilt konfigureeritav veesõlm.",
            level=Qgis.MessageLevel.Info,
            duration=5,
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
            self._show_error("Sõlme konfiguraatori kihid ei ole enam saadaval.")
            self.cancel()
            return

        progress_dialog: NodeConfigurationProgressDialog | None = None
        try:
            layer_point = self._to_layer_point(canvas_point, context.node_layer)
            tolerance = self._layer_tolerance(context.node_layer)
            candidates = self._node_candidates(context, layer_point, tolerance)
            node_id = self._choose_node(candidates)
            if node_id is None:
                return
            state = NodeAssemblyReader(context).read(node_id)
            dialog = self.dialog_class(
                state,
                context.branch_options,
                context.valve_options,
                context.valve_subtype_options,
                context.valve_default_type_id,
                context.valve_default_subtype_id,
                context.manhole_options,
                context.facility_options,
                parent=self.iface.mainWindow(),
            )
            if dialog.exec() != QDialog.Accepted:
                self.cancel()
                return
            plan = dialog.configuration()
            progress_dialog = NodeConfigurationProgressDialog(
                state.node_id,
                self.iface.mainWindow(),
            )
            progress_dialog.show()
            progress_dialog.update_progress(
                0,
                len(plan.ports)
                + (6 if context.facility_options is not None else 5),
                "Käivitan vajalikud kihid redigeerimisrežiimis.",
            )
            self._start_editing(context)
            result = NodeAssemblyWriter(context).write(
                plan,
                lambda current, total, message: (
                    progress_dialog.update_progress(
                        current + 1,
                        total + 1,
                        message,
                    )
                ),
            )
        except (NodeConfigurationContextError, NodeConfigurationError) as error:
            if progress_dialog is not None:
                progress_dialog.show_failure(str(error))
            self._show_error(str(error))
            return
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            if progress_dialog is not None:
                progress_dialog.show_failure(
                    "Sõlme konfigureerimine ebaõnnestus."
                )
            QgsMessageLog.logMessage(
                f"Sõlme konfigureerimine ebaõnnestus: {error!r}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
            self._show_error(
                "Sõlme konfigureerimine ebaõnnestus ootamatu vea tõttu. "
                "Üksikasjad on QGIS-i logis."
            )
            return
        finally:
            if progress_dialog is not None:
                progress_dialog.close()
                progress_dialog.deleteLater()

        valve_count = len(result.created_valve_node_ids)
        valve_text = (
            f"; loodi {valve_count} uut sulgeseadme sõlme"
            if valve_count
            else ""
        )
        manhole_text = "; sõlm asub kaevus" if result.manhole_enabled else ""
        facility_text = ""
        if (
            result.facility_variant_key is not None
            and context.facility_options is not None
        ):
            facility_label = next(
                (
                    variant.label
                    for variant in context.facility_options.variants
                    if variant.key == result.facility_variant_key
                ),
                "rajatis",
            )
            facility_text = f"; rajatis: {facility_label}"
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            f"Veesõlme {result.node_id} konfiguratsioon lisati "
            f"redigeerimispuhvrisse{valve_text}{manhole_text}"
            f"{facility_text}.",
            level=Qgis.MessageLevel.Success,
            duration=7,
        )
        self.cancel()

    def _node_candidates(
        self,
        context: NodeConfigurationContext,
        point: QgsPointXY,
        tolerance: float,
    ) -> list[tuple[int, float]]:
        rectangle = QgsRectangle(
            point.x() - tolerance,
            point.y() - tolerance,
            point.x() + tolerance,
            point.y() + tolerance,
        )
        request = QgsFeatureRequest().setFilterRect(rectangle)
        point_geometry = QgsGeometry.fromPointXY(point)
        candidates: list[tuple[int, float]] = []
        id_index = context.node_layer.fields().lookupField("MSLINK")
        for feature in context.node_layer.getFeatures(request):
            value = feature.attribute(id_index)
            if QgsVariantUtils.isNull(value) or not feature.hasGeometry():
                continue
            distance = feature.geometry().distance(point_geometry)
            if distance <= tolerance:
                try:
                    candidates.append((int(value), distance))
                except (TypeError, ValueError):
                    continue
        candidates.sort(key=lambda item: (item[1], item[0]))
        if not candidates:
            raise NodeConfigurationError(
                "Klõpsu lähedalt ei leitud veesõlme. Suumi lähemale ja proovi uuesti."
            )
        return candidates

    def _choose_node(self, candidates: list[tuple[int, float]]) -> int | None:
        if len(candidates) == 1:
            return candidates[0][0]
        labels = [f"Sõlm {node_id} ({distance:.3f} m)" for node_id, distance in candidates]
        selected, accepted = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Vali veesõlm",
            "Klõpsu lähedal on mitu sõlme:",
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        return candidates[labels.index(selected)][0]

    def _start_editing(self, context: NodeConfigurationContext) -> None:
        layer_tools = self.iface.vectorLayerTools()
        if layer_tools is None:
            raise NodeConfigurationError(
                "QGIS-i redigeerimistööriistu ei õnnestunud avada."
            )
        layers = [
            context.edge_layer,
            context.node_layer,
            context.branch_detail_layer,
            context.valve_detail_layer,
            context.manhole_detail_layer,
        ]
        if context.facility_options is not None:
            layers.extend(
                variant.detail_layer
                for variant in context.facility_options.variants
            )
        seen: set[str] = set()
        for layer in layers:
            if layer.id() in seen:
                continue
            seen.add(layer.id())
            if not layer.isEditable() and not layer_tools.startEditing(layer):
                raise NodeConfigurationError(
                    f"Kihi „{layer.name()}“ redigeerimisrežiimi "
                    "käivitamine ebaõnnestus."
                )

    def _to_layer_point(self, point: QgsPointXY, layer) -> QgsPointXY:
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        if canvas_crs == layer.crs():
            return QgsPointXY(point)
        try:
            return QgsCoordinateTransform(
                canvas_crs, layer.crs(), QgsProject.instance()
            ).transform(point)
        except QgsCsException as error:
            raise NodeConfigurationError(
                "Kaardi koordinaati ei õnnestunud sõlmekihi CRS-i teisendada."
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
                canvas_crs, layer.crs(), QgsProject.instance()
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
            duration=8,
        )
