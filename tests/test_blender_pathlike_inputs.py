"""Blender path helpers accept strings; QA galleries pass pathlib.Path objects.

Exercise the import preflight without importing Blender in host CPython. This
catches WindowsPath passed directly to bpy.path.abspath before texture loading.
"""
import ast
import math
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def extract_functions(relative_path, names, scope):
    tree = ast.parse((ROOT / relative_path).read_text(encoding='utf-8'))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name in names]
    if len(selected) != len(names):
        raise AssertionError('Missing expected function(s): ' + str(names))
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(relative_path), 'exec'), scope)
    return scope


class GlassStub(dict):
    type = 'MESH'
    library = None
    name = 'Glass_p_001'
    data = types.SimpleNamespace(library=None)

    def __init__(self):
        super().__init__(bvt_role='glass_overlay')


class BlenderPathlikeInputTests(unittest.TestCase):
    def test_photo_maps_accept_path_objects_before_loading(self):
        calls = []

        def strict_abspath(value):
            if not isinstance(value, str):
                raise TypeError('bpy.path.abspath requires a str')
            calls.append(value)
            return value

        def stop_load(*args, **kwargs):
            raise RuntimeError('reached image loading')

        bpy = types.SimpleNamespace(
            path=types.SimpleNamespace(abspath=strict_abspath),
            data=types.SimpleNamespace(images=types.SimpleNamespace(load=stop_load)))
        names = ('image_key', 'path_key', 'check_transform', '_glass_check',
                 'import_droplet_maps')
        fake_package = types.ModuleType('bvt_studio')
        fake_package.__path__ = []
        fake_glass = types.ModuleType('bvt_studio.glass')
        fake_glass.configure_glass = lambda obj: None
        scope = {'__name__': 'bvt_studio.droplet_maps', '__package__': 'bvt_studio',
                 'isfinite': math.isfinite, 'Path': Path,
                 'KINDS': ('alpha', 'height', 'normal'),
                 'MODE_KEY': 'bvt_droplet_source_mode',
                 'TILING_KEY': 'bvt_droplet_map_tiling',
                 'ROTATION_KEY': 'bvt_droplet_map_rotation'}
        extract_functions('bvt_studio/droplet_maps.py', names, scope)
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / (name + '.png') for name in ('alpha', 'height', 'normal')]
            for path in paths:
                path.write_bytes(b'preflight only')
            with patch.dict(sys.modules, {'bpy': bpy, 'bvt_studio': fake_package,
                                         'bvt_studio.glass': fake_glass}):
                with self.assertRaisesRegex(RuntimeError, 'reached image loading'):
                    scope['import_droplet_maps'](GlassStub(), *paths)
        self.assertEqual(calls, [str(p) for p in paths])

    def test_precision_mask_accepts_path_objects_before_loading(self):
        calls = []

        def strict_abspath(value):
            if not isinstance(value, str):
                raise TypeError('bpy.path.abspath requires a str')
            calls.append(value)
            return value

        def stop_load(*args, **kwargs):
            raise RuntimeError('reached mask loading')

        bpy = types.SimpleNamespace(
            path=types.SimpleNamespace(abspath=strict_abspath),
            data=types.SimpleNamespace(images=types.SimpleNamespace(load=stop_load)))
        scope = {'Path': Path}
        extract_functions('bvt_studio/glass_mask.py', ('load_mask_for_glass',), scope)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'mask.png'
            path.write_bytes(b'preflight only')
            with patch.dict(sys.modules, {'bpy': bpy}):
                with self.assertRaisesRegex(RuntimeError, 'reached mask loading'):
                    scope['load_mask_for_glass'](GlassStub(), path)
        self.assertEqual(calls, [str(path)])


if __name__ == '__main__':
    unittest.main()
