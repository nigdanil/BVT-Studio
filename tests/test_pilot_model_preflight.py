import importlib.util
from pathlib import Path
import tempfile
import argparse
import csv
import json
import contextlib
import io
import unittest

spec=importlib.util.spec_from_file_location('preflight',Path(__file__).resolve().parents[1]/'scripts'/'bvt_pilot_model_preflight.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ModelPreflightTests(unittest.TestCase):
    def test_one_to_one(self):
        gt=[[0,0,.5,.5]]
        predictions=[dict(xyxy=gt[0],score=.9),dict(xyxy=gt[0],score=.8),dict(xyxy=[.6,.6,1,1],score=.7)]
        outcomes=m.match(gt,predictions,.25)
        self.assertEqual(outcomes,[(.9,True),(.8,False),(.7,False)])
        self.assertEqual(m.stats(outcomes,1)['tp'],1)
        self.assertEqual(m.stats(outcomes,1)['fp'],2)
        self.assertAlmostEqual(m.ap50(outcomes,1),1.)
    def test_confidence_and_empty(self):
        gt=[[0,0,.5,.5]]
        self.assertEqual(m.match(gt,[dict(xyxy=gt[0],score=.2)],.25),[])
        self.assertEqual(m.stats([],1)['recall'],0)
        self.assertEqual(m.ap50([],1),0)
    def test_ap_partial(self):
        self.assertAlmostEqual(m.ap50([(.9,True)],2),51/101)
    def test_labels(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.txt';p.write_text('0 0.5 0.5 0.2 0.2\n')
            self.assertEqual(m.load_labels(p),[[.4,.4,.6,.6]])
            for text in ['1 0.5 0.5 0.2 0.2','0 0.1 0.5 0.8 0.2','0 nan 0.5 0.1 0.2']:
                p.write_text(text)
                with self.assertRaises(ValueError):m.load_labels(p)

    def test_dry_run_and_integrity_guard(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); run=root/'run'; qa=root/'qa'; qa.mkdir()
            for kind in ('images','labels','metadata'):
                (run/'00_clean'/kind).mkdir(parents=True)
            rows=[]
            for i,count in enumerate(m.EXPECTED_COUNTS,1):
                sid=f'{i:04d}'; stem=f'scene_{sid}'
                img=run/'00_clean'/'images'/(stem+'.png'); lbl=run/'00_clean'/'labels'/(stem+'.txt')
                Image.new('RGB',(1672,941),(i,0,0)).save(img)
                lbl.write_text('0 .5 .5 .2 .2\n'*count)
                row=dict(scene=sid,condition='00_clean',boxes=count,image_sha256=m.sha(img),label_sha256=m.sha(lbl));rows.append(row)
                meta=dict(row,id=sid,condition={'id':'00_clean'},geometry_unchanged=True)
                m.write_json(run/'00_clean'/'metadata'/(stem+'.json'),meta)
            m.write_json(qa/'qa_summary.json',dict(status='PASS',offline=False,images_verified=210,source_boxes=285,scenes_passed=10,failures=[]))
            with (qa/'metrics.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            out=root/'result';args=argparse.Namespace(run=run,qa=qa,output=out,model='world',device='cpu',execute=False)
            with contextlib.redirect_stdout(io.StringIO()):m.run(args)
            self.assertFalse(out.exists())
            lbl.write_text('corrupted')
            with self.assertRaisesRegex(ValueError,'provenance mismatch'):m.run(args)

if __name__=='__main__':unittest.main()
