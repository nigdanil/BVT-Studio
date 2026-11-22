"""Read-only Blender verification of source, camera, pane geometry and box projection."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bvt_studio
from bvt_studio.annotation import collect_boxes
from bvt_studio.common import get_source,image_from_mesh,scene_annotations
from bvt_studio.glass import scene_glass
from bvt_studio.glass_mask import mask_image_for
from bvt_studio.glass_material_blender import image_bytes,BAKE_KEY
SCHEMA='bvt.yolo-matrix-propagation.v01'
TOL_PX=.05


def need(ok,msg):
    if not ok: raise ValueError(msg)


def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def digest(im):
    need(im is not None and im.packed_file,'Missing packed image')
    return hashlib.sha256(image_bytes(im)).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')


def open_scene(path,expected):
    need(sha(path)==expected,'Scene file SHA mismatch: '+str(path))
    need(bpy.ops.wm.open_mainfile(filepath=str(path))=={'FINISHED'},'Open failed: '+str(path))
    bpy.context.view_layer.update()
    return bpy.context.scene


def projected(scene,coords,size):
    values=[world_to_camera_view(scene,scene.camera,Vector(v)) for v in coords]
    need(all(v.z>0 for v in values),'Projection behind camera')
    arr=np.asarray([(v.x*size[0],(1-v.y)*size[1]) for v in values],dtype=float)
    need(np.isfinite(arr).all(),'Nonfinite camera projection')
    return arr


def world_vertices(obj,dg):
    transform=obj.evaluated_get(dg).matrix_world
    return [list(transform @ v.co) for v in obj.data.vertices]


def fingerprint(scene,plan):
    size=plan['size']; camera=scene.camera; r=scene.render
    need(camera is not None and camera.data.type=='ORTHO','Expected orthographic camera')
    need([r.resolution_x,r.resolution_y]==size and r.resolution_percentage==100 and not r.use_border,'Camera raster changed')
    source=get_source(scene); need(source is not None,'Missing source')
    original=image_from_mesh(source)
    need(digest(original)==plan['source_sha256'],'Original source SHA mismatch')
    need(tuple(original.size)==tuple(size),'Source image dimensions mismatch')
    glasses=sorted(scene_glass(scene),key=lambda o:o.name)
    need([g.name for g in glasses]==['Glass_p_001','Glass_p_002','Glass_p_003','Glass_p_004'],'Expected four named glass panes')
    dg=bpy.context.evaluated_depsgraph_get(); cam=camera.evaluated_get(dg); records={}
    for obj in [source,*glasses]:
        need(obj.type=='MESH' and obj.data.uv_layers.active is not None and not obj.modifiers,'Expected original photo/glass mesh and UVs: '+obj.name)
        coords=world_vertices(obj,dg); px=projected(scene,coords,size)
        records[obj.name]={'world':coords,'projected':px.tolist(),'polygons':[list(p.vertices) for p in obj.data.polygons],'uv':[list(v.uv) for v in obj.data.uv_layers.active.data]}
        if obj!=source:
            records[obj.name]['mask_sha256']=digest(mask_image_for(obj))
            records[obj.name]['uid']=str(obj.get('bvt_glass_uid',''))
            need(bool(records[obj.name]['uid']),'Missing glass UID: '+obj.name)
    return {'camera':camera.name,'camera_world':[list(v) for v in cam.matrix_world],'camera_frame':[list(v) for v in camera.data.view_frame(scene=scene)],'clip':[camera.data.clip_start,camera.data.clip_end],'pixel_aspect':[r.pixel_aspect_x,r.pixel_aspect_y],'source':source.name,'source_sha256':plan['source_sha256'],'objects':records}


def close(a,b,tol,label):
    x=np.asarray(a,dtype=float); y=np.asarray(b,dtype=float)
    need(x.shape==y.shape and np.isfinite(x).all() and np.isfinite(y).all(),'Shape/nonfinite geometry: '+label)
    delta=float(np.max(np.abs(x-y))) if x.size else 0.
    need(delta<=tol,f'Geometry mismatch {label}: {delta:.8g} > {tol}')
    return delta


def compare(ref,actual):
    for key in ('camera','source','source_sha256','pixel_aspect'):
        need(ref[key]==actual[key],'Changed '+key)
    for key in ('camera_world','camera_frame','clip'): close(ref[key],actual[key],1e-6,key)
    need(set(ref['objects'])==set(actual['objects']),'Source/pane inventory changed')
    maxpx=0.
    for name,a in ref['objects'].items():
        b=actual['objects'][name]
        for key in ('polygons','mask_sha256','uid'):need(a.get(key)==b.get(key),name+': changed '+key)
        close(a['world'],b['world'],1e-6,name+' world geometry'); close(a['uv'],b['uv'],1e-6,name+' UV')
        maxpx=max(maxpx,close(a['projected'],b['projected'],TOL_PX,name+' projection'))
    return maxpx


def align_reference_to_control(ref, control, diagnostics):
    """Accept only a rigid camera-axis translation of transparent reference panes.

    Never normalize the matrix itself: every derivative is compared strictly
    with the SHA-verified clean matrix control, including full world geometry.
    The reference source, camera, UVs, topology, masks, IDs and screen
    projection remain subject to the original strict comparison.
    """
    tol=1e-6
    close(ref['camera_world'],control['camera_world'],tol,'reference camera world')
    camera=np.asarray(control['camera_world'],dtype=float)
    need(camera.shape==(4,4) and np.isfinite(camera).all(),'Invalid camera matrix')
    axis=camera[:3,2]; length=float(np.linalg.norm(axis))
    need(length>tol,'Degenerate camera axis')
    axis=axis/length  # camera local +Z points toward the camera / away from view
    origin=camera[:3,3]
    need(set(ref['objects'])==set(control['objects']),'Source/pane inventory changed')
    need(ref['source']==control['source'],'Changed source')
    source=ref['source']
    close(ref['objects'][source]['world'],control['objects'][source]['world'],tol,'reference source world')
    normalised=dict(ref,objects={k:dict(v) for k,v in ref['objects'].items()})
    for name,a in ref['objects'].items():
        if name==source: continue
        b=control['objects'][name]
        x=np.asarray(a['world'],dtype=float); y=np.asarray(b['world'],dtype=float)
        need(x.shape==y.shape and x.ndim==2 and x.shape[1]==3 and len(x)>0 and np.isfinite(x).all() and np.isfinite(y).all(),'Invalid pane coordinates: '+name)
        delta=x-y; axial=delta@axis
        shift=float(np.mean(axial)); rigid=float(np.max(np.linalg.norm(delta-shift*axis,axis=1)))
        lateral=float(np.max(np.linalg.norm(delta-axial[:,None]*axis,axis=1)))
        px=float(np.max(np.abs(np.asarray(a['projected'])-np.asarray(b['projected']))))
        entry={'reference_minus_control_axis_shift':shift,'max_vertex_world_delta':float(np.max(np.abs(delta))), 'max_rigid_residual':rigid,'max_lateral_delta':lateral,'max_projection_delta_px':px,'status':'ERROR'}
        diagnostics[name]=entry
        need(rigid<=tol and lateral<=tol,'Reference pane is not a rigid camera-axis translation: '+name)
        close(a['projected'],b['projected'],TOL_PX,name+' reference projection')
        # A translated pane must remain in front of the photo and within the
        # common camera clipping range in both scenes. No behind-photo waiver.
        if abs(shift)>tol:
            for objset,world,clip in ((ref['objects'],x,ref['clip']),(control['objects'],y,control['clip'])):
                photo=np.asarray(objset[source]['world'],dtype=float)
                pd=-(photo-origin)@axis; gd=-(world-origin)@axis
                need(float(gd.min())>=clip[0] and float(pd.max())<=clip[1] and float(gd.max())<float(pd.min()),'Reference/control pane depth order or clip invalid: '+name)
        # Only the already verified axial component is removed for the reference
        # comparison; lateral movement, deformation and projection are not waived.
        normalised['objects'][name]['world']=(x-shift*axis).tolist()
        entry['status']='AXIAL_TRANSLATION' if abs(shift)>tol else 'UNCHANGED_WITHIN_TOLERANCE'
    return compare(normalised,control)


def bbox_px(coords):
    return np.r_[coords.min(axis=0),coords.max(axis=0)]


def check_boxes(scene,plan):
    boxes,issues,classes=collect_boxes(scene)
    need(not issues,'Reference annotation check: '+str(issues))
    by_uid={b['uid']:b for b in boxes}; expected=plan['boxes']; size=plan['size']; scale=np.array([size[0],size[1],size[0],size[1]],dtype=float)
    need(len(boxes)==len(expected)==len(by_uid) and set(by_uid)=={b['uid'] for b in expected},'Reference annotation IDs/count changed')
    dg=bpy.context.evaluated_depsgraph_get(); coords={}; maxpx=0.
    for b in expected:
        actual=by_uid[b['uid']]; name=b['object']
        need(actual['object']==name and actual['class_id']==b['class_id'] and actual['class_name']==b['class_name'],'Reference class/object mismatch: '+name)
        target=np.asarray(b['xyxy'])*scale
        maxpx=max(maxpx,close([actual[k]*scale[i] for i,k in enumerate(('xmin','ymin','xmax','ymax'))],target,TOL_PX,name+' export box'))
        coords[name]=world_vertices(scene.objects[name],dg)
        maxpx=max(maxpx,close(bbox_px(projected(scene,coords[name],size)),target,TOL_PX,name+' projected box'))
    return coords,maxpx


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',required=True,type=Path);p.add_argument('--report',required=True,type=Path)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]); plan=json.loads(a.plan.read_text(encoding='utf-8'));need(plan['schema']==SCHEMA,'Invalid geometry plan')
    report={'schema':SCHEMA,'status':'ERROR','reference_blend_sha256':plan['reference_blend_sha256'],'source_sha256':plan['source_sha256'],'blender':bpy.app.version_string,'boxes':len(plan['boxes']),'projection_tolerance_px':TOL_PX,'jobs':[]}
    try:
        if not hasattr(bpy.types.Scene,'bvt_studio'): bvt_studio.register()
        refpath=Path(plan['reference_blend']);s=open_scene(refpath,plan['reference_blend_sha256']); original=fingerprint(s,plan)
        m=plan['manifest'];need(s.camera.name==m['camera'] and get_source(s).name==m['source_image'] and s.name==m['scene'] and s.bvt_studio.camera_profile==m['camera_profile'],'Reference blend/manifest context mismatch')
        need(not get_source(s).get(BAKE_KEY) and all(g.get('bvt_artifact_preset')=='QA_TRANSPARENT' for g in scene_glass(s)),'Reference blend not clean transparent')
        coords,delta=check_boxes(s,plan); report['reference_max_box_delta_px']=delta
        controls=[item for item in plan['scenes'] if item['id']=='clear_glass__00_clean']
        need(len(controls)==1,'Expected exactly one clean matrix control')
        control=controls[0]; control_path=Path(control['path'])
        s=open_scene(control_path,control['sha256'])
        need(s.get('bvt_material_artifact_job_v01')==control['id'],'Clean control job mismatch')
        need(not scene_annotations(s),'Clean matrix control already contains annotation objects')
        need(not get_source(s).get(BAKE_KEY) and all(g.get('bvt_artifact_preset')=='QA_TRANSPARENT' for g in scene_glass(s)),'Matrix control not clean transparent')
        baseline=fingerprint(s,plan)
        alignment={'policy':'rigid_camera_axis_only_reference_to_clean_control','matrix_control_id':control['id'],'matrix_control_sha256':control['sha256'],'world_tolerance':1e-6,'panes':{}}
        report['reference_alignment']=alignment
        alignment['max_projection_delta_px']=align_reference_to_control(original,baseline,alignment['panes'])
        alignment['status']='PASS'
        print('YOLO_REFERENCE_ALIGNMENT=PASS',flush=True)
        scale=np.array([plan['size'][0],plan['size'][1],plan['size'][0],plan['size'][1]],dtype=float)
        for item in plan['scenes']:
            path=Path(item['path']);s=open_scene(path,item['sha256']);name=item['id']
            need(s.get('bvt_material_artifact_job_v01')==name,'Scene job metadata mismatch: '+name)
            need(not scene_annotations(s),'Matrix scene already contains annotation objects: '+name)
            geom=compare(baseline,fingerprint(s,plan)); boxdelta=0.
            for b in plan['boxes']:
                actual=bbox_px(projected(s,coords[b['object']],plan['size'])); expected=np.asarray(b['xyxy'])*scale
                boxdelta=max(boxdelta,close(actual,expected,TOL_PX,name+' '+b['object']))
            need(sha(path)==item['sha256'],'Scene bytes changed: '+name)
            report['jobs'].append({'id':name,'sha256':item['sha256'],'status':'PASS','max_geometry_delta_px':geom,'max_box_delta_px':boxdelta,'box_count':len(coords)})
            print('YOLO_GEOMETRY=PASS '+name,flush=True)
        need(sha(refpath)==plan['reference_blend_sha256'],'Reference file changed')
        report['status']='PASS';write(a.report,report); print('BLENDER_YOLO_GEOMETRY=PASS',flush=True)
    except Exception as exc:
        report['error']=str(exc);write(a.report,report);raise


if __name__=='__main__':main()
