"""Read and validate the editable EVEL client GeoPackage."""

from __future__ import annotations

import hashlib
from pathlib import Path

from qgis.PyQt.QtCore import QDate, QDateTime, QTime
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsVariantUtils,
    QgsVectorLayer,
)

from .model import (
    DETAIL_TABLES,
    DUCT_TABLES,
    GEOMETRY_TABLES,
    NODE_PARENT_TABLE,
    NODE_TABLES,
    PRIMARY_KEYS,
    TABLE_ORDER,
    ImportPlan,
    ImportRecord,
)


class EvelImportPackageError(RuntimeError):
    """Raised when a selected GeoPackage is not safe to import."""


class EvelImportPackageReader:
    EXPECTED_PACKAGE_TYPE = "EVEL kliendi kontrollpakett"
    PROVIDER_FIELDS = frozenset({"FID"})
    CONSTANT_FIELDS = frozenset(
        {
            "NETWORK_ID",
            "NETTYPE_ID",
            "DUCT_TYPE_ID",
            "MATERIAL_ID",
            "DIAMETER_TYPE_ID",
            "DIAMETER_ID",
            "FORM_CODE_ID",
            "PRESSURE_CLASS_ID",
            "FIRMNESS_CLASS_ID",
            "LOCATION_ID",
            "CONDITION_CLASS_ID",
            "USAGE_STATE",
            "OWNER_ID",
            "LESSEE_ID",
            "LOCATION_ACCURACY_ID",
            "HEIGHT_ACCURACY_ID",
            "MAPPING_METHOD_ID",
            "TYPE_AQUA_ID",
            "TYPE_ID",
            "PLUG_TYPE_ID",
            "LID_TYPE_ID",
            "LID_MATERIAL_ID",
            "LID_SHAPE_ID",
            "LID_DIAMETER_ID",
            "LID_CAPACITY_ID",
            "VALVE_HAND",
        }
    )

    def read(self, path: str | Path) -> ImportPlan:
        package_path = Path(path)
        if not package_path.is_file():
            raise EvelImportPackageError(
                "Valitud GeoPackage'i faili ei leitud."
            )
        if package_path.suffix.casefold() != ".gpkg":
            raise EvelImportPackageError(
                "Importer toetab EVEL-i kontrollpaketi .gpkg faili."
            )

        info = self._read_package_info(package_path)
        if info.get("PACKAGE_TYPE") != self.EXPECTED_PACKAGE_TYPE:
            raise EvelImportPackageError(
                "GeoPackage ei ole EVEL-i kliendi kontrollpakett."
            )
        if info.get("DATABASE_WRITE", "").casefold() != "false":
            raise EvelImportPackageError(
                "Paketi päritolu või DATABASE_WRITE tunnus ei vasta "
                "kontrollpaketi lepingule."
            )

        layers = {
            table: self._layer(package_path, table)
            for table in TABLE_ORDER
        }
        invalid = [table for table, layer in layers.items() if not layer.isValid()]
        if invalid:
            raise EvelImportPackageError(
                "Kontrollpaketist puuduvad EVEL-i kihid: "
                + ", ".join(invalid)
            )

        geometry_normalizations: dict[str, int] = {}
        records = {
            table: tuple(
                self._records(table, layer, geometry_normalizations)
            )
            for table, layer in layers.items()
        }
        self._validate_local_relations(records)
        records, duplicate_warnings = self._deduplicate_exact_details(records)
        warnings = [
            *self._warnings(
                package_path,
                records,
                geometry_normalizations,
            ),
            *duplicate_warnings,
        ]
        constant_ids = self._constant_ids(records)
        return ImportPlan(
            package_path=package_path,
            package_sha256=self._sha256(package_path),
            records=records,
            package_info=info,
            referenced_constant_ids=frozenset(constant_ids),
            warnings=tuple(warnings),
        )

    def _deduplicate_exact_details(
        self,
        records: dict[str, tuple[ImportRecord, ...]],
    ) -> tuple[
        dict[str, tuple[ImportRecord, ...]],
        list[str],
    ]:
        normalized = dict(records)
        warnings = []
        for table in DETAIL_TABLES:
            rows_by_node: dict[int, list[ImportRecord]] = {}
            for record in records[table]:
                node_id = int(record.values["NODE_ID"])
                rows_by_node.setdefault(node_id, []).append(record)

            removed_ids = []
            kept_rows = []
            for rows in rows_by_node.values():
                ordered = sorted(rows, key=lambda record: record.local_id)
                first = ordered[0]
                kept_rows.append(first)
                if len(ordered) == 1:
                    continue
                if all(row.values == first.values for row in ordered[1:]):
                    removed_ids.extend(
                        row.local_id for row in ordered[1:]
                    )
                else:
                    kept_rows.extend(ordered[1:])

            normalized[table] = tuple(
                sorted(kept_rows, key=lambda record: record.local_id)
            )
            if removed_ids:
                warnings.append(
                    f"{table}: importimisel jäetakse välja "
                    f"{len(removed_ids)} täpset duplikaati "
                    f"(detailide ID-d "
                    f"{', '.join(map(str, sorted(removed_ids)))})."
                )
        return normalized, warnings

    def _records(
        self,
        table: str,
        layer: QgsVectorLayer,
        geometry_normalizations: dict[str, int],
    ):
        primary_key = PRIMARY_KEYS[table]
        required_fields = {primary_key}
        if table in DETAIL_TABLES:
            required_fields.add("NODE_ID")
        if table in DUCT_TABLES:
            required_fields.update({"BEGIN_NODE_ID", "END_NODE_ID"})
        actual_fields = {field.name().upper() for field in layer.fields()}
        missing = required_fields - actual_fields
        if missing:
            raise EvelImportPackageError(
                f"Kihil {table} puuduvad väljad: {', '.join(sorted(missing))}."
            )

        if table in GEOMETRY_TABLES:
            if not layer.isSpatial():
                raise EvelImportPackageError(
                    f"Kiht {table} peab sisaldama geomeetriat."
                )
            if layer.crs().authid().upper() != "EPSG:3301":
                raise EvelImportPackageError(
                    f"Kihi {table} koordinaatsüsteem peab olema EPSG:3301."
                )

        seen_ids = set()
        field_names = [field.name().upper() for field in layer.fields()]
        for feature in layer.getFeatures():
            local_id = self._positive_int(
                feature[primary_key],
                f"{table}.{primary_key}",
            )
            if local_id in seen_ids:
                raise EvelImportPackageError(
                    f"Kihil {table} kordub kohalik ID {local_id}."
                )
            seen_ids.add(local_id)
            geometry_wkb = None
            if table in GEOMETRY_TABLES:
                geometry = feature.geometry()
                if (
                    not feature.hasGeometry()
                    or geometry.isNull()
                    or geometry.isEmpty()
                ):
                    raise EvelImportPackageError(
                        f"Kihi {table} objektil {local_id} puudub geomeetria."
                    )
                expected_type = (
                    Qgis.GeometryType.Point
                    if table in NODE_TABLES
                    else Qgis.GeometryType.Line
                )
                if geometry.type() != expected_type:
                    raise EvelImportPackageError(
                        f"Kihi {table} objekti {local_id} geomeetriatüüp "
                        "ei vasta EVEL-i mudelile."
                    )
                if geometry.isMultipart():
                    parts = geometry.asGeometryCollection()
                    if len(parts) != 1:
                        raise EvelImportPackageError(
                            f"Kihi {table} objekti {local_id} geomeetria "
                            f"koosneb {len(parts)} eraldiseisvast osast. "
                            "EVEL-i üks toru või sõlm peab olema üheosaline."
                        )
                    geometry = parts[0]
                    geometry_normalizations[table] = (
                        geometry_normalizations.get(table, 0) + 1
                    )
                geometry_wkb = bytes(geometry.asWkb())

            values = {
                field_name: self._python_value(feature[field_name])
                for field_name in field_names
                if (
                    field_name != primary_key
                    and field_name not in self.PROVIDER_FIELDS
                )
            }
            yield ImportRecord(
                local_id=local_id,
                values=values,
                geometry_wkb=geometry_wkb,
            )

    def _validate_local_relations(
        self,
        records: dict[str, tuple[ImportRecord, ...]],
    ) -> None:
        node_ids = {
            table: {record.local_id for record in records[table]}
            for table in NODE_TABLES
        }
        for table in DETAIL_TABLES:
            parent = NODE_PARENT_TABLE[table]
            for record in records[table]:
                node_id = self._positive_int(
                    record.values.get("NODE_ID"),
                    f"{table}.NODE_ID",
                )
                if node_id not in node_ids[parent]:
                    raise EvelImportPackageError(
                        f"{table} kohalik ID {record.local_id} viitab "
                        f"puuduvale sõlmele {node_id}."
                    )
        for table in DUCT_TABLES:
            parent = NODE_PARENT_TABLE[table]
            for record in records[table]:
                for field_name in ("BEGIN_NODE_ID", "END_NODE_ID"):
                    node_id = self._positive_int(
                        record.values.get(field_name),
                        f"{table}.{field_name}",
                    )
                    if node_id not in node_ids[parent]:
                        raise EvelImportPackageError(
                            f"{table} kohalik ID {record.local_id} viitab "
                            f"puuduvale sõlmele {node_id}."
                        )

    def _constant_ids(
        self,
        records: dict[str, tuple[ImportRecord, ...]],
    ) -> set[int]:
        values = set()
        for rows in records.values():
            for record in rows:
                for field_name, value in record.values.items():
                    if field_name not in self.CONSTANT_FIELDS:
                        continue
                    if value is None:
                        continue
                    try:
                        constant_id = int(value)
                    except (TypeError, ValueError) as error:
                        raise EvelImportPackageError(
                            f"Välja {field_name} väärtus {value!r} ei ole "
                            "EVEL-i klassifikaatori ID."
                        ) from error
                    values.add(constant_id)
        return values

    def _warnings(
        self,
        package_path: Path,
        records: dict[str, tuple[ImportRecord, ...]],
        geometry_normalizations: dict[str, int],
    ) -> list[str]:
        warnings = []
        excluded = self._layer(package_path, "EVEL_SIDUMATA_OBJEKTID")
        if excluded.isValid() and excluded.featureCount():
            warnings.append(
                f"{excluded.featureCount()} sidumata objekti ei impordita."
            )
        empty_roles = sum(
            1
            for table in DUCT_TABLES
            for record in records[table]
            if record.values.get("DUCT_TYPE_ID") is None
        )
        if empty_roles:
            warnings.append(
                f"{empty_roles} toru otstarve jääb tühjaks."
            )
        review_notes = sum(
            1
            for table in DUCT_TABLES
            for record in records[table]
            if str(record.values.get("NOTE") or "").casefold()
            == "kontrollida"
        )
        if review_notes:
            warnings.append(
                f"{review_notes} toru NOTE väärtus on „kontrollida“."
            )
        normalized_geometry_count = sum(geometry_normalizations.values())
        if normalized_geometry_count:
            warnings.append(
                f"{normalized_geometry_count} üheosalist multipart-"
                "geomeetriat teisendatakse importimisel EVEL-i "
                "üheosaliseks geomeetriaks."
            )
        for table in DETAIL_TABLES:
            details_by_node: dict[int, int] = {}
            for record in records[table]:
                node_id = int(record.values["NODE_ID"])
                details_by_node[node_id] = details_by_node.get(node_id, 0) + 1
            duplicate_count = sum(
                count > 1 for count in details_by_node.values()
            )
            if duplicate_count:
                warnings.append(
                    f"{table}: {duplicate_count} sõlmel on mitu sama liigi "
                    "detailkirjet; SQL-import blokeeritakse."
                )
        return warnings

    def _read_package_info(self, path: Path) -> dict[str, str]:
        layer = self._layer(path, "EVEL_PACKAGE_INFO")
        if not layer.isValid():
            raise EvelImportPackageError(
                "GeoPackage'is puudub EVEL_PACKAGE_INFO tabel."
            )
        fields = {field.name().upper() for field in layer.fields()}
        if not {"KEY", "VALUE"}.issubset(fields):
            raise EvelImportPackageError(
                "EVEL_PACKAGE_INFO tabeli struktuur on vigane."
            )
        return {
            str(feature["KEY"] or ""): str(feature["VALUE"] or "")
            for feature in layer.getFeatures()
        }

    @staticmethod
    def _layer(path: Path, table: str) -> QgsVectorLayer:
        return QgsVectorLayer(
            f"{path}|layername={table}",
            table,
            "ogr",
        )

    @staticmethod
    def _python_value(value):
        if value is None or QgsVariantUtils.isNull(value):
            return None
        if isinstance(value, QDateTime):
            return value.toPyDateTime() if value.isValid() else None
        if isinstance(value, QDate):
            return value.toPyDate() if value.isValid() else None
        if isinstance(value, QTime):
            return value.toPyTime() if value.isValid() else None
        if isinstance(value, bytearray):
            return bytes(value)
        return value

    @staticmethod
    def _positive_int(value, label: str) -> int:
        if value is None or QgsVariantUtils.isNull(value):
            raise EvelImportPackageError(f"{label} on tühi.")
        try:
            result = int(value)
        except (TypeError, ValueError) as error:
            raise EvelImportPackageError(
                f"{label} ei ole täisarv."
            ) from error
        if result <= 0:
            raise EvelImportPackageError(
                f"{label} peab olema positiivne kohalik ID."
            )
        return result

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
