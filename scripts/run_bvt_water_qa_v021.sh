#!/usr/bin/env bash
# Run isolated v0.2.1 calibration (v0.2 results remain untouched).
set -euo pipefail
cd /d/BVT-Studio
BLENDER="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"
PHOTO="C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png"
REPO="D:/BVT-Studio"
OUT="$REPO/qa_renders/effects_gallery_v021"
RECT="$REPO/configs/bvt_freezer_glass_rects_1672x941.json"
[[ -f "$RECT" ]] || RECT="$REPO/configs/bvt_freezer_glass_rects_v02_default.json"
CONFIG="$REPO/configs/effects_gallery_v02.json"
[[ -f "$BLENDER" && -f "$PHOTO" && -f "$RECT" && -f "$CONFIG" ]] || {
  echo "Missing Blender/photo/rects/config; inspect paths in this script" >&2
  exit 1
}
mkdir -p "$OUT"
for MODE in 00_clean 06_microbeads_only 07_macro_droplets_only 08_running_water_only \
            09_combined_water_no_optics 10_combined_water_optics \
            11_heavy_running_water 12_stress_optics
do
  echo "========== v0.2.1 $MODE =========="
  "$BLENDER" --background --factory-startup --python-exit-code 1 \
    --python scripts/bvt_glass_effect_gallery_v02.py -- \
    --repo "$REPO" --photo "$PHOTO" --output "$OUT" \
    --rects-file "$RECT" --config "$CONFIG" --mode "$MODE"
done
echo "========== PERSISTENCE =========="
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_gallery_v02_persistence.py -- \
  --blend "$OUT/10_combined_water_optics/scene.blend"
echo "========== MANIFEST QA =========="
python scripts/check_gallery_v021_outputs.py --output "$OUT"
echo "WATER_QA_V021_EXIT=0"
echo "GALLERY_INDEX=$OUT/index.html"
