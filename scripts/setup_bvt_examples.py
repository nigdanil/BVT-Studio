#!/usr/bin/env python3
"""Install self-contained BVT Studio examples; no Git commands or Blender execution."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

IMAGE = 'chatgpt_000011.png'
EXPECTED_SHA = 'c3dd40d774eec1c3571866ab56b1c418f4665f783fa99d2b8dcef4da01972b30'
CONFIGS = ('bvt_freezer_glass_rects_1672x941.json', 'bvt_freezer_glass_rects_v02_default.json',
           'effects_gallery_v02.json', 'scene_four_glasses_v02.json')
COMMON = '''#!/usr/bin/env bash
# Shared gallery paths. Source from any gallery runner.
BVT_ROOT_POSIX="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "$BVT_ROOT_POSIX"
if command -v cygpath >/dev/null 2>&1; then
  REPO="$(cygpath -am "$BVT_ROOT_POSIX")"
else
  REPO="$BVT_ROOT_POSIX"
fi
EXAMPLE="${BVT_EXAMPLE_DIR:-$REPO/examples/freezer_planogram}"
PHOTO="${BVT_PHOTO:-$EXAMPLE/images/chatgpt_000011.png}"
RECTS="${BVT_RECTS:-$EXAMPLE/configs/bvt_freezer_glass_rects_1672x941.json}"
RECT="$RECTS"
CONFIG="${BVT_CONFIG:-$EXAMPLE/configs/effects_gallery_v02.json}"
if [[ -n "${BVT_BLENDER:-}" ]]; then
  BLENDER="$BVT_BLENDER"
elif command -v blender >/dev/null 2>&1; then
  BLENDER="$(command -v blender)"
else
  BLENDER="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"
fi
'''
ROOT_README = '''# BVT Studio examples

Self-contained, small reproducible inputs; source code stays in `bvt_studio/`,
canonical regression configurations in `configs/`, and generated results in
`qa_renders/` (ignored by Git). `local/` is an ignored area for private or large data.

- `freezer_planogram/`: synthetic four-pane reference fixture from Gallery v0.2.1,
  including scene and effect JSON, source image, and optional sample mask/map PNGs.
- Run `bash scripts/run_bvt_water_qa_v021.sh` from the repository or invoke it
  using its full path. It locates the repository relative to the runner.
- Override input paths with `BVT_EXAMPLE_DIR`, `BVT_PHOTO`, `BVT_RECTS`,
  `BVT_CONFIG`, and Blender with `BVT_BLENDER`. `BVT_OUTPUT_DIR` overrides the
  default output. Use absolute paths for overrides.
- Only commit images and assets you have permission to redistribute. Do not
  commit customer photos, full training datasets, or generated galleries.
'''
SCENE_README = '''# Freezer planogram reference (1672 x 941)

- `images/`: exact synthetic source image from the calibrated gallery.
- `configs/`: editable example copies of the canonical regression JSON files.
  The rectangles are approximate, not verified real-glass ground truth.
- `masks/`: optional generated per-pane precision-mask PNG examples.
- `maps/`: optional generated Alpha/Height/Normal PNG triplets (synthetic,
  not photographs); no external maps are necessary for REALISTIC_ATLAS.
- `labels/`: reserved for genuine YOLO annotations; no labels are fabricated.
- `scenes/`: reserved for small manually curated example .blend files.
  Bulk .blend/PNG outputs belong in ignored `qa_renders/`.

Default run: `bash scripts/run_bvt_water_qa_v021.sh`.
For GUI preset import, use `configs/scene_four_glasses_v02.json` **in this example**.
Generated test masks and maps, if copied, originate from
`effects_gallery_v021/10_combined_water_optics`. The gallery regenerates them;
these example PNGs are provided for manual UI testing only.
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rewrite_runner(src, boundary, folder, v01=False):
    marker = 'source "$(dirname -- "${BASH_SOURCE[0]}")/gallery_paths.sh"'
    if marker in src:
        return src
    start = src.index('cd /d/BVT-Studio')
    end = src.index(boundary, start)
    result = src[:start] + marker + '\nOUT="${BVT_OUTPUT_DIR:-$REPO/qa_renders/' + folder + '}"\n' + src[end:]
    if v01:
        if "--repo 'D:/BVT-Studio'" not in result:
            raise ValueError('v01 --repo anchor missing')
        result = result.replace("--repo 'D:/BVT-Studio'", '--repo "$REPO"', 1)
    return result


def main():
    if (Path(__file__).resolve().parents[1] / 'examples/freezer_planogram/configs/presets/single_glass').is_dir():
        raise SystemExit('Examples already organized; run scripts/validate_examples.py instead')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=Path.cwd())
    ap.add_argument('--photo', type=Path, help='Original tested PNG; required on first setup')
    ap.add_argument('--copy-gallery-assets', action='store_true', help='Copy optional masks and maps from existing calibrated gallery')
    a = ap.parse_args()
    root = a.repo.resolve()
    if not (root / 'bvt_studio/__init__.py').is_file():
        ap.error('Not a BVT Studio repo: ' + str(root))
    ex = root / 'examples/freezer_planogram'
    dest = ex / 'images' / IMAGE
    photo_path = a.photo.resolve() if a.photo else dest
    data = photo_path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', data[16:24]) != (1672, 941):
        raise ValueError('Expected PNG with dimensions 1672x941')
    if digest(data) != EXPECTED_SHA:
        raise ValueError('Photo SHA-256 differs from tested v0.2.1 source; do not substitute another image with these masks')
    copies = {dest: data}
    for name in CONFIGS:
        p = root / 'configs' / name
        content = p.read_bytes()
        json.loads(content)
        target = ex / 'configs' / name
        # Preserve user edits to example configurations on subsequent runs.
        if not target.exists():
            copies[target] = content
    if a.copy_gallery_assets:
        run = root / 'qa_renders/effects_gallery_v021/10_combined_water_optics'
        manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('source_sha256') != EXPECTED_SHA:
            raise ValueError('Gallery assets originate from a different source')
        rects = json.loads((root / 'configs' / CONFIGS[0]).read_text(encoding='utf-8'))
        if manifest.get('rects') != rects.get('glass_rectangles'):
            raise ValueError('Gallery rectangles differ from canonical example rectangles')
        for i in range(1, 5):
            files = [Path(f'masks/mask_glass_{i:03}.png')]
            files += [Path(f'maps/Glass_p_{i:03}/{kind}.png') for kind in ('alpha','height','normal')]
            for rel in files:
                copies[ex / rel] = (run / rel).read_bytes()
    # Never overwrite hand-edited examples or other independent assets.
    for path, content in copies.items():
        if path.exists() and path.read_bytes() != content:
            raise ValueError('Refusing to overwrite existing file: ' + str(path))
    changes = {}
    specs = (
        ('run_bvt_glass_gallery.sh', '\n[ -f "$PHOTO" ]', 'effects_gallery_v01', True),
        ('run_bvt_glass_gallery_v02.sh', '\n[[ -f "$PHOTO" ]]', 'effects_gallery_v02', False),
        ('run_bvt_water_qa_v021.sh', '\n[[ -f "$BLENDER"', 'effects_gallery_v021', False),
    )
    for name, boundary, folder, v01 in specs:
        p = root / 'scripts' / name
        src = p.read_text(encoding='utf-8')
        result = rewrite_runner(src, boundary, folder, v01)
        # Preserve explicit original checks, and add Blender check for v02.
        if v01 is False and folder == 'effects_gallery_v02' and '[[ -f "$BLENDER" ]]' not in result:
            result = result.replace('\n[[ -f "$PHOTO" ]]', '\n[[ -f "$BLENDER" ]] || { echo "ERROR: set BVT_BLENDER"; exit 1; }\n[[ -f "$PHOTO" ]]', 1)
        if result != src:
            changes[p] = result
    gui = root / 'scripts/blender_gallery_v021_gui_smoke.py'
    src = gui.read_text(encoding='utf-8')
    if 'BVT_EXAMPLE_DIR' not in src:
        before = "config=Path('D:/BVT-Studio/configs/scene_four_glasses_v02.json')"
        after = "repo=Path(os.environ.get('BVT_REPO_ROOT', str(source_file.parents[3])))\n    example=Path(os.environ.get('BVT_EXAMPLE_DIR', str(repo/'examples/freezer_planogram')))\n    config=example/'configs/scene_four_glasses_v02.json'"
        old_out = "output=Path('D:/BVT-Studio/qa_renders/effects_gallery_v021/ui_gui_smoke_report.json')"
        if src.count(before)!=1 or src.count(old_out)!=1 or src.count('import json\n')!=1:
            raise ValueError('GUI script differs from expected v0.2.1; review manually')
        src = src.replace('import json\n', 'import json\nimport os\n', 1).replace(before, after, 1)
        src = src.replace(old_out, "output=source_file.parents[1]/'ui_gui_smoke_report.json'", 1)
        ast.parse(src)
        changes[gui] = src
    for path, content in ((root/'scripts/gallery_paths.sh', COMMON),
                          (root/'examples/README.md', ROOT_README),
                          (ex/'README.md', SCENE_README),
                          (root/'examples/.gitignore', 'local/\n**/generated/\n')):
        if path.exists() and path.read_text(encoding='utf-8') != content:
            raise ValueError('Refusing to overwrite independently edited file: ' + str(path))
        if not path.exists():
            changes[path] = content
    # Keep historical docs coherent with the new location; old installer steps remain historical.
    for name in ('BVT_GLASS_EFFECT_GALLERY_README.md', 'GLASS_GALLERY_V02.md', 'WATER_QA_CALIBRATION_V021.md'):
        p = root/'docs'/name
        if not p.is_file():
            continue
        src = p.read_text(encoding='utf-8')
        note = '\n\n> Current example inputs: `examples/freezer_planogram/`. See `examples/README.md`; older installation and absolute path examples below describe the historical patch.\n'
        if 'Current example inputs:' not in src:
            first, sep, rest = src.partition('\n')
            changes[p] = first + note + rest if sep else src + note
    # All validation completed; no changes have been made until this point.
    for path, content in copies.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    for path, content in changes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    for folder in ('masks','maps','labels','scenes'):
        p = ex / folder
        p.mkdir(parents=True, exist_ok=True)
        if not any(p.iterdir()):
            (p/'.gitkeep').touch()
    print('EXAMPLES_SETUP=OK')
    print('SOURCE_SHA256='+digest(data))
    print('EXAMPLE_DIR='+str(ex))
    print('GALLERY_ASSETS_PRESENT='+str(all((ex / f'masks/mask_glass_{i:03}.png').is_file() for i in range(1,5)) and all((ex / f'maps/Glass_p_{i:03}/{kind}.png').is_file() for i in range(1,5) for kind in ('alpha','height','normal'))))
    print('REVIEW_GIT_DIFF_AND_RUN_BLENDER_BEFORE_COMMIT')

if __name__ == '__main__':
    main()
