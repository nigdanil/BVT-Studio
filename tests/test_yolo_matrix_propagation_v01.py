"""Pure planner, numerical and Blender geometry contract tests for Step 5."""
import ast
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import bvt_yolo_matrix_propagation as m


def png(arr):
    b=io.BytesIO(); Image.fromarray(arr).save(b,format='PNG'); return b.getvalue()


def annotation(uid='u1',obj='plane_p_001',x=.5,y=.5,w=.2,h=.4):
    return dict(uid=uid,object=obj,class_id=0,class_name='ice_cream',x=x,y=y,w=w,h=h,xmin=x-w/2,ymin=y-h/2,xmax=x+w/2,ymax=y+h/2)


def label(a): return '0 '+' '.join(f'{a[k]:.7f}' for k in m.FIELDS)+'\n'


class YoloMatrixTests(unittest.TestCase):
    def test_label_contract(self):
        a=annotation(); b,c=m.parse_labels(label(a),[a],[100,100]); self.assertEqual(c,{0:'ice_cream'}); self.assertEqual(b[0]['rect'],[40,30,60,70]); self.assertEqual(b[0]['uid'],'u1')
    def test_reject_invalid_labels(self):
        a=annotation()
        for t in ('0 nan .5 .2 .4','0 .5 .1 .2 .4','0 .5 .5 0 .4','1 .5 .5 .2 .4','0 .6 .5 .2 .4','0 .5 .5 .2 .4 1',''):
            with self.subTest(t=t),self.assertRaises(ValueError):m.parse_labels(t,[a],[100,100])
    def test_duplicate_or_mismatched_manifest(self):
        a=annotation(); b=annotation('u2','plane_p_002')
        for anns in ([a,a],[a,b],[dict(a,xmin=.1)]):
            with self.assertRaises(ValueError):m.parse_labels(''.join(label(x) for x in anns),anns,[100,100])
    def test_yaml_class_contract(self):
        good='train: images/train\nval: images/val\nnc: 1\nnames:\n  0: "ice_cream"\n';m.validate_yaml(good,{0:'ice_cream'})
        for bad in (good.replace('ice_cream','product'),good.replace('nc: 1','nc: 2'),good.replace('images/train','../train')):
            with self.assertRaises(ValueError):m.validate_yaml(bad,{0:'ice_cream'})
    def test_path_guards(self):
        for s in ('../a','/a','a/../b','a\\b','C:/a','a//b','./a'):
            with self.assertRaises(ValueError):m.safe_relative(s)
        with tempfile.TemporaryDirectory() as t,patch.object(m,'ROOT',Path(t)):
            root=Path(t)/'qa_renders';root.mkdir();orig=root/'input';orig.mkdir()
            with self.assertRaises(ValueError):m.output_guard(orig/'new',[orig])
            with self.assertRaises(ValueError):m.output_guard(orig,[])
            self.assertEqual(m.output_guard(root/'new',[orig]),root/'new')
    def test_rgb_strict(self):
        a=np.zeros((20,30,3),np.uint8); raw=png(a);np.testing.assert_array_equal(m.rgb(raw,[30,20]),a)
        with self.assertRaises(ValueError):m.rgb(raw,[20,30])
        with self.assertRaises(ValueError):m.rgb(png(np.zeros((20,30,4),np.uint8)))
    def test_reference_zip(self):
        a=annotation(); data={'schema':'bvt_studio_2d_yolo_v0.1','camera_type':'ORTHO','camera_profile':'ORIGINAL','image_width':100,'image_height':100,'image':'images/train/sample_000001.png','labels':'labels/train/sample_000001.txt','glass':[{'artifact_preset':'QA_TRANSPARENT'}]*4,'annotations':[a]}
        with tempfile.TemporaryDirectory() as t:
            zpath=Path(t)/'ref.zip'
            with zipfile.ZipFile(zpath,'w') as z:
                z.writestr('sample_000001_manifest.json',json.dumps(data));z.writestr(data['image'],png(np.zeros((100,100,3),np.uint8)));z.writestr(data['labels'],label(a));z.writestr('scene.blend',b'fixture');z.writestr('data.yaml','train: images/train\nval: images/val\nnc: 1\nnames:\n  0: "ice_cream"\n')
            ref=m.reference_archive(zpath);self.assertEqual(len(ref['boxes']),1);self.assertEqual(ref['classes'],{0:'ice_cream'})
    def test_box_review_and_invariance(self):
        a=np.random.default_rng(20).integers(0,256,(100,100,3),dtype=np.uint8);b=a.copy();b[30:70,40:60]=128;box=m.parse_labels(label(annotation()),[annotation()],[100,100])[0][0]
        q=m.box_qa(a,b,box,[35,25,65,75],4,'EXPERIMENTAL');self.assertIn('LOW_DETAIL_PROXY',q['flags']);self.assertEqual(q['status'],'REVIEW');self.assertEqual(q['uid'],box['uid']);self.assertEqual(q['rect'],box['rect'])
        q=m.box_qa(a,a,box,[0,0,20,20],4,'EXPERIMENTAL');self.assertEqual(q['status'],'CANDIDATE_UNCHANGED');self.assertFalse(q['affected_roi']);self.assertEqual(q['changed_gt4_pct'],0)
        q=m.box_qa(a,b,box,[0,0,20,20],4,'QA_ONLY');self.assertEqual(q['status'],'QA_ONLY');self.assertIn('OUTSIDE_TARGET_CHANGE',q['flags'])
    def test_matrix_png_fail_closed(self):
        a=np.zeros((50,60,3),np.uint8); b=a.copy(); b[15:25,15:25]=40; name=m.CONTROL; row={'id':name,'rect':[10,10,30,30],'guard_px':4,'render_sha256':m.digest(png(b)),'total_delta':{'changed_gt4':100,'max_rgb':40}}
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);d=root/'gallery'/name;d.mkdir(parents=True); (d/'render.png').write_bytes(png(b));(d/'reopened.png').write_bytes(png(b));m.check_matrix_png(root,row,[60,50],a)
            (d/'reopened.png').write_bytes(png(a))
            with self.assertRaises(ValueError):m.check_matrix_png(root,row,[60,50],a)
            b[0,0]=9;(d/'render.png').write_bytes(png(b));(d/'reopened.png').write_bytes(png(b));row['render_sha256']=m.digest(png(b))
            with self.assertRaisesRegex(ValueError,'leakage'):m.check_matrix_png(root,row,[60,50],a)
    def test_geometry_numeric_contract(self):
        # Execute pure geometry helpers from Blender worker without importing bpy.
        src=(ROOT/'scripts/blender_yolo_matrix_check.py').read_text(); tree=ast.parse(src); names={'need','close','compare','bbox_px'}; funcs=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]); ns={'np':np,'TOL_PX':.05};exec(compile(funcs,'geometry','exec'),ns)
        a=dict(camera='camera',source='source',source_sha256='x',pixel_aspect=[1,1],camera_world=[[1]],camera_frame=[[2]],clip=[.1,100],objects={'s':dict(world=[[1,2,3]],projected=[[20.,30.]],uv=[[.5,.5]],polygons=[[0]])})
        self.assertEqual(ns['compare'](a,copy.deepcopy(a)),0)
        for field in ('world','projected','uv','polygons'):
            b=copy.deepcopy(a);b['objects']['s'][field][0][0]+=1
            with self.assertRaises(ValueError):ns['compare'](a,b)
        np.testing.assert_array_equal(ns['bbox_px'](np.array([[1,2],[4,6],[2,3]])),[1,2,4,6])
    def _depth_helpers(self):
        tree=ast.parse((ROOT/'scripts/blender_yolo_matrix_check.py').read_text())
        names={'need','close','compare','align_reference_to_control'}
        ns={'np':np,'TOL_PX':.05}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'geometry','exec'),ns)
        cam=np.eye(4);cam[2,3]=5
        photo=dict(world=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],projected=[[0,0],[100,0],[100,100],[0,100]],uv=[[0,0],[1,0],[1,1],[0,1]],polygons=[[0,1,2,3]])
        pane=dict(copy.deepcopy(photo),world=[[0,0,.02],[1,0,.02],[1,1,.02],[0,1,.02]],uid='g',mask_sha256='mask')
        a=dict(camera='cam',camera_world=cam.tolist(),camera_frame=[[1]],clip=[.1,100],pixel_aspect=[1,1],source='photo',source_sha256='sha',objects={'photo':photo,'Glass_p_001':pane})
        return ns,a

    def test_reference_axial_translation_only(self):
        ns,a=self._depth_helpers();b=copy.deepcopy(a)
        b['objects']['Glass_p_001']['world']=(np.asarray(a['objects']['Glass_p_001']['world'])+[0,0,.012681067]).tolist()
        d={};self.assertEqual(ns['align_reference_to_control'](b,a,d),0)
        self.assertAlmostEqual(d['Glass_p_001']['reference_minus_control_axis_shift'],.012681067)
        self.assertEqual(d['Glass_p_001']['status'],'AXIAL_TRANSLATION')
        with self.assertRaises(ValueError):ns['compare'](a,b)

    def test_reference_rotated_camera_axis(self):
        ns,a=self._depth_helpers();rot=np.array([[0,0,1],[0,1,0],[-1,0,0]])
        cam=np.asarray(a['camera_world']);cam[:3,:]=rot@cam[:3,:];a['camera_world']=cam.tolist()
        for v in a['objects'].values():v['world']=(np.asarray(v['world'])@rot.T).tolist()
        b=copy.deepcopy(a);b['objects']['Glass_p_001']['world']=(np.asarray(a['objects']['Glass_p_001']['world'])+[.012681067,0,0]).tolist()
        self.assertEqual(ns['align_reference_to_control'](b,a,{}),0)

    def test_reference_lateral_or_nonrigid_rejected(self):
        ns,a=self._depth_helpers()
        for delta in ([.001,0,.012681067],[[0,0,.01],[0,0,.02],[0,0,.01],[0,0,.01]]):
            b=copy.deepcopy(a);b['objects']['Glass_p_001']['world']=(np.asarray(a['objects']['Glass_p_001']['world'])+delta).tolist()
            with self.assertRaisesRegex(ValueError,'not a rigid camera-axis'):ns['align_reference_to_control'](b,a,{})

    def test_reference_depth_order_and_projection_rejected(self):
        ns,a=self._depth_helpers()
        for shift in (-.03,4.99):
            b=copy.deepcopy(a);b['objects']['Glass_p_001']['world']=(np.asarray(a['objects']['Glass_p_001']['world'])+[0,0,shift]).tolist()
            with self.assertRaisesRegex(ValueError,'depth order or clip'):ns['align_reference_to_control'](b,a,{})
        b=copy.deepcopy(a);b['objects']['Glass_p_001']['projected'][0][0]+=.06
        with self.assertRaises(ValueError):ns['align_reference_to_control'](b,a,{})

    def test_reference_camera_source_uv_mask_identity_strict(self):
        ns,a=self._depth_helpers()
        for path,value in ((('camera_world',0,3),.01),(('objects','photo','world',0,2),.001),(('objects','Glass_p_001','uv',0,0),.01),(('objects','Glass_p_001','mask_sha256'),'changed'),(('objects','Glass_p_001','uid'),'changed')):
            b=copy.deepcopy(a);target=b
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
            with self.assertRaises(ValueError):ns['align_reference_to_control'](b,a,{})

    def test_worker_strict_matrix_and_reference_alignment_report(self):
        src=(ROOT/'scripts/blender_yolo_matrix_check.py').read_text()
        self.assertIn('align_reference_to_control(original,baseline',src)
        self.assertIn('geom=compare(baseline,fingerprint(s,plan))',src)
        self.assertIn("report['reference_alignment']=alignment",src)
        self.assertIn('need(sha(path)==item',src)

    def test_pack_qa_archive(self):
        import bvt_yolo_matrix_pack as pack
        with tempfile.TemporaryDirectory() as t,patch.object(pack,'ROOT',Path(t)):
            root=Path(t)/'qa_renders';base=root/'candidate';base.mkdir(parents=True);name=m.CONTROL
            raw=png(np.zeros((50,60,3),np.uint8));txt=label(annotation()).encode();image=f'images/pilot/{name}.png';labels=f'labels/pilot/{name}.txt'
            r={'id':name,'image':image,'labels':labels,'render_sha256':m.digest(raw),'label_sha256':m.digest(txt)}
            report={'schema':m.SCHEMA,'status':'PASS_CANDIDATES','geometry_status':'PASS','jobs':1,'jobs_summary':[r]}
            files={'report.json':json.dumps(report).encode(),'geometry.json':b'{}','summary.csv':b'id\n','box_review.csv':b'id\n','blender.log':b'PASS','classes.json':b'{}','reference/labels.txt':txt,'reference/manifest.json':b'{}','reference/clean.png':raw,'reference/data.yaml':b'names: {}',f'manifests/{name}.json':b'{}',image:raw,labels:txt,f'previews/{name}.png':raw}
            for rel,content in files.items():
                f=base/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(content)
            target=root/'review.zip';pack.main(['--input-dir',str(base),'--archive',str(target)])
            with zipfile.ZipFile(target) as z:
                self.assertEqual(z.testzip(),None);self.assertIn(f'preview_jpeg/{name}.jpg',z.namelist());self.assertNotIn(image,z.namelist());manifest=json.loads(z.read('archive_manifest.json'));self.assertEqual(manifest['files'][labels]['sha256'],m.digest(txt))
            with self.assertRaises(ValueError):pack.main(['--input-dir',str(base),'--archive',str(target)])
            (base/labels).write_bytes(b'changed')
            with self.assertRaises(ValueError):pack.main(['--input-dir',str(base),'--archive',str(root/'another.zip')])

    def test_contract_not_training_or_mutating_blends(self):
        self.assertEqual(len(m.MATERIALS)*len(m.EFFECTS),84);self.assertEqual(len(m.QA_EFFECTS)*len(m.MATERIALS),18)
        worker=(ROOT/'scripts/blender_yolo_matrix_check.py').read_text();self.assertNotIn('save_as_mainfile',worker);self.assertIn('collect_boxes(scene)',worker);self.assertIn('world_to_camera_view',worker)
        cli=(ROOT/'scripts/bvt_yolo_matrix_propagation.py').read_text();self.assertIn('INHERITED_CANDIDATES_NOT_APPROVED',cli);self.assertIn('train_val_split=None',cli);self.assertIn('if not a.audit_only:',cli)
        ast.parse((ROOT/'scripts/bvt_yolo_matrix_pack.py').read_text())

if __name__=='__main__': unittest.main()
