"""Discovery and preflight diagnostics for generated EVEL water projects.

The generated QGIS project is the source of truth.  This module only reads
project and layer state; it never changes project settings or starts editing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

from qgis.core import (
    Qgis,
    QgsDataProvider,
    QgsDataSourceUri,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
)


PROJECT_GROUP = "EVEL"
MODEL_VERSION_KEY = "/model_version"
CONTRACT_VERSION_KEY = "/network_tools_contract_version"
SUPPORTED_MODEL_VERSION = "1"
SUPPORTED_CONTRACT_VERSION = "1"

EDGE_ROLE = "water_edge"
NODE_ROLE = "water_node"
EDGE_TABLE = "sn_water_duct"
NODE_TABLE = "sn_water_node"
EXPECTED_PROVIDER = "postgres"
EXPECTED_SCHEMA = "evel"
EXPECTED_GEOMETRY_COLUMN = "GEOM"
EXPECTED_CRS = "EPSG:3301"

EDGE_REQUIRED_FIELDS = frozenset(
    {
        "MSLINK",
        "NETWORK_ID",
        "NETTYPE_ID",
        "BEGIN_NODE_ID",
        "END_NODE_ID",
        "LENGTH_2D",
    }
)
NODE_REQUIRED_FIELDS = frozenset(
    {"MSLINK", "NETWORK_ID", "NETTYPE_ID"}
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


class DiagnosticLevel(str, Enum):
    """Severity of a preflight diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Diagnostic:
    """A stable, user-facing preflight finding."""

    code: str
    level: DiagnosticLevel
    message: str
    layer_id: str = ""


@dataclass(frozen=True)
class ProjectInspection:
    """Resolved EVEL layers and all diagnostics produced for them."""

    edge_layer: Optional[QgsVectorLayer]
    node_layer: Optional[QgsVectorLayer]
    diagnostics: tuple[Diagnostic, ...]

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(
            item
            for item in self.diagnostics
            if item.level is DiagnosticLevel.ERROR
        )

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(
            item
            for item in self.diagnostics
            if item.level is DiagnosticLevel.WARNING
        )

    @property
    def can_add_water_duct(self) -> bool:
        """Whether the client-side add-tool preflight is successful."""

        return (
            self.edge_layer is not None
            and self.node_layer is not None
            and not self.errors
        )

    def short_message(self) -> str:
        """Return a concise Estonian status suitable for the toolbar."""

        if self.errors:
            return self.errors[0].message
        if self.warnings:
            return self.warnings[0].message
        if self.edge_layer is None:
            return "Aktiivne EVEL-i veetoru kiht puudub."
        return f"Aktiivne torukiht „{self.edge_layer.name()}” on kasutatav."


