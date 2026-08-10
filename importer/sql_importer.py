"""One-transaction PostgreSQL importer for an EVEL review package."""

from __future__ import annotations

import re
from collections.abc import Callable

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from .model import (
    DETAIL_TABLES,
    DUCT_TABLES,
    GEOMETRY_TABLES,
    NODE_PARENT_TABLE,
    NODE_TABLES,
    PRIMARY_KEYS,
    TABLE_ORDER,
    DatabaseTarget,
    ImportPlan,
    ImportRecord,
    ImportRunResult,
)


class EvelSqlImportError(RuntimeError):
    """Raised after the import transaction has been rolled back."""


class EvelSqlImportCanceled(EvelSqlImportError):
    """Raised when the user cancels an active import."""


class EvelSqlImporter:
    """Validate and import all records through one psycopg2 transaction."""

    SRID = 3301
    BATCH_SIZE = 500
    LOCK_NAME = "EVEL_network_tools_import"

    def run(
        self,
        plan: ImportPlan,
        target: DatabaseTarget,
        *,
        dry_run: bool,
        progress: Callable[[int, int, str], None] | None = None,
        is_canceled: Callable[[], bool] | None = None,
    ) -> ImportRunResult:
        progress = progress or (lambda _current, _total, _message: None)
        is_canceled = is_canceled or (lambda: False)
        total = max(plan.total_count, 1)
        connection = None
        try:
            self._package_preflight(plan)
            connection = psycopg2.connect(
                target.connection_dsn,
                application_name="EVEL Network Tools importer",
            )
            connection.autocommit = False
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '30min'")
                cursor.execute("SET LOCAL lock_timeout = '15s'")
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (self.LOCK_NAME,),
                )
                self._check_canceled(is_canceled)
                progress(0, total, "Kontrollin sihtandmebaasi ja õigusi…")
                database_columns = self._database_preflight(
                    cursor,
                    plan,
                    target,
                )
                self._check_existing_overlap(cursor, plan, target)
                server_ids = self._assign_server_ids(
                    cursor,
                    plan,
                    target,
                    dry_run=dry_run,
                )

                inserted_counts = {}
                completed = 0
                for table in TABLE_ORDER:
                    rows = plan.records.get(table, ())
                    if not rows:
                        inserted_counts[table] = 0
                        continue
                    message = self._table_message(table, dry_run)
                    inserted = self._insert_table(
                        cursor,
                        table,
                        rows,
                        target,
                        database_columns[table],
                        server_ids,
                        completed,
                        total,
                        message,
                        progress,
                        is_canceled,
                    )
                    inserted_counts[table] = inserted
                    completed += inserted

                self._check_canceled(is_canceled)
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                if dry_run:
                    connection.rollback()
                    final_message = (
                        "SQL-kontroll õnnestus. Kõik proovikirjed "
                        "pöörati tagasi."
                    )
                else:
                    connection.commit()
                    final_message = "Kõik EVEL-i andmed on imporditud."
                progress(total, total, final_message)
                return ImportRunResult(
                    dry_run=dry_run,
                    inserted_counts=inserted_counts,
                    total_count=sum(inserted_counts.values()),
                    server_id_ranges={
                        table: self._id_range(server_ids.get(table, {}))
                        for table in TABLE_ORDER
                    },
                )
        except EvelSqlImportCanceled:
            if connection is not None:
                connection.rollback()
            raise
        except Exception as error:
            if connection is not None:
                connection.rollback()
            if isinstance(error, EvelSqlImportError):
                raise
            raise EvelSqlImportError(
                "SQL-import ebaõnnestus ja kõik muudatused pöörati tagasi: "
                + self._safe_error(error)
            ) from error
        finally:
            if connection is not None:
                connection.close()

    def _package_preflight(self, plan: ImportPlan) -> None:
        problems = []
        for table in DETAIL_TABLES:
            details_by_node: dict[int, list[int]] = {}
            for record in plan.records.get(table, ()):
                node_id = int(record.values["NODE_ID"])
                details_by_node.setdefault(node_id, []).append(record.local_id)
            duplicates = {
                node_id: detail_ids
                for node_id, detail_ids in details_by_node.items()
                if len(detail_ids) > 1
            }
            if not duplicates:
                continue
            samples = ", ".join(
                f"NODE_ID {node_id} (detailid "
                f"{'/'.join(map(str, detail_ids))})"
                for node_id, detail_ids in list(duplicates.items())[:8]
            )
            problems.append(
                f"{table}: {len(duplicates)} sõlme – {samples}"
            )
        if problems:
            raise EvelSqlImportError(
                "Kontrollpaketis on ühe baassõlmega seotud mitu sama liigi "
                "detailkirjet. EVEL-i andmemudel lubab ühe detaili liigi "
                "kohta ühe kirje. Paranda kontrollpakett: "
                + "; ".join(problems)
            )

    def _database_preflight(
        self,
        cursor,
        plan: ImportPlan,
        target: DatabaseTarget,
    ) -> dict[str, frozenset[str]]:
        schema = target.schema
        cursor.execute(
            """
            SELECT table_name, column_name, is_identity, column_default
            FROM information_schema.columns
            WHERE table_schema = %s
              AND upper(table_name) = ANY(%s)
            """,
            (schema, list(TABLE_ORDER)),
        )
        rows = cursor.fetchall()
        columns: dict[str, set[str]] = {table: set() for table in TABLE_ORDER}
        key_generation = {}
        for table_name, column_name, is_identity, default in rows:
            table = str(table_name).upper()
            column = str(column_name).upper()
            if table not in columns:
                continue
            columns[table].add(column)
            if column == PRIMARY_KEYS[table]:
                key_generation[table] = (is_identity, default)
        missing_tables = [table for table, fields in columns.items() if not fields]
        if missing_tables:
            raise EvelSqlImportError(
                "Sihtandmebaasis puuduvad tabelid: "
                + ", ".join(missing_tables)
            )
        for table in TABLE_ORDER:
            primary_key = PRIMARY_KEYS[table]
            if primary_key not in columns[table]:
                raise EvelSqlImportError(
                    f"Sihttabelis {table} puudub primaarvõti {primary_key}."
                )
            identity, default = key_generation.get(table, (None, None))
            if identity != "YES" and not default:
                raise EvelSqlImportError(
                    f"Sihttabeli {table}.{primary_key} väärtust ei loo "
                    "server. Käivita generaatori „Uuenda andmemudelit“."
                )
            cursor.execute(
                "SELECT has_table_privilege(current_user, %s, 'INSERT')",
                (f"{schema}.{table.lower()}",),
            )
            if not bool(cursor.fetchone()[0]):
                raise EvelSqlImportError(
                    f"Andmebaasikasutajal puudub INSERT õigus tabelile {table}."
                )

            package_non_null = {
                field_name
                for record in plan.records.get(table, ())
                for field_name, value in record.values.items()
                if value is not None
            }
            missing_columns = package_non_null - columns[table]
            if missing_columns:
                raise EvelSqlImportError(
                    f"Sihttabelist {table} puuduvad paketis täidetud väljad: "
                    + ", ".join(sorted(missing_columns))
                )

        if plan.referenced_constant_ids:
            cursor.execute(
                sql.SQL(
                    "SELECT {} FROM {}.{} WHERE {} = ANY(%s)"
                ).format(
                    sql.Identifier("ID"),
                    sql.Identifier(schema),
                    sql.Identifier("sn_constant"),
                    sql.Identifier("ID"),
                ),
                (list(sorted(plan.referenced_constant_ids)),),
            )
            existing = {int(row[0]) for row in cursor.fetchall()}
            missing = sorted(plan.referenced_constant_ids - existing)
            if missing:
                raise EvelSqlImportError(
                    "Sihtandmebaasi SN_CONSTANT tabelist puuduvad paketis "
                    "kasutatavad ID-d: "
                    + ", ".join(str(value) for value in missing)
                    + ". Käivita generaatori „Uuenda andmemudelit“."
                )

        cursor.execute(
            """
            SELECT upper(f_table_name), srid
            FROM public.geometry_columns
            WHERE f_table_schema = %s
              AND upper(f_table_name) = ANY(%s)
            """,
            (schema, list(GEOMETRY_TABLES)),
        )
        srids = {str(table): int(srid) for table, srid in cursor.fetchall()}
        for table in GEOMETRY_TABLES:
            if srids.get(table) != self.SRID:
                raise EvelSqlImportError(
                    f"Sihttabeli {table} geomeetria SRID peab olema "
                    f"{self.SRID}."
                )
        return {
            table: frozenset(fields) for table, fields in columns.items()
        }

    def _check_existing_overlap(
        self,
        cursor,
        plan: ImportPlan,
        target: DatabaseTarget,
    ) -> None:
        samples = []
        for table in DUCT_TABLES:
            for record in plan.records.get(table, ()):
                network_id = record.values.get("NETWORK_ID")
                if record.geometry_wkb is None:
                    continue
                samples.append(
                    (
                        table,
                        network_id,
                        psycopg2.Binary(record.geometry_wkb),
                    )
                )
        if not samples:
            return
        cursor.execute(
            """
            CREATE TEMP TABLE _evel_import_overlap (
                table_name text NOT NULL,
                network_id integer,
                geom geometry(Geometry, 3301) NOT NULL
            ) ON COMMIT DROP
            """
        )
        query = (
            "INSERT INTO _evel_import_overlap "
            "(table_name, network_id, geom) VALUES %s"
        )
        template = "(%s, %s, ST_SetSRID(ST_GeomFromWKB(%s), 3301))"
        for start in range(0, len(samples), self.BATCH_SIZE):
            execute_values(
                cursor,
                query,
                samples[start : start + self.BATCH_SIZE],
                template=template,
                page_size=self.BATCH_SIZE,
            )
        cursor.execute(
            "CREATE INDEX ON _evel_import_overlap USING gist (geom)"
        )
        cursor.execute("ANALYZE _evel_import_overlap")
        overlaps = 0
        for table in DUCT_TABLES:
            cursor.execute(
                sql.SQL(
                    """
                    SELECT count(*)
                    FROM {}.{} AS target
                    JOIN _evel_import_overlap AS source
                      ON source.table_name = %s
                     AND source.network_id IS NOT DISTINCT FROM target.{}
                     AND ST_Equals(source.geom, target.{})
                    """
                ).format(
                    sql.Identifier(target.schema),
                    sql.Identifier(table.lower()),
                    sql.Identifier("NETWORK_ID"),
                    sql.Identifier("GEOM"),
                ),
                (table,),
            )
            overlaps += int(cursor.fetchone()[0])
        if overlaps:
            raise EvelSqlImportError(
                f"Sihtandmebaasis on juba {overlaps} paketiga kattuvat toru. "
                "Importer on lisamisrežiimis ega impordi sama võrku teist korda."
            )

    def _assign_server_ids(
        self,
        cursor,
        plan: ImportPlan,
        target: DatabaseTarget,
        *,
        dry_run: bool,
    ) -> dict[str, dict[int, int]]:
        result = {}
        for table in TABLE_ORDER:
            records = plan.records.get(table, ())
            if not records:
                result[table] = {}
                continue
            primary_key = PRIMARY_KEYS[table]
            if dry_run:
                cursor.execute(
                    sql.SQL("SELECT COALESCE(MAX({}), 0) FROM {}.{}").format(
                        sql.Identifier(primary_key),
                        sql.Identifier(target.schema),
                        sql.Identifier(table.lower()),
                    )
                )
                start = int(cursor.fetchone()[0]) + 1_000_000
                ids = list(range(start, start + len(records)))
            else:
                cursor.execute(
                    "SELECT pg_get_serial_sequence(%s, %s)",
                    (f"{target.schema}.{table.lower()}", primary_key),
                )
                sequence = cursor.fetchone()[0]
                if not sequence:
                    raise EvelSqlImportError(
                        f"Tabeli {table}.{primary_key} IDENTITY jada ei leitud."
                    )
                cursor.execute(
                    "SELECT nextval(%s::regclass) "
                    "FROM generate_series(1, %s)",
                    (sequence, len(records)),
                )
                ids = [int(row[0]) for row in cursor.fetchall()]
            result[table] = {
                record.local_id: server_id
                for record, server_id in zip(records, ids)
            }
        return result

    def _insert_table(
        self,
        cursor,
        table: str,
        records: tuple[ImportRecord, ...],
        target: DatabaseTarget,
        database_columns: frozenset[str],
        server_ids: dict[str, dict[int, int]],
        completed: int,
        total: int,
        message: str,
        progress: Callable[[int, int, str], None],
        is_canceled: Callable[[], bool],
    ) -> int:
        primary_key = PRIMARY_KEYS[table]
        fields = sorted(
            {
                field_name
                for record in records
                for field_name, value in record.values.items()
                if value is not None and field_name in database_columns
            }
            - {"NODE_ID", "BEGIN_NODE_ID", "END_NODE_ID"}
        )
        relation_fields = []
        if table in DETAIL_TABLES:
            relation_fields = ["NODE_ID"]
        elif table in DUCT_TABLES:
            relation_fields = ["BEGIN_NODE_ID", "END_NODE_ID"]
        columns = [primary_key, *fields, *relation_fields]
        if table in GEOMETRY_TABLES:
            columns.append("GEOM")

        query = sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
            sql.Identifier(target.schema),
            sql.Identifier(table.lower()),
            sql.SQL(", ").join(sql.Identifier(name) for name in columns),
        )
        value_placeholders = ["%s"] * (len(columns) - int(table in GEOMETRY_TABLES))
        if table in GEOMETRY_TABLES:
            value_placeholders.append(
                f"ST_SetSRID(ST_GeomFromWKB(%s), {self.SRID})"
            )
        template = "(" + ", ".join(value_placeholders) + ")"

        inserted = 0
        for start in range(0, len(records), self.BATCH_SIZE):
            self._check_canceled(is_canceled)
            batch = records[start : start + self.BATCH_SIZE]
            values = [
                self._record_values(
                    table,
                    record,
                    fields,
                    relation_fields,
                    server_ids,
                )
                for record in batch
            ]
            execute_values(
                cursor,
                query.as_string(cursor),
                values,
                template=template,
                page_size=self.BATCH_SIZE,
            )
            inserted += len(batch)
            progress(completed + inserted, total, message)
        return inserted

    def _record_values(
        self,
        table: str,
        record: ImportRecord,
        fields: list[str],
        relation_fields: list[str],
        server_ids: dict[str, dict[int, int]],
    ) -> tuple:
        values = [server_ids[table][record.local_id]]
        values.extend(record.values.get(field) for field in fields)
        if relation_fields:
            parent = NODE_PARENT_TABLE[table]
            for field in relation_fields:
                local_node_id = int(record.values[field])
                try:
                    values.append(server_ids[parent][local_node_id])
                except KeyError as error:
                    raise EvelSqlImportError(
                        f"{table} kohalik ID {record.local_id} viitab "
                        f"puuduvale sõlmele {local_node_id}."
                    ) from error
        if table in GEOMETRY_TABLES:
            if record.geometry_wkb is None:
                raise EvelSqlImportError(
                    f"{table} kohalikul ID-l {record.local_id} puudub "
                    "geomeetria."
                )
            values.append(psycopg2.Binary(record.geometry_wkb))
        return tuple(values)

    @staticmethod
    def _check_canceled(is_canceled: Callable[[], bool]) -> None:
        if is_canceled():
            raise EvelSqlImportCanceled(
                "Import katkestati ja kõik muudatused pöörati tagasi."
            )

    @staticmethod
    def _id_range(values: dict[int, int]) -> tuple[int, int] | None:
        if not values:
            return None
        server_ids = list(values.values())
        return min(server_ids), max(server_ids)

    @staticmethod
    def _table_message(table: str, dry_run: bool) -> str:
        action = "Kontrollin" if dry_run else "Impordin"
        labels = {
            "SN_WATER_NODE": "veesõlmi",
            "SN_SEWER_NODE": "kanalisatsioonisõlmi",
            "SN_WATER_MANHOLE": "veekaevusid",
            "SN_WATER_VALVE": "vee sulgeseadmeid",
            "SN_FIRE_PLUG": "hüdrante",
            "SN_SEWER_MANHOLE": "kanalisatsioonikaevusid",
            "SN_SEWER_VALVE": "kanalisatsiooni sulgeseadmeid",
            "SN_WATER_DUCT": "veetorusid",
            "SN_SEWER_DUCT": "kanalisatsioonitorusid",
        }
        return f"{action} {labels[table]}…"

    @staticmethod
    def _safe_error(error: Exception) -> str:
        text = str(error).strip() or error.__class__.__name__
        text = re.sub(
            r"(?i)(password\\s*=\\s*)(?:'[^']*'|\\S+)",
            r"\\1'***'",
            text,
        )
        return text[:2000]
