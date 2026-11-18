# BVT Studio — Glass Effects Gallery v0.2 (experimental patch)

**Patch baseline:** `8934f24`, branch `feature/photorealistic-droplets-v05`.
**Blender:** 5.2.3 LTS on Windows. **Status:** source-level unit tests pass; GUI, EEVEE and headless rendering require validation on your Blender installation. Do not merge to `develop` before this validation.

## Scope

1. **Macro droplets:** independent count, diameter, outline irregularity, seed.
2. **Microbeads:** independent count and diameter; not merely `LIGHT_CONDENSATION` with a new scale.
3. **Running water:** elongated vertical streaks with adjustable count/length/width/taper. Gravity runs downward along pane V. Not fluid simulation.
4. **Optics:** existing BVT 2.5D local refraction, contact shadows/highlights and micro glints; default safety clamps are unchanged. Opt-in stress checkbox selectively raises the energy/clamps for experimental QA ONLY.
5. **Per-pane UI:** a new child panel **3A. Glass Target & Presets v0.2** lists `Glass_p_001…N`, switches target via BVT property (even when `hide_select` is set) and syncs that object's saved values into the controls. Legacy section 4's mask status now follows the explicit Glass Target instead of an unrelated Blender active object.
6. **Import scene JSON:** `configs/scene_four_glasses_v02.json` provides a reproducible preset per explicitly named pane; validate inputs before applying. Currently sequential application is NOT a transactional undo/rollback over all panes; keep a copy of your `.blend`.
7. **Universal gallery:** `configs/effects_gallery_v02.json` defines 13 modes; each mode yields a separate packed `.blend`, PNG, JSON manifest, 4 per-pane test masks and separate Alpha/Height/Normal preview maps; a root `index.html` and `summary.csv` are regenerated each run. Water-effect variants also render `preset_without_water.png` using exactly the same non-water glass settings, so "visible droplets" QA cannot be satisfied merely by the condensation haze of the preset. `summary.csv` reports water-specific changes separately from overall changes against `00_clean`.
8. **Render QA:** changed-pixel fraction, changes outside four geometric panes (3px anti-aliasing allowance), and per-generated-event *render-visible proxies* for macro/micro/streak. Visibility is measured from local RGB change and spatial span, and is not human perception or detector quality.

## Install (Git Bash)

**Back up** any real `.blend` and unsaved Blender changes first. **Do not use `git reset --hard`**. Keep this work in the current feature branch.

1. Unzip `BVT_Studio_Glass_Gallery_v02_PATCH.zip` **into `D:\BVT-Studio`** while preserving `bvt_studio/`, `scripts/`, `configs/`, `tests/`, `docs/`. These files have new names; they do not replace the v0.1 gallery files.
2. Verify the feature branch and HEAD is descended from `8934f24`.
3. Run the source installer, static/numeric tests and build:

```bash
cd /d/BVT-Studio
python scripts/install_gallery_v02.py
python -m unittest discover -s tests -v
python scripts/build_addon.py
git diff --check
git diff --stat
git status --short
```

4. Reinstall the **newly built** `dist/BVT_Studio_Blender_Addon_v0.4.0-alpha.5-step5.zip` in Blender via **Edit → Preferences → Get Extensions → Install from Disk**. The legacy ZIP filename still says `step5` because no release version bump is made in this experimental patch. If Blender keeps the old extension loaded, disable/remove that local installation and restart Blender before installing the new one. The v0.2 UI will not appear until the updated ZIP is loaded.

5. For the **full test under Blender's bundled NumPy**:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python-expr "import sys,unittest;sys.path.insert(0,'D:/BVT-Studio');r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('D:/BVT-Studio/tests'));assert r.wasSuccessful()"
```

6. A *quick visual smoke* of just macro droplets, instead of generating all scenes:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/bvt_glass_effect_gallery_v02.py -- \
  --repo "D:/BVT-Studio" \
  --photo "C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png" \
  --rects-file "D:/BVT-Studio/configs/bvt_freezer_glass_rects_1672x941.json" \
  --config "D:/BVT-Studio/configs/effects_gallery_v02.json" \
  --output "D:/BVT-Studio/qa_renders/effects_gallery_v02" \
  --mode 07_macro_droplets_only
```

