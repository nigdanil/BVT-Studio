"""Step 6 real-dataset pair QA regression tests; no Blender required."""
import ast
import json
import importlib.util
import tempfile
from unittest import mock
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if 'bvt_studio' not in sys.modules:
    module = types.ModuleType('bvt_studio')
    module.__path__ = [str(ROOT/'bvt_studio')]
    sys.modules['bvt_studio'] = module
from bvt_studio.real_dataset_qa import (POLICIES, parse_yolo_detect,
                                        evaluate_dataset_pair, policy_for)
try:
    import numpy as np
except ImportError:
    np = None


class ParseYoloContract(unittest.TestCase):
    def test_precise_pixel_conversion_top_down(self):
        a = parse_yolo_detect('2 0.25 0.75 0.2 0.1', 100, 200)[0]
        self.assertEqual(a['class_id'], 2)
        self.assertEqual(a['bbox_xyxy_px'], [15,140,35,160])
        self.assertEqual(a['line'], 1)

    def test_preserve_class_zero_and_multiple_boxes(self):
        rows = parse_yolo_detect('0 .5 .5 .4 .4\n\n9 .2 .2 .2 .2\n', 100, 100)
        self.assertEqual([x['class_id'] for x in rows], [0, 9])
        self.assertEqual(rows[1]['line'], 3)

    def test_invalid_boxes_fail_closed(self):
        invalid = ['', '0 0.5 0.5 0.0 0.4', '0 0.5 0.5 0.1',
                   '1.0 0.5 0.5 0.4 0.4', '-1 0.5 0.5 0.4 0.4',
                   '0 NaN 0.5 0.4 0.4', '0 0.02 0.5 0.4 0.4',
                   '0 0.5 0.5 1.2 0.4', '0 0.5 0.5 0.4 0.4 0.1',
                   'x 0.5 0.5 0.4 0.4']
        for line in invalid:
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_yolo_detect(line, 100, 100)

    def test_nonpositive_image_dimensions(self):
        for width,height in [(0,20),(20,-1),(True,5),(20,0)]:
            with self.assertRaises(ValueError):
                parse_yolo_detect('0 0.5 0.5 0.3 0.3', width, height)

    def test_profiles_are_distinct_and_copy_on_read(self):
        self.assertLess(POLICIES['LIGHT']['target'], POLICIES['MEDIUM']['target'])
        self.assertLess(POLICIES['MEDIUM']['target'], POLICIES['HEAVY']['target'])
        profile=policy_for('light')
        profile['target']=10
        self.assertNotEqual(POLICIES['LIGHT']['target'], 10)
        with self.assertRaises(ValueError):
            policy_for('unknown')

    def test_blender_cli_contract_and_no_old_code_replacements(self):
        for filename in ('scripts/blender_real_dataset_quality.py',
                         'scripts/blender_real_dataset_quality_smoke.py'):
            code=(ROOT/filename).read_text('utf-8')
            ast.parse(code)
        script=(ROOT/'scripts/blender_real_dataset_quality.py').read_text('utf-8')
        for token in ('--clean-dir', '--augmented-dir', '--labels-dir',
                      '--masks-dir', '--strict', 'sha256_file(',
                      'accepted_manifest.json', 'objects.csv', 'samples.csv', 'classes.csv',
                      'real_dataset_quality_report.json', 'load_blender_image('):
            self.assertIn(token, script)
        self.assertIn('Missing mask is REVIEW',script)
        self.assertIn('git apply', (ROOT/'docs/REAL_DATASET_QA_STEP6.md').read_text('utf-8'))


