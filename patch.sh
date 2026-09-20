#!/bin/bash

set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

./scripts/check-ohos-hdr-contract.sh
python3 ./scripts/verify_source_lock.py

while IFS= read -r dep_path; do
  dep=${dep_path##*/}
  target="$ROOT/libmpv/$dep"
  test -d "$target" || {
    echo "Missing dependency checkout: $target" >&2
    exit 1
  }

  pushd "$target" >/dev/null
  echo "Patching $dep..."
  while IFS= read -r patch; do
    [ -n "$patch" ] || continue
    echo "Applying $patch..."
    if git apply --unidiff-zero --check "$patch"; then
      git apply --unidiff-zero "$patch"
    elif git apply --unidiff-zero --reverse --check "$patch"; then
      echo "Already applied: $patch"
    else
      echo "Patch does not apply cleanly: $patch" >&2
      exit 1
    fi
  done < <(find "$dep_path" -maxdepth 1 -type f -name '*.patch' -print | sort)
  popd >/dev/null
done < <(find "$ROOT/patches" -mindepth 1 -maxdepth 1 -type d -print | sort)
