# PiliPlus OHOS WebP build contract

The application's actual `MpvConvertWebp` requests `of=webp`, `ovc=libwebp_anim`, `ofopts=loop=0` and presets. The previous minimal FFmpeg configuration disabled all muxers and enabled only PNG/MJPEG encoders; enabling the application entrypoint alone cannot provide this feature.

Add the upstream libwebp v1.6.0 source (tag object b7e29b9d75bd31422b00c2a446d49d7af06c328d, commit 4fa21912338357f89e4fd51cf2368325b59e9bd9, checked against upstream Gitiles and its GitHub mirror). Build static PIC libwebp, libwebpmux and their required internal libraries with the OHOS CMake toolchain. Enable both FFmpeg WebP encoders and the WebP muxer while retaining the previous decoder/OHCodec configuration. Static pkg-config closure is required; do not load a host libwebp into the target build.

`bundle.sh` now requires compile-time feature evidence from FFmpeg config, generated codec/muxer registries and the final AArch64 libmpv. The evidence binds to the library SHA256 and is embedded in manifest.json, covered by SHA256SUMS. It does not claim actual device encoding, UI cancellation, or memory/resource safety. Six negative/positive Python tests validate the gate; the new target build must separately prove cross-compilation and HAP payload identity.

Do not reuse an old green native/HAP run for this revision or disable the feature checks when the build fails.
