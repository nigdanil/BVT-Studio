"""Validate, relocate packed resource paths, save, and reopen a generated release scene."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bvt_studio.common import image_from_mesh
from bvt_studio.droplet_maps import packed_maps_for
from bvt_studio.glass_mask import MASK_PATH_KEY, mask_image_for
from bvt_studio.hybrid_condensation import HYBRID_PRESETS, ATLAS_SIZE

def check(ok,msg):
    if not ok: raise RuntimeError(msg)

def relocate_packed(image, relative):
    # Set both layers of Blender path metadata; do not reload external files.
    check(bool(image.packed_file), 'Missing packed payload: '+image.name)
    before=hashlib.sha256(bytes(image.packed_file.data)).hexdigest()
    image.filepath_raw=relative
    for packed in image.packed_files:
        packed.filepath=relative
    check(hashlib.sha256(bytes(image.packed_file.data)).hexdigest()==before,
          'Packed payload changed: '+image.name)


def inspect(scene, manifest, relocate=False):
    sources=[o for o in scene.objects if o.get('bvt_role')=='planogram_image']
    check(len(sources)==1,'Expected a single source object')
    image=image_from_mesh(sources[0]); check(image is not None and image.packed_file,'Source not packed')
    check(hashlib.sha256(bytes(image.packed_file.data)).hexdigest()==manifest['source_sha256'],'Packed source hash mismatch')
    if relocate: relocate_packed(image, '//../source.png')
    glasses=sorted((o for o in scene.objects if o.get('bvt_role')=='glass_overlay'),key=lambda o:o.name)
    check([o.name for o in glasses]==[p['name'] for p in manifest['panes']],'Pane list mismatch')
    uids=[str(g.get('bvt_glass_uid') or '') for g in glasses]
    check(all(uids) and len(set(uids))==len(uids),'Invalid glass UIDs')
    check(tuple(image.size)==(scene.render.resolution_x,scene.render.resolution_y),'Source/render resolution mismatch')
    check(scene.get('bvt_gallery_v02_variant')==manifest['variant'],'Variant mismatch')
    check(scene.get('bvt_gallery_v02_source_sha256')==manifest['source_sha256'],'Source metadata mismatch')
    record=[]; ids=set(); packed={image.name}
    for i,(g,p) in enumerate(zip(glasses,manifest['panes']),1):
        check(bool(g.get('bvt_glass_mask_enabled')),g.name+': mask disabled')
        mask=mask_image_for(g); check(mask is not None and mask.packed_file,g.name+': mask not packed')
        check(mask.use_fake_user,g.name+': mask persistence flag missing')
        rel=f'//masks/mask_glass_{i:03}.png'
        if relocate: relocate_packed(mask, rel); g[MASK_PATH_KEY]=rel
        packed.add(mask.name)
        check(g.get('bvt_artifact_seed')==p['seed'],g.name+': seed mismatch')
        row={'name':g.name,'mask_packed':True,'water_kind':p['water_kind']}
        if p['water_kind']:
            check(g.get('bvt_water_v02_kind')==p['water_kind'],g.name+': kind mismatch')
            events=json.loads(g.get('bvt_water_v02_event_json','null'))
            check(isinstance(events,list) and all(sum(e['type']==k for e in events)==v for k,v in p['events_generated'].items()),g.name+': events mismatch')
            bank=packed_maps_for(g,mode='REALISTIC_ATLAS')
            check(set(bank)=={'alpha','height','normal'},g.name+': map bank incomplete')
            for channel,im in bank.items():
                check(im.packed_file and im.use_fake_user,g.name+': map not packed')
                check(im.name not in ids,g.name+': shared atlas')
                ids.add(im.name); packed.add(im.name)
                if relocate: relocate_packed(im, f'//maps/{g.name}/{channel}.png')
            row['events']=len(events)
        else:
            check(not g.get('bvt_water_v02_kind'),g.name+': unexpected water atlas')
            if p['preset'] in HYBRID_PRESETS:
                check(g.active_material and g.active_material.node_tree,g.name+': missing material')
                node=g.active_material.node_tree.nodes.get('BVT_Hybrid_Atlas')
                im=node.image if node else None
                check(im is not None and im.packed_file,g.name+': procedural atlas not packed')
                check(tuple(im.size)==(ATLAS_SIZE,ATLAS_SIZE),g.name+': atlas size mismatch')
                check(im.alpha_mode=='CHANNEL_PACKED' and im.colorspace_settings.name=='Non-Color',g.name+': atlas channel settings')
                data=bytes(im.packed_file.data)
                check(data[:4]==b'\x76\x2f\x31\x01',g.name+': expected EXR atlas')
                check(im.name not in ids,g.name+': shared procedural atlas')
                ids.add(im.name); packed.add(im.name)
                if relocate: relocate_packed(im, f'//atlases/{g.name}.exr')
                row['procedural_atlas_sha256']=hashlib.sha256(data).hexdigest()
        record.append(row)
    check(scene.camera is not None,'Missing camera')
    check(scene.render.filepath=='//render.png','Nonportable render filepath')
    # Check any image directly referenced by the used source/glass materials.
    for o in sources+glasses:
        for mat in o.data.materials:
            if mat and mat.node_tree:
                for node in mat.node_tree.nodes:
                    im=getattr(node,'image',None)
                    if im is not None and im.source=='FILE':
                        check(im.packed_file,f'Unpacked material image: {im.name}')
    if not relocate:
        for name in packed:
            im=bpy.data.images[name]
            check(im.filepath.startswith('//'),f'Nonportable image path: {name}')
            check(all(p.filepath.startswith('//') for p in im.packed_files),f'Nonportable packed path: {name}')
    return record

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--blend',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]); m=json.loads(a.manifest.read_text(encoding='utf-8'))
    path=a.blend.resolve(); bpy.ops.wm.open_mainfile(filepath=str(path)); before=inspect(bpy.context.scene,m,True)
    # Avoid .blend1 backup files and path remapping back to build-machine locations.
    bpy.context.preferences.filepaths.save_version=0
    check(bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=True,relative_remap=False)=={'FINISHED'},'Save failed')
    bpy.ops.wm.open_mainfile(filepath=str(path)); records=inspect(bpy.context.scene,m,False)
    check(before==records,'Packed atlas or pane record changed on reopen')
    a.report.write_text(json.dumps({'status':'PASS','variant':m['variant'],'blender':bpy.app.version_string,'panes':records},indent=2),encoding='utf-8')
    print('RELEASE_REOPEN=PASS '+m['variant'])
if __name__=='__main__':main()
