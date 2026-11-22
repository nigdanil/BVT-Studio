"""Runner planning and output validation, without bpy."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import bvt_dataset_runner as runner
from validate_examples import read, validate


class DatasetRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = validate(ROOT/'examples/freezer_planogram')
        cls.gallery = read(cls.example['configs']['gallery'])

    def plan(self, effects=runner.DEFAULT_EFFECTS, count=2, seed=72):
        return runner.make_plan(self.example, self.gallery, effects, count, seed)

    def test_count_control_and_seeds(self):
        p, c = self.plan()
        self.assertEqual(len(p['jobs']), 5)
        self.assertEqual(p['jobs'][0]['id'], '00_clean')
        self.assertEqual(p['jobs'][1]['pane_seeds'], [72,73,74,75])
        self.assertEqual(p['jobs'][2]['pane_seeds'], [76,77,78,79])
        self.assertEqual(p['jobs'][3]['pane_seeds'], p['jobs'][1]['pane_seeds'])
        self.assertEqual(set(c['variants']), {x['id'] for x in p['jobs']})
        self.assertEqual(p['labels_status'], 'UNLABELED')
        self.assertTrue(all(x['labels'] is None for x in p['jobs']))

    def test_repeatable_and_order_independent(self):
        self.assertEqual(self.plan(), self.plan(tuple(reversed(runner.DEFAULT_EFFECTS))))
        self.assertNotEqual(self.plan(seed=73), self.plan())

    def test_parameters_preserved(self):
        before = json.dumps(self.gallery, sort_keys=True)
        p,c = self.plan()
        for j in p['jobs']:
            expected = dict(self.gallery['variants'][j['effect']], seed_base=j['seed_base'])
            self.assertEqual(c['variants'][j['id']], expected)
        self.assertEqual(json.dumps(self.gallery, sort_keys=True), before)

    def test_invalid_requests(self):
        for args in [dict(count=0),dict(count=101),dict(seed=-1),dict(seed=2**31-1),
                     dict(effects=('00_clean',)),dict(effects=('12_stress_optics',)),
                     dict(effects=('unknown',)),dict(effects=(runner.DEFAULT_EFFECTS[0],)*2)]:
            with self.subTest(args=args), self.assertRaises(ValueError): self.plan(**args)

    def test_output_guard(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t).resolve()
            (root/'qa_renders').mkdir()
            self.assertEqual(runner.output_path(root,Path('qa_renders/new')),root/'qa_renders/new')
            for bad in ('examples/output','qa_renders','qa_renders/../other'):
                with self.subTest(bad=bad),self.assertRaises(ValueError): runner.output_path(root,Path(bad))
            (root/'qa_renders/existing').mkdir()
            with self.assertRaises(ValueError): runner.output_path(root,Path('qa_renders/existing'))

    def test_reject_wrong_manifest(self):
        plan, gallery = self.plan()
        job = plan['jobs'][0]
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); d=root/job['id'];d.mkdir()
            (d/'manifest.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Wrong variant'): runner.check_render(root,job,plan,gallery['variants'][job['id']])


if __name__ == '__main__': unittest.main()
