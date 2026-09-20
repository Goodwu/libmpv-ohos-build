#!/bin/bash

set -eu

mkdir -p ./libmpv/arm64-build

if [ "$(uname -s)" = "Linux" ]; then
  ohos_ndk_home=${OHOS_NDK_HOME:-/home/wuweiwei1/ohos-sdk/command-line-tools/sdk/default/openharmony}
  if [ ! -d "$ohos_ndk_home" ]; then
    echo "Downloading OpenHarmony SDK..."
    ./download/download-sdk.sh
  fi
  rm -f ./libmpv/arm64-crossfile.ini
  sed "s#/sdk/linux#$ohos_ndk_home#g" \
    ./crossfiles/arm64-crossfile-linux.ini > ./libmpv/arm64-crossfile.ini
elif [ "$(uname -s)" = "Darwin" ]; then
  echo "Using DevEco Studio for macOS, please make sure DevEco Studio is installed."
  ln -sf ../crossfiles/arm64-crossfile-macos.ini ./libmpv/arm64-crossfile.ini
else
  echo "Unsupported platform." >&2
  exit 1
fi

./download/download-ohos-rs.sh
./download/download-deps.sh
