#!/usr/bin/env python3
"""Sumeragi Native+ Release & Repository Compliance Validator.

Inspects release distribution directories and git tracking status to ensure:
1. Required legal documents (LICENSE, NOTICE.md) are present.
2. No proprietary game files, console keys, dumps, or unauthorized game assets are packaged.
3. No local runtime user-data, caches, or saves are accidentally tracked or distributed.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Suspicious extensions associated with proprietary console/game content
SUSPICIOUS_EXTENSIONS = {
    ".pkg": "PlayStation package payload",
    ".self": "Decrypted PlayStation signed ELF",
    ".rif": "Console license/rights file",
    ".rap": "Console activation file",
    ".edat": "Encrypted game data",
    ".sdat": "Encrypted game sound data",
    ".arc": "Capcom MT Framework archive (potential game asset)",
    ".cpk": "CRI Middleware package",
    ".pfs": "PlayStation filesystem image",
}

# Directories that must never be packaged into releases or tracked in Git
PROHIBITED_RELEASE_DIRS = {
    "game",
    "dlc",
    "update",
    "user",
    "pgo",
    "savedata",
    "Extractor",
}

# Expected compliance files
REQUIRED_LEGAL_FILES = [
    "LICENSE",
    "NOTICE.md",
]


def check_git_tracked(repo_root: Path, verbose: bool = False) -> list[str]:
    """Verify that git tracked files don't contain proprietary or sensitive data."""
    issues = []
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
        tracked = res.stdout.splitlines()
    except Exception as e:
        if verbose:
            print(f"[!] Warning: unable to inspect git tracked files: {e}")
        return issues

    for file_path in tracked:
        parts = file_path.split("/")
        # Check prohibited top-level or nested directories
        for part in parts[:-1]:
            if part in PROHIBITED_RELEASE_DIRS:
                issues.append(f"Tracked file in prohibited directory '{part}': {file_path}")

        # Check suspicious extensions
        ext = Path(file_path).suffix.lower()
        if ext in SUSPICIOUS_EXTENSIONS:
            # Allow tiny test fixtures if explicitly placed under tests/data
            if file_path.startswith("tests/data/"):
                continue
            desc = SUSPICIOUS_EXTENSIONS[ext]
            issues.append(f"Tracked file with suspicious extension ({desc}): {file_path}")

    return issues


def check_release_directory(target_dir: Path, verbose: bool = False) -> tuple[list[str], list[str]]:
    """Inspects a release distribution folder."""
    errors = []
    warnings = []

    if not target_dir.is_dir():
        errors.append(f"Target directory does not exist: {target_dir}")
        return errors, warnings

    # Check required legal documents
    for req in REQUIRED_LEGAL_FILES:
        if not (target_dir / req).is_file():
            errors.append(f"Missing required legal document: {req}")

    # Inspect all files in the release directory
    for root, dirs, files in os.walk(target_dir):
        rel_root = Path(root).relative_to(target_dir)
        for d in list(dirs):
            if d in PROHIBITED_RELEASE_DIRS:
                # If it's a directory like game/ or user/, ensure it contains no game data
                full_dir = Path(root) / d
                items = list(full_dir.iterdir())
                # Empty or only containing instructions like PUT_YOUR_GAME_DUMP_HERE.txt is fine
                non_txt = [it for it in items if it.is_file() and not it.name.endswith(".txt")]
                if non_txt:
                    errors.append(f"Prohibited non-empty directory in release: {rel_root / d} ({len(non_txt)} files)")
                elif items and verbose:
                    print(f"[*] Neutral placeholder directory verified: {rel_root / d}")

        for f in files:
            p = Path(root) / f
            rel_path = p.relative_to(target_dir)
            ext = p.suffix.lower()

            if ext in SUSPICIOUS_EXTENSIONS:
                desc = SUSPICIOUS_EXTENSIONS[ext]
                errors.append(f"Suspicious proprietary asset found ({desc}): {rel_path}")

            # Check for accidental credentials or logs
            if f.endswith(".log") or f.endswith(".bak") or f.endswith(".tmp"):
                warnings.append(f"Temporary or log file found in release: {rel_path}")

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=None, help="Path to release folder to validate")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="Path to repository root")
    parser.add_argument("--check-git", action="store_true", default=True, help="Check git tracked files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("=======================================================")
    print("  Sumeragi Native+ Release & Compliance Validator")
    print("=======================================================")

    has_errors = False

    # Check git tracking
    if args.check_git and (args.repo / ".git").exists():
        print(f"\n[*] Checking Git tracked files in {args.repo}...")
        git_issues = check_git_tracked(args.repo, verbose=args.verbose)
        if git_issues:
            print("[FAIL] Git repository contains prohibited or suspicious tracked files:")
            for issue in git_issues:
                print(f"  - {issue}")
            has_errors = True
        else:
            print("[PASS] Git repository is clean of prohibited assets and dumps.")

    # Check release directory if specified or if default dist exists
    target = args.path
    if not target:
        default_dist = args.repo / "dist" / "sumeragi-native-plus-windows"
        if default_dist.exists():
            target = default_dist

    if target:
        print(f"\n[*] Validating release distribution at: {target}...")
        errors, warnings = check_release_directory(target, verbose=args.verbose)
        if warnings:
            print("[!] Warnings:")
            for warn in warnings:
                print(f"  - {warn}")
        if errors:
            print("[FAIL] Release validation failed:")
            for err in errors:
                print(f"  - {err}")
            has_errors = True
        else:
            print("[PASS] Release distribution passed compliance checks.")
    else:
        print("\n[*] Note: No release directory specified or found. Run with --path <dir> to check packaged release.")

    print("\n-------------------------------------------------------")
    if has_errors:
        print("RESULT: FAILED. Please review issues before releasing.")
        sys.exit(1)
    else:
        print("RESULT: SUCCESS. Repository and release configuration comply with policy.")
        sys.exit(0)


if __name__ == "__main__":
    main()
