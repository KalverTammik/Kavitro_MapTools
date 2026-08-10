"""Build deterministic QGIS repository assets for EVEL Network Tools."""

from __future__ import annotations

import argparse
import configparser
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    from .build_release import PLUGIN_FOLDER, validate_release
except ImportError:
    from build_release import PLUGIN_FOLDER, validate_release


def _read_metadata(plugin_dir: Path) -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    with (plugin_dir / "metadata.txt").open(encoding="utf-8") as handle:
        parser.read_file(handle)
    if "general" not in parser:
        raise ValueError("metadata.txt is missing the [general] section")
    return parser["general"]


def _required(metadata: configparser.SectionProxy, key: str) -> str:
    value = metadata.get(key, "").strip()
    if not value:
        raise ValueError(f"metadata.txt is missing required value {key!r}")
    return value


def _build_zip(plugin_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(plugin_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(plugin_dir).as_posix()
            archive.write(path, f"{PLUGIN_FOLDER}/{relative}")


def _add(parent: ET.Element, tag: str, text: str) -> None:
    node = ET.SubElement(parent, tag)
    node.text = text


def _write_plugins_xml(
    metadata: configparser.SectionProxy,
    xml_path: Path,
    zip_name: str,
    download_url: str,
    icon_url: str,
) -> None:
    name = _required(metadata, "name")
    version = _required(metadata, "version")
    plugin = ET.Element("pyqgis_plugin", {"name": name, "version": version})

    _add(plugin, "description", _required(metadata, "description"))
    _add(plugin, "about", _required(metadata, "about"))
    _add(plugin, "version", version)
    _add(plugin, "qgis_minimum_version", _required(metadata, "qgisMinimumVersion"))
    _add(plugin, "homepage", metadata.get("homepage", "").strip())
    _add(plugin, "file_name", zip_name)
    _add(plugin, "download_url", download_url)
    _add(plugin, "icon", icon_url)
    _add(plugin, "author_name", _required(metadata, "author"))
    _add(plugin, "email", metadata.get("email", "").strip())
    _add(plugin, "tracker", metadata.get("tracker", "").strip())
    _add(plugin, "repository", metadata.get("repository", "").strip())
    _add(plugin, "tags", metadata.get("tags", "").strip())
    _add(plugin, "experimental", metadata.get("experimental", "False").strip())
    _add(plugin, "deprecated", metadata.get("deprecated", "False").strip())
    _add(plugin, "server", metadata.get("server", "False").strip())
    _add(plugin, "changelog", _required(metadata, "changelog"))
    _add(plugin, "create_date", datetime.now(UTC).date().isoformat())

    root = ET.Element("plugins")
    root.append(plugin)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=True)


def validate_repository(
    output_dir: Path,
    base_url: str,
    version: str,
) -> tuple[int, int]:
    zip_name = f"{PLUGIN_FOLDER}.{version}.zip"
    zip_path = output_dir / zip_name
    xml_path = output_dir / "plugins.xml"
    expected_download_url = base_url + zip_name

    if not zip_path.is_file() or not xml_path.is_file():
        raise ValueError("QGIS repository is missing plugins.xml or the plugin ZIP")

    root = ET.parse(xml_path).getroot()
    plugin_nodes = root.findall("pyqgis_plugin")
    if len(plugin_nodes) != 1:
        raise ValueError("plugins.xml must contain exactly one pyqgis_plugin")
    plugin = plugin_nodes[0]
    expected_xml = {
        "version": version,
        "file_name": zip_name,
        "download_url": expected_download_url,
        "experimental": "False",
    }
    mismatches = [
        f"{tag}={(plugin.findtext(tag) or '').strip()!r} (expected {value!r})"
        for tag, value in expected_xml.items()
        if (plugin.findtext(tag) or "").strip() != value
    ]
    if mismatches:
        raise ValueError("Invalid plugins.xml: " + "; ".join(mismatches))
    if not (plugin.findtext("changelog") or "").strip():
        raise ValueError("plugins.xml is missing a changelog")

    with zipfile.ZipFile(zip_path) as archive:
        file_entries = [name for name in archive.namelist() if not name.endswith("/")]
        roots = {name.split("/", 1)[0] for name in file_entries}
        if roots != {PLUGIN_FOLDER}:
            raise ValueError(f"Plugin ZIP has invalid root folders: {sorted(roots)}")
        forbidden = [
            name
            for name in file_entries
            if "/tests/" in name
            or "/__pycache__/" in name
            or name.endswith((".pyc", ".db", ".gpkg"))
        ]
        if forbidden:
            raise ValueError(f"Plugin ZIP contains forbidden files: {forbidden}")
        metadata_name = f"{PLUGIN_FOLDER}/metadata.txt"
        if metadata_name not in file_entries:
            raise ValueError("Plugin ZIP is missing metadata.txt in its root folder")

    return len(file_entries), zip_path.stat().st_size


def build_repository(
    plugin_dir: Path,
    output_dir: Path,
    base_url: str,
) -> tuple[Path, Path, Path]:
    plugin_dir = plugin_dir.resolve()
    output_dir = output_dir.resolve()
    if plugin_dir.name != PLUGIN_FOLDER:
        raise ValueError(f"Plugin directory must be named {PLUGIN_FOLDER!r}")
    if not base_url.startswith("https://"):
        raise ValueError("Base URL must use HTTPS")
    if not base_url.endswith("/"):
        base_url += "/"

    metadata = _read_metadata(plugin_dir)
    version = _required(metadata, "version")
    validate_release(plugin_dir, version)
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_name = f"{PLUGIN_FOLDER}.{version}.zip"
    zip_path = output_dir / zip_name
    xml_path = output_dir / "plugins.xml"
    icon_source = plugin_dir / _required(metadata, "icon")
    if not icon_source.is_file():
        raise ValueError(f"Plugin icon does not exist: {icon_source}")
    icon_path = output_dir / icon_source.name

    _build_zip(plugin_dir, zip_path)
    shutil.copy2(icon_source, icon_path)
    _write_plugins_xml(
        metadata,
        xml_path,
        zip_name,
        base_url + zip_name,
        base_url + icon_path.name,
    )
    validate_repository(output_dir, base_url, version)
    return xml_path, zip_path, icon_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("release_repo"))
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    xml_path, zip_path, icon_path = build_repository(
        args.plugin_dir,
        args.out,
        args.base_url,
    )
    file_count, zip_size = validate_repository(
        args.out.resolve(),
        args.base_url if args.base_url.endswith("/") else args.base_url + "/",
        _read_metadata(args.plugin_dir.resolve())["version"],
    )
    print(f"Built {xml_path}")
    print(f"Built {zip_path}: {file_count} files, {zip_size / 1024 / 1024:.2f} MiB")
    print(f"Built {icon_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
