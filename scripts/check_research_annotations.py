"""Read-only validation of research YOLO Detect labels, glass masks and inheritance."""
import argparse
from collections import Counter
from math import isfinite
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys

from jsonschema import ValidationError
from PIL import Image

if __package__:
    from . import manage_research_runs as runs
    from .prepare_research_datasets import COLLECTIONS, read_manifests, safe_path, verified_bytes, require
else:
    import manage_research_runs as runs
    from prepare_research_datasets import COLLECTIONS, read_manifests, safe_path, verified_bytes, require

ROOT = Path(__file__).resolve().parents[1]
CLASS_PATH = 'data_local/classes.json'
KINDS = {'annotation': ('labels', '.txt', 'annotation_status'),
         'glass_mask': ('glass_masks', '.png', 'glass_mask_status')}
ERRORS = (OSError, ValueError, SyntaxError, ValidationError)


def digest(data):
    return sha256(data).hexdigest()


def json_object(data):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, f'Duplicate JSON key: {key}')
            obj[key] = value
        return obj
    def reject(value):
        raise ValueError(f'Nonfinite JSON: {value}')
    return json.loads(data.decode('utf-8'), object_pairs_hook=unique, parse_constant=reject)


def file_bytes(path):
    require(path.is_file() and path.stat().st_nlink == 1, f'Expected regular non-hardlinked file: {path}')
    return path.read_bytes()


def catalog(root):
    path = safe_path(root, CLASS_PATH)
    if not path.exists():
        return None, None
    data = file_bytes(path)
    value = json_object(data)
    require(isinstance(value, dict) and set(value) == {'schema', 'classes'} and
            value['schema'] == 'bvt.research-classes.v1', 'Invalid class catalog')
    names = value['classes']
    require(isinstance(names, list) and bool(names) and
            all(isinstance(n, str) and bool(n.strip()) and n == n.strip() for n in names),
            'Classes must be a nonempty list of names')
    require(len({n.casefold() for n in names}) == len(names), 'Duplicate class names')
    return names, digest(data)


