#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
if [ ! -d "$ROOT/libmpv/libwebp" ]; then
  git -c advice.detachedHead=false clone --depth 1 --branch v1.6.0 \
    https://github.com/webmproject/libwebp.git "$ROOT/libmpv/libwebp"
fi
# patch.sh verifies this checkout against the complete source lock before builds.
