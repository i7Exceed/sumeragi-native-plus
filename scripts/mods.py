#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Filesystem link helpers for game update overlay and mod views.

Supports symlinks, Windows NTFS junctions (without symlink privilege),
and hard links as fallback, tracking created reparse points so temporary views
can be deleted cleanly without descending into the original game files.
"""
import ctypes
import os
from pathlib import Path
import shutil
import stat

# Windows without symlink privileges: track links created via junctions/hard links
LINKED = {}


def _win_delete_readonly(path: Path) -> bool:
    """Deletes a Windows file, hardlink, or reparse point (junction/symlink) ignoring READONLY.

    Uses FileDispositionInfoEx (Win10+) so hardlink deletion never clears the READONLY
    attribute on the shared MFT record / original target file.
    """
    if os.name != "nt":
        return False
    try:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        DELETE = 0x00010000
        SHARE_ALL = 0x7
        OPEN_EXISTING = 3
        FLAGS = 0x02000000 | 0x00200000  # FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
        FILE_DISPOSITION_INFO_EX = 21

        class FILE_DISPOSITION_EX(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD)]

        handle = kernel32.CreateFileW(str(path), DELETE, SHARE_ALL, None, OPEN_EXISTING, FLAGS, None)
        if handle == INVALID_HANDLE_VALUE or not handle:
            return False
        try:
            for flags in (0x1 | 0x2 | 0x10, 0x1 | 0x10):
                info = FILE_DISPOSITION_EX(flags)
                if kernel32.SetFileInformationByHandle(
                    handle, FILE_DISPOSITION_INFO_EX, ctypes.byref(info), ctypes.sizeof(info)
                ):
                    return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        pass
    return False


def _win_find_sibling_hardlink(path: Path) -> Path | None:
    """Returns another hardlink path pointing to the same file, if discoverable."""
    tracked = LINKED.get(str(path))
    if tracked and Path(tracked).exists() and Path(tracked).resolve() != path.resolve():
        return Path(tracked)
    if tracked and Path(tracked).exists():
        return Path(tracked)
    if os.name != "nt":
        return None
    try:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
        buf_len = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(buf_len.value)
        anchor = Path(path.anchor)
        cur_rel = os.path.splitdrive(str(path.resolve()))[1].casefold()
        h = kernel32.FindFirstFileNameW(str(path), 0, ctypes.byref(buf_len), buf)
        if h == INVALID_HANDLE_VALUE or not h:
            return None
        try:
            while True:
                cand_rel = buf.value
                if cand_rel.casefold() != cur_rel:
                    cand = Path(str(anchor).rstrip("\\/")) / cand_rel.lstrip("\\/")
                    if cand.exists():
                        return cand
                buf_len = wintypes.DWORD(1024)
                if not kernel32.FindNextFileNameW(h, ctypes.byref(buf_len), buf):
                    break
        finally:
            kernel32.FindClose(h)
    except Exception:
        pass
    return None


def safe_unlink(path):
    """Unlinks a file or hardlink without modifying attributes of any linked source file."""
    path = Path(path)
    try:
        path.unlink()
        return
    except PermissionError:
        if os.name != "nt":
            raise
    if _win_delete_readonly(path):
        return
    # Fallback for older Windows/filesystems: preserve read-only on sibling hardlink if nlink > 1
    st = path.lstat()
    is_ro = not (st.st_mode & stat.S_IWRITE)
    sibling = _win_find_sibling_hardlink(path) if (st.st_nlink > 1 and is_ro) else None
    if not path.is_symlink():
        path.chmod(0o666)
    path.unlink()
    if sibling is not None and sibling.exists():
        sibling.chmod(st.st_mode & 0o777)


def make_link(link, target):
    """Creates a link from link to target.
    Tries symlinks first. On Windows without symlink privileges, uses junctions for directories
    and hard links (or cross-volume copies) for files.
    """
    link, target = Path(link), Path(target)
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
        return
    except OSError:
        if os.name != 'nt':
            raise
    if target.is_dir():
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        except OSError:
            # Mirror the folder when junctions are refused (e.g. SMB network shares)
            link.mkdir(exist_ok=True)
            for entry in target.iterdir():
                make_link(link / entry.name, entry)
            return
    else:
        try:
            os.link(target, link)
        except OSError:
            shutil.copy2(target, link)
    LINKED[str(link)] = target


def is_link(path):
    """Returns True if path is a symlink, tracked reparse point, or Windows junction."""
    path = Path(path)
    return path.is_symlink() or str(path) in LINKED or (hasattr(path, 'is_junction') and path.is_junction())


def link_target(path):
    """Returns the target of the link/junction."""
    path = Path(path)
    return LINKED.get(str(path)) or path.resolve(strict=True)


def remove_link(path):
    """Removes a link or junction without touching its target or target attributes."""
    path = Path(path)
    is_junc = hasattr(path, 'is_junction') and path.is_junction()
    is_dir_sym = os.name == 'nt' and path.is_symlink() and path.is_dir()
    if is_junc or is_dir_sym:
        try:
            os.rmdir(path)
        except PermissionError:
            if not _win_delete_readonly(path):
                # Clear FILE_ATTRIBUTE_READONLY on the reparse point itself (does not follow junction)
                if os.name == 'nt':
                    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
                    if attrs != -1 and (attrs & 0x1):
                        ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs & ~0x1)
                os.rmdir(path)
    else:
        safe_unlink(path)
    LINKED.pop(str(path), None)


def child(folder, name):
    """Finds an entry inside folder case-insensitively, returning folder / name if not found."""
    folder = Path(folder)
    for entry in (folder.iterdir() if folder.is_dir() else ()):
        if entry.name.casefold() == name.casefold():
            return entry
    return folder / name
