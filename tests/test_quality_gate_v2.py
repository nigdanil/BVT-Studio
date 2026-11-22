"""Quality Gate v2 policy/metric regression tests (real numbers need NumPy)."""
import ast
import sys
import types
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if 'bvt_studio' not in sys.modules:
    package = types.ModuleType('bvt_studio')
    package.__path__ = [str(ROOT / 'bvt_studio')]
    sys.modules['bvt_studio'] = package
from bvt_studio.quality_gate_v2 import (PROFILES, OPTICAL_VARIANTS,
                                       profile_config, validated_gate_settings,
                                       evaluate_quality_v2, select_optics_v2,
                                       assert_isolation)
try:
    import numpy as np
except ImportError:
    np = None


class QualityGateV2Contract(unittest.TestCase):
    def test_three_severity_profiles_have_distinct_water_density(self):
        self.assertEqual(list(PROFILES), ['LIGHT', 'MEDIUM', 'HEAVY'])
        self.assertLess(PROFILES['LIGHT']['density'], PROFILES['MEDIUM']['density'])
        self.assertLess(PROFILES['MEDIUM']['streaks'], PROFILES['HEAVY']['streaks'])
        self.assertEqual(len(OPTICAL_VARIANTS), 3)
        self.assertEqual(profile_config('light')['preset'], 'LIGHT_CONDENSATION')

    def test_fail_closed_targets_and_thresholds(self):
        for profile in PROFILES:
            cfg = validated_gate_settings(profile)
            self.assertLess(cfg['min_optical_changed_ratio'], cfg['target_optical_changed_ratio'])
            self.assertLess(cfg['target_optical_changed_ratio'], cfg['max_optical_changed_ratio'])
        for value in ({'target_optical_changed_ratio': True},
                      {'max_bright_rim_ratio': float('nan')},
                      {'max_detail_loss_ratio': -1},
                      {'preset': 'QA_TRANSPARENT'},
                      {'max_optical_changed_ratio': .002}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validated_gate_settings('MEDIUM', value)
        with self.assertRaises(ValueError):
            profile_config('MYSTERY')

    def test_rank_does_not_reward_rejected_or_large_score(self):
        cases = {
            'strong': {'accepted': False, 'score': 100.},
            'balanced': {'accepted': True, 'score': .3},
            'gentle': {'accepted': True, 'score': .3},
        }
        self.assertEqual(select_optics_v2(cases), 'balanced')
        self.assertIsNone(select_optics_v2({'bad': {'accepted': False, 'score': 5}}))

    def test_blender_scripts_and_ui_and_version(self):
        for path in ('scripts/blender_quality_gate_v2.py',
                     'scripts/blender_quality_gate_v2_persistence_smoke.py',
                     'bvt_studio/quality_gate_v2.py'):
            ast.parse((ROOT/path).read_text('utf-8'))
        script=(ROOT/'scripts/blender_quality_gate_v2.py').read_text('utf-8')
        for token in ('blender_precision_mask_qa.py', 'generate_realistic_atlas(',
                      'evaluate_quality_v2(', 'assert_isolation(', '--yolo-labels',
                      '40_quality_gate_v2_montage.png', 'quality_gate_v2_report.json',
                      'quality_gate_v2_smoke.blend'):
            self.assertIn(token, script)
        self.assertIn("stage == 'alpha.5-step5'", (ROOT/'bvt_studio/visual_quality_ui.py').read_text('utf-8'))
        self.assertIn('alpha.5-step5', (ROOT/'bvt_studio/__init__.py').read_text('utf-8'))
        self.assertIn('alpha.5-step5.zip', (ROOT/'scripts/build_addon.py').read_text('utf-8'))

    def test_yolo_modules_are_untouched(self):
        # The patch intentionally leaves all YOLO modules and dataset exports alone.
        protected = ('annotation.py', 'annotation_manager.py', 'quality_gate.py',
                     'export_preview.py', 'validation.py')
        for name in protected:
            self.assertTrue((ROOT/'bvt_studio'/name).is_file())


@unittest.skipUnless(np is not None, 'Requires NumPy; run with Blender Python')
class QualityGateV2Numeric(unittest.TestCase):
    def setUp(self):
        self.ref = np.full((128,128,3), .24, dtype=np.float32)
        self.mask = np.zeros((128,128), dtype=np.float32)
        self.mask[8:120,8:120] = 1.

    def _changed(self, frac):
        output = self.ref.copy()
        n = int(np.count_nonzero(self.mask) * frac)
        pixels = np.argwhere(self.mask>0)[:n]
        output[pixels[:,0], pixels[:,1]] += .03
        return output

    def test_profiles_target_different_intensities_not_strongest(self):
        candidates = {k:self._changed(v) for k,v in
                      [('gentle',.006),('balanced',.010),('strong',.014)]}
        for profile, desired in [('LIGHT','gentle'),('MEDIUM','balanced'),('HEAVY','strong')]:
            reports = {k:evaluate_quality_v2(self.ref, rgb, self.mask,
                        profile=profile) for k,rgb in candidates.items()}
            self.assertEqual(select_optics_v2(reports), desired,
                             (profile, {k:r['score'] for k,r in reports.items()}))

    def test_no_opacity_change_rejected_as_too_weak(self):
        result=evaluate_quality_v2(self.ref,self.ref,self.mask,profile='LIGHT')
        self.assertFalse(result['accepted'])
        self.assertTrue(any('optical_changed_ratio' in s for s in result['reasons']))

    def test_clipped_bright_rim_fails_even_if_changed_ratio_in_band(self):
        result=self._changed(.012)
        points=np.argwhere(self.mask>0)[:85]
        result[points[:,0],points[:,1]] = .98
        qa=evaluate_quality_v2(self.ref,result,self.mask,profile='LIGHT')
        self.assertFalse(qa['accepted'])
        self.assertGreater(qa['metrics']['bright_rim_ratio_v2'], .0015)

    def test_cross_pane_leakage_rejected(self):
        changed=self._changed(.01)
        changed[0:6,0:6] = 1.
        qa=evaluate_quality_v2(self.ref,changed,self.mask)
        self.assertFalse(qa['accepted'])
        self.assertGreater(qa['metrics']['leakage_ratio'], 0)
        isolated=assert_isolation(self.ref,changed,self.mask)
        self.assertFalse(isolated['accepted'])

    def test_severe_texture_detail_loss(self):
        checkers=(np.indices((128,128)).sum(0)%2).astype(np.float32)
        ref=np.repeat((.25+checkers*.4)[:,:,None],3,axis=2)
        candidate=ref.copy();candidate[8:120,8:120] = .45
        qa=evaluate_quality_v2(ref,candidate,self.mask,profile='MEDIUM')
        self.assertFalse(qa['accepted'])
        self.assertGreater(qa['metrics']['local_detail_loss_ratio_v2'], .35)

    def test_isolation_ignores_forbidden_aa_boundary_but_not_far_leak(self):
        new=self.ref.copy();new[20:30,20:30] += .05
        result=assert_isolation(self.ref,new,self.mask)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['leakage_pixels'],0)


if __name__=='__main__':
    unittest.main()
