"""Dependency-free structural checks; Blender runtime is not installed in CI."""
from pathlib import Path
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'bvt_studio'

class TestSource(unittest.TestCase):
    def test_all_python_parses(self):
        for path in PACKAGE.rglob('*.py'):
            with self.subTest(file=path.name):
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def test_version_bumped(self):
        self.assertIn('"version": (0, 3, 0)', (PACKAGE / '__init__.py').read_text())

    def test_glass_operators_have_unique_ids(self):
        content = (PACKAGE / 'glass.py').read_text()
        ids = re.findall(r"bl_idname\s*=\s*'([^']+)'", content)
        self.assertIn('bvt_studio.add_glass', ids)
        self.assertIn('bvt_studio.setup_glass', ids)
        self.assertIn('bvt_studio.setup_selected_glass_batch', ids)
        self.assertIn('bvt_studio.organize_glass', ids)
        self.assertIn('bvt_studio.renumber_glass', ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_ui_has_glass_collection_controls(self):
        content = (PACKAGE / 'ui.py').read_text()
        for name in ('add_glass', 'setup_glass', 'organize_glass', 'renumber_glass', 'setup_selected_glass_batch'):
            self.assertIn('bvt_studio.' + name, content)

    def test_version_visible_in_ui(self):
        ui = (PACKAGE / 'ui.py').read_text(encoding='utf-8')
        self.assertIn("bl_info['version']", ui)

    def test_glass_and_annotations_separate(self):
        glass = (PACKAGE / 'glass.py').read_text()
        annotations = (PACKAGE / 'annotation.py').read_text()
        self.assertIn("GLASS_COLLECTION = 'BVT_Glass'", glass)
        self.assertIn("'BVT_Annotations'", annotations)
        self.assertIn('def renumber_glass(', glass)

    def test_scene_lock_registration_and_ui(self):
        init = (PACKAGE / '__init__.py').read_text()
        ui = (PACKAGE / 'ui.py').read_text()
        props = (PACKAGE / 'props.py').read_text()
        self.assertIn('scene_lock, depth, quality_gate, ui', init)
        for key in ('photo_edit_enable', 'camera_edit_enable', 'light_edit_enable',
                    'glass_edit_enable', 'annotations_edit_enable'):
            self.assertIn(key, ui)
            self.assertIn(key, props)
        for operator in ('annotation_lock_mode', 'unlock_scene'):
            self.assertIn(f'bvt_studio.{operator}', ui)
        self.assertIn('activate_default_scene_locks(scene)',
                      (PACKAGE / 'scene_tools.py').read_text())

if __name__ == '__main__':
    unittest.main()
