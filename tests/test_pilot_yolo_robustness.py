import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import bvt_pilot_yolo_robustness as m


class RobustnessTests(unittest.TestCase):
    def test_matrix(self):
        self.assertEqual(len(m.CONDITIONS), 21)
        self.assertEqual(len(m.SIDS), 10)
        self.assertEqual(m.CONF, .05)

    def test_pooled_matching(self):
        gt=[[0,0,.5,.5]]
        hit=dict(xyxy=gt[0],score=.06,class_id=0)
        low=dict(xyxy=gt[0],score=.01,class_id=0)
        r=m.aggregate([(gt,[hit]),(gt,[low])])
        self.assertEqual(r['tp'],1)
        self.assertEqual(r['recall'],.5)
        self.assertEqual(r['ap50'],1.)
        self.assertEqual(m.matched_ids(gt,[hit,low]),{0})

    def test_transitions_and_delta(self):
        a=[0,0,.4,.4]; b=[.6,.6,1,1]
        jobs=[]; predictions={}
        for c in m.CONDITIONS:
            for sid in m.SIDS:
                jobs.append(dict(id=sid,condition=c,gt=[a,b],intensity=0.,rgb_delta=0.))
                predictions[c,sid]=[dict(xyxy=a if c=='00_clean' else b,score=.1,class_id=0)]
        conditions,rows=m.summarize(jobs,predictions)
        self.assertEqual(len(rows),210)
        self.assertEqual(conditions[1]['lost_clean_tp'],10)
        self.assertEqual(conditions[1]['gained_tp'],10)
        self.assertEqual(conditions[1]['delta_recall'],0.)

    def test_invalid_predictions(self):
        with self.assertRaises(ValueError):
            m.validate_predictions([dict(xyxy=[0,0,1,1],score=float('nan'),class_id=0)])
        with self.assertRaises(ValueError):
            m.validate_predictions([dict(xyxy=[0,0,1,1],score=.5,class_id=1)])


if __name__=='__main__': unittest.main()
