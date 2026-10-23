#!/usr/bin/env python3
"""Export the completed OHOS build and a media-kit native-package spec.

The common media-kit packer creates manifest.json from this spec afterwards.
Only compilation/input identity is certified here; device execution is not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from verify_media_features import verify as verify_media_features

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_HEADERS = ("client.h", "render.h", "render_gl.h", "stream_cb.h")
CAPABILITIES = ["libmpv", "webp-encode", "webp-animated-encode", "webp-mux"]
REQUIRED_SYMBOLS = {
    "mpv_client_api_version", "mpv_create", "mpv_initialize", "mpv_terminate_destroy",
    "mpv_get_property", "mpv_set_property", "mpv_command",
    "mpv_render_context_create", "mpv_render_context_render", "mpv_render_context_free",
}


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def command(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def source_identity(root: Path) -> dict:
    if command("git", "status", "--porcelain", "--untracked-files=normal", cwd=root):
        raise ValueError("Commit the producer recipe before creating a reusable native package")
    lock_path = root / "reproducibility/source-lock.json"
    lock = json.loads(lock_path.read_text())
    sources = {}
    for dependency in lock["dependencies"]:
        record = {"repository": dependency["url"]}
        if dependency["commit"] != "archive-only":
            record["commit"] = dependency["commit"]
        if dependency.get("archive"):
            record["archive_url"] = dependency.get("archive_url", dependency["url"])
            record["archive_sha256"] = dependency["archive_sha256"]
        sources[dependency["name"]] = record
    patches = {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted((root / "patches").rglob("*.patch"))
    }
    sdk = Path(os.environ["OHOS_NDK_HOME"])
    sdk_metadata = sdk.parent / "sdk-pkg.json"
    sdk_info = json.loads(sdk_metadata.read_text())["data"]
    rust = lock["tools"]["rust"]
    actual_tools = {
        "clang": command(str(sdk / "native/llvm/bin/clang"), "--version"),
        "meson": command("meson", "--version"),
        "rust": command("rustup", "run", rust, "rustc", "--version"),
        "cargo_c": command("rustup", "run", rust, "cargo", "cinstall", "--version"),
    }
    if actual_tools["meson"] != lock["tools"]["meson"]:
        raise ValueError("Meson differs from the source lock")
    if not actual_tools["rust"].startswith("rustc " + rust + " "):
        raise ValueError("Rust differs from the source lock")
    if lock["tools"]["cargo_c"].split("+", 1)[0] not in actual_tools["cargo_c"]:
        raise ValueError("cargo-c differs from the source lock")
    return {
        "origin": "source",
        "sources": sources,
        "recipe": {
            "repository": command("git", "config", "--get", "remote.origin.url", cwd=root).removesuffix(".git"),
            "commit": command("git", "rev-parse", "HEAD", cwd=root),
            "source_lock_sha256": digest(lock_path),
        },
        "toolchain": {
            "sdk": lock["sdk"],
            "sdk_metadata": {"sha256": digest(sdk_metadata), "version": sdk_info["version"], "api": sdk_info["apiVersion"]},
            "locked_tools": lock["tools"], "actual_tools": actual_tools,
        },
        "patches": patches,
        "options": {"target": "aarch64-linux-ohos", "profile": "default", "webp": True},
    }


def inspect_runtime(library: Path, sdk: Path) -> dict:
    symbols_text = command(str(sdk / "native/llvm/bin/llvm-nm"), "--dynamic", "--defined-only", str(library))
    symbols = {line.split()[-1] for line in symbols_text.splitlines() if line.split()}
    if not REQUIRED_SYMBOLS.issubset(symbols):
        raise ValueError("Runtime omits required libmpv exports: " + ", ".join(sorted(REQUIRED_SYMBOLS - symbols)))
    dynamic = command(str(sdk / "native/llvm/bin/llvm-readelf"), "--dynamic", str(library))
    needed = sorted(set(re.findall(r"\(NEEDED\).*Shared library: \[([^]]+)\]", dynamic)))
    sdk_libraries = {path.name for path in (sdk / "native").rglob("*.so*") if path.is_file()}
    missing = set(needed) - sdk_libraries
    if missing:
        raise ValueError("Unbundled non-SDK runtime dependencies: " + ", ".join(sorted(missing)))
    return {
        "scope": "ELF-export-and-platform-dependency-inspection",
        "libmpv_sha256": digest(library), "required_symbols": sorted(REQUIRED_SYMBOLS),
        "sdk_runtime_dependencies": needed, "runtime_execution": "not-run",
    }


def export(root: Path, output: Path, spec_path: Path, identity: dict, runtime_report: dict | None = None) -> dict:
    if output.exists():
        raise ValueError("Output already exists; packages are immutable")
    if spec_path.resolve().is_relative_to(output.resolve()):
        raise ValueError("Keep the spec outside the package root")
    prefix = root / "libmpv/arm64-build"
    features = verify_media_features(root)
    metadata = json.loads((prefix / "manifest.json").read_text())
    lock = json.loads((root / "reproducibility/source-lock.json").read_text())
    if metadata["dependencies"] != lock["dependencies"] or metadata["sdk"] != lock["sdk"]:
        raise ValueError("Native build metadata differs from the selected source lock")
    if metadata["builder_commit"] != identity["recipe"]["commit"]:
        raise ValueError("Native build metadata belongs to a different producer commit")
    if {entry["file"]: entry["sha256"] for entry in metadata["patches"]} != identity["patches"]:
        raise ValueError("Native build metadata differs from the selected patch stack")
    if metadata.get("media_features") != features:
        raise ValueError("Native build metadata does not describe these compiled features")
    library = prefix / "libmpv.so"
    archive = prefix / "libmpv_aarch64.zip"
    artifact_hashes = {entry["file"]: entry["sha256"] for entry in metadata["artifacts"]}
    if any(artifact_hashes.get(path.name) != digest(path) for path in (library, archive)):
        raise ValueError("Native files differ from their build metadata")
    expected = library.read_bytes()
    with zipfile.ZipFile(archive) as source:
        if source.namelist() != ["libmpv.so"] or source.read("libmpv.so") != expected:
            raise ValueError("Native archive differs from the current build")
    # The public headers must be from the very source Meson compiled, including
    # the applied patch stack. Do not reuse independently downloaded headers.
    installed = prefix / "mpv/include/mpv"
    compiled = root / "libmpv/mpv/include/mpv"
    for name in PUBLIC_HEADERS:
        if (installed / name).read_bytes() != (compiled / name).read_bytes():
            raise ValueError("Installed header differs from compiled mpv source: " + name)
    installed_pc = (prefix / "mpv/lib/pkgconfig/mpv.pc").read_text()
    versions = [line.partition(":")[2].strip() for line in installed_pc.splitlines() if line.startswith("Version:")]
    if len(versions) != 1:
        raise ValueError("Installed mpv.pc has no unique client API version")
    output.mkdir(parents=True)
    (output / "lib").mkdir()
    (output / "include/mpv").mkdir(parents=True)
    (output / "provenance").mkdir()
    shutil.copy2(library, output / "lib/libmpv.so")
    shutil.copy2(archive, output / "lib/libmpv_aarch64.zip")
    for name in PUBLIC_HEADERS:
        shutil.copy2(installed / name, output / "include/mpv" / name)
    for name in ("manifest.json", "media-features.json", "sbom.cdx.json", "SHA256SUMS"):
        # PiliPlus' OHOS native-input gate consumes the original producer
        # manifest beside libmpv.so. Keep its unchanged archive and receipts
        # together; the package-wide manifest lives at the package root.
        shutil.copy2(prefix / name, output / "lib" / name)
    shutil.copy2(root / "reproducibility/source-lock.json", output / "provenance/source-lock.json")
    if runtime_report is not None:
        if runtime_report["libmpv_sha256"] != digest(library):
            raise ValueError("ELF report belongs to a different library")
        (output / "provenance/elf-report.json").write_text(json.dumps(runtime_report, indent=2, sort_keys=True) + "\n")
    # This pkg-config file is relocatable; the native dependencies are already
    # linked into libmpv. Platform SDK libraries remain provided by the OHOS SDK.
    pkgconfig = output / "lib/pkgconfig"
    pkgconfig.mkdir()
    (pkgconfig / "mpv.pc").write_text(
        "prefix=${pcfiledir}/../..\nlibdir=${prefix}/lib\nincludedir=${prefix}/include\n\n"
        "Name: mpv\nDescription: Locked OHOS libmpv client SDK\n"
        "Version: " + versions[0] + "\n"
        "Libs: -L${libdir} -lmpv\nCflags: -I${includedir}\n"
    )
    spec = {
        "schema": 1,
        "kind": "media-kit-native-package",
        "platform": "ohos",
        "architectures": ["arm64"],
        "profile": "default",
        "identity": identity,
        "layout": {"archive": "lib/libmpv_aarch64.zip", "runtime": "lib/libmpv.so", "include": "include"},
        "capabilities": CAPABILITIES,
        "validation": {"compiled": True, "runtime": False, "device": False},
    }
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    return spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    args = parser.parse_args()
    identity = source_identity(ROOT)
    report = inspect_runtime(ROOT / "libmpv/arm64-build/libmpv.so", Path(os.environ["OHOS_NDK_HOME"]))
    export(ROOT, args.output, args.spec, identity, report)
    print(json.dumps({"root": str(args.output.resolve()), "spec": str(args.spec.resolve())}))


if __name__ == "__main__":
    main()
