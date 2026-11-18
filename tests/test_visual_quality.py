"""Regression tests for realistic, *bounded* QA proxies, no Blender needed."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    import numpy as np
except ImportError:
    np = None

# Load only the pure module as a namespace submodule; running bvt_studio's
# add-on __init__ directly would require Blender's unavailable `bpy`.
import sys
import types
if 'bvt_studio' not in sys.modules:
    package = types.ModuleType('bvt_studio')
    package.__path__ = [str(ROOT/'bvt_studio')]
    sys.modules['bvt_studio'] = package
from bvt_studio.visual_quality import validated_limits, rank_candidates


class VisualQualityContractTests(unittest.TestCase):
    def test_threshold_validation(self):
        self.assertEqual(validated_limits()['max_leakage_ratio'], .0005)
        for bad in ({'not_a_limit': .2}, {'max_bright_halo_ratio': float('nan')},
                    {'max_sku_detail_loss_ratio': 2}, {'max_leakage_ratio': -1},
                    {'max_sku_mean_rgb_delta': True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validated_limits(bad)

    def test_rank_uses_only_accepted_and_has_stable_tiebreak(self):
        candidates = {'rejected': {'accepted': False, 'score': 20},
                      'balanced': {'accepted': True, 'score': .2},
                      'gentle': {'accepted': True, 'score': .2}}
        self.assertEqual(rank_candidates(candidates), 'balanced')
        self.assertIsNone(rank_candidates({'reject': {'accepted': False, 'score': 100}}))

    def test_gallery_and_ui_contract(self):
        script = ROOT/'scripts/blender_visual_quality_calibration.py'
        viewer = ROOT/'bvt_studio/visual_quality_ui.py'
        ast.parse(script.read_text('utf-8'))
        ast.parse(viewer.read_text('utf-8'))
        contents = script.read_text('utf-8')
        for needle in ('blender_precision_mask_qa.py','yolo_roi_mask',
                       'evaluate_candidate(', 'rank_candidates(',
                       '20_isolated_off_', '21_isolated_on_',
                       'visual_quality_report.json', '30_visual_calibration_montage.png',
                       'visual_quality_smoke.blend', 'opts.strict'):
            self.assertIn(needle, contents)
        ui = (ROOT/'bvt_studio/ui.py').read_text('utf-8')
        self.assertIn('bvt_studio.read_visual_quality_report', ui)
        self.assertIn('alpha.5-step5', (ROOT/'bvt_studio/__init__.py').read_text('utf-8'))
        self.assertIn('BVT_Studio_Blender_Addon_v0.4.0-alpha.5-step5.zip',
                      (ROOT/'scripts/build_addon.py').read_text('utf-8'))
        for path in ('annotation.py','annotation_manager.py','quality_gate.py',
                     'export_preview.py','validation.py'):
            self.assertTrue((ROOT/'bvt_studio'/path).exists())


@unittest.skipUnless(np is not None, 'Requires NumPy (available in Blender Python)')
class VisualQualityNumericalTests(unittest.TestCase):
    def setUp(self):
        from bvt_studio.visual_quality import evaluate_candidate, yolo_roi_mask
        self.evaluate = evaluate_candidate
        self.to_mask = yolo_roi_mask
        self.base = np.full((64, 64, 3), .3, dtype=np.float32)
        self.mask = np.zeros((64, 64), dtype=np.float32)
        self.mask[10:54, 10:54] = 1

    def test_yolo_roi_center_and_top_down_conversion(self):
        m = self.to_mask(200, 100, '2 0.25 0.20 0.20 0.20\n')
        self.assertTrue(m[75,50])  # top-down y=.2 -> bottom-up row 80
        self.assertFalse(m[20,50])
        self.assertEqual(m.shape, (100,200))
        for bad in ('2 0.5 0.5 0 0.2', 'x 0.5 0.5 0.2 0.2',
                    '2 0.9 0.9 0.4 0.4', '2 0.5 0.5 nan 0.1', '',
                    '2 0.2 0.2 0.3'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.to_mask(100,100,bad)

    def test_zero_change_is_rejected_as_uninformative(self):
        res = self.evaluate(self.base, self.base, self.mask)
        self.assertFalse(res['accepted'])
        self.assertEqual(res['metrics']['effect_changed_ratio'], 0)

    def test_isolated_brightening_is_measured(self):
        new = self.base.copy()
        new[20:40,20:40] = .9
        res = self.evaluate(self.base, new, self.mask,
                            limits={'max_bright_halo_ratio': .01})
        self.assertFalse(res['accepted'])
        self.assertGreater(res['metrics']['bright_halo_proxy_ratio'], .1)
        self.assertEqual(res['metrics']['leakage_pixels'], 0)

    def test_far_leak_not_hidden(self):
        new = self.base.copy()
        new[30:36,30:36] = .33
        new[1:6,1:6] = .9
        res = self.evaluate(self.base, new, self.mask)
        self.assertGreater(res['metrics']['leakage_pixels'], 0)
        self.assertFalse(res['accepted'])
        self.assertIsNotNone(res['metrics']['leakage_bbox_xyxy'])

    def test_detail_retention_proxy_detects_blur(self):
        checkers = np.indices((64,64)).sum(0) % 2
        img = np.repeat((.25+checkers*.4)[:,:,None],3,axis=2).astype(np.float32)
        new = img.copy()
        new[10:54,10:54] = .45
        res = self.evaluate(img, new, self.mask,
                            limits={'max_sku_detail_loss_ratio': .1})
        self.assertGreater(res['metrics']['sku_detail_loss_proxy_ratio'], .1)
        self.assertFalse(res['accepted'])

    def test_bad_inputs_and_roi_are_rejected(self):
        new = self.base.copy()
        for wrong in (np.zeros((63,64,3),dtype=np.float32),
                      np.full((64,64,3),np.nan,dtype=np.float32),
                      np.full((64,64,3),1.2,dtype=np.float32)):
            with self.assertRaises(ValueError):
                self.evaluate(self.base, wrong, self.mask)
        with self.assertRaises(ValueError):
            self.evaluate(self.base, new, np.zeros((64,64),dtype=np.float32))
        with self.assertRaises(ValueError):
            self.evaluate(self.base, new, self.mask, sku_roi=np.zeros((64,64),dtype=bool))

    def test_one_pane_change_does_not_touch_other_roi(self):
        new = self.base.copy()
        new[20:32,20:32] += .04
        white = np.zeros_like(self.mask); white[15:38,15:38]=1
        stats = self.evaluate(self.base,new,white,
                              limits={'min_effect_changed_ratio': 0.})
        self.assertTrue(stats['accepted'])
        self.assertEqual(stats['metrics']['leakage_pixels'],0)


if __name__ == '__main__':
    unittest.main()
