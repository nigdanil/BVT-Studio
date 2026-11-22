#!/usr/bin/env python3
"""Preview material-only appearance on a clean RGB PNG, without Blender."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
# Same lightweight package-import convention as the existing numerical tests.
# The addon's real __init__ needs bpy; this CLI only uses pure numerical modules.
if 'bvt_studio' not in sys.modules:
    pkg = types.ModuleType('bvt_studio')
    pkg.__path__ = [str(ROOT/'bvt_studio')]
    sys.modules['bvt_studio'] = pkg
from bvt_studio.glass_material_config import MATERIAL_IDS, load_library, require
from bvt_studio.glass_materials import render_materials
import numpy as np


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def safe_output(path):
    base = ROOT/'qa_renders'
    target = path if path.is_absolute() else ROOT/path
    require(not base.is_symlink() and target.absolute() == target.resolve(), 'Output must not traverse symlinks or aliases')
    require(target.resolve().is_relative_to(base.resolve()) and target.resolve() != base.resolve(), 'Output must be under qa_renders')
    require(not target.exists() and not target.is_symlink(), 'Output already exists; choose a new directory')
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True, help='Clean rendered RGB PNG (not an already augmented image)')
    p.add_argument('--rects-file', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--materials', choices=MATERIAL_IDS, nargs='+', default=list(MATERIAL_IDS))
    p.add_argument('--seed', type=int, default=72)
    a = p.parse_args()
    try:
        from PIL import Image
    except ImportError:
        p.error('Install Pillow: python -m pip install Pillow')
    require(len(a.materials)==len(set(a.materials)), 'Duplicate material requested')
    source = a.input.resolve(); rectfile = a.rects_file.resolve()
    out = safe_output(a.output_dir)
    require(source.is_file() and source.suffix.lower()=='.png', 'Input must be a PNG file')
    library_dir = ROOT/'configs/glass_materials'
    library = load_library(library_dir)
    paths = [source, rectfile, *[library_dir/(m+'.json') for m in a.materials], Path(__file__), ROOT/'bvt_studio/glass_materials.py', ROOT/'bvt_studio/glass_material_config.py']
    hashes = {path:sha(path) for path in paths}
    with Image.open(source) as img:
        require(img.format=='PNG' and img.mode=='RGB' and not img.info.get('icc_profile'), 'Expected RGB PNG without embedded ICC profile; normalize deliberately first')
        rgb = np.array(img, dtype=np.uint8)
    h,w = rgb.shape[:2]
    spec = json.loads(rectfile.read_text(encoding='utf-8-sig'))
    require(spec.get('reference_size')==[w,h], 'Geometry must match render dimensions')
    rects = spec.get('glass_rectangles')
    require(isinstance(rects,list) and bool(rects), 'Missing glass rectangles')
    # Preflight all geometry and seeds using the exact identity control.
    assignments = [dict(rect=r,material=library['clear_glass'],seed=a.seed+i) for i,r in enumerate(rects)]
    require(np.array_equal(render_materials(rgb,assignments),rgb), 'Identity control failed')
    mask = np.zeros((h,w),dtype=bool)
    for x0,y0,x1,y1 in rects:
        mask[y0:y1,x0:x1]=True
    require(not source.is_relative_to(out.resolve()) and not rectfile.is_relative_to(out.resolve()), 'Input/output overlap')
    out.mkdir(parents=True,exist_ok=False)
    rows = []
    for key in a.materials:
        assignments = [dict(rect=r,material=library[key],seed=a.seed+i) for i,r in enumerate(rects)]
        result=render_materials(rgb,assignments)
        repeat=render_materials(rgb,assignments)
        delta=np.max(np.abs(result.astype(np.int16)-rgb.astype(np.int16)),axis=2)
        require(np.array_equal(result,repeat), 'Non-deterministic render: '+key)
        require(not np.any(delta[~mask]), 'Outside pane change: '+key)
        require(key!='clear_glass' or not np.any(delta), 'Clear profile must be exact RGB identity')
        path=out/(key+'.png'); Image.fromarray(result).save(path)
        with Image.open(path) as saved:
            require(np.array_equal(np.array(saved),result),'PNG roundtrip differs: '+key)
        rows.append(dict(id=key,output=path.name,output_sha256=sha(path),profile_sha256=hashes[library_dir/(key+'.json')],
                         changed_ratio_inside_gt4=float(np.mean(delta[mask]>4)),
                         changed_pixels_outside=int(np.count_nonzero(delta[~mask])),
                         max_abs_rgb=int(delta.max()),repeat_exact=True,
                         informative=bool(np.any(delta[mask]>4)) if key!='clear_glass' else None))
        print(f'MATERIAL_PREVIEW=PASS {key}; CHANGED_GT4={rows[-1]["changed_ratio_inside_gt4"]:.6f}')
    require(all(sha(path)==digest for path,digest in hashes.items()), 'An input changed during preview')
    report=dict(schema='bvt.glass-material-preview.v01',status='PASS',mode='IMAGE_SPACE_REFERENCE_ONLY',
                source_sha256=hashes[source],geometry_sha256=hashes[rectfile],size=[w,h],rectangles=rects,
                seed_base=a.seed,pane_seeds=[a.seed+i for i in range(len(rects))],
                numpy_version=np.__version__,engine_sha256={path.name:hashes[path] for path in paths[-3:]},
                mask_provenance='rectangular_geometry_not_ground_truth',labels_status='NOT_EXPORTED',
                warning='Uncalibrated appearance preview; not physical glass, Blender shader output, paired artifact QA, or detector evidence.',materials=rows)
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('GLASS_MATERIAL_PREVIEW=PASS')
    print('REPORT='+str(out/'report.json'))

if __name__=='__main__':
    main()
