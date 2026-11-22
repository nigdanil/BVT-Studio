"""Reopen Blender atlas scene and verify both map sets survive independently."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from bvt_studio.droplet_maps import MODE_KEY, packed_maps_for
from bvt_studio.glass_mask import MASK_ENABLED_KEY, mask_image_for

argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--blend',required=True)
args = parser.parse_args(argv)
source = Path(args.blend).resolve()
if not source.is_file():
    raise AssertionError('Missing atlas Blender scene: ' + str(source))
bpy.ops.wm.open_mainfile(filepath=str(source))
obj = next((o for o in bpy.data.objects
            if o.get('bvt_role') == 'glass_overlay' and o.get(MODE_KEY) == 'REALISTIC_ATLAS'),None)
if obj is None:
    raise AssertionError('No realistic atlas glass in saved Blender scene')
for mode in ('REALISTIC_ATLAS','PHOTO_MAPS'):
    data = packed_maps_for(obj, mode=mode)
    if set(data) != {'alpha','height','normal'} or not all(im.packed_file for im in data.values()):
        raise AssertionError('Packed maps missing after reopen: ' + mode)
    # The inactive bank must survive a future Save/Open too; an image may be
    # packed and still get dropped if it has neither a user nor a fake user.
    for im in data.values():
        if not im.use_fake_user:
            raise AssertionError('Missing Fake User for saved map: ' + mode + ' / ' + im.name)
for key in ('bvt_atlas_generation_seed','bvt_atlas_resolution',
            'bvt_atlas_density','bvt_atlas_streaks'):
    if key not in obj:
        raise AssertionError('Atlas generation provenance missing: ' + key)
if obj.get(MASK_ENABLED_KEY):
    image = mask_image_for(obj)
    if not image or not image.packed_file:
        raise AssertionError('Atlas Precision Mask not packed')
if not obj.active_material or not obj.active_material.use_nodes:
    raise AssertionError('Atlas material lost')
shader = obj.active_material.node_tree.nodes
if not shader.get('BVT_Photo_Droplet_Alpha') or not shader.get('BVT_Precision_Final_Mask_Gate'):
    raise AssertionError('Atlas or mask shader not restored')
print('BVT REALISTIC ATLAS PERSISTENCE: OK — photo maps, generated maps, precision mask and shader')
