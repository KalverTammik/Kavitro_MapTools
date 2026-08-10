"""Read and atomically write EVEL connection points."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsRectangle,
    QgsVariantUtils,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)

from ..layers.connection_point import ConnectionPointContext


NETWORK_LABELS = {
    "water": "Vesi",
    "sewer": "Reovesi",
    "rain": "Sademevesi",
}
NETWORK_FIELDS = {
    "water": ("WATER_NETWORK_NODE", "WATER_JUNCTION"),
    "sewer": ("SEWER_NETWORK_NODE", "SEWER_JUNCTION"),
    "rain": ("RAIN_NETWORK_NODE", "STORM_WATER_JUNCTION"),
}


class ConnectionPointError(RuntimeError):
    """Raised when a connection point cannot be resolved or saved safely."""


@dataclass(frozen=True)
class ConnectionNodeCandidate:
    network_kind: str
    node_id: int
    point: QgsPoint
    layer: QgsVectorLayer
    distance: float

    @property
    def label(self) -> str:
        return f"{NETWORK_LABELS[self.network_kind]} · sõlm {self.node_id}"


@dataclass(frozen=True)
class ConnectionPointState:
    feature: QgsFeature
    feature_id: int | None
    point_id: int | None
    node_candidate: ConnectionNodeCandidate | None = None

    @property
    def is_new(self) -> bool:
        return self.feature_id is None


@dataclass(frozen=True)
class ConnectionPointPlan:
    state: ConnectionPointState
    values: dict[str, object]


@dataclass(frozen=True)
class ConnectionPointWriteResult:
    point_id: int
    created: bool


class ConnectionPointReader:
    """Resolve a click to an existing point or one or more network nodes."""

    def __init__(self, context: ConnectionPointContext) -> None:
        self.context = context

    def existing(
        self,
        point: QgsPointXY,
        tolerance: float,
    ) -> ConnectionPointState | None:
        map_point = QgsPoint(point.x(), point.y())
        candidates = self._feature_candidates(
            self.context.point_layer,
            map_point,
            tolerance,
            "ID",
        )
        if len(candidates) > 1:
            labels = ", ".join(str(item[1]) for item in candidates)
            raise ConnectionPointError(
                f"Klõpsu lähedal on mitu liitumispunkti ({labels}). "
                "Suumi lähemale."
            )
        if not candidates:
            return None
        _distance, point_id, feature = candidates[0]
        return ConnectionPointState(
            feature=QgsFeature(feature),
            feature_id=int(feature.id()),
            point_id=point_id,
        )

    def node_candidates(
        self,
        point: QgsPointXY,
        tolerance: float,
    ) -> tuple[ConnectionNodeCandidate, ...]:
        map_point = QgsPoint(point.x(), point.y())
        result = []
        for base_kind, layer in self.context.node_layers:
            for distance, node_id, feature in self._feature_candidates(
                layer,
                map_point,
                tolerance,
                "MSLINK",
            ):
                kinds = (base_kind,)
                if base_kind == "sewer":
                    kinds = ("sewer", "rain")
                geometry_point = feature.geometry().asPoint()
                for kind in kinds:
                    result.append(
                        ConnectionNodeCandidate(
                            network_kind=kind,
                            node_id=node_id,
                            point=QgsPoint(
                                geometry_point.x(),
                                geometry_point.y(),
                            ),
                            layer=layer,
                            distance=distance,
                        )
                    )
        result.sort(
            key=lambda item: (
                item.distance,
                NETWORK_LABELS[item.network_kind],
                item.node_id,
            )
        )
        return tuple(result)

    def new_state(
        self,
        candidate: ConnectionNodeCandidate,
    ) -> ConnectionPointState:
        layer = self.context.point_layer
        node_field, junction_field = NETWORK_FIELDS[candidate.network_kind]
        attributes = {
            layer.fields().lookupField(node_field): candidate.node_id,
            layer.fields().lookupField(junction_field): True,
        }
        feature = QgsVectorLayerUtils.createFeature(
            layer,
            QgsGeometry.fromPoint(candidate.point),
            attributes,
        )
        return ConnectionPointState(
            feature=feature,
            feature_id=None,
            point_id=None,
            node_candidate=candidate,
        )

    @staticmethod
    def _feature_candidates(
        layer: QgsVectorLayer,
        point: QgsPoint,
        tolerance: float,
        id_field: str,
    ) -> list[tuple[float, int, QgsFeature]]:
        request = QgsFeatureRequest().setFilterRect(
            QgsRectangle(
                point.x() - tolerance,
                point.y() - tolerance,
                point.x() + tolerance,
                point.y() + tolerance,
            )
        )
        point_geometry = QgsGeometry.fromPoint(point)
        result = []
        for feature in layer.getFeatures(request):
            if not feature.hasGeometry():
                continue
            distance = feature.geometry().distance(point_geometry)
            if distance > tolerance:
                continue
            value = feature[id_field]
            if QgsVariantUtils.isNull(value):
                continue
            try:
                object_id = int(value)
            except (TypeError, ValueError):
                continue
            result.append((distance, object_id, QgsFeature(feature)))
        result.sort(key=lambda item: (item[0], item[1]))
        return result


class ConnectionPointWriter:
    """Create or update one CONSUMER_POINT row in the active edit buffer."""

    COMMAND_TEXT = "Lisa või muuda EVEL-i liitumispunkti"

    def __init__(self, context: ConnectionPointContext) -> None:
        self.context = context

    def write(self, plan: ConnectionPointPlan) -> ConnectionPointWriteResult:
        layer = self.context.point_layer
        if not layer.isEditable():
            raise ConnectionPointError(
                "Liitumispunktide kiht peab olema redigeerimisrežiimis."
            )
        layer.beginEditCommand(self.COMMAND_TEXT)
        try:
            if plan.state.is_new:
                point_id = self._add(plan)
            else:
                point_id = self._update(plan)
            layer.endEditCommand()
        except Exception:
            layer.destroyEditCommand()
            raise
        layer.triggerRepaint()
        return ConnectionPointWriteResult(
            point_id=point_id,
            created=plan.state.is_new,
        )

    def _add(self, plan: ConnectionPointPlan) -> int:
        layer = self.context.point_layer
        feature = QgsFeature(plan.state.feature)
        self._set_values(feature, plan.values)
        if not layer.addFeature(feature):
            raise ConnectionPointError(
                "Liitumispunkti kirje lisamine ebaõnnestus."
            )
        value = feature["ID"]
        if QgsVariantUtils.isNull(value):
            raise ConnectionPointError(
                "Andmepakkuja ei tagastanud uue liitumispunkti ID-d."
            )
        return int(value)

    def _update(self, plan: ConnectionPointPlan) -> int:
        layer = self.context.point_layer
        feature_id = int(plan.state.feature_id)
        feature = layer.getFeature(feature_id)
        if not feature.isValid():
            raise ConnectionPointError(
                "Muudetavat liitumispunkti ei leitud enam kihist."
            )
        changes = {}
        old_values = {}
        for name, value in plan.values.items():
            if name in {"ID", "GEOM"}:
                continue
            index = layer.fields().lookupField(name)
            if index < 0 or feature.attribute(index) == value:
                continue
            changes[index] = value
            old_values[index] = feature.attribute(index)
        if changes and not layer.changeAttributeValues(
            feature_id,
            changes,
            old_values,
            False,
        ):
            raise ConnectionPointError(
                "Liitumispunkti atribuutide muutmine ebaõnnestus."
            )
        return int(plan.state.point_id)

    @staticmethod
    def _set_values(feature: QgsFeature, values: dict[str, object]) -> None:
        for name, value in values.items():
            if name in {"ID", "GEOM"}:
                continue
            index = feature.fields().lookupField(name)
            if index >= 0:
                feature.setAttribute(index, value)
