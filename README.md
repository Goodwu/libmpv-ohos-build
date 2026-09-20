# libmpv-ohos-build

Build scripts of [libmpv](https://github.com/mpv-player/mpv) for ohos-arm64 (API 15+).

Scripts are compatible with macOS, Linux and WSL, Windows is not supported.

## Build Dependencies

- git
- make
- python3
- pkg-conf
- gperf
- meson

ohos sdk is automatically downloaded on Linux / WSL, but you need to manually download DevEco Studio on your mac.

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

