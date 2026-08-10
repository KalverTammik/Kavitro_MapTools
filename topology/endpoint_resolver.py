"""Resolve captured water-duct endpoints against the generated project layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from qgis.core import (
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsRectangle,
    QgsVectorLayer,
    QgsVariantUtils,
)


class EndpointKind(str, Enum):
    EXISTING_NODE = "existing_node"
    NEW_NODE = "new_node"


@dataclass(frozen=True)
class EdgeEndpointConnection:
    """Existing edge endpoint which must be linked to the resolved node."""

    feature_id: int
    edge_id: Optional[int]
    field_name: str
    point: QgsPoint
    current_node_id: Optional[int] = None


@dataclass(frozen=True)
class EdgeSplitConnection:
    """Existing edge whose interior must be split at ``point``."""

    feature_id: int
    edge_id: Optional[int]
    point: QgsPoint


@dataclass(frozen=True)
class EndpointResolution:
    kind: EndpointKind
    point: QgsPoint
    node_id: Optional[int] = None
    edge_connections: tuple[EdgeEndpointConnection, ...] = ()
    edge_split: Optional[EdgeSplitConnection] = None


@dataclass(frozen=True)
class WaterDuctPlan:
    geometry: QgsGeometry
    start: EndpointResolution
    end: EndpointResolution


class EndpointResolutionError(RuntimeError):
    """Raised when an endpoint cannot be resolved without guessing."""


class EndpointOnEdgeError(EndpointResolutionError):
    """Raised when multiple nearby edges make a split ambiguous."""


class WaterEndpointResolver:
    """Build a write-free endpoint plan for one captured line."""

    def __init__(
        self,
        edge_layer: QgsVectorLayer,
        node_layer: QgsVectorLayer,
        tolerance: float,
    ) -> None:
        self.edge_layer = edge_layer
        self.node_layer = node_layer
        self.tolerance = max(float(tolerance), 1e-9)

    def resolve(self, geometry: QgsGeometry) -> WaterDuctPlan:
        if geometry.isNull() or geometry.isEmpty():
            raise EndpointResolutionError("Toru geomeetria on tühi.")

        curve = geometry.constGet()
        if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
            raise EndpointResolutionError(
                "Lisa toru toetab praegu üheosalist LineString geomeetriat."
            )

        start_point = self._copy_point(curve.pointN(0))
        end_point = self._copy_point(curve.pointN(curve.numPoints() - 1))
        if start_point.distance(end_point) <= self.tolerance:
            raise EndpointResolutionError(
                "Sama sõlmega algav ja lõppev suletud toru ei ole veel toetatud."
            )

        start = self._resolve_point(start_point, "alguspunkt")
        end = self._resolve_point(end_point, "lõpp-punkt")

        if (
            start.kind is EndpointKind.EXISTING_NODE
            and end.kind is EndpointKind.EXISTING_NODE
            and start.node_id == end.node_id
        ):
            raise EndpointResolutionError(
                "Toru mõlemad otsad lahenevad samaks sõlmeks; suletud toru "
                "ei ole veel toetatud."
            )

        if (
            start.edge_split is not None
            and end.edge_split is not None
            and start.edge_split.feature_id == end.edge_split.feature_id
        ):
            raise EndpointResolutionError(
                "Ühe uue toruga sama olemasoleva toru kahte kohta "
                "poolitamine ei ole veel toetatud."
            )

        adjusted = self._replace_endpoints(geometry, start.point, end.point)
        if adjusted.length() <= 0:
            raise EndpointResolutionError("Toru pikkus peab olema suurem kui null.")

        return WaterDuctPlan(adjusted, start, end)

    def resolve_point(
        self,
        point: QgsPoint,
        label: str = "punkt",
    ) -> EndpointResolution:
        """Resolve one map point for node-based water assets.

        This exposes the same node, coincident endpoint and edge-split rules
        used by the water-duct capture workflow without requiring a dummy
        line geometry.
        """

        return self._resolve_point(self._copy_point(point), label)

    def _resolve_point(self, point: QgsPoint, label: str) -> EndpointResolution:
        candidates = self._node_candidates(point)
        if len(candidates) > 1:
            ids = ", ".join(str(node_id) for _, node_id, _ in candidates)
            raise EndpointResolutionError(
                f"Toru {label} lähedal on mitu võimalikku sõlme: {ids}. "
                "Tööriist ei vali nende vahel automaatselt."
            )

        edge_endpoints, edge_splits = self._edge_hits(point)
        if len(edge_splits) > 1:
            ids = ", ".join(self._split_label(item) for item in edge_splits)
            raise EndpointOnEdgeError(
                f"Toru {label} lähedal on mitu poolitatavat toru: {ids}. "
                "Tööriist ei vali nende vahel automaatselt."
            )
        edge_split = edge_splits[0] if edge_splits else None

        if edge_endpoints:
            self._validate_coincident_edge_endpoints(edge_endpoints, label)
        if edge_split is not None and edge_endpoints:
            self._validate_split_against_endpoints(
                edge_split, edge_endpoints, label
            )

        if candidates:
            _, node_id, node_point = candidates[0]
            if edge_split is not None:
                self._validate_coincident_points(
                    node_point,
                    edge_split.point,
                    f"Toru {label} lähedal olev sõlm {node_id} ja "
                    f"poolitamiskoht {self._split_label(edge_split)} "
                    "ei lange kokku.",
                )
            connections = self._connections_for_existing_node(
                edge_endpoints, node_id, node_point, label
            )
            return EndpointResolution(
                EndpointKind.EXISTING_NODE,
                node_point,
                node_id,
                connections,
                edge_split,
            )

        if edge_endpoints:
            referenced_ids = sorted(
                {
                    connection.current_node_id
                    for connection in edge_endpoints
                    if connection.current_node_id is not None
                }
            )
            if referenced_ids:
                ids = ", ".join(str(node_id) for node_id in referenced_ids)
                raise EndpointResolutionError(
                    f"Toru {label} olemasolev ots viitab sõlmele {ids}, kuid "
                    "seda sõlme ei leitud otsapunktist. Paranda olemasolev "
                    "topoloogia enne uue lõigu lisamist."
                )

            node_point = self._copy_point(
                edge_split.point
                if edge_split is not None
                else edge_endpoints[0].point
            )
            return EndpointResolution(
                EndpointKind.NEW_NODE,
                node_point,
                edge_connections=edge_endpoints,
                edge_split=edge_split,
            )

        if edge_split is not None:
            return EndpointResolution(
                EndpointKind.NEW_NODE,
                self._copy_point(edge_split.point),
                edge_split=edge_split,
            )

        return EndpointResolution(
            EndpointKind.NEW_NODE, self._copy_point(point)
        )

    def _node_candidates(
        self, point: QgsPoint
    ) -> list[tuple[float, int, QgsPoint]]:
        mslink_index = self.node_layer.fields().lookupField("MSLINK")
        request = QgsFeatureRequest().setFilterRect(self._search_rectangle(point))
        if mslink_index >= 0:
            request.setSubsetOfAttributes([mslink_index])

        candidates: list[tuple[float, int, QgsPoint]] = []
        for feature in self.node_layer.getFeatures(request):
            geometry = feature.geometry()
            if geometry.isNull() or geometry.isEmpty():
                continue
            raw_point = geometry.constGet()
            if not isinstance(raw_point, QgsPoint):
                continue
            node_point = self._copy_point(raw_point)
            distance = point.distance(node_point)
            if distance > self.tolerance:
                continue
            value = feature.attribute(mslink_index)
            if QgsVariantUtils.isNull(value):
                raise EndpointResolutionError(
                    f"Sõlmel FID {feature.id()} puudub MSLINK väärtus."
                )
            try:
                node_id = int(value)
            except (TypeError, ValueError) as error:
                raise EndpointResolutionError(
                    f"Sõlme FID {feature.id()} MSLINK ei ole täisarv."
                ) from error
            candidates.append((distance, node_id, node_point))

        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates

    def _edge_hits(
        self, point: QgsPoint
    ) -> tuple[
        tuple[EdgeEndpointConnection, ...],
        tuple[EdgeSplitConnection, ...],
    ]:
        request = QgsFeatureRequest().setFilterRect(self._search_rectangle(point))
        fields = self.edge_layer.fields()
        mslink_index = fields.lookupField("MSLINK")
        begin_index = fields.lookupField("BEGIN_NODE_ID")
        end_index = fields.lookupField("END_NODE_ID")
        request.setSubsetOfAttributes(
            [
                index
                for index in (mslink_index, begin_index, end_index)
                if index >= 0
            ]
        )
        tolerance_squared = self.tolerance * self.tolerance
        endpoint_hits: list[EdgeEndpointConnection] = []
        interior_hits: list[EdgeSplitConnection] = []
        for feature in self.edge_layer.getFeatures(request):
            geometry = feature.geometry()
            if geometry.isNull() or geometry.isEmpty():
                continue
            curve = geometry.constGet()
            if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
                continue

            edge_id = self._optional_int(
                feature.attribute(mslink_index) if mslink_index >= 0 else None
            )
            display_id = edge_id if edge_id is not None else int(feature.id())
            start_point = self._copy_point(curve.startPoint())
            end_point = self._copy_point(curve.endPoint())
            start_near = point.distance(start_point) <= self.tolerance
            end_near = point.distance(end_point) <= self.tolerance

            if start_near and end_near:
                raise EndpointResolutionError(
                    f"Olemasoleva toru {display_id} mõlemad otsad jäävad "
                    "valikutolerantsi. Suumi lähemale ja vali üks ots."
                )
            if start_near:
                endpoint_hits.append(
                    EdgeEndpointConnection(
                        feature_id=int(feature.id()),
                        edge_id=edge_id,
                        field_name="BEGIN_NODE_ID",
                        point=start_point,
                        current_node_id=self._optional_int(
                            feature.attribute(begin_index)
                            if begin_index >= 0
                            else None
                        ),
                    )
                )
                continue
            if end_near:
                endpoint_hits.append(
                    EdgeEndpointConnection(
                        feature_id=int(feature.id()),
                        edge_id=edge_id,
                        field_name="END_NODE_ID",
                        point=end_point,
                        current_node_id=self._optional_int(
                            feature.attribute(end_index)
                            if end_index >= 0
                            else None
                        ),
                    )
                )
                continue

            distance_squared, _nearest, _after, _left = (
                geometry.closestSegmentWithContext(
                    QgsPointXY(point.x(), point.y())
                )
            )
            if 0 <= distance_squared <= tolerance_squared:
                interior_hits.append(
                    EdgeSplitConnection(
                        feature_id=int(feature.id()),
                        edge_id=edge_id,
                        point=QgsPoint(_nearest.x(), _nearest.y()),
                    )
                )

        endpoint_hits.sort(
            key=lambda item: (
                item.edge_id if item.edge_id is not None else item.feature_id,
                item.field_name,
            )
        )
        interior_hits.sort(
            key=lambda item: (
                item.edge_id if item.edge_id is not None else item.feature_id
            )
        )
        return tuple(endpoint_hits), tuple(interior_hits)

    def _validate_coincident_edge_endpoints(
        self,
        connections: tuple[EdgeEndpointConnection, ...],
        label: str,
    ) -> None:
        reference = connections[0].point
        coincidence_tolerance = self._coincidence_tolerance()
        if any(
            reference.distance(connection.point) > coincidence_tolerance
            for connection in connections[1:]
        ):
            ids = ", ".join(self._edge_label(item) for item in connections)
            raise EndpointResolutionError(
                f"Toru {label} lähedal on mitu erinevat toruotsa: {ids}. "
                "Suumi lähemale või kasuta QGIS-i snäppimist."
            )

    def _validate_split_against_endpoints(
        self,
        edge_split: EdgeSplitConnection,
        connections: tuple[EdgeEndpointConnection, ...],
        label: str,
    ) -> None:
        for connection in connections:
            self._validate_coincident_points(
                edge_split.point,
                connection.point,
                f"Toru {label} lähedal olev toruots "
                f"{self._edge_label(connection)} ja poolitamiskoht "
                f"{self._split_label(edge_split)} ei lange kokku.",
            )

    def _connections_for_existing_node(
        self,
        connections: tuple[EdgeEndpointConnection, ...],
        node_id: int,
        node_point: QgsPoint,
        label: str,
    ) -> tuple[EdgeEndpointConnection, ...]:
        updates: list[EdgeEndpointConnection] = []
        for connection in connections:
            self._validate_coincident_points(
                connection.point,
                node_point,
                f"Toru {label} lähedal olev sõlm {node_id} ja toruots "
                f"{self._edge_label(connection)} ei lange kokku.",
            )
            if connection.current_node_id is None:
                updates.append(connection)
            elif connection.current_node_id != node_id:
                raise EndpointResolutionError(
                    f"Toruotsa {self._edge_label(connection)} viide "
                    f"{connection.current_node_id} ei vasta leitud sõlmele "
                    f"{node_id}."
                )
        return tuple(updates)

    @staticmethod
    def _optional_int(value: object) -> Optional[int]:
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _edge_label(connection: EdgeEndpointConnection) -> str:
        if connection.edge_id is not None:
            return str(connection.edge_id)
        return f"FID {connection.feature_id}"

    @staticmethod
    def _split_label(connection: EdgeSplitConnection) -> str:
        if connection.edge_id is not None:
            return str(connection.edge_id)
        return f"FID {connection.feature_id}"

    def _validate_coincident_points(
        self,
        first: QgsPoint,
        second: QgsPoint,
        message: str,
    ) -> None:
        if first.distance(second) > self._coincidence_tolerance():
            raise EndpointResolutionError(message)

    def _coincidence_tolerance(self) -> float:
        return max(min(self.tolerance * 0.01, 0.01), 1e-6)

    def _search_rectangle(self, point: QgsPoint) -> QgsRectangle:
        return QgsRectangle(
            point.x() - self.tolerance,
            point.y() - self.tolerance,
            point.x() + self.tolerance,
            point.y() + self.tolerance,
        )

    @staticmethod
    def _replace_endpoints(
        geometry: QgsGeometry, start: QgsPoint, end: QgsPoint
    ) -> QgsGeometry:
        source = geometry.constGet()
        points = [
            WaterEndpointResolver._copy_point(source.pointN(index))
            for index in range(source.numPoints())
        ]
        points[0] = WaterEndpointResolver._copy_point(start)
        points[-1] = WaterEndpointResolver._copy_point(end)
        return QgsGeometry(QgsLineString(points))

    @staticmethod
    def _copy_point(point: QgsPoint) -> QgsPoint:
        # The SIP binding for QGIS 3.40 does not expose QgsPoint's C++ copy
        # constructor, even though pointN() already returns a QgsPoint.
        return QgsPoint(point.x(), point.y())
