# BVT Studio — 2.5D Dataset Builder for Blender

[![Source checks](https://github.com/nigdanil/BVT-Studio/actions/workflows/check.yml/badge.svg?branch=main)](https://github.com/nigdanil/BVT-Studio/actions/workflows/check.yml)
[![Alpha demo](https://img.shields.io/badge/release-v0.4.0--alpha.5--demo.2-orange)](https://github.com/nigdanil/BVT-Studio/releases/tag/v0.4.0-alpha.5-demo.2)

**Experimental open-source Blender add-on for controlled image augmentation and computer vision research.**
Create independent glass layers over a source image, apply reproducible visual artifacts, annotate objects and export clean renders with YOLO Detect labels.

## Quick start — download a ready-to-open demo

Tested on **Blender 5.2.3 LTS (Windows)**. The current public release is an alpha pre-release, not a production-ready product.

| Download | Contents |
| --- | --- |
| [Add-on ZIP](https://github.com/nigdanil/BVT-Studio/releases/download/v0.4.0-alpha.5-demo.2/BVT_Studio_Addon.zip) | Installable legacy Blender add-on |
| [Effects Gallery](https://github.com/nigdanil/BVT-Studio/releases/download/v0.4.0-alpha.5-demo.2/BVT_Studio_Effects_Gallery.zip) | 13 ready-to-open `.blend` scenes, PNG renders and HTML index |
| [Examples](https://github.com/nigdanil/BVT-Studio/releases/download/v0.4.0-alpha.5-demo.2/BVT_Studio_Examples.zip) | Source image, masks, maps and JSON presets |
| [QA Reports](https://github.com/nigdanil/BVT-Studio/releases/download/v0.4.0-alpha.5-demo.2/BVT_Studio_QA_Reports.zip) | Render comparisons, manifests and reopen reports |
| [Checksums](https://github.com/nigdanil/BVT-Studio/releases/download/v0.4.0-alpha.5-demo.2/SHA256SUMS.txt) | SHA-256 archive integrity |

1. In Blender, disable/remove any previous BVT Studio installation; restart if needed.
2. Open **Edit → Preferences → Get Extensions → Install from Disk** (top-right menu). Select `BVT_Studio_Addon.zip` and enable **BVT Studio — 2.5D Dataset Builder** if needed.
3. In the 3D Viewport press **N**, then select **BVT Studio**. The published demo uses internal build label `v0.4.0-alpha.5-step5` and Blender add-on version `0.4.0`.
4. Extract the Effects Gallery ZIP. Open `BVT_Studio_Effects_Gallery/10_combined_water_optics/scene.blend`, and press **F12** to render. Work on a copy if editing. No gallery regeneration is required.
5. In the **3A. Glass Target & Presets v0.2** panel select a glass target; edit its effect parameters or import `examples/freezer_planogram/configs/scene_four_glasses_v02.json` from the Examples ZIP.

The gallery has packed image resources. Existing Blender installations load add-on code from their installed add-ons directory, not from a Git clone.

## Capabilities

| Area | Implemented |
| --- | --- |
| Scene | Photo import, orthographic camera, aspect profiles, photo-relative depth and edit locks |
| Glass | Independent panes, per-glass masks, source-relative UV sampling |
| Artifacts | Light/heavy condensation, frost, dirt, reflections, macro droplets, microbeads, running water, combined optical modes |
| Configuration | Explicit seeds, per-glass parameters, JSON preset import |
| Annotation | Create/register rectangular annotations, class IDs, batch editing, validation and outlines |
| Export | Clean PNG, YOLO Detect TXT, relative data.yaml, SVG review preview and JSON manifest |
| QA | Calibrated zero-water controls, pixel leakage/visibility proxies, packed resource checks and scene reopen |

These are 2.5D image-space approximations, not physically traced droplet geometry.

## Create a scene and export a sample

Import a source image using **Photo / Scene → New Scene from Photo**. In **Glass / Surfaces**, create and position a glass overlay for each glass region. Set per-pane effects via the Glass Target / Artifact Engine panels. Use the Annotation Manager to create and place rectangles over visible objects, assign classes and validate boxes. Save the `.blend`, choose an output directory, then use **Export Clean Image + YOLO**. The export temporarily hides annotation outlines and restores their previous state.

Typical output:

```text
bvt_studio_dataset/
  images/train/sample_000001.png
  labels/train/sample_000001.txt
  previews/sample_000001.svg
  sample_000001_manifest.json
  data.yaml
  images/val/
  labels/val/
```

The validation folders are initially empty. Use independently sourced, reviewed validation/test images; do not split augmented variants of the same original across training and evaluation sets. The current bundled freezer example has no verified YOLO labels.

## Build and test from source

```bash
git clone https://github.com/nigdanil/BVT-Studio.git
cd BVT-Studio
python -m pip install numpy==2.2.6 Pillow==12.3.0 openpyxl==3.1.5 jsonschema==4.26.0
python scripts/validate_examples.py
python -m unittest discover -s tests -v
python scripts/build_addon.py
```

Python 3.12 is used in source CI. The add-on ZIP contains `bvt_studio/` at its root. To render the calibrated water gallery locally (Git Bash):

```bash
bash scripts/run_bvt_water_qa_v021.sh
```

To build the full local demo and verify isolated rerenders (Windows Git Bash; pick a new, unused local version):

```bash
python scripts/build_release.py --version v0.4.0-alpha.5-local.1 \
  --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
python scripts/bvt_release_portability_smoke_v02.py \
  --release dist/releases/v0.4.0-alpha.5-local.1 \
  --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' \
  --report qa_renders/local_portability_report.json
```

The release builder requires a clean Git tree and Blender 5.2.3. It does not publish. See [Release Builder](docs/RELEASE_BUILDER_V01.md) and [Post-Merge QA](docs/POST_MERGE_QA.md).

## Validated baseline

Public demo tag: `v0.4.0-alpha.5-demo.2`, source commit `383a4b0`. Subsequent clean-clone regression on merged `main` (`beae8a8`, 2026-11-22) passed 193 unit tests, eight Blender integration smokes, 13 scene builds/reopens, seven zero-water controls and 13 isolated rerenders. Portability checks require packed resource hashes, relative paths and no RGB pixel differences above 4/255. This is evidence of reproducibility in the tested Windows environment, not ML accuracy or cross-platform validation.

## Project layout and documentation

- `bvt_studio/` — add-on source
- `configs/` — canonical regression configurations
- `examples/` — [self-contained example inputs](examples/README.md)
- `datasets/` — [research dataset metadata and setup](datasets/README.md)
- `docs/datasets/` — [collection provenance and storage policy](docs/datasets/README.md)
- `data_local/` — local research inputs and outputs (ignored by Git)
- `scripts/` — build, render and QA tools
- `tests/` — source and numerical tests
- `qa_renders/`, `dist/` — local generated outputs (ignored by Git)

Technical references: [Glass gallery](docs/GLASS_GALLERY_V02.md), [Water QA](docs/WATER_QA_CALIBRATION_V021.md), [Quality Gate v2](docs/QUALITY_GATE_V2_STEP5.md), [Real Dataset QA](docs/REAL_DATASET_QA_STEP6.md), [Changelog](CHANGELOG.md). Some technical notes describe historical patches; their installers are not required for a fresh clone of the current main branch. The [historical README at the release commit](https://github.com/nigdanil/BVT-Studio/blob/383a4b00c10989789dbcb596457366ec4e40b4a7/README.md) preserves earlier detailed instructions.

## Roadmap and limitations

Next: multi-example Dataset Runner, verified real-world photos and labels, independent data splits, controlled YOLO/VLM benchmarks. No validated real-world detection gains or physical realism claims are made. No automatic ground-truth annotation of hidden products, full 3D scene reconstruction, or segmentation export is provided by this demo.

## License

See [LICENSE](LICENSE) for the source-code license (GNU GPL v3). Confirm separate redistribution rights for any example assets or user-provided data. Do not commit private/customer data or large generated datasets.

## Example preset catalog (current source checkout)

See [the example configuration layout](examples/freezer_planogram/README.md). Import JSON from `examples/freezer_planogram/configs/presets/scenes/` or `examples/freezer_planogram/configs/presets/single_glass/`. Geometry and gallery configs are not GUI presets. The already published Demo 2 ZIP retains its original paths.
