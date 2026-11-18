"""Reopen a saved alpha.5 photo maps .blend and verify its packed source maps.

Run from repo root with Blender --background --factory-startup --python this.py --
  --blend "D:/BVT-Studio/qa_renders/photo_droplets_step1/photo_droplets_smoke.blend"
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from bvt_studio.droplet_maps import packed_maps_for, MODE_KEY
from bvt_studio.glass_mask import MASK_ENABLED_KEY, mask_image_for

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--blend', required=True)
opts = parser.parse_args(argv)
file = Path(opts.blend).resolve()
if not file.is_file():
    raise AssertionError('Saved Blender scene not found: ' + str(file))
bpy.ops.wm.open_mainfile(filepath=str(file))
obj = next((o for o in bpy.data.objects
            if o.get('bvt_role') == 'glass_overlay' and o.get(MODE_KEY) == 'PHOTO_MAPS'), None)
if obj is None:
    raise AssertionError('No photo-map Glass Plane in reopened .blend')
images = packed_maps_for(obj)
if set(images) != {'alpha', 'height', 'normal'}:
    raise AssertionError('Not all three photo maps were restored')
if not all(i.packed_file is not None for i in images.values()):
    raise AssertionError('At least one photographic droplet map was not packed')
if not obj.active_material or not obj.active_material.use_nodes:
    raise AssertionError('Glass material is not saved')
nodes = obj.active_material.node_tree.nodes
if not nodes.get('BVT_Photo_Droplet_Alpha') or not nodes.get('BVT_Photo_Droplet_Normal'):
    raise AssertionError('Saved material does not use photo maps')
if obj.get(MASK_ENABLED_KEY, False):
    mask = mask_image_for(obj)
    if mask is None or mask.packed_file is None:
        raise AssertionError('Precision PNG mask did not persist')
print('BVT PHOTO DROPLETS PERSISTENCE: OK — packed maps, material and mask restored')
