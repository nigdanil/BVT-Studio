"""Test actual Blender renders, source preservation, artifacts and packed persistence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bvt_studio
from bvt_studio.common import get_source,image_from_mesh
from bvt_studio.glass import scene_glass
from bvt_studio.glass_material_blender import source_nodes,rebuild_materials,image_bytes,BAKE_KEY,PROFILE_KEY
from bvt_studio.glass_material_builtin import builtin_profile
from bvt_studio.glass_material_config import MATERIAL_IDS
from bvt_studio.glass_material_png import decode_png
from bvt_studio.glass_v02_ui import parse_scene_config,apply_scene_config
from bvt_studio.glass_realism import source_for_glass

def check(x,msg):
    if not x: raise RuntimeError(msg)

def snap(scene):
    return {o.name:{'matrix':[[float(x) for x in row] for row in o.matrix_world], 'verts':[tuple(v.co) for v in o.data.vertices] if o.type=='MESH' else None} for o in scene.objects}

def metrics(a,b):
    check(a.shape==b.shape,'Render shape changed'); d=np.max(np.abs(a.astype(np.int16)-b.astype(np.int16)),axis=2)
    return {'max_rgb':int(d.max()),'changed_gt4':int((d>4).sum())}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--blend',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=a.output_dir.resolve();src=a.blend.resolve()
    check(src.is_file() and not out.exists() and not src.is_relative_to(out),'Input required; choose new output directory');out.mkdir(parents=True)
    if not hasattr(bpy.types.Scene,'bvt_studio'): bvt_studio.register()
    bpy.ops.wm.open_mainfile(filepath=str(src));
    bpy.context.view_layer.update()
    scene=bpy.context.scene; check(hasattr(bpy.types.Scene,'bvt_material_choice_v01'),'Material UI not registered')
    source=get_source(scene); original=image_from_mesh(source); original_hash=hashlib.sha256(image_bytes(original)).hexdigest(); glasses=scene_glass(scene);check(len(glasses)>=2 and all(g.get('bvt_artifact_preset')=='QA_TRANSPARENT' for g in glasses),'Use Step 1 00_clean scene')
    check(not source.get(BAKE_KEY),'Expected clean source');g=glasses[0]; other=glasses[1]; target_name=g.name; before=snap(scene)
    def render(name):
        scene=bpy.context.scene; scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.image_settings.color_depth='8';path=out/(name+'.png');scene.render.filepath=str(path);bpy.ops.render.render(write_still=True);return decode_png(path.read_bytes())
    def assign(obj,name,seed=72):
        scene=bpy.context.scene;scene.bvt_studio.artifact_target_glass=obj;scene.bvt_material_choice_v01=name;scene.bvt_material_seed_v01=seed
        check(bpy.ops.bvt_studio.apply_glass_material_v01()=={'FINISHED'},'Apply failed: '+name)
        check(hashlib.sha256(image_bytes(image_from_mesh(get_source(scene)))).hexdigest()==original_hash,'Original changed')
        check(snap(scene)==before,'Geometry changed')
    base=render('00_legacy'); rows=[]; material_only=None
    for name in MATERIAL_IDS:
        assign(g,name); img=render(name); m=metrics(base,img)
        if name=='clear_glass': check(m['max_rgb']==0,'Clear glass must not change pixels')
        else: check(m['changed_gt4']>0,'No visible material: '+name)
        if name!='clear_glass':
            state=json.loads(source[BAKE_KEY]);rect=state['panes'][0]['rect'];x0,y0,x1,y1=rect;h,w=base.shape[:2]
            # Existing camera fills with slight crop; allow 4px guard at image edges.
            guard=np.ones((h,w),bool);guard[max(0,y0-4):min(h,y1+4),max(0,x0-4):min(w,x1+4)]=False
            d=np.max(np.abs(base.astype(np.int16)-img.astype(np.int16)),axis=2);check(not np.any(d[guard]>4),'Material leakage beyond 4 px camera guard: '+name)
        else: check(source_nodes(source)[2] is None,'Clear must not introduce bake')
        rows.append({'material':name,**m});print('MATERIAL_RENDER=PASS '+name+' '+str(m))
    assign(g,'frosted_glass'); material_only=render('material_only')
    scene.bvt_material_json_v01=str(ROOT/'configs/glass_materials/frosted_glass.json')
    check(bpy.ops.bvt_studio.import_glass_material_v01()=={'FINISHED'},'Material JSON import failed')
    check(metrics(material_only,render('material_json'))['max_rgb']==0,'JSON and built-in differ')
    assign(other,'tinted_glass');both=render('two_independent_materials'); rect=json.loads(source[BAKE_KEY])['panes'][0]['rect'];x0,y0,x1,y1=rect;check(metrics(material_only[y0:y1,x0:x1],both[y0:y1,x0:x1])['max_rgb']==0,'Other pane modified first pane')
    assign(other,'clear_glass');check(metrics(material_only,render('other_clear'))['max_rgb']==0,'Clear did not restore other pane')
    cfg=ROOT/'examples/freezer_planogram/configs/presets/single_glass/water/07_macro_droplets_only.json'
    prepared=parse_scene_config(cfg);check(set(prepared)=={target_name},'Expected first-pane config');apply_scene_config(bpy.context.scene,prepared)
    check(source_for_glass(g)[1]==source_nodes(source)[1].image,'Artifact engine does not sample baked source')
    check(any(n.type=='TEX_IMAGE' and n.image==source_nodes(source)[1].image for n in g.active_material.node_tree.nodes),'Artifact graph has no baked source texture')
    both=render('material_plus_macro');m=metrics(material_only,both);check(m['changed_gt4']>0,'Macro did not change material-only render')
    artifact_before={k:g.get(k) for k in g.keys() if k.startswith(('bvt_artifact_','bvt_water_','bvt_droplet_','bvt_optical_'))}
    assign(g,'tinted_glass');check(all(g.get(k)==v for k,v in artifact_before.items()),'Material assignment changed artifact parameters');combined=render('tinted_plus_macro')
    check(source_for_glass(g)[1]==source_nodes(source)[1].image,'Reassignment did not refresh artifact image')
    check(any(n.type=='TEX_IMAGE' and n.image==source_nodes(source)[1].image for n in g.active_material.node_tree.nodes),'Existing artifact graph was not updated')
    path=out/'combined_scene.blend';bpy.context.preferences.filepaths.save_version=0
    bpy.context.scene.render.filepath='//render.png';bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=True,relative_remap=False)
    bpy.ops.wm.open_mainfile(filepath=str(path));scene=bpy.context.scene;source=get_source(scene);g=scene.objects[target_name];eff=source_nodes(source)[1].image
    check(eff.packed_file and eff.filepath.startswith('//') and all(p.filepath.startswith('//') for p in eff.packed_files),'Derived PNG not portable')
    check(hashlib.sha256(image_bytes(image_from_mesh(source))).hexdigest()==original_hash,'Original lost after reload');check(source_for_glass(g)[1]==eff,'Baked source not restored')
    check(metrics(combined,render('reopened'))['max_rgb']==0,'Rerender after reopen differs')
    # Return material to clear without removing the artifact, compare to same artifact on original.
    assign(g,'clear_glass');check(source_nodes(source)[2] is None and image_from_mesh(source)==source_nodes(source)[1].image,'Original not restored');check(all(g.get(k)==v for k,v in artifact_before.items()),'Clear changed artifact parameters');render('clear_plus_macro')
    report={'status':'PASS','materials':rows,'combined_delta':m,'original_sha256':original_hash,'geometry_unchanged':True,'reopen_rgb_equal':True,'clear_restores_original':True,'warning':'2.5D experiment; not measured glass optics or YOLO accuracy validation'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8');print('GLASS_MATERIAL_BLENDER_SMOKE=PASS')
if __name__=='__main__':main()
