#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Read-only combined view of a dumped base game and its separate update folder.

The update (eboot.bin, sce_sys, ...) is laid over the base game in a temporary folder, so
neither dump is modified. Whatever the update does not touch is linked as a whole (a symlink,
or a junction / hard link on Windows without the symlink privilege, see mods.make_link), so
large game assets cost a handful of links. Names are matched without regard to case.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from mods import child, is_link, link_target, make_link, remove_link, safe_unlink
from patches import find_sfo, game_title_id, game_app_ver


def overlay(source, dest, skip_names=None):
    """Lays source over dest: its files replace dest's, folders are merged, names are
    case-insensitive. dest holds links to the base; a folder both have is made a real one."""
    source, dest = Path(source), Path(dest)
    skip = {name.casefold() for name in skip_names} if skip_names else None
    entries = {entry.name.casefold(): entry for entry in dest.iterdir()}
    for item in source.iterdir():
        if skip and item.name.casefold() in skip:
            continue
        match = entries.get(item.name.casefold(), dest / item.name)
        if item.is_dir() and match.exists() and match.is_dir():
            if not any(item.iterdir()):
                continue
            if is_link(match):  # a linked folder of the base: replace the link by a merged copy
                inner = link_target(match)
                remove(match)
                match.mkdir()
                for ch in inner.iterdir():
                    make_link(match / ch.name, ch)
            overlay(item, match)
        else:
            if match.exists() or is_link(match):
                remove(match)
            make_link(match, item)


def remove(path):
    """Removes a file, link or folder of a view without following links into the dumps."""
    path = Path(path)
    if is_link(path):
        remove_link(path)
    elif path.is_dir():
        for ch in list(path.iterdir()):
            remove(ch)
        try:
            path.rmdir()
        except PermissionError:
            path.chmod(0o777)
            path.rmdir()
    else:
        safe_unlink(path)


def read_mod_metadata(mod_path):
    """Reads optional mod.json metadata from a mod folder."""
    mod_path = Path(mod_path)
    meta = {
        "name": mod_path.name,
        "order": None,
        "description": "",
        "author": "",
        "version": "",
        "has_manifest": False,
    }
    manifest = child(mod_path, "mod.json")
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                meta["has_manifest"] = True
                if isinstance(data.get("name"), str) and data["name"].strip():
                    meta["name"] = data["name"].strip()
                raw_order = data.get("order", data.get("priority"))
                if isinstance(raw_order, (int, float)) and not isinstance(raw_order, bool):
                    meta["order"] = float(raw_order)
                if isinstance(data.get("description"), str):
                    meta["description"] = data["description"].strip()
                if isinstance(data.get("author"), str):
                    meta["author"] = data["author"].strip()
                if isinstance(data.get("version"), str):
                    meta["version"] = data["version"].strip()
        except (OSError, ValueError):
            pass
    return meta


def _mod_has_assets(mod_path: Path) -> bool:
    """Returns True if the mod directory contains at least one non-metadata file or link."""
    for entry in mod_path.iterdir():
        if entry.name.casefold() == "mod.json":
            continue
        if entry.is_file() or is_link(entry):
            return True
        if entry.is_dir():
            for _root, _dirs, files in os.walk(entry, followlinks=False):
                if files:
                    return True
                for d in _dirs:
                    if is_link(Path(_root) / d):
                        return True
    return False


def validate_mod(mod_path, base=None, update=None, out=None):
    """Validates a pure mod folder (does NOT require eboot.bin or sce_sys/param.sfo).

    Ensures the folder exists, does not overlap with base/update/out, and contains assets.
    Returns the resolved Path.
    """
    if not mod_path:
        raise ValueError("Mod folder path cannot be empty.")
    p = Path(mod_path)
    if not p.is_dir():
        raise ValueError(f"Mod folder does not exist: {mod_path}")
    resolved = p.resolve()

    for label, other in (("game", base), ("update", update), ("out", out)):
        if not other:
            continue
        other_resolved = Path(other).resolve()
        if resolved == other_resolved or resolved in other_resolved.parents or other_resolved in resolved.parents:
            raise ValueError(f"Mod folder must be separate from {label} folder: {mod_path}")

    if not _mod_has_assets(resolved):
        raise ValueError(f"Mod folder is empty (no game assets found): {mod_path}")
    return resolved


