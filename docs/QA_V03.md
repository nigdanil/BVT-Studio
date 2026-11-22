# BVT Studio v0.3 — release acceptance (alpha.6)

## Scope

Validate the same workflow a user runs in Blender 5.2.3 LTS:
Photo → camera → Glass → Annotation → group protection / normal-depth
constraint → Quality Gate → clean PNG + YOLO TXT + portable YAML + SVG + JSON.

This is **integration QA**, not a claim that synthetic data is realistic or
sufficient for training. Source photos and SKU-class completeness still need
manual review; empty `val` remains expected for a single-scene export.

## Automated acceptance

From the repository root in Git Bash:

```bash
python -m unittest discover -s tests -v

"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python scripts/blender_v03_e2e_smoke.py
```

Expected Blender output ends with:

```text
BVT V0.3 E2E SMOKE: OK — photo, locks, tilted depth, glass, annotation, quality gate, clean PNG, YOLO TXT, SVG, manifest
```

The smoke test generates a 256×160 artificial PNG in a temporary directory,
then imports a new BVT scene, adds two glass panels and two annotation planes,
assigns two classes, applies Annotation Mode and glass depth, validates,
renders and verifies the export and restored render/lock state.

The test deliberately uses a rotated photo plane. Its images and outputs are
deleted when the test finishes. It does not install an add-on or package ZIP.

## Manual GUI QA — perform before v0.3.0 stable

- [ ] Save a copy of the user's existing `.blend` scene.
- [ ] Install the add-on built by the project maintainer; verify **alpha.6** in the UI.
- [ ] Import a real retail photo, create two glass surfaces and verify the
      glass material sliders continue working with scene selection protected.
- [ ] Create and reposition ten annotations; verify `Lock Scene for Annotation`
      prevents selection of the photo/camera/glass and allows editing boxes.
- [ ] Tilt the source photograph, re-frame the camera and move annotations
      along photo tangents; verify their normal depth remains fixed.
- [ ] Use Annotation Manager to select, group-edit, disable and re-enable
      boxes. Verify class names, render outlines and collection organization.
- [ ] Run Quality Gate with one intentionally duplicated or out-of-frame
      annotation and confirm export is blocked. Restore the box and revalidate.
- [ ] Export a clean dataset and open its SVG preview. Verify every expected
      SKU has a valid box and no visible outlines are baked into PNG.
- [ ] Reopen the saved `.blend` and verify edit flags, custom depth constraints
      and object names/collections persist and remain editable via UI.
- [ ] Confirm unrelated objects in a second Blender scene were not modified.
- [ ] Copy dataset directory to another path and open SVG/YAML without
      references to the original Windows user directory.
- [ ] Do not train with the single-image, empty-val dataset. Validate with
      independent source photographs grouped before augmentation.

## Release gate

Do not merge/release stable until the Blender end-to-end smoke test passes
and the manual GUI checklist has been signed off. Each feature branch was
created on top of the previous one, so merge in ancestry order (or merge the
latest branch once), not by cherry-picking overlapping patches.
