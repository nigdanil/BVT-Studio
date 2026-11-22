"""Check a saved BVT Gallery v0.2 .blend independently after reopening."""
import argparse
import sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--blend',required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
bpy.ops.wm.open_mainfile(filepath=str(Path(a.blend).resolve()))
from bvt_studio.droplet_maps import packed_maps_for
from bvt_studio.common import image_from_mesh
scene=bpy.context.scene
source=next((o for o in scene.objects if o.get('bvt_role')=='planogram_image'),None)
assert source is not None
assert image_from_mesh(source).packed_file, 'Source image not packed'
glasses=sorted((o for o in scene.objects if o.get('bvt_role')=='glass_overlay'),key=lambda x:x.name)
assert glasses, 'No glass objects'
assert len({str(o.get('bvt_glass_uid')) for o in glasses})==len(glasses),'Glass UIDs not unique'
for g in glasses:
    assert g.get('bvt_water_v02_kind'), g.name+': water kind missing'
    assert g.get('bvt_water_v02_event_json'),g.name+': events missing'
    assert all(im.packed_file and im.use_fake_user for im in packed_maps_for(g,mode='REALISTIC_ATLAS').values())
    if g.get('bvt_glass_mask_enabled'):
        assert bpy.data.images.get(g.get('bvt_glass_mask_image')).packed_file
print('BVT GALLERY v02 PERSISTENCE: OK — source, masks, atlas, UIDs, generated events')
