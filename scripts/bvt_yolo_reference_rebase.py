#!/usr/bin/env python3
"""Create a new annotated reference from the immutable clean matrix control.

Host validates the original export and pixels; Blender copies only annotation
geometry, not the edited glass meshes. Existing propagation gates stay intact.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import zipfile

SCHEMA = 'bvt.yolo-reference-rebase.v01'


def source_only(fingerprint):
    """Select only the camera and photo; never use this for matrix-to-matrix QA."""
    return dict(fingerprint, objects={fingerprint['source']: fingerprint['objects'][fingerprint['source']]})


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def worker(plan_path, result_path):
    import bpy
    import numpy as np
    from mathutils import Vector
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import blender_yolo_matrix_check as g
    from bvt_studio.annotation import configure_outline, PREVIEW_PROP
    from bvt_studio.common import ensure_collection
    p = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    report = {'schema': SCHEMA, 'status': 'ERROR', 'control_sha256': p['control_sha256'],
              'original_reference_sha256': p['reference_blend_sha256'], 'boxes': len(p['boxes'])}
    result_path = Path(result_path)
    try:
        require(p['schema'] == g.SCHEMA, 'Invalid worker plan')
        if not hasattr(bpy.types.Scene, 'bvt_studio'):
            g.bvt_studio.register()
        ref = Path(p['reference_blend']); control = Path(p['control']); out = result_path.parent
        s = g.open_scene(ref, p['reference_blend_sha256']); original = g.fingerprint(s, p)
        m = p['manifest']
        require(s.name == m['scene'] and s.camera.name == m['camera'] and g.get_source(s).name == m['source_image'] and s.bvt_studio.camera_profile == m['camera_profile'], 'Original reference context mismatch')
        require(not g.get_source(s).get(g.BAKE_KEY) and all(o.get('bvt_artifact_preset') == 'QA_TRANSPARENT' for o in g.scene_glass(s)), 'Original reference is not clean transparent')
        coords, report['original_box_delta_px'] = g.check_boxes(s, p)
        # Only evaluated RAW annotation vertices and polygon indices cross files.
        records = []
        for b in p['boxes']:
            obj = s.objects[b['object']]
            vertices = coords[obj.name]
            faces = [list(poly.vertices) for poly in obj.data.polygons]
            require(len(vertices) == 4 and len(faces) == 1 and sorted(faces[0]) == [0,1,2,3], 'Expected a single annotation quad: '+obj.name)
            records.append((b, vertices, faces))
        s = g.open_scene(control, p['control_sha256'])
        require(s.get('bvt_material_artifact_job_v01') == 'clear_glass__00_clean', 'Wrong matrix control')
        require(not g.scene_annotations(s), 'Control already contains annotations')
        require(s.name == m['scene'] and s.bvt_studio.camera_profile == m['camera_profile'], 'Control scene/profile mismatch')
        require(not g.get_source(s).get(g.BAKE_KEY) and all(o.get('bvt_artifact_preset') == 'QA_TRANSPARENT' for o in g.scene_glass(s)), 'Control is not clean transparent')
        baseline = g.fingerprint(s, p)
        report['photo_camera_delta_px'] = g.compare(source_only(original), source_only(baseline))
        report['discarded_reference_panes'] = {name: {'max_projection_delta_px': float(np.max(np.abs(np.asarray(a['projected'])-np.asarray(baseline['objects'][name]['projected']))))} for name,a in original['objects'].items() if name != original['source']}
        # Explicitly verify all original bounding-box coordinates in the control
        # BEFORE creating anything. A changed camera/source cannot be waived.
        size = p['size']; scale = np.array([size[0],size[1],size[0],size[1]])
        report['control_box_delta_px'] = max(g.close(g.bbox_px(g.projected(s,vs,size)),np.asarray(b['xyxy'])*scale,g.TOL_PX,b['object']+' control box') for b,vs,_ in records)
        collection = ensure_collection(s, 'BVT_Annotations')
        s[PREVIEW_PROP] = False
        for index,(b,vs,faces) in enumerate(records):
            name = b['object']; require(bpy.data.objects.get(name) is None, 'Annotation name occupied: '+name)
            center = Vector(np.asarray(vs,dtype=float).mean(axis=0).tolist())
            mesh = bpy.data.meshes.new('BVT_Rebased_Annotation_Mesh')
            mesh.from_pydata([tuple(Vector(v)-center) for v in vs], [], faces); mesh.update()
            obj = bpy.data.objects.new(name,mesh); collection.objects.link(obj); obj.location = center
            obj['bvt_role']='annotation'; obj['bvt_annotation_uid']=b['uid']; obj['bvt_class_id']=b['class_id']; obj['bvt_class_name']=b['class_name']; obj['bvt_enabled']=True
            bpy.context.view_layer.update(); configure_outline(obj,index,False)
            require(obj.name==name and obj.hide_render, 'Annotation identity/render flag changed: '+name)
        bpy.context.view_layer.update()
        _, report['rebased_box_delta_px'] = g.check_boxes(s,p)
        report['control_geometry_delta_px'] = g.compare(baseline,g.fingerprint(s,p))
        # Capture actual glass metadata; original annotation manifest/TXT values
        # remain unchanged (not requantized after reconstructing the quads).
        fields = {'reflection':('bvt_glass_reflection',0),'tint':('bvt_glass_tint',0),'haze':('bvt_glass_haze',0),'frost':('bvt_glass_frost',0),'droplets':('bvt_glass_droplets',0),'dirt':('bvt_glass_dirt',0),'artifact_coverage':('bvt_artifact_coverage',0),'artifact_seed':('bvt_artifact_seed',0),'artifact_droplet_scale':('bvt_artifact_droplet_scale',1.0),'artifact_frost_edge':('bvt_artifact_frost_edge',.35),'artifact_refraction':('bvt_artifact_refraction',.016),'artifact_relief':('bvt_artifact_relief',.8),'artifact_preset':('bvt_artifact_preset','CUSTOM')}
        report['glass'] = [dict(object=o.name,**{k:o.get(prop,default) for k,(prop,default) in fields.items()}) for o in g.scene_glass(s)]
        target = out/'scene.blend'; require(not target.exists(),'Output scene exists')
        require(bpy.ops.wm.save_as_mainfile(filepath=str(target),relative_remap=False)=={'FINISHED'},'Save failed')
        saved_sha = g.sha(target); s = g.open_scene(target,saved_sha)
        _,report['reopened_box_delta_px']=g.check_boxes(s,p)
        report['reopened_geometry_delta_px']=g.compare(baseline,g.fingerprint(s,p))
        require(all(o.hide_render for o in g.scene_annotations(s)),'Annotation outlines visible after reopen')
        s.render.image_settings.file_format='PNG'; s.render.image_settings.color_mode='RGB'; s.render.filepath=str(out/'reopened.png')
        require(bpy.ops.render.render(write_still=True)=={'FINISHED'},'Render failed')
        require(g.sha(target)==saved_sha and g.sha(ref)==p['reference_blend_sha256'] and g.sha(control)==p['control_sha256'],'Input/output blend bytes changed')
        report.update(status='PASS',rebased_blend_sha256=saved_sha)
        g.write(result_path,report)
        print('BLENDER_REFERENCE_REBASE=PASS',flush=True)
    except Exception as exc:
        report['error']=str(exc); g.write(result_path,report); raise


def host(argv=None):
    import numpy as np
    import bvt_yolo_matrix_propagation as m
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ('reference-zip','matrix-dir','output-dir','blender'):
        ap.add_argument('--'+arg,required=True,type=Path)
    a=ap.parse_args(argv); refpath=a.reference_zip.resolve(); base=a.matrix_dir.resolve()
    out=m.output_guard(a.output_dir,[base,refpath]); require(a.blender.is_file(),'Missing Blender executable')
    ref=m.reference_archive(refpath); plan,rows=m.matrix_jobs(base); control=next(r for r in rows if r['id']==m.CONTROL)
    size=ref['image_size']; require(size==[plan['source']['width'],plan['source']['height']],'Reference size mismatch')
    clean=m.rgb(ref['image'],size); _,render=m.check_matrix_png(base,control,size,clean)
    require(np.array_equal(clean,render),'Original YOLO image differs from control')
    controlpath=m.existing_file(base,'gallery/'+m.CONTROL+'/scene.blend'); require(m.sha(controlpath)==control['blend_sha256'],'Control SHA mismatch')
    input_sha=m.sha(refpath); out.mkdir(parents=True)
    report={'schema':SCHEMA,'status':'ERROR','reference_zip_sha256':input_sha,'control_sha256':control['blend_sha256'],'labels_sha256':m.digest(ref['label'])}
    try:
        # Keep diagnostic JSON, not an extracted copy of the reference blend.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='bvt_yolo_rebase_') as tmp:
            tmp=Path(tmp); refblend=tmp/'reference.blend'; refblend.write_bytes(ref['blend']); planfile=tmp/'plan.json'
            m.write(planfile,dict(schema=m.SCHEMA,reference_blend=str(refblend),reference_blend_sha256=m.digest(ref['blend']),source_sha256=plan['source']['sha256'],size=size,manifest=ref['manifest'],boxes=ref['boxes'],control=str(controlpath),control_sha256=control['blend_sha256']))
            cmd=[str(a.blender.resolve()),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).resolve()),'--','--worker',str(planfile),str(out/'geometry.json')]
            with (out/'blender.log').open('w',encoding='utf-8') as log:
                proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
            require(proc.returncode==0,'Blender rebase failed; see geometry.json and blender.log')
        g=m.read(out/'geometry.json'); scene=out/'scene.blend'
        require(g['schema']==SCHEMA and g['status']=='PASS' and g['boxes']==len(ref['boxes']) and g['control_sha256']==control['blend_sha256'] and g['original_reference_sha256']==m.digest(ref['blend']) and g['rebased_blend_sha256']==m.sha(scene),'Rebase proof mismatch')
        require(np.array_equal(clean,m.rgb((out/'reopened.png').read_bytes(),size)),'Rebased clean render differs from reference pixels')
        require(m.sha(refpath)==input_sha and m.sha(controlpath)==control['blend_sha256'],'Inputs changed during rebase')
        manifest=dict(ref['manifest'],glass=g['glass'],note='Rebased annotations on immutable clean matrix control; original TXT and annotation coordinates retained. One source group; val is empty.')
        stem=Path(manifest['image']).stem; manifest_name=stem+'_manifest.json'
        archive=out/'yolo_export_rebased_v02.zip'; provisional=out/'reference.tmp.zip'
        report.update(status='PASS',boxes=len(ref['boxes']),clean_rgb_equal=True,rebased_blend_sha256=m.sha(scene),original_reference_blend_sha256=m.digest(ref['blend']))
        with zipfile.ZipFile(provisional,'x',zipfile.ZIP_DEFLATED) as z:
            z.write(scene,'scene.blend'); z.writestr(manifest['image'],ref['image']); z.writestr(manifest['labels'],ref['label']); z.writestr('data.yaml',ref['yaml']); z.writestr(manifest_name,json.dumps(manifest,ensure_ascii=False,indent=2))
            preview=manifest.get('preview'); m.safe_relative(preview)
            with zipfile.ZipFile(refpath) as old:
                info=old.getinfo(preview); require(0<info.file_size<=8*1024*1024,'Invalid preview'); z.writestr(preview,old.read(info))
            z.writestr('reference_rebase_provenance.json',json.dumps(report,indent=2))
        # Validate same parser used by propagation; original coordinates/TXT must be byte-identical.
        new=m.reference_archive(provisional); require(new['label']==ref['label'] and new['manifest']['annotations']==ref['manifest']['annotations'] and new['image']==ref['image'],'Rebased archive label/image mismatch')
        with zipfile.ZipFile(provisional) as z: require(z.testzip() is None,'ZIP CRC failure')
        provisional.replace(archive); report['archive_sha256']=m.sha(archive); m.write(out/'report.json',report)
        print('YOLO_REFERENCE_REBASE=PASS',flush=True); print('REFERENCE_ZIP='+str(archive),flush=True)
    except Exception as exc:
        report.update(status='ERROR',error=str(exc)); m.write(out/'report.json',report); raise


if __name__=='__main__':
    if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:][:1]==['--worker']:
        args=sys.argv[sys.argv.index('--')+2:]; worker(*args)
    else:
        try: host()
        except Exception as exc: print('YOLO_REFERENCE_REBASE=ERROR: '+str(exc),file=sys.stderr); sys.exit(1)
