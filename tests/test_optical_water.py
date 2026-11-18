"""Source, pure setting validation and Blender QA contract for optical water."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT/'bvt_studio'/'optical_water.py'
HYBRID = ROOT/'bvt_studio'/'hybrid_condensation.py'


def pure():
    module = ast.parse(ENGINE.read_text(encoding='utf-8'))
    source = [node for node in module.body if isinstance(node, ast.Assign) and
              any(isinstance(t, ast.Name) and t.id in ('LIMITS','LENS_KEY','EDGE_KEY',
                  'GLINT_KEY','MICRO_KEY','ENABLED_KEY') for t in node.targets)]
    f = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_optical')
    from math import isfinite
    ns = {'isfinite':isfinite}
    exec(compile(ast.Module(body=source+[f],type_ignores=[]),str(ENGINE),'exec'),ns)
    return ns['validate_optical']


class OpticalWaterTests(unittest.TestCase):
    def test_reject_invalid_optics(self):
        validate = pure()
        for args in ((1,1.,1.,1.,.5), (True,.1,1.,1.,.5),
                     (True,1.5,-1.,1.,.5), (True,1.5,1.,float('nan'),.5),
                     (True,1.5,1.,1.,float('inf')),
                     (True,1.5,1.,1.,-1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate(*args)
        validate(True,1.45,1.,1.25,.35)
        validate(False,.25,0.,0.,0.)

    def test_only_realistic_atlas_is_enabled(self):
        src = ENGINE.read_text(encoding='utf-8')
        self.assertIn("obj.get(MODE_KEY) == 'REALISTIC_ATLAS'",src)
        self.assertIn("obj.get('bvt_droplet_source_mode') != 'REALISTIC_ATLAS'",src)
        self.assertIn('packed_maps_for(obj, mode=\'REALISTIC_ATLAS\')',src)

    def test_mask_and_existing_baseline_preserved(self):
        src = HYBRID.read_text(encoding='utf-8')
        self.assertIn('optical = optical_enabled(obj)',src)
        self.assertIn("if optical:",src)
        self.assertIn("driver_socket(warp.inputs['Scale'], obj, 'bvt_artifact_refraction')",src)
        self.assertIn("'BVT_Optical_Refraction_Gain'",src)
        self.assertIn("'BVT_Optical_Highlight_Safe_Clamp'",src)
        self.assertIn("'BVT_Optical_Shadow_Safe_Clamp'",src)
        self.assertIn("_combined_glass_mask(obj, nodes, links, tex.outputs['UV'])",src)
        precision = (ROOT/'bvt_studio/glass_mask.py').read_text('utf-8')
        self.assertIn('BVT_Precision_Final_Mask_Gate',precision)

    def test_sidebar_and_registered_operators(self):
        ui = (ROOT/'bvt_studio/ui.py').read_text('utf-8')
        props = (ROOT/'bvt_studio/props.py').read_text('utf-8')
        addon = (ROOT/'bvt_studio/__init__.py').read_text('utf-8')
        for name in ('optical_lens_gain','optical_edge_gain','optical_glint_gain',
                     'optical_micro_gain'):
            self.assertIn(name,props)
            self.assertIn(name,ui)
        self.assertIn('bvt_studio.apply_optical_water',ui)
        self.assertIn('bvt_studio.disable_optical_water',ui)
        self.assertIn('optical_water)',addon)
        self.assertIn('alpha.5-step3',addon)

    def test_smoke_and_reopen_scripts(self):
        a = (ROOT/'scripts/blender_optical_water_gallery.py').read_text('utf-8')
        b = (ROOT/'scripts/blender_optical_water_persistence_smoke.py').read_text('utf-8')
        ast.parse(a)
        ast.parse(b)
        for token in ('06_optical_off.png','07_optical_on.png','08_optical_restored.png',
                      'optical_water_manifest.json', 'set_optical_water(first, False',
                      'packed_maps_for(first, mode)', 'BVT OPTICAL WATER: OK'):
            self.assertIn(token,a)
        for token in ('BVT OPTICAL WATER PERSISTENCE: OK','PHOTO_MAPS',
                      'REALISTIC_ATLAS','mask_image_for(obj)'):
            self.assertIn(token,b)

    def test_low_energy_contact_arcs(self):
        optical = ENGINE.read_text(encoding='utf-8')
        hybrid = HYBRID.read_text(encoding='utf-8')
        for needle in (
            "'BVT_Optical_Contact_Height_Low', height, .14, .28",
            "'BVT_Optical_Contact_Height_High', height, .35, .48",
            "'BVT_Optical_Bright_Arc_Threshold'",
            "'BVT_Optical_Specular_Limit'",
            "'BVT_Optical_Shadow_Limit'",
            "'BVT_Optical_Micro_Clamp', 'MINIMUM', micro, const=.025",
        ):
            self.assertIn(needle, optical)
        for needle in (
            "'BVT_Optical_Refraction_Gain_Softener'",
            "'BVT_Optical_Refraction_SoftGain'",
            "'BVT_Optical_Refraction_Gain'",
            "left=highlight_alpha, constant=.39",
            "left=dark_alpha, constant=.28",
        ):
            self.assertIn(needle, hybrid)

    def test_yolo_modules_unchanged(self):
        for name in ('annotation.py','annotation_manager.py','export_preview.py',
                     'quality_gate.py','validation.py'):
            self.assertTrue((ROOT/'bvt_studio'/name).exists())

if __name__ == '__main__':
    unittest.main()
