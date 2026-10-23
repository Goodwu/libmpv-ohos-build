#!/bin/bash

set -euo pipefail

export PATH="${HOME}/.cargo/bin:${HOME}/.local/bin:$PATH"
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
command -v rustup >/dev/null || {
  echo "Install rustup before building; the GitHub runner already provides it." >&2
  exit 1
}
rust_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tools"]["rust"])' "$ROOT_DIR/reproducibility/source-lock.json")
cargo_c_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tools"]["cargo_c"])' "$ROOT_DIR/reproducibility/source-lock.json")
rustup toolchain install "$rust_version" --profile minimal --target aarch64-unknown-linux-ohos
cargo +"$rust_version" install cargo-c --version "$cargo_c_version" --locked --features=vendored-openssl
