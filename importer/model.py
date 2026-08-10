"""Immutable data passed between the importer UI and SQL worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


NODE_TABLES = ("SN_WATER_NODE", "SN_SEWER_NODE")
DETAIL_TABLES = (
    "SN_WATER_MANHOLE",
    "SN_WATER_VALVE",
    "SN_FIRE_PLUG",
    "SN_SEWER_MANHOLE",
    "SN_SEWER_VALVE",
)
DUCT_TABLES = ("SN_WATER_DUCT", "SN_SEWER_DUCT")
TABLE_ORDER = (*NODE_TABLES, *DETAIL_TABLES, *DUCT_TABLES)
PRIMARY_KEYS = {
    "SN_WATER_NODE": "MSLINK",
    "SN_SEWER_NODE": "MSLINK",
    "SN_WATER_DUCT": "MSLINK",
    "SN_SEWER_DUCT": "MSLINK",
    "SN_WATER_MANHOLE": "ID",
    "SN_WATER_VALVE": "ID",
    "SN_FIRE_PLUG": "ID",
    "SN_SEWER_MANHOLE": "ID",
    "SN_SEWER_VALVE": "ID",
}
NODE_PARENT_TABLE = {
    "SN_WATER_MANHOLE": "SN_WATER_NODE",
    "SN_WATER_VALVE": "SN_WATER_NODE",
    "SN_FIRE_PLUG": "SN_WATER_NODE",
    "SN_SEWER_MANHOLE": "SN_SEWER_NODE",
    "SN_SEWER_VALVE": "SN_SEWER_NODE",
    "SN_WATER_DUCT": "SN_WATER_NODE",
    "SN_SEWER_DUCT": "SN_SEWER_NODE",
}
GEOMETRY_TABLES = {*NODE_TABLES, *DUCT_TABLES}


@dataclass(frozen=True)
class ImportRecord:
    local_id: int
    values: dict[str, object]
    geometry_wkb: bytes | None = None


@dataclass(frozen=True)
class ImportPlan:
    package_path: Path
    package_sha256: str
    records: dict[str, tuple[ImportRecord, ...]]
    package_info: dict[str, str]
    referenced_constant_ids: frozenset[int]
    warnings: tuple[str, ...] = ()

    @property
    def total_count(self) -> int:
        return sum(len(rows) for rows in self.records.values())

    def count(self, table: str) -> int:
        return len(self.records.get(table, ()))


@dataclass(frozen=True)
class DatabaseTarget:
    schema: str
    connection_dsn: str = field(repr=False)
    connection_key: tuple[str, str, str, str]
    table_columns: dict[str, frozenset[str]]
    project_layer_ids: tuple[str, ...]


@dataclass(frozen=True)
class ImportRunResult:
    dry_run: bool
    inserted_counts: dict[str, int]
    total_count: int
    server_id_ranges: dict[str, tuple[int, int] | None]
