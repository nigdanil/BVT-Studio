"""Dependency-free smoke-test contract checks; actual bpy test runs in Blender."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'blender_v03_e2e_smoke.py'


class TestV03EndToEndContract(unittest.TestCase):
    def test_smoke_script_is_valid_python(self):
        ast.parse(SCRIPT.read_text(encoding='utf-8'), filename=str(SCRIPT))

    def test_imports_photo_using_public_operator(self):
        code = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('bvt_studio.load_photo(', code)
        self.assertIn('bvt_studio.fit_camera(', code)

    def test_exercises_real_user_workflow(self):
        code = SCRIPT.read_text(encoding='utf-8')
        for operator in ('add_glass', 'add_annotation', 'batch_annotation_class',
                         'annotation_lock_mode', 'apply_glass_depth', 'validate',
                         'export_yolo'):
            with self.subTest(operator=operator):
                self.assertIn('bvt_studio.' + operator + '()', code)

    def test_verifies_export_contract_and_state_recovery(self):
        code = SCRIPT.read_text(encoding='utf-8')
        for marker in ('parse_label_text(', "yaml_file.read_text", 'ET.parse(svg_file)',
                       'manifest_file', 'before_hidden', 'before_render_path'):
            with self.subTest(marker=marker):
                self.assertIn(marker, code)

    def test_maintainer_build_filename_is_current(self):
        build_script = (ROOT/'scripts'/'build_addon.py').read_text(encoding='utf-8')
        self.assertIn('BVT_Studio_Blender_Addon_v0.4.0-alpha.4-step4.zip', build_script)

    def test_temporary_output_no_assets_or_zip(self):
        code = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('tempfile.TemporaryDirectory(', code)
        self.assertNotIn('build_addon(', code)
        self.assertNotIn('import requests', code)
        self.assertNotIn('from urllib.request', code)


if __name__ == '__main__':
    unittest.main()
