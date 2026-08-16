"""Read-only context model for the compact duct preview widget."""

from __future__ import annotations

from dataclasses import dataclass
import math

from qgis.core import (
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVariantUtils,
    QgsVectorLayer,
    QgsWkbTypes,
)


@dataclass(frozen=True)
class DuctEndpointPreview:
    """Resolved identity and transient edit state of one duct endpoint."""

    node_id: int | None
    identification: str = ""
    status: str = "Sidumata"

    @property
    def title(self) -> str:
        if self.identification:
            return f"Sõlm {self.identification}"
        if self.node_id is not None:
            return f"Sõlm {self.node_id}"
        return "Sõlm puudub"


@dataclass(frozen=True)
class DuctPreviewContext:
    """Geometry and topology data needed by a map-free object preview."""

    active_points: tuple[tuple[float, float], ...]
    background_lines: tuple[tuple[tuple[float, float], ...], ...]
    background_nodes: tuple[tuple[float, float], ...]
    begin: DuctEndpointPreview
    end: DuctEndpointPreview
    length_2d: float
    z_profile: tuple[tuple[float, float], ...] = ()

    @property
    def has_geometry(self) -> bool:
        return len(self.active_points) >= 2

    @property
    def has_z_geometry(self) -> bool:
        return len(self.z_profile) >= 2