**Note:** for measured QA, generate `00_clean` before running any other mode. The single-mode smoke still produces the scene and render but skips clean-relative QA until `00_clean/render.png` exists.

7. **Full gallery** (edit `PHOTO` in the runner if moved):

```bash
bash scripts/run_bvt_glass_gallery_v02.sh
```

Outputs:

```text
qa_renders/effects_gallery_v02/
  index.html
  summary.csv
  00_clean/{scene.blend,render.png,manifest.json,masks/*.png}
  06_microbeads_only/{scene.blend,render.png,manifest.json,masks/*.png}
  07_macro_droplets_only/{scene.blend,render.png,manifest.json,masks/*.png}
  08_running_water_only/{scene.blend,render.png,manifest.json,masks/*.png}
  09_combined_water_no_optics/{...}
  10_combined_water_optics/{...}
  12_stress_optics/{...}
  10_combined_water_optics/maps/Glass_p_001/{alpha.png,height.png,normal.png}
```

The runner reuses your existing v0.1 rectangles JSON if present, without overwriting it; otherwise it uses `bvt_freezer_glass_rects_v02_default.json`. If your source photo dimensions differ, edit a separate copy of the rectangle config.

The runner finishes by reopening `10_combined_water_optics/scene.blend` to check all atlas map banks, image masks and the source photo remain packed in Blender. The saved `.blend` may contain local source path metadata, but packed images are the primary embedded content. Some Blender warnings about external relative paths may still appear; the persistence check is authoritative for our packed images.

## In Blender UI

Open any saved `scene.blend` → `N` sidebar → **BVT Studio** → **3A. Glass Target & Presets v0.2**.

- Click `Glass_p_001` (or another pane). The target pointer changes without forcing a viewport selection or unlocking the photo.
- Choose `Water Type`: `MACRO`, `MICRO`, `RUNNING`, `COMBINED`.
- Edit counts, diameters, streak length/width/taper; enable/disable `Optical Water`.
- Click **Generate Water v0.2 (Selected Pane)**. It changes just one glass and packs new maps in the `.blend`.
- To import full pane presets, put `D:/BVT-Studio/configs/scene_four_glasses_v02.json` in the JSON path, then click **Import Glass Preset JSON v0.2**. Save the `.blend` as a NEW file first; the operation is sequential and will overwrite effects on the specifically named panes.
- Existing **4. Glass Artifact Engine** continues to work; its controls/quality report and YOLO exports are preserved.

## Masks versus droplet maps

The supplied gallery autogenerates **approximate rectangular PNG masks** for display only and packs them per pane. `Alpha/Height/Normal` are automatically produced by `water_effects_v02.py` and stored as `REALISTIC_ATLAS` maps. You do NOT need to type paths for them. For genuine photos, replace generated masks with correctly segmented glass areas; never reuse these approximate masks as verified ground truth.

## Review / acceptance checklist

- [ ] 13/13 modes produce `scene.blend`, `render.png`, `manifest.json` without Blender error.
- [ ] Reopen check: `BVT GALLERY v02 PERSISTENCE: OK`.
- [ ] Macro and micro variants are visually distinguishable at real camera resolution.
- [ ] Running streaks show continuous downward motion *appearance* (a static image), not merely short disconnected dots.
- [ ] 09 and 10 use identical source, geometry and atlas pattern, with only optical params changing.
- [ ] 10 and 12 differ visibly under stress mode, while normal mode remains bounded.
- [ ] UI changes only the selected `Glass_p_NNN`; other glass SHA/render appearance remains unchanged when it should.
- [ ] JSON import reuses known names, rejects unknown names/invalid values before any changes.
- [ ] No YOLO annotation or input images modified; no leaks beyond 3px geometry allowance.
- [ ] Manually review products for occluded text/labels before training. QA visibility counts are *proxies*, not certification.

## Constraints and design choices

- The source photo remains a 2.5D plane; refraction is a shader-space approximation, not glass/water ray tracing. Distinct graphics represent controlled effects, not physical evidence.
- The gallery produces new output under `qa_renders/`; never commit hundreds of PNGs or `.blend` outputs to the source repository.
- We intentionally leave existing `realistic_atlas.py`, YOLO exports, and Step 6 QA unchanged. New water generator runs alongside the old one.
- If Blender reports a validation/registration problem, do not push or merge. Share the full console log; source-only tests cannot establish in-Blender correctness.
