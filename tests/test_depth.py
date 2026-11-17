"""Unit checks for Layer Depth API, without Blender runtime.

Geometry math is verified independently; an actual rotated constraint evaluation
must be tested by the companion Blender smoke test.
"""
import ast
import math
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'bvt_studio' / 'depth.py'


class FakeConstraint(dict):
    def __init__(self, kind='LIMIT_LOCATION'):
        super().__init__()
        self.type = kind
        self.name = ''
        self.mute = False


class FakeConstraints:
    def __init__(self):
        self.items = {}

    def get(self, name):
        return self.items.get(name)

    def new(self, type):
        c = FakeConstraint(type)
        c.name = '__unnamed__'
        self.items[c.name] = c
        return c


class FakeObject(dict):
    def __init__(self):
        super().__init__()
        self.constraints = FakeConstraints()
        self.name = 'Glass_p_001'


class TestLayerDepth(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in {'_world_meters_to_local_z', '_set_limit'}]
        env = {'math': math, 'MIN_AXIS_LENGTH': 1e-8,
               'DEPTH_CONSTRAINT': 'BVT_Studio_Photo_Relative_Depth',
               'CONSTRAINT_MARKER': '_bvt_studio_owns_depth_constraint'}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), env)
        self.f = env

    def test_axis_scale_conversion(self):
        # Photo rotated 30 deg X and 20 deg Y with 2.5 Z-scale. A 12 mm
        # distance along its normal must convert to 0.0048 local units.
        for side in (-1.0, 1.0):
            z = self.f['_world_meters_to_local_z'](0.012, 2.5, side)
            self.assertAlmostEqual(z, side * 0.0048)
            self.assertAlmostEqual(z * 2.5 * side, 0.012)

    def test_reject_invalid_axis(self):
        with self.assertRaises(ValueError):
            self.f['_world_meters_to_local_z'](0.012, 0.0, 1.0)
        with self.assertRaises(ValueError):
            self.f['_world_meters_to_local_z'](float('nan'), 1.0, 1.0)

    def test_constraint_references_photo_custom_space_only_z(self):
        obj = FakeObject()
        source = object()
        self.f['_set_limit'](obj, source, 0.021, True)
        c = list(obj.constraints.items.values())[0]
        self.assertIs(c.space_object, source)
        self.assertEqual(c.owner_space, 'CUSTOM')
        self.assertTrue(c.use_transform_limit)
        self.assertTrue(c.use_min_z and c.use_max_z)
        self.assertFalse(c.use_min_x or c.use_max_x)
        self.assertFalse(c.use_min_y or c.use_max_y)
        self.assertAlmostEqual(c.min_z, c.max_z)
        self.assertFalse(c.mute)

    def test_constraint_mute_and_enable_reuses_existing(self):
        obj = FakeObject()
        source = object()
        self.f['_set_limit'](obj, source, 0.02, True)
        c = list(obj.constraints.items.values())[0]
        # Fake constraints don't auto-key by Blender's name property.
        obj.constraints.items.clear()
        obj.constraints.items[c.name] = c
        self.f['_set_limit'](obj, source, 0.02, False)
        self.assertTrue(c.mute)
        self.f['_set_limit'](obj, source, 0.03, True)
        self.assertFalse(c.mute)
        self.assertEqual(len(obj.constraints.items), 1)
        self.assertAlmostEqual(c.min_z, 0.03)

    def test_refuse_unrelated_constraint_with_reserved_name(self):
        obj = FakeObject()
        c = FakeConstraint('LIMIT_LOCATION')
        c.name = self.f['DEPTH_CONSTRAINT']
        obj.constraints.items[c.name] = c
        with self.assertRaises(RuntimeError):
            self.f['_set_limit'](obj, object(), 0.02, True)

    def test_yolo_export_uses_constrained_world_transform(self):
        content = (SOURCE.parent / 'annotation.py').read_text(encoding='utf-8')
        self.assertIn('evaluated_get(depsgraph).matrix_world', content)
        self.assertIn('for v in obj.data.vertices', content)

    def test_ui_and_registration(self):
        base = SOURCE.parent
        init = (base / '__init__.py').read_text(encoding='utf-8')
        ui = (base / 'ui.py').read_text(encoding='utf-8')
        props = (base / 'props.py').read_text(encoding='utf-8')
        self.assertIn('scene_lock, depth, quality_gate, artifact_presets, ui', init)
        for key in ('photo_depth_lock', 'glass_depth_lock',
                    'annotations_depth_lock', 'depth_target_glass',
                    'glass_depth_offset_m'):
            self.assertIn(key, props)
            self.assertIn(key, ui)
        for command in ('apply_glass_depth', 'reset_layer_depth'):
            self.assertIn('bvt_studio.' + command, ui)


if __name__ == '__main__':
    unittest.main()
