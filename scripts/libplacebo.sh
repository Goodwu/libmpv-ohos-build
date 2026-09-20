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
if [ ! -d "$VULKAN_HEADERS_DIR/vulkan" ] || \
	[ ! -d "$VULKAN_HEADERS_DIR/vk_video" ] || \
	[ ! -f "$VULKAN_HEADERS_DIR/vk_video/vulkan_video_codec_vp9std.h" ] || \
	[ ! -f "$VULKAN_HEADERS_DIR/vk_video/vulkan_video_codec_vp9std_decode.h" ] || \
	[ ! -f "$OHOS_VULKAN_HEADERS_DIR/vulkan_ohos.h" ]; then
	printf 'Vulkan headers are incomplete: %s\n' "$VULKAN_HEADERS_DIR" >&2
	exit 1
fi

mkdir -p "$DEST/include" "$DEST/lib/pkgconfig"
cp -R "$VULKAN_HEADERS_DIR/vulkan" "$DEST/include/"
cp "$OHOS_VULKAN_HEADERS_DIR/vulkan_ohos.h" "$DEST/include/vulkan/"
mkdir -p "$DEST/include/vk_video"
cp -R "$VULKAN_HEADERS_DIR/vk_video/." "$DEST/include/vk_video/"

if [ -f "$OHOS_VULKAN_HEADERS_DIR/vk_ohos_native_buffer.h" ]; then
	cp "$OHOS_VULKAN_HEADERS_DIR/vk_ohos_native_buffer.h" "$DEST/include/vulkan/"
else
cat > "$DEST/include/vulkan/vk_ohos_native_buffer.h" <<'EOF'
#ifndef VK_OHOS_NATIVE_BUFFER_H_
#define VK_OHOS_NATIVE_BUFFER_H_ 1
#define VK_OHOS_NATIVE_BUFFER_EXTENSION_NAME "VK_OHOS_native_buffer"
#endif
EOF
fi
VULKAN_HEADER_VERSION=$(sed -n 's/^#define VK_HEADER_VERSION \([0-9][0-9]*\)$/\1/p' "$DEST/include/vulkan/vulkan_core.h" | head -n 1)
if ! grep -Eq '^#define VK_HEADER_VERSION_COMPLETE VK_(MAKE_VERSION\(1, 4,|MAKE_API_VERSION\(0, 1, 4,)' "$DEST/include/vulkan/vulkan_core.h"; then
	printf 'Unsupported Vulkan header API version; expected 1.4\n' >&2
	exit 1
fi
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
