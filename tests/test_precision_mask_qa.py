"""Portable QA contract checks; numerical tests also run in Blender's NumPy."""
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
PURE = ROOT / 'bvt_studio' / 'precision_mask_qa.py'
spec = importlib.util.spec_from_file_location('bvt_precision_qa_test', PURE)
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class PrecisionMaskQA(unittest.TestCase):
    def test_png_mask_can_be_assigned_packed_and_toggled_per_glass(self):
        source = (ROOT / 'bvt_studio' / 'glass_mask.py').read_text('utf-8')
        ast.parse(source)
        for phrase in ('MASK_IMAGE_KEY', 'MASK_PATH_KEY', 'MASK_ENABLED_KEY',
                       'check_existing=False', 'image.pack()', 'image.packed_file',
                       "colorspace_settings.name = 'Non-Color'", 'ShaderNodeRGBToBW',
                       'ShaderNodeTexImage', "sample.extension = 'CLIP'",
                       'BVT_Precision_Final_Mask_Gate', 'BVT_Precision_QA_Mask',
                       'force_transparent_control', 'BVT_QA_Transparent_Control',
                       'bvt_studio.assign_precision_mask', 'bvt_studio.toggle_precision_mask'):
            self.assertIn(phrase, source)

    def test_no_changes_in_yolo_modules_and_baseline_control(self):
        init = (ROOT/'bvt_studio/__init__.py').read_text('utf-8')
        props = (ROOT/'bvt_studio/props.py').read_text('utf-8')
        shaders = (ROOT/'bvt_studio/glass.py').read_text('utf-8')
        presets = (ROOT/'bvt_studio/artifact_presets.py').read_text('utf-8')
        for source in (init, props, shaders, presets):
            ast.parse(source)
        self.assertIn('alpha.5-step4', init)
        self.assertIn('QA_TRANSPARENT', props)
        self.assertIn("obj.get('bvt_artifact_preset') == 'QA_TRANSPARENT'", shaders)
        self.assertIn('apply_precision_mask(', shaders)
        self.assertIn('force_transparent_control(', shaders)
        self.assertIn("preset_values('CLEAN', 0.0, 0.0)", presets)
        for expected in ('precision_mask_path', 'qa_leakage_limit'):
            self.assertIn(expected, props)

    def test_visual_gallery_contract_and_independence(self):
        source = (ROOT/'scripts/blender_precision_mask_qa.py').read_text('utf-8')
        ast.parse(source)
        for phrase in ('--photo', '--output', '--save-blend',
                       '00_source.png', '01_control_transparent.png',
                       '06_mask_debug.png', '07_isolated_glass_',
                       'mask_glass_', 'precision_qa_report.json',
                       'leakage_metrics(', 'control_metrics(', 'mask_render(',
                       'image.packed_file', 'bpy.ops.wm.save_as_mainfile',
                       'BVT PRECISION MASK QA: OK'):
            self.assertIn(phrase, source)
        self.assertNotIn('ZipFile', source)
        reopen = (ROOT/'scripts/blender_precision_mask_persistence_smoke.py').read_text('utf-8')
        ast.parse(reopen)
        self.assertIn('BVT PRECISION MASK PERSISTENCE: OK', reopen)

    @unittest.skipUnless(np is not None, 'Requires Blender NumPy')
    def test_grayscale_mask_black_white_and_gray_semantics(self):
        source = np.zeros((8, 12, 3), np.float32)
        affected = source.copy()
        mask = np.zeros((8, 12), np.float32)
        mask[:, 4:8] = 1.0
        mask[:, 8:10] = .5  # gray pixels allow partial effects
        affected[:, 4:10, :] = .25
        stats = metrics.leakage_metrics(source, affected, mask, guard_pixels=0)
        self.assertEqual(stats['leakage_pixels'], 0)
        self.assertEqual(stats['forbidden_pixels'], 8 * 6)
        self.assertEqual(stats['leakage_ratio'], 0)

    @unittest.skipUnless(np is not None, 'Requires Blender NumPy')
    def test_leakage_detected_with_spatial_bbox(self):
        source = np.zeros((12, 13, 3), np.float32)
        affected = source.copy()
        affected[4:6, 2:4, :] = .1
        mask = np.zeros((12, 13), np.float32)
        mask[:, 7:] = 1.0
        stats = metrics.leakage_metrics(source, affected, mask, guard_pixels=0)
        self.assertEqual(stats['leakage_pixels'], 4)
        self.assertEqual(stats['leakage_bbox_xyxy'], [2, 4, 4, 6])
        self.assertGreater(stats['leakage_ratio'], 0)

    @unittest.skipUnless(np is not None, 'Requires Blender NumPy')
    def test_guard_does_not_hide_far_leak(self):
        source = np.zeros((32, 32, 3), np.float32)
        affected = source.copy()
        affected[4, 4] = .5
        mask = np.zeros((32, 32), np.float32)
        mask[12:20, 12:20] = 1.0
        result = metrics.leakage_metrics(source, affected, mask, guard_pixels=2)
        self.assertEqual(result['leakage_pixels'], 1)

    @unittest.skipUnless(np is not None, 'Requires Blender NumPy')
    def test_control_delta_and_size_preflight(self):
        a = np.zeros((7, 9, 3), np.float32)
        b = a.copy()
        self.assertEqual(metrics.control_metrics(a, b)['max_rgb_delta'], 0.0)
        b[0, 1] = 1
        self.assertGreater(metrics.control_metrics(a, b)['mean_rgb_delta'], 0)
        with self.assertRaises(ValueError):
            metrics.leakage_metrics(a, b, np.ones((6, 9), np.float32))


if __name__ == '__main__':
    unittest.main()
