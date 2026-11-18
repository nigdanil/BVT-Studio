# alpha.5-step6 pilot — Real Dataset Quality Calibration

**Status:** research/QA pilot; **not** an automatic YOLO training or export system.

This incremental Git patch applies on top of commit `60d8eb7` in branch
`feature/photorealistic-droplets-v05`. Check with `git apply --check` before use.

## Why

Step 5 used a synthetic four-glass QA fixture and optional **one** YOLO Detect
annotation file. Step 6 introduces a **read-only batch evaluation** of paired
existing original and artifact-augmented images with their actual YOLO Detect
`class cx cy w h` TXT labels. Report a QA decision **per SKU, per class and per
image**. Do not rewrite YOLO coordinates or claim improvement in detector mAP.

Input pairs MUST be aligned to the same pixel grid, unchanged crop, same
image dimensions, and unchanged boxes. Otherwise the metrics are not valid.

## Expected directory layout

```text
my_dataset/
  clean/images/shopA/001.jpg
  augmented/images/shopA/001.png
  labels/shopA/001.txt
  glass_masks/shopA/001.png    # optional, but required for PASS
```

Matching uses the **relative stem** `shopA/001` rather than file extension.
Glass masks are grayscale PNG of **verified glass extent** (white=allowed,
black=forbidden, gray=partially allowed). Synthetic 4-pane fixture masks from
Step 5 must **not** be considered verified on different retail photographs.

## Commands in Git Bash (Blender 5.2+)

First run integration smoke with **generated test images, not real data**:

```bash
cd /d/BVT-Studio
set +e
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_real_dataset_quality_smoke.py -- \
  --output-dir "D:/BVT-Studio/qa_renders/real_dataset_step6_smoke"
echo "BLENDER_EXIT=$?"
```

Then analyze **your** existing YOLO dataset, after arranging the source pairs:

```bash
cd /d/BVT-Studio
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_real_dataset_quality.py -- \
  --clean-dir "D:/Dataset/clean/images" \
  --augmented-dir "D:/Dataset/augmented/images" \
  --labels-dir "D:/Dataset/labels" \
  --masks-dir "D:/Dataset/glass_masks" \
  --output-dir "D:/BVT-Studio/qa_renders/real_dataset_step6" \
  --profile MEDIUM --max-overlays 12 --strict
```

The `D:/Dataset` paths above are **examples**. Use the real directory paths
for your datasets. Do not execute them unchanged if the folders do not exist.

`--masks-dir` can be omitted for an exploratory run: all otherwise-valid
samples become `REVIEW`, **never `PASS`**; they will not enter the accepted
manifest. `--strict` returns exit code 2 if any image is REVIEW, REJECT, or
ERROR. Without strict, the report is saved and a nonzero exit is reserved for
unrecoverable setup errors. `--max-overlays 0` skips annotated previews.

## Outputs (all under --output-dir)

- `real_dataset_quality_report.json`: per-image, per-object and per-class
  decisions and metrics, input SHA256 and source relative paths.
- `accepted_manifest.json`: **references** only to accepted original, augmented,
  label and glass mask files; no assets are copied or relabeled.
- `samples.csv` / `objects.csv` / `classes.csv`: image, per-SKU, and aggregated class QA.
- `overlays/...png`: bounded number of **new** diagnostic images with bbox
  outlines (green=PASS, yellow=REVIEW, red=REJECT).

## Rules and limits

- YOLO **Detect** TXT only: five tokens per nonblank row, nonnegative integral
  class ID and normalized valid center/width/height. Other YOLO dialects fail.
- `LIGHT/MEDIUM/HEAVY` select preliminary **original-vs-augmentation** changed
  pixel bands, distinct from Step 5 optics-only target bands.
- Out-of-bounds or unpaired images fail closed. Labels and all inputs are
  SHA256 checked before/after the read-only QA.
- Glass mask absence is **REVIEW**; any far-outside-mask pixel change
  is **REJECT** after a 2-pixel AA guard.
- Per-SKU checks include changed ratio, brightening ratio, mean RGB drift and
  significant-edge suppression. Boxes outside glass are exempt from required
  water effects, but their pixels remain protected by the global leakage check.
- If there are too few baseline edges in a SKU to test detail retention,
  mark REVIEW rather than claim success.

**Limitations:** input images may have different color management, camera
position, crop, compression or lighting. This makes per-pixel comparisons
unreliable. A `PASS` does not establish photorealism, shelf compliance,
readable brand text or improved detector accuracy. Use a controlled YOLO
experiment with held-out real-world images and compare mAP/recall before
claiming ML gains. Do not use synthetic fixture masks as verified real masks.

The Step 6 patch intentionally contains **new files only**, with no addon
version bump and no modifications to existing Step 5 code. After Blender
integration and real-data checks are accepted, version/UI integration can be
performed as a separate, verified release step.
