"""Independent realistic atlas contracts and deterministic image-array tests."""
import ast
import importlib.util
import unittest
from pathlib import Path
try:
    import numpy as np
except ModuleNotFoundError as exc:
    if exc.name != 'numpy':
        raise
    np = None

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'bvt_studio' / 'realistic_atlas.py'
DROPLETS = ROOT / 'bvt_studio' / 'droplet_maps.py'

# Import only pure functions so system Python need not have bpy installed.
tree = ast.parse(SCRIPT.read_text(encoding='utf-8'))
pure_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name in ('validate_atlas','generate_atlas_arrays')]
ns = {'__name__': 'atlas_pure_test'}
from math import isfinite
ns['isfinite'] = isfinite
exec(compile(ast.Module(body=pure_nodes, type_ignores=[]), str(SCRIPT),'exec'), ns)
validate = ns['validate_atlas']
generate = ns['generate_atlas_arrays']


class RealisticAtlasTests(unittest.TestCase):
    def test_bad_generator_settings_are_rejected(self):
        for args in [(True,512,1.,.3),(-1,512,1.,.3),
                     (1,128,1.,.3),(1,512,0.,.3),
                     (1,512,float('nan'),.3),(1,512,1.,-1),
                     (1,512,1.,float('inf'))]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                validate(*args)
        validate(72,256,.25,0.)
        validate(72,512,2.,1.)

    def test_third_mode_keeps_photo_maps_in_independent_slots(self):
        src = DROPLETS.read_text('utf-8')
        for token in ("'REALISTIC_ATLAS'", "'PHOTO_MAPS'",
                      "'bvt_atlas_'", "'bvt_droplet_'",
                      "target_mode='PHOTO_MAPS'", "packed_maps_for(obj, mode=mode)",
                      "obj[MODE_KEY] = 'PHOTO_MAPS'", "obj[MODE_KEY] = 'REALISTIC_ATLAS'"):
            self.assertIn(token, src)
        self.assertIn('generate_realistic_atlas', (ROOT/'bvt_studio/ui.py').read_text('utf-8'))
        self.assertIn('realistic_atlas, optical_water)', (ROOT/'bvt_studio/__init__.py').read_text('utf-8'))
        self.assertIn("== 'REALISTIC_ATLAS'", (ROOT/'bvt_studio/hybrid_condensation.py').read_text('utf-8'))

    def test_inactive_map_bank_survives_blend_save_reopen(self):
        """Packed orphan PNG IDs require Fake User; the two modes are never used simultaneously."""
        tree = ast.parse(DROPLETS.read_text(encoding='utf-8'))
        importer = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'import_droplet_maps')
        fake_user_enabled = any(
            isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Attribute) and target.attr == 'use_fake_user'
                for target in node.targets) and
            isinstance(node.value, ast.Constant) and node.value.value is True
            for node in ast.walk(importer)
        )
        self.assertTrue(fake_user_enabled, 'Packed inactive maps must have Blender Fake User')
        self.assertIn('old_image.users <= int(old_image.use_fake_user)',
                      DROPLETS.read_text(encoding='utf-8'))
        persistence = (ROOT / 'scripts/blender_realistic_atlas_persistence_smoke.py').read_text('utf-8')
        self.assertIn('if not im.use_fake_user:', persistence)

    def test_gallery_compares_all_three_modes_and_persists_maps(self):
        script = (ROOT/'scripts/blender_realistic_droplet_atlas_gallery.py').read_text('utf-8')
        persistence = (ROOT/'scripts/blender_realistic_atlas_persistence_smoke.py').read_text('utf-8')
        ast.parse(script)
        ast.parse(persistence)
        for token in ('01_procedural.png','02_photo_maps.png','03_realistic_atlas.png',
                      '04_atlas_seed73.png','05_realistic_masked.png',
                      'preview_dir=out','realistic_atlas_manifest.json',
                      "packed_maps_for(first, mode='PHOTO_MAPS')",'BVT REALISTIC ATLAS: OK'):
            self.assertIn(token, script)
        for token in ('REALISTIC_ATLAS','PHOTO_MAPS','MASK_ENABLED_KEY',
                      'BVT REALISTIC ATLAS PERSISTENCE: OK'):
            self.assertIn(token, persistence)
        for fn in ('annotation.py','annotation_manager.py','quality_gate.py','export_preview.py'):
            self.assertTrue((ROOT/'bvt_studio'/fn).exists())

    @unittest.skipUnless(np is not None,'NumPy arrays require Blender Python or system NumPy')
    def test_reproducible_arrays_and_provenance(self):
        a=generate(72,256,.8,.25)
        b=generate(72,256,.8,.25)
        self.assertEqual(set(a),{'alpha','height','normal'})
        for key in a:
            self.assertEqual(a[key].shape,(256,256,3))
            self.assertEqual(a[key].dtype,np.float32)
            self.assertTrue(np.array_equal(a[key],b[key]))
            self.assertTrue(np.isfinite(a[key]).all())
            self.assertGreaterEqual(float(a[key].min()),0.)
            self.assertLessEqual(float(a[key].max()),1.)
        self.assertTrue(np.allclose(a['normal'][:,:,2],1.,atol=.2))

    @unittest.skipUnless(np is not None,'NumPy arrays require Blender Python or system NumPy')
    def test_density_seed_and_streaks_change_output(self):
        a=generate(72,256,.25,0.)
        b=generate(72,256,1.7,0.)
        c=generate(73,256,1.7,0.)
        d=generate(72,256,1.7,.9)
        self.assertGreater(float(np.count_nonzero(b['alpha'][:,:,0]>.05)),
                           float(np.count_nonzero(a['alpha'][:,:,0]>.05)))
        self.assertGreater(float(np.mean(np.abs(b['height']-c['height']))),.005)
        self.assertGreater(float(np.mean(np.abs(b['height']-d['height']))),.0001)

    @unittest.skipUnless(np is not None,'NumPy arrays require Blender Python or system NumPy')
    def test_normals_are_nonflat_and_alpha_has_clear_glass(self):
        a=generate(72,256,1.,.5)
        mask=a['alpha'][:,:,0]
        fraction=float(np.mean(mask>.08))
        self.assertGreater(fraction,.03)
        self.assertLess(fraction,.93)
        self.assertGreater(float(np.std(a['normal'][:,:,0])),.012)
        self.assertGreater(float(np.std(a['normal'][:,:,1])),.012)
        self.assertLess(float(np.max(np.abs(a['normal'][:,:,0]-.5))),.5)


if __name__ == '__main__':
    unittest.main()
