"""Read-only research dataset integrity and readiness report (no network or rendering)."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

if __package__:
    from . import check_research_annotations as annotations
    from . import prepare_research_datasets as storage
    from . import build_dataset_manifests as manifests
else:
    import check_research_annotations as annotations
    import prepare_research_datasets as storage
    import build_dataset_manifests as manifests

ROOT = Path(__file__).resolve().parents[1]
LICENSE_URLS = dict(manifests.LICENSES.values())
RIGHTS = ('derivative_use_review_status', 'commercial_use_review_status',
          'redistribution_review_status', 'trademark_review_status')


def publication_metadata_ready(record):
    # A conservative metadata gate, not legal clearance or a publication command.
    return (record['license_verification_status'] == 'verified'
            and all(record[k] == 'approved' for k in RIGHTS)
            and LICENSE_URLS.get(record['license_id']) == record['license_url']
            and all(isinstance(record[k], str) and record[k].strip() for k in
                    ('author', 'license_id', 'license_url', 'license_checked_at',
                     'license_evidence_url', 'attribution_text')))


def validate(root):
    root = Path(root).resolve()
    issues, rows, summaries, manifest_hashes = [], [], {}, {}
    valid_records = {}
    declared_hashes, actual_hashes, split_groups = defaultdict(list), defaultdict(list), defaultdict(list)

    def issue(code, detail, collection=None, image_id=None):
        issues.append(dict(code=code, collection_id=collection, image_id=image_id, detail=str(detail)))

    def path(relative):
        return storage.safe_path(root, relative)

    try:
        schema = annotations.json_object(path(manifests.SCHEMA).read_bytes())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
    except Exception as exc:
        issue('schema_invalid', exc)
        validator = None
    try:
        names, class_sha = annotations.catalog(root)
    except Exception as exc:
        issue('class_catalog_invalid', exc)
        names, class_sha = None, None

    for rel in storage.directory_paths():
        try:
            if not path(rel).is_dir():
                issue('directory_missing', rel)
        except Exception as exc:
            issue('directory_invalid', exc)

    for collection, (prefix, ext, fmt, drive, origin) in storage.COLLECTIONS.items():
        ids = [f'{prefix}_{i:06d}' for i in range(1, 101)]
        expected_names = {key + ext for key in ids}
        expected_paths = {key: f'data_local/{collection}/clean/images/{key}{ext}' for key in ids}
        summary = dict(expected=100, present=0, missing=0, unique_sha256=0, bad_format=0,
                       unverified=0, ready_for_qa=0, ready_for_publication=0, manifest_records=0,
                       split_counts={}, license_counts={}, license_verification_counts={})
        summaries[collection] = summary
        records = {}
        seen = set()
        try:
            source = manifests.SYNTHETIC_DOC if origin == 'synthetic' else manifests.REGISTRY
            version = 'sha256:' + sha256(path(source).read_bytes()).hexdigest()
        except Exception as exc:
            issue('registry_missing_or_invalid', exc, collection)
            version = None
        try:
            data = path(f'datasets/manifests/{collection}.jsonl').read_bytes()
            manifest_hashes[collection] = sha256(data).hexdigest()
            lines = data.decode('utf-8').splitlines()
            summary['manifest_records'] = len(lines)
            if len(lines) != 100:
                issue('manifest_count', f'Expected 100 lines, got {len(lines)}', collection)
            for number, line in enumerate(lines, 1):
                key = None
                try:
                    r = annotations.json_object(line.encode('utf-8'))
                    if not isinstance(r, dict):
                        raise ValueError('Expected JSON object')
                    key = r.get('image_id')
                    if not isinstance(key, str) or key not in expected_paths:
                        raise ValueError('Unexpected image ID')
                    if key in seen:
                        raise ValueError('Duplicate image ID')
                    seen.add(key)
                    if validator is None:
                        raise ValueError('Schema unavailable')
                    validator.validate(r)
                    name = key + ext
                    expected = dict(collection_id=collection, origin_type=origin, file_format=fmt,
                                    relative_path=f'clean/images/{name}',
                                    local_cache_path=expected_paths[key],
                                    storage_relative_path=f'{drive}/images/{name}')
                    if any(r[k] != v for k, v in expected.items()):
                        raise ValueError('Manifest ID/path/format mismatch')
                    if key != f'{prefix}_{number:06d}':
                        raise ValueError('Manifest order/ID mismatch')
                    records[key] = r
                    valid_records[key] = r
                    if version is None or r['source_registry_version'] != version:
                        issue('registry_version_mismatch', 'Source registry SHA-256 mismatch', collection, key)
                    declared_hashes[r['sha256']].append(key)
                    if r['split'] is not None:
                        split_groups[r['source_group_id']].append((key, r['split']))
                    if origin == 'real':
                        try:
                            manifests.commons_title(r['source_page_url'])
                        except ValueError as exc:
                            issue('source_page_invalid', exc, collection, key)
                        if r['license_id'] is not None and (r['license_id'] not in LICENSE_URLS or
                                LICENSE_URLS[r['license_id']] != r['license_url']):
                            issue('license_metadata_mismatch', 'Unknown license or inconsistent canonical URL', collection, key)
                        if r['license_verification_status'] in ('api_evidence_recorded', 'verified') and not all(
                                r[k] for k in ('author', 'license_id', 'license_url', 'license_checked_at', 'license_evidence_url', 'attribution_text')):
                            issue('license_evidence_incomplete', 'Recorded evidence fields missing', collection, key)
                    if r['integrity_status'] != 'verified':
                        issue('integrity_status_unverified', r['integrity_status'], collection, key)
                except Exception as exc:
                    issue('manifest_record_invalid', f'Line {number}: {exc}', collection,
                          key if isinstance(key, str) else None)
        except Exception as exc:
            issue('manifest_unreadable', exc, collection)

        for folder, allowed in [('clean/images', expected_names)] + [
            (folder, {key + suffix for key in ids for suffix in (suffix1, '.json')})
            for folder, suffix1, _ in annotations.KINDS.values()
        ]:
            try:
                directory = path(f'data_local/{collection}/{folder}')
                if directory.is_dir():
                    for extra in sorted(p.name for p in directory.iterdir() if p.name not in allowed):
                        issue('unexpected_entry', f'{folder}/{extra}', collection)
            except Exception as exc:
                issue('inventory_invalid', exc, collection)

        hashes = set()
        for key in ids:
            r = records.get(key)
            row = dict(image_id=key, collection_id=collection, present=False,
                       actual_sha256=None, integrity_verified=False, bad_format=False,
                       annotation_status='not_checked', glass_mask_status='not_checked',
                       split=r['split'] if r else None,
                       source_group_id=r['source_group_id'] if r else None,
                       license_id=r['license_id'] if r else None,
                       license_verification_status=r['license_verification_status'] if r else None,
                       rights={k: r[k] for k in RIGHTS} if r else None,
                       ready_for_qa=False, ready_for_publication=False)
            rows.append(row)
            if r is None:
                issue('manifest_record_missing', 'No valid manifest record', collection, key)
            try:
                image = path(expected_paths[key])
                if not image.is_file():
                    issue('image_missing_or_not_file', expected_paths[key], collection, key)
                    continue
                row['present'] = True
                data = image.read_bytes()
                actual = sha256(data).hexdigest()
                row['actual_sha256'] = actual
                hashes.add(actual)
                actual_hashes[actual].append(key)
                hash_ok = r is not None and actual == r['sha256']
                if r is not None and not hash_ok:
                    issue('sha256_mismatch', expected_paths[key], collection, key)
                try:
                    with Image.open(BytesIO(data)) as im:
                        if im.format != fmt:
                            raise ValueError(f'Expected {fmt}, got {im.format}')
                        size = im.size
                        im.verify()
                    with Image.open(BytesIO(data)) as im:
                        im.load()
                except Exception as exc:
                    row['bad_format'] = True
                    issue('image_format_or_decode_invalid', exc, collection, key)
                    continue
                dimensions_ok = r is not None and size == (r['width'], r['height'])
                if r is not None and not dimensions_ok:
                    issue('dimensions_mismatch', f'Actual {size}', collection, key)
                row['integrity_verified'] = bool(hash_ok and dimensions_ok and r['integrity_status'] == 'verified')
            except Exception as exc:
                issue('image_unreadable', exc, collection, key)
                continue
            if not row['integrity_verified']:
                continue
            for kind in annotations.KINDS:
                try:
                    artifact = annotations.inspect_artifact(root, r, kind, names, class_sha)
                    row[kind + '_status'] = artifact['status']
                except Exception as exc:
                    row[kind + '_status'] = 'invalid'
                    issue('annotation_invalid', f'{kind}: {exc}', collection, key)
            row['ready_for_qa'] = (row['annotation_status'] == row['glass_mask_status'] == 'verified')
            row['ready_for_publication'] = publication_metadata_ready(r)
        summary['unique_sha256'] = len(hashes)

    for code, index in [('duplicate_declared_sha256', declared_hashes), ('duplicate_actual_sha256', actual_hashes)]:
        for digest, keys in index.items():
            if len(keys) > 1:
                issue(code, f'{digest}: {", ".join(keys)}')
    for group, items in split_groups.items():
        if len({split for _, split in items}) > 1:
            issue('split_leakage', f'{group}: {items}')
    # The same declared Commons page must not cross splits even if group IDs differ.
    pages = defaultdict(list)
    for key, r in valid_records.items():
        if r['origin_type'] == 'real' and r['split'] is not None:
            try:
                title = manifests.commons_title(r['source_page_url'])
            except ValueError:
                continue  # Already reported above.
            pages[title].append((key, r['split']))
    for page, items in pages.items():
        if len({split for _, split in items}) > 1:
            issue('source_page_split_leakage', f'{page}: {items}')

    # Fail closed globally: a broken dataset is not approved for downstream use.
    for row in rows:
        if issues:
            row['ready_for_qa'] = row['ready_for_publication'] = False
    for collection, summary in summaries.items():
        group = [r for r in rows if r['collection_id'] == collection]
        summary.update(present=sum(r['present'] for r in group),
                       missing=sum(not r['present'] for r in group),
                       bad_format=sum(r['bad_format'] for r in group),
                       unverified=sum(not r['integrity_verified'] for r in group),
                       ready_for_qa=sum(r['ready_for_qa'] for r in group),
                       ready_for_publication=sum(r['ready_for_publication'] for r in group),
                       split_counts=dict(Counter(r['split'] or 'unassigned' for r in group)),
                       annotation_counts=dict(Counter(r['annotation_status'] for r in group)),
                       glass_mask_counts=dict(Counter(r['glass_mask_status'] for r in group)),
                       license_counts=dict(Counter(r['license_id'] or 'unknown' for r in group)),
                       license_verification_counts=dict(Counter(r['license_verification_status'] or 'unknown' for r in group)))
    totals = {key: sum(s[key] for s in summaries.values()) for key in
              ('expected', 'present', 'missing', 'bad_format', 'unverified', 'ready_for_qa', 'ready_for_publication')}
    totals['unique_sha256'] = len(actual_hashes)
    return dict(schema='bvt.research-dataset-validation.v1', status='FAIL' if issues else 'PASS',
                manifest_sha256=manifest_hashes, class_catalog_sha256=class_sha,
                collections=summaries, totals=totals, issues=issues, records=rows,
                split_validation='assigned_groups_only', publication_gate='metadata_only')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Full JSON report on stdout (even on validation failure)')
    parser.add_argument('--require-ready', choices=('qa', 'publication'),
                        help='Require every image to meet the selected readiness gate')
    args = parser.parse_args(argv)
    report = validate(ROOT)
    required = args.require_ready
    report['required_readiness'] = required
    report['readiness_requirement_met'] = (required is None or
        report['totals']['ready_for_' + required] == report['totals']['expected'])
    if args.json:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    else:
        for collection, summary in report['collections'].items():
            print(f'COLLECTION={collection} ' + ' '.join(f'{k.upper()}={v}' for k,v in summary.items() if isinstance(v,int)))
            print('LICENSE_STATUS=' + json.dumps(summary['license_verification_counts'], sort_keys=True))
            print('SPLITS=' + json.dumps(summary['split_counts'], sort_keys=True))
        print('TOTALS=' + json.dumps(report['totals'], sort_keys=True))
        for item in report['issues']:
            print(json.dumps(item, ensure_ascii=True), file=sys.stderr)
        print('DATASET_VALIDATOR=' + report['status'])
        if required:
            print('READINESS_REQUIREMENT=' + ('PASS' if report['readiness_requirement_met'] else 'FAIL'))
    return 1 if report['status'] != 'PASS' or not report['readiness_requirement_met'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
