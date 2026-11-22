# Dataset Runner v0.1 — step 1 (unlabeled pilot)

Runs the existing calibrated gallery renderer and existing packed-scene reopen checker in separate Blender processes. No shader or annotation changes. Only the bundled `freezer_planogram` is supported in this step; no YOLO labels are present. No training data or accuracy claim is produced.

## Usage (Git Bash, from repository root)

```bash
python scripts/bvt_dataset_runner.py --example freezer_planogram \
  --effects 07_macro_droplets_only 10_combined_water_optics \
  --count 2 --seed 72 --output-dir qa_renders/runner_plan_01 --dry-run

python scripts/bvt_dataset_runner.py --example freezer_planogram \
  --effects 07_macro_droplets_only 10_combined_water_optics \
  --count 2 --seed 72 --output-dir qa_renders/runner_pilot_01 \
  --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
```

One clean control + two effects × two replicates = five final renders. Water variants additionally render their neutral control and independent neutral rebuild. `--count` is per effect, not total. Each replicate uses a consecutive block of pane seeds; matching seed blocks across effects are intentional for paired comparisons. All four panes use the gallery preset. No calibrated severity axis yet; normal gallery variants 01–11 are eligible, while the stress variant is deliberately excluded. The independent single-pane GUI presets are not reinterpreted in this step.

The output must be a new directory under `qa_renders/` (ignored by Git). No resume/overwrite. Plan-only runs write `plan.json` and `resolved_gallery.json` without Blender. Full runs write those files, `logs/`, `gallery/` with `source.png`, scenes, renders, QA manifest, reopen reports and gallery HTML, and `run_report.json`. Input files and code hashes are recorded in the plan, and checked again at completion. The report is only PASS if every planned render and reopen passes. A partial/error run is not accepted. `PASS` is a technical generation result, not a realism or accuracy claim. This stage does not do the independent rerender portability test; the existing release portability tool is unchanged.

## Acceptance

- All 195 existing tests and six runner tests pass.
- Dry-run creates five jobs and no rendered images.
- A full run yields five PASS jobs, with matching source, geometry, seeds and dimensions, four water null tests and five reopen reports.
- A second run with the same arguments (different output directory) should have matching decoded RGB, and matching plan inputs/config; `.blend` binary hashes are not expected to be identical. This independent repeat-run check is still to be performed in Blender.

## Next

Add a separate external dataset manifest with original images, detection labels, class vocabulary and per-image glass regions/masks; validate dimensions/YOLO coordinates; propagate labels without geometry changes; review occlusions and leakage. Keep all descendants of a source in the same split. Only then run a 20–100 source pilot and a fixed-model detector degradation benchmark. Calibrate severity empirically rather than equating preset names or nominal intensity with real-world occlusion.
