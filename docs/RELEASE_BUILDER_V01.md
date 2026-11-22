# BVT Studio Release Builder v0.1

This stage packages the existing synthetic freezer example and calibrated gallery.
It does not implement Real Dataset Runner or claim a new add-on version. Choose a
new demo prerelease tag, e.g. `v0.4.0-alpha.5-demo.1`.

## Install and check

A fresh clone of current `main` already contains the Release Builder; do not run historical patch installers. Run `python scripts/validate_examples.py` and `python -m unittest discover -s tests -v` with Python 3.12 + NumPy 2.2.6. For isolated rerender validation, see [Post-Merge QA](POST_MERGE_QA.md).

Do not commit assets unless redistribution permission is confirmed. `examples/local/`, `qa_renders/` and `dist/` stay ignored. Release builds require a clean Git tree and record its exact SHA.

## Build locally on Windows (Git Bash)

```
python -m pip install numpy==2.2.6
python scripts/build_release.py --version v0.4.0-alpha.5-demo.1 \
  --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
```

It runs tests and validates the example; generates all 13 variants from the
calibrated v0.2.1 gallery; checks all manifests including seven null controls;
reopens all 13 scenes, relocates packed source/mask/map paths, saves and reopens
again; builds the legacy add-on; creates four ZIPs and checksums. The file
validation is not a human visual realism check. Local Blender 5.2.3 is required.

Outputs:

- `qa_renders/release_builds/<version>/gallery/index.html`: all 13 cases.
- `dist/releases/<version>/BVT_Studio_Addon.zip`: installer (legacy layout).
- `BVT_Studio_Examples.zip`: manifest-allowlisted example assets/configs.
- `BVT_Studio_Effects_Gallery.zip`: packed .blend files, source PNG, final PNGs,
  masks/maps and an HTML index; extract and open, no generation required.
- `BVT_Studio_QA_Reports.zip`: manifests, final/control PNGs for comparison,
  summary CSV and per-scene reopen reports.
- `release_manifest.json` / `SHA256SUMS.txt`: provenance and archive integrity.

No output ZIP directory is made until every run and reopen passes. A failed
build leaves a dedicated working directory for debugging; inspect it before
explicitly removing or archiving it to rerun the same version. Do not clear the
whole `qa_renders/`. `--version` is a **release tag**, not a change to `bl_info`.

## Publish (explicit, draft only)

Once the feature branch is reviewed and pushed, authenticate GitHub CLI (`gh auth
login`) and run `python scripts/publish_release.py --version
v0.4.0-alpha.5-demo.1 --approve-assets` on the exact built commit. It refuses dirty
trees, incorrect remote heads, changed archives and existing tags. Inspect the
created draft at https://github.com/nigdanil/BVT-Studio/releases before publishing.
Prefer publishing from accepted main after the PR merge, building again from that
commit. Nothing is published by build_release.py or normal source-checks.

Optional `demo-release` workflow: after the workflow is present on `main`, use
Actions → demo-release → Run workflow on main. Provide a new release version,
official Blender 5.2.3 Linux tar.xz URL and trusted SHA-256, confirm redistribution,
and choose whether to create a draft. The hosted runner uses Xvfb and software
Mesa; actual EEVEE compatibility is unverified. If GPU/headless support fails,
use the already known Windows Blender path. Never bypass rendering/QA to publish.

Remaining steps (separate work): multi-example dataset generator, real licensed
photos and verified masks, true YOLO labels, data splits and A/B ML validation.
