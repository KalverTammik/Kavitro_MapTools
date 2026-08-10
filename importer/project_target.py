"""Discover the physical EVEL PostGIS tables behind the open project."""

from __future__ import annotations

from qgis.core import QgsDataSourceUri, QgsProject, QgsVectorLayer

from .model import TABLE_ORDER, DatabaseTarget


class EvelImportTargetError(RuntimeError):
    """Raised when the open project is not a safe importer target."""


class EvelImportTargetInspector:
    EXPECTED_SCHEMA = "evel"

    def inspect(self, project: QgsProject) -> DatabaseTarget:
        candidates: dict[str, list[tuple[QgsVectorLayer, QgsDataSourceUri]]] = {
            table: [] for table in TABLE_ORDER
        }
        postgres_layers = []
        for layer in project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if layer.providerType() != "postgres" or not layer.isValid():
                continue
            uri = QgsDataSourceUri(layer.source())
            postgres_layers.append((layer, uri))
            table = uri.table().upper()
            schema = uri.schema().casefold()
            if schema != self.EXPECTED_SCHEMA or table not in candidates:
                continue
            candidates[table].append((layer, uri))

        missing = [table for table, rows in candidates.items() if not rows]
        if missing:
            raise EvelImportTargetError(
                "Projektis puuduvad importimiseks vajalikud PostGIS-tabelid: "
                + ", ".join(missing)
            )

        selected = {
            table: min(
                rows,
                key=lambda item: (
                    bool(item[0].subsetString()),
                    len(item[0].fields()),
                    item[0].name(),
                ),
            )
            for table, rows in candidates.items()
        }
        first_uri = selected[TABLE_ORDER[0]][1]
        connection_key = self._connection_key(first_uri)
        for table, (_layer, uri) in selected.items():
            if self._connection_key(uri) != connection_key:
                raise EvelImportTargetError(
                    f"Tabel {table} kasutab teist PostgreSQL-ühendust. "
                    "Import peab toimuma ühte andmebaasi."
                )
        if any(
            layer.isEditable()
            and self._connection_key(uri) == connection_key
            for layer, uri in postgres_layers
        ):
            raise EvelImportTargetError(
                "Enne importi salvesta või tühista kõik sama andmebaasi "
                "projekti redigeerimised ja lõpeta redigeerimisrežiim."
            )

        table_columns = {
            table: frozenset(
                field.name().upper() for field in layer.fields()
            )
            for table, (layer, _uri) in selected.items()
        }
        relevant_ids = tuple(
            layer.id()
            for layer, uri in postgres_layers
            if (
                uri.schema().casefold() == self.EXPECTED_SCHEMA
                and uri.table().upper() in set(TABLE_ORDER)
            )
        )
        return DatabaseTarget(
            schema=self.EXPECTED_SCHEMA,
            connection_dsn=first_uri.connectionInfo(False),
            connection_key=connection_key,
            table_columns=table_columns,
            project_layer_ids=relevant_ids,
        )

    def is_available(self, project: QgsProject) -> tuple[bool, str]:
        try:
            self.inspect(project)
        except EvelImportTargetError as error:
            return False, str(error)
        return True, (
            "Aktiivses projektis on kõik EVEL-i impordi sihttabelid "
            "ühes PostgreSQL-andmebaasis."
        )

    @staticmethod
    def _connection_key(uri: QgsDataSourceUri) -> tuple[str, str, str, str]:
        return (
            uri.host().casefold(),
            str(uri.port()),
            uri.database().casefold(),
            uri.username().casefold(),
        )
