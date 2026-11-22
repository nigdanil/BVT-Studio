#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/gallery_paths.sh"
OUT="${BVT_OUTPUT_DIR:-$REPO/qa_renders/effects_gallery_v02}"

[[ -f "$BLENDER" ]] || { echo "ERROR: set BVT_BLENDER"; exit 1; }
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
