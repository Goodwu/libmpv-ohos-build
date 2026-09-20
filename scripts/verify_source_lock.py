#!/usr/bin/env python3
"""Fail closed if downloaded dependency checkouts differ from the lock."""
from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    lock = json.loads((ROOT / "reproducibility/source-lock.json").read_text(encoding="utf-8"))
    failures = []
    for dependency in lock["dependencies"]:
        path = ROOT / "libmpv" / dependency["name"]
        archive = dependency.get("archive")
        if archive:
            archive_path = ROOT / "libmpv" / archive
            if not archive_path.is_file():
                failures.append(f"{dependency['name']}: source archive missing: {archive_path}")
                continue
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            if digest != dependency["archive_sha256"]:
                failures.append(f"{dependency['name']}: expected archive {dependency['archive_sha256']}, got {digest}")
            continue
        try:
            actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            failures.append(f"{dependency['name']}: checkout missing or not a git repository")
            continue
        if actual != dependency["commit"]:
            failures.append(f"{dependency['name']}: expected {dependency['commit']}, got {actual}")
    if failures:
        raise SystemExit("source lock verification failed:\n" + "\n".join(failures))
    print(f"source lock verified: {len(lock['dependencies'])} dependencies")


if __name__ == "__main__":
    main()