class DuctPreviewContextBuilder:
    """Build a bounded preview without introducing a second map canvas."""

    MAX_BACKGROUND_EDGES = 80
    MAX_BACKGROUND_NODES = 120

    def build(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        profile: object,
    ) -> DuctPreviewContext:
        current = layer.getFeature(feature.id())
        if not current.isValid():
            current = QgsFeature(feature)
        geometry = current.geometry() if current.hasGeometry() else QgsGeometry()
        active_points = self._line_points(geometry)
        length_2d = geometry.length() if active_points else 0.0
        preview_extent = self._preview_extent(geometry, length_2d)
        background_lines = self._background_lines(
            layer,
            current.id(),
            preview_extent,
        )

        node_layer = self._resolve_node_layer(profile)
        background_nodes = self._background_nodes(
            layer,
            node_layer,
            preview_extent,
        )
        begin = self._endpoint(
            current,
            "BEGIN_NODE_ID",
            node_layer,
        )
        end = self._endpoint(
            current,
            "END_NODE_ID",
            node_layer,
        )
        return DuctPreviewContext(
            active_points=active_points,
            background_lines=background_lines,
            background_nodes=background_nodes,
            begin=begin,
            end=end,
            length_2d=float(length_2d),
            z_profile=self._z_profile(geometry),
        )

    @staticmethod
    def _line_points(
        geometry: QgsGeometry,
    ) -> tuple[tuple[float, float], ...]:
        if geometry.isNull() or geometry.isEmpty():
            return ()
        if geometry.isMultipart():
            parts = geometry.asMultiPolyline()
            points = parts[0] if parts else []
        else:
            points = geometry.asPolyline()
        return tuple((float(point.x()), float(point.y())) for point in points)

    @staticmethod
    def _preview_extent(
        geometry: QgsGeometry,
        length_2d: float,
    ) -> QgsRectangle:
        if geometry.isNull() or geometry.isEmpty():
            return QgsRectangle()
        extent = geometry.boundingBox()
        span = max(
            extent.width(),
            extent.height(),
            float(length_2d) * 0.35,
            1.0,
        )
        margin = span * 0.65
        return QgsRectangle(
            extent.xMinimum() - margin,
            extent.yMinimum() - margin,
            extent.xMaximum() + margin,
            extent.yMaximum() + margin,
        )

    def _background_lines(
        self,
        layer: QgsVectorLayer,
        feature_id: int,
        extent: QgsRectangle,
    ) -> tuple[tuple[tuple[float, float], ...], ...]:
        if extent.isNull() or extent.isEmpty():
            return ()
        request = QgsFeatureRequest().setFilterRect(extent)
        request.setNoAttributes()
        request.setLimit(self.MAX_BACKGROUND_EDGES)
        lines: list[tuple[tuple[float, float], ...]] = []
        for candidate in layer.getFeatures(request):
            if candidate.id() == feature_id or not candidate.hasGeometry():
                continue
            geometry = candidate.geometry()
            if geometry.isMultipart():
                parts = geometry.asMultiPolyline()
            else:
                part = geometry.asPolyline()
                parts = [part] if part else []
            for points in parts:
                line = tuple(
                    (float(point.x()), float(point.y())) for point in points
                )
                if len(line) >= 2:
                    lines.append(line)
        return tuple(lines)

    def _resolve_node_layer(self, profile: object) -> QgsVectorLayer | None:
        profile_value = str(getattr(profile, "value", profile)).casefold()
        table = (
            "sn_water_node"
            if profile_value == "water"
            else "sn_sewer_node"
        )
        role = "water_node" if profile_value == "water" else "sewer_node"
        candidates: list[tuple[int, QgsVectorLayer]] = []
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PointGeometry:
                continue
            metadata_table = str(
                layer.customProperty("evel_project_table", "")
            ).strip().casefold()
            metadata_role = str(
                layer.customProperty("evel_topology_role", "")
            ).strip().casefold()
            source = layer.source().casefold()
            if (
                metadata_table != table
                and metadata_role != role
                and table not in source
            ):
                continue
            score = 0
            if metadata_table == table:
                score += 8
            if metadata_role == role:
                score += 8
            if not layer.subsetString().strip():
                score += 4
            if "baaskiht" in layer.name().casefold():
                score += 2
            candidates.append((score, layer))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _background_nodes(
        self,
        edge_layer: QgsVectorLayer,
        node_layer: QgsVectorLayer | None,
        edge_extent: QgsRectangle,
    ) -> tuple[tuple[float, float], ...]:
        if node_layer is None or edge_extent.isNull() or edge_extent.isEmpty():
            return ()
        node_extent = QgsRectangle(edge_extent)
        to_edge = None
        if node_layer.crs() != edge_layer.crs():
            try:
                transform_context = QgsProject.instance().transformContext()
                edge_to_node = QgsCoordinateTransform(
                    edge_layer.crs(),
                    node_layer.crs(),
                    transform_context,
                )
                to_edge = QgsCoordinateTransform(
                    node_layer.crs(),
                    edge_layer.crs(),
                    transform_context,
                )
                node_extent = edge_to_node.transformBoundingBox(edge_extent)
            except QgsCsException:
                return ()

        request = QgsFeatureRequest().setFilterRect(node_extent)
        request.setNoAttributes()
        request.setLimit(self.MAX_BACKGROUND_NODES)
        points: list[tuple[float, float]] = []
        for feature in node_layer.getFeatures(request):
            if not feature.hasGeometry():
                continue
            point = feature.geometry().asPoint()
            if to_edge is not None:
                try:
                    point = to_edge.transform(QgsPointXY(point))
                except QgsCsException:
                    continue
            points.append((float(point.x()), float(point.y())))
        return tuple(points)

    def _endpoint(
        self,
        edge: QgsFeature,
        field_name: str,
        node_layer: QgsVectorLayer | None,
    ) -> DuctEndpointPreview:
        node_id = self._optional_int(edge, field_name)
        if node_id is None:
            return DuctEndpointPreview(None)
        if node_layer is None:
            return DuctEndpointPreview(node_id, status="Seotud")
        node = self._node_by_id(node_layer, node_id)
        if node is None:
            return DuctEndpointPreview(node_id, status="Seotud")
        identification = self._text_attribute(node, "IDENTIFICATION")
        edit_buffer = node_layer.editBuffer()
        is_new = bool(
            edit_buffer is not None
            and node.id() in edit_buffer.addedFeatures()
        )
        return DuctEndpointPreview(
            node_id,
            identification,
            "Uus sõlm" if is_new else "Olemasolev",
        )

    @staticmethod
    def _node_by_id(
        layer: QgsVectorLayer,
        node_id: int,
    ) -> QgsFeature | None:
        if layer.fields().lookupField("MSLINK") < 0:
            return None
        request = QgsFeatureRequest().setFilterExpression(
            f'"MSLINK" = {int(node_id)}'
        )
        return next(layer.getFeatures(request), None)

    @staticmethod
    def _optional_int(feature: QgsFeature, field_name: str) -> int | None:
        index = feature.fields().lookupField(field_name)
        if index < 0:
            return None
        value = feature.attribute(index)
        if QgsVariantUtils.isNull(value):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _text_attribute(feature: QgsFeature, field_name: str) -> str:
        index = feature.fields().lookupField(field_name)
        if index < 0:
            return ""
        value = feature.attribute(index)
        if QgsVariantUtils.isNull(value):
            return ""
        return str(value).strip()

    @staticmethod
    def _z_profile(
        geometry: QgsGeometry,
    ) -> tuple[tuple[float, float], ...]:
        if (
            geometry.isNull()
            or geometry.isEmpty()
            or not QgsWkbTypes.hasZ(geometry.wkbType())
        ):
            return ()
        vertices = list(geometry.vertices())
        if len(vertices) < 2 or any(not math.isfinite(point.z()) for point in vertices):
            return ()
        result: list[tuple[float, float]] = [(0.0, float(vertices[0].z()))]
        chainage = 0.0
        for previous, point in zip(vertices, vertices[1:]):
            chainage += math.hypot(
                float(point.x() - previous.x()),
                float(point.y() - previous.y()),
            )
            result.append((chainage, float(point.z())))
        return tuple(result)
