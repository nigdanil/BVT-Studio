"""Contract checks for Alpha/Height/Normal photo-map flow without Blender runtime."""
import ast
import math
import unittest
from pathlib import Path
from _bvt_contract_v02 import assert_registered_modules

ROOT = Path(__file__).resolve().parents[1]
MAPS = ROOT / 'bvt_studio' / 'droplet_maps.py'
HYBRID = ROOT / 'bvt_studio' / 'hybrid_condensation.py'


def pure_functions(*names):
    tree = ast.parse(MAPS.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in names]
    ns = {'isfinite': math.isfinite, 'KINDS': ('alpha', 'height', 'normal')}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<photo maps>', 'exec'), ns)
    return ns


class PhotoDropletMapsTests(unittest.TestCase):
    def test_transform_values_and_validation(self):
        check = pure_functions('check_transform')['check_transform']
        check(.25, -180)
        check(8, 180)
        for scale, angle in ((0, 0), (8.1, 0), (1, -181), (1, 181),
                             (float('nan'), 0), (1, float('inf'))):
            with self.subTest(scale=scale, angle=angle), self.assertRaises(ValueError):
                check(scale, angle)

    def test_channels_are_distinct(self):
        funcs = pure_functions('image_key', 'path_key')
        self.assertEqual([funcs['image_key'](k) for k in ('alpha','height','normal')],
                         ['bvt_droplet_alpha_image', 'bvt_droplet_height_image',
                          'bvt_droplet_normal_image'])
        self.assertEqual(len(set(funcs['path_key'](k) for k in ('alpha','height','normal'))), 3)
        with self.assertRaises(ValueError):
            funcs['image_key']('bad')

    def test_import_packs_independent_images_and_fails_closed(self):
        src = MAPS.read_text(encoding='utf-8')
        for name in ('check_existing=False', 'image.pack()', 'packed_maps_for(obj, mode=mode)',
                     "obj[MODE_KEY] = 'PHOTO_MAPS'", "image.colorspace_settings.name = 'Non-Color'",
                     "image.alpha_mode = 'CHANNEL_PACKED'", 'identical dimensions'):
            self.assertIn(name, src)
        self.assertIn('if not image.packed_file', src)
        self.assertIn('image.users <= int(image.use_fake_user)', src)
        self.assertNotIn('bpy.ops.object.', src)

    def test_true_alpha_height_normal_and_seed_uv(self):
        src = MAPS.read_text(encoding='utf-8')
        for token in ('BVT_Photo_Droplet_Alpha_Grayscale',
                      'BVT_Photo_Droplet_Height_Grayscale',
                      'BVT_Photo_Droplet_Normal_Channels',
                      'BVT_Photo_Droplet_Height_Masked',
                      'BVT_Photo_Droplet_UV_Seed',
                      'seed_offsets(seed)',
                      'BVT_Photo_Droplet_Rotated_X_Masked',
                      'BVT_Photo_Droplet_Rotated_Y_Masked'):
            self.assertIn(token, src)
        self.assertIn("n.extension = 'REPEAT'", src)

    def test_hybrid_source_selective_and_precision_mask(self):
        hybrid = HYBRID.read_text(encoding='utf-8')
        glass = (ROOT/'bvt_studio/glass.py').read_text(encoding='utf-8')
        self.assertIn("== 'PHOTO_MAPS'", hybrid)
        self.assertIn('droplet_photo_channels(', hybrid)
        self.assertIn('atlas = ensure_atlas(obj)', hybrid)
        self.assertIn('left=wet_film', hybrid)
        self.assertIn('apply_precision_mask(', glass)
        self.assertIn("if obj.get('bvt_artifact_preset') in HYBRID_PRESETS", glass)

    def test_registration_panel_and_version(self):
        init = (ROOT/'bvt_studio/__init__.py').read_text(encoding='utf-8')
        ui = (ROOT/'bvt_studio/ui.py').read_text(encoding='utf-8')
        props = (ROOT/'bvt_studio/props.py').read_text(encoding='utf-8')
        self.assertIn('alpha.5-step5', init)
        assert_registered_modules(self, init, 'droplet_maps', 'realistic_atlas',
                                  'optical_water', 'visual_quality_ui', 'glass_v02_ui')
        for key in ('droplet_alpha_path','droplet_height_path','droplet_normal_path',
                    'droplet_map_tiling','droplet_map_rotation'):
            self.assertIn(key, ui)
            self.assertIn(key, props)
        self.assertIn('bvt_studio.assign_droplet_maps', ui)
        self.assertIn('bvt_studio.use_droplet_photos', ui)
        self.assertIn('bvt_studio.use_droplet_procedural', ui)

    def test_blender_gallery_compares_modes_without_mutating_yolo(self):
        script = (ROOT/'scripts/blender_droplet_maps_gallery.py').read_text(encoding='utf-8')
        ast.parse(script)
        for needle in ('--photo', '01_procedural.png', '02_photo_maps.png',
                       '03_photo_seed73.png', '04_masked_photo.png',
                       'load_mask_for_glass', 'packed_maps_for',
                       'BVT PHOTO DROPLETS: OK'):
            self.assertIn(needle, script)
        self.assertNotIn('ZipFile', script)
        persistence = (ROOT/'scripts/blender_droplet_maps_persistence_smoke.py').read_text('utf-8')
        ast.parse(persistence)
        self.assertIn('BVT PHOTO DROPLETS PERSISTENCE: OK', persistence)
        self.assertTrue((ROOT/'tests/test_export_preview.py').exists())


if __name__ == '__main__':
    unittest.main()
