# BVT Studio — 2.5D Dataset Builder v0.4.0-alpha.5-step2

**Experimental standalone Blender 5.2+ add-on**, built from the seven BVT prototype Python scripts.
No external dependencies beyond Blender's included Python API.

## Installation (Windows Blender 5.2.3)

1. Back up your `.blend` project.
2. Blender → **Edit → Preferences → Get Extensions** → drop-down at the top right → **Install from Disk**.
3. Choose the ZIP produced by **`python scripts/build_addon.py`**. This is a legacy add-on ZIP, with `bvt_studio/__init__.py` at the archive root.
4. If necessary, enable **BVT Studio — 2.5D Dataset Builder** in preferences (add-ons / installed extensions).
5. In the **3D Viewport**, press **N** and open the **BVT Studio** tab.

If the Blender version displays the extension-warning prompt, allow installation of this local legacy add-on.

## Recommended workflow

1. **Photo / Scene:** Click *New Scene from Photo* (makes a separate scene, preserves your original), or select an existing `BVT_Freezer_Image_Plane` and click *Use Selected Image Plane*. Select the camera frame profile and click *Frame Camera to Photo*.
2. **Glass:** Press *Add Glass* to create a plane in front of the photo, then position/scale it. You can also select an existing Plane and press *Setup Selected Glass Plane*. Tune `Reflections`, `Tint`, `Haze`, `Frost` with sliders. One glass object per independent surface is supported. Never run Glass Setup on the photo plane.
3. **Glass organization:** When you select any user-created Plane and click *Setup Selected Glass Plane*, BVT Studio assigns a glass shader, moves it into `BVT_Glass` and renumbers every glass plane as `Glass_p_001`, `Glass_p_002`, etc. **Register / Setup Glass All** also recognizes old `Glass`, `Glass.001`, `Glass_01`, `Glas_001` and existing tagged glass overlays, moves them into the same collection and configures their materials (image-textured/photo planes are skipped to avoid overwriting). **Renumber Glass 001...N** changes names and collection membership only. Geometry, position, and user-defined glass settings are preserved. Glass objects remain independent of `BVT_Annotations`.
4. **Annotations:** Click *Add Annotation* and move/resize the rectangular plane over each visible SKU, or use existing manually made `plane_p_001..N` and click *Register / Color All*. A colored **Wireframe modifier** makes the rectangle visible in viewport. Move the **original rectangle mesh**, not its modifier. Edit Class ID / name on the selected annotation. For default category detection, keep all IDs at `0`, class name `ice_cream`.
5. *Renumber 001...N*, *Validate YOLO Boxes*, and optionally *Render Outlines: ON* to preview colored bounding boxes in F12. For dataset export, outlines will **always** be hidden temporarily.
6. **Export:** Save the `.blend`, select an output folder, then *Export Clean Image + YOLO*. Each click adds `sample_000001`, `sample_000002`, ... in a dataset structure.

## Collapsible sidebar (v0.4.0-alpha.2-ui.1)

- The **N → BVT Studio** sidebar now uses eight native Blender child panels under the
  existing **BVT Studio | 2.5D** parent. Click the disclosure arrow to expand/collapse
  each panel; Blender remembers the state per UI region.
- **Glass Artifact Engine** starts expanded, while Scene Locks, Layer Depth, Photo / Scene,
  Glass / Surfaces, YOLO Annotation Manager, YOLO Quality Gate and YOLO Export start closed.
- Glass creation/manual per-object sliders are under **Glass / Surfaces**; preset/seed/
  intensity/coverage/shape controls are under **Glass Artifact Engine**. YOLO annotation,
  quality and export are separate siblings, no longer hidden behind the tall Glass section.
- No operator identifiers, properties, camera/scene logic, shaders, export formats or
  existing `.blend` data are changed by this patch.
- Verify the new UI by expanding each child panel in Blender 5.2.3. CLI smoke:
  `--background --factory-startup --python scripts/blender_ui_panels_smoke.py`.

## Multi-scale procedural glass (v0.4.0-alpha.2)

- Droplets combine **large sparse beads**, **medium condensation** and **fine specks** with a seeded UV warp.
- Frost combines broad seeded islands, fine crystalline texture, and optional edge buildup in **glass UV**, not global Z.
- `Droplet Scale` (0.5–2.0) adjusts the three droplet frequencies; higher means smaller droplets.
- `Frost Edge` (0–1) controls the extra edge buildup, without changing glass placement.
- Apply Glass Preset writes both shape controls to the selected glass object. Refresh Pattern
  rebuilds from the **object** settings, allowing manual per-object adjustments.
