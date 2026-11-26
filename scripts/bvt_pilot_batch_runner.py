#!/usr/bin/env python3
"""BVT-Studio Pilot 001: immutable master scenes -> paired smoke-test renders.

Normal Python launcher; Blender 5.2 worker uses repository APIs. Default is
read-only planning. --execute creates a NEW run; no master file is saved.
The built-in conditions remain an engineering smoke test. --matrix loads
a validated experimental JSON matrix; its exact bytes are archived in the run.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path.home() / 'Desktop' / 'YOLO'
REPO = Path(__file__).resolve().parents[1]
BUILD = 'alpha.5-step5'
CONDITIONS = (
    dict(id='00_clean', preset=None, intensity=0.0, coverage=0.0),
    dict(id='01_light_condensation', preset='LIGHT_CONDENSATION', intensity=0.5, coverage=0.24),
    dict(id='02_frost', preset='FROST', intensity=0.5, coverage=0.40),
)
SEED = 42
CHANNELS = frozenset({
    'bvt_glass_droplets', 'bvt_glass_frost',
    'bvt_glass_reflection', 'bvt_glass_dirt',
})
PRESETS = frozenset({
    'LIGHT_CONDENSATION', 'HEAVY_CONDENSATION', 'FROST',
    'DIRTY_GLASS', 'REFLECTIONS',
})
MATRIX_SCHEMA = 'bvt_pilot_matrix_v1'


def validate_conditions(conditions):
    """Reject ambiguous interventions before any output directory is created."""
    if not isinstance(conditions, (list, tuple)) or not 2 <= len(conditions) <= 64:
        raise ValueError('Expected 2..64 conditions, including one clean control')
    seen = set()
    for index, c in enumerate(conditions):
        if not isinstance(c, dict):
            raise ValueError('Condition must be an object')
        required = {'id', 'preset', 'intensity', 'coverage'}
        extra = set(c) - required
        if not required <= set(c) or extra not in (set(), {'channel', 'channel_max'}):
            raise ValueError('Invalid condition keys')
        name = c['id']
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', name) or name in seen:
            raise ValueError(f'Invalid or duplicate condition ID: {name!r}')
        seen.add(name)
        for key in ('intensity', 'coverage', *(['channel_max'] if extra else [])):
            value = c[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f'{name}: {key} must be finite in [0, 1]')
        if index == 0:
            if name != '00_clean' or c['preset'] is not None or extra or c['intensity'] != 0 or c['coverage'] != 0:
                raise ValueError('First condition must be 00_clean with zero parameters')
        elif c['intensity'] <= 0:
            raise ValueError(f'{name}: non-clean intensity must be positive')
        elif extra:
            if c['preset'] != 'CUSTOM' or c['channel'] not in CHANNELS or c['channel_max'] <= 0:
                raise ValueError(f'{name}: invalid single-channel intervention')
        elif c['preset'] not in PRESETS:
            raise ValueError(f'{name}: unsupported preset')
    return conditions


def load_matrix(path):
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema') != MATRIX_SCHEMA:
        raise ValueError('Unsupported matrix schema')
    if set(data) != {'schema', 'description', 'seed', 'conditions'} or not isinstance(data['description'], str):
        raise ValueError('Invalid matrix fields')
    seed = data['seed']
    if type(seed) is not int or not 0 <= seed <= 2147483646:
        raise ValueError('Seed must allow seed + 1 for the second glass')
    return validate_conditions(data['conditions']), seed, raw


def digest(path):
    with Path(path).open('rb') as f:
        h = hashlib.sha256()
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
        return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def find_blender(explicit):
    if explicit:
        p = Path(explicit).resolve()
        if p.is_file():
            return str(p)
        raise FileNotFoundError(p)
    for env in ('ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA'):
        if os.environ.get(env):
            root = Path(os.environ[env])
            for base in (root/'Blender Foundation', root/'Programs'/'Blender Foundation', root/'Programs'):
                for p in sorted(base.glob('Blender 5.2*/blender.exe'), reverse=True):
                    if p.is_file():
                        return str(p.resolve())
    exe = shutil.which('blender') or shutil.which('blender.exe')
    if exe:
        return exe
    raise FileNotFoundError('Specify --blender with the full path to Blender 5.2')


def same_rows(a, b):
    remaining = list(b)
    if len(a) != len(remaining):
        return False
    for row in a:
        idx = next((i for i, other in enumerate(remaining)
                    if row[0] == other[0] and all(abs(x-y) <= 1e-6 for x,y in zip(row[1:], other[1:]))), None)
        if idx is None:
            return False
        remaining.pop(idx)
    return not remaining


def plan(repo, root, ids, run_id, conditions=CONDITIONS, seed=SEED):
    validate_conditions(conditions)
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', run_id):
        raise ValueError('Invalid run ID')
    if not ids or len(set(ids)) != len(ids) or any(not 1 <= i <= 10 for i in ids):
        raise ValueError('Unique scene IDs 1..10 required for Pilot 001')
    if not (repo/'bvt_studio'/'__init__.py').is_file():
        raise FileNotFoundError('Missing repository package: ' + str(repo))
    out = (repo/'data_local'/'research_runs'/run_id).resolve()
    if out.exists():
        raise FileExistsError('Run already exists; use a new --run-id: ' + str(out))
    if out == root or root in out.parents or out in root.parents:
        raise ValueError('Run directory must be separate from master directory')
    jobs = []
    for i in ids:
        sid = f'{i:04d}'
        folder = root/sid
        candidates = [p for p in (folder/f'scene_{sid}.blend', folder/f'{sid}.blend') if p.is_file()]
        if len(candidates) != 1:
            raise ValueError(f'{sid}: expected exactly one master filename, found {len(candidates)}')
        master = candidates[0].resolve()
        source = (repo/'data_local'/'synthetic_chatgpt'/'clean'/'images'/f'chatgpt_{i:06d}.png').resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        labels = sorted(folder.glob('labels/train/*.txt')) + sorted(folder.glob('labels/val/*.txt'))
        if not labels:
            raise ValueError(f'{sid}: no exported reference YOLO TXT')
        jobs.append(dict(id=sid, master=str(master), master_sha256=digest(master), source=str(source),
                         source_sha256=digest(source), labels=[dict(path=str(p.resolve()), sha256=digest(p)) for p in labels],
                         repo=str(repo), output=str(out), conditions=list(conditions), seed=seed))
    return out, jobs


def assert_inputs(job):
    for path, expected in [(job['master'], job['master_sha256']), (job['source'], job['source_sha256'])] + [(x['path'], x['sha256']) for x in job['labels']]:
        if digest(path) != expected:
            raise RuntimeError('Input changed: ' + path)


def worker(job):
    import bpy
    import numpy as np
    from bpy_extras.object_utils import world_to_camera_view
    repo = Path(job['repo']).resolve()
    master = Path(job['master'])
    out = Path(job['output'])
    sid = job['id']
    sys.path.insert(0, str(repo))
    import bvt_studio
    if Path(bvt_studio.__file__).resolve().parent != repo/'bvt_studio':
        raise RuntimeError('Unexpected BVT module path')
    if bpy.app.version[:2] != (5, 2) or getattr(bvt_studio, 'BUILD_STAGE', None) != BUILD:
        raise RuntimeError('Expected Blender 5.2 and BVT ' + BUILD)
    if not hasattr(bpy.types.Scene, 'bvt_studio'):
        bvt_studio.register()
    from bvt_studio.common import get_source, image_from_mesh, scene_annotations
    from bvt_studio.glass import scene_glass, configure_glass
    from bvt_studio.annotation import collect_boxes
    from bvt_studio.export_preview import label_text, parse_label_text
    from bvt_studio.artifact_presets import apply_preset
    from bvt_studio.scene_lock import apply_scene_locks

    def snapshot(scene):
        # Compare actual camera-projected vertices (not UI lock flags), camera,
        # and serialized YOLO coordinates before and after every intervention.
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        camera = scene.camera
        def coords(obj):
            mat = obj.evaluated_get(dg).matrix_world
            return [[float(v) for v in world_to_camera_view(scene, camera, mat @ vert.co)] for vert in obj.data.vertices]
        boxes, issues, classes = collect_boxes(scene)
        if issues or classes != {0: 'ice_cream'} or not boxes:
            raise RuntimeError(f'YOLO validation failed: {issues}; classes={classes}')
        if len({b['uid'] for b in boxes}) != len(boxes):
            raise RuntimeError('Duplicate annotation UID')
        panes = scene_glass(scene)
        if len(panes) != 2 or len({str(p.get('bvt_glass_uid','')) for p in panes}) != 2 or any(not p.get('bvt_glass_uid') for p in panes):
            raise RuntimeError('Expected two uniquely identified glass planes')
        objects = [get_source(scene), *panes, *scene_annotations(scene)]
        projections = {obj.name: coords(obj) for obj in objects}
        if any(not math.isfinite(v) for rows in projections.values() for row in rows for v in row):
            raise RuntimeError('Non-finite projection')
        return dict(labels=label_text(boxes), uids=[b['uid'] for b in boxes], projections=projections,
                    camera_matrix=[list(row) for row in camera.matrix_world], ortho_scale=float(camera.data.ortho_scale),
                    size=[scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage])

    def verify_geometry(first, second):
        if first['labels'] != second['labels'] or first['uids'] != second['uids'] or first['size'] != second['size']:
            raise RuntimeError('YOLO labels, UIDs or resolution changed')
        if first['projections'].keys() != second['projections'].keys():
            raise RuntimeError('Scene objects changed')
        for name, a in first['projections'].items():
            b = second['projections'][name]
            if np.shape(a) != np.shape(b) or not np.allclose(a, b, atol=1e-7, rtol=0):
                raise RuntimeError('Projected geometry changed: ' + name)
        if not np.allclose(first['camera_matrix'], second['camera_matrix'], atol=1e-7, rtol=0) or abs(first['ortho_scale']-second['ortho_scale']) > 1e-7:
            raise RuntimeError('Camera changed')

    def pixels(path):
        image = bpy.data.images.load(str(path), check_existing=False)
        try:
            w, h = image.size[:]
            data = np.empty(len(image.pixels), dtype=np.float32)
            image.pixels.foreach_get(data)
            if data.size != w*h*4 or not np.isfinite(data).all():
                raise RuntimeError('Unexpected PNG pixel buffer')
            return (w, h), data.reshape(h, w, 4)[:, :, :3].copy()
        finally:
            bpy.data.images.remove(image)

    baseline = None
    clean_path = None
    records = []
    for condition in job['conditions']:
        assert_inputs(job)
        # Reload the original for each condition: no cumulative shader state.
        bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False, use_scripts=False)
        candidates = [s for s in bpy.data.scenes if get_source(s) is not None and scene_annotations(s)]
        if len(candidates) != 1 or bpy.context.window is None:
            raise RuntimeError('Expected one annotated BVT scene with a window context')
        scene = candidates[0]
        bpy.context.window.scene = scene
        bpy.context.view_layer.update()
        image = image_from_mesh(get_source(scene))
        if image is None or scene.camera is None or scene.camera.data.type != 'ORTHO' or scene.render.use_border:
            raise RuntimeError('Invalid source/camera or render border enabled')
        if image.packed_file:
            if hashlib.sha256(bytes(image.packed_file.data)).hexdigest() != job['source_sha256']:
                raise RuntimeError('Packed photo differs from canonical source')
        else:
            actual = Path(bpy.path.abspath(image.filepath, library=image.library))
            if not actual.is_file() or digest(actual) != job['source_sha256']:
                raise RuntimeError('External photo differs from canonical source')
        resolution = [round(scene.render.resolution_x * scene.render.resolution_percentage / 100), round(scene.render.resolution_y * scene.render.resolution_percentage / 100)]
        if resolution != list(image.size[:]) or min(resolution) <= 0:
            raise RuntimeError('Render/source dimensions differ')
        before = snapshot(scene)
        live = parse_label_text(before['labels'])
        matches = [x['path'] for x in job['labels'] if same_rows(live, parse_label_text(Path(x['path']).read_text(encoding='utf-8-sig')))]
        if not matches:
            raise RuntimeError('No matching exported reference TXT')
        if baseline is None:
            baseline = before
        else:
            verify_geometry(baseline, before)
        settings = scene.bvt_studio
        settings.scene_locks_enabled = True
        settings.photo_edit_enable = False
        settings.camera_edit_enable = False
        settings.light_edit_enable = False
        settings.glass_edit_enable = False
        apply_scene_locks(scene)
        for obj in scene_annotations(scene):
            obj.hide_render = True
        glass_state = []
        for idx, obj in enumerate(scene_glass(scene)):
            # Clean = photo-only render; effect = fresh independent shader.
            # Neither path modifies the mesh or saves the .blend.
            if condition['preset'] is None:
                obj.hide_render = True
            else:
                # Remove inherited material slots in RAM only, then rebuild via
                # the project API. Existing master material differences vanish.
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                obj.data.materials.clear()
                seed = job['seed'] + idx
                if condition['preset'] == 'CUSTOM':
                    # Start from a zero-channel, fully reset procedural preset.
                    # CUSTOM uses the regular shader, not the hybrid atlas.
                    apply_preset(obj, 'CLEAN', 0.0, condition['coverage'], seed)
                    obj['bvt_artifact_preset'] = 'CUSTOM'
                    obj[condition['channel']] = round(condition['channel_max'] * condition['intensity'], 6)
                    configure_glass(obj)
                else:
                    apply_preset(obj, condition['preset'], condition['intensity'], condition['coverage'], seed)
                obj.hide_render = False
            glass_state.append(dict(name=obj.name, uid=str(obj['bvt_glass_uid']), hide_render=bool(obj.hide_render),
                                    preset=str(obj.get('bvt_artifact_preset','')), seed=int(obj.get('bvt_artifact_seed',0)),
                                    channels={k:float(obj.get(k,0)) for k in ('bvt_glass_reflection','bvt_glass_tint','bvt_glass_haze','bvt_glass_frost','bvt_glass_droplets','bvt_glass_dirt','bvt_artifact_coverage')}))
        verify_geometry(before, snapshot(scene))
        condition_root = out/condition['id']
        target = condition_root/'images'/f'scene_{sid}.png'
        label = condition_root/'labels'/f'scene_{sid}.txt'
        if target.exists() or label.exists():
            raise FileExistsError('Output already exists')
        scene.render.engine = 'BLENDER_EEVEE'
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '8'
        scene.render.filepath = str(target)
        if 'FINISHED' not in bpy.ops.render.render(write_still=True) or not target.is_file():
            raise RuntimeError('Render failed')
        verify_geometry(before, snapshot(scene))
        size, rendered = pixels(target)
        if list(size) != resolution:
            raise RuntimeError('Rendered PNG dimensions differ')
        if condition['preset'] is None:
            clean_path = target
            delta = None
        else:
            clean_size, clean = pixels(clean_path)
            if clean_size != size:
                raise RuntimeError('Clean/effect dimensions differ')
            diff = np.abs(rendered-clean)
            delta = dict(mean_abs_rgb=float(diff.mean()), max_abs_rgb=float(diff.max()), changed_pixel_fraction=float((diff.max(axis=2)>1e-6).mean()))
            if delta['max_abs_rgb'] <= 1e-6:
                raise RuntimeError('Effect render identical to clean')
        label.write_text(before['labels'], encoding='utf-8', newline='\n')
        record = dict(id=sid, condition=condition, image=str(target.relative_to(out)), image_sha256=digest(target),
                      label=str(label.relative_to(out)), label_sha256=digest(label), boxes=len(live),
                      reference_txt=matches, resolution=resolution, glass=glass_state, pixel_delta_vs_clean=delta,
                      master_sha256=job['master_sha256'], source_sha256=job['source_sha256'], blender=bpy.app.version_string,
                      bvt_build=BUILD, geometry_unchanged=True)
        write_json(condition_root/'metadata'/f'scene_{sid}.json', record)
        records.append(record)
        assert_inputs(job)
        print(f'{sid} {condition["id"]}: PASS | boxes={len(live)} | delta={delta}', flush=True)
    if len({r['label_sha256'] for r in records}) != 1:
        raise RuntimeError('Paired labels differ')
    write_json(out/'jobs'/f'{sid}.result.json', dict(status='PASS', records=records))


def main():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', default=str(REPO)); p.add_argument('--root', default=str(ROOT))
    p.add_argument('--ids', nargs='+', type=int, default=[1,6]); p.add_argument('--run-id', default='pilot_001_smoke')
    p.add_argument('--blender'); p.add_argument('--execute', action='store_true'); p.add_argument('--dry-run', action='store_true')
    p.add_argument('--matrix', type=Path, help='JSON experimental matrix (default: built-in smoke conditions)')
    p.add_argument('--worker-job', help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.worker_job:
        worker(json.loads(Path(args.worker_job).read_text(encoding='utf-8')))
        return 0
    if args.execute and args.dry_run:
        p.error('Choose --execute OR --dry-run')
    repo, root = Path(args.repo).resolve(), Path(args.root).resolve()
    conditions, seed, matrix_raw = load_matrix(args.matrix) if args.matrix else (CONDITIONS, SEED, None)
    out, jobs = plan(repo, root, args.ids, args.run_id, conditions, seed)
    print(f'Run: {out}\nScenes: {[j["id"] for j in jobs]}\nConditions: {[c["id"] for c in conditions]}\nExpected PNG: {len(jobs)*len(conditions)}', flush=True)
    if not args.execute:
        print('DRY RUN: no files written'); return 0
    blender = find_blender(args.blender)
    # Create the run only after inputs and Blender executable are validated.
    out.mkdir(parents=True, exist_ok=False)
    (out/'jobs').mkdir(); (out/'logs').mkdir()
    for c in conditions:
        for sub in ('images','labels','metadata'):
            (out/c['id']/sub).mkdir(parents=True)
    try:
        commit = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'], text=True).strip()
        git_status = subprocess.check_output(['git','--no-optional-locks','-C',str(repo),'status','--porcelain'], text=True).splitlines()
    except (OSError, subprocess.CalledProcessError):
        commit, git_status = None, None
    matrix_sha256 = None
    if matrix_raw is not None:
        (out/'matrix.json').write_bytes(matrix_raw)
        matrix_sha256 = hashlib.sha256(matrix_raw).hexdigest()
    write_json(out/'run_plan.json', dict(jobs=jobs, git_commit=commit, git_status=git_status,
                                       runner_sha256=digest(__file__), matrix_sha256=matrix_sha256))
    summary = []
    for job in jobs:
        sid = job['id']; jobfile = out/'jobs'/f'{sid}.json'; logfile = out/'logs'/f'{sid}.log'
        write_json(jobfile, job)
        cmd = [blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).resolve()),'--','--worker-job',str(jobfile)]
        print(f'--- Rendering scene {sid} ---', flush=True)
        try:
            with logfile.open('wb') as log:
                proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            result_path = out/'jobs'/f'{sid}.result.json'
            if proc.returncode or not result_path.is_file():
                raise RuntimeError(f'Blender exit={proc.returncode}; see {logfile}')
            result = json.loads(result_path.read_text(encoding='utf-8'))
            assert_inputs(job)
            if result['status'] != 'PASS' or len(result['records']) != len(job['conditions']):
                raise RuntimeError('Incomplete scene result')
            summary.append(dict(id=sid, status='PASS', records=result['records']))
            print(f'{sid}: PASS | {len(result["records"])} renders', flush=True)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            summary.append(dict(id=sid,status='FAIL',error=str(exc),log=str(logfile)))
            print(f'{sid}: FAIL | {exc}', flush=True)
    success = sum(x['status']=='PASS' for x in summary)
    write_json(out/'run_summary.json', dict(status='PASS' if success==len(jobs) else 'FAIL', passed=success, total=len(jobs), scenes=summary))
    print(f'PASS={success} FAIL={len(jobs)-success}\nReport: {out / "run_summary.json"}', flush=True)
    return 0 if success==len(jobs) else 1


if __name__ == '__main__':
    sys.exit(main())
