"""v0.2.1 regression: neutral atlas, unbiased RGB QA, no water events."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

WATER=load('water_021',ROOT/'bvt_studio/water_effects_v02.py')
GALLERY=load('gallery_021',ROOT/'scripts/bvt_glass_effect_gallery_v02.py')

def neutral(cfg):
    c=WATER.validated_config(cfg)
    return dict(c,macro_count=0,micro_count=0,streak_count=0)

class WaterQACalibrationTests(unittest.TestCase):
    def test_neutral_all_families_are_exactly_empty(self):
        for kind in WATER.KINDS:
            for seed in (0,72,74):
                with self.subTest(kind=kind,seed=seed):
                    textures,events=WATER.generate_water_arrays(
                        kind=kind,seed=seed,resolution=256,config=neutral({}))
                    self.assertEqual(events,[])
                    self.assertEqual(float(np.max(np.abs(textures['alpha']))),0.)
                    self.assertEqual(float(np.max(np.abs(textures['height']))),0.)
                    self.assertTrue(np.array_equal(textures['normal'][:,:,0],
                                                   np.full((256,256),.5,dtype=np.float32)))
                    self.assertTrue(np.array_equal(textures['normal'][:,:,1],
                                                   np.full((256,256),.5,dtype=np.float32)))
                    self.assertTrue(np.array_equal(textures['normal'][:,:,2],
                                                   np.ones((256,256),dtype=np.float32)))

    def test_null_same_image_produces_exactly_zero_visibility(self):
        rng=np.random.default_rng(45)
        baseline=rng.random((120,180,3)).astype(np.float32)
        rects=[[10,5,85,110],[90,5,175,110]]
        events=[[],[]]
        report=GALLERY.visibility_qa(baseline,baseline.copy(),rects,events)
        self.assertEqual(report['changed_ratio_in_rects'],0.0)
        self.assertEqual(report['leakage_pixels_beyond_3px_geometry_guard'],0)
        self.assertTrue(all(p[k]['visible_proxy']==0 for p in report['per_glass_event_visibility_proxy']
                            for k in ('macro','micro','streak')))

    def test_small_png_quantization_noise_does_not_create_visibility(self):
        a=np.zeros((100,100,3),dtype=np.float32)
        b=a.copy()
        b[25:70,25:70]=2/255
        r=GALLERY.visibility_qa(a,b,[[10,10,90,90]],
                [[{'type':'macro','uv_bbox':[.2,.2,.8,.8]}]])
        self.assertEqual(r['changed_ratio_in_rects'],0.)
        self.assertEqual(r['per_glass_event_visibility_proxy'][0]['macro']['visible_proxy'],0)

    def test_true_macro_and_running_delta_detected(self):
        a=np.zeros((180,180,3),dtype=np.float32)
        b=a.copy()
        b[55:105,45:65]=.3
        rects=[[10,10,170,170]]
        event=[{'type':'streak','uv_bbox':[.20,.35,.45,.80]}]
        report=GALLERY.visibility_qa(a,b,rects,[event])
        self.assertGreater(report['changed_ratio_in_rects'],0.)
        self.assertEqual(report['per_glass_event_visibility_proxy'][0]['streak']['visible_proxy'],1)

    def test_same_shader_signature_ignores_texture_pixel_content(self):
        from types import SimpleNamespace as N
        node_a=N(name='ShaderAlpha',bl_idname='ShaderNodeTexImage')
        node_b=N(name='ShaderOutput',bl_idname='ShaderNodeOutputMaterial')
        links=[N(from_node=node_a,to_node=node_b,
                 from_socket=N(identifier='Color'),to_socket=N(identifier='Surface'))]
        obj=N(active_material=N(use_nodes=True,node_tree=N(nodes=[node_a,node_b],links=links)))
        self.assertEqual(GALLERY.shader_signature(obj),GALLERY.shader_signature(obj))

    def test_gallery_does_not_render_procedural_as_wateroff(self):
        source=(ROOT/'scripts/bvt_glass_effect_gallery_v02.py').read_text('utf8')
        self.assertIn("neutral[count_key]=0",source)
        self.assertIn("assert_neutral_maps(packed_maps_for(obj,mode='REALISTIC_ATLAS'))",source)
        self.assertIn("zero_water_rebuild.png",source)
        self.assertIn("'baseline_mode']='REALISTIC_ATLAS_NEUTRAL_SAME_SHADER'",source)
        self.assertIn('signatures[name]!=shader_signature(obj)',source)
        self.assertIn('state_signatures[name]!=shader_state_signature(obj)',source)
        self.assertIn("'zero_water_test':zero_water_report",source)
        self.assertLess(source.index('for index,obj,name,seed,waterspec,cfg,optics,stress in pending_water:\n            neutral=dict(cfg)'),
                        source.index("scene.render.filepath=str(water_baseline)"))

if __name__=='__main__':unittest.main()
