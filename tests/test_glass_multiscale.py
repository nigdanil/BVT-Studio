"""Dependency-free contracts for v0.4 alpha.2 procedural glass."""
import ast
import importlib.util
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('artifact_config', ROOT/'bvt_studio/artifact_config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class MultiScaleGlassTests(unittest.TestCase):
    def test_defaults_are_in_range(self):
        self.assertEqual(config.validate_shape_params(1.0, .35), (1.0, .35))
        self.assertEqual(config.validate_shape_params(.5, 0), (.5, 0.0))
        self.assertEqual(config.validate_shape_params(2, 1), (2.0, 1.0))

    def test_bad_shape_inputs_rejected(self):
        for size, edge in ((.49, .2), (2.01, .2), (1, -0.01), (1, 1.01),
                           (float('nan'), .5), (1, float('inf'))):
            with self.subTest(size=size, edge=edge), self.assertRaises(ValueError):
                config.validate_shape_params(size, edge)

    def test_shape_validation_does_not_touch_rng(self):
        original = config.seed_offsets(72)
        config.validate_shape_params(1.35, .62)
        self.assertEqual(config.seed_offsets(72), original)

    def test_named_masks_and_seeded_frost(self):
        s = (ROOT/'bvt_studio/glass.py').read_text(encoding='utf-8')
        for name in ('BVT_Droplets_Voronoi', 'BVT_Droplets_Warped_UV',
                     'BVT_Droplets_Large_Gate', 'BVT_Frost_Islands',
                     'BVT_Frost_Crystals', 'BVT_Frost_Edge_Mask'):
            with self.subTest(name=name):
                self.assertIn(name, s)
        self.assertIn("droplet_ring('_Fine', 105.0", s)
        self.assertIn("droplet_ring('_Large', 14.0", s)
        self.assertIn("links.new(offset.outputs['Vector'], frost_islands.inputs['Vector'])", s)
        self.assertIn("links.new(offset.outputs['Vector'], frost_crystals.inputs['Vector'])", s)
        self.assertIn("driver_socket(scale.inputs[0], obj, 'bvt_artifact_droplet_scale')", s)
        self.assertIn("driver_socket(frost_edge_weight.inputs[1], obj, 'bvt_artifact_frost_edge')", s)

    def test_property_ui_and_export_manifest(self):
        props = (ROOT/'bvt_studio/props.py').read_text(encoding='utf-8')
        ui = (ROOT/'bvt_studio/ui.py').read_text(encoding='utf-8')
        manifest = (ROOT/'bvt_studio/annotation.py').read_text(encoding='utf-8')
        for name in ('artifact_droplet_scale', 'artifact_frost_edge'):
            self.assertIn(name, props)
            self.assertIn(name, ui)
            self.assertIn(name, manifest)

    def test_glass_material_keeps_target_independent(self):
        s = (ROOT/'bvt_studio/glass.py').read_text(encoding='utf-8')
        self.assertIn("if mat and mat.get('bvt_studio_glass') and mat.users == 1", s)
        self.assertIn("obj['bvt_role'] = 'glass_overlay'", s)
        self.assertNotIn('bpy.ops.object.transform_apply', s)

    def test_blender_smoke_runs_multiscale_checks(self):
        s = (ROOT/'scripts/blender_glass_artifacts_smoke.py').read_text('utf-8')
        ast.parse(s)
        self.assertIn('BVT_Droplets_Voronoi_Large', s)
        self.assertIn('BVT_Frost_Edge_Mask', s)
        self.assertIn('Droplet Scale driver missing', s)

if __name__ == '__main__':
    unittest.main()
