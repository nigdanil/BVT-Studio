"""Offline fixture tests for the restore workflow; no live data or Blender."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from hashlib import sha256

from PIL import Image
from scripts import prepare_research_datasets as p
from scripts import build_dataset_manifests as m


class PrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.template = Path(temp.name) / 'template'
        cls.cloud_template = Path(temp.name) / 'source'
        schema = cls.template / m.SCHEMA
        schema.parent.mkdir(parents=True)
        shutil.copyfile(m.ROOT / m.SCHEMA, schema)
        folder = cls.template / 'datasets/manifests'
        folder.mkdir()
        for collection, (prefix, ext, fmt, storage, origin) in p.COLLECTIONS.items():
            records = []
            images = cls.cloud_template / storage / 'images'
            images.mkdir(parents=True)
            for i in range(1, 101):
                name = f'{prefix}_{i:06d}{ext}'
                image_id = Path(name).stem
                path = images / name
                Image.new('RGB', (i+5, 9), (i, 12, 34)).save(path, format=fmt)
                r = dict.fromkeys(json.loads(schema.read_text())['required'])
                r.update(schema_version='1.0', image_id=image_id, collection_id=collection,
                         relative_path=f'clean/images/{name}', sha256=sha256(path.read_bytes()).hexdigest(),
                         width=i+5, height=9, file_format=fmt, origin_type=origin,
                         source_page_url=(f'https://commons.wikimedia.org/wiki/File:Fixture_{i}.jpg'
                                          if origin == 'real' else None),
                         source_group_id=image_id, storage_provider='google_drive',
                         storage_relative_path=f'{storage}/images/{name}',
                         local_cache_path=f'data_local/{collection}/clean/images/{name}',
                         integrity_status='verified', source_registry_version='sha256:'+'0'*64)
                for key in ('license_verification_status', 'derivative_use_review_status',
                            'commercial_use_review_status', 'redistribution_review_status',
                            'trademark_review_status', 'annotation_status', 'glass_mask_status'):
                    r[key] = 'pending'
                records.append(r)
            (folder / f'{collection}.jsonl').write_bytes(m.encode(records))

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root, self.cloud = base / 'repo', base / 'cloud'
        shutil.copytree(self.template, self.root)
        shutil.copytree(self.cloud_template, self.cloud)
        self.first = self.root / 'data_local/synthetic_chatgpt/clean/images/chatgpt_000001.png'
        self.original = self.cloud / '01_ChatGPT_Synthetic/images/chatgpt_000001.png'

    def test_clean_restore_and_offline_check(self):
        self.assertEqual(p.prepare(self.root, self.cloud), (0, 200))
        self.assertEqual(p.prepare(self.root, check=True), (200, 0))
        self.assertEqual(self.first.read_bytes(), self.original.read_bytes())
        self.assertTrue(all((self.root / d).is_dir() for d in p.directory_paths()))

    def test_resume_and_no_recopy(self):
        self.first.parent.mkdir(parents=True)
        shutil.copyfile(self.original, self.first)
        stamp = self.first.stat().st_mtime_ns
        self.assertEqual(p.prepare(self.root, self.cloud), (1, 199))
        self.assertEqual(self.first.stat().st_mtime_ns, stamp)
        self.assertEqual(p.prepare(self.root, self.cloud / 'absent'), (200, 0))

    def test_offline_check_missing_read_only(self):
        with self.assertRaisesRegex(ValueError, 'Missing cache'):
            p.prepare(self.root, check=True)
        self.assertFalse((self.root / 'data_local').exists())

    def test_corrupt_existing_is_not_overwritten(self):
        self.first.parent.mkdir(parents=True)
        self.first.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            p.prepare(self.root, self.cloud)
        self.assertEqual(self.first.read_bytes(), b'corrupt')
        self.assertEqual(len(list(self.first.parent.iterdir())), 1)

    def test_missing_source_no_partial_copy(self):
        self.original.unlink()
        with self.assertRaisesRegex(ValueError, 'Invalid source'):
            p.prepare(self.root, self.cloud)
        self.assertFalse((self.root / 'data_local').exists())

    def test_corrupt_source_no_partial_copy(self):
        self.original.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            p.prepare(self.root, self.cloud)
        self.assertFalse((self.root / 'data_local').exists())

    def test_extra_clean_file_rejected(self):
        self.first.parent.mkdir(parents=True)
        (self.first.parent / 'unexpected.png').touch()
        with self.assertRaisesRegex(ValueError, 'Unexpected clean entries'):
            p.prepare(self.root, self.cloud)

    def test_manifest_path_mismatch(self):
        path = self.root / 'datasets/manifests/synthetic_chatgpt.jsonl'
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[0]['local_cache_path'] = records[1]['local_cache_path']
        path.write_bytes(m.encode(records))
        with self.assertRaisesRegex(ValueError, 'Manifest path/ID mismatch'):
            p.prepare(self.root, self.cloud)
        self.assertFalse((self.root / 'data_local').exists())

    def test_wrong_dimensions_with_matching_hash(self):
        path = self.root / 'datasets/manifests/synthetic_chatgpt.jsonl'
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[0]['width'] += 1
        path.write_bytes(m.encode(records))
        with self.assertRaisesRegex(ValueError, 'Dimensions mismatch'):
            p.prepare(self.root, self.cloud)

    def test_wrong_format_with_matching_hash(self):
        Image.new('RGB', (6, 9)).save(self.original, format='JPEG')
        path = self.root / 'datasets/manifests/synthetic_chatgpt.jsonl'
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[0]['sha256'] = sha256(self.original.read_bytes()).hexdigest()
        path.write_bytes(m.encode(records))
        with self.assertRaisesRegex(ValueError, 'Format mismatch'):
            p.prepare(self.root, self.cloud)

    def test_missing_manifest_rejected(self):
        (self.root / 'datasets/manifests/real_wikimedia.jsonl').unlink()
        with self.assertRaises(FileNotFoundError):
            p.prepare(self.root, self.cloud)
        self.assertFalse((self.root / 'data_local').exists())

    def test_export_metadata_and_collision(self):
        self.assertEqual(p.export_metadata(self.root, self.cloud), (4, 0))
        self.assertEqual(p.export_metadata(self.root, self.cloud), (0, 4))
        target = self.cloud / '01_ChatGPT_Synthetic/manifest.jsonl'
        self.assertEqual(target.read_bytes(), (self.root / 'datasets/manifests/synthetic_chatgpt.jsonl').read_bytes())
        sums = (target.parent / 'SHA256SUMS.txt').read_text().splitlines()
        self.assertEqual(len(sums), 100)
        self.assertEqual(sums[0], sha256(self.original.read_bytes()).hexdigest()+'  images/chatgpt_000001.png')
        target.write_bytes(b'old')
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            p.export_metadata(self.root, self.cloud)
        self.assertEqual(target.read_bytes(), b'old')

    def test_source_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, 'must not overlap'):
            p.prepare(self.root, self.root)


if __name__ == '__main__':
    unittest.main()
