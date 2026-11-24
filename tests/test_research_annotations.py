"""Offline annotation contract tests. No real images, labels or renderer."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image
from scripts import check_research_annotations as a
from scripts import manage_research_runs as runs


class AnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.template = Path(temp.name).resolve() / 'repo'
        schemas = cls.template / 'datasets/schemas'
        schemas.mkdir(parents=True)
        for name in ('dataset_manifest.schema.json', 'run_manifest.schema.json'):
            shutil.copyfile(a.ROOT / 'datasets/schemas' / name, schemas / name)
        required = json.loads((schemas / 'dataset_manifest.schema.json').read_text())['required']
        manifests = cls.template / 'datasets/manifests'
        manifests.mkdir()
        for collection, (prefix, ext, fmt, storage, origin) in a.COLLECTIONS.items():
            base = cls.template / 'data_local' / collection
            clean = base / 'clean/images'
            clean.mkdir(parents=True)
            for folder in ('labels', 'glass_masks', 'runs'):
                (base / folder).mkdir()
            records = []
            for i in range(1, 101):
                image_id = f'{prefix}_{i:06d}'
                name = image_id + ext
                path = clean / name
                Image.new('RGB', (8+i, 10), (i, 7, 20)).save(path, format=fmt)
                row = dict.fromkeys(required)
                row.update(schema_version='1.0', image_id=image_id, collection_id=collection,
                           relative_path=f'clean/images/{name}', sha256=a.digest(path.read_bytes()),
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
        self.root = Path(temp.name).resolve() / 'repo'
        shutil.copytree(self.template, self.root)
        self.collection = 'synthetic_chatgpt'
        self.image_id = 'chatgpt_000001'
        self.base = self.root / 'data_local' / self.collection
        self.label = self.base / 'labels' / (self.image_id + '.txt')
        self.mask = self.base / 'glass_masks' / (self.image_id + '.png')
        self.catalog = self.root / a.CLASS_PATH
        self.manifest = self.root / 'datasets/manifests/synthetic_chatgpt.jsonl'
        self.record = json.loads(self.manifest.read_text().splitlines()[0])

    def put_json(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def make_label(self):
        self.put_json(self.catalog, {'schema':'bvt.research-classes.v1', 'classes':['fixture']})
        self.label.write_text('0 0.5 0.5 0.5 0.5\n', encoding='utf-8')

    def make_mask(self):
        im = Image.new('L', (9,10))
        im.putpixel((4,4), 255)
        im.save(self.mask)

    def approve(self, kind, path, decision='approved'):
        value = dict(schema='bvt.research-annotation-review.v1', kind=kind,
                     image_id=self.image_id, input_sha256=self.record['sha256'],
                     artifact_sha256=a.digest(path.read_bytes()),
                     class_catalog_sha256=a.digest(self.catalog.read_bytes()) if kind=='annotation' else None,
                     decision=decision, reviewer='fixture reviewer')
        self.put_json(path.with_suffix('.json'), value)
        return value

    def row(self):
        report = a.audit(self.root, self.collection)
        return report['records'][0], report['issues']

    def test_empty_both_collections_read_only(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts}
        report = a.audit(self.root)
        self.assertEqual(len(report['records']), 200)
        self.assertEqual(report['counts'], {'annotation':{'pending':200}, 'glass_mask':{'pending':200}})
        self.assertFalse(report['issues'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts})

    def test_valid_unreviewed_is_pending(self):
        self.make_label(); self.make_mask()
        row, issues = self.row()
        self.assertFalse(issues)
        self.assertEqual(row['annotation']['box_count'], 1)
        self.assertEqual(row['glass_mask']['active_pixels'], 1)
        for kind in a.KINDS:
            self.assertEqual(row[kind]['status'], 'pending')
            self.assertEqual(row[kind]['reason'], 'manual_review_required')

    def test_explicit_review_and_rejection(self):
        self.make_label(); self.make_mask()
        self.approve('annotation', self.label)
        self.approve('glass_mask', self.mask, 'rejected')
        row, issues = self.row()
        self.assertFalse(issues)
        self.assertEqual(row['annotation']['status'], 'verified')
        self.assertEqual(row['annotation']['manifest_status'], 'pending')
        self.assertEqual(row['glass_mask']['status'], 'rejected')

    def test_yolo_invalid_rows(self):
        for text in ('', '1 0.5 0.5 1 1', '-1 0.5 0.5 1 1', '0 0.1 0.5 0.5 0.5',
                     '0 NaN 0.5 0.5 0.5', '0 0.5 0.5 0 1', '0 0.5 0.5 1 1 0.2',
                     '0 0.5 0.5 1e999 1', '0 0.5 0.5 1 1e-999'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                a.label_count(text.encode(), ['fixture'])
        self.assertEqual(a.label_count(b'0 .5 .5 1 1\n', ['fixture']), 1)

    def test_catalog_required_and_class_names(self):
        self.label.write_text('0 .5 .5 1 1')
        row, issues = self.row()
        self.assertTrue(issues)
        self.assertEqual(row['annotation']['status'], 'invalid')
        self.put_json(self.catalog, {'schema':'bvt.research-classes.v1', 'classes':['A','a']})
        with self.assertRaisesRegex(ValueError, 'Duplicate class'):
            a.catalog(self.root)

    def test_bad_masks(self):
        for mode, size, color in [('L',(8,10),255), ('RGB',(9,10),(0,0,0)), ('L',(9,10),0),
                                  ('L',(9,10),255), ('L',(9,10),128)]:
            with self.subTest(mode=mode, size=size, color=color):
                Image.new(mode,size,color).save(self.mask)
                with self.assertRaises(ValueError):
                    a.mask_pixels(self.mask.read_bytes(), self.record)

    def test_artifact_tamper_and_wrong_source_review(self):
        self.make_label()
        evidence = self.approve('annotation', self.label)
        self.label.write_text('0 .5 .5 .3 .3')
        row, issues = self.row()
        self.assertTrue(issues)
        self.assertEqual(row['annotation']['status'], 'invalid')
        evidence = self.approve('annotation', self.label)
        evidence['input_sha256'] = '0'*64
        self.put_json(self.label.with_suffix('.json'), evidence)
        self.assertTrue(self.row()[1])

    def test_catalog_change_invalidates_review(self):
        self.make_label(); self.approve('annotation', self.label)
        self.put_json(self.catalog, {'schema':'bvt.research-classes.v1', 'classes':['renamed']})
        self.assertTrue(self.row()[1])

    def test_orphan_extra_and_stale_manifest(self):
        self.put_json(self.label.with_suffix('.json'), {})
        (self.base / 'labels/other.txt').touch()
        self.assertEqual(len(self.row()[1]), 2)
        self.label.with_suffix('.json').unlink()
        (self.base / 'labels/other.txt').unlink()
        rows = [json.loads(line) for line in self.manifest.read_text().splitlines()]
        rows[0]['annotation_status'] = 'verified'
        self.manifest.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        self.assertIn('Stale manifest', self.row()[1][0])

    def test_original_corruption_fails(self):
        (self.root / self.record['local_cache_path']).write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            self.row()

    def test_geometry_gate(self):
        self.make_label(); self.make_mask()
        self.approve('annotation', self.label); self.approve('glass_mask', self.mask)
        runs.initialize(self.root, self.collection, 'fixture-run', 'fixture', 42, {}, [self.image_id])
        folder = runs.run_path(self.root, self.collection, 'fixture-run')
        with self.assertRaisesRegex(ValueError, 'registered'):
            a.inheritance(self.root, self.collection, 'fixture-run')
        output = folder / 'augmented/images' / (self.image_id + '.png')
        Image.new('RGB',(9,10),(0,0,0)).save(output)
        runs.record_outputs(self.root, self.collection, 'fixture-run')
        with self.assertRaisesRegex(ValueError, "Expected regular"):
            a.inheritance(self.root, self.collection, 'fixture-run')
        item = dict(image_id=self.image_id, input_sha256=self.record['sha256'],
                    output_sha256=a.digest(output.read_bytes()), transform='unknown', reviewer='fixture reviewer')
        review_path = folder / 'reports/geometry_review.json'
        def check():
            self.put_json(review_path, dict(schema='bvt.research-geometry-review.v1', records=[item]))
            return a.inheritance(self.root, self.collection, 'fixture-run')['records'][0]
        self.assertIsNone(check()['label_path'])
        item['transform'] = 'changed'
        self.assertIsNone(check()['mask_path'])
        item['transform'] = 'identity_pixel_grid'
        row = check()
        self.assertEqual(row['label_sha256'], a.digest(self.label.read_bytes()))
        self.assertEqual(row['mask_sha256'], a.digest(self.mask.read_bytes()))
        self.label.with_suffix('.json').unlink()
        self.assertIsNone(check()['label_path'])
        item['output_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            check()

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            a.json_object(b'{"classes":[],"classes":[]}')


if __name__ == '__main__':
    unittest.main()
