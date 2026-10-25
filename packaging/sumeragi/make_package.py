"""Basara 4 PC - by Razz.   Copyright (C) 2026 Razz.   GPL-2.0-or-later (NOTICE.md).

Builds the Windows folder that is handed to players, from this repository.

  python packaging/basara4/make_package.py --out dist/basara4-windows
  python packaging/basara4/make_package.py --out D:/Games/basara4-windows --update

Needs: MSYS2 CLANG64 (build.sh already run, so out/gpu/basara4-core.exe exists), and
`python -m pip install pyinstaller` on the Windows Python that runs this script.

--update refreshes the programs of an existing folder and leaves game\\, user\\ and out\\ alone.
Without it the folder must not exist yet; empty game\\, user\\ and out\\ folders are created.
The game itself is never copied.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
LAUNCHER = REPO / "launcher"
NAME = "Sumeragi Native+"
STDLIB = ["argparse", "base64", "collections", "ctypes", "ctypes.wintypes", "hashlib", "json", "shutil", "struct",
          "subprocess", "pathlib", "zlib", "re", "tempfile", "lzma", "bz2", "gzip", "io", "itertools", "math", "time",
          "textwrap", "binascii", "zipfile", "functools", "dataclasses", "typing", "enum", "string", "traceback",
          "stat", "errno", "copy", "contextlib", "datetime", "fnmatch", "glob", "operator", "xml.etree.ElementTree",
          "uuid", "codecs", "array", "bisect", "heapq", "runpy", "importlib.util"]
PREPARE_SCRIPTS = ["prepare.py", "link_libc.py", "link_modules.py", "content_profile.py",
                   "game_update.py", "mods.py", "patches.py", "dlc.py"]


def run(*cmd, **kw):
    print(">", " ".join(str(c) for c in cmd)[:220])
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def msys(msys_root, command):
    """Runs a command in the MSYS2 CLANG64 shell, in the repository root."""
    bash = Path(msys_root) / "usr/bin/bash.exe"
    env = {**__import__("os").environ, "MSYSTEM": "CLANG64"}
    run(bash, "-lc", f'cd "$(cygpath -u "{REPO}")" && source ./msys2-env.sh && {command}', env=env)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "dist/sumeragi-native-plus-windows")
    ap.add_argument("--update", action="store_true", help="refresh programs in an existing folder")
    ap.add_argument("--msys2", type=Path, default=Path(r"C:\msys64"))
    args = ap.parse_args()
    target, clang = args.out.resolve(), args.msys2 / "clang64/bin"

    core = REPO / "out/gpu/sumeragi-core.exe"
    if not core.is_file():
        core = REPO / "out/gpu/basara4-core.exe"
    mapper = REPO / "out/sumeragi-pad-mapper.exe"
    if not mapper.is_file():
        mapper = REPO / "out/basara4-pad-mapper.exe"

    if not core.is_file():
        sys.exit(f"{core} is missing: run `bash build.sh` in the MSYS2 CLANG64 shell first")
    if target.exists() and not args.update:
        sys.exit(f"{target} already exists (use --update to refresh its programs)")
    if args.update and not target.is_dir():
        sys.exit(f"{target} does not exist")

    # the controller mapper (SDL3 console program)
    msys(args.msys2, "clang tools/gamepad_mapper.c $(pkg-config --cflags sdl3) -lSDL3 -mconsole "
                     "-o out/sumeragi-pad-mapper.exe && cp -f out/sumeragi-pad-mapper.exe out/basara4-pad-mapper.exe")

    # the launcher executable
    work = REPO / "out/sumeragi-package"
    shutil.rmtree(work, ignore_errors=True)
    icon_path = LAUNCHER / "sumeragi.ico"

    pyi = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--name", NAME,
           "--icon", icon_path, "--paths", LAUNCHER, "--paths", REPO / "scripts",
           "--add-data", f"{icon_path};.",
           "--distpath", work / "dist", "--workpath", work / "build", "--specpath", work]
    for module in STDLIB:
        pyi += ["--hidden-import", module]
    for script in ("game_update", "mods", "patches", "dlc", "sumeragi_patches"):
        pyi += ["--hidden-import", script]
    pyi.append(LAUNCHER / "sumeragi_launcher.py")
    run(*pyi)
    built = work / "dist" / NAME

    target.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(target / "_internal", ignore_errors=True)
    shutil.copytree(built / "_internal", target / "_internal")
    shutil.copy2(built / f"{NAME}.exe", target / f"{NAME}.exe")

    # runtime, mapper and the DLLs they load
    bin_dir = target / "bin"
    bin_dir.mkdir(exist_ok=True)
    for exe_name in ("sumeragi-core.exe", "basara4-core.exe"):
        shutil.copy2(core, bin_dir / exe_name)
        if (clang / "llvm-strip.exe").is_file():
            run(clang / "llvm-strip.exe", "-s", bin_dir / exe_name)
    for map_name in ("sumeragi-pad-mapper.exe", "basara4-pad-mapper.exe"):
        if mapper.is_file():
            shutil.copy2(mapper, bin_dir / map_name)
            if (clang / "llvm-strip.exe").is_file():
                run(clang / "llvm-strip.exe", "-s", bin_dir / map_name)
    for dll in (HERE / "dlls.txt").read_text().split():
        if (clang / dll).is_file():
            shutil.copy2(clang / dll, bin_dir / dll)

    # image preparation scripts and the launcher source
    scripts = target / "scripts"
    scripts.mkdir(exist_ok=True)
    for name in PREPARE_SCRIPTS:
        if (REPO / "scripts" / name).is_file():
            shutil.copy2(REPO / "scripts" / name, scripts / name)
    shutil.rmtree(target / "launcher", ignore_errors=True)
    (target / "launcher").mkdir()
    for name in ("sumeragi_launcher.py", "sumeragi_patches.py", "sumeragi.ico", "sumeragi.png"):
        if (LAUNCHER / name).is_file():
            shutil.copy2(LAUNCHER / name, target / "launcher" / name)

    # documents and shortcuts
    for doc in ("NOTICE.md", "LICENSE"):
        if (REPO / doc).is_file():
            shutil.copy2(REPO / doc, target / doc)
    for doc in ("README.txt", "README.id.txt", "Play Sumeragi Native+.cmd"):
        if (HERE / doc).is_file():
            shutil.copy2(HERE / doc, target / doc)

    if not args.update:
        for folder in ("game", "user", "out"):
            (target / folder).mkdir(exist_ok=True)
        (target / "game/PUT_YOUR_GAME_DUMP_HERE.txt").write_text(
            "Put the folder that contains eboot.bin here (or choose it with Browse in the launcher).\n"
            "No game files are included with this program.\n", encoding="utf-8")
    print("done:", target)


if __name__ == "__main__":
    main()
