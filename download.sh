#!/bin/bash

set -eu

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT_DIR"

# Reuse verified *packages* in the application pipeline. Native production uses
# an empty output prefix so an old library can never acquire a fresh manifest.
if [ -d ./libmpv/arm64-build ] && [ -n "$(ls -A ./libmpv/arm64-build)" ]; then
  echo "Native output prefix is not empty; use a fresh build workspace." >&2
  exit 1
fi
mkdir -p ./libmpv/arm64-build

if [ "$(uname -s)" = "Linux" ]; then
  : "${OHOS_NDK_HOME:?Set OHOS_NDK_HOME to the locked HarmonyOS SDK (CI uses setup-ohos).}"
  ohos_ndk_home=$OHOS_NDK_HOME
  test -x "$ohos_ndk_home/native/llvm/bin/clang"
  rm -f ./libmpv/arm64-crossfile.ini
  sed "s#/sdk/linux#$ohos_ndk_home#g" \
    ./crossfiles/arm64-crossfile-linux.ini > ./libmpv/arm64-crossfile.ini
elif [ "$(uname -s)" = "Darwin" ]; then
  ohos_ndk_home=${OHOS_NDK_HOME:-/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony}
  test -x "$ohos_ndk_home/native/llvm/bin/clang"
  sed "s#/sdk/linux#$ohos_ndk_home#g" \
    ./crossfiles/arm64-crossfile-linux.ini > ./libmpv/arm64-crossfile.ini
else
  echo "Unsupported platform." >&2
  exit 1
fi

./download/download-ohos-rs.sh
python3 ./scripts/fetch_sources.py
