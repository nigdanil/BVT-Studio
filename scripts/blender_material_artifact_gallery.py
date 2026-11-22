"""Blender worker: isolated job state, paired controls, packed persistence."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import sys
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'scripts'))
import bvt_studio
from bvt_studio.common import get_source,image_from_mesh
from bvt_studio.glass import scene_glass
from bvt_studio.glass_mask import mask_image_for,MASK_PATH_KEY
from bvt_studio.glass_material_blender import (rebuild_materials,source_nodes,image_bytes,BAKE_KEY,PROFILE_KEY,SEED_KEY,_corners)
from bvt_studio.glass_material_geometry import pane_rect
from bvt_studio.glass_material_png import decode_png
from bvt_studio.glass_realism import image_uv_bounds,source_for_glass
from bvt_studio.glass_v02_ui import parse_scene_config,apply_scene_config
from bvt_studio.droplet_maps import packed_maps_for
from bvt_studio.hybrid_condensation import HYBRID_PRESETS
from bvt_material_artifact_gallery import SCHEMA,TARGET,need,sha,read_json,write_json
from bvt_matrix_resource_qa import packed_layout,validate_runtime_size,snapshot_delta,canonical_resource_path


def geometry(scene):
    bpy.context.view_layer.update()
    return {o.name: ([list(row) for row in o.matrix_world], [list(v.co) for v in o.data.vertices] if o.type=='MESH' else None) for o in scene.objects}


def digest(image):
    return hashlib.sha256(image_bytes(image)).hexdigest()


def render(path):
    s=bpy.context.scene
    s.render.image_settings.file_format='PNG'; s.render.image_settings.color_mode='RGB'; s.render.image_settings.color_depth='8'
    s.render.filepath=str(path)
    need(bpy.ops.render.render(write_still=True)=={'FINISHED'}, 'Render failed')
    return decode_png(path.read_bytes())


def stats(a,b,rect):
    need(a.shape==b.shape,'Render shape mismatch')
    d=np.max(np.abs(a.astype(np.int16)-b.astype(np.int16)),axis=2)
    x0,y0,x1,y1=rect; h,w=d.shape
    roi=d[y0:y1,x0:x1]; guard=np.ones((h,w),bool)
    # The example camera has a slight fill crop. A 4 px guard matches Step 3 smoke.
    guard[max(0,y0-4):min(h,y1+4),max(0,x0-4):min(w,x1+4)]=False
    return {'max_rgb':int(d.max()),'changed_gt4':int((d>4).sum()),
            'roi_changed_gt4':int((roi>4).sum()),'roi_pixels':int(roi.size),
            'roi_changed_pct':float(100*(roi>4).mean()),'outside_guard_gt4':int((d[guard]>4).sum())}


def resource_snapshot(scene,relocate=False,observed=None):
    """Inspect referenced source, derived layer, glass masks and atlas banks."""
    images={}; masks={}
    source=get_source(scene); glasses=scene_glass(scene)
    targets=[source,*glasses]
    def add(im):
        if im is None or im.source!='FILE': return
        need(bool(im.packed_file),'Unpacked image: '+im.name)
        images[im.name]=im
    for obj in targets:
        for slot in obj.material_slots:
            mat=slot.material
            if mat and mat.node_tree:
                for n in mat.node_tree.nodes:
                    if n.type=='TEX_IMAGE': add(n.image)
    for g in glasses:
        mask=mask_image_for(g); need(mask is not None and mask.packed_file, 'Missing mask: '+g.name)
        add(mask); masks[g.name]=mask
        if g.get('bvt_droplet_source_mode')=='REALISTIC_ATLAS':
            bank=packed_maps_for(g, mode='REALISTIC_ATLAS')
            need(set(bank)=={'alpha','height','normal'},'Incomplete water atlas: '+g.name)
            for im in bank.values(): add(im)
        elif g.get('bvt_artifact_preset') in HYBRID_PRESETS:
            node=g.active_material.node_tree.nodes.get('BVT_Hybrid_Atlas')
            need(node is not None and node.image is not None and node.image.packed_file,'Missing packed hybrid atlas: '+g.name)
            add(node.image)
    records={}
    for name,im in sorted(images.items()):
        raw=bytes(im.packed_file.data); h=hashlib.sha256(raw).hexdigest()
        ext,size=packed_layout(raw)
        runtime=list(im.size)
        if observed is not None:
            observed[name]={'runtime_size':runtime,'packed_size':size,'sha256':h,
                            'path':im.filepath,'packed_paths':[p.filepath for p in im.packed_files]}
        validate_runtime_size(runtime,size)
        need(len(im.packed_files)==1,'Expected single packed payload: '+name)
        rel='//resources/'+h+ext
        if relocate:
            im.filepath_raw=rel
            for p in im.packed_files: p.filepath=rel
            need(hashlib.sha256(bytes(im.packed_file.data)).hexdigest()==h,'Packed data changed')
        raw_paths=[p.filepath for p in im.packed_files]
        if observed is not None:
            observed[name]['comparison_path_raw']=im.filepath
            observed[name]['comparison_packed_paths_raw']=raw_paths
        path=canonical_resource_path(im.filepath,rel)
        paths=[canonical_resource_path(p,rel) for p in raw_paths]
        records[name]={'sha256':h,'path':path,'packed_paths':paths,'size':size}
    if relocate:
        for name,im in masks.items(): scene.objects[name][MASK_PATH_KEY]=im.filepath
    return records


def load_clean(path, plan):
    need(bpy.ops.wm.open_mainfile(filepath=str(path))=={'FINISHED'},'Open failed')
    bpy.context.view_layer.update(); s=bpy.context.scene; source=get_source(s)
    original=image_from_mesh(source); glasses=scene_glass(s)
    need(original is not None and original.packed_file and digest(original)==plan['source']['sha256'],'Wrong packed source')
    need(len(glasses)==4 and glasses[0].name==TARGET and all(g.get('bvt_artifact_preset')=='QA_TRANSPARENT' for g in glasses),'Use Step 1 00_clean four-pane scene')
    need(not source.get(BAKE_KEY) and all(not g.get(PROFILE_KEY) for g in glasses),'Input must not contain material assignments')
    need(s.camera is not None and s.render.resolution_percentage==100 and (s.render.resolution_x,s.render.resolution_y)==tuple(original.size),'Expected full-size camera render')
    need(not s.render.use_border,'Render border not supported')
    return s,source,glasses[0]


def index(out,rows):
    with (out/'summary.csv').open('w',encoding='utf-8',newline='') as f:
        keys=['id','material','effect','role','status','material_only_delta_pct','artifact_delta_pct','outside_guard_gt4','reopen_max_rgb']
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader()
        for r in rows: w.writerow({k:r[k] for k in keys})
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><title>BVT Material x Artifact Gallery</title><style>body{font:16px system-ui;margin:24px;background:#17191c;color:#eee}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px}article{background:#22262a;padding:12px;border-radius:8px}img{width:100%;height:auto}a{color:#9bd1ff}</style><h1>Material × Artifact — experimental 2.5D QA</h1><p>One synthetic image, first pane only. Artifact contrasts are not matched-topology zero-water controls.</p><main>']
    for r in rows:
        j=html.escape(r['id']); label=html.escape(r['status']+' · '+r['role'])
        parts.append(f'<article><h3>{j}</h3><a href="gallery/{j}/render.png"><img loading="lazy" src="gallery/{j}/render.png" alt="{j}"></a><p>{label} · artifact Δ {r["artifact_delta_pct"]:.3f}%</p><a href="gallery/{j}/scene.blend">Blender scene</a> · <a href="gallery/{j}/manifest.json">Manifest</a></article>')
    (out/'index.html').write_text('\n'.join(parts)+ '</main></html>',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--blend',type=Path,required=True); p.add_argument('--plan',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]); path=a.blend.resolve(); plan=read_json(a.plan); out=a.plan.resolve().parent
    need(plan['schema']==SCHEMA and plan['target']==TARGET and sha(path)==plan['input_blend_sha256'],'Plan/input mismatch')
    for rel,h in plan['inputs'].items():
        file=(ROOT/rel).resolve(); need(file.is_relative_to(ROOT) and sha(file)==h,'Input changed: '+rel)
    if not hasattr(bpy.types.Scene,'bvt_studio'): bvt_studio.register()
    # Validate all resolved artifact JSON with the actual Blender parser before rendering.
    resolved={}
    (out/'resolved_presets').mkdir()
    for effect,cfg in plan['presets'].items():
        pth=out/'resolved_presets'/(effect+'.json'); write_json(pth,cfg); resolved[effect]=parse_scene_config(pth)
    s,source,g=load_clean(path,plan); before=geometry(s)
    original=image_from_mesh(source); w,h=tuple(original.size)
    rect=pane_rect(_corners(g,source,image_uv_bounds(source)),w,h)
    legacy=render(out/'legacy.png'); need(legacy.shape==(h,w,3),'Unexpected render shape')
    (out/'gallery').mkdir(); rows=[]
    for job in plan['jobs']:
        name=job['id']; mat=job['material']; eff=job['effect']; d=out/'gallery'/name; d.mkdir()
        s,source,g=load_clean(path,plan)
        need(geometry(s)==before,'Input geometry changed')
        rebuild_materials(s,target=g,profile=plan['materials'][mat],seed=job['seed'])
        # Apply artifact after material (fresh clean scene, no cumulative atlas state).
        need(apply_scene_config(s,resolved[eff])==1,'Expected exactly one artifact target')
        need(digest(image_from_mesh(source))==plan['source']['sha256'],'Original source changed')
        need(geometry(s)==before,'Geometry changed while applying effects')
        need(source_for_glass(g)[1]==source_nodes(source)[1].image,'Glass samples incorrect source')
        for other in scene_glass(s):
            if other!=g: need(other.get('bvt_artifact_preset')=='QA_TRANSPARENT' and not other.get(PROFILE_KEY),'Non-target glass changed')
        write_json(d/'material.json',plan['materials'][mat]); write_json(d/'artifact.json',plan['presets'][eff])
        img=render(d/'render.png')
        if name=='clear_glass__00_clean': need(stats(legacy,img,rect)['max_rgb']==0,'Clear transparent control must match legacy')
        mat_base=decode_png((out/'gallery'/job['material_baseline']/'render.png').read_bytes())
        art_base=decode_png((out/'gallery'/job['artifact_baseline']/'render.png').read_bytes())
        m=stats(legacy,mat_base,rect); a_delta=stats(mat_base,img,rect); c=stats(art_base,img,rect); total=stats(legacy,img,rect)
        outside=max(m['outside_guard_gt4'],a_delta['outside_guard_gt4'],c['outside_guard_gt4'],total['outside_guard_gt4'])
        need(outside==0,'Changes outside target rectangle + 4px guard: '+name)
        reasons=[]
        if mat!='clear_glass' and m['roi_changed_gt4']==0: reasons.append('Material has no visible delta at threshold')
        if eff not in ('00_clean','13_clean_glass') and a_delta['roi_changed_gt4']==0: reasons.append('Artifact has no visible delta at threshold')
        # Old variant metadata belongs to the baseline gallery, not this experiment.
        for key in list(s.keys()):
            if key.startswith('bvt_gallery_v02_'): del s[key]
        s['bvt_material_artifact_job_v01']=name
        s.render.filepath='//render.png'
        diagnostics=d/'resource_persistence.json'
        report={'schema':'bvt.matrix-resource-persistence.v01','job':name,'status':'BEFORE_SAVE',
                'runtime_before':{},'runtime_after':{}}
        try:
            resources=resource_snapshot(s,True,report['runtime_before'])
            report['before']=resources
        except Exception as exc:
            report.update(status='ERROR_BEFORE_SAVE',error=str(exc));write_json(diagnostics,report);raise
        write_json(diagnostics,report)
        bpy.context.preferences.filepaths.save_version=0; scene_path=d/'scene.blend'
        need(bpy.ops.wm.save_as_mainfile(filepath=str(scene_path),compress=True,relative_remap=False)=={'FINISHED'},'Save failed')
        need(bpy.ops.wm.open_mainfile(filepath=str(scene_path))=={'FINISHED'},'Reopen failed')
        s=bpy.context.scene; source=get_source(s); g=s.objects[TARGET]
        need(s.get('bvt_material_artifact_job_v01')==name and s.render.filepath=='//render.png','Scene metadata or render path changed')
        need(geometry(s)==before and digest(image_from_mesh(source))==plan['source']['sha256'],'Persistence geometry/source failure')
        need(json.loads(g[PROFILE_KEY])==plan['materials'][mat] and g[SEED_KEY]==job['seed'],'Material state lost')
        need(g.get('bvt_artifact_preset')==resolved[eff][TARGET].get('preset','HEAVY_CONDENSATION') and g.get('bvt_artifact_seed')==job['seed'],'Artifact state lost')
        try:
            after=resource_snapshot(s,observed=report['runtime_after'])
            report['after']=after;report['delta']=snapshot_delta(resources,after)
            need(after==resources,'Packed resources changed after reopen: '+str(diagnostics))
        except Exception as exc:
            report.update(status='ERROR_AFTER_REOPEN',error=str(exc));write_json(diagnostics,report)
            print('RESOURCE_PERSISTENCE=ERROR '+str(diagnostics),flush=True);raise
        report['status']='PACKED_MATCH';write_json(diagnostics,report)
        need(source_for_glass(g)[1]==source_nodes(source)[1].image,'Reopened glass source mismatch')
        reopened=render(d/'reopened.png'); r_delta=stats(img,reopened,rect)
        report['rerender']=r_delta
        report['status']='PASS' if r_delta['max_rgb']==0 else 'RGB_MISMATCH'
        write_json(diagnostics,report)
        need(r_delta['max_rgb']==0,'Reopened render differs: '+name)
        row={**job,'status':'REVIEW' if reasons else 'PASS','review_reasons':reasons,'source_sha256':plan['source']['sha256'],'target':TARGET,'rect':rect,'guard_px':4,
             'material_only_delta':m,'artifact_delta':a_delta,'material_delta_at_fixed_artifact':c,'total_delta':total,'material_only_delta_pct':m['roi_changed_pct'],'artifact_delta_pct':a_delta['roi_changed_pct'],'outside_guard_gt4':outside,'reopen_max_rgb':r_delta['max_rgb'],'resources':resources,'render_sha256':sha(d/'render.png'),'blend_sha256':sha(scene_path)}
        write_json(d/'manifest.json',row); rows.append(row); print('MATRIX_JOB='+row['status']+' '+name,flush=True)
    status='REVIEW' if any(r['status']=='REVIEW' for r in rows) else 'PASS'
    index(out,rows); write_json(out/'report.json',{'schema':SCHEMA,'status':status,'blender':bpy.app.version_string,'jobs':rows,'warning':plan['warning'],'labels_status':'UNLABELED'})
    print('BLENDER_MATRIX='+status)

if __name__=='__main__': main()
