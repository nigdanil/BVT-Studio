#!/usr/bin/env bash
# Run isolated v0.2.1 calibration (v0.2 results remain untouched).
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/gallery_paths.sh"
OUT="${BVT_OUTPUT_DIR:-$REPO/qa_renders/effects_gallery_v021}"

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
