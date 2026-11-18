#!/usr/bin/env bash
set -euo pipefail
cd /d/BVT-Studio
BLENDER="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"
PHOTO="C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png"
REPO="D:/BVT-Studio"
OUT="D:/BVT-Studio/qa_renders/effects_gallery_v02"
RECTS="$REPO/configs/bvt_freezer_glass_rects_1672x941.json"
# Keep any user-edited v0.1 rectangle definitions intact; use v0.2 defaults otherwise.
[[ -f "$RECTS" ]] || RECTS="$REPO/configs/bvt_freezer_glass_rects_v02_default.json"
CONFIG="$REPO/configs/effects_gallery_v02.json"

[[ -f "$PHOTO" ]] || { echo "ERROR: edit PHOTO in this shell script"; exit 1; }
[[ -f "$CONFIG" && -f "$RECTS" ]] || { echo "ERROR: missing JSON config/rects"; exit 1; }
[[ -f "$REPO/bvt_studio/water_effects_v02.py" ]] || { echo "ERROR: apply v02 patch first"; exit 1; }
mkdir -p "$OUT"

# Keep frozen ordering so 00_clean exists before all delta/visibility QA runs.
for mode in \
  00_clean \
  01_light_condensation \
  02_heavy_condensation \
  03_frost \
  04_dirty_glass \
  05_reflections \
  06_microbeads_only \
  07_macro_droplets_only \
  08_running_water_only \
  09_combined_water_no_optics \
  10_combined_water_optics \
  11_heavy_running_water \
  12_stress_optics
do
  echo "===== GALLERY v02: $mode ====="
  "$BLENDER" --background --factory-startup --python-exit-code 1 \
    --python scripts/bvt_glass_effect_gallery_v02.py -- \
    --repo "$REPO" --photo "$PHOTO" --output "$OUT" \
    --rects-file "$RECTS" --config "$CONFIG" --mode "$mode"
done

echo "====== REOPEN CHECK ======"
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_gallery_v02_persistence.py -- \
  --blend "$OUT/10_combined_water_optics/scene.blend"

echo "GALLERY_V02_EXIT=0"
echo "GALLERY_INDEX=$OUT/index.html"