def validate_mods(mods, base=None, update=None, out=None):
    """Validates a sequence of mod folders, returning resolved Paths in overlay order."""
    if not mods:
        return []
    resolved_list = []
    for mod in mods:
        resolved = validate_mod(mod, base=base, update=update, out=out)
        for prev in resolved_list:
            if resolved == prev or resolved in prev.parents or prev in resolved.parents:
                raise ValueError(f"Mod folders cannot overlap: {prev} / {resolved}")
        resolved_list.append(resolved)
    return resolved_list


def discover_mods(mods_dir=None, extra_mods=None, base=None, update=None, out=None):
    """Discovers mod folders in mods_dir and optional extra_mods paths."""
    candidates = []
    seen = set()

    if mods_dir:
        root_dir = Path(mods_dir)
        if root_dir.is_dir():
            for entry in sorted(root_dir.iterdir(), key=lambda e: e.name.casefold()):
                if entry.is_dir():
                    key = str(entry.resolve()).casefold()
                    if key not in seen:
                        seen.add(key)
                        candidates.append((entry.resolve(), False))

    if extra_mods:
        for raw in extra_mods:
            if not raw:
                continue
            p = Path(raw)
            resolved = p.resolve() if p.exists() else p
            key = str(resolved).casefold()
            if key not in seen:
                seen.add(key)
                candidates.append((resolved, True))

    results = []
    for mod_path, is_external in candidates:
        meta = read_mod_metadata(mod_path) if mod_path.is_dir() else {
            "name": mod_path.name,
            "order": None,
            "description": "",
            "author": "",
            "version": "",
            "has_manifest": False,
        }
        valid = True
        error = None
        try:
            validate_mod(mod_path, base=base, update=update, out=out)
        except (ValueError, OSError) as err:
            valid = False
            error = str(err)
        results.append({
            "path": mod_path,
            "name": meta["name"],
            "folder_name": mod_path.name,
            "order": meta["order"],
            "description": meta["description"],
            "author": meta["author"],
            "version": meta["version"],
            "has_manifest": meta["has_manifest"],
            "valid": valid,
            "error": error,
            "is_external": is_external,
        })

    results.sort(key=lambda m: (m["order"] is None, m["order"] if m["order"] is not None else 0.0, m["name"].casefold(), m["folder_name"].casefold()))
    return results


_OVERLAY_DIR_NAME = ".sumeragi-overlay"