- Two glass objects retain separate shaders; the same object properties and seed recreate
  the same pattern in a fixed Blender version. Export manifest records both new parameters.
- These are **2.5D overlay masks**, not physically traced droplet/refraction geometry.
  Inspect renders at training resolution before generating large datasets.

Blender smoke (from repository root):

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python scripts/blender_glass_artifacts_smoke.py
```

## What is implemented

- Image import (and original/current-scene reuse) + alpha-aware unlit photo material.
- Exact image aspect, orthographic camera, presets for photo, 4:3, 3:4, 16:9, tablet 4:3.
- Glass on user-created mesh Plane: reflection, haze, tint and frost shader controlled by Blender object custom-property drivers.
- Automatic `Glass_p_001...N` naming, `BVT_Glass` collection, batch registration/setup and explicit glass renumbering; *Add Glass* creates a new overlay Plane.
- Create/register/renumber annotation rectangles, independently colored emission-based outline preview, editable class metadata.
- Validate rectangles in camera coordinates (outside frame, zero size, class ID gaps, near-duplicates), single-image YOLO `class cx cy w h` export.
- Clean PNG render, TXT label file, `data.yaml`, per-sample JSON manifest (with annotations, camera profile, glass parameters).
- Existing project scene preserved when importing a new photo.

## Annotation Manager (v0.3.0-alpha.3)

- `Annotation Planes` shows an RNA UIList of the scene's actual `plane_p_*` / tagged annotation objects. Click a row to select that rectangle in the viewport when annotations are editable.
- `Add Annotation`, `Register / Color All` and `Renumber` refresh the list. After deleting or renaming an object directly in Outliner, press **Refresh List**.
- Press **Select All Annotations** to select every currently editable BVT annotation in this scene, leaving unrelated objects untouched by batch class/enable actions.
- Fill **Class ID** and **Class Name**, then **Apply Class to Selected**. The action is atomic and rejects conflicting names for a class ID on unselected annotations.
- **Enabled for YOLO** + **Apply Enabled to Selected** controls `bvt_enabled` on selected rectangles. Disabled boxes are excluded by the existing YOLO exporter.
- Edits honor `Annotations Edit Enable` when scene protection is active; list items and classes persist in `.blend` with regular Blender scene data.

Run CPython unit tests with `python -m unittest discover -s tests -v`. Then run this actual Blender smoke test:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python scripts/blender_annotation_manager_smoke.py
```

This slice does **not** yet implement automated completeness checks or a visual YOLO quality-gate report; those are next in the v0.3 roadmap.


## YOLO Preview and portable export (v0.3.0-alpha.5)

- **Export Clean Image + YOLO** also creates `previews/sample_000001.svg` (and so on).
  Open with **Open Last YOLO Preview** or any browser; the SVG points to the clean PNG
  at `../images/train/sample_000001.png` and draws boxes from the *serialized TXT labels*.
  **Do not move the SVG away from its dataset folder without the image**: both paths are
  relative so the entire dataset directory can be moved or copied intact.
- `data.yaml` no longer includes a `path:` value specific to one Windows computer.
  Train/validation paths are relative to the directory containing `data.yaml`.
- The SVG is **for review only** and is never used as training input. Exported PNGs
  still contain **no colored annotation outlines**.
- The `images/val` and `labels/val` directories remain empty for one-off export.
  **Before training**, provide a real validation set from independent source photos.
  Do **not** randomly split augmented variants of the same original photo between
  train and val, because that leaks information between splits.

Run Python tests with `python -m unittest discover -s tests -v`. Run the actual
Blender headless export test from the repository root:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python scripts/blender_export_preview_smoke.py
```


## v0.3 integration QA (alpha.6)

Run the end-to-end test in real Blender 5.2.3:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python scripts/blender_v03_e2e_smoke.py
```

It exercises photo scene import, default protection, a tilted photo, two
glass overlays and two annotations, Annotation Manager classes, depth offsets,
Quality Gate, and a full PNG/TXT/YAML/SVG/manifest export. All output is
created under an automatically deleted temporary directory. No ZIP is built.

