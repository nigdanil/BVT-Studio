"""Open a saved step4 QA .blend and assert all four PNG masks are still packed.

Blender:
    blender --background --factory-startup --python-exit-code 1 \
      --python scripts/blender_precision_mask_persistence_smoke.py -- \
      --blend 'D:/BVT-Studio/qa_renders/precision_step4/precision_mask_qa.blend'
"""
import argparse
import sys
from pathlib import Path
import bpy

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--blend', required=True)
opts = parser.parse_args(args)
blend = Path(opts.blend).resolve()
if not blend.is_file():
    raise RuntimeError(f'QA blend missing: {blend}')
bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
glasses = sorted((obj for obj in bpy.context.scene.objects
                  if obj.get('bvt_role') == 'glass_overlay'), key=lambda o: o.name)
if len(glasses) != 4:
    raise AssertionError('Expected four Glass_p_* objects after reopen')
image_names = []
for obj in glasses:
    if not obj.get('bvt_glass_mask_enabled', False):
        raise AssertionError(obj.name + ': mask disabled after reopen')
    name = obj.get('bvt_glass_mask_image', '')
    image = bpy.data.images.get(name)
    if image is None or image.packed_file is None or min(image.size) < 2:
        raise AssertionError(obj.name + ': packed PNG mask unavailable after reopen')
    if obj.active_material is None or obj.active_material.node_tree.nodes.get('BVT_Precision_QA_Mask') is None:
        raise AssertionError(obj.name + ': mask shader disconnected after reopen')
    image_names.append(name)
if len(set(image_names)) != 4:
    raise AssertionError('Reopened glass masks are not independent')
print('BVT PRECISION MASK PERSISTENCE: OK — four packed masks, materials and object bindings')
