#!/usr/bin/env bash
set -euo pipefail

cd /d/BVT-Studio
BLENDER='/c/Program Files/Blender Foundation/Blender 5.2/blender.exe'
PHOTO='C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png'
OUT='D:/BVT-Studio/qa_renders/effects_gallery_v01'
RECTS='D:/BVT-Studio/configs/bvt_freezer_glass_rects_1672x941.json'

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
    --repo 'D:/BVT-Studio' \
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
