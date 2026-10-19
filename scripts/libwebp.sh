#!/bin/bash
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
. "$ROOT_DIR/env.sh"
build="$ROOT_DIR/libmpv/libwebp/.ohos-build"
case "${1:-}" in
  build) ;;
  clean) rm -rf "$build"; exit 0 ;;
  *) echo 'Expected build or clean' >&2; exit 1 ;;
esac
# libwebpmux is required by FFmpeg's libwebp_anim encoder. CLI tools and
# image-file dependencies are not needed; this is a PIC static library build.
env -u CC -u CXX cmake -S "$ROOT_DIR/libmpv/libwebp" -B "$build" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$OHOS_NDK_HOME/native/build/cmake/ohos.toolchain.cmake" \
  -DOHOS_ARCH=arm64-v8a -DOHOS_PLATFORM=OHOS \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$DEST" \
  -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
  -DBUILD_SHARED_LIBS=OFF -DWEBP_LINK_STATIC=ON \
  -DWEBP_BUILD_LIBWEBPMUX=ON -DWEBP_BUILD_ANIM_UTILS=OFF \
  -DWEBP_BUILD_CWEBP=OFF -DWEBP_BUILD_DWEBP=OFF -DWEBP_BUILD_GIF2WEBP=OFF \
  -DWEBP_BUILD_IMG2WEBP=OFF -DWEBP_BUILD_VWEBP=OFF -DWEBP_BUILD_WEBPINFO=OFF \
  -DWEBP_BUILD_WEBPMUX=OFF -DWEBP_BUILD_EXTRAS=OFF -DWEBP_BUILD_FUZZTEST=OFF
cmake --build "$build" --parallel "$CORES"
cmake --install "$build"
