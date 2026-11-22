"""Real Blender smoke: verify float atlas packing, channel data, and regeneration."""
import hashlib
from pathlib import Path
import sys
import tempfile
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bvt_studio.hybrid_condensation import ensure_atlas, make_condensation_atlas

def pixels(im):
    data=np.empty(len(im.pixels),dtype=np.float32)
    im.pixels.foreach_get(data)
    return data

def check(ok,msg):
    if not ok: raise RuntimeError(msg)

def validate(im,seed,coverage):
    check(im.packed_file is not None,'Atlas unpacked')
    check(im.alpha_mode=='CHANNEL_PACKED','Alpha mode changed')
    check(im.colorspace_settings.name=='Non-Color','Color space changed')
    expected=make_condensation_atlas(seed,coverage).ravel()
    actual=pixels(im)
    delta=float(np.max(np.abs(expected-actual)))
    print(f'ATLAS_PIXEL_MAX_DELTA={delta:.9f}',flush=True)
    check(delta<=0.002,'Atlas channel data changed beyond float storage tolerance')
    return hashlib.sha256(bytes(im.packed_file.data)).hexdigest(), actual

def main():
    with tempfile.TemporaryDirectory(prefix='bvt_hybrid_atlas_test_') as tmp:
        obj=bpy.data.objects.new('AtlasSmoke',None)
        bpy.context.scene.collection.objects.link(obj)
        obj['bvt_glass_uid']='atlas_smoke'
        obj['bvt_artifact_seed']=72
        obj['bvt_artifact_coverage']=.32
        im=ensure_atlas(obj)
        im.use_fake_user=True # stand-alone test has no material texture user
        h1,p1=validate(im,72,.32)
        name=im.name
        dest=Path(tmp)/'atlas.blend'
        bpy.context.preferences.filepaths.save_version=0
        check(bpy.ops.wm.save_as_mainfile(filepath=str(dest),relative_remap=False)=={'FINISHED'},'Save failed')
        bpy.ops.wm.open_mainfile(filepath=str(dest))
        im=bpy.data.images[name]
        h2,p2=validate(im,72,.32)
        check(h1==h2,'Packed bytes changed across reopen')
        check(float(np.max(np.abs(p1-p2)))<=.002,'Reopened buffer changed')
        obj=bpy.data.objects['AtlasSmoke']
        obj['bvt_artifact_coverage']=.65
        im=ensure_atlas(obj)
        h3,_=validate(im,72,.65)
        check(h3!=h2,'Updated parameters did not change packed bytes')
        check(bpy.ops.wm.save_as_mainfile(filepath=str(dest),relative_remap=False)=={'FINISHED'},'Resave failed')
        bpy.ops.wm.open_mainfile(filepath=str(dest))
        h4,_=validate(bpy.data.images[name],72,.65)
        check(h3==h4,'Updated packed bytes changed across reopen')
    print('HYBRID_ATLAS_PERSISTENCE=PASS')

if __name__=='__main__': main()