def label_count(data, classes):
    require(classes is not None, 'Class catalog required for YOLO labels')
    count = 0
    for i, line in enumerate(data.decode('utf-8').splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        require(len(parts) == 5 and re.fullmatch(r'[0-9]+', parts[0]), f'Invalid YOLO Detect row {i}')
        require(int(parts[0]) < len(classes), f'Unknown class ID at row {i}')
        require(all(re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', x)
                    for x in parts[1:]), f'Invalid coordinate at row {i}')
        # Bounded floats avoid pathological Decimal exponents; strict bounds, no clipping.
        cx, cy, w, h = map(float, parts[1:])
        require(all(map(isfinite, (cx, cy, w, h))) and 0 < w <= 1 and 0 < h <= 1 and
                w/2 <= cx <= 1-w/2 and h/2 <= cy <= 1-h/2,
                f'Box outside image or invalid size at row {i}')
        count += 1
    require(count > 0, 'Empty YOLO labels unsupported by current Real Dataset QA')
    return count


def mask_pixels(data, record):
    with Image.open(BytesIO(data)) as im:
        require(im.format == 'PNG' and im.mode == 'L' and im.size == (record['width'], record['height']),
                'Mask must be 8-bit grayscale PNG matching source dimensions')
        im.verify()
    with Image.open(BytesIO(data)) as im:
        im.load()
        histogram = im.histogram()
    require(sum(histogram[1:255]) == 0, 'Mask must be binary (0 or 255)')
    require(histogram[255] > 0, 'Mask has no active pixels')
    require(histogram[0] > 0, 'Full-frame mask unsupported; individual glass region required')
    return histogram[255]


def review(data, record, kind, artifact_sha, class_sha):
    value = json_object(data)
    expected = dict(schema='bvt.research-annotation-review.v1', kind=kind,
                    image_id=record['image_id'], input_sha256=record['sha256'],
                    artifact_sha256=artifact_sha, class_catalog_sha256=class_sha)
    require(isinstance(value, dict) and set(value) == set(expected) | {'decision', 'reviewer'},
            'Invalid review fields')
    require(all(value[k] == v for k, v in expected.items()), 'Review identity/hash mismatch')
    require(value['decision'] in ('approved', 'rejected') and isinstance(value['reviewer'], str)
            and bool(value['reviewer'].strip()), 'Explicit review decision and reviewer required')
    return value['decision']


def inspect_artifact(root, record, kind, names, class_sha):
    folder, ext, manifest_field = KINDS[kind]
    base = f'data_local/{record["collection_id"]}/{folder}/{record["image_id"]}'
    path, sidecar = safe_path(root, base + ext), safe_path(root, base + '.json')
    result = dict(status='pending', reason='missing', artifact_path=None, artifact_sha256=None,
                  review_sha256=None, manifest_status=record[manifest_field])
    if not path.exists():
        require(not sidecar.exists(), 'Review without artifact')
    else:
        data = file_bytes(path)
        result.update(artifact_path=base + ext, artifact_sha256=digest(data))
        if kind == 'annotation':
            result['box_count'] = label_count(data, names)
        else:
            result['active_pixels'] = mask_pixels(data, record)
        result['reason'] = 'manual_review_required'
        if sidecar.exists():
            evidence = file_bytes(sidecar)
            decision = review(evidence, record, kind, result['artifact_sha256'],
                              class_sha if kind == 'annotation' else None)
            result.update(status='verified' if decision == 'approved' else 'rejected',
                          reason='review_declared_' + decision, review_sha256=digest(evidence))
    require(record[manifest_field] not in ('verified', 'rejected') or
            record[manifest_field] == result['status'], f'Stale manifest {manifest_field}')
    return result


def audit(root, collection=None):
    root = Path(root).resolve()
    groups = read_manifests(root)
    require(collection is None or collection in COLLECTIONS, 'Unknown collection')
    names, class_sha = catalog(root)
    rows, issues = [], []
    for c, (records, _) in groups.items():
        if collection is not None and c != collection:
            continue
        for folder, ext, _ in KINDS.values():
            path = safe_path(root, f'data_local/{c}/{folder}')
            require(path.is_dir(), f'Missing directory: {path}')
            allowed = {r['image_id'] + suffix for r in records for suffix in (ext, '.json')}
            extras = sorted(p.name for p in path.iterdir() if p.name not in allowed)
            issues.extend(f'Unexpected annotation entry: {c}/{folder}/{x}' for x in extras)
        for r in records:
            verified_bytes(safe_path(root, r['local_cache_path']), r)
            row = dict(collection_id=c, image_id=r['image_id'], input_sha256=r['sha256'])
            for kind in KINDS:
                try:
                    row[kind] = inspect_artifact(root, r, kind, names, class_sha)
                except ERRORS as exc:
                    row[kind] = dict(status='invalid', reason=str(exc), artifact_path=None,
                                     artifact_sha256=None, review_sha256=None,
                                     manifest_status=r[KINDS[kind][2]])
                    issues.append(f'{r["image_id"]}/{kind}: {exc}')
            rows.append(row)
    return dict(schema='bvt.research-annotation-audit.v1', class_catalog_sha256=class_sha,
                records=rows, issues=issues,
                counts={kind: dict(Counter(r[kind]['status'] for r in rows)) for kind in KINDS})


def inheritance(root, collection, run_id):
    """A declaration is human evidence, not an image-registration algorithm."""
    root = Path(root).resolve()
    run = runs.check(root, collection, run_id)
    require(run['status'] == 'outputs_recorded', 'Run outputs must be registered')
    report = audit(root, collection)
    require(not report['issues'], 'Annotation audit contains errors')
    by_id = {r['image_id']: r for r in report['records']}
    folder = runs.run_path(root, collection, run_id)
    data = file_bytes(safe_path(folder, 'reports/geometry_review.json'))
    evidence = json_object(data)
    require(isinstance(evidence, dict) and set(evidence) == {'schema', 'records'} and
            evidence['schema'] == 'bvt.research-geometry-review.v1' and isinstance(evidence['records'], list),
            'Invalid geometry review')
    pairs = {r['image_id']: r for r in run['records']}
    seen, result = set(), []
    for item in evidence['records']:
        require(isinstance(item, dict) and set(item) == {'image_id', 'input_sha256', 'output_sha256', 'transform', 'reviewer'},
                'Invalid geometry record fields')
        key = item['image_id']
        require(isinstance(key, str) and key in pairs and key not in seen, 'Unknown/duplicate geometry ID')
        seen.add(key)
        pair = pairs[key]
        require(item['input_sha256'] == pair['input_sha256'] and item['output_sha256'] == pair['output_sha256'],
                'Geometry review hash mismatch')
        require(item['transform'] in ('identity_pixel_grid', 'changed', 'unknown') and
                isinstance(item['reviewer'], str) and bool(item['reviewer'].strip()), 'Invalid geometry declaration')
        aligned = item['transform'] == 'identity_pixel_grid'
        annotation = by_id[key]['annotation']
        mask = by_id[key]['glass_mask']
        result.append(dict(image_id=key, input_sha256=pair['input_sha256'], output_sha256=pair['output_sha256'],
                           transform=item['transform'],
                           label_path=annotation['artifact_path'] if aligned and annotation['status']=='verified' else None,
                           label_sha256=annotation['artifact_sha256'] if aligned and annotation['status']=='verified' else None,
                           label_review_sha256=annotation['review_sha256'] if aligned and annotation['status']=='verified' else None,
                           mask_path=mask['artifact_path'] if aligned and mask['status']=='verified' else None,
                           mask_sha256=mask['artifact_sha256'] if aligned and mask['status']=='verified' else None,
                           mask_review_sha256=mask['review_sha256'] if aligned and mask['status']=='verified' else None))
    require(seen == set(pairs), 'Geometry review must cover every output')
    return dict(schema='bvt.research-inheritance-audit.v1', collection_id=collection, run_id=run_id,
                class_catalog_sha256=report['class_catalog_sha256'], geometry_review_sha256=digest(data),
                records=sorted(result, key=lambda r: r['image_id']))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='action', required=True)
    a = subs.add_parser('audit')
    a.add_argument('--collection', choices=COLLECTIONS)
    a.add_argument('--json', action='store_true', help='Emit complete read-only report to stdout')
    i = subs.add_parser('inherit')
    i.add_argument('--collection', required=True, choices=COLLECTIONS)
    i.add_argument('--run-id', required=True)
    args = p.parse_args(argv)
    try:
        if args.action == 'inherit':
            report = inheritance(ROOT, args.collection, args.run_id)
            print(json.dumps(report, ensure_ascii=True, sort_keys=True))
            return 0
        report = audit(ROOT, args.collection)
        if args.json:
            print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        else:
            print(f'IMAGES={len(report["records"])} CLASS_CATALOG={"PRESENT" if report["class_catalog_sha256"] else "MISSING"}')
            for kind, counts in report['counts'].items():
                print(kind.upper() + ' ' + ' '.join(f'{s.upper()}={counts.get(s,0)}' for s in ('pending','verified','rejected','invalid')))
            for issue in report['issues']:
                print(issue, file=sys.stderr)
            print('ANNOTATION_AUDIT=' + ('FAIL' if report['issues'] else 'PASS'))
        return 1 if report['issues'] else 0
    except ERRORS as exc:
        p.exit(1, f'ANNOTATION_ERROR: {exc}\n')


if __name__ == '__main__':
    sys.exit(main())
