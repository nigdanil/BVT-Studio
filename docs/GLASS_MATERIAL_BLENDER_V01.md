# Glass Material Library — Blender integration v0.1 (Step 3)

Experimental opt-in 2.5D image-space material layer, separate from artifact
presets. Reuses the Step 2 NumPy reference model. It is not a physical BSDF,
ray-traced glass, measured transmission, or validated detection augmentation.

## Install / verify

Requires Dataset Runner Step 1 and Glass Material Library Step 2. Unpack this
patch at repository root, then run `python scripts/install_glass_material_blender_v01.py --dry-run`
and `python scripts/install_glass_material_blender_v01.py`. The installer checks
anchors, saves backups under ignored `qa_renders/patch_backups`, and is idempotent.
Run `python -m unittest discover -s tests -v` (expected 221 tests) and
`python scripts/build_addon.py`. Reinstall the newly built addon ZIP, not the
published Demo 3 ZIP; restart Blender to clear old module imports.

## GUI

1. Open the Step 1 `00_clean/scene.blend` or a new standard BVT photo scene.
2. In N > BVT Studio > 3B. Glass Material Library v0.1 choose the target.
3. Choose a built-in material (six profiles) and material seed, then Apply Glass
   Material. Alternatively select an individual `configs/glass_materials/*.json`
   with schema `bvt.glass-material.v01`, and Apply Material JSON to Target.
4. Use the existing 3A/4 panels to apply water/frost/dirt etc. separately.
5. Choose Clear Glass to remove the material effect from that target; other
   material assignments and artifact properties are retained.
6. **Rebuild Material Layer after moving, adding, removing or editing masks on
   panes.** This version has no live geometry-change handler. Switch source only
   after clearing all assigned materials. Save a copy, not a release scene.

## Representation and limits

- The BVT source node uses a derived packed RGB PNG. The hidden original node
  preserves the original image; `image_from_mesh` returns it for provenance.
  The artifact shader source accessor uses the active material texture when
  present. Existing glass source texture nodes are updated without rebuilding
  shader graphs. Legacy/no-material scenes use the previous source path.
- Per-pane JSON and independent material seed are stored on the glass object;
  the source stores original/baked SHA-256 and the applied pane records.
- Only standard BVT source materials, opaque sRGB 8-bit non-interlaced PNG
  (<=8,388,608 pixels), rectangular coplanar/parallel affine UV panes and
  nonoverlapping projected rectangles are supported. Reject invalid geometry,
  shared/linked materials, unsupported PNGs and non-grayscale masks. RGB mask
  coverage is independent of artifact inset/aperture and is bilinearly sampled.
- The original image is packed when a nonneutral layer is applied. Original
  pixel data is never overwritten. Clear restores the original texture reference.
- Source pixels are baked in original pixel coordinates, not render coordinates.
  Camera framing retains its existing behavior. No mesh, annotation or camera
  transforms are changed. This does not yet establish label alignment or physical
  optics. Artifact refraction can sample nearby background pixels as before.
- Dataset Runner/Release Builder integration and automated freshness checks
  are deferred; do not submit materials to the old gallery release verifier.
- No Pillow required by the add-on. JSON built-ins are mirrored in a Python
  module because the current addon ZIP builder packages Python files only.

## Blender acceptance

From Git Bash on Windows (choose an unused output directory):

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_glass_materials_smoke.py -- \
  --blend qa_renders/runner_pilot_01/gallery/00_clean/scene.blend \
  --output-dir qa_renders/glass_material_blender_smoke_v01
```

Expected `GLASS_MATERIAL_BLENDER_SMOKE=PASS`. The test verifies six renders,
clear RGB identity, localization (4-pixel camera boundary guard), per-pane
independence, composition with macro droplets, original source digest, unchanged
geometry/artifact parameters, packed derived texture and exact rerender after
reopen. Run the existing gallery / Runner regression separately to verify the
legacy path. No Blender runtime was available in the patch authoring environment;
all integration results must be confirmed on the target Blender build.