@unittest.skipUnless(np is not None,'NumPy required for image metrics; run with Blender Python')
class PairNumericalQA(unittest.TestCase):
    def setUp(self):
        h,w=100,100
        iy,ix=np.indices((h,w))
        chess=((iy//4+ix//4)%2).astype(np.float32)
        self.clean=np.repeat((.25+chess*.25)[:,:,None],3,axis=2)
        self.mask=np.zeros((h,w),dtype=np.float32)
        self.mask[10:90,10:90]=1.
        self.labels='0 0.5 0.5 0.6 0.6\n1 0.06 0.06 0.08 0.08'

    def change(self):
        image=self.clean.copy()
        image[35:50,40:55] += .05
        return image

    def test_nominal_light_pass_with_glass(self):
        quality=evaluate_dataset_pair(self.clean,self.change(),self.labels,
                                      profile='LIGHT',glass_mask=self.mask)
        self.assertEqual(quality['status'],'PASS',quality)
        self.assertEqual(quality['annotations_count'],2)
        self.assertEqual(quality['objects'][0]['scope'],'glass_intersection')
        self.assertEqual(quality['objects'][1]['scope'],'outside_glass')
        self.assertEqual(quality['metrics']['far_glass_leakage_pixels'],0)
        self.assertEqual(set(quality['classes']),{'0','1'})
        json.dumps(quality)

    def test_original_arrays_not_mutated(self):
        modified=self.change()
        before=self.clean.copy(); before_aug=modified.copy()
        evaluate_dataset_pair(self.clean,modified,self.labels,profile='LIGHT',glass_mask=self.mask)
        np.testing.assert_array_equal(self.clean,before)
        np.testing.assert_array_equal(modified,before_aug)

    def test_nomask_never_passes(self):
        quality=evaluate_dataset_pair(self.clean,self.change(),self.labels,
                                      profile='LIGHT')
        self.assertEqual(quality['status'],'REVIEW')
        self.assertFalse(quality['accepted'])
        self.assertIsNone(quality['metrics']['far_glass_leakage_ratio'])

    def test_far_glass_leak_detected(self):
        modified=self.change()
        modified[0:4,0:4] += .05
        qa=evaluate_dataset_pair(self.clean,modified,self.labels,
                                 profile='LIGHT',glass_mask=self.mask)
        self.assertEqual(qa['status'],'REJECT')
        self.assertEqual(qa['metrics']['far_glass_leakage_pixels'],16)

    def test_aa_2px_border_is_exempt_from_leak(self):
        modified=self.change()
        modified[9:10,20:25] += .05
        qa=evaluate_dataset_pair(self.clean,modified,self.labels,
                                 profile='LIGHT',glass_mask=self.mask)
        self.assertEqual(qa['metrics']['far_glass_leakage_pixels'],0)

    def test_fade_to_uniform_rejected_by_detail(self):
        modified=self.clean.copy()
        modified[20:80,20:80] = .375
        qa=evaluate_dataset_pair(self.clean,modified,self.labels,
                                 profile='HEAVY',glass_mask=self.mask)
        self.assertEqual(qa['objects'][0]['status'],'REJECT')
        self.assertGreater(qa['objects'][0]['metrics']['detail_loss_ratio'],.5)

    def test_bright_clipped_patch_rejected(self):
        modified=self.change()
        modified[31:59,33:63]=1.
        qa=evaluate_dataset_pair(self.clean,modified,self.labels,
                                 profile='LIGHT',glass_mask=self.mask)
        self.assertEqual(qa['objects'][0]['status'],'REJECT')
        self.assertGreater(qa['objects'][0]['metrics']['bright_ratio'],.08)

    def test_no_effect_rejected(self):
        qa=evaluate_dataset_pair(self.clean,self.clean,self.labels,
                                 profile='LIGHT',glass_mask=self.mask)
        self.assertEqual(qa['status'],'REJECT')
        self.assertTrue(any('changed_ratio' in s for s in qa['reasons']))

    def test_shape_and_finiteness_fail_closed(self):
        with self.assertRaises(ValueError):
            evaluate_dataset_pair(self.clean,self.clean[:-1],self.labels)
        modified=self.change()
        modified[50,50,1]=float('nan')
        with self.assertRaises(ValueError):
            evaluate_dataset_pair(self.clean,modified,self.labels)
        with self.assertRaises(ValueError):
            evaluate_dataset_pair(self.clean,self.change(),self.labels,
                                  glass_mask=np.zeros((100,100)))

    def test_yolo_no_annotation_fail(self):
        with self.assertRaises(ValueError):
            evaluate_dataset_pair(self.clean,self.change(),'\n',glass_mask=self.mask)

    def test_sku_outside_glass_is_not_forced_to_change(self):
        qa=evaluate_dataset_pair(self.clean,self.change(),self.labels,
                                 profile='LIGHT',glass_mask=self.mask)
        self.assertEqual(qa['objects'][1]['status'],'PASS')


@unittest.skipUnless(np is not None,'NumPy required for test batch fixture')
class BatchDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bvt_step6_test_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for folder in ('clean','augmented','labels','masks'):
            (self.root/folder).mkdir()
        for name in ('clean','augmented','masks'):
            (self.root/name/'scene.png').write_bytes(b'fixture image placeholder')
        (self.root/'labels'/'scene.txt').write_text('0 0.5 0.5 0.6 0.6\n', encoding='utf-8')
        y,x=np.indices((96,96))
        tiled=((x//4 + y//4)%2).astype(np.float32)
        self.original=np.repeat((.28+.25*tiled)[:,:,None],3,axis=2)
        self.changed=self.original.copy()
        self.changed[30:45,35:50] += .055
        self.glass=np.zeros((96,96),dtype=np.float32)
        self.glass[8:88,8:88] = 1.
        fake=types.ModuleType('bpy')
        fake.app=types.SimpleNamespace(version_string='Test Blender stub')
        script=ROOT/'scripts/blender_real_dataset_quality.py'
        spec=importlib.util.spec_from_file_location('bvt_real_dataset_cli_test',script)
        self.cli=importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules,{'bpy':fake}):
            spec.loader.exec_module(self.cli)
        def fake_load(path,*,grayscale=False):
            if grayscale:
                return self.glass.copy()
            return (self.changed if 'augmented' in path.parts else self.original).copy()
        self.cli.load_blender_image=fake_load
        self.cli.save_overlay=lambda filepath,rgb,objects: (filepath.parent.mkdir(parents=True,exist_ok=True),filepath.write_bytes(b'overlay'))

    def argv(self,*,masks=True,strict=False,out='out'):
        args=['--clean-dir',str(self.root/'clean'),
              '--augmented-dir',str(self.root/'augmented'),
              '--labels-dir',str(self.root/'labels'),
              '--output-dir',str(self.root/out), '--profile','LIGHT']
        if masks:
            args += ['--masks-dir',str(self.root/'masks')]
        if strict:
            args += ['--strict']
        return args

    def test_paired_batch_writes_immutable_manifest_and_csv(self):
        before=(self.root/'labels'/'scene.txt').read_bytes()
        result=self.cli.main(self.argv(strict=True))
        self.assertEqual(result['counts']['PASS'],1)
        self.assertEqual((self.root/'labels'/'scene.txt').read_bytes(),before)
        output=self.root/'out'
        manifest=json.loads((output/'accepted_manifest.json').read_text('utf-8'))
        self.assertEqual(manifest['accepted'][0]['sample'],'scene')
        self.assertEqual(len(manifest['accepted'][0]['input']['sha256']),4)
        self.assertEqual(result['per_class']['0']['pass'],1)
        for name in ('samples.csv','objects.csv','classes.csv','real_dataset_quality_report.json','overlays/scene.png'):
            self.assertTrue((output/name).is_file(),name)

    def test_no_glass_mask_is_review_and_manifest_empty(self):
        result=self.cli.main(self.argv(masks=False,out='review'))
        self.assertEqual(result['counts']['REVIEW'],1)
        manifest=json.loads((self.root/'review'/'accepted_manifest.json').read_text('utf-8'))
        self.assertEqual(manifest['accepted'],[])
        with self.assertRaises(SystemExit) as cm:
            self.cli.main(self.argv(masks=False,strict=True,out='strict_review'))
        self.assertEqual(cm.exception.code,2)
        self.assertTrue((self.root/'strict_review'/'real_dataset_quality_report.json').exists())

    def test_bad_annotation_errors_without_touching_images(self):
        (self.root/'labels'/'scene.txt').write_text('malformed\n',encoding='utf-8')
        result=self.cli.main(self.argv(out='invalid'))
        self.assertEqual(result['counts']['ERROR'],1)
        self.assertEqual(result['samples'][0]['status'],'ERROR')
        self.assertEqual(json.loads((self.root/'invalid'/'accepted_manifest.json').read_text())['accepted'],[])

    def test_missing_augmented_is_error(self):
        (self.root/'augmented'/'scene.png').unlink()
        result=self.cli.main(self.argv(out='missing'))
        self.assertEqual(result['counts']['ERROR'],1)

    def test_output_cannot_overlap_inputs(self):
        with self.assertRaises(SystemExit):
            self.cli.configure(self.argv(out='clean'))
        with self.assertRaises(SystemExit):
            self.cli.configure(self.argv(out='clean/injected'))



if __name__=='__main__':
    unittest.main()
