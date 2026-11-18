"""Hybrid Condensation contracts; numeric atlas tests need NumPy (bundled in Blender)."""
import ast
import importlib.util
import unittest
from pathlib import Path
# System Python may lack NumPy while Blender ships it. Keep structural tests
# runnable without optional host dependencies; the numerical tests are then
# exercised with Blender's own Python.
try:
    import numpy as np
except ModuleNotFoundError as exc:
    if exc.name != 'numpy':
        raise
    np = None

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'bvt_studio' / 'hybrid_condensation.py'
spec = importlib.util.spec_from_file_location('_bvt_hybrid_atlas_test', P)
hybrid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)


class HybridCondensationTests(unittest.TestCase):
    @unittest.skipUnless(np is not None, "Numerical atlas checks require NumPy; run with Blender Python")
    def test_same_seed_same_data(self):
        a = hybrid.make_condensation_atlas(72, .7, 1.25, .72, .65, .72, size=256)
        b = hybrid.make_condensation_atlas(72, .7, 1.25, .72, .65, .72, size=256)
        self.assertTrue(np.array_equal(a, b))
        self.assertEqual(a.shape, (256, 256, 4))
        self.assertEqual(a.dtype, np.float32)

    @unittest.skipUnless(np is not None, "Numerical atlas checks require NumPy; run with Blender Python")
    def test_seed_changes_height_and_wet_film(self):
        a = hybrid.make_condensation_atlas(72, .65, 1., .72, .5, .6, size=256)
        b = hybrid.make_condensation_atlas(73, .65, 1., .72, .5, .6, size=256)
        self.assertGreater(np.mean(np.abs(a[:, :, 0] - b[:, :, 0])), .002)
        self.assertGreater(np.mean(np.abs(a[:, :, 3] - b[:, :, 3])), .002)

    @unittest.skipUnless(np is not None, "Numerical atlas checks require NumPy; run with Blender Python")
    def test_shape_and_normals_plausible(self):
        a = hybrid.make_condensation_atlas(42, .7, 1.0, .72, .7, .7, size=256)
        self.assertTrue(np.isfinite(a).all())
        self.assertGreaterEqual(float(a.min()), 0.)
        self.assertLessEqual(float(a.max()), 1.)
        self.assertGreater(float(a[:, :, 0].max()), .6)
        # Non-empty and non-uniform curvature on a 2D glass plane.
        self.assertGreater(float(np.std(a[:, :, 1])), .015)
        self.assertGreater(float(np.std(a[:, :, 2])), .015)
        self.assertGreater(float(np.mean(a[:, :, 0] > .1)), .01)
        self.assertLess(float(np.mean(a[:, :, 0] > .1)), .95)

    @unittest.skipUnless(np is not None, "Numerical atlas checks require NumPy; run with Blender Python")
    def test_coverage_modulates_occupied_fraction(self):
        low = hybrid.make_condensation_atlas(72, .18, 1., .72, .5, .6, size=256)
        high = hybrid.make_condensation_atlas(72, .85, 1., .72, .5, .6, size=256)
        lo = float(np.mean(low[:, :, 0] > .15))
        hi = float(np.mean(high[:, :, 0] > .15))
        self.assertGreater(hi, lo)

    @unittest.skipUnless(np is not None, "Numerical atlas checks require NumPy; run with Blender Python")
    def test_clear_glass_is_clear(self):
        a = hybrid.make_condensation_atlas(12, 0, 1., .72, .7, 0, size=256)
        self.assertTrue(np.all(a[:, :, 0] == 0))
        self.assertTrue(np.all(a[:, :, 3] == 0))
        self.assertTrue(np.all(a[:, :, 1:3] == .5))

    @unittest.skipUnless(np is not None, "Numerical atlas checks require NumPy; run with Blender Python")
    def test_reject_invalid_settings(self):
        for params in [(1, -0.1, 1, .7, 1, 1), (1, 2, 1, .7, 1, 1),
                       (1, .2, 0, .7, 1, 1), (1, .2, 1, -1, 1, 1),
                       (1, .2, 1, .7, -1, 1),
                       (1, .2, 1, .7, 1, float('nan')),
                       (-1, .2, 1, .7, 1, 1)]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                hybrid.make_condensation_atlas(*params, size=128)

    def test_shader_contract_and_per_glass_independence(self):
        src = P.read_text(encoding='utf-8')
        for label in ('BVT_Hybrid_Atlas', 'BVT_Hybrid_Refracted_Photo',
                      'BVT_Hybrid_Dark_Rim_Overlay', 'BVT_Hybrid_Specular_Overlay',
                      'BVT_Hybrid_Glass_Mask', "image['bvt_atlas_parameters']", "obj.get('bvt_glass_uid')",
                      "image.pixels.foreach_set", "photo_coord.object = source"):
            self.assertIn(label, src)
        self.assertNotIn('bpy.ops.object.', src)
        self.assertNotIn('obj.location =', src)
        self.assertNotIn('obj.scale =', src)
        self.assertEqual(ast.parse(src).type_ignores, [])

    def test_preset_isolation_and_ui(self):
        glass = (ROOT/'bvt_studio/glass.py').read_text(encoding='utf-8')
        ui = (ROOT/'bvt_studio/ui.py').read_text(encoding='utf-8')
        presets = (ROOT/'bvt_studio/artifact_presets.py').read_text(encoding='utf-8')
        self.assertIn("if obj.get('bvt_artifact_preset') in HYBRID_PRESETS", glass)
        self.assertIn('build_realistic_glass(obj', glass)
        for v in ('hybrid_wetness', 'hybrid_macro', 'hybrid_micro', 'artifact_mask_inset', 'artifact_mask_feather',
                  'artifact_aperture_left', 'artifact_aperture_right', 'artifact_aperture_bottom',
                  'artifact_aperture_top', 'artifact_aperture_feather'):
            self.assertIn(v, ui)
            self.assertIn(v, presets)
            self.assertIn(v, (ROOT/'bvt_studio/props.py').read_text())
        self.assertIn('alpha.5-step5', (ROOT/'bvt_studio/__init__.py').read_text())

    def test_gallery_opt_in_photo_and_no_zip(self):
        p = ROOT / 'scripts/blender_hybrid_condensation_gallery.py'
        s = p.read_text(encoding='utf-8')
        ast.parse(s)
        self.assertIn('--photo', s)
        self.assertIn('bpy.ops.render.render(write_still=True)', s)
        self.assertIn('04_hybrid_heavy_seed73.png', s)
        self.assertIn('HYBRID_QA_DIR=', s)
        self.assertIn('render_size', s)
        self.assertNotIn('ZipFile', s)


if __name__ == '__main__':
    unittest.main()
