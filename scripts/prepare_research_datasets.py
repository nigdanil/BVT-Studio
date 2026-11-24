"""Restore missing research images from an authorized Drive folder; verify offline.

No network API, credentials, overwrites, deletions of existing files or rights changes.
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = {
    'synthetic_chatgpt': ('chatgpt', '.png', 'PNG', '01_ChatGPT_Synthetic', 'synthetic'),
    'real_wikimedia': ('wikimedia', '.jpg', 'JPEG', '02_Wikimedia_Commons', 'real'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(root, relative):
    """Reject redirected descendants, including Windows junctions and broken links."""
    path = root
    for part in Path(relative).parts:
        require(part not in ('..', '.', '') and not Path(part).anchor,
                f'Unsafe path: {relative}')
        path = path / part
        require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
                f'Redirected path: {path}')
    require(path.resolve() == path, f'Redirected path: {path}')
    return path


def read_manifests(root):
    schema = json.loads(safe_path(root, 'datasets/schemas/dataset_manifest.schema.json')
                        .read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    groups, hashes = {}, set()
    for collection, (prefix, ext, fmt, storage, origin) in COLLECTIONS.items():
        path = safe_path(root, f'datasets/manifests/{collection}.jsonl')
        data = path.read_bytes()
        records = [json.loads(line) for line in data.decode('utf-8').splitlines()]
        require(len(records) == 100, f'Expected 100 records: {collection}')
        for i, r in enumerate(records, 1):
            validator.validate(r)
            image_id = f'{prefix}_{i:06d}'
            name = image_id + ext
            expected = dict(image_id=image_id, collection_id=collection,
                            relative_path=f'clean/images/{name}', file_format=fmt,
                            origin_type=origin, storage_provider='google_drive',
                            storage_relative_path=f'{storage}/images/{name}',
                            local_cache_path=f'data_local/{collection}/clean/images/{name}')
            require(all(r[k] == v for k, v in expected.items()),
                    f'Manifest path/ID mismatch: {collection}/{i}')
            require(r['sha256'] not in hashes, f'Duplicate SHA-256: {image_id}')
            hashes.add(r['sha256'])
        groups[collection] = (records, data)
    return groups


def verified_bytes(path, record):
    require(path.is_file(), f'Missing or not a file: {path}')
    data = path.read_bytes()
    require(sha256(data).hexdigest() == record['sha256'], f'SHA256 mismatch: {path}')
    with Image.open(BytesIO(data)) as im:
        require(im.format == record['file_format'], f'Format mismatch: {path}')
        require(im.size == (record['width'], record['height']), f'Dimensions mismatch: {path}')
        im.verify()
    with Image.open(BytesIO(data)) as im:
        im.load()
    return data


def source_root(root, source):
    path = Path(source).resolve()
    require(path.is_dir(), f'Source directory missing: {path}')
    require(not path.is_relative_to(root) and not root.is_relative_to(path),
            'Source and repository must not overlap')
    return path


def directory_paths():
    for collection in COLLECTIONS:
        for rel in ('clean/images', 'labels', 'glass_masks', 'runs'):
            yield f'data_local/{collection}/{rel}'
    for rel in ('downloads_staging', 'attribution'):
        yield f'data_local/real_wikimedia/{rel}'


def prepare(root, source=None, check=False):
    root = Path(root).resolve()
    groups = read_manifests(root)
    directories = [safe_path(root, rel) for rel in directory_paths()]
    missing, problems = [], []
    good = 0
    for folder in directories:
        if folder.exists() and not folder.is_dir():
            problems.append(f'Not a directory: {folder}')
        elif check and not folder.is_dir():
            problems.append(f'Missing directory: {folder}')
    for collection, (records, _) in groups.items():
        folder = safe_path(root, f'data_local/{collection}/clean/images')
        expected = {Path(r['local_cache_path']).name for r in records}
        if folder.is_dir():
            extras = sorted(p.name for p in folder.iterdir() if p.name not in expected)
            if extras:
                problems.append(f'Unexpected clean entries: {collection}: {extras}')
        for r in records:
            path = safe_path(root, r['local_cache_path'])
            if not path.exists():
                missing.append((path, r))
                continue
            try:
                verified_bytes(path, r)
                good += 1
            except (OSError, ValueError, SyntaxError) as exc:
                problems.append(f'Invalid cache {r["image_id"]}: {exc}')
    print(f'CACHE_VALID={good} CACHE_MISSING={len(missing)} CACHE_PROBLEMS={len(problems)}')
    if check or source is None:
        problems.extend(f'Missing cache: {r["image_id"]}' for _, r in missing)
    require(not problems, '\n'.join(problems))
    if check:
        return good, 0
    # Only consult Drive if images are actually missing. Complete caches work offline.
    pending = []
    if missing:
        cloud = source_root(root, source)
        for path, r in missing:
            original = safe_path(cloud, r['storage_relative_path'])
            try:
                verified_bytes(original, r)
                pending.append((path, original, r))
            except (OSError, ValueError, SyntaxError) as exc:
                problems.append(f'Invalid source {r["image_id"]}: {exc}')
        require(not problems, '\n'.join(problems))
    for folder in directories:
        folder.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for path, original, r in pending:
            data = verified_bytes(original, r)
            # Exclusive creation: never replace a file that appeared after preflight.
            with path.open('xb') as out:
                created.append(path)
                out.write(data)
            verified_bytes(path, r)
        for records, _ in groups.values():
            for r in records:
                verified_bytes(safe_path(root, r['local_cache_path']), r)
    except Exception:
        # Remove only files created by this invocation; existing cache is untouched.
        for path in created:
            path.unlink()
        raise
    return good, len(created)


def export_metadata(root, source):
    """Stage exact JSONL copies and image checksum lists in a downloaded Drive root."""
    root = Path(root).resolve()
    cloud = source_root(root, source)
    groups = read_manifests(root)
    outputs = {}
    for collection, (records, manifest_bytes) in groups.items():
        storage = COLLECTIONS[collection][3]
        folder = safe_path(cloud, f'{storage}/images')
        expected = {Path(r['storage_relative_path']).name for r in records}
        require(folder.is_dir() and {p.name for p in folder.iterdir()} == expected,
                f'Source inventory mismatch: {collection}')
        for r in records:
            verified_bytes(safe_path(cloud, r['storage_relative_path']), r)
        outputs[safe_path(cloud, f'{storage}/manifest.jsonl')] = manifest_bytes
        sums = ''.join(f'{r["sha256"]}  images/{Path(r["storage_relative_path"]).name}\n'
                       for r in records)
        outputs[safe_path(cloud, f'{storage}/SHA256SUMS.txt')] = sums.encode('ascii')
    for path, data in outputs.items():
        if path.exists():
            require(path.is_file() and path.read_bytes() == data,
                    f'Metadata differs; refusing overwrite: {path}')
    created = []
    try:
        for path, data in outputs.items():
            if not path.exists():
                with path.open('xb') as out:
                    created.append(path)
                    out.write(data)
            require(path.read_bytes() == data, f'Metadata write mismatch: {path}')
    except Exception:
        for path in created:
            path.unlink()
        raise
    return len(created), len(outputs) - len(created)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-copy', type=Path, help='Authorized external downloaded or mounted Drive root')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='Read-only local cache verification')
    modes.add_argument('--export-metadata', action='store_true', help='Stage metadata in source copy; no upload API')
    args = parser.parse_args()
    try:
        if args.export_metadata:
            require(args.source_copy is not None, '--export-metadata requires --source-copy')
            created, existing = export_metadata(ROOT, args.source_copy)
            print(f'METADATA_CREATED={created} METADATA_EXISTING={existing}')
            print('DATASET_METADATA_EXPORT=PASS')
        else:
            reused, copied = prepare(ROOT, args.source_copy, args.check)
            print(f'REUSED_IMAGES={reused} COPIED_IMAGES={copied} TOTAL_IMAGES={reused + copied}')
            print('RESEARCH_DATASET_PREPARE=PASS')
    except Exception as exc:
        parser.exit(1, f'RESEARCH_DATASET=FAIL: {exc}\n')


if __name__ == '__main__':
    main()