See [docs/QA_V03.md](docs/QA_V03.md) for the manual Blender GUI release gate.
The v0.3 release is **not** considered stable until those checks pass.

## Scene collections and naming

```text
Scene
├── BVT_Studio_Photo/
│   ├── BVT_Freezer_Image_Plane
│   └── BVT_Studio_Camera
├── BVT_Glass/
│   ├── Glass_p_001
│   ├── Glass_p_002
│   └── ...
└── BVT_Annotations/
    ├── plane_p_001
    ├── plane_p_002
    └── ...
```

**Naming is scene-aware but Blender object names are globally unique**. If a desired `Glass_p_*` name is already used by an unrelated object in another scene, renumbering reports a conflict rather than silently altering that object. Collection names in second and subsequent scenes may become `BVT_Glass.001` because Blender collection names are global; the add-on remembers their semantic role.

## Build the installation ZIP

Run Python from repository root (Blender is NOT needed just to package):

```bash
python scripts/build_addon.py
python -m unittest discover -s tests -v
```

The generated **legacy Blender add-on archive** is `dist/BVT_Studio_Blender_Addon_v0.3.0-alpha.6.zip`. It has the `bvt_studio/` Python package at ZIP root, which is the same structure that worked in Blender 5.2.3 for v0.1. This is not a Blender Extensions platform manifest package.

See [docs/PUBLISHING.md](docs/PUBLISHING.md) for GitHub initialization and release upload.

## Output structure

```text
bvt_studio_dataset/
  images/train/sample_000001.png
  images/val/                     # EMPTY — prepare independent validation data
  labels/train/sample_000001.txt
  previews/sample_000001.svg
  labels/val/                     # EMPTY — prepare independent validation data
  sample_000001_manifest.json
  data.yaml
```

`data.yaml` uses the actual absolute folder path so local training tools can find this dataset. Edit `path` after moving the dataset to a different machine.

## Deliberate limitations of v0.2

- **Blender has not been executed to integration-test this ZIP in this environment.** Python syntax has been compiled and ZIP checked. Run in a backup `.blend` first; report any errors from Blender Console.
- Uses **flat 2D photos**. Moving a Blender camera cannot reconstruct hidden geometry. Phone/tablet profiles currently change **frame and resolution only**; no physically calibrated phone lens/sensor simulation yet.
- Annotation rectangles produce axis-aligned **YOLO Detect** boxes, even when rotated. No polygons, segmentation masks or rotated YOLO OBB export yet.
- Bounding boxes are derived from original mesh vertices and transformed through the current Blender camera; the rendered outline thickness is not included.
- No automatic labeling of unseen/occluded products. Annotation completeness is a human review task, and imperfect AI-generated packaging art is not a verified real-world SKU dataset.
- The exported `images/val` and `labels/val` directories are deliberately empty. **Do not train/evaluate with train=val**: add independent labeled validation examples and check all YOLO labels before experiments.
- This standalone prototype deliberately **does not replace the existing BVT 3D add-on**. Integration as an optional submodule is a later step.
- Existing annotations named `plane_p_001` are discovered; arbitrary other mesh names must be converted manually or annotated anew. Users may create many annotation objects.

## Source scripts mapped

| Original prototype | BVT Studio module |
| --- | --- |
| BVT_Planogram_AutoSetup | `scene_tools.py` |
| BVT_Setup_Selected_Glass_Plane | `glass.py` |
| BVT_Glass_Overlay | replaced by **Add Glass**: the addon creates one simple Plane per overlay (not 3D refrigerator glass geometry) |
| BVT_YOLO_Annotation_Planes | `annotation.py` |
| BVT_Annotation_Colored_Outlines v01 | `annotation.py` |
| BVT_Annotation_Colored_Outlines v02_Renumber | `annotation.py` |
| BVT_assign_icecream_materials | **not included in v0.1**: image is now a single photographed planogram; standalone SKU material replacement is a separate workflow |

## Next milestones

- Mobile camera noise, white-balance, JPEG and motion blur with parameters recorded in the manifest.
- Glass artifacts with deterministic seeds, batch randomization.
- Automated photo/label augmentation with bbox synchronization.
- Per-object segmentation and occlusion-aware annotation.
- BVT core integration (`src/ui`, `src/artifacts`, `src/annotation`, `src/export` shared modules).

## License and reuse

