"""Research Runner contract: generated test data and a stub renderer, not Blender QA."""
from copy import deepcopy
from contextlib import redirect_stderr
from io import StringIO
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageChops
from scripts import run_research_dataset as runner
from scripts import manage_research_runs as runs
from scripts import build_dataset_manifests as manifests
import test_validate_research_dataset as fixtures


def init_fixture(root, template, engine_root=None):
    shutil.copytree(template, root)
    shutil.copyfile(runs.ROOT/runs.SCHEMA, root/runs.SCHEMA)
    (root/'configs').mkdir()
    # Real catalog for Blender smoke; bounded catalog fixture for contract tests.
    if engine_root is None:
        variants = {'00_clean': {'preset':'QA_TRANSPARENT','coverage':0},
                    '01_light_condensation':{'preset':'LIGHT_CONDENSATION','coverage':.35},
                    '07_macro_droplets_only':{'preset':'HEAVY_CONDENSATION','water':{'kind':'MACRO'}}}
        (root/runner.CONFIG).write_text(json.dumps({'schema':'bvt.glass-gallery.v02','variants':variants}))
        (root/'scripts').mkdir(); (root/'scripts/fixture.py').write_text('# fixture\n')
        (root/'bvt_studio').mkdir()
        for name in ('scripts/bvt_glass_effect_gallery_v02.py','scripts/blender_release_reopen.py','bvt_studio/__init__.py'):
            (root/name).write_text('# mocked renderer\n')
    else:
        shutil.copyfile(engine_root/runner.CONFIG, root/runner.CONFIG)
        for dirname in ('scripts','bvt_studio'):
            shutil.copytree(engine_root/dirname, root/dirname, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (root/'.gitignore').write_text('/data_local/\n__pycache__/\n')
    for args in [('init','-q'),('add','.'),('-c','user.name=QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false','commit','-qm','Fixture')]:
        subprocess.run(['git',*args],cwd=root,check=True,stdout=subprocess.DEVNULL)


def approve_mask(root, collection, key, large=False):
    path = root/f'datasets/manifests/{collection}.jsonl'
    records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    record = next(r for r in records if r['image_id']==key)
    if large:
        # Purpose-built synthetic geometry, never a mask of a real photo.
        source = root/record['local_cache_path']
        im=Image.new('RGB',(320,240),(45,60,85)); draw=ImageDraw.Draw(im)
        for i in range(5):
            draw.rectangle((42+i*48,55,74+i*48,185),fill=(90+i*22,100,160-i*13))
        im.save(source,format=record['file_format'])
        record.update(width=320,height=240,sha256=sha256(source.read_bytes()).hexdigest())
        path.write_bytes(manifests.encode(records))
    mask = root/f'data_local/{collection}/glass_masks/{key}.png'
    im = Image.new('L',(record['width'],record['height']))
    # Non-rectangular support: deliberately leave a hole in the envelope.
    draw = ImageDraw.Draw(im)
    draw.rectangle((1,1,record['width']-2,record['height']-2),fill=255)
    draw.rectangle((2,2,3,3),fill=0)
    im.save(mask)
    review = dict(schema='bvt.research-annotation-review.v1',kind='glass_mask',image_id=key,
                  input_sha256=record['sha256'],artifact_sha256=sha256(mask.read_bytes()).hexdigest(),
                  class_catalog_sha256=None,reviewer='synthetic test fixture only',decision='approved')
    mask.with_suffix('.json').write_text(json.dumps(review))
    return mask


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ValidatorTests.setUpClass()
        cls.addClassCleanup(fixtures.ValidatorTests.doClassCleanups)
        cls.template = fixtures.ValidatorTests.template

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()/'repo'
        init_fixture(self.root,self.template)
        self.c='synthetic_chatgpt'; self.key='chatgpt_000001'
        self.blender=self.root/'mock-blender'; self.blender.write_text('fixture')

    def plan(self,effect='00_clean',ids=None,**kwargs):
        return runner.make_plan(self.root,self.c,'pilot',effect,42,[self.key] if ids is None else ids,**kwargs)

    def test_unreviewed_mask_blocks_without_writes(self):
        plan=self.plan('01_light_condensation')
        self.assertFalse(plan['executable'])
        self.assertEqual(plan['jobs'][0]['blockers'],['verified_glass_mask_required'])
        with self.assertRaisesRegex(ValueError,'Execution blocked'):
            runner.execute(self.root,plan)
        self.assertFalse(runs.run_path(self.root,self.c,'pilot').exists())

    def test_deterministic_plan_and_limit(self):
        ids=['chatgpt_000002',self.key]
        self.assertEqual(self.plan(ids=ids),self.plan(ids=ids[::-1]))
        with self.assertRaisesRegex(ValueError,'max-images'):
            runner.make_plan(self.root,self.c,'all','00_clean',42,None)
        self.assertEqual(len(runner.make_plan(self.root,self.c,'all','00_clean',42,None,100)['jobs']),100)

    def test_invalid_selection_and_stress(self):
        for effect,ids in [('12_stress_optics',[self.key]),('00_clean',[self.key,self.key]),('00_clean',['wikimedia_000001'])]:
            with self.assertRaises(ValueError): self.plan(effect,ids)

    def test_clean_both_collections(self):
        for c,key in [(self.c,self.key),('real_wikimedia','wikimedia_000001')]:
            plan=runner.make_plan(self.root,c,'clean-'+c,'00_clean',42,[key])
            result=runner.execute(self.root,plan)
            folder=runs.run_path(self.root,c,plan['run_id'])
            m=runs.check(self.root,c,plan['run_id'])
            row=m['records'][0]
            self.assertEqual(m['status'],'outputs_recorded')
            self.assertEqual(row['qa_status'],'pending')
            self.assertIsNone(row['label_path']); self.assertIsNone(row['mask_path'])
            with Image.open(self.root/row['input_path']) as a, Image.open(folder/row['output_path']) as b:
                self.assertIsNone(ImageChops.difference(a.convert('RGB'),b).getbbox())
            self.assertEqual(result['status'],'PASS')
            self.assertTrue(result['jobs'][0]['evidence']['identity_decoded_rgb'])
            self.assertEqual(sha256((self.root/row['input_path']).read_bytes()).hexdigest(),row['input_sha256'])

    def test_collision(self):
        plan=self.plan(); runner.execute(self.root,plan)
        with self.assertRaisesRegex(ValueError,'Run already exists'): runner.execute(self.root,plan)

    def test_corrupt_source(self):
        plan=self.plan(); (self.root/plan['jobs'][0]['output_path']).parent.mkdir(parents=True,exist_ok=True)
        record=runs.inputs(self.root,self.c,[self.key])[0][0]
        (self.root/record['input_path']).write_bytes(b'bad')
        with self.assertRaises(ValueError): runner.execute(self.root,plan)
        self.assertFalse(runs.run_path(self.root,self.c,'pilot').exists())

    def test_mask_tamper_blocks(self):
        mask=approve_mask(self.root,self.c,self.key)
        plan=self.plan('01_light_condensation'); self.assertTrue(plan['executable'])
        mask.write_bytes(b'bad')
        with self.assertRaises(ValueError): runner.execute(self.root,plan,self.blender)
        self.assertFalse(runs.run_path(self.root,self.c,'pilot').exists())

    def stub(self,command,root,log):
        # Verify the real adapter's external CLI contract; no photorealism claim.
        args=list(map(str,command)); log.write_text('stub renderer')
        def arg(key): return args[args.index(key)+1]
        if '--blend' in args:
            m=json.loads(Path(arg('--manifest')).read_text())
            Path(arg('--report')).write_text(json.dumps({'status':'PASS','variant':m['variant']})); return
        gallery=Path(arg('--output')); mode=arg('--mode'); folder=gallery/mode
        folder.mkdir(); (folder/'masks').mkdir()
        photo=Path(arg('--photo')); spec=json.loads(Path(arg('--config')).read_text())['variants'][mode]
        # Mirror the real gallery path guard, which the original stub missed.
        self.assertFalse(gallery.resolve().is_relative_to(photo.resolve().parent))
        self.assertEqual((gallery/'source.png').read_bytes(), photo.read_bytes())
        rect=json.loads(Path(arg('--rects-file')).read_text())['glass_rectangles']
        self.assertTrue((Path(arg('--mask-dir'))/'mask_glass_001.png').is_file())
        with Image.open(photo) as im:
            # Stub intentionally changes all pixels; final composite must remove outside changes.
            out=im.copy() if mode=='00_clean' else Image.new('RGB',im.size,(250,200,170))
            out.save(folder/'render.png')
        (folder/'scene.blend').write_bytes(b'fixture')
        m=dict(schema='bvt.glass-gallery.v02',variant=mode,source_sha256=sha256(photo.read_bytes()).hexdigest(),
               rects=rect,mask_provenance='external_not_verified',calibration='v0.2.1_matched_neutral_realistic_atlas',
               panes=[dict(name='Glass_p_001',seed=spec['seed_base'],preset=spec['preset'],mask_packed=True,water_kind=None)],
               quality=None if mode=='00_clean' else {'leakage_pixels_beyond_3px_geometry_guard':0})
        (folder/'manifest.json').write_text(json.dumps(m))

    def test_masked_renderer_and_registration(self):
        mask=approve_mask(self.root,self.c,self.key)
        plan=self.plan('01_light_condensation')
        with patch.object(runner.subprocess,'check_output',wraps=subprocess.check_output) as check, patch.object(runner,'invoke',side_effect=self.stub):
            real=check._mock_wraps
            check.side_effect=lambda cmd,*a,**k:'Blender 5.2.3\n' if '--version' in list(map(str,cmd)) else real(cmd,*a,**k)
            report=runner.execute(self.root,plan,self.blender)
        folder=runs.run_path(self.root,self.c,'pilot'); row=runs.check(self.root,self.c,'pilot')['records'][0]
        with Image.open(mask) as gate, Image.open(self.root/row['input_path']) as original, Image.open(folder/row['output_path']) as output:
            outside=gate.point(lambda x:255-x)
            self.assertIsNone(Image.composite(ImageChops.difference(original.convert('RGB'),output),Image.new('RGB',output.size),outside).getbbox())
            self.assertIsNotNone(ImageChops.difference(original.convert('RGB'),output).getbbox())
        self.assertEqual(report['status'],'PASS'); self.assertEqual(row['qa_status'],'pending')
        self.assertEqual(report['jobs'][0]['evidence']['outside_mask_changed_pixels'],0)
        self.assertIsNone(row['mask_path'])

    def test_renderer_failure_not_registered(self):
        approve_mask(self.root,self.c,self.key)
        plan=self.plan('01_light_condensation'); real=subprocess.check_output
        with patch.object(runner.subprocess,'check_output',side_effect=lambda cmd,*a,**k:'Blender 5.2.3\n' if '--version' in list(map(str,cmd)) else real(cmd,*a,**k)), patch.object(runner,'invoke',side_effect=RuntimeError('render failure')):
            with self.assertRaisesRegex(RuntimeError,'render failure'): runner.execute(self.root,plan,self.blender)
        folder=runs.run_path(self.root,self.c,'pilot')
        self.assertEqual(runs.check(self.root,self.c,'pilot')['status'],'prepared')
        self.assertEqual(json.loads((folder/'reports/runner_report.json').read_text())['status'],'ERROR')

    def test_invoke_exposes_child_error_and_keeps_log(self):
        log=self.root/'child.log'
        stderr=StringIO()
        with redirect_stderr(stderr), self.assertRaisesRegex(RuntimeError, r'Blender failed \(7\)'):
            runner.invoke([sys.executable, '-c', 'import sys; print("fixture child error"); sys.exit(7)'], self.root, log)
        self.assertIn('fixture child error', stderr.getvalue())
        self.assertIn('fixture child error', log.read_text(encoding='utf-8'))
        self.assertIn('BLENDER_LOG=', stderr.getvalue())

    def test_catalog_changed(self):
        plan=self.plan(); p=self.root/runner.CONFIG; p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Stale plan'): runner.execute(self.root,plan)


def blender_smoke(engine_root, blender):
    """Optional real Blender smoke, using only purpose-built synthetic fixtures."""
    fixtures.ValidatorTests.setUpClass()
    try:
        with tempfile.TemporaryDirectory(prefix='bvt16_blender_fixture_') as temp:
            root=Path(temp).resolve()/'repo'
            init_fixture(root,fixtures.ValidatorTests.template,engine_root)
            for c,key in [('synthetic_chatgpt','chatgpt_000001'),('real_wikimedia','wikimedia_000001')]:
                approve_mask(root,c,key,large=True)
                plan=runner.make_plan(root,c,'artifact-'+c,'01_light_condensation',42,[key])
                report=runner.execute(root,plan,blender)
                assert report['status']=='PASS'
                assert report['jobs'][0]['evidence']['outside_mask_changed_pixels']==0
                assert runs.check(root,c,plan['run_id'])['status']=='outputs_recorded'
                print('BLENDER_FIXTURE_PASS='+c,flush=True)
    finally:
        fixtures.ValidatorTests.doClassCleanups()
