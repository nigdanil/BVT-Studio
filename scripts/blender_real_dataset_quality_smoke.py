"""Blender integration smoke using GENERATED fixture (not a real retail dataset).

 blender --background --factory-startup --python-exit-code 1 \\
   --python scripts/blender_real_dataset_quality_smoke.py -- --output-dir DIR
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.blender_real_dataset_quality import main

args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', required=True)
opts = parser.parse_args(args)
root = Path(opts.output_dir).resolve()
for part in ('clean','augmented','labels','masks','qa'):
    (root/part).mkdir(parents=True,exist_ok=True)

h=w=96
# Synthetic textured "label" with contrast edges to test detail retention.
xs, ys = np.meshgrid(np.arange(w),np.arange(h))
checker = ((xs//4+ys//4)%2).astype(np.float32)
clean = np.empty((h,w,3),dtype=np.float32)
clean[:] = .28 + checker[:,:,None]*.26
aug = clean.copy()
aug[28:43, 33:49] += .055
mask = np.zeros((h,w,3),dtype=np.float32)
mask[8:88,8:88] = 1.


def save_png(filepath, rgb):
    rgba = np.ones((h,w,4),dtype=np.float32)
    rgba[:,:,:3] = rgb
    im = bpy.data.images.new('BVT_RealDataset_Smoke',width=w,height=h,alpha=True)
    try:
        im.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
        im.filepath_raw=str(filepath)
        im.file_format='PNG'
        im.save()
    finally:
        bpy.data.images.remove(im)


save_png(root/'clean'/'sample.png',clean)
save_png(root/'augmented'/'sample.png',aug)
save_png(root/'masks'/'sample.png',mask)
label = root/'labels'/'sample.txt'
label.write_text('0 0.5 0.5 0.65 0.65\n',encoding='utf-8')
original_hash=hashlib.sha256(label.read_bytes()).hexdigest()

result=main(['--clean-dir',str(root/'clean'),
             '--augmented-dir',str(root/'augmented'),
             '--labels-dir',str(root/'labels'),
             '--masks-dir',str(root/'masks'),
             '--output-dir',str(root/'qa'),
             '--profile','LIGHT','--strict'])
assert result['counts']['PASS'] == 1, result['counts']
assert result['counts']['ERROR'] == 0
assert len(result['samples'][0]['objects'])==1
assert hashlib.sha256(label.read_bytes()).hexdigest()==original_hash
assert (root/'qa'/'overlays'/'sample.png').is_file()
assert (root/'qa'/'accepted_manifest.json').is_file()

# Missing verified mask MUST be REVIEW; never silently accepted.
no_masks=main(['--clean-dir',str(root/'clean'),
               '--augmented-dir',str(root/'augmented'),
               '--labels-dir',str(root/'labels'),
               '--output-dir',str(root/'qa_without_masks'),
               '--profile','LIGHT','--max-overlays','0'])
assert no_masks['counts']['REVIEW'] == 1, no_masks['counts']
assert not json.loads((root/'qa_without_masks'/'accepted_manifest.json').read_text('utf-8'))['accepted']
print('BVT REAL DATASET QA SMOKE: OK — strict YOLO, per-SKU, mask fail-closed, input hashes')
