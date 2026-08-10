"""Dedicated sewer pumping-station topology reader and writer."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

from qgis.PyQt.QtCore import QDate, QDateTime, QTime
from qgis.core import (
    QgsExpression,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsVectorLayer,
    QgsVariantUtils,
)

from ..layers import SewerPumpingStationContext
from .sewer_manhole import (
    SewerManholeError,
    SewerManholePort,
    SewerManholeReader,
    SewerManholeState,
    SewerManholeWriteResult,
    SewerManholeWriter,
)


PUMP_NODE_NETTYPE_ID = 308
PUMP_SUPPORTED_NETWORK_IDS = frozenset({315, 316, 317})
PUMP_NETWORK_LABELS = {
    315: "Reovesi",
    316: "Sademevesi",
    317: "Drenaaž",
}


@dataclass(frozen=True)
class SewerPumpingStationConfiguration:
    """Editable base-node and SN_SEWER_PUMPING_STATION values."""

    identification: str = ""
    element_height: float | None = None
    bottom_height: float | None = None
    ground_height: float | None = None
    type_aqua_id: int | None = None
    material_id: int | None = None
    role_id: int | None = None
    name: str = ""
    productivity: float | None = None
    pressure_increase: float | None = None
    power_consumption: float | None = None
    el_max_current: float | None = None
    control_id: int | None = None
    parcel_nr: str = ""
    address_id: int | None = None


@dataclass(frozen=True)
class SewerPumpConfiguration:
    """One SN_SEWER_PUMP child record edited by the pumping-station UI."""

    feature_id: int | None = None
    record_id: int | None = None
    type_id: int | None = None
    install_method_id: int | None = None
    install_date: date | None = None
    power_w: float | None = None
    manufacturer: str = ""
    mark: str = ""
    productivity: float | None = None
    pump_head: float | None = None
    running_time: float | None = None
    in_diameter: float | None = None
    out_diameter: float | None = None
    engine_current: float | None = None
    engine_voltage: float | None = None
    remarks: str = ""


@dataclass(frozen=True)
class SewerPumpingStationState:
    topology: SewerManholeState
    configuration: SewerPumpingStationConfiguration
    pumps: tuple[SewerPumpConfiguration, ...] = ()

    @property
    def network_label(self) -> str:
        return PUMP_NETWORK_LABELS.get(
            self.topology.network_id,
            str(self.topology.network_id),
        )


@dataclass(frozen=True)
class SewerPumpingStationPlan:
    state: SewerManholeState
    configuration: SewerPumpingStationConfiguration
    port_heights: tuple[tuple[str, float | None], ...]
    pumps: tuple[SewerPumpConfiguration, ...] = ()
    original_pumps: tuple[SewerPumpConfiguration, ...] = ()

    def height_for(self, port: SewerManholePort) -> float | None:
        return dict(self.port_heights).get(port.key)


class SewerPumpingStationReader:
    """Resolve one map click and read an optional pumping-station detail."""

    def __init__(self, context: SewerPumpingStationContext) -> None:
        self.context = context

    def resolve(
        self,
        point,
        tolerance: float,
    ) -> SewerPumpingStationState:
        topology = SewerManholeReader(
            self.context.topology_context
        ).resolve(point, tolerance)
        if topology.network_id not in PUMP_SUPPORTED_NETWORK_IDS:
            supported = ", ".join(PUMP_NETWORK_LABELS.values())
            raise SewerManholeError(
                f"Pumplat saab lisada ainult võrkudele {supported}. "
                f"Valitud võrgu ID on {topology.network_id}."
            )
        if (
            topology.manhole_detail_feature_id is not None
            or topology.branch_detail_feature_id is not None
        ):
            raise SewerManholeError(
                "Valitud sõlmel on juba kaevu või ühenduskoha detail. "
                "Pumpla on eraldiseisev sõlmeobjekt; eemalda olemasolev "
                "detail enne pumpla loomist."
            )
        detail = self._detail(topology)
        return SewerPumpingStationState(
            topology=topology,
            configuration=self._configuration(topology, detail),
            pumps=self._pumps(detail),
        )

    def _detail(
        self,
        topology: SewerManholeState,
    ) -> QgsFeature | None:
        feature_id = topology.pumping_station_detail_feature_id
        if feature_id is None:
            return None
        feature = self.context.detail_layer.getFeature(feature_id)
        if not feature.isValid():
            raise SewerManholeError(
                "Olemasolevat pumpla detailkirjet ei õnnestunud lugeda."
            )
        return feature

    def _configuration(
        self,
        topology: SewerManholeState,
        detail: QgsFeature | None,
    ) -> SewerPumpingStationConfiguration:
        base = topology.configuration
        options = self.context.options
        return SewerPumpingStationConfiguration(
            identification=base.identification,
            element_height=base.element_height,
            bottom_height=base.bottom_height,
            ground_height=base.ground_height,
            type_aqua_id=self._detail_int(
                detail,
                "TYPE_AQUA_ID",
                options.default_type_id,
            ),
            material_id=self._detail_int(
                detail,
                "MATERIAL_ID",
                options.default_material_id,
            ),
            role_id=self._detail_int(
                detail,
                "ROLE_ID",
                options.default_role_id,
            ),
            name=self._detail_text(detail, "NAME"),
            productivity=self._detail_float(detail, "PRODUCTIVITY"),
            pressure_increase=self._detail_float(
                detail,
                "PRESSURE_INCREASE",
            ),
            power_consumption=self._detail_float(
                detail,
                "POWER_CONSUMPTION",
            ),
            el_max_current=self._detail_float(
                detail,
                "EL_MAX_CURRENT",
            ),
            control_id=self._detail_int(
                detail,
                "CONTROL_ID",
                options.default_control_id,
            ),
            parcel_nr=self._detail_text(detail, "PARCEL_NR"),
            address_id=self._detail_int(detail, "ADDRESS_ID"),
        )

    def _pumps(
        self,
        detail: QgsFeature | None,
    ) -> tuple[SewerPumpConfiguration, ...]:
        if detail is None:
            return ()
        station_id = self._detail_int(detail, "ID")
        if station_id is None:
            raise SewerManholeError(
                "Olemasoleval pumplal puudub pumpade lugemiseks vajalik ID."
            )
        request = QgsFeatureRequest().setFilterExpression(
            '"PSTATION_ID" = '
            + QgsExpression.quotedValue(station_id)
        )
        pumps = [
            self._pump_configuration(feature)
            for feature in self.context.pump_layer.getFeatures(request)
        ]
        pumps.sort(
            key=lambda pump: (
                pump.record_id is None,
                pump.record_id or pump.feature_id or 0,
            )
        )
        return tuple(pumps)

    def _pump_configuration(
        self,
        feature: QgsFeature,
    ) -> SewerPumpConfiguration:
        record_id = self._feature_int(feature, "ID")
        if record_id is None:
            raise SewerManholeError(
                "Kanalisatsioonipumba kirjel puudub ID."
            )
        return SewerPumpConfiguration(
            feature_id=int(feature.id()),
            record_id=record_id,
            type_id=self._feature_int(feature, "TYPE_ID"),
            install_method_id=self._feature_int(
                feature,
                "INSTALL_METHOD_ID",
            ),
            install_date=self._feature_date(feature, "INSTALL_DATE"),
            power_w=self._feature_float(feature, "POWER_W"),
            manufacturer=self._feature_text(feature, "MANUFACTURER"),
            mark=self._feature_text(feature, "MARK"),
            productivity=self._feature_float(feature, "PRODUCTIVITY"),
            pump_head=self._feature_float(feature, "PUMP_HEAD"),
            running_time=self._feature_float(feature, "RUNNING_TIME"),
            in_diameter=self._feature_float(feature, "IN_DIAMETER"),
            out_diameter=self._feature_float(feature, "OUT_DIAMETER"),
            engine_current=self._feature_float(feature, "ENGINE_CURRENT"),
            engine_voltage=self._feature_float(feature, "ENGINE_VOLTAGE"),
            remarks=self._feature_text(feature, "REMARKS"),
        )

    @staticmethod
    def _feature_int(
        feature: QgsFeature,
        field_name: str,
    ) -> int | None:
        if QgsVariantUtils.isNull(feature[field_name]):
            return None
        try:
            return int(feature[field_name])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _feature_float(
        feature: QgsFeature,
        field_name: str,
    ) -> float | None:
        if QgsVariantUtils.isNull(feature[field_name]):
            return None
        try:
            return float(feature[field_name])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _feature_text(
        feature: QgsFeature,
        field_name: str,
    ) -> str:
        if QgsVariantUtils.isNull(feature[field_name]):
            return ""
        return str(feature[field_name]).strip()

    @staticmethod
    def _feature_date(
        feature: QgsFeature,
        field_name: str,
    ) -> date | None:
        value = feature[field_name]
        if QgsVariantUtils.isNull(value):
            return None
        if isinstance(value, QDateTime):
            value = value.date()
        if isinstance(value, QDate):
            return value.toPyDate()
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return None

    @staticmethod
    def _detail_int(
        detail: QgsFeature | None,
        field_name: str,
        default: int | None = None,
    ) -> int | None:
        if detail is None or QgsVariantUtils.isNull(detail[field_name]):
            return default
        try:
            return int(detail[field_name])
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _detail_float(
        detail: QgsFeature | None,
        field_name: str,
    ) -> float | None:
        if detail is None or QgsVariantUtils.isNull(detail[field_name]):
            return None
        try:
            return float(detail[field_name])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _detail_text(
        detail: QgsFeature | None,
        field_name: str,
    ) -> str:
        if detail is None or QgsVariantUtils.isNull(detail[field_name]):
            return ""
        return str(detail[field_name]).strip()


class SewerPumpingStationWriter(SewerManholeWriter):
    """Write a pumping station while reusing the sewer topology machinery."""

    COMMAND_TEXT = "Lisa või muuda EVEL-i kanalisatsioonipumplat"

    def __init__(self, context: SewerPumpingStationContext) -> None:
        self.pumping_context = context
        super().__init__(context.topology_context)

    def write(
        self,
        plan: SewerPumpingStationPlan,
    ) -> SewerManholeWriteResult:
        result = super().write(plan)
        self.pumping_context.visible_layer.triggerRepaint()
        return result

    def _materialize_node(
        self,
        plan: SewerPumpingStationPlan,
    ) -> tuple[int, bool]:
        adjusted = replace(
            plan,
            state=replace(
                plan.state,
                nettype_id=PUMP_NODE_NETTYPE_ID,
            ),
        )
        return super()._materialize_node(adjusted)

    def _write_node_attributes(
        self,
        plan: SewerPumpingStationPlan,
        node_id: int,
    ) -> None:
        super()._write_node_attributes(plan, node_id)
        state = plan.state
        if state.node_id is None:
            return
        layer = state.node_feature_layer
        feature_id = state.node_feature_id
        if layer is None or feature_id is None:
            raise SewerManholeError(
                f"Sõlme {node_id} baaskirje ei ole projektikihis muudetav."
            )
        if not layer.changeAttributeValue(
            feature_id,
            self._field_index(layer, "NETTYPE_ID"),
            PUMP_NODE_NETTYPE_ID,
        ):
            raise SewerManholeError(
                "Pumpla sõlmetüübi NETTYPE_ID uuendamine ebaõnnestus."
            )

    def _write_detail(
        self,
        plan: SewerPumpingStationPlan,
        node_id: int,
    ) -> None:
        layer = self.pumping_context.detail_layer
        config = plan.configuration
        values = {
            "TYPE_AQUA_ID": config.type_aqua_id,
            "MATERIAL_ID": config.material_id,
            "ROLE_ID": config.role_id,
            "NAME": config.name or None,
            "PRODUCTIVITY": config.productivity,
            "PRESSURE_INCREASE": config.pressure_increase,
            "POWER_CONSUMPTION": config.power_consumption,
            "EL_MAX_CURRENT": config.el_max_current,
            "CONTROL_ID": config.control_id,
            "PARCEL_NR": config.parcel_nr or None,
            "ADDRESS_ID": config.address_id,
        }
        existing_id = plan.state.pumping_station_detail_feature_id
        if existing_id is not None:
            station_id = self._ensure_feature_server_key(
                layer,
                existing_id,
                "ID",
                "olemasolevale kanalisatsioonipumplale",
            )
            for field_name, value in values.items():
                if not layer.changeAttributeValue(
                    existing_id,
                    self._field_index(layer, field_name),
                    value,
                ):
                    raise SewerManholeError(
                        f"Pumpla välja {field_name} uuendamine ebaõnnestus."
                    )
            self._write_pumps(plan, station_id)
            return

        attributes = {
            self._field_index(layer, "NODE_ID"): node_id,
        }
        attributes.update(
            {
                self._field_index(layer, field_name): value
                for field_name, value in values.items()
            }
        )
        feature = self._create_feature_with_server_key(
            layer,
            QgsGeometry(),
            attributes,
            "ID",
        )
        reserved_id = self._required_integer_attribute(
            layer,
            feature,
            "ID",
            "uuele kanalisatsioonipumplale",
        )
        if not layer.addFeature(feature):
            provider_errors = "; ".join(layer.dataProvider().errors())
            detail = (
                f" Andmepakkuja: {provider_errors}"
                if provider_errors
                else ""
            )
            raise SewerManholeError(
                "Kanalisatsioonipumpla detailkirje lisamine ebaõnnestus "
                f"(reserveeritud ID {reserved_id}).{detail}"
            )
        self._write_pumps(plan, reserved_id)

    def _write_pumps(
        self,
        plan: SewerPumpingStationPlan,
        station_id: int,
    ) -> None:
        layer = self.pumping_context.pump_layer
        original = {
            pump.record_id: pump
            for pump in plan.original_pumps
            if pump.record_id is not None
        }
        planned = {
            pump.record_id: pump
            for pump in plan.pumps
            if pump.record_id is not None
        }

        for record_id in original.keys() - planned.keys():
            feature_id = original[record_id].feature_id
            if feature_id is None or not layer.deleteFeature(feature_id):
                raise SewerManholeError(
                    f"Kanalisatsioonipumba {record_id} eemaldamine "
                    "ebaõnnestus."
                )

        for pump in plan.pumps:
            values = {
                "PSTATION_ID": station_id,
                "TYPE_ID": pump.type_id,
                "INSTALL_METHOD_ID": pump.install_method_id,
                "INSTALL_DATE": (
                    QDateTime(
                        QDate(
                            pump.install_date.year,
                            pump.install_date.month,
                            pump.install_date.day,
                        ),
                        QTime(0, 0),
                    )
                    if pump.install_date is not None
                    else None
                ),
                "POWER_W": pump.power_w,
                "MANUFACTURER": pump.manufacturer or None,
                "MARK": pump.mark or None,
                "PRODUCTIVITY": pump.productivity,
                "PUMP_HEAD": pump.pump_head,
                "RUNNING_TIME": pump.running_time,
                "IN_DIAMETER": pump.in_diameter,
                "OUT_DIAMETER": pump.out_diameter,
                "ENGINE_CURRENT": pump.engine_current,
                "ENGINE_VOLTAGE": pump.engine_voltage,
                "REMARKS": pump.remarks or None,
            }
            if pump.record_id is not None:
                current = original.get(pump.record_id)
                if current is None or current.feature_id is None:
                    raise SewerManholeError(
                        f"Kanalisatsioonipump {pump.record_id} ei kuulu "
                        "valitud pumplale."
                    )
                for field_name, value in values.items():
                    if not layer.changeAttributeValue(
                        current.feature_id,
                        self._field_index(layer, field_name),
                        value,
                    ):
                        raise SewerManholeError(
                            f"Kanalisatsioonipumba {pump.record_id} välja "
                            f"{field_name} uuendamine ebaõnnestus."
                        )
                continue

            attributes = {
                self._field_index(layer, field_name): value
                for field_name, value in values.items()
            }
            feature = self._create_feature_with_server_key(
                layer,
                QgsGeometry(),
                attributes,
                "ID",
            )
            reserved_id = self._required_integer_attribute(
                layer,
                feature,
                "ID",
                "uuele kanalisatsioonipumbale",
            )
            if not layer.addFeature(feature):
                provider_errors = "; ".join(layer.dataProvider().errors())
                detail = (
                    f" Andmepakkuja: {provider_errors}"
                    if provider_errors
                    else ""
                )
                raise SewerManholeError(
                    "Kanalisatsioonipumba lisamine ebaõnnestus "
                    f"(reserveeritud ID {reserved_id}).{detail}"
                )

    def _validate_plan(self, plan: SewerPumpingStationPlan) -> None:
        expected = {port.key for port in plan.state.ports}
        actual = {key for key, _height in plan.port_heights}
        if expected != actual or len(actual) != len(plan.port_heights):
            raise SewerManholeError(
                "Pumpla torukõrguste loend ei vasta sõlme toruharudele."
            )
        if plan.state.network_id not in PUMP_SUPPORTED_NETWORK_IDS:
            raise SewerManholeError(
                "Pumpla võrk peab olema reovesi, sademevesi või drenaaž."
            )
        if (
            plan.state.manhole_detail_feature_id is not None
            or plan.state.branch_detail_feature_id is not None
        ):
            raise SewerManholeError(
                "Pumplat ei saa kirjutada kaevu või ühenduskoha detailiga "
                "samale sõlmele."
            )
        config = plan.configuration
        self._validate_lookup(
            config.type_aqua_id,
            self.pumping_context.options.type_options,
            "pumpla liik",
        )
        self._validate_lookup(
            config.material_id,
            self.pumping_context.options.material_options,
            "pumpla materjal",
        )
        self._validate_lookup(
            config.role_id,
            self.pumping_context.options.role_options,
            "pumpla roll",
        )
        self._validate_lookup(
            config.control_id,
            self.pumping_context.options.control_options,
            "pumpla juhtimisviis",
        )
        original_ids = [
            pump.record_id
            for pump in plan.original_pumps
            if pump.record_id is not None
        ]
        planned_ids = [
            pump.record_id
            for pump in plan.pumps
            if pump.record_id is not None
        ]
        if len(original_ids) != len(set(original_ids)):
            raise SewerManholeError(
                "Pumpla olemasolevate pumpade ID-d ei ole unikaalsed."
            )
        if len(planned_ids) != len(set(planned_ids)):
            raise SewerManholeError(
                "Pumba kirje on pumpla plaanis rohkem kui üks kord."
            )
        if not set(planned_ids).issubset(set(original_ids)):
            raise SewerManholeError(
                "Pumpla plaan sisaldab sellele pumplale mittekuuluvat pumpa."
            )
        meaningful_types = {
            option.value
            for option in self.pumping_context.options.pump_type_options
            if not option.label.strip().casefold().startswith("määramata")
        }
        install_methods = {
            option.value
            for option in (
                self.pumping_context.options.pump_install_method_options
            )
        }
        for index, pump in enumerate(plan.pumps, start=1):
            if pump.type_id not in meaningful_types:
                raise SewerManholeError(
                    f"Pumba {index} tüüp peab olema valitud."
                )
            if (
                pump.install_method_id is not None
                and pump.install_method_id not in install_methods
            ):
                raise SewerManholeError(
                    f"Pumba {index} paigaldusviis ei ole EVEL-i "
                    "lookup-loendis."
                )
            for value, label in (
                (pump.power_w, "võimsus"),
                (pump.productivity, "tootlikkus"),
                (pump.pump_head, "tõstekõrgus"),
                (pump.running_time, "töötunnid"),
                (pump.in_diameter, "sisendi läbimõõt"),
                (pump.out_diameter, "väljundi läbimõõt"),
                (pump.engine_current, "mootori vool"),
                (pump.engine_voltage, "mootori pinge"),
            ):
                if value is not None and value < 0:
                    raise SewerManholeError(
                        f"Pumba {index} {label} ei tohi olla negatiivne."
                    )
            for value, maximum, label in (
                (pump.manufacturer, 50, "tootja"),
                (pump.mark, 30, "mark"),
                (pump.remarks, 250, "märkused"),
            ):
                if len(value) > maximum:
                    raise SewerManholeError(
                        f"Pumba {index} välja „{label}” pikkus ületab "
                        f"{maximum} märki."
                    )

    @staticmethod
    def _validate_lookup(value, options, label: str) -> None:
        if value not in {option.value for option in options}:
            raise SewerManholeError(
                f"Valitud {label} ei ole generaatori lookup-loendis."
            )

    def _command_layers(
        self,
        state: SewerManholeState,
    ) -> list[QgsVectorLayer]:
        candidates = [
            self.pumping_context.detail_layer,
            self.pumping_context.pump_layer,
            (
                state.node_feature_layer
                if state.node_id is not None
                else self.context.node_layer
            ),
            state.split_layer,
            *(
                connection.layer
                for connection in state.endpoint_connections
            ),
            *(port.layer for port in state.ports),
        ]
        layers: list[QgsVectorLayer] = []
        seen: set[str] = set()
        for layer in candidates:
            if layer is None or layer.id() in seen:
                continue
            seen.add(layer.id())
            layers.append(layer)
        return layers
