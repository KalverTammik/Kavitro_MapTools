"""Build and validate the minimal EVEL_network_tools QGIS plugin directory."""

from __future__ import annotations

import argparse
import configparser
import re
import shutil
from pathlib import Path


PLUGIN_FOLDER = "EVEL_network_tools"
ROOT_FILES = (
    "__init__.py",
    "plugin.py",
    "metadata.txt",
)
RUNTIME_DIRECTORIES = (
    "importer",
    "layers",
    "map_tools",
    "resources",
    "topology",
    "ui",
)
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".github",
    ".idea",
    ".pytest_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "docs",
    "release_repo",
    "release_stage",
    "tests",
    "tools",
}
EXCLUDED_FILE_NAMES = {
    ".coverage",
    ".env",
    ".gitkeep",
    ".qgis-plugin-ci",
    "Thumbs.db",
    "secrets.md",
    "symbology-style.db",
    "user-history.db",
}
EXCLUDED_SUFFIXES = {
    ".bak",
    ".db",
    ".gpkg",
    ".log",
    ".md",
    ".pyc",
    ".pyo",
    ".qgs",
    ".qgz",
    ".sqlite",
    ".sqlite3",
    ".swp",
    ".swo",
    ".temp",
    ".tmp",
    ".zip",
}
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[.-][0-9A-Za-z.-]+)?$")


def _should_exclude(path: Path) -> bool:
    return (
        any(part in EXCLUDED_DIRECTORY_NAMES for part in path.parts)
        or path.name in EXCLUDED_FILE_NAMES
        or path.name.startswith(".env.")
        or path.suffix.lower() in EXCLUDED_SUFFIXES
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def _copy_runtime_tree(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if _should_exclude(relative):
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _metadata_lines_with_changelog(
    lines: list[str],
    version: str,
    changelog: str,
) -> list[str]:
    output: list[str] = []
    found_version = False
    found_experimental = False
    skipping_changelog = False

    for line in lines:
        if skipping_changelog and (line.startswith(" ") or line.startswith("\t")):
            continue
        skipping_changelog = False

        if line.startswith("version="):
            output.append(f"version={version}")
            found_version = True
        elif line.startswith("experimental="):
            output.append("experimental=False")
            found_experimental = True
        elif line.startswith("changelog="):
            skipping_changelog = True
        else:
            output.append(line)

    if not found_version:
        raise ValueError("metadata.txt does not contain a version entry")
    if not found_experimental:
        output.append("experimental=False")

    clean_changelog = changelog.strip()
    if clean_changelog:
        changelog_lines = clean_changelog.splitlines()
        output.append(f"changelog={changelog_lines[0]}")
        output.extend(f"    {line}" for line in changelog_lines[1:])

    return output


def _rewrite_metadata(metadata_path: Path, version: str, changelog: str) -> None:
    lines = metadata_path.read_text(encoding="utf-8").splitlines()
    output = _metadata_lines_with_changelog(lines, version, changelog)
    metadata_path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _read_metadata(metadata_path: Path) -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with metadata_path.open(encoding="utf-8") as handle:
        parser.read_file(handle)
    if "general" not in parser:
        raise ValueError("metadata.txt is missing the [general] section")
    return parser["general"]


def validate_release(plugin_dir: Path, version: str) -> tuple[int, int]:
    if plugin_dir.name != PLUGIN_FOLDER:
        raise ValueError(f"Release root folder must be named {PLUGIN_FOLDER!r}")

    required = [Path(name) for name in ROOT_FILES]
    required.extend(Path(name) for name in RUNTIME_DIRECTORIES)
    missing = [str(path) for path in required if not (plugin_dir / path).exists()]
    if missing:
        raise ValueError(f"Release is missing required paths: {', '.join(missing)}")

    file_count = 0
    total_size = 0
    for path in plugin_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(plugin_dir)
        if _should_exclude(relative):
            raise ValueError(f"Forbidden release file: {relative.as_posix()}")
        file_count += 1
        total_size += path.stat().st_size

    metadata = _read_metadata(plugin_dir / "metadata.txt")
    expected = {
        "name": "EVEL Võrgutööriistad",
        "version": version,
        "qgisMinimumVersion": "3.40",
        "experimental": "False",
        "repository": "https://github.com/KalverTammik/Kavitro_MapTools",
        "tracker": "https://github.com/KalverTammik/Kavitro_MapTools/issues",
        "icon": "resources/icons/evel_network_tools.svg",
    }
    mismatches = [
        f"{key}={metadata.get(key)!r} (expected {value!r})"
        for key, value in expected.items()
        if metadata.get(key) != value
    ]
    if mismatches:
        raise ValueError("Invalid release metadata: " + "; ".join(mismatches))
    if not (plugin_dir / metadata["icon"]).is_file():
        raise ValueError("Release metadata icon does not exist in the plugin package")
    return file_count, total_size


def build_release(
    source_root: Path,
    output_dir: Path,
    version: str,
    changelog: str = "",
) -> tuple[int, int]:
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"Invalid release version {version!r}; expected x.y.z")
    if output_dir == source_root or output_dir in source_root.parents:
        raise ValueError("Release output cannot be the source directory or its parent")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    for relative_name in ROOT_FILES:
        source = source_root / relative_name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, output_dir / relative_name)

    for relative_name in RUNTIME_DIRECTORIES:
        source = source_root / relative_name
        if not source.is_dir():
            raise FileNotFoundError(source)
        _copy_runtime_tree(source, output_dir / relative_name)

    _rewrite_metadata(output_dir / "metadata.txt", version, changelog)
    return validate_release(output_dir, version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Version in x.y.z format")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release_stage") / PLUGIN_FOLDER,
        help=f"Output plugin directory (must end with {PLUGIN_FOLDER})",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Plugin source root",
    )
    parser.add_argument(
        "--changelog-file",
        type=Path,
        help="Optional UTF-8 release notes to embed in release metadata",
    )
    args = parser.parse_args()

    changelog = ""
    if args.changelog_file:
        changelog = args.changelog_file.read_text(encoding="utf-8").strip()

    file_count, total_size = build_release(
        args.source,
        args.output,
        args.version,
        changelog,
    )
    print(f"Built {args.output}: {file_count} files, {total_size / 1024 / 1024:.2f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
