# Glass Material Library v0.1 — Step 2 / reference model

This additive stage defines a versioned material catalog independently of existing
surface artifacts. The numerical preview is image-space, not a Blender shader,
not a calibrated BRDF/BTDF, and not physical or thermal simulation. Nothing in
`configure_glass`, YOLO export, the original gallery or Dataset Runner is changed.
No `--glass-types` argument is implemented yet. Existing release assets remain unchanged.

## Catalog

`configs/glass_materials/*.json` contains six profiles (`bvt.glass-material.v01`).
`physical_metadata` (nominal thickness, IOR, layers, construction) is illustrative
metadata, not measured and not used by the numerical renderer. `appearance` is
an independent, explicitly uncalibrated numerical model, with strict bounds:

- transmission_rgb: linear-light per-channel attenuation, [0,1]
- scatter_mix, scatter_radius_fraction: blend with a three-pass box blur,
  radius relative to shorter pane dimension
- haze_mix, haze_rgb: blend with uniform linear-light veiling colour
- distortion_fraction, texture_cycles: seeded bilinear rib displacement
- reflection_mix, reflection_rgb: synthetic bright band, no view/environment reflection
- ghost_mix, ghost_offset_fraction: approximate secondary shifted image, no optical ray tracing
- edge_feather_fraction: attenuation of effect at pane rectangle edge

Clear is an exact identity control (on the clean rendered image, not necessarily
on the external source photo). Frosted material is permanent scattering; frost
artifact is temporary ice. Insulated glazing is construction metadata plus a
chosen illustrative ghost; actual insulated glazing need not show that effect.
Appearance profiles can be tuned in research after separate reference acquisition.

## Run

On the existing `feature/dataset-runner-v01` branch, from the repository root:

```bash
python -m unittest discover -s tests -p 'test_glass_materials_v01.py' -v
python -m pip install Pillow # only for the optional standalone preview CLI
python scripts/bvt_glass_material_preview.py \
  --input qa_renders/runner_pilot_01/gallery/00_clean/render.png \
  --rects-file examples/freezer_planogram/configs/geometry/bvt_freezer_glass_rects_1672x941.json \
  --output-dir qa_renders/glass_material_preview_v01 --seed 72
```

Output may not exist yet, and must be inside `qa_renders/`. The script checks
source/output PNG, geometry, catalog validity, per-pane seeds, exact repeat,
exact zero outside-pane change, clear identity, and input hashes. It emits a
report and six PNGs; these are not `.blend` scenes or a YOLO dataset. It uses
rectangles only in this CLI. The numerical API supports optional local coverage
masks in [0,1] and different materials per pane, validated against overlaps.
A non-clear profile may have little effect on a uniform ROI; informativeness
is reported, not silently promoted to physical realism. No source pixels or
input files are overwritten.

## Next integration gate

1. Add a per-glass material ID and resolved settings to Blender object metadata.
2. Integrate material sampling into the existing source UV / glass shader pipeline,
   using the existing precision mask; do not apply material to the entire render.
3. Preserve exact old rendering when the property is absent or clear. Verify
   per-pane isolation, packed resources, persistence, GUI and all 13 old scenes.
4. Pair each material+artifact with a material-only control of identical geometry,
   sampling, and seed. The clear control remains useful but cannot isolate the
   effect of an artifact on nonclear glass.
5. Extend Dataset Runner plan schema and input hashes only after Blender QA.
   Check render/source alignment and YOLO label geometry before label reuse.
6. Calibrate appearances on real images before claims about physics or detector gains.
