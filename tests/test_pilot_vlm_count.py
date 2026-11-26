import base64
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bvt_pilot_vlm_count as v


class VLMCountTests(unittest.TestCase):
    def test_strict_parse(self):
        def reply(content): return {'done':True,'done_reason':'stop','message':{'content':content}}
        self.assertEqual(v.parse_count(reply('{"count":0}')),(0,'ok'))
        self.assertEqual(v.parse_count(reply('{"count":28}')),(28,'ok'))
        for bad in ('{"count":true}','{"count":2.0}','{"count":-1}','{"count":"3"}',
                    '{"count":1,"count":2}','{"count":3,"extra":1}','28','```json\n{"count":3}\n```'):
            self.assertIsNone(v.parse_count(reply(bad))[0])
        self.assertIsNone(v.parse_count({'done':False})[0])

    def test_payload(self):
        p=v.payload(v.MODEL,b'png bytes')
        self.assertEqual(base64.b64decode(p['messages'][0]['images'][0]),b'png bytes')
        self.assertEqual(p['messages'][0]['content'],v.PROMPT)
        self.assertEqual(len(p['messages']),1)
        self.assertFalse(p['stream'])

    def test_metrics(self):
        r=[{'scene':'a','gt':25,'count':20},{'scene':'b','gt':30,'count':30},{'scene':'c','gt':30,'count':None}]
        m=v.summarize(r)
        self.assertEqual((m['valid'],m['invalid'],m['exact'],m['mae_valid'],m['bias_valid']),(2,1,1,2.5,-2.5))
        self.assertAlmostEqual(m['exact_rate_all'],1/3)
        b={'a':{'count':25,'gt':25},'b':{'count':27,'gt':30},'c':{'count':30,'gt':30}}
        self.assertEqual(v.paired(r,b),{'paired_valid':2,'paired_delta_mae':1.,'worse':1,'better':1,'same':0})

    def test_dry_run_no_api(self):
        with TemporaryDirectory() as t:
            root=Path(t); out=root/'out'
            a=SimpleNamespace(run=root/'run',qa=root/'qa',baseline=root/'base',output=out,
                              clean_only=True,model=v.MODEL,execute=False)
            with patch.object(v.robust,'load_inputs',return_value=([{'condition':'00_clean','id':'0001'}],{},{})),patch.object(v,'request') as req:
                v.run(a); req.assert_not_called(); self.assertFalse(out.exists())


if __name__=='__main__': unittest.main()
