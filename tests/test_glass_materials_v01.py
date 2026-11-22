"""Pure NumPy tests; no Blender/Pillow dependency in existing CI."""
import copy
from pathlib import Path
import sys
import tempfile
import types
import unittest
ROOT=Path(__file__).resolve().parents[1]
if 'bvt_studio' not in sys.modules:
    pkg=types.ModuleType('bvt_studio');pkg.__path__=[str(ROOT/'bvt_studio')];sys.modules['bvt_studio']=pkg
from bvt_studio.glass_material_config import load_library, validate_material, read_material, MATERIAL_IDS
import numpy as np
from bvt_studio.glass_materials import render_materials

class GlassMaterialTests(unittest.TestCase):
    def setUp(self):
        self.lib=load_library(ROOT/'configs/glass_materials')
        self.rgb=np.random.default_rng(11).integers(0,256,(100,120,3),dtype=np.uint8)
        self.r=[4,5,60,95]
    def pane(self,key='clear_glass',seed=72,rect=None,**kw):
        return dict(rect=self.r if rect is None else rect,material=self.lib[key],seed=seed,**kw)
    def test_catalog_complete(self):
        self.assertEqual(tuple(self.lib),MATERIAL_IDS)
        self.assertEqual(self.lib['insulated_glass']['physical_metadata']['layers'],2)
    def test_validation_and_independence(self):
        d=copy.deepcopy(self.lib['tinted_glass']);v=validate_material(d)
        v['appearance']['transmission_rgb'][0]=0
        self.assertNotEqual(d,v)
        for key,bad in [('scatter_mix',float('nan')),('ghost_mix',True),('distortion_fraction',.5),('transmission_rgb',[1,2,1]),('bad',1)]:
            m=copy.deepcopy(d);m['appearance'][key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):validate_material(m)
    def test_clear_contract_rejects_nonidentity(self):
        m=copy.deepcopy(self.lib['clear_glass']);m['appearance']['haze_mix']=.1
        with self.assertRaisesRegex(ValueError,'exact no-op'):validate_material(m)
    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'a.json';p.write_text('{"schema":1,"schema":2}')
            with self.assertRaisesRegex(ValueError,'Duplicate'):read_material(p)
    def test_identity_exact_and_input_immutable(self):
        original=self.rgb.copy();out=render_materials(self.rgb,[self.pane()])
        np.testing.assert_array_equal(out,original);np.testing.assert_array_equal(self.rgb,original)
        self.assertFalse(np.shares_memory(out,self.rgb))
    def test_all_nonclear_distinct_and_localized(self):
        results=[];mask=np.zeros(self.rgb.shape[:2],bool);mask[5:95,4:60]=True
        for i in MATERIAL_IDS[1:]:
            with self.subTest(id=i):
                out=render_materials(self.rgb,[self.pane(i)])
                self.assertEqual(out.shape,self.rgb.shape);self.assertEqual(out.dtype,np.uint8)
                np.testing.assert_array_equal(out[~mask],self.rgb[~mask])
                self.assertGreater(np.mean(np.abs(out[mask].astype(int)-self.rgb[mask].astype(int))),.5)
                self.assertFalse(any(np.array_equal(out,x) for x in results));results.append(out)
    def test_seed_repeat_and_change(self):
        p=self.pane('textured_glass')
        a=render_materials(self.rgb,[p]);b=render_materials(self.rgb,[p]);c=render_materials(self.rgb,[self.pane('textured_glass',73)])
        np.testing.assert_array_equal(a,b);self.assertFalse(np.array_equal(a,c))
    def test_per_pane_isolation_and_order(self):
        a=self.pane('frosted_glass');b=self.pane('coated_glass',rect=[64,5,116,95])
        one=render_materials(self.rgb,[a]);two=render_materials(self.rgb,[b,a]);three=render_materials(self.rgb,[a,b])
        np.testing.assert_array_equal(one[:, :60],two[:, :60]);np.testing.assert_array_equal(two,three)
    def test_mask_zero_is_exact_and_partial(self):
        mask=np.zeros((90,56));mask[:,28:]=1
        out=render_materials(self.rgb,[self.pane('tinted_glass',mask=mask)])
        np.testing.assert_array_equal(out[:,:32],self.rgb[:,:32]);self.assertFalse(np.array_equal(out[:,32:60],self.rgb[:,32:60]))
        np.testing.assert_array_equal(render_materials(self.rgb,[self.pane('frosted_glass',mask=mask*0)]),self.rgb)
    def test_invalid_assignments_fail_closed(self):
        for panes in ([],[self.pane(rect=[0,0,121,10])],[self.pane(seed=-1)],[self.pane(seed=True)],
                      [self.pane(),self.pane('tinted_glass')],[self.pane(mask=np.ones((2,2)))],
                      [self.pane(mask=np.full((90,56),float('nan')))]):
            before=self.rgb.copy()
            with self.assertRaises(ValueError):render_materials(self.rgb,panes)
            np.testing.assert_array_equal(before,self.rgb)
    def test_scattering_reduces_detail(self):
        src=np.tile(((np.indices((100,120)).sum(0)%2)*255).astype(np.uint8)[...,None],(1,1,3))
        out=render_materials(src,[self.pane('frosted_glass')]);roi=out[15:85,15:50,0].astype(float)
        self.assertLess(np.abs(np.diff(roi,axis=1)).mean(),100)
    def test_no_sampling_outside_own_roi(self):
        a=self.rgb.copy();b=a.copy();b[:,:4]=0;b[:,60:]=255;b[:5]=0;b[95:]=255
        p=self.pane('textured_glass')
        np.testing.assert_array_equal(render_materials(a,[p])[5:95,4:60],render_materials(b,[p])[5:95,4:60])

if __name__=='__main__':unittest.main()
