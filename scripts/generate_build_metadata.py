#!/usr/bin/env python3
"""Create auditable output metadata for the OHOS native build."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "libmpv" / "arm64-build"
LOCK = ROOT / "reproducibility" / "source-lock.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_head(path: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    archive = OUT / "libmpv_aarch64.zip"
    library = OUT / "libmpv.so"
    if not archive.is_file() or not library.is_file():
        raise SystemExit("native outputs are missing")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    patches = []
    for path in sorted(ROOT.glob("patches/**/*.patch")):
        patches.append({"file": str(path.relative_to(ROOT)), "sha256": sha256(path)})
    manifest = {
        "schema": 1,
        "platform": "ohos-arm64",
        "source_commit": git_head(ROOT),
        "builder_commit": git_head(ROOT),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "workflow_run": os.environ.get("GITHUB_RUN_ID"),
        "sdk": lock["sdk"],
        "dependencies": lock["dependencies"],
        "patches": patches,
        "artifacts": [
            {"file": archive.name, "sha256": sha256(archive), "size": archive.stat().st_size},
            {"file": library.name, "sha256": sha256(library), "size": library.stat().st_size},
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": [
            {"type": "library", "name": d["name"], "version": d["ref"], "purl": d["url"] + "@" + d["commit"], "licenses": [{"license": {"id": d["license"]}}]}
            for d in lock["dependencies"]
        ],
    }
    (OUT / "sbom.cdx.json").write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(p)}  {p.name}\n" for p in sorted(OUT.glob("*.zip")) + [OUT / "libmpv.so", OUT / "manifest.json", OUT / "sbom.cdx.json"]),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
