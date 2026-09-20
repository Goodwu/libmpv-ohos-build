#!/bin/bash

set -eu

ROOT_DIR=$(cd $(dirname "$0")/..; pwd)

. $ROOT_DIR/env.sh

pushd $ROOT_DIR/libmpv/libplacebo

if [ "$1" == "build" ]; then
	echo -e "\nBuilding libplacebo..."
elif [ "$1" == "clean" ]; then
	rm -rf .build
	exit 0
else
	exit 1
fi

mkdir -p .build
cd .build

meson setup .. \
  --cross-file $ROOT_DIR/libmpv/arm64-crossfile.ini \
  --prefix=$DEST \
  -Ddovi=enabled \
  -Dlcms=enabled \
  -Dshaderc=enabled \
  -Dvulkan=enabled \
  -Dopengl=enabled \
  -Ddemos=false
ninja -j$CORES
ninja install

# libplacebo resolves Vulkan through its recursive Vulkan-Headers submodule, but
# mpv discovers Vulkan through pkg-config in a separate Meson project. Export
# the same headers and OHOS Vulkan loader as a normal Vulkan package so mpv can
# resolve the dependency without relying on host Vulkan development files.
VULKAN_HEADERS_DIR=$ROOT_DIR/libmpv/libplacebo/3rdparty/Vulkan-Headers/include
OHOS_VULKAN_HEADERS_DIR=$OHOS_NDK_HOME/native/sysroot/usr/include/vulkan
if [ ! -d "$VULKAN_HEADERS_DIR/vulkan" ] || [ ! -d "$VULKAN_HEADERS_DIR/vk_video" ] || \
	[ ! -f "$OHOS_VULKAN_HEADERS_DIR/vulkan_ohos.h" ] || \
	[ ! -f "$OHOS_VULKAN_HEADERS_DIR/vk_ohos_native_buffer.h" ]; then
	printf 'Vulkan headers are missing: %s\n' "$VULKAN_HEADERS_DIR" >&2
	exit 1
fi

mkdir -p "$DEST/include" "$DEST/lib/pkgconfig"
cp -R "$VULKAN_HEADERS_DIR/vulkan" "$VULKAN_HEADERS_DIR/vk_video" "$DEST/include/"
cp "$OHOS_VULKAN_HEADERS_DIR/vulkan_ohos.h" \
	"$OHOS_VULKAN_HEADERS_DIR/vk_ohos_native_buffer.h" "$DEST/include/vulkan/"
VULKAN_HEADER_VERSION=$(sed -n 's/^#define VK_HEADER_VERSION \([0-9][0-9]*\)$/\1/p' "$VULKAN_HEADERS_DIR/vulkan/vulkan_core.h" | head -n 1)
VULKAN_VERSION=1.4.$VULKAN_HEADER_VERSION
if [ -z "$VULKAN_HEADER_VERSION" ]; then
	printf 'Unable to determine Vulkan header version\n' >&2
	exit 1
fi
cat > "$DEST/lib/pkgconfig/vulkan.pc" <<EOF
prefix=$DEST
includedir=\${prefix}/include
libdir=$OHOS_NDK_HOME/native/sysroot/usr/lib

Name: Vulkan
Description: Vulkan loader for OpenHarmony
Version: $VULKAN_VERSION
Libs: -L\${libdir} -lvulkan
Cflags: -I\${includedir}
EOF

popd
