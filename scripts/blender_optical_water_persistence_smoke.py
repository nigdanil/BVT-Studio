"""Reopen optical-water scene and check both banks and effect shader persist."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from bvt_studio.droplet_maps import packed_maps_for
from bvt_studio.glass_mask import mask_image_for
from bvt_studio.optical_water import optical_enabled, LENS_KEY, EDGE_KEY, GLINT_KEY, MICRO_KEY

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument('--blend', required=True)
a = p.parse_args(argv)
source = Path(a.blend).resolve()
if not source.is_file():
    raise AssertionError('Missing saved Optical Water scene: ' + str(source))
bpy.ops.wm.open_mainfile(filepath=str(source))
obj = next((o for o in bpy.data.objects if o.get('bvt_role') == 'glass_overlay'
            and optical_enabled(o)), None)
if obj is None:
    raise AssertionError('Optical atlas glass missing after reopening .blend')
for mode in ('PHOTO_MAPS', 'REALISTIC_ATLAS'):
    for kind, image in packed_maps_for(obj, mode).items():
        if not (image.packed_file and image.use_fake_user):
            raise AssertionError(f'{mode} {kind} map not packed/persistent')
if obj.get('bvt_glass_mask_enabled'):
    if not mask_image_for(obj).packed_file:
        raise AssertionError('Precision mask not packed')
for prop in (LENS_KEY, EDGE_KEY, GLINT_KEY, MICRO_KEY):
    if prop not in obj:
        raise AssertionError('Optical setting was lost: ' + prop)
if not obj.active_material or not obj.active_material.node_tree:
    raise AssertionError('Optical material missing')
nodes = obj.active_material.node_tree.nodes
for name in ('BVT_Optical_Contact_Glass_Mask','BVT_Optical_Refraction_Gain',
             'BVT_Optical_Highlight_Safe_Clamp','BVT_Precision_Final_Mask_Gate'):
    if not nodes.get(name):
        raise AssertionError('Expected optical shader node missing: ' + name)
print('BVT OPTICAL WATER PERSISTENCE: OK — optical shader, both packed banks, precision mask')
