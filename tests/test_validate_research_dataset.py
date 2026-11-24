"""Validator fixtures are tiny generated images, never live research assets."""
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from scripts import validate_research_dataset as v
from scripts import build_dataset_manifests as m


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.template = Path(temp.name).resolve()
        schema = cls.template / m.SCHEMA
        schema.parent.mkdir(parents=True)
        shutil.copyfile(m.ROOT / m.SCHEMA, schema)
        fields = json.loads(schema.read_text())['required']
        for rel in v.storage.directory_paths():
            (cls.template / rel).mkdir(parents=True, exist_ok=True)
        for c, (prefix, ext, fmt, drive, origin) in v.storage.COLLECTIONS.items():
            doc = cls.template / (m.REGISTRY if origin == 'real' else m.SYNTHETIC_DOC)
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_bytes(b'test registry version')
            records = []
            for i in range(1, 101):
                key = f'{prefix}_{i:06d}'
                name = key + ext
                rel = f'data_local/{c}/clean/images/{name}'
                image = cls.template / rel
                Image.new('RGB', (i+8, 10), (i, 7, 20)).save(image, format=fmt)
                record = dict.fromkeys(fields)
                record.update(schema_version='1.0', image_id=key, collection_id=c,
                              relative_path=f'clean/images/{name}', sha256=sha256(image.read_bytes()).hexdigest(),
                              width=i+8, height=10, file_format=fmt, origin_type=origin,
                              source_page_url=f'https://commons.wikimedia.org/wiki/File:Fixture_{i}.jpg' if origin == 'real' else None,
                              source_group_id=key, storage_provider='google_drive',
                              storage_relative_path=f'{drive}/images/{name}', local_cache_path=rel,
                              integrity_status='verified', source_registry_version='sha256:'+sha256(doc.read_bytes()).hexdigest())
                for k in (*v.RIGHTS, 'license_verification_status', 'annotation_status', 'glass_mask_status'):
                    record[k] = 'pending'
                records.append(record)
            manifest = cls.template / f'datasets/manifests/{c}.jsonl'
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_bytes(m.encode(records))

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / 'repo'
        shutil.copytree(self.template, self.root)
        self.collection = 'synthetic_chatgpt'
        self.base = self.root / 'data_local' / self.collection
        self.image = self.base / 'clean/images/chatgpt_000001.png'
        self.manifest = self.root / 'datasets/manifests/synthetic_chatgpt.jsonl'

    def edit(self, fn, path=None):
        path = path or self.manifest
        records = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        fn(records)
        path.write_bytes(m.encode(records))

    def check(self, code):
        report = v.validate(self.root)
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn(code, {i['code'] for i in report['issues']})
        self.assertEqual(report['totals']['ready_for_qa'], 0)
        self.assertEqual(report['totals']['ready_for_publication'], 0)
        return report

    def test_complete_unannotated_and_read_only(self):
        before = {p: (sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        report = v.validate(self.root)
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['totals'], dict(expected=200, present=200, missing=0, unique_sha256=200,
                                               bad_format=0, unverified=0, ready_for_qa=0, ready_for_publication=0))
        self.assertEqual(report['collections'][self.collection]['split_counts'], {'unassigned':100})
        self.assertEqual(before, {p:(sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_missing_and_extra_and_directory(self):
        self.image.unlink()
        (self.image.parent / 'extra.png').write_bytes(b'extra')
        (self.base / 'runs').rmdir()
        report = self.check('directory_missing')
        self.assertEqual(report['totals']['missing'], 1)
        self.assertIn('unexpected_entry', {i['code'] for i in report['issues']})

    def test_bad_bytes_and_hash(self):
        self.image.write_bytes(b'not an image')
        report = self.check('sha256_mismatch')
        self.assertEqual(report['totals']['bad_format'], 1)
        self.assertEqual(report['totals']['unverified'], 1)

    def test_valid_wrong_format_matching_hash(self):
        Image.new('RGB', (9,10)).save(self.image, format='JPEG')
        self.edit(lambda r:r[0].update(sha256=sha256(self.image.read_bytes()).hexdigest()))
        self.assertEqual(self.check('image_format_or_decode_invalid')['totals']['bad_format'], 1)

    def test_wrong_dimensions(self):
        self.edit(lambda r:r[0].update(width=123))
        self.check('dimensions_mismatch')

    def test_duplicate_declared_and_actual(self):
        other = self.image.with_name('chatgpt_000002.png')
        shutil.copyfile(self.image, other)
        self.edit(lambda r:r[1].update(sha256=r[0]['sha256'],width=r[0]['width']))
        report = self.check('duplicate_declared_sha256')
        self.assertIn('duplicate_actual_sha256', {i['code'] for i in report['issues']})
        self.assertEqual(report['totals']['unique_sha256'], 199)

    def test_duplicate_json_key_and_id(self):
        lines = self.manifest.read_bytes().splitlines()
        lines[0] = b'{"image_id":"chatgpt_000001",' + lines[0][1:]
        lines[2] = lines[1]
        self.manifest.write_bytes(b'\n'.join(lines)+b'\n')
        report = self.check('manifest_record_invalid')
        self.assertEqual(sum(i['code']=='manifest_record_invalid' for i in report['issues']), 2)

    def test_manifest_path_mismatch(self):
        self.edit(lambda r:r[0].update(local_cache_path=r[1]['local_cache_path']))
        self.check('manifest_record_invalid')

    def test_registry_version_mismatch(self):
        (self.root / m.SYNTHETIC_DOC).write_bytes(b'new version')
        self.check('registry_version_mismatch')

    def test_split_leakage_across_collections(self):
        self.edit(lambda r:r[0].update(split='train',source_group_id='same'))
        self.edit(lambda r:r[0].update(split='test',source_group_id='same'), self.root/'datasets/manifests/real_wikimedia.jsonl')
        self.check('split_leakage')

    def test_page_leakage(self):
        def change(r):
            r[0].update(split='train')
            r[1].update(split='val',source_page_url=r[0]['source_page_url'])
        self.edit(change, self.root/'datasets/manifests/real_wikimedia.jsonl')
        self.check('source_page_split_leakage')

    def test_invalid_annotation(self):
        (self.base/'labels/chatgpt_000001.txt').write_text('0 1 1 1 1\n')
        (self.base/'glass_masks/chatgpt_000001.png').write_bytes(b'bad')
        report = self.check('annotation_invalid')
        self.assertEqual(report['records'][0]['annotation_status'],'invalid')
        self.assertEqual(report['records'][0]['glass_mask_status'],'invalid')

    def test_verified_annotation_readiness(self):
        catalog = self.root/'data_local/classes.json'
        catalog.write_text(json.dumps({'schema':'bvt.research-classes.v1','classes':['fixture']}))
        label = self.base/'labels/chatgpt_000001.txt'
        label.write_text('0 0.5 0.5 0.5 0.5\n')
        mask = self.base/'glass_masks/chatgpt_000001.png'
        im = Image.new('L',(9,10)); im.putpixel((4,4),255); im.save(mask)
        for kind, artifact in [('annotation',label),('glass_mask',mask)]:
            review = dict(schema='bvt.research-annotation-review.v1', kind=kind,
                          image_id='chatgpt_000001', input_sha256=sha256(self.image.read_bytes()).hexdigest(),
                          artifact_sha256=sha256(artifact.read_bytes()).hexdigest(),
                          class_catalog_sha256=sha256(catalog.read_bytes()).hexdigest() if kind=='annotation' else None,
                          reviewer='fixture', decision='approved')
            artifact.with_suffix('.json').write_text(json.dumps(review))
        report = v.validate(self.root)
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['totals']['ready_for_qa'],1)
        self.assertEqual(report['totals']['ready_for_publication'],0)

    def test_license_metadata_gate(self):
        def change(r):
            r[0].update(author='Fixture',license_id='CC-BY-4.0',license_url='https://creativecommons.org/licenses/by/4.0/',
                        license_checked_at='2026-11-24',license_evidence_url='https://commons.wikimedia.org/w/index.php?oldid=123',
                        attribution_text='fixture',license_verification_status='api_evidence_recorded')
            r[0].update({k:'approved' for k in v.RIGHTS})
        path = self.root/'datasets/manifests/real_wikimedia.jsonl'
        self.edit(change,path)
        self.assertEqual(v.validate(self.root)['totals']['ready_for_publication'],0)
        self.edit(lambda r:r[0].update(license_verification_status='verified'),path)
        self.assertEqual(v.validate(self.root)['totals']['ready_for_publication'],1)
        self.edit(lambda r:r[0].update(redistribution_review_status='conditional'),path)
        self.assertEqual(v.validate(self.root)['totals']['ready_for_publication'],0)

    def test_missing_manifest_still_reports_inventory(self):
        self.manifest.unlink()
        report = self.check('manifest_unreadable')
        self.assertEqual(report['totals']['present'], 200)
        self.assertEqual(report['totals']['unverified'], 100)

    def test_license_metadata_mismatch(self):
        self.edit(lambda r:r[0].update(license_id='CC0-1.0',license_url='https://creativecommons.org/licenses/by/4.0/'),
                  self.root/'datasets/manifests/real_wikimedia.jsonl')
        self.check('license_metadata_mismatch')
        self.edit(lambda r:r[0].update(license_id='unknown-custom',license_url=None),
                  self.root/'datasets/manifests/real_wikimedia.jsonl')
        self.check('license_metadata_mismatch')

    def test_cli_exit_codes_and_json_failure(self):
        with patch.object(v,'ROOT',self.root), redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()):
            self.assertEqual(v.main(['--require-ready','qa']),1)
            self.assertEqual(v.main([]),0)
            self.image.unlink()
            out.seek(0); out.truncate(0)
            self.assertEqual(v.main(['--json']),1)
            self.assertEqual(json.loads(out.getvalue())['status'],'FAIL')


if __name__ == '__main__':
    unittest.main()
