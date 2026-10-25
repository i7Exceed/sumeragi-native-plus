#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Local DLC discovery, validation, and manifest generation for Basara 4 PC.

Discovers locally supplied, extracted add-on content adhering to:
  <DLC_ROOT>/<TITLE_ID>/<ENTITLEMENT_ID>/<content files>

Validates directory safety, entitlement IDs, SFO metadata, duplicate IDs,
and produces:
  - out/addons.json (human-readable versioned JSON manifest)
  - out/addons.bin  (binary manifest format B4ADD001 consumed by the C runtime)
"""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import sys

from patches import find_sfo
from prepare import read_sfo

MAGIC = b"B4ADD001"
MANIFEST_VERSION = 1
HEADER_FORMAT = "<8sII16s"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 32 bytes
ENTRY_FORMAT = "<I20sI512sI"
ENTRY_SIZE = struct.calcsize(ENTRY_FORMAT)    # 544 bytes
MAX_ADDONS = 64

# Entitlement ID: 1-16 characters, alphanumeric, underscores, hyphens
ENTITLEMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
STATUS_INSTALLED = 4  # OrbisAppContentAddcontDownloadStatus::Installed


class DLCValidationError(ValueError):
    """Raised when DLC directory structure or content fails validation."""
    pass


def is_valid_entitlement_id(name: str) -> bool:
    """Check if an entitlement identifier is valid and safe."""
    return bool(ENTITLEMENT_PATTERN.match(name))


def is_path_safe(base_dir: Path, target_path: Path) -> bool:
    """Verify target_path does not escape outside base_dir."""
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        return resolved_target.is_relative_to(resolved_base)
    except (ValueError, OSError):
        return False


def discover_addons(dlc_dir: Path | str | None, title_id: str = "CUSA01159") -> list[dict]:
    """Discover and validate all add-on content under dlc_dir for title_id.

    Returns a list of dicts:
      [{'service_label': 0, 'entitlement_label': str, 'status': 4, 'host_path': str}]
    """
    if not dlc_dir:
        return []

    dlc_dir = Path(dlc_dir).resolve()
    if not dlc_dir.is_dir():
        raise DLCValidationError(f"DLC directory does not exist or is not a directory: {dlc_dir}")

    # Determine the title folder:
    # 1. dlc_dir / title_id
    # 2. dlc_dir itself if its name matches title_id
    target_dir = dlc_dir / title_id
    if not target_dir.is_dir():
        if dlc_dir.name.casefold() == title_id.casefold():
            target_dir = dlc_dir
        else:
            # Check for case-insensitive match among children
            found = False
            for child in dlc_dir.iterdir():
                if child.is_dir() and child.name.casefold() == title_id.casefold():
                    target_dir = child
                    found = True
                    break
            if not found:
                # No subfolder for title_id found under DLC root
                return []

    if not is_path_safe(dlc_dir, target_dir):
        raise DLCValidationError(f"Target DLC path escapes DLC root: {target_dir}")

    discovered = []
    seen_entitlements = set()

    # Optional user manifest: dlc_manifest.json in target_dir or dlc_dir
    user_manifest_file = target_dir / "dlc_manifest.json"
    if not user_manifest_file.is_file():
        user_manifest_file = dlc_dir / "dlc_manifest.json"

    user_manifest = None
    if user_manifest_file.is_file():
        try:
            with user_manifest_file.open("r", encoding="utf-8") as f:
                user_manifest = json.load(f)
        except Exception as err:
            raise DLCValidationError(f"Invalid dlc_manifest.json: {err}") from err

        if not isinstance(user_manifest, dict):
            raise DLCValidationError("dlc_manifest.json must be a JSON object")
        if user_manifest.get("version") != 1:
            raise DLCValidationError(f"Unsupported manifest version: {user_manifest.get('version')}")
        manifest_title = user_manifest.get("title_id", "")
        if manifest_title.casefold() != title_id.casefold():
            raise DLCValidationError(f"Manifest title_id '{manifest_title}' does not match expected '{title_id}'")

        entries = user_manifest.get("addons")
        if not isinstance(entries, list):
            raise DLCValidationError("dlc_manifest.json must contain an 'addons' array")

        for entry in entries:
            if not isinstance(entry, dict):
                raise DLCValidationError("Each manifest addon entry must be an object")
            ent_id = str(entry.get("entitlement_label", "")).strip()
            if not is_valid_entitlement_id(ent_id):
                raise DLCValidationError(f"Invalid entitlement_label in manifest: '{ent_id}'")
            if ent_id.casefold() in seen_entitlements:
                raise DLCValidationError(f"Duplicate entitlement_label in manifest: '{ent_id}'")

            sub_path = entry.get("path") or ent_id
            addon_dir = (target_dir / sub_path).resolve()
            if not is_path_safe(dlc_dir, addon_dir) or not addon_dir.is_dir():
                raise DLCValidationError(f"Addon directory missing or unsafe: {addon_dir}")

            _validate_addon_directory(addon_dir, ent_id, title_id)
            seen_entitlements.add(ent_id.casefold())
            discovered.append({
                "service_label": int(entry.get("service_label", 0)),
                "entitlement_label": ent_id,
                "status": STATUS_INSTALLED,
                "host_path": str(addon_dir)
            })

        return discovered

    # Auto-discovery by iterating subdirectories in target_dir
    for item in sorted(target_dir.iterdir(), key=lambda p: p.name):
        if not item.is_dir():
            continue
        ent_id = item.name
        if not is_valid_entitlement_id(ent_id):
            continue
        if not is_path_safe(dlc_dir, item):
            raise DLCValidationError(f"Unsafe symlink or path traversal in add-on folder: {item}")

        if ent_id.casefold() in seen_entitlements:
            raise DLCValidationError(f"Duplicate entitlement ID detected: '{ent_id}'")

        _validate_addon_directory(item, ent_id, title_id)
        seen_entitlements.add(ent_id.casefold())
        discovered.append({
            "service_label": 0,
            "entitlement_label": ent_id,
            "status": STATUS_INSTALLED,
            "host_path": str(item.resolve())
        })

    return discovered


def _validate_addon_directory(addon_dir: Path, ent_id: str, title_id: str):
    """Validate the contents of an individual add-on folder."""
    # Check that directory is not empty
    try:
        contents = list(addon_dir.iterdir())
    except OSError as err:
        raise DLCValidationError(f"Cannot read add-on directory {addon_dir}: {err}") from err

    if not contents:
        raise DLCValidationError(f"Add-on folder is empty: {addon_dir}")

    # Check SFO if present
    sfo_path = find_sfo(addon_dir)
    if sfo_path.is_file():
        values = read_sfo(sfo_path)
        if not values:
            raise DLCValidationError(f"Add-on param.sfo unreadable in {addon_dir}")

        category = str(values.get("CATEGORY", ""))
        if not category.startswith("ac"):
            raise DLCValidationError(
                f"Add-on {addon_dir} CATEGORY is '{category}', expected 'ac' (add-on content)")

        sfo_title = str(values.get("TITLE_ID", ""))
        if sfo_title and sfo_title.casefold() != title_id.casefold():
            raise DLCValidationError(
                f"Add-on {addon_dir} TITLE_ID '{sfo_title}' does not match expected '{title_id}'")

        content_id = str(values.get("CONTENT_ID", ""))
        if content_id and len(content_id) > 20:
            sfo_ent = content_id[20:]
            if sfo_ent.casefold() != ent_id.casefold():
                raise DLCValidationError(
                    f"Add-on CONTENT_ID suffix '{sfo_ent}' does not match folder '{ent_id}'")


def build_binary_manifest(addons: list[dict], title_id: str = "CUSA01159") -> bytes:
    """Serialize the add-ons list into B4ADD001 binary format."""
    if len(addons) > MAX_ADDONS:
        raise DLCValidationError(f"Too many add-ons ({len(addons)}), max supported is {MAX_ADDONS}")

    encoded_title = title_id.encode("ascii")[:15]
    header = struct.pack(
        HEADER_FORMAT,
        MAGIC,
        MANIFEST_VERSION,
        len(addons),
        encoded_title
    )

    body = bytearray()
    for item in addons:
        service_label = int(item["service_label"])
        ent_label = str(item["entitlement_label"]).encode("ascii")[:19]
        status = int(item["status"])
        host_path = str(item["host_path"]).encode("utf-8")[:511]
        entry = struct.pack(
            ENTRY_FORMAT,
            service_label,
            ent_label,
            status,
            host_path,
            0  # reserved flags
        )
        body.extend(entry)

    return header + bytes(body)


def generate_manifest(dlc_dir: Path | str, out_dir: Path | str, title_id: str = "CUSA01159") -> tuple[Path, Path, list[dict]]:
    """Discover add-ons, serialize to addons.json and addons.bin in out_dir."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    addons = discover_addons(dlc_dir, title_id=title_id)

    # 1. Human-readable JSON manifest
    json_path = out_dir / "addons.json"
    manifest_data = {
        "version": MANIFEST_VERSION,
        "title_id": title_id,
        "count": len(addons),
        "addons": addons
    }
    json_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    # 2. Binary manifest consumed by C runtime
    bin_path = out_dir / "addons.bin"
    raw_binary = build_binary_manifest(addons, title_id=title_id)
    bin_path.write_bytes(raw_binary)

    return json_path, bin_path, addons


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dlc_dir", type=Path, help="root DLC folder or <DLC_ROOT>/<TITLE_ID>")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "out",
                   help="output directory for manifest files")
    p.add_argument("--title-id", default="CUSA01159", help="expected PS4 title ID (default: CUSA01159)")
    args = p.parse_args()

    try:
        json_path, bin_path, addons = generate_manifest(args.dlc_dir, args.out, title_id=args.title_id)
        print(f"Discovered {len(addons)} add-on(s) for {args.title_id}:")
        for a in addons:
            print(f"  [{a['service_label']}] {a['entitlement_label']} -> {a['host_path']}")
        print(f"Wrote {json_path} and {bin_path}")
    except DLCValidationError as err:
        sys.exit(f"DLC Validation Error: {err}")


if __name__ == "__main__":
    main()