class EVELProjectInspector:
    """Resolve generated EVEL layers and validate the add-tool prerequisites."""

    def inspect(
        self,
        project: QgsProject,
        active_layer: object | None,
        *,
        check_runtime: bool = True,
    ) -> ProjectInspection:
        """Inspect *project* without changing it.

        ``check_runtime=False`` skips PostGIS connection, transaction and
        provider capability checks.  It exists for isolated memory-layer unit
        tests; production callers must use the default.
        """

        diagnostics: list[Diagnostic] = []
        self._validate_project_versions(project, diagnostics)

        edge_layer = self._resolve_active_edge(active_layer, diagnostics)
        node_layer = self._resolve_node_layer(project, diagnostics)

        if edge_layer is not None:
            self._validate_edge_layer(
                edge_layer, diagnostics, check_runtime=check_runtime
            )
        if node_layer is not None:
            self._validate_node_layer(
                node_layer, diagnostics, check_runtime=check_runtime
            )
        if check_runtime and edge_layer is not None and node_layer is not None:
            self._validate_runtime(project, edge_layer, node_layer, diagnostics)

        return ProjectInspection(
            edge_layer=edge_layer,
            node_layer=node_layer,
            diagnostics=tuple(diagnostics),
        )

    def _validate_project_versions(
        self, project: QgsProject, diagnostics: list[Diagnostic]
    ) -> None:
        self._validate_version(
            project,
            MODEL_VERSION_KEY,
            SUPPORTED_MODEL_VERSION,
            "PROJECT_MODEL_VERSION",
            "andmemudeli",
            diagnostics,
        )
        self._validate_version(
            project,
            CONTRACT_VERSION_KEY,
            SUPPORTED_CONTRACT_VERSION,
            "PROJECT_CONTRACT_VERSION",
            "võrgutööriistade väljundi",
            diagnostics,
        )

    @staticmethod
    def _validate_version(
        project: QgsProject,
        key: str,
        supported: str,
        code_prefix: str,
        label: str,
        diagnostics: list[Diagnostic],
    ) -> None:
        value, exists = project.readEntry(PROJECT_GROUP, key)
        if not exists or not str(value).strip():
            diagnostics.append(
                Diagnostic(
                    f"{code_prefix}_MISSING",
                    DiagnosticLevel.WARNING,
                    f"Projektil puudub EVEL-i {label} versioonitunnus; "
                    "kihid tuvastatakse varureeglitega.",
                )
            )
            return
        if str(value).strip() != supported:
            diagnostics.append(
                Diagnostic(
                    f"{code_prefix}_UNSUPPORTED",
                    DiagnosticLevel.ERROR,
                    f"EVEL-i {label} versioon {value} ei ole toetatud "
                    f"(toetatud: {supported}).",
                )
            )

    def _resolve_active_edge(
        self, active_layer: object | None, diagnostics: list[Diagnostic]
    ) -> Optional[QgsVectorLayer]:
        if not isinstance(active_layer, QgsVectorLayer):
            diagnostics.append(
                Diagnostic(
                    "EDGE_ACTIVE_MISSING",
                    DiagnosticLevel.ERROR,
                    "Vali aktiivseks generaatori loodud veetoru kiht.",
                )
            )
            return None

        if self._property(active_layer, "evel_topology_role") == EDGE_ROLE:
            return active_layer

        if self._layer_table(active_layer) == EDGE_TABLE:
            diagnostics.append(
                Diagnostic(
                    "EDGE_METADATA_FALLBACK",
                    DiagnosticLevel.WARNING,
                    f"Kiht „{active_layer.name()}” tuvastati tabeli ja väljade "
                    "järgi; evel_topology_role metadata puudub.",
                    active_layer.id(),
                )
            )
            return active_layer

        diagnostics.append(
            Diagnostic(
                "EDGE_ACTIVE_INVALID",
                DiagnosticLevel.ERROR,
                f"Aktiivne kiht „{active_layer.name()}” ei ole EVEL-i veetoru kiht.",
                active_layer.id(),
            )
        )
        return None

    def _resolve_node_layer(
        self, project: QgsProject, diagnostics: list[Diagnostic]
    ) -> Optional[QgsVectorLayer]:
        layers = [
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        ]
        explicit = [
            layer
            for layer in layers
            if self._property(layer, "evel_topology_role") == NODE_ROLE
        ]

        if len(explicit) == 1:
            return explicit[0]
        if len(explicit) > 1:
            diagnostics.append(
                Diagnostic(
                    "NODE_LAYER_AMBIGUOUS",
                    DiagnosticLevel.ERROR,
                    "Projektis on mitu water_node rolliga veesõlmede baaskihti.",
                )
            )
            return None

        fallback = [
            layer
            for layer in layers
            if self._layer_table(layer) == NODE_TABLE
            and not layer.subsetString().strip()
            and self._has_fields(layer, NODE_REQUIRED_FIELDS)
        ]
        if len(fallback) == 1:
            diagnostics.append(
                Diagnostic(
                    "NODE_METADATA_FALLBACK",
                    DiagnosticLevel.WARNING,
                    f"Kiht „{fallback[0].name()}” tuvastati filtreerimata "
                    "sn_water_node baaskihina; topology metadata puudub.",
                    fallback[0].id(),
                )
            )
            return fallback[0]
        if len(fallback) > 1:
            diagnostics.append(
                Diagnostic(
                    "NODE_LAYER_AMBIGUOUS",
                    DiagnosticLevel.ERROR,
                    "Projektis on mitu võimalikku filtreerimata sn_water_node "
                    "baaskihti.",
                )
            )
            return None

        diagnostics.append(
            Diagnostic(
                "NODE_LAYER_MISSING",
                DiagnosticLevel.ERROR,
                "Projektis puudub filtreerimata veesõlmede baaskiht.",
            )
        )
        return None

    def _validate_edge_layer(
        self,
        layer: QgsVectorLayer,
        diagnostics: list[Diagnostic],
        *,
        check_runtime: bool,
    ) -> None:
        self._validate_generated_metadata(
            layer, EDGE_TABLE, EDGE_ROLE, diagnostics
        )
        self._validate_geometry(
            layer,
            expected_type=Qgis.GeometryType.Line,
            type_label="joongeomeetria",
            diagnostics=diagnostics,
            check_runtime=check_runtime,
        )
        self._validate_fields(layer, EDGE_REQUIRED_FIELDS, "torukihil", diagnostics)

        if not layer.subsetString().strip():
            diagnostics.append(
                Diagnostic(
                    "EDGE_FILTER_MISSING",
                    DiagnosticLevel.ERROR,
                    f"Torukihil „{layer.name()}” puudub generaatori alamfilter.",
                    layer.id(),
                )
            )

        network_id = self._positive_int_property(
            layer, "evel_topology_node_network_id"
        )
        nettype_id = self._positive_int_property(
            layer, "evel_topology_node_nettype_id"
        )
        if network_id is None:
            diagnostics.append(
                Diagnostic(
                    "EDGE_NODE_NETWORK_ID_MISSING",
                    DiagnosticLevel.ERROR,
                    f"Torukihil „{layer.name()}” puudub kehtiv "
                    "evel_topology_node_network_id.",
                    layer.id(),
                )
            )
        if nettype_id is None:
            diagnostics.append(
                Diagnostic(
                    "EDGE_NODE_NETTYPE_ID_MISSING",
                    DiagnosticLevel.ERROR,
                    f"Torukihil „{layer.name()}” puudub kehtiv "
                    "evel_topology_node_nettype_id.",
                    layer.id(),
                )
            )

        self._validate_default(
            layer, "NETWORK_ID", network_id, diagnostics
        )
        self._validate_default(layer, "NETTYPE_ID", nettype_id, diagnostics)
        self._validate_length_default(layer, diagnostics)
        self._validate_form(layer, diagnostics)

    def _validate_node_layer(
        self,
        layer: QgsVectorLayer,
        diagnostics: list[Diagnostic],
        *,
        check_runtime: bool,
    ) -> None:
        self._validate_generated_metadata(
            layer, NODE_TABLE, NODE_ROLE, diagnostics
        )
        self._validate_geometry(
            layer,
            expected_type=Qgis.GeometryType.Point,
            type_label="punktgeomeetria",
            diagnostics=diagnostics,
            check_runtime=check_runtime,
        )
        self._validate_fields(layer, NODE_REQUIRED_FIELDS, "sõlmekihil", diagnostics)

        if layer.subsetString().strip():
            diagnostics.append(
                Diagnostic(
                    "NODE_LAYER_FILTERED",
                    DiagnosticLevel.ERROR,
                    f"Veesõlmede baaskihil „{layer.name()}” on alamfilter; "
                    "tööriist vajab filtreerimata tugikihti.",
                    layer.id(),
                )
            )
        if not self._truthy(
            layer.customProperty("evel_project_support_layer", False)
        ):
            diagnostics.append(
                Diagnostic(
                    "NODE_SUPPORT_PROPERTY_MISSING",
                    DiagnosticLevel.ERROR,
                    f"Kihil „{layer.name()}” puudub evel_project_support_layer=true.",
                    layer.id(),
                )
            )
        if not self._truthy(
            layer.customProperty("evel_topology_support_layer", False)
        ):
            diagnostics.append(
                Diagnostic(
                    "NODE_TOPOLOGY_SUPPORT_PROPERTY_MISSING",
                    DiagnosticLevel.ERROR,
                    f"Kihil „{layer.name()}” puudub "
                    "evel_topology_support_layer=true.",
                    layer.id(),
                )
            )

    def _validate_generated_metadata(
        self,
        layer: QgsVectorLayer,
        expected_table: str,
        expected_role: str,
        diagnostics: list[Diagnostic],
    ) -> None:
        expected = {
            "evel_project_source": EXPECTED_PROVIDER,
            "evel_project_schema": EXPECTED_SCHEMA,
            "evel_project_table": expected_table,
            "evel_topology_role": expected_role,
        }
        if not self._truthy(layer.customProperty("evel_project_layer", False)):
            diagnostics.append(
                Diagnostic(
                    "LAYER_PROJECT_PROPERTY_MISSING",
                    DiagnosticLevel.ERROR,
                    f"Kihil „{layer.name()}” puudub evel_project_layer=true.",
                    layer.id(),
                )
            )
        for key, expected_value in expected.items():
            actual = self._property(layer, key)
            if actual != expected_value:
                diagnostics.append(
                    Diagnostic(
                        "LAYER_METADATA_MISMATCH",
                        DiagnosticLevel.ERROR,
                        f"Kihi „{layer.name()}” omadus {key} peab olema "
                        f"„{expected_value}”, praegu „{actual or 'puudub'}”.",
                        layer.id(),
                    )
                )

    def _validate_geometry(
        self,
        layer: QgsVectorLayer,
        *,
        expected_type: Qgis.GeometryType,
        type_label: str,
        diagnostics: list[Diagnostic],
        check_runtime: bool,
    ) -> None:
        if layer.geometryType() != expected_type:
            diagnostics.append(
                Diagnostic(
                    "LAYER_GEOMETRY_TYPE_INVALID",
                    DiagnosticLevel.ERROR,
                    f"Kihil „{layer.name()}” peab olema {type_label}.",
                    layer.id(),
                )
            )
        if layer.crs().authid().upper() != EXPECTED_CRS:
            diagnostics.append(
                Diagnostic(
                    "LAYER_CRS_INVALID",
                    DiagnosticLevel.ERROR,
                    f"Kihi „{layer.name()}” CRS peab olema {EXPECTED_CRS}, "
                    f"praegu {layer.crs().authid() or 'määramata'}.",
                    layer.id(),
                )
            )
        if not check_runtime:
            return
        provider = layer.dataProvider()
        geometry_column = provider.geometryColumnName() if provider else ""
        if geometry_column.upper() != EXPECTED_GEOMETRY_COLUMN:
            diagnostics.append(
                Diagnostic(
                    "LAYER_GEOMETRY_COLUMN_INVALID",
                    DiagnosticLevel.ERROR,
                    f"Kihi „{layer.name()}” geomeetriaveerg peab olema GEOM, "
                    f"praegu {geometry_column or 'määramata'}.",
                    layer.id(),
                )
            )

    @staticmethod
    def _validate_fields(
        layer: QgsVectorLayer,
        required: Iterable[str],
        label: str,
        diagnostics: list[Diagnostic],
    ) -> None:
        actual = {field.name().upper() for field in layer.fields()}
        missing = sorted(set(required) - actual)
        if missing:
            diagnostics.append(
                Diagnostic(
                    "LAYER_FIELDS_MISSING",
                    DiagnosticLevel.ERROR,
                    f"{label.capitalize()} „{layer.name()}” puuduvad väljad: "
                    f"{', '.join(missing)}.",
                    layer.id(),
                )
            )

    @staticmethod
    def _validate_default(
        layer: QgsVectorLayer,
        field_name: str,
        expected_value: Optional[int],
        diagnostics: list[Diagnostic],
    ) -> None:
        if expected_value is None:
            return
        index = layer.fields().lookupField(field_name)
        if index < 0:
            return
        expression = layer.defaultValueDefinition(index).expression().strip()
        normalized = expression.strip("'\"")
        if normalized != str(expected_value):
            diagnostics.append(
                Diagnostic(
                    "EDGE_DEFAULT_VALUE_INVALID",
                    DiagnosticLevel.ERROR,
                    f"Kihi „{layer.name()}” välja {field_name} vaikeväärtus "
                    f"peab olema {expected_value}, praegu "
                    f"{expression or 'määramata'}.",
                    layer.id(),
                )
            )

    @staticmethod
    def _validate_length_default(
        layer: QgsVectorLayer, diagnostics: list[Diagnostic]
    ) -> None:
        index = layer.fields().lookupField("LENGTH_2D")
        if index < 0:
            return
        definition = layer.defaultValueDefinition(index)
        expression = "".join(definition.expression().lower().split())
        if expression != "length($geometry)" or not definition.applyOnUpdate():
            diagnostics.append(
                Diagnostic(
                    "EDGE_LENGTH_DEFAULT_INVALID",
                    DiagnosticLevel.ERROR,
                    f"Kihi „{layer.name()}” LENGTH_2D peab kasutama avaldist "
                    "length($geometry) koos geomeetria muutmisel uuendamisega.",
                    layer.id(),
                )
            )

    @staticmethod
    def _validate_form(
        layer: QgsVectorLayer, diagnostics: list[Diagnostic]
    ) -> None:
        form_path = layer.editFormConfig().uiForm().strip()
        if not form_path:
            diagnostics.append(
                Diagnostic(
                    "EDGE_FORM_NOT_CONFIGURED",
                    DiagnosticLevel.WARNING,
                    f"Torukihil „{layer.name()}” ei ole projektis .ui vormi määratud.",
                    layer.id(),
                )
            )
            return
        if not Path(form_path).is_file():
            diagnostics.append(
                Diagnostic(
                    "EDGE_FORM_FILE_MISSING",
                    DiagnosticLevel.WARNING,
                    f"Torukihi „{layer.name()}” vormifaili ei leitud: {form_path}.",
                    layer.id(),
                )
            )

    def _validate_runtime(
        self,
        project: QgsProject,
        edge_layer: QgsVectorLayer,
        node_layer: QgsVectorLayer,
        diagnostics: list[Diagnostic],
    ) -> None:
        for layer in (edge_layer, node_layer):
            if not layer.isValid():
                diagnostics.append(
                    Diagnostic(
                        "LAYER_INVALID",
                        DiagnosticLevel.ERROR,
                        f"Kihti „{layer.name()}” ei õnnestunud andmepakkujast laadida.",
                        layer.id(),
                    )
                )
                continue
            if layer.providerType() != EXPECTED_PROVIDER:
                diagnostics.append(
                    Diagnostic(
                        "LAYER_PROVIDER_INVALID",
                        DiagnosticLevel.ERROR,
                        f"Kiht „{layer.name()}” peab kasutama PostGIS-i "
                        f"andmepakkujat, praegu {layer.providerType()}.",
                        layer.id(),
                    )
                )
                continue
            self._validate_provider_source(layer, diagnostics)
            self._validate_edit_capabilities(layer, diagnostics)
            provider = layer.dataProvider()
            if provider and not bool(
                provider.providerProperty(
                    QgsDataProvider.EvaluateDefaultValues, False
                )
            ):
                diagnostics.append(
                    Diagnostic(
                        "PROVIDER_DEFAULTS_DISABLED",
                        DiagnosticLevel.ERROR,
                        f"Kihi „{layer.name()}” PostgreSQL-i andmepakkuja ei "
                        "hinda serveripoolseid vaikeväärtusi.",
                        layer.id(),
                    )
                )

        if project.transactionMode() != Qgis.TransactionMode.AutomaticGroups:
            diagnostics.append(
                Diagnostic(
                    "PROJECT_TRANSACTION_MODE_INVALID",
                    DiagnosticLevel.ERROR,
                    "Projekti tehingurežiim peab olema Automatic Transaction Groups.",
                )
            )
        if not bool(
            project.flags()
            & Qgis.ProjectFlag.EvaluateDefaultValuesOnProviderSide
        ):
            diagnostics.append(
                Diagnostic(
                    "PROJECT_DEFAULTS_DISABLED",
                    DiagnosticLevel.ERROR,
                    "Projektis peab olema lubatud serveripoolsete "
                    "vaikeväärtuste hindamine.",
                )
            )

        edge_connection = self._connection_info(edge_layer)
        node_connection = self._connection_info(node_layer)
        if not edge_connection or edge_connection != node_connection:
            diagnostics.append(
                Diagnostic(
                    "LAYER_CONNECTION_MISMATCH",
                    DiagnosticLevel.ERROR,
                    "Veetoru- ja veesõlmekiht ei kasuta sama PostGIS-i ühendust.",
                )
            )
            return

        group = project.transactionGroup(edge_layer.providerType(), edge_connection)
        if group is None or edge_layer not in group.layers() or node_layer not in group.layers():
            diagnostics.append(
                Diagnostic(
                    "TRANSACTION_GROUP_MISSING",
                    DiagnosticLevel.ERROR,
                    "Veetoru- ja veesõlmekiht ei kuulu samasse automaatsesse "
                    "tehingugruppi.",
                )
            )

    def _validate_provider_source(
        self, layer: QgsVectorLayer, diagnostics: list[Diagnostic]
    ) -> None:
        decoded = self._decode_source(layer)
        expected_table = (
            EDGE_TABLE
            if self._property(layer, "evel_topology_role") == EDGE_ROLE
            else NODE_TABLE
        )
        actual_table = str(decoded.get("table", "")).lower()
        actual_schema = str(decoded.get("schema", "")).lower()
        geometry_column = str(decoded.get("geometrycolumn", ""))
        if actual_table != expected_table or actual_schema != EXPECTED_SCHEMA:
            diagnostics.append(
                Diagnostic(
                    "LAYER_SOURCE_MISMATCH",
                    DiagnosticLevel.ERROR,
                    f"Kihi „{layer.name()}” andmeallikas peab olema "
                    f"{EXPECTED_SCHEMA}.{expected_table}.",
                    layer.id(),
                )
            )
        if geometry_column.upper() != EXPECTED_GEOMETRY_COLUMN:
            diagnostics.append(
                Diagnostic(
                    "LAYER_SOURCE_GEOMETRY_COLUMN_MISMATCH",
                    DiagnosticLevel.ERROR,
                    f"Kihi „{layer.name()}” andmeallika geomeetriaveerg peab "
                    "olema GEOM.",
                    layer.id(),
                )
            )

    @staticmethod
    def _validate_edit_capabilities(
        layer: QgsVectorLayer, diagnostics: list[Diagnostic]
    ) -> None:
        if layer.readOnly():
            diagnostics.append(
                Diagnostic(
                    "LAYER_READ_ONLY",
                    DiagnosticLevel.ERROR,
                    f"Kiht „{layer.name()}” on projektis kirjutuskaitstud.",
                    layer.id(),
                )
            )
            return
        provider = layer.dataProvider()
        if provider is None:
            return
        required = Qgis.VectorProviderCapability.AddFeatures
        if layer.geometryType() == Qgis.GeometryType.Line:
            required |= Qgis.VectorProviderCapability.ChangeAttributeValues
            required |= Qgis.VectorProviderCapability.ChangeGeometries
        if provider.capabilities() & required != required:
            diagnostics.append(
                Diagnostic(
                    "LAYER_EDIT_CAPABILITIES_MISSING",
                    DiagnosticLevel.ERROR,
                    f"Kihi „{layer.name()}” andmepakkujal puuduvad vajalikud "
                    "lisamise või muutmise õigused.",
                    layer.id(),
                )
            )

    @classmethod
    def _layer_table(cls, layer: QgsVectorLayer) -> str:
        metadata_table = cls._property(layer, "evel_project_table")
        if metadata_table:
            return metadata_table
        return str(cls._decode_source(layer).get("table", "")).lower()

    @staticmethod
    def _decode_source(layer: QgsVectorLayer) -> dict:
        try:
            return QgsProviderRegistry.instance().decodeUri(
                layer.providerType(), layer.source()
            )
        except (AttributeError, TypeError, ValueError):
            return {}

    @staticmethod
    def _connection_info(layer: QgsVectorLayer) -> str:
        if layer.providerType() != EXPECTED_PROVIDER:
            return ""
        try:
            return QgsDataSourceUri(layer.source()).connectionInfo(False)
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def _has_fields(layer: QgsVectorLayer, required: Iterable[str]) -> bool:
        actual = {field.name().upper() for field in layer.fields()}
        return set(required).issubset(actual)

    @staticmethod
    def _property(layer: QgsVectorLayer, key: str) -> str:
        return str(layer.customProperty(key, "")).strip().lower()

    @staticmethod
    def _truthy(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _TRUE_VALUES

    @staticmethod
    def _positive_int_property(layer: QgsVectorLayer, key: str) -> Optional[int]:
        try:
            value = int(layer.customProperty(key, ""))
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