Source code is distributed under **GPL-3.0-or-later**, consistent with the BVT project's draft source-code licensing policy. No generated SKU photographs, real-brand labels, or other third-party assets are bundled with this code-only add-on.

## Release status

This is a Python-compiled, ZIP-verified **prototype**. Runtime integration inside Blender 5.2.3 is not tested in this build environment. Please test against a copy of your `.blend` before publishing a formal tested release.

For one-command GitHub creation and beta publication (Git Bash, after `gh auth login` and a Blender smoke test), run `bash scripts/publish_github.sh`. This script is **not executed as part of ZIP installation**.


### Upgrading from 0.2.0 to 0.2.1

Blender loads the add-on code from its **installed extensions/addons folder**, not
from the GitHub repository. A `git pull` alone will **not** update Blender.

1. In Blender > Preferences > Get Extensions / Add-ons, remove or disable
   the old `BVT Studio` installation. Restart Blender.
2. Build the installable ZIP using `python scripts/build_addon.py` and
   install it from disk. Restart Blender again.
3. The sidebar must display **BVT Studio v0.2.1**. If not, an older add-on
   copy remains installed. Check the add-on path via Blender's Python console:
   `import bvt_studio; print(bvt_studio.__file__, bvt_studio.bl_info['version'])`.

- **Use Selected / Current Photo** accepts the selected textured mesh, but keeps
  the existing `Source` when an untextured `Plane` or glass Plane is active.
- **Setup Selected Planes (Batch)** accepts multiple selected glass Planes even
  with default names `Plane`, `Plane.001` etc., and organizes them in `BVT_Glass`.
  It refuses to overwrite image-textured and annotation meshes.
- If Blender shows `//bvt_studio_dataset` in red on an unsaved project, save the
  `.blend` or select an absolute export path before exporting.


### Add Glass — no manual Plane creation (v0.2.2)

1. Click **New Scene from Photo** (or set Source to a textured Image Plane).
2. In **Glass / Artifacts**, click **Add Glass**. A new mesh named
   `Glass_p_001` is created and registered in `BVT_Glass`.
3. The selected Plane has the procedural material and editable Reflection,
   Tint, Haze, and Frost parameters already attached.
4. Use **G** to move and **S** to scale the Plane over the actual glass part of
   the photograph. Click **Add Glass** again for a second area (`Glass_p_002`).

On the standard top-down freezer photo, the first two new panels start over
approximate left and right halves. These are **editable guides**; they do not
identify the real glass boundaries automatically. Additional planes can be
created and adjusted independently. The source photo, camera and annotations
are never changed by this command.

If the same `.blend` already has a `Glass_p_001` object in another scene,
Blender will choose the next globally available object name (Blender object
names are global, not per scene). Existing glass planes remain untouched.

Install the newly built `dist/BVT_Studio_Blender_Addon_v0.2.2.zip` into Blender,
then restart Blender. Confirm that the sidebar shows **BVT Studio v0.2.2**.


## Scene Lock Manager (0.3.0-alpha.1)

In N-panel **0. Scene Editing / Locks** click **Lock Scene for Annotation** to protect
BVT-managed Photo, Camera, Lights and Glass while leaving annotation Plane objects editable.
Toggle `... Edit Enable` to temporarily edit one group. Use **Unlock Scene** to
restore the original Blender object locks (confirmation required). Existing foreign
objects are never included in the policy; multi-scene shared objects are skipped. Photo and studio camera created via
**New Scene from Photo** are protected automatically. The locks are for manual
viewport input; Python/Blender operations are not sandboxed.

**Not yet implemented:** depth locks relative to the source photo normal, Glass
Depth Offset and Reset Layer Depth (roadmap 1.0.1). Do not confuse the current
full-transform group locks with geometric plane-depth constraints.


## 0.3.0-alpha.2 — Photo-relative Layer Depth (roadmap 1.0.1)

- `Photo / Glass / Annotations - Lock Depth` checkboxes are enabled by default.
- The add-on installs a **Limit Location** constraint (`BVT_Studio_Photo_Relative_Depth`)
  with `Owner Space = Custom` based on the original Photo Plane. It restricts
  motion along the **photo normal**, not the global world Z axis. Normal `G`
  moving along photo surface, rotations and scaling remain available if the
  corresponding `Edit Enable` is active.
- The Photo is referenced by a hidden-from-selection control Empty inside
  `BVT_Studio_Controls`; this prevents circular constraint dependencies.