def _can_create_symlink(folder: Path) -> bool:
    """Returns True if symlinks can be created inside folder without elevation errors."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe_target = folder / f".symlink-probe-target-{os.getpid()}"
        probe_link = folder / f".symlink-probe-link-{os.getpid()}"
        probe_target.write_bytes(b"")
        try:
            probe_link.symlink_to(probe_target)
            return True
        except OSError:
            return False
        finally:
            try:
                if probe_link.is_symlink() or probe_link.exists():
                    probe_link.unlink()
            except OSError:
                pass
            try:
                if probe_target.exists():
                    probe_target.unlink()
            except OSError:
                pass
    except OSError:
        return False


def _choose_view_root(base: Path, out_path: Path) -> Path:
    """Chooses where to materialize the temporary overlay view.

    On Windows without symlink privileges, hardlinks (os.link) only work within the same drive.
    If base and out are on different drives, placing the view on base's drive avoids copying
    gigabytes of untouched base assets across drives via shutil.copy2.
    """
    if os.name == "nt" and base.drive and out_path.drive and base.drive.casefold() != out_path.drive.casefold():
        if not _can_create_symlink(out_path):
            same_vol = base.parent / _OVERLAY_DIR_NAME
            try:
                same_vol.mkdir(parents=True, exist_ok=True)
                probe = Path(tempfile.mkdtemp(prefix=".probe-", dir=same_vol))
                probe.rmdir()
                return same_vol
            except OSError:
                pass
    return out_path


def create_view(base, update=None, out=None, mods=None):
    """Creates a combined overlay view: base -> update (optional) -> mods[0] -> mods[1] -> ..."""
    base = Path(base).resolve()
    if not base.is_dir():
        raise ValueError(f'Game folder does not exist: {base}')
    if out is None:
        out = Path(__file__).resolve().parent.parent / 'out'
    out_path = Path(out).resolve()
    update_path = Path(update).resolve() if update else None

    if update_path:
        base_id, update_id = game_title_id(base), game_title_id(update_path)
        if not base_id or base_id != update_id:
            raise ValueError(f'Game and update are not the same title: {base_id} / {update_id}')
        if base == update_path or base in update_path.parents or update_path in base.parents:
            raise ValueError('Choose two separate folders for the game and its update')
        if not (update_path / 'eboot.bin').is_file():
            raise ValueError('The update folder needs eboot.bin and sce_sys/param.sfo')

    mod_list = validate_mods(mods, base=base, update=update_path, out=out_path)
    if not update_path and not mod_list:
        raise ValueError('An update folder or at least one mod folder is required')

    view_root = _choose_view_root(base, out_path)
    view_root.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix='game-update-', dir=view_root))
    try:
        for entry in base.iterdir():
            make_link(target / entry.name, entry)
        if update_path:
            overlay(update_path, target)
        for mod_path in mod_list:
            overlay(mod_path, target, skip_names={'mod.json'})
    except BaseException:
        remove_view(target)
        raise
    return target


def remove_view(path):
    """Deletes a view made by create_view (the dumps and mods stay untouched)."""
    p = Path(path)
    parent = p.parent
    if p.exists() or is_link(p):
        remove(p)
    if parent.name == _OVERLAY_DIR_NAME and parent.is_dir():
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass


def validate_game(base, update=None, mods=None, out=None):
    """Validates the base game folder, optional update folder, and optional mod folders before launch.
    Base and update must contain the required executable (eboot.bin) and metadata (sce_sys/param.sfo).
    Mod folders do NOT require eboot.bin or sce_sys/param.sfo.
    Returns (base_metadata, update_metadata).
    """
    from prepare import load_sfo

    if not base:
        raise ValueError("Choose the game folder (the one with eboot.bin).")
    base_path = Path(base).resolve()
    if not base_path.is_dir():
        raise ValueError(f"Game folder does not exist: {base}")
    if not (base_path / "eboot.bin").is_file():
        raise ValueError(f"Missing eboot.bin in game folder: {base}")

    base_sfo = find_sfo(base_path)
    if not base_sfo.is_file():
        raise ValueError(f"Missing sce_sys/param.sfo in game folder: {base}")
    try:
        base_meta = load_sfo(base_sfo)
    except Exception as err:
        raise ValueError(f"Invalid metadata in game folder {base_sfo}: {err}") from err

    base_title_id = base_meta.get("TITLE_ID")
    base_app_ver = base_meta.get("APP_VER")
    if not base_title_id or not isinstance(base_title_id, str) or not base_title_id.strip():
        raise ValueError(f"Missing or invalid TITLE_ID in game folder: {base_sfo}")
    if not base_app_ver or not isinstance(base_app_ver, str) or not base_app_ver.strip():
        raise ValueError(f"Missing or invalid APP_VER in game folder: {base_sfo}")

    update_meta = None
    update_path = None
    if update:
        update_path = Path(update).resolve()
        if not update_path.is_dir():
            raise ValueError(f"Update folder does not exist: {update}")
        if base_path == update_path or base_path in update_path.parents or update_path in base_path.parents:
            raise ValueError("Choose two separate folders for the game and its update")
        if not (update_path / "eboot.bin").is_file():
            raise ValueError(f"Missing eboot.bin in update folder: {update}")

        update_sfo = find_sfo(update_path)
        if not update_sfo.is_file():
            raise ValueError(f"Missing sce_sys/param.sfo in update folder: {update}")
        try:
            update_meta = load_sfo(update_sfo)
        except Exception as err:
            raise ValueError(f"Invalid metadata in update folder {update_sfo}: {err}") from err

        update_title_id = update_meta.get("TITLE_ID")
        update_app_ver = update_meta.get("APP_VER")
        if not update_title_id or not isinstance(update_title_id, str) or not update_title_id.strip():
            raise ValueError(f"Missing or invalid TITLE_ID in update folder: {update_sfo}")
        if not update_app_ver or not isinstance(update_app_ver, str) or not update_app_ver.strip():
            raise ValueError(f"Missing or invalid APP_VER in update folder: {update_sfo}")

        if base_title_id.strip() != update_title_id.strip():
            raise ValueError(f"Game and update are not the same title: {base_title_id.strip()} / {update_title_id.strip()}")

    if mods:
        validate_mods(mods, base=base_path, update=update_path, out=out)

    return base_meta, update_meta


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path, help='Base game dump folder')
    parser.add_argument('update', nargs='?', type=Path, default=None, help='Extracted game update folder')
    parser.add_argument('--mod', dest='mods', action='append', type=Path, default=[], help='Mod folder to overlay (repeatable, applied in order)')
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent.parent / 'out')
    args = parser.parse_args()
    view = create_view(args.base, args.update, args.out, mods=args.mods)
    print(view)
