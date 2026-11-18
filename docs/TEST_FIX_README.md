# BVT Studio Gallery v0.2 — source-contract test compatibility fix

Applies to feature/photorealistic-droplets-v05 at commit `8934f24`, with Gallery v0.2 source already installed.

**Cause:** 4 legacy source-string assertions fail after adding the `glass_v02_ui` module and a conditional normal/stress cap in `optical_water.py`. These 4 assertions inspect string layout, not rendered output.

**Changes only:** `tests/test_droplet_maps.py`, `tests/test_optical_water.py`, `tests/test_realistic_atlas.py`, plus new helper `tests/_bvt_contract_v02.py`.

**No edits to:** source add-on modules, saved scenes, existing image/YOLO files, UI, gallery generation.

Run (Git Bash, from the repo root after extracting the ZIP into `D:/BVT-Studio`):

```bash
cd /d/BVT-Studio
set +e
python scripts/fix_gallery_v02_test_contracts.py
echo "FIX_EXIT=$?"

"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python-expr "import sys,unittest;sys.path.insert(0,'D:/BVT-Studio');r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('D:/BVT-Studio/tests'));assert r.wasSuccessful()"
echo "UNIT_TEST_EXIT=$?"

git diff --check
echo "DIFF_CHECK_EXIT=$?"
```

Expected: `FIX_EXIT=0`, `Ran 182 tests`, `OK`, `UNIT_TEST_EXIT=0`, and `DIFF_CHECK_EXIT=0`. Actual counts may change if additional tests are present.

The optical test still asserts the normal `.025` clamp, the stress `.06` clamp, and the explicit `bvt_optical_stress_test` gate. Registration assertions now check Python import and static `MODULES` registration via AST rather than adjacency in the source text.

**Important:** This does not prove Blender renders, `.blend` persistence, JSON scene loading, or real-world photo quality. Run gallery and persistence smoke afterward. Do not commit until all tests and Blender checks pass.
