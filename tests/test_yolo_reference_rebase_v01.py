import ast
import copy
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import bvt_yolo_reference_rebase as r

class ReferenceRebaseTests(unittest.TestCase):
    def setUp(self):
        t=ast.parse((ROOT/'scripts/blender_yolo_matrix_check.py').read_text())
        names={'need','close','compare'}
        self.ns={'np':np,'TOL_PX':.05}
        exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'geometry','exec'),self.ns)
        mesh=dict(world=[[0,0,0],[1,0,0]],projected=[[0,0],[100,0]],uv=[[0,0],[1,0]],polygons=[[0,1]])
        self.a=dict(camera='cam',source='photo',source_sha256='sha',camera_world=np.eye(4).tolist(),camera_frame=[[0,1,2]],clip=[.1,10],pixel_aspect=[1,1],objects={'photo':copy.deepcopy(mesh),'Glass_p_001':copy.deepcopy(mesh)})
    def test_rebase_discards_old_pane_not_matrix_guard(self):
        b=copy.deepcopy(self.a); b['objects']['Glass_p_001']['world'][0][0]=.012681067; b['objects']['Glass_p_001']['projected'][0][0]=10.62265
        self.assertEqual(self.ns['compare'](r.source_only(self.a),r.source_only(b)),0)
        with self.assertRaises(ValueError): self.ns['compare'](self.a,b)
        self.assertEqual(len(self.a['objects']),2)
    def test_photo_and_camera_still_strict(self):
        for change in ('camera','photo','uv','sha'):
            b=copy.deepcopy(self.a)
            if change=='camera': b['camera_world'][0][3]=.01
            elif change=='photo': b['objects']['photo']['world'][0][0]=.01
            elif change=='uv': b['objects']['photo']['uv'][0][0]=.01
            else: b['source_sha256']='other'
            with self.assertRaises(ValueError): self.ns['compare'](r.source_only(self.a),r.source_only(b))
    def test_proof_contract(self):
        src=(ROOT/'scripts/bvt_yolo_reference_rebase.py').read_text()
        ast.parse(src)
        self.assertIn('g.check_boxes(s,p)',src)
        self.assertIn('g.compare(baseline,g.fingerprint(s,p))',src)
        self.assertIn('np.array_equal(clean,m.rgb',src)
        self.assertIn("new['label']==ref['label']",src)
        self.assertIn("new['manifest']['annotations']==ref['manifest']['annotations']",src)
        self.assertIn("g.sha(control)==p['control_sha256']",src)
        self.assertIn('provisional.replace(archive)',src)

if __name__=='__main__': unittest.main()
