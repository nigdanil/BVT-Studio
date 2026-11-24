"""Build the initial research JSONL inventory from local files and the registry.

No downloads, image mutations, annotations, split assignments or rights clearance.
"""
import argparse
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from openpyxl import load_workbook
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DOCS = Path('docs/datasets')
REGISTRY = DOCS / 'BVT_Studio_Registry_100_Verified.xlsx'
SYNTHETIC_DOC = DOCS / 'CHATGPT_GENERATED_IMAGES.md'
SCHEMA = Path('datasets/schemas/dataset_manifest.schema.json')
COLLECTIONS = {
    'synthetic_chatgpt': ('chatgpt', '.png', 'PNG', '01_ChatGPT_Synthetic', 'synthetic'),
    'real_wikimedia': ('wikimedia', '.jpg', 'JPEG', '02_Wikimedia_Commons', 'real'),
}
REGISTRY_HEADERS = ('№', 'Площадка', 'Уникальная ссылка', 'Лицензия', 'Статус', 'URL')
AUDIT_HEADERS = ('№', 'Наименование файла (как в реестре)', 'Лицензия', 'Площадка',
                 'Ссылка на фото', 'Наложение артефактов', 'Коммерческое использование',
                 'Публикация модификации', 'Атрибуция', 'Веб-проверка страницы',
                 'Автор (проверенный)', 'Особые условия / риски', 'Статус в исходном реестре',
                 'Ссылка на лицензию', 'Текст исходной лицензии', 'Следующее действие')
DETAIL_HEADERS = ('№', 'Тип витрины / оборудования', 'Описание сцены', 'Ракурс',
                  'Виды упаковки', 'Стекло / зоны эффектов', 'Имя файла Commons',
                  'Автор', 'Лицензия', 'Разрешение на артефакты', 'Размер',
                  'Источник (страница файла)', 'Текст лицензии (URL)', 'Ограничения / назначение')
API_SHEET = 'Commons API 2026-11-24'
API_AUDIT_HEADERS = AUDIT_HEADERS[:9] + ('Историческая веб-проверка', 'Автор по данным API') + AUDIT_HEADERS[11:]
API_HEADERS = ('№', 'Source page', 'API author', 'License ID', 'License URL',
               'Checked UTC', 'Page revision', 'Thumbnail URL', 'Thumbnail SHA256',
               'Evidence SHA256', 'Review status', 'Previous author', 'Previous license',
               'Previous license text', 'Previous review status', 'Credit', 'Attribution',
               'Restrictions', 'Audit SHA256', 'Review SHA256')
