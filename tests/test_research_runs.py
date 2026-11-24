"""Research run registry tests using generated fixtures, no Blender or real data."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image
from jsonschema import ValidationError
from scripts import manage_research_runs as r


class ResearchRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.template = Path(temp.name) / 'repo'
        schemas = cls.template / 'datasets/schemas'
        schemas.mkdir(parents=True)
        for name in ('dataset_manifest.schema.json', 'run_manifest.schema.json'):
            shutil.copyfile(r.ROOT / 'datasets/schemas' / name, schemas / name)
        required = json.loads((schemas / 'dataset_manifest.schema.json').read_text())['required']
        manifests = cls.template / 'datasets/manifests'
        manifests.mkdir()
        for collection, (prefix, ext, fmt, storage, origin) in r.COLLECTIONS.items():
            records = []
            clean = cls.template / 'data_local' / collection / 'clean/images'
            clean.mkdir(parents=True)
            for i in range(1, 101):
                image_id = f'{prefix}_{i:06d}'
                name = image_id + ext
                path = clean / name
                Image.new('RGB', (8+i, 10), (i, 7, 20)).save(path, format=fmt)
                row = dict.fromkeys(required)
                row.update(schema_version='1.0', image_id=image_id, collection_id=collection,
                           relative_path=f'clean/images/{name}', sha256=r.digest(path.read_bytes()),
                           width=8+i, height=10, file_format=fmt, origin_type=origin,
                           source_page_url=f'https://commons.wikimedia.org/wiki/File:Fixture_{i}.jpg' if origin=='real' else None,
                           source_group_id=image_id, storage_provider='google_drive',
                           storage_relative_path=f'{storage}/images/{name}',
                           local_cache_path=f'data_local/{collection}/clean/images/{name}',
                           integrity_status='verified', source_registry_version='sha256:'+'0'*64)
                for key in ('license_verification_status','derivative_use_review_status','commercial_use_review_status',
                            'redistribution_review_status','trademark_review_status','annotation_status','glass_mask_status'):
                    row[key] = 'pending'
                records.append(row)
            (manifests / f'{collection}.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in records), encoding='utf-8')
        (cls.template / '.gitignore').write_text('/data_local/\n')
        (cls.template / 'scripts').mkdir()
        (cls.template / 'scripts/fixture.py').write_text('# fixture\n')
        def git(*args):
            subprocess.run(['git', *args], cwd=cls.template, check=True, capture_output=True)
        git('init', '-q')
        git('add', '.')
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture')

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'repo'
        shutil.copytree(self.template, self.root)
        self.c = 'synthetic_chatgpt'
        self.image = 'chatgpt_000001'
        self.folder = self.root / 'data_local' / self.c / 'runs/pilot-001'
        self.manifest = self.folder / 'run_manifest.json'
        self.original = self.root / 'data_local' / self.c / 'clean/images/chatgpt_000001.png'
        self.output = self.folder / 'augmented/images/chatgpt_000001.png'

    def init(self, **kwargs):
        options = dict(collection=self.c, run_id='pilot-001', preset_id='fixture', seed=42,
                       parameters={'intensity': 0.1}, image_ids=[self.image])
        options.update(kwargs)
        return r.initialize(self.root, **options)

    def render_fixture(self, size=(9,10), fmt='PNG'):
        Image.new('RGB', size, (110, 120, 130)).save(self.output, format=fmt)

    def record(self, **kwargs):
        return r.record_outputs(self.root, self.c, 'pilot-001', **kwargs)

    def check(self):
        return r.check(self.root, self.c, 'pilot-001')

    def test_init_contract_and_paths(self):
        original = self.original.read_bytes()
        m = self.init(engine_versions={'renderer':'test-only'})
        self.assertEqual(m['status'], 'prepared')
        self.assertEqual(m['seed'], 42)
        self.assertEqual(m['tool_versions']['declared_engine_versions'], {'renderer':'test-only'})
        self.assertEqual(m['records'][0]['input_sha256'], r.digest(original))
        self.assertIsNone(m['records'][0]['output_sha256'])
        self.assertEqual(m['records'][0]['qa_status'], 'pending')
        self.assertTrue(all((self.folder / name).is_dir() for name in r.DIRS))
        self.assertFalse(self.output.exists())
        self.assertEqual(self.check(), m)
        self.assertEqual(self.original.read_bytes(), original)

    def test_full_collection(self):
        m = self.init(image_ids=None)
        self.assertEqual(len(m['records']), 100)
        self.assertEqual(len({x['input_sha256'] for x in m['records']}), 100)

    def test_distinct_runs_and_collision(self):
        self.init()
        data = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Run already exists'):
            self.init()
        with self.assertRaisesRegex(ValueError, 'Run already exists'):
            self.init(collection='real_wikimedia', image_ids=['wikimedia_000001'])
        self.init(run_id='pilot-002')
        self.assertEqual(self.manifest.read_bytes(), data)

    def test_invalid_id_or_selection(self):
        for bad in ('../escape', 'a/b', 'CON', 'con', 'a\\b', ''):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.init(run_id=bad)
        for ids in ([], [self.image,self.image], ['wikimedia_000001']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.init(image_ids=ids)
        self.assertFalse(self.folder.exists())

    def test_invalid_parameters_no_directory(self):
        with self.assertRaises(ValidationError):
            self.init(seed=-1)
        with self.assertRaises(ValueError):
            self.init(parameters={'bad':float('nan')})
        self.assertFalse(self.folder.exists())

    def test_input_corruption_rejected(self):
        self.original.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.init()
        self.assertFalse(self.folder.exists())

    def test_register_idempotent_and_read_only(self):
        self.init()
        original = self.original.read_bytes()
        self.render_fixture()
        m = self.record(generated_at='2026-11-24T12:00:00Z')
        self.assertEqual(m['status'], 'outputs_recorded')
        self.assertEqual(m['records'][0]['output_sha256'], r.digest(self.output.read_bytes()))
        self.assertEqual(m['records'][0]['qa_status'], 'pending')
        self.assertEqual(m['records'][0]['generated_at'], '2026-11-24T12:00:00Z')
        stamp = self.manifest.stat().st_mtime_ns
        self.assertEqual(self.record(), m)
        self.assertEqual(self.check(), m)
        self.assertEqual(self.manifest.stat().st_mtime_ns, stamp)
        self.assertEqual(self.original.read_bytes(), original)

    def test_missing_extra_and_invalid_output(self):
        self.init()
        original = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Output inventory mismatch'):
            self.record()
        self.render_fixture(size=(10,10))
        with self.assertRaisesRegex(ValueError, 'format/dimensions'):
            self.record()
        self.render_fixture(fmt='JPEG')
        with self.assertRaisesRegex(ValueError, 'format/dimensions'):
            self.record()
        self.render_fixture()
        extra = self.output.parent / 'extra.png'
        extra.touch()
        with self.assertRaisesRegex(ValueError, 'Output inventory mismatch'):
            self.record()
        self.assertEqual(self.manifest.read_bytes(), original)

    def test_registered_output_tamper_detected(self):
        self.init()
        self.render_fixture()
        self.record()
        Image.new('RGB',(9,10),(1,2,3)).save(self.output)
        with self.assertRaisesRegex(ValueError, 'Output SHA256 mismatch'):
            self.check()

    def test_code_or_inventory_change_rejected(self):
        self.init()
        self.render_fixture()
        (self.root / 'scripts/fixture.py').write_text('# changed\n')
        with self.assertRaisesRegex(ValueError, 'Code changed'):
            self.record()
        path = self.root / 'datasets/manifests/synthetic_chatgpt.jsonl'
        path.write_bytes(path.read_bytes().replace(b'"width": 9',b'"width": 9 ',1))
        with self.assertRaisesRegex(ValueError, 'Dataset manifest changed'):
            self.check()

    def test_qa_report_bound_to_output_and_immutable(self):
        m = self.init()
        self.render_fixture()
        report_path = self.folder / 'reports/qa_results.json'
        row = dict(image_id=self.image, input_sha256=m['records'][0]['input_sha256'],
                   output_sha256='0'*64, qa_status='REVIEW')
        report = dict(schema='bvt.research-run.qa.v1', records=[row])
        report_path.write_bytes(r.encode(report))
        with self.assertRaisesRegex(ValueError, 'QA hash mismatch'):
            self.record()
        row['output_sha256'] = r.digest(self.output.read_bytes())
        report_path.write_bytes(r.encode(report))
        m = self.record()
        self.assertEqual(m['records'][0]['qa_status'], 'REVIEW')
        self.assertEqual(m['qa_report_sha256'], r.digest(report_path.read_bytes()))
        row['qa_status'] = 'PASS'
        report_path.write_bytes(r.encode(report))
        with self.assertRaisesRegex(ValueError, 'QA report hash changed'):
            self.check()

    def test_hardlinked_output_rejected(self):
        import os
        self.init()
        try:
            os.link(self.original, self.output)
        except OSError as exc:
            self.skipTest(f'Hard links unavailable: {exc}')
        with self.assertRaisesRegex(ValueError, 'Hard-linked output forbidden'):
            self.record()


if __name__ == '__main__':
    unittest.main()
