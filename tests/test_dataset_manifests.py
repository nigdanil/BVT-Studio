"""Independent fixtures; no research collection, network or Blender required."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openpyxl import Workbook, load_workbook
from PIL import Image

from scripts import build_dataset_manifests as m


def workbook():
    wb = Workbook()
    r = wb.active
    r.title = 'Реестр'
    a = wb.create_sheet('Аудит BVT')
    d = wb.create_sheet('Новые 6 — источники')
    r.append(m.REGISTRY_HEADERS)
    a.append(m.AUDIT_HEADERS)
    d.append(m.DETAIL_HEADERS)
    for i in reversed(range(1, 101)):
        title = f'Photo {i}.jpg'
        url = f'https://commons.wikimedia.org/wiki/File:Photo_{i}.jpg'
        reviewed = i in {12, 80, 81, 82, 90, 95, 96, 97, 98, 99, 100}
        author = 'Fixture author' if reviewed else None
        status = 'Страница и лицензия проверены 24.11.2026' if i >= 95 else 'Подтверждена'
        review = ('Проверена индивидуально 24.11.2026' if i >= 95 else
                  'Подтверждена по странице' if reviewed else 'Не проверено индивидуально')
        key = 'CC BY 4.0' if i == 99 else 'CC BY-SA 4.0'
        license_url = m.LICENSES[key][1]
        r.append([i, 'Wikimedia Commons', 'File:' + title, 'License text', status, url])
        a.append([i, 'File:' + title, key, 'Wikimedia Commons', url, 'Да', 'Да', 'Да',
                  'Attribution', review, author, 'Risks', status, license_url, 'License text', 'Review'])
        if i >= 95:
            d.append([i, 'Display', 'Scene', 'Front', 'Cartons, bottles', 'Glass', title,
                      author, key, 'Да', '6000 × 4000', url, license_url, 'Review'])
    data = BytesIO()
    wb.save(data)
    wb.close()
    return data.getvalue()


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        base = Path(cls.temp.name)
        cls.root, cls.cloud = base / 'repo', base / 'copy'
        for rel in (m.DOCS, m.SCHEMA.parent, Path('datasets/manifests')):
            (cls.root / rel).mkdir(parents=True, exist_ok=True)
        (cls.root / m.REGISTRY).write_bytes(workbook())
        (cls.root / m.SYNTHETIC_DOC).write_text('Fixture provenance', encoding='utf-8')
        shutil.copyfile(m.ROOT / m.SCHEMA, cls.root / m.SCHEMA)
        for c, (prefix, ext, fmt, storage, _) in m.COLLECTIONS.items():
            folder = cls.root / 'data_local' / c / 'clean/images'
            cloud = cls.cloud / storage / 'images'
            folder.mkdir(parents=True)
            cloud.mkdir(parents=True)
            for i in range(1, 101):
                path = folder / f'{prefix}_{i:06d}{ext}'
                # Distinct dimensions guarantee distinct bytes even with JPEG quantization.
                Image.new('RGB', (i + 8, 12), (i, 50, 180)).save(path, format=fmt)
                shutil.copyfile(path, cloud / path.name)
        cls.records = m.build(cls.root, cls.cloud)
        schema = json.loads((cls.root / m.SCHEMA).read_text())
        cls.validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def test_schema_and_unique_ids(self):
        records = [r for group in self.records.values() for r in group]
        self.assertEqual(len(records), 200)
        self.assertEqual(len({r['image_id'] for r in records}), 200)
        self.assertEqual(len({r['sha256'] for r in records}), 200)
        for r in records:
            self.assertEqual(len(r), 36)
            self.validator.validate(r)
            self.assertEqual(r['image_id'], r['source_group_id'])
            self.assertIsNone(r['split'])
            self.assertEqual(r['annotation_status'], 'pending')
            self.assertEqual(r['glass_mask_status'], 'pending')
            self.assertEqual(r['redistribution_review_status'], 'pending')

    def test_registry_join_by_id_and_metadata(self):
        r = self.records['real_wikimedia'][98]
        self.assertEqual(r['image_id'], 'wikimedia_000099')
        self.assertEqual(r['original_filename'], 'Photo 99.jpg')
        self.assertEqual(r['license_id'], 'CC-BY-4.0')
        self.assertEqual(r['license_checked_at'], '2026-11-24')
        self.assertEqual((r['width'], r['height']), (107, 12))
        self.assertEqual(r['license_verification_status'], 'registry_page_reviewed')
        self.assertEqual(r['packaging_types'], ['Cartons', 'bottles'])
        self.assertEqual(r['derivative_use_review_status'], 'pending')
        self.assertIsNone(r['source_url'])
        self.assertIsNone(r['license_evidence_url'])

    def test_unknown_metadata(self):
        s = self.records['synthetic_chatgpt'][0]
        r = self.records['real_wikimedia'][0]
        for key in ('author', 'source_page_url', 'license_id', 'original_filename'):
            self.assertIsNone(s[key])
        self.assertIsNone(r['author'])
        self.assertIsNone(r['scene_type'])
        self.assertEqual(r['license_verification_status'], 'pending')
        self.assertEqual(r['license_id'], 'CC-BY-SA-4.0')
        self.assertEqual(sum(x['license_verification_status'] == 'registry_page_reviewed'
                             for x in self.records['real_wikimedia']), 11)

    def test_invalid_schema_paths(self):
        for field, value in [('relative_path', '../outside.png'), ('local_cache_path', 'D:/private.png'),
                             ('storage_relative_path', '/secret.png'), ('file_format', 'JPEG'),
                             ('width', 0), ('sha256', 'wrong'), ('collection_id', 'unknown')]:
            r = dict(self.records['synthetic_chatgpt'][0], **{field: value})
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate(r)

    def test_registry_duplicate_and_cross_sheet_mismatch(self):
        for column, value in [('A', 99), ('E', 'https://commons.wikimedia.org/wiki/File:Other.jpg')]:
            wb = load_workbook(BytesIO(workbook()))
            wb['Аудит BVT'][column + '2'] = value
            stream = BytesIO()
            wb.save(stream)
            wb.close()
            with self.subTest(column=column), self.assertRaises(ValueError):
                m.read_registry(stream.getvalue())

    def test_missing_image_rejected(self):
        path = self.root / 'data_local/synthetic_chatgpt/clean/images/chatgpt_000001.png'
        original = path.read_bytes()
        path.unlink()
        try:
            with self.assertRaisesRegex(ValueError, 'missing image'):
                m.build(self.root, self.cloud)
        finally:
            path.write_bytes(original)

    def test_source_copy_mismatch_rejected(self):
        path = self.cloud / '01_ChatGPT_Synthetic/images/chatgpt_000001.png'
        original = path.read_bytes()
        try:
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
                m.build(self.root, self.cloud)
        finally:
            path.write_bytes(original)

    def test_duplicate_sha_rejected(self):
        local = self.root / 'data_local/synthetic_chatgpt/clean/images'
        cloud = self.cloud / '01_ChatGPT_Synthetic/images'
        targets = [d / 'chatgpt_000002.png' for d in (local, cloud)]
        original = [p.read_bytes() for p in targets]
        try:
            for p in targets:
                p.write_bytes((local / 'chatgpt_000001.png').read_bytes())
            with self.assertRaisesRegex(ValueError, 'Duplicate SHA'):
                m.build(self.root, self.cloud)
        finally:
            for p, data in zip(targets, original):
                p.write_bytes(data)

    def test_deterministic_and_no_overwrite(self):
        before = {p: m.digest(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()
                  and 'manifests' not in p.parts}
        rebuilt = m.build(self.root, self.cloud)
        self.assertEqual(rebuilt, self.records)
        m.publish(self.root, rebuilt)
        m.publish(self.root, rebuilt, check=True)
        m.publish(self.root, rebuilt)
        self.assertEqual(before, {p: m.digest(p.read_bytes()) for p in before})
        changed = deepcopy(rebuilt)
        changed['real_wikimedia'][0]['split'] = 'train'
        path = self.root / 'datasets/manifests/real_wikimedia.jsonl'
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            m.publish(self.root, changed)
        self.assertEqual(path.read_bytes(), original)

    def test_wrong_format_rejected(self):
        local = self.root / 'data_local/synthetic_chatgpt/clean/images/chatgpt_000001.png'
        cloud = self.cloud / '01_ChatGPT_Synthetic/images/chatgpt_000001.png'
        original = local.read_bytes()
        try:
            Image.new('RGB', (12, 12)).save(local, format='JPEG')
            shutil.copyfile(local, cloud)
            with self.assertRaisesRegex(ValueError, 'Invalid format'):
                m.build(self.root, self.cloud)
        finally:
            local.write_bytes(original)
            cloud.write_bytes(original)

    def test_unknown_license_rejected(self):
        wb = load_workbook(BytesIO(workbook()))
        wb['Аудит BVT']['C2'] = 'Unknown license'
        stream = BytesIO()
        wb.save(stream)
        wb.close()
        with self.assertRaisesRegex(ValueError, 'Unknown recorded license'):
            m.read_registry(stream.getvalue())

    def test_missing_output_check_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'datasets/manifests').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'absent or different'):
                m.publish(root, self.records, check=True)
            self.assertEqual(list((root / 'datasets/manifests').iterdir()), [])

    def test_review_status_not_promoted(self):
        self.assertEqual(m.review_status('Не проверено индивидуально', None), ('pending', None))
        self.assertEqual(m.review_status('Подтверждена по странице', 'Author'),
                         ('registry_page_reviewed', None))
        with self.assertRaises(ValueError):
            m.review_status('Проверена индивидуально 24.11.2026', None)


if __name__ == '__main__':
    unittest.main()
