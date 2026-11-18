# alpha.5-step4 — Visual Quality & Calibration

Base SHA: `e9e56fb` (`feature/photorealistic-droplets-v05`).

## Scope

This is a **headless QA/calibration workflow**, not a new water shader. It
compares three different optical gain combinations (`gentle`, `balanced`,
`strong`) on exactly the same per-glass Realistic Atlas textures and seeds.
Neither the source image, YOLO annotation files nor their exporter are edited.
Four independent glass sections use the actual shader-derived grayscale
Precision Masks from the step4 mask fixture.

Run in **Git Bash**, from `D:/BVT-Studio`, after applying the Git diff patch:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_visual_quality_calibration.py -- \
  --photo "C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png" \
  --output "D:/BVT-Studio/qa_renders/visual_quality_step4" --save-blend
```

Optional: `--yolo-labels "D:/dataset/labels/sample.txt"` uses existing YOLO
Detect class/cx/cy/w/h boxes as a read-only SKU detail ROI. Without it, the
ROI is an approximate central part of each glass. Optional QA limits:
`--halo-limit 0.06`, `--detail-loss-limit 0.45`, `--leakage-limit 0.0005`.
`--strict` makes QA fail when no candidate passes. Without `--strict`, results
and rejection reasons are still written for visual inspection.

Outputs include:

- `00_source.png`, `01_control_transparent.png`, `06_mask_debug.png` and four
  grayscale mask PNGs from the existing precision mask fixture.
- `10_atlas_optics_off.png` as a fixed baseline, `11_gentle.png`,
  `12_balanced.png`, `13_strong.png` with identical atlas seeds.
- `20_isolated_off_001.png` through `...004.png` and `21_isolated_on_...png`.
- `30_visual_calibration_montage.png`, optional `31_selected_difference_5x.png`.
- `visual_quality_report.json` with metrics, thresholds, selection, reasons,
  four single-pane checks and source provenance.
- `visual_quality_smoke.blend` only with `--save-blend`.

The panel **N → BVT Studio → 4. Glass Artifact Engine → Visual Quality
Calibration** can load the JSON and display the selected configuration. The
panel does not independently run the headless calibration.

## Metrics and limitations

- `leakage_ratio`: changed pixels outside the **actual shader mask**, with
  a two-pixel AA boundary guard, using a >3/255 per-channel change threshold.
- `bright_halo_proxy_ratio`: fraction of allowed pixels that become much
  brighter than the same atlas **without** optional optics. This measures
  suspect brightness, **not** the geometric shape of circular halos.
- `sku_detail_loss_proxy_ratio`: count of high-contrast reference edge pixels
  suppressed in the candidate, with a 1-pixel tolerance for refraction.
  **This is not OCR, SKU classification accuracy or legibility guarantee.**
- `sku_mean_rgb_delta`: average change in SKU ROIs; `effect_changed_ratio`:
  how much of the allowed glass area was visibly changed.

The synthetic aperture masks exclude diagnostic shapes, **not all metal** in
an actual freezer. To verify production segmentation, replace these masks
with manually traced or segmented glass apertures. Always inspect original
and montage PNGs. A pass is a limited *numerical QA gate*, not certified
photorealism or downstream model performance.

## Validation

1. `python -m unittest discover -s tests -v` (NumPy-dependent tests may be
   skipped by system Python; run them using Blender Python if needed).
2. Run the headless Blender command above and inspect JSON and PNGs.
3. Verify Blender persistence:

   ```bash
   "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
     --background --factory-startup --python-exit-code 1 \
     --python scripts/blender_visual_quality_persistence_smoke.py -- \
     --blend "D:/BVT-Studio/qa_renders/visual_quality_step4/visual_quality_smoke.blend"
   ```
4. Do not commit generated PNG/BLEND datasets (`qa_renders` is ignored).
5. Keep the existing untracked `docs/OPTICAL_WATER_STEP3.md` untouched; it is
   not included or deleted by this patch.
