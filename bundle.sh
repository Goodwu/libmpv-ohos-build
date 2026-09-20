#!/bin/bash

set -eu

./download.sh
./patch.sh
./build.sh

cd ./libmpv/arm64-build
zip libmpv_aarch64.zip libmpv.so
python3 ../../scripts/generate_build_metadata.py
