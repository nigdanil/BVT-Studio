# BVT Studio — Water QA Calibration v0.2.1

> Current example inputs: `examples/freezer_planogram/`. See `examples/README.md`; older installation and absolute path examples below describe the historical patch.

Target: `feature/photorealistic-droplets-v05`, based on the uncommitted Gallery v0.2 on commit `8934f24`.

This patch changes **only** `scripts/bvt_glass_effect_gallery_v02.py`, plus new tests/scripts/docs. The water generator, addon registration, UI implementation, YOLO exporter and Step 6 dataset QA are unchanged.

## Problem addressed

Gallery v0.2 rendered `preset_without_water.png` before installing the `REALISTIC_ATLAS`. Thus the comparison changed both the shader mode and the water, inflating `changed_ratio_in_rects` and `visible_proxy`.

v0.2.1 first installs a valid neutral RGB atlas on every affected glass pane: `Alpha=(0,0,0)`, `Height=(0,0,0)`, `Normal=(0.5,0.5,1)`. The same real Blender importer, packed PNG texture datablocks, masks, seed, UV tiling, preset, optical gains and stress flag are applied on baseline and final. Blender shader **node graph topology** is independently fingerprinted by nodes and links and required to match. Renderer-affecting BVT object settings (seed, preset, mask identity, optical gains, tiling, stress) must also match. `preset_without_water.png` now means *neutral REALISTIC_ATLAS with the underlying condensation preset still active*, not clean glass.

The null test re-installs zero-water textures and rerenders `zero_water_rebuild.png`. Any changed pixels exceeding RGB 4/255, within or outside the four glass panes, make the Blender run fail. JSON manifests include `zero_water_test`, `calibration` and `quality.baseline_mode`. To prevent a false demonstration of visibility, `visible_proxy` is recalculated from the matched baseline. These values are local RGB visibility proxies, not visual realism or instance detection, and overlapping event boxes may share evidence.

## Install

1. Extract ZIP at `D:\BVT-Studio`, preserving `scripts/`, `tests/`, `patches/`, `docs/` and `PATCH_MANIFEST_V021.json`. Do not extract into another nested directory.
2. In Git Bash:

```bash
cd /d/BVT-Studio
set +e
python scripts/install_water_qa_v021.py
echo "INSTALL_V021_EXIT=$?"
python -m py_compile scripts/bvt_glass_effect_gallery_v02.py scripts/blender_gallery_v021_gui_smoke.py
echo "COMPILE_EXIT=$?"
```

Installer is idempotent and refuses unknown source edits. Backup: `qa_renders/patch_backups/bvt_glass_effect_gallery_v02_pre_v021.py`. If it refuses due to a SHA mismatch, do not delete/revert any changes; inspect `git diff` and review the conflicting gallery script.

3. All unit tests in Blender 5.2.3:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python-expr "import sys,unittest;sys.path.insert(0,'D:/BVT-Studio');r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('D:/BVT-Studio/tests'));assert r.wasSuccessful()"
echo "UNIT_TEST_EXIT=$?"
git diff --check
echo "DIFF_EXIT=$?"
```

Expected test count is **188** if the user's previous 182 tests and this patch's 6 added tests are present. Any other test additions change this count; rely on `OK` and `UNIT_TEST_EXIT=0`.

## Blender integration and QA

```bash
cd /d/BVT-Studio
set +e
bash scripts/run_bvt_water_qa_v021.sh
echo "RUNNER_EXIT=$?"
```

`run_bvt_water_qa_v021.sh` creates a fresh folder `D:\BVT-Studio\qa_renders\effects_gallery_v021` and leaves `effects_gallery_v02` untouched. It renders `00_clean` plus Micro, Macro, Running, Combined with and without optics, Heavy Running and Stress; it reopens `10_combined_water_optics/scene.blend` and then runs strict manifest QA. Each water variant contains:

```text
07_macro_droplets_only/
  scene.blend
  render.png
  preset_without_water.png     # neutral REALISTIC_ATLAS, same material topology
  zero_water_rebuild.png       # independent zero-water rerender
  manifest.json
  maps/Glass_p_001/{alpha,height,normal}.png
  masks/...
```

Success markers: `ZERO_WATER_NULL_TEST=PASS`, `NEUTRAL_CONTROL=REALISTIC_ATLAS_SAME_SHADER`, `GALLERY_V021_MANIFEST_QA=PASS`, `WATER_QA_V021_EXIT=0`. The strict report fails if no event is locally visible in an expected family; this is diagnostic, not a reason to raise shader intensity blindly.

**Important:** the re-render null test does not certify the *realism* of the water. Visual review of actual PNGs is still required. Geometric masks are synthetic and must not be described as verified glass segmentation.

## Independent Glass Manager / JSON test in Blender GUI

1. Ensure the v0.2 add-on ZIP is installed and enabled in Blender 5.2.3. This v0.2.1 patch does not change addon code. If needed, run `python scripts/build_addon.py` and reinstall its generated `dist/` ZIP.
2. In the Blender UI, open `D:\BVT-Studio\qa_renders\effects_gallery_v021\10_combined_water_optics\scene.blend`.
3. Open the Python Console (Shift+F4 when cursor is over a Blender editor). Run:

```python
exec(compile(open(r'D:\BVT-Studio\scripts\blender_gallery_v021_gui_smoke.py', encoding='utf-8').read(), r'D:\BVT-Studio\scripts\blender_gallery_v021_gui_smoke.py', 'exec'))
```

Expected: `GUI_GLASS_SELECT=PASS`, `GUI_JSON_IMPORT=PASS` and the report `qa_renders/effects_gallery_v021/ui_gui_smoke_report.json`. This test invokes the actual add-on operators **in the GUI context** and checks independent packed atlas maps for four glasses, seeds, and imported types. It does not simulate a mouse click.
4. Switch the editor back to 3D Viewport (Shift+F5), press `N`, open **BVT Studio → 3A. Glass Target & Presets v0.2**. Click `Glass_p_001`, `Glass_p_002`, `Glass_p_003`, `Glass_p_004`: ensure the selected target and seed/Water Type fields follow the selected pane, while unaffected panes retain their settings. Check the `4. Glass Artifact Engine` display for the same target. Take screenshots of pane 001 and 004.
5. Import `D:\BVT-Studio\configs\scene_four_glasses_v02.json` manually in the panel and verify the visible feedback `Applied 4 glass pane(s)` and distinct water types Macro, Micro, Running, Combined. Render with F12 and inspect boundaries.
6. **Do not save over the opened gallery scene after the GUI smoke unless you intend to retain its imported configuration.** Reopen the `.blend` without saving to discard in-memory changes.

The tool author cannot run the user's interactive Blender window. The GUI runtime and click-through checks must be confirmed from the user's output/screenshots.

## Acceptance checklist

- [ ] `INSTALL_V021_EXIT=0`; original v0.2 source SHA matches or was already upgraded
- [ ] All Blender unit tests pass, `UNIT_TEST_EXIT=0` and `DIFF_EXIT=0`
- [ ] Macro, Running, Combined, Stress scene render/persistence pass
- [ ] Neutral Atlas A/B: `ZERO_WATER_NULL_TEST=PASS`, no changed pixels >4/255 in repeated neutral render
- [ ] Baseline vs water shader topology fingerprints identical per glass
- [ ] `visible_proxy` recalculated and manifest guard passes, no leakage outside test geometry
- [ ] Real UI selection of all four glass panes confirmed; JSON import successful
- [ ] Visual quality reviewed by user on PNGs; only then commit to feature branch