- To edit glass depth even when the glass cannot be selected, choose it via
  `Glass Target`, enter `Depth Offset` in meters, then click **Apply Glass Depth Offset**.
  The offset is measured towards the **active camera**. This moves the origin
  along the photo normal and leaves its in-plane coordinates unchanged.
- **Reset Layer Depth** restores photo baseline and configured glass/annotation
  depths, and re-aligns the reference frame when the photo was rotated.
- Existing photo/glass/annotation geometry is kept on initial enabling. If a
  legacy overlay is coplanar, press Reset to place it at a visible depth.
- Disabling a depth checkbox mutes BVT's own constraint; enabling it again
  restores the earlier configured depth. Unrelated constraints are not edited.
- Constraint controls affect object-origin transforms in Object Mode. Mesh
  Edit Mode, external scripts and intentional constraint changes can bypass
  them. This is an ergonomics feature, not a security control.

### Blender acceptance test for rotated photo

1. Back up `.blend`. Install the new ZIP, and restart Blender.
2. Create a photo scene; add two Glass planes and three annotations.
3. Turn `Glass Edit Enable` ON and use the `Glass - Lock Depth` checkbox.
4. Try `G, Z` on a flat photo: the visual depth must stay fixed. `G, X/Y`
   should still work. For a tilted photo, use global `G` directions with a
   normal component and verify that the final position still lies on the
   photo-relative layer, even though its world Z may change when moving in XY.
5. Rotate the Photo Plane with Photo Edit enabled (e.g. X=30 degrees,
   Y=20 degrees), then click **Reset Layer Depth**; move glass/annotations
   in photo plane again and verify no visible drifting along the normal.
6. Turn `Annotations - Lock Depth` OFF and ON, inspect modifier-free original
   mesh corners; use **Export Clean Image + YOLO** as the smoke test.
7. Save/reopen the `.blend` and confirm constraint targets and offsets persist.


### v0.3.0-alpha.4 — YOLO Quality Gate

Use **4. YOLO Quality Gate → Validate YOLO Boxes** to populate a structured
report. **Errors** block export (missing camera, invalid classes, boxes outside
the image, identical annotations). **Warnings** do not block export: high
box overlap (IoU >= 0.70) or projected dimensions under 5 pixels. Some
warnings represent valid crowded products and require manual review.

Click a row and **Select Problem Annotation** to select the corresponding
Plane when Annotation Edit is enabled. The report is a **snapshot**: rerun
validation after modifying objects. Export always reruns validation, even if
the visible report was generated earlier. No rendered imagery or dataset ZIP
is produced by this feature.

Blender smoke check (from repository root, Git Bash):

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python scripts/blender_quality_gate_smoke.py
```


## v0.4-alpha.1 — Deterministic glass artifact presets

The Glass / Artifacts panel now exposes one-target preset controls:
`Clean`, `Light Condensation`, `Heavy Condensation`, `Frost`,
`Dirty Glass`, `Reflections`. Each applies to the selected or explicitly
chosen **Glass Target**, including objects locked in Annotation Mode.
The procedure changes **only material and custom properties** — no position,
geometry, camera, photo source, or YOLO annotation is modified.

`Intensity` scales the preset strengths; `Coverage` controls procedural
micro-droplet density; `Seed` chooses a reproducible Voronoi/dirt UV pattern.
`Reflections`, `Haze`, `Frost`, `Droplets`, `Dirt` and `Coverage` object
sliders update the material through drivers. An edited **Object Seed** needs
`Refresh Glass Pattern` to regenerate the UV pattern.

All presets are procedural and approximate, not physically validated
ice/fog optics. The original image is never modified. These controls are
for image variation; dataset batch randomization remains a future stage.

Blender smoke (run from repository root):

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python scripts/blender_glass_artifacts_smoke.py
```


## Glass Realism v0.4.0-alpha.3 (2.5D source-photo warp)

Glass artifacts use a new **render-only** shader layer. It introduces contrast-
shaded droplet rims, a seeded local displacement of source-photo UVs inside
individual droplets, broad moisture islands, and fine Voronoi crystal branches
strengthened in frost regions. No mesh, camera or YOLO coordinates are changed.

