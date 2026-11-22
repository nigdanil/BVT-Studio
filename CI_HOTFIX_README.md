# BVT Studio CI hotfix (2026-11-18)

Target: `feature/photorealistic-droplets-v05` at/after `c0547cc`.

GitHub Actions `source-checks` failed: NumPy missing in Python 3.12 causes 2 errors. The previous upload path does not match the ZIP emitted by `scripts/build_addon.py`.

Extract to `D:\BVT-Studio` preserving the `scripts/` folder.

```bash
cd /d/BVT-Studio
set +e
python scripts/install_ci_hotfix_20261118.py
echo "CI_PATCH_EXIT=$?"
git diff -- .github/workflows/check.yml
git diff --check
```

If `CI_PATCH_EXIT=0`, review the workflow diff, then stage **only** the CI change:

```bash
git add .github/workflows/check.yml
git diff --cached --check && git commit -m "ci(studio): install NumPy and upload current Blender addon" && git push origin feature/photorealistic-droplets-v05
```

Check GitHub Actions for the **new** commit. This package does not alter tests, Blender engine, masks, or YOLO code.
