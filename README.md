# libmpv-ohos-build

在原仓库基础上增加了由 [@0Chencc](https://github.com/0Chencc) 为 Kazumi 编写的 [patch](./patches/ffmpeg/ffmpeg-hls-kazumi-combined.patch) 用于实现 hls 广告跳过功能。

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

## 如何开启广告跳过

```shell
demuxer-lavf-o=hls_ad_filter=1
```
