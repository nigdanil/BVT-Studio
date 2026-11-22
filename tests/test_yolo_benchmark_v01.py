import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bvt_yolo_benchmark as b


def gt(uid='a',box=(0.,0.,.4,.4),affected=True,index=1):
    return dict(uid=uid,class_id=0,xyxy=list(box),affected_roi=affected,index=index,flags=[])


def pred(box=(0.,0.,.4,.4),conf=.9):
    return dict(class_id=0,xyxy=list(box),confidence=conf)


class BenchmarkTests(unittest.TestCase):
    def test_iou_identity_disjoint_partial(self):
        self.assertEqual(b.iou([0,0,1,1],[0,0,1,1]),1.)
        self.assertEqual(b.iou([0,0,.2,.2],[.3,.3,.4,.4]),0.)
        self.assertAlmostEqual(b.iou([0,0,.5,.5],[.25,0,.75,.5]),1/3)

    def test_duplicate_predictions_are_false_positives(self):
        m=b.metrics([([gt()],[pred(),pred(conf=.8)])],.25)
        self.assertEqual((m['tp'],m['fp'],m['fn']),(1,1,0))
        self.assertEqual(m['precision'],.5)
        self.assertEqual(m['ap50'],1.)

    def test_confidence_order_and_stable_tie(self):
        o,m=b.match([gt()],[pred(conf=.1),pred(conf=.9),pred(conf=.9)])
        self.assertEqual(m['a']['prediction_index'],1)
        self.assertEqual([x[1] for x in o],[True,False,False])

    def test_empty_predictions(self):
        m=b.metrics([([gt()],[])],.25)
        self.assertEqual((m['tp'],m['fp'],m['fn']),(0,0,1))
        self.assertIsNone(m['precision']); self.assertEqual(m['recall'],0.)
        self.assertEqual(m['ap50_95'],0.); self.assertEqual(m['f1'],0.)
        self.assertIsNone(m['mean_matched_iou'])

    def test_operating_threshold_distinct_from_ap(self):
        m=b.metrics([([gt()],[pred(conf=.1)])],.25)
        self.assertEqual(m['recall'],0.); self.assertEqual(m['ap50'],1.)

    def test_ap_rank_penalizes_high_conf_false_positive(self):
        m=b.metrics([([gt()],[pred((.6,.6,.8,.8),.99),pred(conf=.8)])],.25)
        self.assertEqual(m['ap50'],.5)

    def test_partial_recall_and_iou_threshold_grid(self):
        p=pred((0.,0.,.3,.4)) # IoU .75
        m=b.metrics([([gt(),gt('b',(.6,.6,.9,.9))],[p])],.25)
        self.assertAlmostEqual(m['ap50'],51/101)
        self.assertEqual(m['ap_by_iou']['0.95'],0.)
        self.assertLess(m['ap50_95'],m['ap50'])

    def test_pool_by_image_no_cross_image_matches(self):
        m=b.metrics([([gt()],[]),([gt('b',(.5,.5,.9,.9))],[pred()])],.25)
        self.assertEqual((m['tp'],m['fp'],m['fn']),(0,1,2))
        self.assertEqual(m['ap50'],0.)

    def test_pair_lost_gained_and_missing_scores(self):
        g=[gt(),gt('b',affected=False,index=2),gt('c',index=3)]
        def hit(c): return dict(confidence=c,iou=1.)
        r=b.pair_rows('variant','base','global_clear',g,{'b':hit(.6),'c':hit(.4)},{'a':hit(.8),'c':hit(.7)})
        s=b.summarize_pair(r)
        self.assertEqual((s['lost'],s['gained'],s['both_detected']),(1,1,1))
        self.assertEqual(s['detection_drop_rate'],.5)
        self.assertAlmostEqual(s['confidence_delta_both'],-.3)
        self.assertAlmostEqual(s['score_delta_with_miss_zero'],(-.8+.6-.3)/3)
        self.assertIsNone(r[0]['confidence_delta_both'])
        self.assertEqual(r[1]['group'],'control')

    def test_no_baseline_detection_does_not_create_drop_zero(self):
        r=b.pair_rows('v','b','global_clear',[gt()],{}, {})
        self.assertIsNone(b.summarize_pair(r)['detection_drop_rate'])

    def test_predictions_fail_closed(self):
        for p in [pred(conf=float('nan')),pred((-1.,0.,.4,.4)),pred((.4,0.,.1,.4)),dict(pred(),class_id=1),dict(pred(),class_id=True)]:
            with self.subTest(p=p),self.assertRaises(ValueError): b.validate_predictions([p])

    def test_smoke_adapter_clearly_labeled(self):
        a=b.SmokeAdapter(); self.assertFalse(a.metadata['scientific_result'])
        job=dict(row={'id':b.CONTROL},annotations=[gt(),gt('b',affected=False,index=2)])
        self.assertEqual(len(a.predict(job)),2); job['row']['id']='variant'
        self.assertEqual(len(a.predict(job)),1)

    def test_pack_requires_completed_report(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'out'; root.mkdir(); z=root.parent/'out.zip'
            b.write(root/'report.json',dict(schema=b.SCHEMA,status='ERROR_INCOMPLETE'))
            with self.assertRaises(ValueError): b.pack(root,z)
            self.assertFalse(z.exists())
            b.write(root/'report.json',dict(schema=b.SCHEMA,status='PASS_SMOKE',images=1))
            for n in ('scenes.csv','groups.csv','paired_objects.csv','paired_summary.csv','paired_groups.csv','index.html'): (root/n).write_text('fixture')
            for folder,ext in [('predictions','.json'),('previews','.jpg')]:
                (root/folder).mkdir(); (root/folder/('a'+ext)).write_text('fixture')
            b.pack(root,z)
            with zipfile.ZipFile(z) as zz:
                manifest=json.loads(zz.read('archive_manifest.json'))
                self.assertEqual(len(manifest['files']),9); self.assertIsNone(zz.testzip())
            with self.assertRaises(ValueError): b.pack(root,z)

    def test_missing_model_path_refused_without_ml_import(self):
        with self.assertRaises(ValueError): b.YoloAdapter(Path('nonexistent.pt'),'ice_cream','cpu',960,.001,.7,300)

    def test_model_class_mapping_and_coco_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            w=Path(td)/'model.pt'; w.write_bytes(b'fake checkpoint for mock only')
            mock_model=types.SimpleNamespace(task='detect',names={0:'person',3:'product'})
            ultra=types.SimpleNamespace(__version__='mock',YOLO=lambda *a,**k:mock_model)
            torch=types.SimpleNamespace(__version__='mock',version=types.SimpleNamespace(cuda=None),cuda=types.SimpleNamespace(is_available=lambda:False))
            with patch.dict(sys.modules,{'ultralytics':ultra,'torch':torch}):
                with self.assertRaisesRegex(ValueError,'class absent'):
                    b.YoloAdapter(w,'ice_cream','cpu',960,.001,.7,300)
                a=b.YoloAdapter(w,'product','cpu',960,.001,.7,300)
                self.assertEqual(a.options['classes'],[3]); self.assertEqual(a.metadata['dataset_class_id'],0)

    def test_dataset_rejects_incomplete_report(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); b.write(root/'report.json',dict(schema=b.INPUT_SCHEMA,status='ERROR')); b.write(root/'geometry.json',{})
            with self.assertRaises(ValueError): b.load_dataset(root)


if __name__=='__main__': unittest.main()
