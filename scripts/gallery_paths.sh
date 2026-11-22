#!/usr/bin/env bash
# Shared gallery paths. Source from any gallery runner.
BVT_ROOT_POSIX="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "$BVT_ROOT_POSIX"
if command -v cygpath >/dev/null 2>&1; then
  REPO="$(cygpath -am "$BVT_ROOT_POSIX")"
else
  REPO="$BVT_ROOT_POSIX"
fi
EXAMPLE="${BVT_EXAMPLE_DIR:-$REPO/examples/freezer_planogram}"
PHOTO="${BVT_PHOTO:-$EXAMPLE/images/BVT_Freezer_Planogram_16x9_v11_eng.png}"
RECTS="${BVT_RECTS:-$EXAMPLE/configs/bvt_freezer_glass_rects_1672x941.json}"
RECT="$RECTS"
CONFIG="${BVT_CONFIG:-$EXAMPLE/configs/effects_gallery_v02.json}"
if [[ -n "${BVT_BLENDER:-}" ]]; then
  BLENDER="$BVT_BLENDER"
elif command -v blender >/dev/null 2>&1; then
  BLENDER="$(command -v blender)"
else
  BLENDER="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"
fi
