"""Tests for the minimal QGIS release package."""

from __future__ import annotations

import configparser
import tempfile
import unittest
from pathlib import Path

try:
    from EVEL_network_tools.tools.build_release import (
        PLUGIN_FOLDER,
        ROOT_FILES,
        RUNTIME_DIRECTORIES,
        build_release,
    )
except ModuleNotFoundError as error:
    if error.name != "EVEL_network_tools":
        raise
    from tools.build_release import (
        PLUGIN_FOLDER,
        ROOT_FILES,
        RUNTIME_DIRECTORIES,
        build_release,
    )


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.12.2"


class ReleasePackagingTest(unittest.TestCase):
    def test_runtime_manifest_covers_source_layout(self) -> None:
        expected_python_files = set(ROOT_FILES) - {"metadata.txt"}
        actual_python_files = {path.name for path in ROOT.glob("*.py")}
        self.assertEqual(expected_python_files, actual_python_files)

        expected_runtime_dirs = set(RUNTIME_DIRECTORIES)
        actual_runtime_dirs = {
            path.name
            for path in ROOT.iterdir()
            if path.is_dir()
            and (path / "__init__.py").is_file()
            and path.name not in {"tests", "tools"}
        }
        self.assertEqual(expected_runtime_dirs - {"resources"}, actual_runtime_dirs)

    def test_build_contains_only_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / PLUGIN_FOLDER
            file_count, total_size = build_release(
                ROOT,
                output,
                VERSION,
                "0.12.2 - Initial GitHub release\n\nValidated package.",
            )

            self.assertGreater(file_count, 20)
            self.assertGreater(total_size, 100_000)
            self.assertTrue((output / "plugin.py").is_file())
            self.assertTrue(
                (output / "resources/icons/evel_network_tools.svg").is_file()
            )
            self.assertFalse((output / "tests").exists())
            self.assertFalse((output / "docs").exists())
            self.assertFalse((output / "tools").exists())
            self.assertFalse((output / "symbology-style.db").exists())
            self.assertFalse((output / "user-history.db").exists())
            self.assertFalse(any(output.rglob("__pycache__")))
            self.assertFalse(any(output.rglob("*.pyc")))

            parser = configparser.ConfigParser(interpolation=None)
            parser.optionxform = str
            parser.read(output / "metadata.txt", encoding="utf-8")
            metadata = parser["general"]
            self.assertEqual(VERSION, metadata["version"])
            self.assertEqual("False", metadata["experimental"])
            self.assertIn("Initial GitHub release", metadata["changelog"])

    def test_rejects_invalid_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / PLUGIN_FOLDER
            with self.assertRaisesRegex(ValueError, "expected x.y.z"):
                build_release(ROOT, output, "v0.12.2")


if __name__ == "__main__":
    unittest.main()
