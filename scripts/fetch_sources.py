#!/usr/bin/env python3
"""Fetch the source lock's exact inputs into a fresh native workspace.

Branches/tags are descriptive labels. Git fetches use complete commits, and
archives are verified before extraction. Native binary reuse is handled by the
package consumer; this producer never silently reuses a modified source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def validate_lock(lock: dict) -> None:
    if lock.get("schema") != 1 or lock.get("platform") != "ohos-arm64":
        raise ValueError("Expected an OHOS ARM64 source lock")
    names = set()
    for dependency in lock["dependencies"]:
        name = dependency["name"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in names:
            raise ValueError("Invalid or duplicate dependency name")
        names.add(name)
        if dependency.get("archive"):
            if Path(dependency["archive"]).name != dependency["archive"]:
                raise ValueError("Archive must be a basename")
            if not re.fullmatch(r"[0-9a-f]{64}", dependency["archive_sha256"]):
                raise ValueError("Archive requires a complete SHA256")
            url = dependency.get("archive_url", dependency["url"])
        else:
            if not re.fullmatch(r"[0-9a-f]{40}", dependency["commit"]):
                raise ValueError("Git dependencies require complete commit SHAs")
            url = dependency["url"]
        if not url.startswith("https://"):
            raise ValueError("Locked source URL must use HTTPS")
    if not {"mpv", "ffmpeg", "libplacebo", "libwebp"}.issubset(names):
        raise ValueError("Source lock omits required media dependencies")


def fetch_archive(dependency: dict, destination: Path) -> None:
    archive = destination / dependency["archive"]
    if archive.exists() and digest(archive) != dependency["archive_sha256"]:
        raise ValueError("Cached source archive differs from its lock: " + archive.name)
    if not archive.exists():
        with tempfile.NamedTemporaryFile(dir=destination, delete=False) as temporary:
            download = Path(temporary.name)
        try:
            request = urllib.request.Request(
                dependency.get("archive_url", dependency["url"]),
                headers={"User-Agent": "libmpv-ohos-source-builder"},
            )
            with urllib.request.urlopen(request, timeout=120) as source, download.open("wb") as output:
                shutil.copyfileobj(source, output)
            if digest(download) != dependency["archive_sha256"]:
                raise ValueError("Downloaded source archive differs from its lock: " + archive.name)
            download.replace(archive)
        finally:
            download.unlink(missing_ok=True)
    target = destination / dependency["name"]
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        unpacked = Path(temporary)
        with tarfile.open(archive) as source:
            source.extractall(unpacked, filter="data")
        children = list(unpacked.iterdir())
        if len(children) != 1 or not children[0].is_dir() or children[0].is_symlink():
            raise ValueError("Source archive must contain one top-level directory")
        children[0].rename(target)


def shaderc_deps(checkout: Path) -> list[tuple[Path, str, str]]:
    """Read the *pinned* shaderc DEPS; reject paths or moving refs.

    shaderc's git-sync-deps starts clone threads whose exceptions do not
    propagate to the process exit code. Do not trust that tool as a CI gate.
    """
    parser = runpy.run_path(str(checkout / "utils/git-sync-deps"))["parse_file_to_dict"]
    data = parser(str(checkout / "DEPS"))
    if (not isinstance(data.get("deps"), dict) or not data["deps"]
            or data.get("recursedeps") or data.get("deps_os")):
        raise ValueError("Unexpected shaderc DEPS format: requires review")
    selected = []
    for relative, origin in sorted(data["deps"].items()):
        path = Path(relative)
        if (path.is_absolute() or ".." in path.parts
                or not path.parts or path.parts[0] != "third_party"
                or len(path.parts) != 2 or not isinstance(origin, str)
                or "@" not in origin):
            raise ValueError("Unsafe shaderc dependency path or ref: " + str(relative))
        url, commit = origin.rsplit("@", 1)
        if not url.startswith("https://github.com/") or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("shaderc DEPS requires HTTPS GitHub and full commit SHA")
        selected.append((path, url, commit))
    return selected


def fetch_pinned_shaderc_git(url: str, commit: str, target: Path,
                             attempts: int = 3) -> None:
    """Fetch one pinned shaderc dependency with bounded network retries.

    Stage each attempt in a temporary directory, then publish only after
    checking the exact commit. Failed attempts cannot leave a partial tree.
    """
    if attempts < 1 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid pinned shaderc commit or retry count")
    if target.exists() or target.is_symlink():
        raise ValueError("Refusing to overwrite existing shaderc dependency: " + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(attempts):
        try:
            with tempfile.TemporaryDirectory(prefix=".shaderc-dep-", dir=target.parent) as temporary:
                checkout = Path(temporary) / "source"
                run("git", "init", "--quiet", str(checkout))
                run("git", "remote", "add", "origin", url, cwd=checkout)
                run("git", "fetch", "--quiet", "--no-tags", "--depth=1", "origin", commit, cwd=checkout)
                run("git", "-c", "advice.detachedHead=false", "checkout",
                    "--quiet", "--detach", "FETCH_HEAD", cwd=checkout)
                head = subprocess.check_output(
                    ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
                if head != commit:
                    raise ValueError("Shaderc dependency fetched the wrong commit")
                checkout.rename(target)
                return
        except subprocess.CalledProcessError as error:
            if attempt + 1 == attempts:
                raise RuntimeError(
                    f"Failed to fetch pinned shaderc dependency {target.name} "
                    f"at {commit} after {attempts} attempts") from error
            print(f"Retrying shaderc dependency {target.name} "
                  f"({attempt + 1}/{attempts}) after Git failure", flush=True)
            time.sleep(attempt + 1)


def sync_shaderc_deps(checkout: Path) -> None:
    for relative, url, commit in shaderc_deps(checkout):
        print(f"Fetching locked shaderc dependency: {relative} @ {commit}", flush=True)
        fetch_pinned_shaderc_git(url, commit, checkout / relative)


def fetch_git(dependency: dict, destination: Path) -> None:
    target = destination / dependency["name"]
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        checkout = Path(temporary) / "source"
        run("git", "init", "--quiet", str(checkout))
        run("git", "remote", "add", "origin", dependency["url"], cwd=checkout)
        run("git", "fetch", "--quiet", "--no-tags", "--depth=1", "origin", dependency["commit"], cwd=checkout)
        run("git", "-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=checkout)
        actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        if actual != dependency["commit"]:
            raise ValueError("Fetched Git object differs from the source lock")
        if (checkout / ".gitmodules").exists():
            run("git", "submodule", "update", "--init", "--recursive", cwd=checkout)
        if dependency["name"] == "shaderc":
            # The script and its DEPS revisions belong to the locked shaderc commit.
            sync_shaderc_deps(checkout)
        checkout.rename(target)


def fetch(lock: dict, destination: Path) -> None:
    validate_lock(lock)
    destination.mkdir(parents=True, exist_ok=True)
    existing = [d["name"] for d in lock["dependencies"] if (destination / d["name"]).exists()]
    if existing:
        raise ValueError("Source directories already exist; use a fresh workspace: " + ", ".join(existing))
    for dependency in lock["dependencies"]:
        print("Fetching locked source: " + dependency["name"], flush=True)
        if dependency.get("archive"):
            fetch_archive(dependency, destination)
        else:
            fetch_git(dependency, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=ROOT / "reproducibility/source-lock.json")
    parser.add_argument("--destination", type=Path, default=ROOT / "libmpv")
    args = parser.parse_args()
    fetch(json.loads(args.lock.read_text()), args.destination)


if __name__ == "__main__":
    main()
