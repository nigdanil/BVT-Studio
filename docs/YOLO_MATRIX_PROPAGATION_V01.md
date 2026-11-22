# YOLO Matrix Propagation v0.1 — Step 5

## Scope and ground-truth semantics

Read-only extension of the accepted Step 4 matrix (`feature/dataset-runner-v01`, baseline commit `0e40b0d`). No addon changes, no new Blender build, no model training. Requires the original annotated BVT export ZIP and the **local complete matrix directory**, including its 84 `scene.blend` files. The smaller matrix QA ZIP is sufficient only for `--audit-only`.

The single reference is the unaltered **exported** `images/train/sample_000001.png`, not an optional top-level `render.png`. The supplied reference contains 28 boxes and class `0: ice_cream`. The PNG must equal `clear_glass__00_clean/render.png` pixel for pixel; do not assume source PNG and rendered camera raster are interchangeable. The input ZIP must contain exactly one root `sample_NNNNNN_manifest.json`, its standard BVT image/TXT, `scene.blend` and `data.yaml`. One source photo and one class in this experiment; the verifier checks contiguous class IDs rather than renaming them.

Labels are inherited **object-position candidates**, not re-measured visible post-refraction boxes. No automatic box deletion, coordinate warping or class changes. Organic background/partially visible products require human policy and review; this is not a semantic completeness guarantee. Stress and control scenarios (`00`, `12`, `13`) remain QA-only. All derivative images share one `source_group` and must never be split across train/val/test. No train/val directories or runnable dataset YAML are created; `reference/data.yaml` is provenance only. No model accuracy is established.

## Install and validate

Extract patch at repository root. Host Python needs NumPy and Pillow (already used in BVT QA). Blender worker does not import Pillow. Run `python scripts/validate_examples.py`, `python -m unittest discover -s tests -v`, `git diff --check`. Expected 262 tests if the baseline has 244 tests and these 18 tests are present.

Put the original `yolo_export_v1.zip` in `qa_renders/`. Keep the full matrix at `qa_renders/material_artifact_full_v03/`. From Git Bash:

```bash
python scripts/bvt_yolo_matrix_propagation.py \
  --reference-zip qa_renders/yolo_export_v1.zip \
  --matrix-dir qa_renders/material_artifact_full_v03 \
  --output-dir qa_renders/yolo_matrix_pilot_v01 \
  --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --pilot
```

Pilot geometry checks 9 scenes; all 84 original PNG pairs are independently audited. On success, rerun without `--pilot` using the new folder `qa_renders/yolo_matrix_full_v01`. Do not overwrite previous runs. `--audit-only` is explicitly offline and writes only audit/preview files, **no candidate images or inherited label files**. Full mode requires the Blender geometry report before copying candidates. It reads existing scenes, never saves/rebuilds the addon, and does not execute embedded blend scripts (`--disable-autoexec`).

## QA gates

1. Validate TXT and manifest row-by-row, finite coordinates, bounds, class map, unique UIDs and no near-duplicate boxes; exact label byte preservation.
2. Validate complete plan, report, all job manifests, material/preset snapshots and recorded resource persistence. Verify SHA-256 of each local scene before invoking Blender and after its check. Verify all 84 image SHA-256s, RGB dimensions, exact reopened RGB equality, exact clean reference equality, recorded total pixel deltas and no changes >4/255 beyond the original target plus 4 px guard.
3. In Blender open the annotated scene and recompute `collect_boxes`. Check source packed image SHA-256, orthographic camera name/frame/world, clipping, raster aspect, source and glass world geometry, UVs, topology, mask SHA and glass IDs. Reproject all annotated raw mesh vertices using their evaluated world transforms into each matrix camera. Maximum allowed projected coordinate discrepancy: 0.05 px. No changes are written into .blend files; annotations are exported as TXT next to existing copied PNGs, not inserted into each .blend.
4. For every bbox record changed-pixel percentage (>4), maximum RGB delta, mean absolute RGB delta and luma gradient detail ratio. Flags: affected optical ROI + any RGB change; detail ratio below 0.55; changed area >=50%; unexpected outside-target change >4. These are deliberately conservative, uncalibrated review proxies, **not visibility confidence or measured optical displacement**. `QA_ONLY`, `REVIEW`, `CANDIDATE_UNCHANGED` are not training approval. No sample is automatically promoted to a training dataset.
5. The 84-job matrix has 18 QA-only controls/stress cases and 66 experimental cases. The current example affects only `Glass_p_001`; seven of the 28 bboxes intersect its padded source ROI. 84 × 28 = 2352 candidate annotation instances, not independent ground truths.

## Output

`report.json` (`PASS_CANDIDATES` only after live geometry and all pixel checks), `geometry.json`, `blender.log`, `summary.csv`, `box_review.csv`, `classes.json`, original evidence under `reference/`, `manifests/<job>.json`, `images/pilot/<job>.png`, `labels/pilot/<job>.txt`, `previews/<job>.png`, `index.html`. Orange boxes have review flags, green boxes have none; they are not approved. Incomplete output is marked `ERROR`/`INVALID_INCOMPLETE_OUTPUT`; do not use for training. A fresh directory is required on retry.

## QA archive

```bash
python scripts/bvt_yolo_matrix_pack.py \
  --input-dir qa_renders/yolo_matrix_full_v01 \
  --archive qa_renders/BVT_YOLO_Matrix_Full_QA_v01.zip
```

The packer verifies existing candidate SHA-256, includes the reference RGB image and all TXT files, manifests, geometry report, logs, CSV and resized JPEG box previews, plus a SHA-256 inventory. It excludes redundant high-resolution image copies and bulky blend files. Upload the QA ZIP and console log; if the propagation fails upload `report.json`, `geometry.json` (if generated), and `blender.log` instead. Machine-local filepaths may be present in the Blender log; review it before sharing publicly. Archive is for private QA, not release publication.

## Next research step

After geometry acceptance and visual box review, design a fixed pretrained-model sensitivity test on the same scene. An ice cream-specific trained model or a model with an appropriate class mapping is needed for class-specific metrics; generic COCO weights do not contain `ice_cream`. One-source paired sensitivity is exploratory, not independent mAP. Use independently labeled real source groups for a held-out evaluation and split by source before augmentation. Do not label fully occluded items or mechanically reuse strongly displaced boxes for training without a defined visibility policy and review.

## Reference depth alignment hotfix v0.2

The first live run reported `Glass_p_001 world geometry: 0.012681067 > 1e-06`, although the annotated reference itself reproduced all boxes within 0.000115 px. An annotation-layer workflow may modify glass depth. The direction of the reported mismatch was not established by the original scalar error.

The SHA-verified `clear_glass__00_clean` scene is now the canonical world-geometry baseline for all matrix scenes. The annotated reference must match that baseline in camera, source, topology, UV, UID, mask and projection. Only rigid translation of transparent reference glass along the orthographic camera optical axis is permitted, with residual and lateral tolerance of 1e-6 world units, original 0.05 px projection tolerance, and a front-of-photo/clipping check. All matrix scenes still pass strict full world geometry comparison against the clean control. Reference box reprojection, immutable input hashes, all PNG checks and candidate-only policy are unchanged. `geometry.json` records the per-pane signed axial shift, lateral/rigid residuals and projection delta. A lateral move, deformation, changed camera, UV, mask or depth order still fails. No scene is modified and no tolerance is raised.
