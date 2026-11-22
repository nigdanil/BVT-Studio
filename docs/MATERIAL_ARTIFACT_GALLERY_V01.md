# Material × Artifact Gallery v0.1 (Step 4)

Experimental visual QA on the **unlabeled** bundled freezer example. It applies
one material and one existing preset to `Glass_p_001`; all other panes stay
QA-transparent. No add-on code is changed. Each cell reloads the clean scene,
sets the material, applies the artifact, renders, saves packed `.blend`, reopens
and rerenders. Both material/seed and artifact/seed are recorded.

## Run in Git Bash

Use the four-pane `00_clean/scene.blend` from Dataset Runner Step 1 (no material
assignments, full-size camera rendering). If absent, first regenerate that pilot.

```bash
python scripts/bvt_material_artifact_gallery.py \
  --blend qa_renders/runner_pilot_01/gallery/00_clean/scene.blend \
  --output-dir qa_renders/material_artifact_plan_v01 --dry-run

python scripts/bvt_material_artifact_gallery.py \
  --blend qa_renders/runner_pilot_01/gallery/00_clean/scene.blend \
  --output-dir qa_renders/material_artifact_pilot_v01 \
  --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
```

Default: 3 materials (clear, frosted, tinted) × 3 presets (transparent, macro,
combined optics). 9 jobs. Use `--materials` and `--effects` to select subsets;
clear and QA-transparent are automatically included as controls. Use `--seed`
(default 72); both material and artifact receive this matched seed. `--all`
selects all 84 combinations (6 × 14) including 18 QA-only cells. Do not confuse
these with 84 independent photographs or training-ready examples.

The output directory must be new. No output is written over existing experiments.
Use `--all` only after the pilot is accepted and enough disk space is available.

## Files and acceptance

- `plan.json`: deterministic job order; input SHA-256; resolved JSON profiles.
- `legacy.png`: original clean scene render.
- `resolved_presets/`: seed-resolved artifact configs validated by Blender.
- `gallery/<job>/`: `scene.blend`, `render.png`, `reopened.png`, `material.json`,
  `artifact.json`, `manifest.json` (paired metrics, packed resource hashes).
- `summary.csv`, `report.json`, `index.html`, `blender.log`.

The runner exits 0 on PASS, 2 on REVIEW (a requested visible effect has no
pixels beyond threshold), and 1 on errors. A failed run may leave partial output,
which must not be interpreted as a completed gallery. Use a new output directory
when retrying. Exact decoded RGB equality is required on reopen and on the
clear transparent baseline against the original clean render. The worker verifies
source hash, geometry, profile/seed persistence and packed image hashes. It rejects
changes >4/255 outside the selected pane's rectangle plus 4 px camera guard.

Comparisons: (i) material-only vs legacy, (ii) combined vs same-material
transparent control, (iii) combined vs clear glass with the same artifact,
(iv) combined vs legacy. These are image contrasts, not independent effect
contributions; they cannot be added. Water comparisons do not use the matched
neutral atlas topology: **not a calibrated zero-water QA**. Full isolated process
portability is a subsequent gate; this worker checks reopening and packed resources
within the running Blender process. No claims of physical realism, YOLO accuracy,
real-data validation, or production suitability. Release only after Blender QA.
