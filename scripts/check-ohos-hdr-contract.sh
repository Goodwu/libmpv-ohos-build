#!/bin/bash

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PATCH="$ROOT/patches/mpv/ohos-color-contract-diagnostics.patch"
MPV_ROOT="${OHOS_MPV_ROOT:-$ROOT/libmpv/mpv}"
SOURCE="$MPV_ROOT/video/out/ohos_common.c"

fail() {
  echo "OHOS HDR/color contract check failed: $*" >&2
  exit 1
}

test -f "$PATCH" || fail "missing $PATCH"

# Check additions, not removed context lines, so this describes the source
# that patch.sh will produce from a clean feat-ohos-0.41.0 checkout.
added=$(mktemp)
trap 'rm -f "$added"' EXIT
awk '/^\+[^+]/ { print substr($0, 2) }' "$PATCH" > "$added"

if rg -n 'if[[:space:]]*\([[:space:]]*0' "$PATCH" "$added"; then
  fail 'constant-false control flow is not a white-point contract'
fi
rg -q 'SET_HDR_WHITE_POINT_BRIGHTNESS' "$added" || \
  fail 'patch does not write the HDR white point'
rg -q 'SET_SDR_WHITE_POINT_BRIGHTNESS' "$added" || \
  fail 'patch does not write the SDR white point'
rg -q 'white-point operations' "$added" || \
  fail 'patch does not declare the NativeWindow white-point owner'
rg -q 'owner=ohos_vo' "$added" || \
  fail 'patch diagnostics do not identify the white-point owner'
rg -q 'sdr_white_point_valid = false' "$added" || \
  fail 'patch does not invalidate the SDR white-point cache'

# The two operations must not be reintroduced in another native patch.
while IFS= read -r patch_file; do
  [ "$patch_file" = "$PATCH" ] && continue
  if rg -q 'SET_HDR_WHITE_POINT_BRIGHTNESS|SET_SDR_WHITE_POINT_BRIGHTNESS' \
      "$patch_file"; then
    fail "another patch writes NativeWindow white-point state: $patch_file"
  fi
done < <(find "$ROOT/patches" -type f -name '*.patch' -print | sort)

if [ -d "$MPV_ROOT/.git" ]; then
  if git -C "$MPV_ROOT" apply --check "$PATCH" >/dev/null 2>&1; then
    source_state=clean
  elif git -C "$MPV_ROOT" apply --reverse --check "$PATCH" >/dev/null 2>&1; then
    source_state=patched
  elif rg -q 'owner=ohos_vo' "$SOURCE" &&
       rg -q 'OHOS consumer color mismatch' "$SOURCE"; then
    # The source may also contain a later, in-tree diagnostic patch.  The
    # color-contract patch is already present in that state; validate its
    # invariants below instead of rejecting the complete patch chain.
    source_state=patched
  else
    fail 'mpv source is neither clean nor the result of the color-contract patch'
  fi

  if [ "$source_state" = patched ]; then
    test -f "$SOURCE" || fail "missing $SOURCE"
    if rg -n 'if[[:space:]]*\([[:space:]]*0' "$SOURCE"; then
      fail 'patched source contains constant-false control flow'
    fi
    rg -q 'SET_HDR_WHITE_POINT_BRIGHTNESS' "$SOURCE" || \
      fail 'patched source does not write the HDR white point'
    rg -q 'SET_SDR_WHITE_POINT_BRIGHTNESS' "$SOURCE" || \
      fail 'patched source does not write the SDR white point'
    rg -q 'owner=ohos_vo' "$SOURCE" || \
      fail 'patched source does not identify the white-point owner'
    rg -q 'hdr_white_point_valid = false' "$SOURCE" || \
      fail 'patched source does not invalidate the HDR white-point cache'
    rg -q 'sdr_white_point_valid = false' "$SOURCE" || \
      fail 'patched source does not invalidate the SDR white-point cache'

    white_point_files=$(rg -l \
      'SET_HDR_WHITE_POINT_BRIGHTNESS|SET_SDR_WHITE_POINT_BRIGHTNESS' \
      "$MPV_ROOT/video/out" || true)
    test "$(printf '%s\n' "$white_point_files" | sed '/^$/d' | wc -l | tr -d ' ')" = 1 || \
      fail 'white-point operations have more than one source writer'
    test "$white_point_files" = "$SOURCE" || \
      fail "white-point writer is not $SOURCE"
  fi
fi

if [ -n "${MEDIA_KIT_ROOT:-}" ]; then
  controller="$MEDIA_KIT_ROOT/media_kit_video/lib/src/video_controller/ohos_video_controller/real.dart"
  hdr_output="$MEDIA_KIT_ROOT/libs/ohos/media_kit_libs_ohos/ohos/src/main/cpp/hdr_output.cc"
  test -f "$controller" || fail "missing $controller"
  test -f "$hdr_output" || fail "missing $hdr_output"
  if rg -q 'Future<void>\.delayed|_diagnosticDelayedHdrReapplyMs' "$controller"; then
    fail 'delayed HDR replay is forbidden by the lifecycle contract'
  fi
  if rg -q 'SET_HDR_WHITE_POINT_BRIGHTNESS|SET_SDR_WHITE_POINT_BRIGHTNESS' "$hdr_output"; then
    fail 'FFI must not write NativeWindow white-point state'
  fi
  rg -q 'setPropertyForRelease' "$controller" || fail 'missing release property path'
  rg -q '_replayPendingHdrConfiguration' "$controller" || fail 'missing HDR replay path'
  rg -q '_hdrConfigRevision' "$controller" || fail 'missing HDR configuration revision'
fi

echo 'OHOS HDR lifecycle/color contract checks passed.'