LICENSES = {
    'CC0 1.0': ('CC0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/'),
    'CC BY 2.0': ('CC-BY-2.0', 'https://creativecommons.org/licenses/by/2.0/'),
    'CC BY 4.0': ('CC-BY-4.0', 'https://creativecommons.org/licenses/by/4.0/'),
    'CC BY-SA 2.5': ('CC-BY-SA-2.5', 'https://creativecommons.org/licenses/by-sa/2.5/'),
    'CC BY-SA 3.0': ('CC-BY-SA-3.0', 'https://creativecommons.org/licenses/by-sa/3.0/'),
    'CC BY-SA 4.0': ('CC-BY-SA-4.0', 'https://creativecommons.org/licenses/by-sa/4.0/'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    if value is None:
        return None
    require(isinstance(value, str), f'Expected text, got {type(value).__name__}')
    return value.strip() or None


def digest(data):
    return sha256(data).hexdigest()


def sheet_rows(wb, name, headers, ids):
    rows = iter(wb[name].iter_rows(values_only=True))
    require(tuple(next(rows, ())) == headers, f'Unexpected headers: {name}')
    result = {}
    for row in rows:
        if all(value is None for value in row):
            continue
        require(len(row) == len(headers), f'Unexpected row width: {name}')
        i = row[0]
        require(type(i) is int and i in ids and i not in result,
                f'Invalid or duplicate ID: {name}: {i}')
        result[i] = row
    require(set(result) == set(ids), f'Missing IDs: {name}')
    return result


def commons_title(url):
    parsed = urlsplit(url or '')
    path = unquote(parsed.path)
    require(parsed.scheme == 'https' and parsed.netloc == 'commons.wikimedia.org'
            and path.startswith('/wiki/File:') and not parsed.query and not parsed.fragment,
            f'Invalid Commons file page: {url}')
    name = path[len('/wiki/File:'):].replace('_', ' ')
    require(name and '/' not in name and '\\' not in name and '\x00' not in name,
            f'Invalid Commons title: {url}')
    return name


def review_status(value, author):
    raw = text(value)
    require(raw is not None, 'Missing registry review status')
    normalized = raw.casefold()
    if normalized.startswith('не провер'):
        return 'pending', None
    require(normalized.startswith(('проверен', 'подтвержд'))
            and not any(word in normalized for word in ('не провер', 'не подтверж', 'частич', 'требует'))
            and author, f'Unrecognized review status: {raw}')
    dates = re.findall(r'\b\d{2}\.\d{2}\.\d{4}\b', raw)
    require(len(dates) <= 1, f'Ambiguous review date: {raw}')
    date = datetime.strptime(dates[0], '%d.%m.%Y').date().isoformat() if dates else None
    return 'registry_page_reviewed', date


def read_registry(data):
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        base = sheet_rows(wb, 'Реестр', REGISTRY_HEADERS, range(1, 101))
        api = sheet_rows(wb, API_SHEET, API_HEADERS, range(1, 101)) if API_SHEET in wb.sheetnames else {}
        audit = sheet_rows(wb, 'Аудит BVT', API_AUDIT_HEADERS if api else AUDIT_HEADERS, range(1, 101))
        details = sheet_rows(wb, 'Новые 6 — источники', DETAIL_HEADERS, range(95, 101))
    finally:
        wb.close()
    result = {}
    titles = set()
    for i in range(1, 101):
        r, a = base[i], audit[i]
        url = text(r[5])
        require(url == text(a[4]), f'Cross-sheet URL mismatch: {i}')
        require(text(r[1]) == text(a[3]) == 'Wikimedia Commons', f'Platform mismatch: {i}')
        require(text(r[2]) == text(a[1]), f'Cross-sheet title mismatch: {i}')
        require(text(r[4]) == text(a[12]), f'Cross-sheet status mismatch: {i}')
        name = commons_title(url)
        require(name not in titles, f'Duplicate Commons title: {i}')
        titles.add(name)
        license_key = text(a[2])
        require(license_key in LICENSES, f'Unknown recorded license: {i}: {license_key}')
        license_id, license_url = LICENSES[license_key]
        require(text(a[13]) == license_url, f'License URL mismatch: {i}')
        author = text(a[10])
        status, date = review_status(a[9], author)
        d = details.get(i)
        if d:
            require((text(d[11]), text(d[7]), text(d[8]), text(d[12])) ==
                    (url, author, license_key, license_url), f'Detail sheet mismatch: {i}')
            require(text(d[6]).replace('_', ' ') == name, f'Detail title mismatch: {i}')
        result[i] = dict(
            original_filename=name, source_page_url=url, author=author,
            license_id=license_id, license_url=license_url,
            license_verification_status=status, license_checked_at=date,
            # Registry page reference, not an independently archived evidence snapshot.
            license_evidence_url=None,
            attribution_text=(f'{name} — {author}; {url}; {license_id} ({license_url}).'
                              if status == 'registry_page_reviewed' else None),
            scene_type=text(d[1]) if d else None,
            viewpoint=text(d[3]) if d else None,
            packaging_types=([part.strip() for part in text(d[4]).split(',') if part.strip()]
                             if d and text(d[4]) else None),
        )
        if api:
            e = api[i]
            require((e[1], e[2], e[3], e[4]) == (url, author, license_id, license_url),
                    f'API sheet metadata mismatch: {i}')
            require(e[10] in ('api_evidence_recorded', 'manual_review_required') and author,
                    f'Invalid API evidence status: {i}')
            require(type(e[6]) is int and e[6] > 0, f'Invalid revision: {i}')
            require(all(isinstance(e[k], str) and re.fullmatch(r'[0-9a-f]{64}', e[k])
                        for k in (8, 9, 18, 19)), f'Invalid evidence hash: {i}')
            u = urlsplit(e[7])
            require(u.scheme == 'https' and u.netloc in ('upload.wikimedia.org', 'thumb.wikimedia.org')
                    and not u.fragment, f'Invalid thumbnail URL: {i}')
            checked = datetime.fromisoformat(e[5])
            require(checked.utcoffset() is not None, f'Missing timezone: {i}')
            revision = f'https://commons.wikimedia.org/w/index.php?oldid={e[6]}'
            credit = f'; credit: {e[15]}' if e[15] else ''
            attribution = f'; requested attribution: {e[16]}' if e[16] else ''
            result[i].update(source_url=e[7], license_verification_status=e[10],
                             license_checked_at=checked.date().isoformat(), license_evidence_url=revision,
                             attribution_text=f'{name} — {author}; {url}; {license_id} ({license_url}){credit}{attribution}. Local Wikimedia thumbnail; further modifications must be disclosed.')
            # Internal only: bind the registry evidence to the exact local image below.
            result[i]['_evidence_sha256'] = e[8]
    return result


def inventory(folder, expected):
    require(folder.is_dir(), f'Missing directory: {folder}')
    entries = list(folder.iterdir())
    require({p.name for p in entries} == expected and
            all(p.is_file() and not p.is_symlink() for p in entries),
            f'Unexpected or missing image files: {folder}')


def image_metadata(path, copy, fmt):
    require(not path.samefile(copy), f'Source copy is the same file: {path}')
    data = path.read_bytes()
    h = digest(data)
    require(h == digest(copy.read_bytes()), f'Source-copy SHA mismatch: {path.name}')
    with Image.open(BytesIO(data)) as im:
        require(im.format == fmt, f'Invalid format: {path.name}')
        width, height = im.size
        require(width > 0 and height > 0, f'Invalid dimensions: {path.name}')
        im.verify()
    with Image.open(BytesIO(data)) as im:
        im.load()
    return h, width, height


def safe_dir(root, relative):
    path = root / relative
    require(path.resolve() == path.absolute(), f'Redirected path: {path}')
    return path


def build(root, source_copy, *, registry_data=None, synthetic_data=None):
    root, source_copy = Path(root).resolve(), Path(source_copy).resolve()
    require(not source_copy.is_relative_to(root), 'Source copy must be outside repository')
    registry_bytes = (root / REGISTRY).read_bytes() if registry_data is None else registry_data
    synthetic_bytes = (root / SYNTHETIC_DOC).read_bytes() if synthetic_data is None else synthetic_data
    metadata = read_registry(registry_bytes)
    schema = json.loads((root / SCHEMA).read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output, seen = {}, set()
    for collection, (prefix, ext, fmt, storage, origin) in COLLECTIONS.items():
        expected = {f'{prefix}_{i:06d}{ext}' for i in range(1, 101)}
        folder = safe_dir(root, f'data_local/{collection}/clean/images')
        cloud = safe_dir(source_copy, f'{storage}/images')
        inventory(folder, expected)
        inventory(cloud, expected)
        records = []
        for i in range(1, 101):
            name = f'{prefix}_{i:06d}{ext}'
            image_id = Path(name).stem
            h, width, height = image_metadata(folder / name, cloud / name, fmt)
            require(h not in seen, f'Duplicate SHA-256: {name}')
            seen.add(h)
            record = dict(
                schema_version='1.0', image_id=image_id, collection_id=collection,
                relative_path=f'clean/images/{name}', original_filename=None,
                sha256=h, width=width, height=height, file_format=fmt, origin_type=origin,
                source_page_url=None, source_url=None, author=None, copyright_notice=None,
                license_id=None, license_url=None, license_verification_status='pending',
                license_checked_at=None, license_evidence_url=None, attribution_text=None,
                derivative_use_review_status='pending', commercial_use_review_status='pending',
                redistribution_review_status='pending', trademark_review_status='pending',
                scene_type=None, viewpoint=None, packaging_types=None,
                annotation_status='pending', glass_mask_status='pending', split=None,
                source_group_id=image_id, storage_provider='google_drive',
                storage_relative_path=f'{storage}/images/{name}',
                local_cache_path=f'data_local/{collection}/clean/images/{name}',
                integrity_status='verified',
                source_registry_version='sha256:' + digest(synthetic_bytes if origin == 'synthetic' else registry_bytes),
            )
            if origin == 'real':
                meta = dict(metadata[i])
                evidence_hash = meta.pop('_evidence_sha256', None)
                require(evidence_hash is None or evidence_hash == h, f'API evidence/image SHA mismatch: {image_id}')
                record.update(meta)
            else:
                record['attribution_text'] = ('Generated using ChatGPT (OpenAI) under the '
                                              'direction of the BVT-Studio author')
            validator.validate(record)
            records.append(record)
        output[collection] = records
    require(len(seen) == 200, 'Unexpected total image count')
    return output


def encode(records):
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True, allow_nan=False,
                              separators=(',', ':')) + '\n' for r in records).encode('utf-8')


def publish(root, collections, check=False):
    folder = safe_dir(Path(root).resolve(), 'datasets/manifests')
    require(folder.is_dir(), f'Missing output directory: {folder}')
    outputs = {folder / f'{name}.jsonl': encode(records) for name, records in collections.items()}
    for path, data in outputs.items():
        require(not path.is_symlink(), f'Symlink output: {path}')
        if path.exists() or check:
            require(path.is_file() and path.read_bytes() == data,
                    f'Manifest absent or different; refusing overwrite: {path}')
    created = []
    try:
        if not check:
            for path, data in outputs.items():
                if not path.exists():
                    with path.open('xb') as stream:
                        created.append(path)
                        stream.write(data)
                    require(path.read_bytes() == data, f'Write verification failed: {path}')
        for path, data in outputs.items():
            require(path.read_bytes() == data, f'Output mismatch: {path}')
    except Exception:
        for path in created:
            path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-copy', required=True, type=Path,
                        help='Previously downloaded authorized dataset root, outside the repository')
    parser.add_argument('--check', action='store_true', help='Verify existing JSONL, never write')
    args = parser.parse_args()
    try:
        collections = build(ROOT, args.source_copy)
        publish(ROOT, collections, args.check)
    except Exception as exc:
        parser.exit(1, f'DATASET_MANIFEST=FAIL: {exc}\n')
    for name, records in collections.items():
        print(f'COLLECTION={name} RECORDS={len(records)} SHA256={digest(encode(records))}')
    print('DATASET_MANIFEST=PASS')


if __name__ == '__main__':
    main()
