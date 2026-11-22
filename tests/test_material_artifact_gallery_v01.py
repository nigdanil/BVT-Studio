"""Host-side planning tests; live rendering is verified separately in Blender."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from bvt_material_artifact_gallery import (MATERIALS,EFFECTS,PILOT_MATERIALS,PILOT_EFFECTS,make_plan,read_json)


class MaterialArtifactGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.blend=Path(self.temp.name)/'placeholder.blend';self.blend.write_bytes(b'planner only; not a real Blender file')
    def plan(self,materials=PILOT_MATERIALS,effects=PILOT_EFFECTS,seed=72):
        return make_plan(ROOT,self.blend,materials,effects,seed)
    def test_pilot(self):
        p=self.plan();self.assertEqual(len(p['jobs']),9);self.assertEqual(p['labels_status'],'UNLABELED')
        self.assertEqual(p['jobs'][0]['id'],'clear_glass__00_clean')
    def test_full_matrix_and_roles(self):
        p=self.plan(MATERIALS,EFFECTS);self.assertEqual(len(p['jobs']),84)
        self.assertEqual(len({j['id'] for j in p['jobs']}),84)
        self.assertEqual(sum(j['role']=='QA_ONLY' for j in p['jobs']),18)
        self.assertTrue(all(j['role']=='QA_ONLY' for j in p['jobs'] if j['effect']=='12_stress_optics'))
    def test_controls_precede_or_equal_job(self):
        p=self.plan(('textured_glass',),('07_macro_droplets_only',));seen=set()
        self.assertEqual(len(p['jobs']),4)
        for job in p['jobs']:
            seen.add(job['id']);self.assertIn(job['material_baseline'],seen);self.assertIn(job['artifact_baseline'],seen)
    def test_deterministic_order_and_seed(self):
        p=self.plan();self.assertEqual(p,self.plan(tuple(reversed(PILOT_MATERIALS)),tuple(reversed(PILOT_EFFECTS))))
        q=self.plan(seed=99);self.assertNotEqual(p,q)
        self.assertTrue(all(x['glass']['Glass_p_001']['seed']==99 for x in q['presets'].values()))
        self.assertTrue(all(j['seed']==99 for j in q['jobs']))
    def test_bad_selection_and_seed(self):
        for args in [(('clear_glass','clear_glass'),PILOT_EFFECTS,72),(('bad',),PILOT_EFFECTS,72),(PILOT_MATERIALS,('bad',),72),(PILOT_MATERIALS,PILOT_EFFECTS,True),(PILOT_MATERIALS,PILOT_EFFECTS,2**31)]:
            with self.assertRaises(ValueError): self.plan(*args)
    def test_input_hash_changes(self):
        p=self.plan();self.blend.write_bytes(b'changed');self.assertNotEqual(p['input_blend_sha256'],self.plan()['input_blend_sha256'])
    def test_no_mutation_and_duplicate_json(self):
        p=self.plan(seed=99)
        r=next((ROOT/'examples/freezer_planogram/configs/presets/single_glass').rglob('07_macro_droplets_only.json'))
        self.assertNotEqual(p['presets']['07_macro_droplets_only']['glass']['Glass_p_001']['seed'],read_json(r)['glass']['Glass_p_001']['seed'])
        f=Path(self.temp.name)/'duplicate.json';f.write_text('{"x":1,"x":2}',encoding='utf8')
        with self.assertRaises(ValueError): read_json(f)

if __name__=='__main__': unittest.main()
