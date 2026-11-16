# BVT Studio — 2.5D Dataset Builder v0.2.0

**Experimental standalone Blender 5.2+ add-on**, built from the seven BVT prototype Python scripts.
No external dependencies beyond Blender's included Python API.

## Installation (Windows Blender 5.2.3)

1. Back up your `.blend` project.
2. Blender → **Edit → Preferences → Get Extensions** → drop-down at the top right → **Install from Disk**.
3. Choose **`BVT_Studio_Blender_Addon_v0.2.zip`**. This is a legacy add-on ZIP, with `bvt_studio/__init__.py` at the archive root.
4. If necessary, enable **BVT Studio — 2.5D Dataset Builder** in preferences (add-ons / installed extensions).
5. In the **3D Viewport**, press **N** and open the **BVT Studio** tab.

If the Blender version displays the extension-warning prompt, allow installation of this local legacy add-on.

## Recommended workflow

1. **Photo / Scene:** Click *New Scene from Photo* (makes a separate scene, preserves your original), or select an existing `BVT_Freezer_Image_Plane` and click *Use Selected Image Plane*. Select the camera frame profile and click *Frame Camera to Photo*.
2. **Glass:** Create/position your own glass Plane slightly **toward camera** from the photo plane. Select it → *Setup Selected Glass Plane*. Tune `Reflections`, `Tint`, `Haze`, `Frost` with sliders. One glass object per independent surface is supported. Never run Glass Setup on the photo plane.
3. **Glass organization:** When you select any user-created Plane and click *Setup Selected Glass Plane*, BVT Studio assigns a glass shader, moves it into `BVT_Glass` and renumbers every glass plane as `Glass_p_001`, `Glass_p_002`, etc. **Register / Setup Glass All** also recognizes old `Glass`, `Glass.001`, `Glass_01`, `Glas_001` and existing tagged glass overlays, moves them into the same collection and configures their materials (image-textured/photo planes are skipped to avoid overwriting). **Renumber Glass 001...N** changes names and collection membership only. Geometry, position, and user-defined glass settings are preserved. Glass objects remain independent of `BVT_Annotations`.
4. **Annotations:** Click *Add Annotation* and move/resize the rectangular plane over each visible SKU, or use existing manually made `plane_p_001..N` and click *Register / Color All*. A colored **Wireframe modifier** makes the rectangle visible in viewport. Move the **original rectangle mesh**, not its modifier. Edit Class ID / name on the selected annotation. For default category detection, keep all IDs at `0`, class name `ice_cream`.
5. *Renumber 001...N*, *Validate YOLO Boxes*, and optionally *Render Outlines: ON* to preview colored bounding boxes in F12. For dataset export, outlines will **always** be hidden temporarily.
6. **Export:** Save the `.blend`, select an output folder, then *Export Clean Image + YOLO*. Each click adds `sample_000001`, `sample_000002`, ... in a dataset structure.

## What is implemented

- Image import (and original/current-scene reuse) + alpha-aware unlit photo material.
- Exact image aspect, orthographic camera, presets for photo, 4:3, 3:4, 16:9, tablet 4:3.
- Glass on user-created mesh Plane: reflection, haze, tint and frost shader controlled by Blender object custom-property drivers.
- Automatic `Glass_p_001...N` naming, `BVT_Glass` collection, batch registration/setup and explicit glass renumbering; no automatic creation of glass geometry.
- Create/register/renumber annotation rectangles, independently colored emission-based outline preview, editable class metadata.
- Validate rectangles in camera coordinates (outside frame, zero size, class ID gaps, near-duplicates), single-image YOLO `class cx cy w h` export.
- Clean PNG render, TXT label file, `data.yaml`, per-sample JSON manifest (with annotations, camera profile, glass parameters).
- Existing project scene preserved when importing a new photo.

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

The generated **legacy Blender add-on archive** is `dist/BVT_Studio_Blender_Addon_v0.2.zip`. It has the `bvt_studio/` Python package at ZIP root, which is the same structure that worked in Blender 5.2.3 for v0.1. This is not a Blender Extensions platform manifest package.

See [docs/PUBLISHING.md](docs/PUBLISHING.md) for GitHub initialization and release upload.

## Output structure

```text
bvt_studio_dataset/
  images/train/sample_000001.png
  images/val/                     # EMPTY — prepare independent validation data
  labels/train/sample_000001.txt
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
| BVT_Glass_Overlay | not used: this add-on **does not** generate glass geometry |
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
