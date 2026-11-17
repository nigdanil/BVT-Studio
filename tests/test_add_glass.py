"""Regression tests for Add Glass without requiring installed Blender."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'bvt_studio' / 'glass.py'
CODE = SOURCE.read_text(encoding='utf-8')
MODULE = ast.parse(CODE)


def get_layout_function():
    fn = next(n for n in MODULE.body
              if isinstance(n, ast.FunctionDef) and n.name == 'default_glass_rect')
    constants = [n for n in MODULE.body if isinstance(n, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id.startswith('DEFAULT_GLASS_')
                     for t in n.targets)]
    sandbox = {}
    exec(compile(ast.Module(body=constants + [fn], type_ignores=[]),
                 str(SOURCE), 'exec'), sandbox)
    return sandbox['default_glass_rect']


class TestAddGlass(unittest.TestCase):
    def test_default_two_panels_fit_within_photo(self):
        layout = get_layout_function()
        for n in range(2):
            w, h, x, y = layout(-1, 1, -.56, .56, n)
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)
            self.assertGreaterEqual(x - w / 2, -1)
            self.assertLessEqual(x + w / 2, 1)
            self.assertGreaterEqual(y - h / 2, -.56)
            self.assertLessEqual(y + h / 2, .56)
        self.assertLess(layout(-1, 1, -1, 1, 0)[2], 0)
        self.assertGreater(layout(-1, 1, -1, 1, 1)[2], 0)

    def test_reject_degenerate_photo(self):
        with self.assertRaises(ValueError):
            get_layout_function()(1, 1, -1, 1, 0)

    def test_registered_and_does_not_use_object_add_operator(self):
        self.assertIn("bl_idname = 'bvt_studio.add_glass'", CODE)
        self.assertIn('BVTSTUDIO_OT_add_glass, BVTSTUDIO_OT_setup_glass', CODE)
        self.assertIn('ensure_collection(scene, GLASS_COLLECTION).objects.link(obj)', CODE)
        self.assertIn('configure_glass(obj)', CODE)
        self.assertNotIn('bpy.ops.mesh.primitive_plane_add', CODE)

    def test_ui_button_precedes_setup(self):
        ui = (SOURCE.parent / 'ui.py').read_text(encoding='utf-8')
        self.assertLess(ui.index("box.operator('bvt_studio.add_glass'"),
                        ui.index("box.operator('bvt_studio.setup_glass'"))


if __name__ == '__main__':
    unittest.main()
