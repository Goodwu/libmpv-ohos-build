# libmpv-ohos-build

Build scripts of [libmpv](https://github.com/mpv-player/mpv) for ohos-arm64 (API 15+).

Scripts are compatible with macOS, Linux and WSL, Windows is not supported.

## Build Dependencies

- git
- make
- python3 (3.12 or newer)
- pkg-conf
- gperf
- meson

Install the HarmonyOS SDK selected in `reproducibility/source-lock.json` and
set `OHOS_NDK_HOME` to its `openharmony` directory. GitHub Actions installs the
locked SDK automatically. On macOS, the default is DevEco Studio's SDK.
Install rustup before a local build; the locked Rust and cargo-c versions are
selected by the build scripts.

## Build

```shell
chmod +x *.sh */*.sh
./bundle.sh
```

## 可复现 OHOS ARM64 构建

当前构建输入锁定在 [`reproducibility/source-lock.json`](./reproducibility/source-lock.json)。
`bundle.sh` 会下载依赖、应用 `patches/`、验证所有依赖 checkout 的完整 commit，构建
`libmpv.so`，并生成：

- `libmpv_aarch64.zip`：HAP 使用的 ARM64 native archive；
- `manifest.json`：源码、SDK、依赖、patch、产物 hash 和 CI run 信息；
- `sbom.cdx.json`：CycloneDX 依赖清单和许可证标识；
- `SHA256SUMS`：所有交付文件的 SHA-256 清单。

GitHub Actions 使用固定 commit 的 `ErBWs/setup-ohos` 和 CLI tools 版本，在干净
Ubuntu runner 上执行相同的 `bundle.sh`。CI 只上传经过 checksum/JSON 校验的 artifact；
Release 发布应使用经过审核的 manifest 和不可变 tag，不使用日期覆盖旧 Release。

## Reusable native SDK

The source producer now fetches the complete commits in the source lock,
including the current WebP encoder/muxer configuration. Descriptive branches in
the lock do not choose a moving checkout. Use a fresh producer workspace for a
source build; existing dependency trees and a nonempty output prefix are
rejected. Reuse a verified native package when native inputs have not changed.

After committing the producer recipe and running `./bundle.sh`:

```sh
python3 scripts/package_native.py \
  --output /absolute/path/native-package \
  --spec /absolute/path/native-package-spec.json
python3 /path/to/media-kit/tool/native_package/package.py create \
  --root /absolute/path/native-package \
  --spec /absolute/path/native-package-spec.json
```

The package includes `lib/libmpv_aarch64.zip`, `lib/libmpv.so`, the public headers
from the same compiled source under `include/mpv`, and a relocatable `mpv.pc`.
The original build manifest, feature report, SBOM and checksums remain beside
the runtime in `lib/` for PiliPlus' OHOS native-input check; the source lock and
ELF inspection report are under `provenance`. The exporter rejects stale
archives, a different builder commit or patch stack, mismatched headers,
missing public API exports, and unbundled non-SDK shared dependencies.
The common packer binds every payload file and relative symbolic link to
`manifest.json`; its printed SHA256 is the application's required input.

`.github/workflows/native-package.yml` is callable with
`producer_repository`, `producer_ref` (full SHA), `media_kit_ref` (full SHA), and
`artifact_name`. It uploads `native-package.tar.gz`, the package spec and a
receipt, and returns `manifest_sha256`, `identity_sha256`, and `archive_sha256`.
It does not publish a release. The application can pass the verified archive
through `MEDIA_KIT_OHOS_LIBMPV_ARCHIVE` and its actual SHA256, or consume the
complete package using media-kit's native-package interface.

The package records compiled WebP support and ARM64 identity. Runtime playback,
device WebP encoding and HDR/display acceptance remain explicitly unverified.

Run the input/package gates without downloading the native dependencies:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
```