**The distortion is an image-space approximation, not physically simulated
ray refraction or a real 3D water surface.** It works when the source photo is a
BVT-style rectangle with affine UVs, even when the Photo Plane is rotated in
3D. Imported photos with unsupported/non-affine UVs automatically retain
shaded rim, wetness and frost, but disable photo resampling to avoid projecting
the wrong image pixels. Two glass surfaces have independent materials and
seeds. The unmodified source photo remains underneath both overlays.

New glass settings: **Refraction Strength** (0–0.04, default .016) and
**Droplet Relief** (0–1, default .8). Both have per-object overrides; Apply
Preset sets them for the targeted glass, Refresh Pattern rebuilds shader data.
The export JSON manifest records both values. For a stronger result, select a
Glass Target, `Heavy Condensation`, Intensity 1.0, Coverage .70, Droplet Scale
1.25, Refraction .024, Relief .95 and Seed 72, then press Apply Glass Preset.

### Render and compare every preset (Blender GUI is not required)

Run from repository root (Git Bash):

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup \
  --python scripts/blender_glass_visual_gallery.py -- \
  --output "D:/BVT-Studio/qa_renders/glass"
```

The smoke test saves **eight actual PNGs**: source, Clean, Light Condensation,
Heavy Condensation, Frost, Dirty Glass, Reflections, and another heavy
condensation render with a different seed. The script checks file creation,
material node connectivity, different resulting PNGs and unchanged glass
transform. Rendering success alone **does not certify photorealism**: inspect
the PNGs side by side at 100% and against real fridge photographs. The output
folder is ignored by Git. Existing v0.3 E2E YOLO smoke tests remain supported.

## Hybrid Glass Artifacts v2 — v0.4.0-alpha.4-step1

The previous Noise/Voronoi-based Light and Heavy Condensation were insufficiently
realistic. This experimental step uses a generated, per-Glass **RGBA atlas**:
red = shaped droplet height, green/blue = encoded X/Y surface slopes, alpha =
spatially varying wet film. Beads are seeded, irregular, mixed-sized and
occasionally elongated by gravity. Shader pseudo-specular rims and image-space
source-photo refraction use the same coherent droplet surface. This is still
**2.5D optical approximation**, not full optical ray tracing.

**Only `LIGHT_CONDENSATION` and `HEAVY_CONDENSATION` use this new shader.**
Other presets remain on the alpha.3 implementation. A per-object generated
Blender image (`BVT_Hybrid_Droplets_<uid>`) is saved in the .blend, reused
when parameters don't change, and regenerated on Apply/Refresh after seed,
coverage, droplet scale, wetness, or micro-droplet changes. No PNG texture
files or external Python packages are downloaded; requires NumPy shipped
with Blender. Non-affine source photo UVs gracefully disable re-sampling.

### Blender UI — Glass Artifact Engine

Select the target Glass Plane and choose Light Condensation / Heavy
Condensation. New controls **Wetness** (0–1) and **Micro Droplets** (0–1)
join Coverage, Droplet Scale, Refraction Strength, Droplet Relief and Seed.
Press **Apply Glass Preset**, then render F12. For selected-object custom
property edits use **Refresh Glass Pattern**.

### Visual QA (Blender 5.2.3)

From Git Bash, run the new gallery with a synthetic high-contrast source:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup \
  --python scripts/blender_hybrid_condensation_gallery.py -- \
  --output "D:/BVT-Studio/qa_renders/hybrid"
```

For genuine retail inspection **pass an actual original fridge PNG/JPEG**:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup \
  --python scripts/blender_hybrid_condensation_gallery.py -- \
  --photo "D:/Images/freezer_photo.png" \
  --output "D:/BVT-Studio/qa_renders/hybrid_freezer"
