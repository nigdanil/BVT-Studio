"""Pure-Python quality-gate test suite. No Blender installation required."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('quality_gate_core',
                                             ROOT / 'bvt_studio' / 'validation.py')
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


def box(name, x1, y1, x2, y2, class_id=0):
    return dict(object=name, class_id=class_id, class_name='ice_cream',
                xmin=x1, ymin=y1, xmax=x2, ymax=y2, w=x2-x1, h=y2-y1)


class TestQualityGate(unittest.TestCase):
    def test_empty_camera_is_blocking(self):
        report = validation.quality_report([], ['No active scene camera'], [], 1000, 1000)
        self.assertEqual((report['errors'], report['warnings']), (1, 0))
        self.assertEqual(report['issues'][0]['code'], 'NO_CAMERA')

    def test_error_links_target_object(self):
        report = validation.quality_report(
            [], ['plane_p_001: part of bbox is outside frame'],
            ['plane_p_001'], 1920, 1080)
        self.assertEqual(report['issues'][0]['object_name'], 'plane_p_001')
        self.assertEqual(report['issues'][0]['code'], 'OUTSIDE_FRAME')

    def test_duplicate_error_links_first_object(self):
        report = validation.quality_report(
            [box('plane_p_001', .1, .1, .2, .2)],
            ['Near-duplicate boxes: plane_p_001 and plane_p_002'],
            ['plane_p_001', 'plane_p_002'], 1000, 1000)
        self.assertEqual(report['issues'][0]['object_name'], 'plane_p_001')
        self.assertEqual(report['issues'][0]['code'], 'DUPLICATE_BOX')

    def test_tiny_object_warns_but_does_not_block(self):
        report = validation.quality_report(
            [box('tiny', .1, .1, .102, .103)], [], ['tiny'], 1000, 1000)
        self.assertEqual(report['errors'], 0)
        self.assertEqual(report['warnings'], 1)
        self.assertEqual(report['issues'][0]['code'], 'TINY_OBJECT')

    def test_heavy_non_identical_overlap_is_warning(self):
        boxes = [box('A', .10, .10, .40, .40), box('B', .14, .10, .44, .40)]
        report = validation.quality_report(boxes, [], ['A', 'B'], 1000, 1000)
        self.assertEqual(report['errors'], 0)
        self.assertEqual(report['warnings'], 1)
        self.assertEqual(report['issues'][0]['code'], 'HIGH_OVERLAP')

    def test_duplicate_hard_error_not_repeated_as_warning(self):
        boxes = [box('A', .10, .10, .40, .40), box('B', .10, .10, .40, .40)]
        report = validation.quality_report(
            boxes, ['Near-duplicate boxes: A and B'], ['A', 'B'], 1000, 1000)
        self.assertEqual((report['errors'], report['warnings']), (1, 0))

    def test_overlapping_different_classes_is_warning(self):
        boxes = [box('A', .1, .1, .4, .4), box('B', .1, .1, .4, .4, class_id=1)]
        report = validation.quality_report(boxes, [], ['A', 'B'], 1000, 1000)
        self.assertEqual((report['errors'], report['warnings']), (0, 1))

    def test_non_overlapping_has_no_issues(self):
        boxes = [box('A', .1, .1, .2, .2), box('B', .6, .6, .7, .7)]
        report = validation.quality_report(boxes, [], ['A', 'B'], 1000, 1000)
        self.assertEqual((report['errors'], report['warnings']), (0, 0))

    def test_no_geometry_mutation(self):
        boxes = [box('A', .1, .1, .2, .2)]
        original = [item.copy() for item in boxes]
        validation.quality_report(boxes, [], ['A'], 1000, 1000)
        self.assertEqual(boxes, original)

    def test_quality_ui_registered_and_export_revalidates(self):
        init = (ROOT/'bvt_studio'/'__init__.py').read_text(encoding='utf8')
        ui = (ROOT/'bvt_studio'/'ui.py').read_text(encoding='utf8')
        anno = (ROOT/'bvt_studio'/'annotation.py').read_text(encoding='utf8')
        self.assertIn('quality_gate, artifact_presets, ui', init)
        self.assertIn('BVTSTUDIO_UL_quality_issues', ui)
        self.assertIn('bvt_studio.focus_quality_issue', ui)
        self.assertIn('evaluate_quality(scene)', anno)


if __name__ == '__main__':
    unittest.main()
