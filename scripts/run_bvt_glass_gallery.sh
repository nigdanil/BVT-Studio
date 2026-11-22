#!/usr/bin/env bash
set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/gallery_paths.sh"
OUT="${BVT_OUTPUT_DIR:-$REPO/qa_renders/effects_gallery_v01}"

[ -f "$PHOTO" ] || { echo "Photo not found: $PHOTO"; exit 1; }
[ -f "$RECTS" ] || { echo "Rectangles config not found: $RECTS"; exit 1; }
[ -f scripts/bvt_glass_effect_gallery.py ] || { echo 'Gallery script missing'; exit 1; }
[ -f "$BLENDER" ] || { echo "Blender missing: $BLENDER"; exit 1; }

MODES=(
  00_clean
  01_light_condensation
  02_heavy_condensation
  03_frost
  04_dirty_glass
  05_reflections
  06_micro_droplets
  07_atlas_light_no_optics
  08_atlas_light_optics
  09_atlas_medium_no_optics
  10_atlas_medium_optics
  11_atlas_heavy_streaks
  12_atlas_strong_optics_stress
)

mkdir -p "$OUT"
for MODE in "${MODES[@]}"; do
  echo "========== $MODE =========="
  "$BLENDER" \
    --background --factory-startup --python-exit-code 1 \
    --python scripts/bvt_glass_effect_gallery.py -- \
    --repo "$REPO" \
    --photo "$PHOTO" \
    --output "$OUT" \
    --rects-file "$RECTS" \
    --mode "$MODE" \
    --atlas-resolution 512
  echo "PASSED: $MODE"
done

echo '========== COMPLETE =========='
echo "GALLERY_INDEX=$OUT/index.html"
echo 'GALLERY_SCENES=13'