```

Each run outputs `00_source.png`, `01_clean.png`, `02_hybrid_light.png`,
`03_hybrid_heavy.png`, `04_hybrid_heavy_seed73.png` and `hybrid_manifest.json`.
The test checks changed rendered pixels, independent glass materials and
unchanged glass transforms; **its `OK` does not establish photorealism**.
Inspect full-size PNGs next to actual droplet photographs before producing
YOLO training data. Existing YOLO code and dataset export are unchanged.


## Current build stage

`alpha.4-step3` adds UV-fitted freezer glass sections and an optional inner aperture mask for Hybrid Condensation visual QA.


## Precision Glass Mask QA (`v0.4.0-alpha.4-step4`)

Assign an optional PNG mask to an individual `Glass_p_*` via **Glass Artifact Engine → Mask PNG → Assign PNG Mask (Pack)**.
Black RGB forbids all glass effects; white permits them; gray partially blends them.
The image is read in the Glass plane's UV space and *packed into the .blend*;
the original filesystem path is stored for traceability. Each glass object owns
its PNG image reference, independent seed, and enabled state. Use **Toggle PNG Mask**
to compare enabled/disabled without losing a packed mask. A requested but missing
packed image raises an error rather than silently rendering an unmasked effect.
The optional rectangular inset/aperture masking remains active.

**QA_TRANSPARENT** is the exact no-effect reference. Do not use legacy CLEAN as a
pixel-identical control, because it intentionally retains subtle reflections.

Run `scripts/blender_precision_mask_qa.py` with Blender 5.2+ and `--photo` pointing
at the real source PNG. The script creates four UV-fitted Glass planes, imports
four independent synthetic test PNG masks (with black forbidden openings and
mid-gray bands), renders per-glass grayscale mask PNGs and a union debug PNG,
compares all effect renders against the QA_TRANSPARENT control, and writes a
report including `leakage_pixels`, `leakage_ratio`, and `leakage_bbox_xyxy`.
These synthetic QA masks test the mask *mechanism*, not the precise outline of
your freezer frame. Replace them with hand-drawn or segmented masks for production.
Use `--save-blend` only when you explicitly want a new QA .blend saved; masks and
parameters will be packed and persist across reopening. The QA script does not
write to a user-supplied `.blend`, and never edits YOLO objects.


## alpha.5-step1 — Photographic water droplet maps

In **N → BVT Studio → Glass Artifact Engine** select one `Glass_p_*`.
Under **Photographic Droplets** provide **three different, same-sized PNG files**:
**Alpha** (black=no droplet; white=full droplet; gray=partial), **Height**
(black=low; white=high) and **Normal** (OpenGL tangent convention RGB;
neutral=(128,128,255), +Y=green). All three are sampled as **Non-Color**.
Use **Import & Pack Droplet Maps** to switch that glass to `PHOTO_MAPS`.
The images are packed into the `.blend`, so they persist across machines.
The **Procedural / Photo Maps** buttons select the source for the chosen glass;
**Map Tiling**, **Map Rotation (degrees)** and the glass's Seed reproduce the
photo-map placement (click **Photo Maps** again to apply edited transforms).
Only **Light Condensation** and **Heavy Condensation** consume droplet maps.
**QA Transparent** and Frost/Dirty/Reflections retain their existing behavior.
Precision PNG Glass Masks continue to gate the *final* material independently.
A missing packed source image raises an error instead of falling back silently.

**Realism is input-dependent:** the patch provides a rendering pathway, not
photographic source textures. The Blender QA script generates synthetic PNGs
to test import/packing/seed/masking only; those generated maps must not be
represented as real droplet photographs or photorealistic training data.

Run the Blender visual gate with your own source photo:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_droplet_maps_gallery.py -- \
  --photo "C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png" \
  --output "D:/BVT-Studio/qa_renders/photo_droplets_step1"
```

Do not accept visual quality until you run this with suitable real photo maps.


## alpha.5-step2 — Generated Realistic Droplet Atlas

BVT Studio now supports **three source modes** per `Glass_p_*`:
`PROCEDURAL` (legacy), `PHOTO_MAPS` (real user PNGs) and `REALISTIC_ATLAS`
(generated synthetic maps). The last mode samples the same packed
Alpha/Height/OpenGL Normal pathway as `PHOTO_MAPS` while preserving
**separate image datablocks** for each mode. This is a more varied synthetic
approximation, **not photographic water or verified photorealistic output**.

In Blender 5.2+ open **N → BVT Studio → Glass Artifact Engine**. Select
Glass Target and preset `LIGHT_CONDENSATION` or `HEAVY_CONDENSATION`; choose
Atlas Resolution (256/512/1024), Density (0.25–2.0), Streaks (0–1), and
Seed. Click **Generate & Pack Atlas**. For switching to previously generated
maps use **Use Saved Realistic Atlas**; previously imported maps remain
accessible through **Photo Maps**, or use **Procedural** for the original atlas.
All generated maps and their provenance parameters are stored in `.blend`.
Existing per-glass Precision PNG Masks still gate the final shader.

Blender headless visual QA from repository root, Git Bash:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_realistic_droplet_atlas_gallery.py -- \
  --photo "C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png" \
  --output "D:/BVT-Studio/qa_renders/realistic_droplets_step2" --save-blend
