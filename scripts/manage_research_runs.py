"""Prepare, register and verify immutable research experiment runs (no rendering)."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from PIL import Image

if __package__:
    from .prepare_research_datasets import COLLECTIONS, read_manifests, safe_path, verified_bytes, require
else:
    from prepare_research_datasets import COLLECTIONS, read_manifests, safe_path, verified_bytes, require

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'datasets/schemas/run_manifest.schema.json'
RUN_ID = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}', re.ASCII)
QA_STATES = ('PASS', 'REVIEW', 'REJECT', 'ERROR')
DIRS = ('augmented/images', 'previews', 'reports')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')


def digest(data):
    return sha256(data).hexdigest()


def read_json(path):
    def reject(value):
        raise ValueError(f'Nonfinite JSON value: {value}')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=reject, object_pairs_hook=unique)


def validate(root, value):
    schema = read_json(safe_path(root, SCHEMA))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def code_snapshot(root):
    # HEAD alone is insufficient for an uncommitted working tree. Include actual
    # code/config/schema bytes, even newly created nonignored source files.
    names = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--',
                'bvt_studio', 'scripts', 'configs', 'datasets/schemas', 'blender_manifest.toml')
    files = {}
    for name in sorted(set(names.decode('utf-8').split('\0')) - {''}):
        path = safe_path(root, name)
        if path.is_file():
            files[name] = digest(path.read_bytes())
    require(bool(files), 'No source files in code snapshot')
    return digest(encode(files))


def run_path(root, collection, run_id):
    require(collection in COLLECTIONS, 'Unknown collection')
    require(isinstance(run_id, str) and RUN_ID.fullmatch(run_id), 'Invalid run ID')
    # Windows reserves these names even with an extension; reject everywhere.
    require(run_id.upper() not in {'CON','PRN','AUX','NUL', *[f'COM{i}' for i in range(1,10)],
                                   *[f'LPT{i}' for i in range(1,10)]}, 'Reserved run ID')
    return safe_path(root, f'data_local/{collection}/runs/{run_id}')


def inputs(root, collection, image_ids=None):
    records, data = read_manifests(root)[collection]
    by_id = {r['image_id']: r for r in records}
    selected = sorted(by_id) if image_ids is None else sorted(image_ids)
    require(bool(selected) and len(selected) == len(set(selected)) and set(selected) <= set(by_id),
            'Unknown, duplicate or empty image selection')
    rows = []
    for image_id in selected:
        r = by_id[image_id]
        verified_bytes(safe_path(root, r['local_cache_path']), r)
        rows.append(dict(image_id=image_id, source_group_id=r['source_group_id'],
                         input_path=r['local_cache_path'], input_sha256=r['sha256'],
                         width=r['width'], height=r['height'],
                         output_path=f'augmented/images/{image_id}.png', output_sha256=None,
                         label_path=None, mask_path=None, qa_status='pending', generated_at=None))
    return rows, digest(data)


def initialize(root, collection, run_id, preset_id, seed, parameters, image_ids=None, engine_versions=None):
    root = Path(root).resolve()
    folder = run_path(root, collection, run_id)
    require(not any(run_path(root, c, run_id).exists() for c in COLLECTIONS),
            f'Run already exists: {run_id}')
    require(isinstance(parameters, dict), 'Effect parameters must be a JSON object')
    require(engine_versions is None or isinstance(engine_versions, dict), 'Tool versions must be a JSON object')
    rows, inventory_sha = inputs(root, collection, image_ids)
    stamp = now()
    value = dict(schema_version='bvt.research-run.v1', run_id=run_id, collection_id=collection,
                 status='prepared', preset_id=preset_id, seed=seed, effect_parameters=parameters,
                 tool_versions=dict(run_manager='1.0', python=sys.version.split()[0], pillow=version('Pillow'),
                                    declared_engine_versions=engine_versions or {}),
                 git_commit=git(root, 'rev-parse', 'HEAD').decode().strip(),
                 git_dirty=bool(git(root, 'status', '--porcelain=v1', '--untracked-files=all').strip()),
                 source_code_sha256=code_snapshot(root), dataset_manifest_sha256=inventory_sha,
                 created_at=stamp, recorded_at=None, qa_report_sha256=None, records=rows)
    validate(root, value)
    data = encode(value)  # reject nonfinite values before creating a directory
    folder.parent.mkdir(parents=True, exist_ok=True)
    folder.mkdir(exist_ok=False)
    for name in DIRS:
        (folder / name).mkdir(parents=True)
    with (folder / 'run_manifest.json').open('xb') as out:
        out.write(data)
    return value


def load_run(root, collection, run_id):
    folder = run_path(root, collection, run_id)
    path = safe_path(folder, 'run_manifest.json')
    value = read_json(path)
    validate(root, value)
    require(value['collection_id'] == collection and value['run_id'] == run_id, 'Run identity mismatch')
    for name in DIRS:
        require(safe_path(folder, name).is_dir(), f'Missing run directory: {name}')
    rows, inventory_sha = inputs(root, collection, [r['image_id'] for r in value['records']])
    require(inventory_sha == value['dataset_manifest_sha256'], 'Dataset manifest changed')
    for expected, actual in zip(rows, value['records']):
        for key in ('image_id','source_group_id','input_path','input_sha256','width','height','output_path',
                    'label_path','mask_path'):
            require(expected[key] == actual[key], f'Input/run metadata mismatch: {key}')
    return folder, path, value


def output_hash(folder, row):
    path = safe_path(folder, row['output_path'])
    require(path.is_file(), f'Missing output: {row["image_id"]}')
    require(path.stat().st_nlink == 1, f'Hard-linked output forbidden: {path}')
    data = path.read_bytes()
    with Image.open(BytesIO(data)) as im:
        require(im.format == 'PNG' and im.size == (row['width'], row['height']),
                f'Output format/dimensions mismatch: {row["image_id"]}')
        im.verify()
    with Image.open(BytesIO(data)) as im:
        im.load()
    return digest(data)


def inspect_outputs(folder, rows):
    images = safe_path(folder, 'augmented/images')
    expected = {Path(r['output_path']).name for r in rows}
    require({p.name for p in images.iterdir()} == expected, 'Output inventory mismatch (missing/extra files)')
    return {r['image_id']: output_hash(folder, r) for r in rows}


def qa_report(folder, rows, hashes):
    path = safe_path(folder, 'reports/qa_results.json')
    if not path.exists():
        return {}, None
    data = path.read_bytes()
    report = read_json(path)
    require(isinstance(report, dict) and set(report) == {'schema','records'} and
            report['schema'] == 'bvt.research-run.qa.v1' and isinstance(report['records'], list), 'Invalid QA report')
    expected = {r['image_id']: r for r in rows}
    statuses = {}
    for row in report['records']:
        require(isinstance(row, dict) and set(row) == {'image_id','input_sha256','output_sha256','qa_status'},
                'Invalid QA record fields')
        image_id = row['image_id']
        require(image_id in expected and image_id not in statuses, 'Invalid/duplicate QA image ID')
        require(row['input_sha256'] == expected[image_id]['input_sha256'] and row['output_sha256'] == hashes[image_id],
                f'QA hash mismatch: {image_id}')
        require(row['qa_status'] in QA_STATES, 'Invalid QA status')
        statuses[image_id] = row['qa_status']
    require(set(statuses) == set(expected), 'QA report must cover every output')
    require(data == path.read_bytes(), 'QA report changed during registration')
    return statuses, digest(data)


def check(root, collection, run_id):
    root = Path(root).resolve()
    folder, _, value = load_run(root, collection, run_id)
    if value['status'] == 'prepared':
        # Prepared is not a completed experiment; output files may be in progress.
        return value
    hashes = inspect_outputs(folder, value['records'])
    statuses, report_sha = qa_report(folder, value['records'], hashes)
    require(report_sha == value['qa_report_sha256'], 'QA report hash changed')
    for row in value['records']:
        image_id = row['image_id']
        require(row['output_sha256'] == hashes[image_id], f'Output SHA256 mismatch: {image_id}')
        require(row['qa_status'] == statuses.get(image_id, 'pending'), f'QA status mismatch: {image_id}')
    return value


def record_outputs(root, collection, run_id, generated_at=None):
    root = Path(root).resolve()
    folder, path, value = load_run(root, collection, run_id)
    if value['status'] == 'outputs_recorded':
        require(generated_at is None or all(r['generated_at'] == generated_at for r in value['records']),
                'Recorded generation timestamp differs')
        return check(root, collection, run_id)
    require(value['git_commit'] == git(root, 'rev-parse', 'HEAD').decode().strip() and
            value['source_code_sha256'] == code_snapshot(root), 'Code changed since run preparation')
    original = path.read_bytes()
    hashes = inspect_outputs(folder, value['records'])
    statuses, report_sha = qa_report(folder, value['records'], hashes)
    for row in value['records']:
        row['output_sha256'] = hashes[row['image_id']]
        row['qa_status'] = statuses.get(row['image_id'], 'pending')
        row['generated_at'] = generated_at
    value.update(status='outputs_recorded', recorded_at=now(), qa_report_sha256=report_sha)
    validate(root, value)
    data = encode(value)
    # Single-writer protocol. Atomic replacement of this run's prepared manifest only;
    # no replacement of inputs, outputs, QA files or previously recorded manifests.
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix='.manifest-', delete=False) as out:
            temp = Path(out.name)
            out.write(data)
        require(path.read_bytes() == original, 'Run manifest changed during registration')
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()
    return value


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='action', required=True)
    for action in ('init', 'record', 'check'):
        sub = subs.add_parser(action)
        sub.add_argument('--collection', required=True, choices=COLLECTIONS)
        sub.add_argument('--run-id', required=action != 'init')
        if action == 'record':
            sub.add_argument('--generated-at', help='Declared actual generation time, ISO 8601 with timezone; otherwise null')
        if action == 'init':
            sub.add_argument('--preset-id', required=True)
            sub.add_argument('--seed', required=True, type=int)
            sub.add_argument('--effect-parameters', required=True, type=Path)
            sub.add_argument('--tool-versions', type=Path, help='Declared renderer/engine versions (JSON object)')
            sub.add_argument('--image-id', action='append', help='Select source IDs; default: whole collection')
    a = p.parse_args(argv)
    try:
        if a.action == 'init':
            run_id = a.run_id or ('run-' + uuid4().hex)
            value = initialize(ROOT, a.collection, run_id, a.preset_id, a.seed,
                               read_json(a.effect_parameters), a.image_id,
                               read_json(a.tool_versions) if a.tool_versions else None)
        elif a.action == 'record':
            value = record_outputs(ROOT, a.collection, a.run_id, a.generated_at)
        else:
            value = check(ROOT, a.collection, a.run_id)
    except (OSError, ValueError, SyntaxError, ValidationError, subprocess.CalledProcessError) as exc:
        p.exit(1, f'RESEARCH_RUN_ERROR: {exc}\n')
    print(f'RUN_ID={value["run_id"]} STATUS={value["status"]} RECORDS={len(value["records"])}')
    print(f'RESEARCH_RUN_{a.action.upper()}=PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
