# Post-merge regression QA

## Recorded baseline — 2026-11-22

- Public pre-release: `v0.4.0-alpha.5-demo.2`, source `383a4b0`.
- Clean clone of merged `main`: `beae8a8` (same source tree as the release commit at merge time).
- Blender 5.2.3 LTS on Windows; Python 3.12 with NumPy 2.2.6 for external tests.
- User-provided console log: 193 unit tests, eight headless integration smokes, 13 generated/reopened scenes, seven zero-water controls, 13 isolated rerenders; all pass. The portability driver expects 157 packed resources. Manual editing and installation of the public ZIP are separate acceptance steps.

This document records a tested configuration; it is not an assertion that every OS, device or actual deployment has passed.

## Repeat from a clean checkout

Use a fresh clone and a new local build version. Never reuse a release tag for a changed source tree. In Git Bash on Windows:

```bash
python -m pip install numpy==2.2.6
python scripts/validate_examples.py
python -m unittest discover -s tests -v
```

```bash
(
  set -e
  BLENDER='/c/Program Files/Blender Foundation/Blender 5.2/blender.exe'
  for script in blender_ui_panels_smoke.py blender_annotation_manager_smoke.py \
    blender_depth_smoke.py blender_glass_artifacts_smoke.py \
    blender_quality_gate_smoke.py blender_export_preview_smoke.py \
    blender_hybrid_atlas_persistence_smoke.py blender_v03_e2e_smoke.py; do
    "$BLENDER" --background --factory-startup --python-exit-code 1 \
      --python "scripts/$script"
  done
)
```

The release builder validates the inputs, repeats unit tests, generates and reopens all 13 scenes, and writes four archives with checksums. The portability smoke extracts scene copies without external texture files, compares SHA-256 of packed payloads and rerenders with Blender. It does not modify the original archives or save the extracted scene. It returns 0 only when all 13 cases and 157 resources pass; pixel tolerance is 4/255, not a requirement of byte-identical ZIPs or cross-GPU renders.

```bash
python scripts/build_release.py --version v0.4.0-alpha.5-mainqa.2 \
  --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
python scripts/bvt_release_portability_smoke_v02.py \
  --release dist/releases/v0.4.0-alpha.5-mainqa.2 \
  --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' \
  --report qa_renders/main_portability_report.json
```

Keep logs/reports local; report only relevant status and anonymize local paths before sharing publicly. A warning during initial atlas saving is not itself a final-scene failure: the release builder relocates and verifies packed resources later. Blender `Material.use_nodes` deprecation is a future compatibility item.

## GUI acceptance (published package)

Install the official add-on ZIP from GitHub, open a **copy** of a four-glass Combined + Optics scene from the public gallery, and confirm the following:

- [ ] Sidebar visible and panels expand.
- [ ] All four targets select independently.
- [ ] Editing/applying parameters to one pane does not change the other panes.
- [ ] JSON example imports into the four targets successfully.
- [ ] F12 render succeeds and the effect is visually plausible for the use case.
- [ ] Save As to a new file and reopen; pane settings and resources persist.

The GUI driver `scripts/blender_gallery_v021_gui_smoke.py` also tests target selection and JSON import. It intentionally requires the opened scene path to contain `effects_gallery_v021`. Extract the public gallery into a folder with this name in its path, open the Combined scene, and set `BVT_REPO_ROOT` to the cloned repository root in Blender's Python Console before executing the driver. It mutates the in-memory scene; do not save over the distributed demo. Manual visuals and actual installation provenance still need checking.

## Not established by these tests

Physical water realism, real-world labeling accuracy, YOLO/VLM metric gains, and cross-platform Blender rendering require independent experiments. The bundled synthetic reference fixture is not a training benchmark.