```

Produces `01_procedural.png`, `02_photo_maps.png` (test synthetic maps),
`03_realistic_atlas.png`, `04_atlas_seed73.png` and
`05_realistic_masked.png`; also writes full grayscale Alpha/Height RGB
normal previews (`atlas_alpha.png`, etc) and `realistic_atlas_manifest.json`.
A saved `.blend` is optional. To verify its packed maps after reopening:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_realistic_atlas_persistence_smoke.py -- \
  --blend "D:/BVT-Studio/qa_renders/realistic_droplets_step2/realistic_droplets_smoke.blend"
```

Atlas textures are synthesized in Blender from seeded NumPy arrays, requiring
no third-party models. They do not segment the refrigerator frame or alter
YOLO labels; supply Precision Masks to exclude metal. For dataset use, review
photographic realism, class-label legibility and source similarity visually.

### alpha.5-step2 — Inactive packed map persistence fix

Blender can drop image datablocks that are no longer used by any material, even
if their pixels were packed. Both the PHOTO_MAPS and REALISTIC_ATLAS image banks
now set Image.use_fake_user=True on import. This preserves the inactive bank in
the saved .blend; replacement and rollback remove orphaned old images correctly.

Existing smoke .blend files created before this fix may already have lost the
inactive map bank. **Rerun blender_realistic_droplet_atlas_gallery.py with
--save-blend** to regenerate and save both banks, then rerun the persistence smoke.

## Optical Water — `v0.4.0-alpha.5-step3`

Optional atlas-only rim/highlight/lens improvements for the generated
`REALISTIC_ATLAS` source. The previous `PROCEDURAL` and `PHOTO_MAPS` shaders
remain unchanged, and optical settings are per Glass Plane (persist in `.blend`).
In Blender, use **N → BVT Studio → 4. Glass Artifact Engine → Optical Water**
and select **Enable Optics** / **Disable Optics** to compare the same atlas.
No extra texture downloads or ZIP assets are required for the A/B smoke test.

See [Optical Water Step 3](docs/OPTICAL_WATER_STEP3.md) for scene setup, headless
comparison, persistence checks, known limitations and reproducibility.


### Optical anti-halo correction (alpha.5-step3 QA)

The optional `REALISTIC_ATLAS` optical shader uses **narrow, directional,
low-energy contact arcs** rather than bright outlines around the whole droplet.
A softened refraction gain avoids exaggerated refracted bright shelf edges.
After applying the follow-up patch, rerun `scripts/blender_optical_water_gallery.py`
on the same photo and compare `06_optical_off.png` vs `07_optical_on.png`;
`08_optical_restored.png` should still be exactly the OFF render.
This does not change Alpha/Height/Normal atlas pixels, masks, or YOLO export.
A realistic look still requires visual approval on your freezer photo.

## alpha.5-step4 — Visual Quality Calibration

Run `scripts/blender_visual_quality_calibration.py` on an existing photo to
compare optical settings on a fixed Realistic Atlas. The script reuses the
four-section precision-mask QA fixture, reports leakage/bright-outlier/edge
retention proxies, exports a four-way PNG montage and chooses a passing
candidate (or explicitly reports none). Existing YOLO Detect TXT can be used
**read-only** as SKU regions of interest. No OCR accuracy is inferred.

For instructions, thresholds and visual limitations, see
[Visual Quality Step 4](docs/VISUAL_QUALITY_STEP4.md). In Blender, the
**Glass Artifact Engine → Visual Quality Calibration** section can load its
`visual_quality_report.json` to display the recommendation.

## alpha.5-step5 — Quality Gate v2

Target-based **LIGHT/MEDIUM/HEAVY** synthetic condensation calibration with
three independent optic variants, per-glass Precision Mask leakage checks,
local highlight/gradient detail proxies and optional read-only YOLO Detect TXT
as SKU regions. Selection penalizes deviation from a profile's target optical
intensity; **maximum distortion no longer wins by default**. All thresholds
are provisional; no OCR or photorealism guarantee is implied. See
[Quality Gate v2 Step 5](docs/QUALITY_GATE_V2_STEP5.md) for the Blender
headless commands, outputs, persistence smoke and limitations. The sidebar's
Visual Quality report reader now accepts the v2 JSON as well as legacy Step 4.
