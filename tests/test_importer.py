"""Tests for the EVEL GeoPackage → PostgreSQL importer."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import psycopg2
from qgis.core import QgsGeometry, QgsProject, QgsWkbTypes

from EVEL_network_tools.importer import (
    CLEAR_ORDER,
    DatabaseTarget,
    EvelImportPackageReader,
    EvelImportTargetInspector,
    EvelSqlImportError,
    EvelSqlImporter,
    EvelSqlClearer,
    ImportPlan,
    ImportRecord,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.ui import EvelImportDialog


start_qgis()


_project_path = os.environ.get("EVEL_IMPORT_TEST_PROJECT")
_package_path = os.environ.get("EVEL_IMPORT_TEST_PACKAGE")
PROJECT_PATH = Path(_project_path) if _project_path else None
PACKAGE_PATH = Path(_package_path) if _package_path else None


class EvelImporterTest(unittest.TestCase):
    def tearDown(self) -> None:
        QgsProject.instance().clear()

    @unittest.skipUnless(
        PACKAGE_PATH is not None and PACKAGE_PATH.exists(),
        "Kontrollpakett puudub",
    )
    def test_reads_real_client_review_package(self) -> None:
        plan = EvelImportPackageReader().read(PACKAGE_PATH)

        self.assertEqual(33173, plan.total_count)
        self.assertEqual(5941, plan.count("SN_WATER_DUCT"))
        self.assertEqual(6893, plan.count("SN_SEWER_DUCT"))
        self.assertEqual(5984, plan.count("SN_WATER_NODE"))
        self.assertEqual(7264, plan.count("SN_SEWER_NODE"))
        self.assertEqual(2220, plan.count("SN_WATER_VALVE"))
        self.assertEqual(41, plan.count("SN_SEWER_VALVE"))
        self.assertIn(615, plan.referenced_constant_ids)
        self.assertTrue(
            all(
                "FID" not in record.values
                for rows in plan.records.values()
                for record in rows
            )
        )
        self.assertTrue(
            any("sidumata objekti" in warning for warning in plan.warnings)
        )
        self.assertTrue(
            any(
                "SN_WATER_VALVE: importimisel jäetakse välja 7 täpset "
                "duplikaati" in warning
                for warning in plan.warnings
            )
        )
        self.assertTrue(
            any(
                "12834 üheosalist multipart-geomeetriat" in warning
                for warning in plan.warnings
            )
        )
        for table in ("SN_WATER_DUCT", "SN_SEWER_DUCT"):
            geometry = QgsGeometry()
            geometry.fromWkb(plan.records[table][0].geometry_wkb)
            self.assertFalse(geometry.isNull())
            self.assertFalse(
                QgsWkbTypes.isMultiType(geometry.wkbType())
            )
        water_valve_ids = {
            record.local_id
            for record in plan.records["SN_WATER_VALVE"]
        }
        self.assertIn(611, water_valve_ids)
        self.assertNotIn(612, water_valve_ids)
        EvelSqlImporter()._package_preflight(plan)

    def test_importer_still_rejects_conflicting_details_on_one_node(self) -> None:
        plan = ImportPlan(
            package_path=Path("conflict.gpkg"),
            package_sha256="hash",
            records={
                "SN_WATER_VALVE": (
                    ImportRecord(
                        local_id=1,
                        values={"NODE_ID": 10, "TYPE_ID": 591},
                    ),
                    ImportRecord(
                        local_id=2,
                        values={"NODE_ID": 10, "TYPE_ID": 592},
                    ),
                )
            },
            package_info={},
            referenced_constant_ids=frozenset(),
        )

        with self.assertRaisesRegex(
            EvelSqlImportError,
            "mitu sama liigi detailkirjet",
        ):
            EvelSqlImporter()._package_preflight(plan)

    @unittest.skipUnless(
        PROJECT_PATH is not None and PROJECT_PATH.exists(),
        "Testprojekt puudub",
    )
    def test_real_project_exposes_one_import_target(self) -> None:
        project = QgsProject.instance()
        self.assertTrue(project.read(str(PROJECT_PATH)))

        target = EvelImportTargetInspector().inspect(project)

        self.assertEqual("evel", target.schema)
        self.assertEqual(9, len(target.table_columns))
        self.assertNotIn("password", repr(target).casefold())
        self.assertTrue(
            {
                "MSLINK",
                "BEGIN_NODE_ID",
                "END_NODE_ID",
            }.issubset(target.table_columns["SN_WATER_DUCT"])
        )

    def test_maps_local_node_ids_to_allocated_server_ids(self) -> None:
        importer = EvelSqlImporter()
        record = ImportRecord(
            local_id=9,
            values={
                "NETWORK_ID": 312,
                "BEGIN_NODE_ID": 1,
                "END_NODE_ID": 2,
            },
            geometry_wkb=b"geometry",
        )
        values = importer._record_values(
            "SN_WATER_DUCT",
            record,
            ["NETWORK_ID"],
            ["BEGIN_NODE_ID", "END_NODE_ID"],
            {
                "SN_WATER_DUCT": {9: 9009},
                "SN_WATER_NODE": {1: 1001, 2: 1002},
            },
        )

        self.assertEqual(9009, values[0])
        self.assertEqual(312, values[1])
        self.assertEqual((1001, 1002), values[2:4])
        self.assertEqual(b"geometry", values[4].adapted)

    def test_database_target_repr_never_contains_dsn(self) -> None:
        target = DatabaseTarget(
            schema="evel",
            connection_dsn="password='secret'",
            connection_key=("host", "5432", "db", "user"),
            table_columns={},
            project_layer_ids=(),
        )

        self.assertNotIn("secret", repr(target))

    def test_dialog_requires_a_validated_package_before_sql_check(self) -> None:
        dialog = EvelImportDialog(QgsProject.instance())
        self.addCleanup(dialog.deleteLater)

        self.assertFalse(dialog.dry_run_button.isEnabled())
        self.assertFalse(dialog.import_button.isEnabled())
        self.assertTrue(dialog.browse_button.isEnabled())

    def test_dialog_stores_import_history_in_project_entries(self) -> None:
        project = QgsProject.instance()
        dialog = EvelImportDialog(project)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual("", dialog._import_timestamp("package_hash"))
        dialog._mark_imported("package_hash", "2026-07-28T12:00:00+03:00")
        self.assertEqual(
            "2026-07-28T12:00:00+03:00",
            dialog._import_timestamp("package_hash"),
        )

    def test_clearer_uses_dependency_safe_table_order(self) -> None:
        self.assertEqual(
            (
                "SN_WATER_MANHOLE",
                "SN_WATER_VALVE",
                "SN_FIRE_PLUG",
                "SN_SEWER_MANHOLE",
                "SN_SEWER_VALVE",
                "SN_WATER_DUCT",
                "SN_SEWER_DUCT",
                "SN_WATER_NODE",
                "SN_SEWER_NODE",
            ),
            CLEAR_ORDER,
        )
        self.assertNotIn(
            "secret",
            EvelSqlClearer._safe_error(
                RuntimeError("password='secret' connection failed")
            ),
        )

    @unittest.skipUnless(
        PROJECT_PATH is not None
        and PROJECT_PATH.exists()
        and PACKAGE_PATH is not None
        and PACKAGE_PATH.exists(),
        "Testprojekt või kontrollpakett puudub",
    )
    def test_dialog_loads_real_package_in_real_project(self) -> None:
        project = QgsProject.instance()
        self.assertTrue(project.read(str(PROJECT_PATH)))
        dialog = EvelImportDialog(project)
        self.addCleanup(dialog.deleteLater)
        package = EvelImportPackageReader().read(PACKAGE_PATH)
        project.removeEntry(
            dialog.IMPORT_ENTRY_SCOPE,
            dialog.IMPORT_ENTRY_PREFIX + package.package_sha256,
        )

        dialog.set_package_path(PACKAGE_PATH)

        self.assertIsNotNone(dialog.plan)
        self.assertEqual(33173, dialog.plan.total_count)
        self.assertTrue(dialog.dry_run_button.isEnabled())
        self.assertFalse(dialog.import_button.isEnabled())

    @unittest.skipUnless(
        os.environ.get("EVEL_RUN_DB_TESTS") == "1"
        and PROJECT_PATH is not None
        and PROJECT_PATH.exists()
        and PACKAGE_PATH is not None
        and PACKAGE_PATH.exists(),
        "Võrguga andmebaasitest pole lubatud",
    )
    def test_real_database_schema_preflight_is_read_only(self) -> None:
        project = QgsProject.instance()
        self.assertTrue(project.read(str(PROJECT_PATH)))
        target = EvelImportTargetInspector().inspect(project)
        plan = EvelImportPackageReader().read(PACKAGE_PATH)
        connection = psycopg2.connect(
            target.connection_dsn,
            application_name="EVEL importer read-only test",
        )
        try:
            connection.set_session(readonly=True, autocommit=False)
            with connection.cursor() as cursor:
                columns = EvelSqlImporter()._database_preflight(
                    cursor,
                    plan,
                    target,
                )
            self.assertEqual(9, len(columns))
        finally:
            connection.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()
