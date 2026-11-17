"""Regression checks for choosing a photo with another Plane selected.

The function under test is loaded from the real module AST because Blender's
`bpy` is not available in normal CPython CI.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'bvt_studio' / 'scene_tools.py'


class FakeMesh(dict):
    def __init__(self, name, has_image=False, role=None):
        super().__init__()
        self.name = name
        self.type = 'MESH'
        self.has_image = has_image
        if role:
            self['bvt_role'] = role


class FakeScene:
    def __init__(self, objects, source):
        self.objects = SimpleNamespace(get=lambda name: next(
            (o for o in objects if o.name == name), None))
        self.source = source


def load_function():
    tree = ast.parse(PATH.read_text(encoding='utf-8'))
    method = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'choose_source_image_plane')
    mod = ast.Module(body=[method], type_ignores=[])
    env = {
        'image_from_mesh': lambda obj: object() if obj.has_image else None,
        'get_source': lambda scene: scene.source,
    }
    exec(compile(mod, str(PATH), 'exec'), env)
    return env['choose_source_image_plane']


class TestSourceSelection(unittest.TestCase):
    def test_active_textured_plane_wins(self):
        old = FakeMesh('Old', True)
        new = FakeMesh('New', True)
        source, reused = load_function()(FakeScene([old, new], old), new)
        self.assertIs(source, new)
        self.assertFalse(reused)

    def test_default_plane_keeps_registered_photo(self):
        photo = FakeMesh('BVT_Freezer_Image_Plane', True, 'planogram_image')
        glass = FakeMesh('Plane.001')
        source, reused = load_function()(FakeScene([photo, glass], photo), glass)
        self.assertIs(source, photo)
        self.assertTrue(reused)

    def test_no_photo_fails_without_guessing(self):
        glass = FakeMesh('Glass_p_001', False, 'glass_overlay')
        with self.assertRaisesRegex(ValueError, 'Image Texture'):
            load_function()(FakeScene([glass], None), glass)

    def test_do_not_register_glass_even_if_textured(self):
        glass = FakeMesh('Glass_p_001', True, 'glass_overlay')
        with self.assertRaises(ValueError):
            load_function()(FakeScene([glass], glass), glass)


if __name__ == '__main__':
    unittest.main()
