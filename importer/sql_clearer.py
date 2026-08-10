"""Transactional clearing of the nine EVEL importer target tables."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import psycopg2
from psycopg2 import sql

from .model import (
    DETAIL_TABLES,
    DUCT_TABLES,
    NODE_TABLES,
    TABLE_ORDER,
    DatabaseTarget,
)


CLEAR_ORDER = (*DETAIL_TABLES, *DUCT_TABLES, *NODE_TABLES)


@dataclass(frozen=True)
class ClearPreview:
    counts: dict[str, int]
    dependent_counts: dict[str, int]
    blockers: tuple[str, ...]

    @property
    def total_count(self) -> int:
        return sum(self.counts.values()) + sum(self.dependent_counts.values())


@dataclass(frozen=True)
class ClearRunResult:
    dry_run: bool
    deleted_counts: dict[str, int]

    @property
    def total_count(self) -> int:
        return sum(self.deleted_counts.values())


class EvelSqlClearError(RuntimeError):
    """Raised after a clear transaction has been rolled back."""


class EvelSqlClearCanceled(EvelSqlClearError):
    """Raised when the user cancels an active clear operation."""


class EvelSqlClearer:
    """Delete importer target rows in dependency order and one transaction."""

    LOCK_NAME = "EVEL_network_tools_import"

    def preview(self, target: DatabaseTarget) -> ClearPreview:
        connection = None
        try:
            connection = psycopg2.connect(
                target.connection_dsn,
                application_name="EVEL Network Tools clear preview",
            )
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor() as cursor:
                preview, _clear_order = self._preflight(cursor, target)
            connection.rollback()
            return preview
        except Exception as error:
            if connection is not None:
                connection.rollback()
            if isinstance(error, EvelSqlClearError):
                raise
            raise EvelSqlClearError(
                "Andmete tühjendamise eelkontroll ebaõnnestus: "
                + self._safe_error(error)
            ) from error
        finally:
            if connection is not None:
                connection.close()

    def run(
        self,
        target: DatabaseTarget,
        *,
        dry_run: bool,
        progress: Callable[[int, int, str], None] | None = None,
        is_canceled: Callable[[], bool] | None = None,
    ) -> ClearRunResult:
        progress = progress or (lambda _current, _total, _message: None)
        is_canceled = is_canceled or (lambda: False)
        connection = None
        try:
            connection = psycopg2.connect(
                target.connection_dsn,
                application_name="EVEL Network Tools clearer",
            )
            connection.autocommit = False
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '30min'")
                cursor.execute("SET LOCAL lock_timeout = '15s'")
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (self.LOCK_NAME,),
                )
                preview, clear_order = self._preflight(cursor, target)
                if preview.blockers:
                    raise EvelSqlClearError(
                        "Sihttabeleid ei saa tühjendada, sest seotud andmed "
                        "asuvad teistes EVEL-i tabelites: "
                        + "; ".join(preview.blockers)
                    )

                total = max(preview.total_count, 1)
                completed = 0
                deleted_counts = {}
                for table in clear_order:
                    self._check_canceled(is_canceled)
                    cursor.execute(
                        sql.SQL("DELETE FROM {}.{}").format(
                            sql.Identifier(target.schema),
                            sql.Identifier(table.lower()),
                        )
                    )
                    deleted = max(int(cursor.rowcount), 0)
                    deleted_counts[table] = deleted
                    completed += deleted
                    progress(
                        min(completed, total),
                        total,
                        f"{'Kontrollin' if dry_run else 'Tühjendan'} "
                        f"tabelit {table}…",
                    )

                self._check_canceled(is_canceled)
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                if dry_run:
                    connection.rollback()
                else:
                    connection.commit()
                progress(
                    total,
                    total,
                    (
                        "Tühjendamise SQL-kontroll õnnestus; muudatused "
                        "pöörati tagasi."
                        if dry_run
                        else "Importeri sihttabelid on tühjendatud."
                    ),
                )
                return ClearRunResult(
                    dry_run=dry_run,
                    deleted_counts=deleted_counts,
                )
        except EvelSqlClearCanceled:
            if connection is not None:
                connection.rollback()
            raise
        except Exception as error:
            if connection is not None:
                connection.rollback()
            if isinstance(error, EvelSqlClearError):
                raise
            raise EvelSqlClearError(
                "Andmete tühjendamine ebaõnnestus ja kõik muudatused "
                "pöörati tagasi: "
                + self._safe_error(error)
            ) from error
        finally:
            if connection is not None:
                connection.close()

    def _preflight(
        self,
        cursor,
        target: DatabaseTarget,
    ) -> tuple[ClearPreview, tuple[str, ...]]:
        dependent_tables, clear_order = self._dependent_tables(
            cursor,
            target,
        )
        all_tables = (*TABLE_ORDER, *dependent_tables)
        all_counts = {}
        for table in all_tables:
            cursor.execute(
                "SELECT has_table_privilege(current_user, %s, 'DELETE')",
                (f"{target.schema}.{table.lower()}",),
            )
            if not bool(cursor.fetchone()[0]):
                raise EvelSqlClearError(
                    f"Andmebaasikasutajal puudub DELETE õigus tabelile {table}."
                )
            cursor.execute(
                sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(target.schema),
                    sql.Identifier(table.lower()),
                )
            )
            all_counts[table] = int(cursor.fetchone()[0])
        counts = {table: all_counts[table] for table in TABLE_ORDER}
        dependent_counts = {
            table: all_counts[table] for table in dependent_tables
        }
        blockers = self._external_fk_blockers(
            cursor,
            target,
            set(all_tables),
        )
        return (
            ClearPreview(
                counts=counts,
                dependent_counts=dependent_counts,
                blockers=tuple(blockers),
            ),
            clear_order,
        )

    def _dependent_tables(
        self,
        cursor,
        target: DatabaseTarget,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        cursor.execute(
            """
            SELECT child_ns.nspname,
                   child.relname,
                   parent_ns.nspname,
                   parent.relname
            FROM pg_constraint AS con
            JOIN pg_class AS child ON child.oid = con.conrelid
            JOIN pg_namespace AS child_ns
              ON child_ns.oid = child.relnamespace
            JOIN pg_class AS parent ON parent.oid = con.confrelid
            JOIN pg_namespace AS parent_ns
              ON parent_ns.oid = parent.relnamespace
            WHERE con.contype = 'f'
            """,
        )
        relations = [
            (
                str(child_schema),
                str(child_table).upper(),
                str(parent_schema),
                str(parent_table).upper(),
            )
            for child_schema, child_table, parent_schema, parent_table
            in cursor.fetchall()
        ]
        delete_tables = set(TABLE_ORDER)
        changed = True
        while changed:
            changed = False
            for child_schema, child, parent_schema, parent in relations:
                if (
                    parent_schema == target.schema
                    and parent in delete_tables
                    and child_schema == target.schema
                    and child not in delete_tables
                ):
                    delete_tables.add(child)
                    changed = True

        dependent_tables = tuple(
            sorted(delete_tables - set(TABLE_ORDER))
        )
        edges = {
            (child, parent)
            for child_schema, child, parent_schema, parent in relations
            if (
                child_schema == target.schema
                and parent_schema == target.schema
                and child in delete_tables
                and parent in delete_tables
                and child != parent
            )
        }
        indegree = {table: 0 for table in delete_tables}
        outgoing = {table: set() for table in delete_tables}
        for child, parent in edges:
            if parent not in outgoing[child]:
                outgoing[child].add(parent)
                indegree[parent] += 1
        ready = sorted(
            table for table, degree in indegree.items() if degree == 0
        )
        ordered = []
        while ready:
            table = ready.pop(0)
            ordered.append(table)
            for parent in sorted(outgoing[table]):
                indegree[parent] -= 1
                if indegree[parent] == 0:
                    ready.append(parent)
                    ready.sort()
        remaining = sorted(delete_tables - set(ordered))
        ordered.extend(remaining)
        return dependent_tables, tuple(ordered)

    def _external_fk_blockers(
        self,
        cursor,
        target: DatabaseTarget,
        delete_tables: set[str],
    ) -> list[str]:
        cursor.execute(
            """
            SELECT child_ns.nspname,
                   child.relname,
                   child_col.attname,
                   parent.relname
            FROM pg_constraint AS con
            JOIN pg_class AS child ON child.oid = con.conrelid
            JOIN pg_namespace AS child_ns
              ON child_ns.oid = child.relnamespace
            JOIN pg_class AS parent ON parent.oid = con.confrelid
            JOIN pg_namespace AS parent_ns
              ON parent_ns.oid = parent.relnamespace
            JOIN pg_attribute AS child_col
              ON child_col.attrelid = child.oid
             AND child_col.attnum = con.conkey[1]
            WHERE con.contype = 'f'
              AND array_length(con.conkey, 1) = 1
              AND parent_ns.nspname = %s
              AND upper(parent.relname) = ANY(%s)
              AND NOT (
                  child_ns.nspname = %s
                  AND upper(child.relname) = ANY(%s)
              )
            ORDER BY child_ns.nspname, child.relname, child_col.attname
            """,
            (
                target.schema,
                list(delete_tables),
                target.schema,
                list(delete_tables),
            ),
        )
        blockers = []
        for schema_name, table_name, column_name, parent_table in cursor.fetchall():
            cursor.execute(
                sql.SQL(
                    "SELECT count(*) FROM {}.{} WHERE {} IS NOT NULL"
                ).format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(column_name),
                )
            )
            count = int(cursor.fetchone()[0])
            if count:
                blockers.append(
                    f"{schema_name}.{table_name}.{column_name} → "
                    f"{parent_table} ({count} kirjet)"
                )
        return blockers

    @staticmethod
    def _check_canceled(is_canceled: Callable[[], bool]) -> None:
        if is_canceled():
            raise EvelSqlClearCanceled(
                "Tühjendamine katkestati ja kõik muudatused pöörati tagasi."
            )

    @staticmethod
    def _safe_error(error: Exception) -> str:
        text = str(error).strip() or error.__class__.__name__
        text = re.sub(
            r"(?i)(password\s*=\s*)(?:'[^']*'|\S+)",
            r"\1'***'",
            text,
        )
        return text[:2000]
