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
        self.assertIn('"version": (0, 2, 0)', (PACKAGE / '__init__.py').read_text())

    def test_glass_operators_have_unique_ids(self):
        content = (PACKAGE / 'glass.py').read_text()
        ids = re.findall(r"bl_idname\s*=\s*'([^']+)'", content)
        self.assertIn('bvt_studio.setup_glass', ids)
        self.assertIn('bvt_studio.organize_glass', ids)
        self.assertIn('bvt_studio.renumber_glass', ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_ui_has_glass_collection_controls(self):
        content = (PACKAGE / 'ui.py').read_text()
        for name in ('setup_glass', 'organize_glass', 'renumber_glass'):
            self.assertIn('bvt_studio.' + name, content)

    def test_glass_and_annotations_separate(self):
        glass = (PACKAGE / 'glass.py').read_text()
        annotations = (PACKAGE / 'annotation.py').read_text()
        self.assertIn("GLASS_COLLECTION = 'BVT_Glass'", glass)
        self.assertIn("'BVT_Annotations'", annotations)
        self.assertIn('def renumber_glass(', glass)

if __name__ == '__main__':
    unittest.main()
