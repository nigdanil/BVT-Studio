"""Research Dataset Runner: plan, decode clean controls, or render reviewed masks.

Called by bvt_dataset_runner.py research; no annotation, split or rights edits.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageChops

if __package__:
    from . import manage_research_runs as runs, check_research_annotations as annotations
    from . import validate_research_dataset as validator, prepare_research_datasets as storage
else:
    import manage_research_runs as runs
    import check_research_annotations as annotations
    import validate_research_dataset as validator
    import prepare_research_datasets as storage

ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'configs/effects_gallery_v02.json'
EFFECTS = ('00_clean', '01_light_condensation', '02_heavy_condensation', '03_frost',
           '04_dirty_glass', '05_reflections', '06_microbeads_only', '07_macro_droplets_only',
           '08_running_water_only', '09_combined_water_no_optics', '10_combined_water_optics',
           '11_heavy_running_water')
SCHEMA = 'bvt.research-runner.v1'
require = storage.require
safe = storage.safe_path


def digest(data):
    return sha256(data).hexdigest()


def exclusive(path, data):
    with path.open('xb') as stream:
        stream.write(data)


def json_new(path, value):
    exclusive(path, runs.encode(value))


def png_bytes(im):
    out = BytesIO()
    im.save(out, format='PNG')
    return out.getvalue()


def source_pixels(root, record):
    data = storage.verified_bytes(safe(root, record['local_cache_path']), record)
    with Image.open(BytesIO(data)) as im:
        require(im.getexif().get(274, 1) == 1, 'Non-identity EXIF orientation requires reviewed normalization')
        require(im.mode in ('RGB', 'RGBA', 'L'), f'Unsupported source mode: {im.mode}')
        if im.mode == 'RGBA':
            require(im.getchannel('A').getextrema() == (255, 255), 'Nonopaque source unsupported')
        return im.convert('RGB')


def mask_pixels(root, record, evidence):
    data = annotations.file_bytes(safe(root, evidence['artifact_path']))
    review = annotations.file_bytes(safe(root, str(Path(evidence['artifact_path']).with_suffix('.json'))))
    require(digest(data) == evidence['artifact_sha256'] and digest(review) == evidence['review_sha256'],
            'Mask/review changed since audit')
    annotations.mask_pixels(data, record)
    require(annotations.review(review, record, 'glass_mask', digest(data), None) == 'approved', 'Mask not approved')
    with Image.open(BytesIO(data)) as im:
        mask = im.copy()
    bbox = mask.getbbox()
    require(bbox[2]-bbox[0] >= 2 and bbox[3]-bbox[1] >= 2, 'Mask envelope must be at least 2x2')
    return mask, bbox, data, review


def make_plan(root, collection, run_id, effect, seed, ids, max_images=5):
    root = Path(root).resolve()
    require(collection in storage.COLLECTIONS and effect in EFFECTS, 'Unsupported collection/effect')
    runs.run_path(root, collection, run_id)  # Validate path/ID without creating it.
    require(not any(runs.run_path(root, c, run_id).exists() for c in storage.COLLECTIONS), 'Run already exists')
    require(type(seed) is int and 0 <= seed < 2**31-100, 'Invalid seed range')
    require(type(max_images) is int and 1 <= max_images <= 100, 'max-images must be 1..100')
    groups = storage.read_manifests(root)
    records, raw = groups[collection]
    by_id = {r['image_id']: r for r in records}
    selected = sorted(by_id) if ids is None else sorted(ids)
    require(bool(selected) and len(set(selected)) == len(selected) and set(selected) <= set(by_id), 'Invalid image selection')
    require(len(selected) <= max_images, f'Selection exceeds explicit max-images={max_images}')
    validation = validator.validate(root)
    require(validation['status'] == 'PASS', f'Dataset validation failed: {validation["issues"][:3]}')
    require(validation['manifest_sha256'][collection] == digest(raw), 'Manifest changed during preflight')
    config_data = safe(root, CONFIG).read_bytes()
    cfg = annotations.json_object(config_data)
    require(cfg['schema'] == 'bvt.glass-gallery.v02', 'Invalid preset catalog')
    variants = {}
    for key in dict.fromkeys(('00_clean', effect)):
        spec = cfg['variants'][key]
        require(isinstance(spec, dict) and not spec.get('stress') and not spec.get('pane_overrides'), 'Unsafe preset')
        variants[key] = deepcopy(spec)
    require(variants['00_clean']['preset'] == 'QA_TRANSPARENT' and not variants['00_clean'].get('water'), 'Invalid clean preset')
    names, class_sha = annotations.catalog(root)
    jobs = []
    for key in selected:
        r = by_id[key]
        label = annotations.inspect_artifact(root, r, 'annotation', names, class_sha)
        mask = annotations.inspect_artifact(root, r, 'glass_mask', names, class_sha)
        bbox = None
        blockers = []
        if effect != '00_clean':
            if mask['status'] != 'verified':
                blockers.append('verified_glass_mask_required')
            else:
                try:
                    _, bbox, _, _ = mask_pixels(root, r, mask)
                except ValueError as exc:
                    blockers.append(str(exc))
        jobs.append(dict(image_id=key, input_sha256=r['sha256'], source_group_id=r['source_group_id'],
                         width=r['width'], height=r['height'], split=r['split'],
                         seed=seed+int(key.rsplit('_', 1)[1])-1,
                         label=label, glass_mask=mask, rect=list(bbox) if bbox else None,
                         blockers=blockers, output_path=f'augmented/images/{key}.png',
                         license_verification_status=r['license_verification_status'],
                         derivative_use_review_status=r['derivative_use_review_status']))
    return dict(schema=SCHEMA, collection_id=collection, run_id=run_id, effect=effect, seed=seed,
                dataset_manifest_sha256=digest(raw), catalog_sha256=digest(config_data),
                class_catalog_sha256=class_sha, variants=variants, jobs=jobs,
                executable=not any(j['blockers'] for j in jobs),
                backend='decoded_rgb_control' if effect == '00_clean' else 'blender_gallery_v02_masked_composite',
                warning='Local research only; no legal clearance, automatic label inheritance, or calibrated severity.')


def invoke(command, root, log):
    try:
        with log.open('x', encoding='utf-8') as stream:
            subprocess.run([str(x) for x in command], cwd=root, stdout=stream, stderr=subprocess.STDOUT, check=True)
    except subprocess.CalledProcessError as exc:
        # Print the actual child error before a temporary smoke fixture is removed.
        tail = log.read_bytes()[-16000:].decode('utf-8', errors='replace')
        print(f'BLENDER_LOG={log}\n{tail}', file=sys.stderr, flush=True)
        raise RuntimeError(f'Blender failed ({exc.returncode}); see {log}') from exc


def load_rgb(path, size):
    with Image.open(path) as im:
        require(im.format == 'PNG' and im.size == size and im.mode == 'RGB', 'Unexpected renderer PNG format/dimensions')
        im.load()
        return im.copy()


def validate_render(gallery, mode, spec, source_sha, bbox, size, seed):
    folder = safe(gallery, mode)
    manifest = runs.read_json(safe(folder, 'manifest.json'))
    require(manifest.get('schema') == 'bvt.glass-gallery.v02' and manifest.get('variant') == mode
            and manifest.get('source_sha256') == source_sha and manifest.get('rects') == [list(bbox)]
            and manifest.get('mask_provenance') == 'external_not_verified', 'Renderer source/mask/geometry contract mismatch')
    require(manifest.get('calibration') == 'v0.2.1_matched_neutral_realistic_atlas', 'Wrong renderer calibration')
    panes = manifest['panes']
    water = spec.get('water')
    require(len(panes) == 1 and panes[0]['name'] == 'Glass_p_001' and panes[0]['seed'] == seed
            and panes[0]['preset'] == spec['preset'] and panes[0].get('mask_packed') is True
            and panes[0].get('water_kind') == (water.get('kind', 'COMBINED') if water else None), 'Renderer pane mismatch')
    if mode != '00_clean':
        q = manifest.get('quality') or {}
        require(q.get('leakage_pixels_beyond_3px_geometry_guard') == 0, 'Renderer geometry QA failed')
    else:
        require(manifest.get('quality') is None, 'Unexpected clean QA')
    if water:
        null = manifest.get('zero_water_test') or {}
        require(null.get('status') == 'PASS' and null.get('changed_pixels_gt_4_255') == 0
                and null.get('same_shader_topology') is True and null.get('same_renderer_controls') is True,
                'Water null test failed')
        for name in ('preset_without_water.png', 'zero_water_rebuild.png'):
            load_rgb(safe(folder, name), size)
    require(safe(folder, 'scene.blend').stat().st_size > 0, 'Missing Blender scene')
    return load_rgb(safe(folder, 'render.png'), size)


def render_effect(root, folder, record, job, plan, source, blender):
    """Use the established gallery backend. Full-frame mask is a final pixel gate."""
    mask, bbox, mask_data, review = mask_pixels(root, record, job['glass_mask'])
    require(list(bbox) == job['rect'], 'Mask geometry changed')
    gallery = folder / 'gallery'
    gallery.mkdir()
    # The gallery forbids output inside the input photo directory. Keep the
    # render input separate, and a byte-identical copy for packed-scene reopen.
    input_dir = folder / 'input'
    input_dir.mkdir()
    photo = input_dir / 'source.png'
    source_data = png_bytes(source)
    exclusive(photo, source_data)
    portable_source = gallery / 'source.png'
    exclusive(portable_source, source_data)
    exclusive(folder/'full_mask.png', mask_data)
    exclusive(folder/'mask_review.json', review)
    rects = folder/'rects.json'
    json_new(rects, dict(reference_size=list(source.size), glass_rectangles=[list(bbox)]))
    masks = folder/'masks'; masks.mkdir()
    crop = png_bytes(mask.crop(bbox))
    exclusive(masks/'mask_glass_001.png', crop)
    variants = deepcopy(plan['variants'])
    for spec in variants.values():
        spec['seed_base'] = job['seed']
    config = folder/'resolved_gallery.json'
    json_new(config, dict(schema='bvt.glass-gallery.v02', variants=variants))
    base = [blender, '--background', '--factory-startup', '--python-exit-code', '1', '--python']
    rendered, evidence = {}, {}
    for mode, spec in variants.items():
        invoke([*base, root/'scripts/bvt_glass_effect_gallery_v02.py', '--', '--repo', root,
                '--photo', photo, '--output', gallery, '--rects-file', rects, '--config', config,
                '--mode', mode, '--mask-dir', masks], root, folder/(mode+'.render.log'))
        rendered[mode] = validate_render(gallery, mode, spec, digest(source_data), bbox, source.size, job['seed'])
        d = gallery/mode
        # The reopen utility relocates the packed mask to this local path.
        exclusive(d/'masks'/'mask_glass_001.png', crop)
        invoke([*base, root/'scripts/blender_release_reopen.py', '--', '--blend', d/'scene.blend',
                '--manifest', d/'manifest.json', '--report', d/'reopen.json'], root, folder/(mode+'.reopen.log'))
        reopened = runs.read_json(d/'reopen.json')
        require(reopened.get('status') == 'PASS' and reopened.get('variant') == mode, 'Scene reopen failed')
        evidence[mode] = {n: digest((d/n).read_bytes()) for n in ('render.png','scene.blend','manifest.json','reopen.json')}
    require(photo.read_bytes() == source_data and portable_source.read_bytes() == source_data
            and (masks/'mask_glass_001.png').read_bytes() == crop,
            'Renderer changed working source or mask')
    effect = rendered[plan['effect']]
    delta = ImageChops.difference(effect, rendered['00_clean'])
    require(Image.composite(delta, Image.new('RGB',source.size), mask).getbbox() is not None,
            'No measurable effect inside verified mask')
    # Do not use the raw Blender output as a research derivative outside glass.
    output = Image.composite(effect, source, mask)
    outside = mask.point(lambda x: 255-x)
    require(Image.composite(ImageChops.difference(output, source), Image.new('RGB',source.size), outside).getbbox() is None,
            'Output changed outside verified mask')
    require(ImageChops.difference(output, source).getbbox() is not None, 'Output identical to source')
    return output, dict(renderer=evidence, rectangle=list(bbox),
                        working_source_sha256=digest(source_data), full_mask_sha256=digest(mask_data),
                        cropped_mask_sha256=digest(crop), mask_review_sha256=digest(review),
                        resolved_gallery_sha256=digest(config.read_bytes()),
                        outside_mask_changed_pixels=0, effect_delta_inside_mask=True)


def execute(root, plan, blender=None):
    root = Path(root).resolve()
    collection, run_id, effect = (plan[k] for k in ('collection_id','run_id','effect'))
    ids = [j['image_id'] for j in plan['jobs']]
    require(plan == make_plan(root, collection, run_id, effect, plan['seed'], ids, len(ids)), 'Stale plan')
    require(plan['executable'], 'Execution blocked: individually verified glass masks required')
    version = None
    if effect != '00_clean':
        require(blender is not None and Path(blender).is_file(), 'Provide --blender executable')
        blender = Path(blender).resolve()
        version = subprocess.check_output([str(blender), '--version'], text=True).splitlines()[0]
        require(version.startswith('Blender '), 'Unexpected Blender version output')
        for name in ('scripts/bvt_glass_effect_gallery_v02.py','scripts/blender_release_reopen.py','bvt_studio/__init__.py'):
            require(safe(root, name).is_file(), f'Missing renderer input: {name}')
    records = {r['image_id']: r for r in storage.read_manifests(root)[collection][0]}
    # Fail before creation on unsupported EXIF/alpha, not halfway through a batch.
    for key in ids:
        source_pixels(root, records[key])
    parameters = dict(plan=plan, backend=plan['backend'])
    runs.initialize(root, collection, run_id, effect, plan['seed'], parameters, ids,
                    dict(research_runner='1.0', **({'blender': version} if version else {})))
    folder = runs.run_path(root, collection, run_id)
    report = dict(schema=SCHEMA, status='RUNNING', run_id=run_id, collection_id=collection,
                  effect=effect, backend=plan['backend'], jobs=[], qa_status='pending',
                  publication_status='not_authorized', label_inheritance='not_performed')
    json_new(folder/'reports/plan.json', plan)
    try:
        for job in plan['jobs']:
            key = job['image_id']; record = records[key]
            source = source_pixels(root, record)
            if effect == '00_clean':
                output, evidence = source, {'identity_decoded_rgb': True, 'artifact_applied': False}
            else:
                d = folder/'previews'/key; d.mkdir()
                output, evidence = render_effect(root, d, record, job, plan, source, blender)
            data = png_bytes(output)
            exclusive(safe(folder, job['output_path']), data)
            report['jobs'].append(dict(image_id=key, source_group_id=job['source_group_id'], split=job['split'],
                input_sha256=job['input_sha256'], output_sha256=digest(data), output_path=job['output_path'],
                seed=job['seed'], annotation_status=job['label']['status'], glass_mask_status=job['glass_mask']['status'],
                qa_status='pending', evidence=evidence))
        # Check all source records and the exact selected annotation/review evidence again.
        validation = validator.validate(root)
        require(validation['status'] == 'PASS' and validation['manifest_sha256'][collection] == plan['dataset_manifest_sha256'],
                'Dataset changed during execution')
        require(digest(safe(root, CONFIG).read_bytes()) == plan['catalog_sha256'], 'Preset catalog changed')
        names, class_sha = annotations.catalog(root)
        require(class_sha == plan['class_catalog_sha256'], 'Class catalog changed')
        for job in plan['jobs']:
            record = records[job['image_id']]
            require(annotations.inspect_artifact(root, record, 'annotation', names, class_sha) == job['label']
                    and annotations.inspect_artifact(root, record, 'glass_mask', names, class_sha) == job['glass_mask'],
                    'Annotation/review changed during execution')
        registered = runs.record_outputs(root, collection, run_id, generated_at=runs.now())
        require({r['image_id']: r['output_sha256'] for r in registered['records']} ==
                {r['image_id']: r['output_sha256'] for r in report['jobs']}, 'Registered output hash mismatch')
        require(all(r['qa_status'] == 'pending' for r in registered['records']), 'Unexpected QA approval')
        report['run_manifest_sha256'] = digest((folder/'run_manifest.json').read_bytes())
        report['status'] = 'PASS'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='ERROR', error=str(exc))
        raise
    finally:
        json_new(folder/'reports/runner_report.json', report)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection', required=True, choices=storage.COLLECTIONS)
    p.add_argument('--run-id', required=True)
    p.add_argument('--effect', required=True, choices=EFFECTS)
    p.add_argument('--seed', type=int, default=42)
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument('--image-id', action='append')
    selection.add_argument('--all', action='store_true')
    p.add_argument('--max-images', type=int, default=5)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Read-only plan (default)')
    mode.add_argument('--execute', action='store_true', help='Create new local run, never publish')
    p.add_argument('--blender', type=Path)
    a = p.parse_args(argv)
    try:
        plan = make_plan(ROOT, a.collection, a.run_id, a.effect, a.seed, a.image_id, a.max_images)
        result = execute(ROOT, plan, a.blender) if a.execute else plan
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except Exception as exc:
        print(f'RESEARCH_DATASET_RUNNER=FAIL: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
