"""Pure Python/NumPy verification. Run via Blender Python for numeric tests."""
import ast
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def module_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

water=module_file('bvt_water_v02_test',ROOT/'bvt_studio'/'water_effects_v02.py')
script=module_file('bvt_gallery_v02_test',ROOT/'scripts'/'bvt_glass_effect_gallery_v02.py')

try:
    import numpy as np
except ImportError:
    np=None


class WaterContract(unittest.TestCase):
    def test_limits(self):
        with self.assertRaises(ValueError):water.validated_config({'bad':1})
        with self.assertRaises(ValueError):water.validated_config({'macro_count':-1})
        with self.assertRaises(ValueError):water.validated_config({'streak_taper':float('nan')})
        with self.assertRaises(ValueError):water.validated_config({'micro_count':1.5})
        with self.assertRaises(ValueError):water.generate_water_arrays(kind='bad')
        with self.assertRaises(ValueError):water.generate_water_arrays(seed=-1)
    def test_source_scripts_valid(self):
        for p in (ROOT/'bvt_studio').glob('*.py'):
            ast.parse(p.read_text('utf8'))
        for p in (ROOT/'scripts').glob('*.py'):
            ast.parse(p.read_text('utf8'))
    def test_json_variants(self):
        config=json.loads((ROOT/'configs'/'effects_gallery_v02.json').read_text('utf8'))
        self.assertEqual(config['schema'],'bvt.glass-gallery.v02')
        self.assertEqual(len(config['variants']),13)
        self.assertIn('12_stress_optics',config['variants'])
        self.assertFalse(config['variants']['10_combined_water_optics'].get('stress',False))
        self.assertTrue(config['variants']['12_stress_optics']['stress'])
        for key,variant in config['variants'].items():
            if 'water' in variant:
                water.validated_config(variant['water'].get('params',{}))
    def test_geometry_rects(self):
        rects=ROOT/'configs'/'bvt_freezer_glass_rects_v02_default.json'
        self.assertEqual(len(script.rects_validate(rects,1672,941)),4)
        with self.assertRaises(ValueError):script.rects_validate(rects,800,600)


@unittest.skipUnless(np is not None,'Blender NumPy required for numeric tests')
class WaterNumerics(unittest.TestCase):
    def test_seed_reproducible_and_distinct(self):
        a,ea=water.generate_water_arrays(kind='MACRO',seed=72,resolution=256)
        b,eb=water.generate_water_arrays(kind='MACRO',seed=72,resolution=256)
        c,ec=water.generate_water_arrays(kind='MACRO',seed=73,resolution=256)
        for key in ('alpha','height','normal'):
            np.testing.assert_array_equal(a[key],b[key])
        self.assertEqual(ea,eb)
        self.assertGreater(np.mean(abs(a['alpha']-c['alpha'])),.002)
        self.assertEqual(len(ea),water.DEFAULTS['macro_count'])
    def test_isolated_families_counts_and_range(self):
        types={'MACRO':'macro','MICRO':'micro','RUNNING':'streak'}
        counts={'MACRO':'macro_count','MICRO':'micro_count','RUNNING':'streak_count'}
        for kind,expected in types.items():
            with self.subTest(kind=kind):
                imgs,events=water.generate_water_arrays(kind=kind,resolution=256,seed=42,
                    config={'macro_count':8,'micro_count':100,'streak_count':4})
                self.assertEqual(len(events),{'MACRO':8,'MICRO':100,'RUNNING':4}[kind])
                self.assertTrue(all(ev['type']==expected for ev in events))
                for image in imgs.values():
                    self.assertEqual(image.shape,(256,256,3))
                    self.assertTrue(np.isfinite(image).all())
                    self.assertGreaterEqual(image.min(),0)
                    self.assertLessEqual(image.max(),1)
                self.assertGreater(np.count_nonzero(imgs['alpha'][:,:,0]>.2),20)
    def test_streaks_really_elongated(self):
        _,events=water.generate_water_arrays(kind='RUNNING',resolution=512,seed=72,
            config={'streak_count':6,'streak_length_px':320,'streak_width_px':9})
        heights=[e['uv_bbox'][3]-e['uv_bbox'][1] for e in events]
        widths=[e['uv_bbox'][2]-e['uv_bbox'][0] for e in events]
        self.assertGreater(min(heights),.28)
        self.assertGreater(min(h/w for h,w in zip(heights,widths)),5)
    def test_render_qa_counts_visible_events(self):
        original=np.zeros((200,300,3),dtype=np.float32)
        modified=original.copy()
        modified[60:100,60:130]=.15
        rects=[[10,10,290,190]]
        event=[{'type':'macro','uv_bbox':[.15,.45,.45,.8]}]
        report=script.visibility_qa(original,modified,rects,[event])
        self.assertEqual(report['leakage_pixels_beyond_3px_geometry_guard'],0)
        self.assertGreater(report['changed_ratio_in_rects'],0)
        modified[0:5,0:5]=.1
        bad=script.visibility_qa(original,modified,rects,[event])
        self.assertEqual(bad['leakage_pixels_beyond_3px_geometry_guard'],25)


if __name__=='__main__':unittest.main()
