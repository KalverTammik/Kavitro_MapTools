"""Atomic QGIS edit operation for a planned water duct."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsVectorLayer,
    QgsVectorLayerUtils,
    QgsVariantUtils,
)

from .endpoint_resolver import (
    EdgeSplitConnection,
    EndpointKind,
    EndpointResolution,
    WaterDuctPlan,
)


class WaterDuctWriteError(RuntimeError):
    """Raised when a planned multi-layer edit cannot be completed."""


class WaterDuctWriteCanceled(WaterDuctWriteError):
    """Raised after the user cancels the configured attribute form."""


@dataclass(frozen=True)
class WaterDuctWriteResult:
    edge_feature_id: int
    begin_node_id: int
    end_node_id: int


class WaterDuctWriter:
    """Apply nodes and one edge as a reversible QGIS edit command."""

    COMMAND_TEXT = "Lisa EVEL-i veetoru"

    def __init__(
        self, edge_layer: QgsVectorLayer, node_layer: QgsVectorLayer
    ) -> None:
        self.edge_layer = edge_layer
        self.node_layer = node_layer

    def write(
        self,
        plan: WaterDuctPlan,
        network_id: int,
        nettype_id: int,
        open_form: Callable[[QgsVectorLayer, QgsFeature], bool],
    ) -> WaterDuctWriteResult:
        if not self.edge_layer.isEditable() or not self.node_layer.isEditable():
            raise WaterDuctWriteError(
                "Veetoru- ja veesõlmekiht peavad olema redigeerimisrežiimis."
            )

        command_layers = [self.edge_layer]
        if (
            plan.start.kind is EndpointKind.NEW_NODE
            or plan.end.kind is EndpointKind.NEW_NODE
        ):
            command_layers.insert(0, self.node_layer)

        for layer in command_layers:
            layer.beginEditCommand(self.COMMAND_TEXT)

        try:
            begin_node_id = self._materialize_endpoint(
                plan.start, network_id, nettype_id
            )
            end_node_id = self._materialize_endpoint(
                plan.end, network_id, nettype_id
            )
            edge_feature = self._add_edge(
                plan.geometry, begin_node_id, end_node_id
            )

            if not open_form(self.edge_layer, edge_feature):
                raise WaterDuctWriteCanceled("Veetoru lisamine tühistati.")

            for layer in reversed(command_layers):
                layer.endEditCommand()

            self.node_layer.triggerRepaint()
            self.edge_layer.triggerRepaint()
            return WaterDuctWriteResult(
                edge_feature_id=int(edge_feature.id()),
                begin_node_id=begin_node_id,
                end_node_id=end_node_id,
            )
        except Exception:
            for layer in reversed(command_layers):
                layer.destroyEditCommand()
            self.node_layer.triggerRepaint()
            self.edge_layer.triggerRepaint()
            raise

    def _materialize_endpoint(
        self,
        endpoint: EndpointResolution,
        network_id: int,
        nettype_id: int,
    ) -> int:
        if endpoint.kind is EndpointKind.EXISTING_NODE:
            if endpoint.node_id is None:
                raise WaterDuctWriteError(
                    "Olemasoleva sõlme MSLINK väärtus puudub."
                )
            node_id = int(endpoint.node_id)
            self._connect_existing_edge_ends(endpoint, node_id)
            self._split_existing_edge(endpoint.edge_split, node_id)
            return node_id

        network_index = self._field_index(self.node_layer, "NETWORK_ID")
        nettype_index = self._field_index(self.node_layer, "NETTYPE_ID")
        mslink_index = self._field_index(self.node_layer, "MSLINK")
        attributes = {
            network_index: int(network_id),
            nettype_index: int(nettype_id),
        }
        feature = QgsVectorLayerUtils.createFeature(
            self.node_layer,
            QgsGeometry.fromPoint(endpoint.point),
            attributes,
        )
        if not self.node_layer.addFeature(feature):
            raise WaterDuctWriteError(
                "Uue veesõlme lisamine andmepakkujasse ebaõnnestus."
            )

        value = feature.attribute(mslink_index)
        if QgsVariantUtils.isNull(value):
            raise WaterDuctWriteError(
                "Andmepakkuja ei tagastanud uue veesõlme MSLINK väärtust."
            )
        try:
            node_id = int(value)
        except (TypeError, ValueError) as error:
            raise WaterDuctWriteError(
                "Andmepakkuja tagastatud veesõlme MSLINK ei ole täisarv."
            ) from error
        self._connect_existing_edge_ends(endpoint, node_id)
        self._split_existing_edge(endpoint.edge_split, node_id)
        return node_id

    def materialize_endpoint(
        self,
        endpoint: EndpointResolution,
        network_id: int,
        nettype_id: int,
    ) -> int:
        """Create/resolve one endpoint inside an already active edit command."""

        return self._materialize_endpoint(endpoint, network_id, nettype_id)

    def _connect_existing_edge_ends(
        self,
        endpoint: EndpointResolution,
        node_id: int,
    ) -> None:
        for connection in endpoint.edge_connections:
            field_index = self._field_index(
                self.edge_layer, connection.field_name
            )
            if not self.edge_layer.changeAttributeValue(
                connection.feature_id,
                field_index,
                node_id,
            ):
                edge_label = (
                    str(connection.edge_id)
                    if connection.edge_id is not None
                    else f"FID {connection.feature_id}"
                )
                raise WaterDuctWriteError(
                    f"Olemasoleva toru {edge_label} välja "
                    f"{connection.field_name} uuendamine ebaõnnestus."
                )

    def _split_existing_edge(
        self,
        connection: EdgeSplitConnection | None,
        node_id: int,
    ) -> None:
        if connection is None:
            return

        original = self.edge_layer.getFeature(connection.feature_id)
        if not original.isValid() or not original.hasGeometry():
            raise WaterDuctWriteError(
                f"Poolitatavat toru {self._split_label(connection)} ei leitud."
            )

        first_geometry, second_geometry = self._split_line_geometry(
            original.geometry(), connection.point
        )
        begin_index = self._field_index(self.edge_layer, "BEGIN_NODE_ID")
        end_index = self._field_index(self.edge_layer, "END_NODE_ID")
        length_index = self._field_index(self.edge_layer, "LENGTH_2D")

        new_attributes, original_attribute_updates = (
            self._split_attribute_values(
                original,
                first_geometry.length(),
                second_geometry.length(),
            )
        )
        new_attributes[begin_index] = node_id
        new_attributes[end_index] = original.attribute(end_index)
        new_attributes[length_index] = second_geometry.length()

        if not self.edge_layer.changeGeometry(
            connection.feature_id, first_geometry
        ):
            raise WaterDuctWriteError(
                f"Toru {self._split_label(connection)} esimese osa "
                "geomeetria uuendamine ebaõnnestus."
            )
        original_attribute_updates.extend(
            (
                (end_index, node_id),
                (length_index, first_geometry.length()),
            )
        )
        for field_index, value in original_attribute_updates:
            if not self.edge_layer.changeAttributeValue(
                connection.feature_id, field_index, value
            ):
                field_name = self.edge_layer.fields().at(field_index).name()
                raise WaterDuctWriteError(
                    f"Toru {self._split_label(connection)} välja "
                    f"{field_name} uuendamine ebaõnnestus."
                )

        second_feature = QgsVectorLayerUtils.createFeature(
            self.edge_layer,
            second_geometry,
            new_attributes,
        )
        if not self.edge_layer.addFeature(second_feature):
            raise WaterDuctWriteError(
                f"Toru {self._split_label(connection)} teise osa lisamine "
                "ebaõnnestus."
            )
        self._required_integer_attribute(
            self.edge_layer,
            second_feature,
            "MSLINK",
            "poolitatud toru teisele osale",
        )

    def _split_attribute_values(
        self,
        original: QgsFeature,
        first_length: float,
        second_length: float,
    ) -> tuple[dict[int, object], list[tuple[int, object]]]:
        fields = self.edge_layer.fields()
        excluded = set(self.edge_layer.primaryKeyAttributes())
        excluded.update(
            self._field_index(self.edge_layer, name)
            for name in (
                "MSLINK",
                "BEGIN_NODE_ID",
                "END_NODE_ID",
                "LENGTH_2D",
            )
        )
        original_length = first_length + second_length
        new_attributes: dict[int, object] = {}
        original_updates: list[tuple[int, object]] = []

        for index, field in enumerate(fields):
            if index in excluded:
                continue
            if fields.fieldOrigin(index) != Qgis.FieldOrigin.Provider:
                continue

            value = original.attribute(index)
            policy = field.splitPolicy()
            if policy == Qgis.FieldDomainSplitPolicy.Duplicate:
                new_attributes[index] = value
            elif policy == Qgis.FieldDomainSplitPolicy.GeometryRatio:
                if QgsVariantUtils.isNull(value) or original_length <= 0:
                    new_attributes[index] = value
                    continue
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    new_attributes[index] = value
                    continue
                first_value = numeric_value * first_length / original_length
                second_value = numeric_value * second_length / original_length
                original_updates.append((index, first_value))
                new_attributes[index] = second_value

        return new_attributes, original_updates

    @classmethod
    def _split_line_geometry(
        cls,
        geometry: QgsGeometry,
        requested_point: QgsPoint,
    ) -> tuple[QgsGeometry, QgsGeometry]:
        curve = geometry.constGet()
        if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
            raise WaterDuctWriteError(
                "Poolitatav toru peab olema üheosaline LineString."
            )

        _distance, nearest, after_vertex, _left = (
            geometry.closestSegmentWithContext(
                QgsPointXY(requested_point.x(), requested_point.y())
            )
        )
        if after_vertex <= 0 or after_vertex >= curve.numPoints():
            raise WaterDuctWriteError(
                "Toru poolitamiskohta ei õnnestunud joone sisemuses määrata."
            )

        split_point = QgsPoint(nearest.x(), nearest.y())
        source_points = [
            QgsPoint(curve.pointN(index).x(), curve.pointN(index).y())
            for index in range(curve.numPoints())
        ]
        first_points = source_points[:after_vertex]
        cls._append_unique_point(first_points, split_point)
        second_points = [split_point]
        for source_point in source_points[after_vertex:]:
            cls._append_unique_point(second_points, source_point)

        if len(first_points) < 2 or len(second_points) < 2:
            raise WaterDuctWriteError(
                "Toru poolitamiskoht langeb joone algus- või lõpp-punkti."
            )
        first = QgsGeometry(QgsLineString(first_points))
        second = QgsGeometry(QgsLineString(second_points))
        if first.length() <= 0 or second.length() <= 0:
            raise WaterDuctWriteError(
                "Toru poolitamisel tekkis nullpikkusega osa."
            )
        return first, second

    @staticmethod
    def _append_unique_point(points: list[QgsPoint], point: QgsPoint) -> None:
        if not points or points[-1].distance(point) > 1e-9:
            points.append(QgsPoint(point.x(), point.y()))

    @staticmethod
    def _split_label(connection: EdgeSplitConnection) -> str:
        if connection.edge_id is not None:
            return str(connection.edge_id)
        return f"FID {connection.feature_id}"

    def _add_edge(
        self, geometry: QgsGeometry, begin_node_id: int, end_node_id: int
    ) -> QgsFeature:
        attributes = {
            self._field_index(self.edge_layer, "BEGIN_NODE_ID"): begin_node_id,
            self._field_index(self.edge_layer, "END_NODE_ID"): end_node_id,
            self._field_index(self.edge_layer, "LENGTH_2D"): geometry.length(),
        }
        feature = QgsVectorLayerUtils.createFeature(
            self.edge_layer, geometry, attributes
        )
        if not self.edge_layer.addFeature(feature):
            raise WaterDuctWriteError(
                "Uue veetoru lisamine andmepakkujasse ebaõnnestus."
            )
        self._required_integer_attribute(
            self.edge_layer,
            feature,
            "MSLINK",
            "uuele veetorule",
        )
        return feature

    @classmethod
    def _required_integer_attribute(
        cls,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        field_name: str,
        object_label: str,
    ) -> int:
        field_index = cls._field_index(layer, field_name)
        value = feature.attribute(field_index)
        if QgsVariantUtils.isNull(value):
            raise WaterDuctWriteError(
                f"Andmepakkuja ei tagastanud {object_label} välja "
                f"{field_name} väärtust."
            )
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise WaterDuctWriteError(
                f"Andmepakkuja tagastatud {object_label} välja "
                f"{field_name} väärtus ei ole täisarv."
            ) from error

    @staticmethod
    def _field_index(layer: QgsVectorLayer, field_name: str) -> int:
        index = layer.fields().lookupField(field_name)
        if index < 0:
            raise WaterDuctWriteError(
                f"Kihil „{layer.name()}“ puudub väli {field_name}."
            )
        return index
