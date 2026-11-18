# alpha.5-step5 — Quality Gate v2 (targeted optical QA)

**Base commit:** `e44e213` (`feature/photorealistic-droplets-v05`).

## Goal

Correct Step 4's "strongest impact wins" failure. Test **three different
synthetic condensation severities**, each with **Gentle / Balanced / Strong
optics** on the same source photo and fixed independent Seed per glass:

| Profile | Glass preset | Atlas density | Streaks | Target optical changed-pixel ratio |
|---|---|---:|---:|---:|
| LIGHT | LIGHT_CONDENSATION | 0.45 | 0.10 | 0.0075 |
| MEDIUM | HEAVY_CONDENSATION | 0.82 | 0.30 | 0.0105 |
| HEAVY | HEAVY_CONDENSATION | 1.25 | 0.60 | 0.0145 |

**MEDIUM is a calibration profile, not a newly introduced Blender artifact
preset.** The targets and limits are *provisional engineering defaults*, not
validated photography standards. `profile_changed_ratio` measures the effect
of the *optional optics pass relative to the identical atlas with optics off*.
The report **separately** records atlas effect versus the transparent control.

A selected variant must pass all configured gates. The numerical score
**penalizes distance from target** rather than rewarding maximum image change:

- `optical_changed_ratio` must stay within the profile's bounded interval.
- `bright_rim_ratio_v2` detects comparatively small bright contact arcs
  (positive luma delta > 0.018 on backgrounds > 0.50); this is a **brightness
  proxy**, not an actual circular-halo detector.
- `local_detail_loss_ratio_v2` measures suppressed high-contrast SKU edges
  allowing a one-pixel shift; **not OCR**, not guaranteed SKU legibility.
- `sku_mean_rgb_delta` measures per-region colour change.
- `leakage_ratio` is tested against *shader-derived* PNG Precision Masks,
  including four additional isolated off/on render pairs per profile.
- Existing YOLO Detect TXT `class cx cy w h` supplies a **read-only** ROI.
  Its SHA256 is checked after QA. Without TXT, central-glass areas are only a
  heuristic, not true item boxes.

Only a candidate that passes the objective gates may be selected, with
stable tie-breaking. When none qualifies, `selected: null` with explicit
`reasons`; `--strict` exits nonzero after writing JSON.

## Run in Git Bash (Blender 5.2.3 LTS)

```bash
cd /d/BVT-Studio

"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_quality_gate_v2.py -- \
  --photo "C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png" \
  --output "D:/BVT-Studio/qa_renders/quality_gate_step5" \
  --save-blend
```

Use `--yolo-labels "D:/dataset/labels/freezer.txt"` if a matching source image
has existing boxes. Use `--profile LIGHT`, `--profile MEDIUM` or `--profile
HEAVY` to run one profile; default is `ALL` (all three). Use `--strict` only
when you want any rejected profile / isolated pane to exit with an error.

Outputs: `quality_gate_v2_report.json`, selected-profile 2x2 montage
`40_quality_gate_v2_montage.png`, `light_00_optics_off.png`,
`light_01_gentle.png` etc. `medium_*` and `heavy_*` are analogous. Four
isolated off/on render pairs per profile are `light_20_glass_001_off.png`,
`light_21_glass_001_on.png`, etc. The existing mask QA fixture also writes
actual grayscale `mask_glass_001.png` through `mask_glass_004.png` and
`06_mask_debug.png`. `--save-blend` writes `quality_gate_v2_smoke.blend`
containing the **last profile** only, with its packed masks/atlas and optical
selection in scene custom properties; it does not package three full scenes.

To confirm persistence:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_quality_gate_v2_persistence_smoke.py -- \
  --blend "D:/BVT-Studio/qa_renders/quality_gate_step5/quality_gate_v2_smoke.blend"
```

Expected: `BVT QUALITY GATE V2 PERSISTENCE: OK`.

In **N → BVT Studio → 4. Glass Artifact Engine → Visual Quality / Quality
Gate v2**, choose `quality_gate_v2_report.json` and press **Read Visual QA
Report**. This loads and summarises results only; the CPU/GPU-intensive
calibration runs through Blender CLI.

## Important limitations and acceptance

The mask generator creates **synthetic geometric apertures**, not true
segmentation of the metal refrigerator frames. Numerical ROI tests alone do
not establish detector mAP, OCR readability, photographic realism or a
valid production training set. Review `40_quality_gate_v2_montage.png`
and every profile's render before declaring visual acceptance. The code does
not modify annotation, YOLO Quality Gate, YOLO export or dataset files.

Tests: `python -m unittest discover -s tests -v`; tests requiring NumPy are
skipped outside Blender. For complete tests, invoke unittest inside Blender's
bundled Python. Do not commit QA PNG, JSON, or .blend; `qa_renders/` is ignored.
The user's existing untracked `docs/OPTICAL_WATER_STEP3.md` is not touched.
