#!/bin/bash

set -eu

export PATH="${HOME}/.cargo/bin:${HOME}/.local/bin:$PATH"
if command -v rustup &> /dev/null; then
  echo "rustup is already installed"
else
  echo "Installing rustup..."
  wget -qO - https://sh.rustup.rs | sh -s -- -y
fi

if ! rustup show active-toolchain &> /dev/null; then
  echo "Selecting the stable Rust toolchain..."
  rustup default stable
fi

rustup target add aarch64-unknown-linux-ohos
cargo install cargo-c --features=vendored-openssl
