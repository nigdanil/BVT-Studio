#!/usr/bin/env python3
"""Read-only BVT-Studio pilot master scene audit. Run with normal Python.
No scene, label, repository or image files are written or updated.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

sys.dont_write_bytecode = True

ROOT = Path.home() / 'Desktop' / 'YOLO'
REPO = Path(__file__).resolve().parents[1]
PREFIX = 'BVT_PILOT_QA_JSON='


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def find_blender(explicit):
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p.resolve())
        raise FileNotFoundError(p)
    for env in ('ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA'):
        if os.environ.get(env):
            root = Path(os.environ[env])
            for base in (root / 'Blender Foundation', root / 'Programs' / 'Blender Foundation', root / 'Programs'):
                for p in sorted(base.glob('Blender 5.2*/blender.exe'), reverse=True):
                    if p.is_file():
                        return str(p.resolve())
    exe = shutil.which('blender') or shutil.which('blender.exe')
    if exe:
        return exe
    raise FileNotFoundError('Use --blender with the full path to blender.exe')


def emit(result):
    print(PREFIX + json.dumps(result, ensure_ascii=True, sort_keys=True), flush=True)



def same_rows(a, b):
    # Match as multisets, independent of export ordering. 7-decimal export.
    remaining = list(b)
    if len(a) != len(remaining):
        return False
    for row in a:
        hit = next((i for i, other in enumerate(remaining)
                    if row[0] == other[0] and all(abs(x-y) <= 1e-6 for x,y in zip(row[1:], other[1:]))), None)
        if hit is None:
            return False
        remaining.pop(hit)
    return not remaining


def worker(args):
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    p = Path(args.master)
    result = dict(id=p.parent.name, master=str(p), errors=[], warnings=[])
    errors, warnings = result['errors'], result['warnings']
    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))
    import bvt_studio
    if Path(bvt_studio.__file__).resolve().parent != repo / 'bvt_studio':
        raise RuntimeError('Unexpected BVT-Studio module path')
    if bpy.app.version[:2] != (5, 2):
        raise RuntimeError('Expected Blender 5.2.x; got ' + bpy.app.version_string)
    result['blender'] = bpy.app.version_string
    result['bvt_build'] = getattr(bvt_studio, 'BUILD_STAGE', 'unknown')
    if not hasattr(bpy.types.Scene, 'bvt_studio'):
        bvt_studio.register()
    from bvt_studio.common import get_source, image_from_mesh, scene_annotations
    from bvt_studio.glass import scene_glass
    from bvt_studio.annotation import collect_boxes
    from bvt_studio.validation import quality_report
    from bvt_studio.export_preview import parse_label_text, label_text
    # Register RNA before opening the file. Never save or run embedded scripts.
    before = digest(p)
    bpy.ops.wm.open_mainfile(filepath=str(p), load_ui=False, use_scripts=False)
    candidates = [s for s in bpy.data.scenes if get_source(s) is not None and scene_annotations(s)]
    if len(candidates) != 1:
        raise RuntimeError(f'Expected one annotated BVT scene, found {len(candidates)}')
    scene = candidates[0]
    if bpy.context.window is None:
        raise RuntimeError('No Blender window context for evaluated scene')
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()
    result['scene'] = scene.name
    source = get_source(scene)
    image = image_from_mesh(source)
    expected = Path(args.repo) / 'data_local' / 'synthetic_chatgpt' / 'clean' / 'images' / f'chatgpt_{int(p.parent.name):06d}.png'
    result['expected_source'] = str(expected)
    if not expected.is_file():
        errors.append('Expected canonical source is missing')
    else:
        result['source_sha256'] = digest(expected)
    if image is None:
        errors.append('Source image texture is missing')
    else:
        path = Path(bpy.path.abspath(image.filepath, library=image.library))
        packed = image.packed_file
        result['source_path'] = str(path)
        result['source_packed'] = bool(packed)
        if packed:
            if expected.is_file() and hashlib.sha256(bytes(packed.data)).hexdigest() != result['source_sha256']:
                errors.append('Packed source SHA-256 differs from canonical image')
        elif not path.is_file():
            errors.append('External source texture not found')
        elif expected.is_file() and digest(path) != result['source_sha256']:
            errors.append('External source SHA-256 differs from canonical image')
        result['source_size'] = list(image.size[:])
        if min(result['source_size']) <= 0:
            errors.append('Source image has invalid dimensions')
    width = round(scene.render.resolution_x * scene.render.resolution_percentage / 100)
    height = round(scene.render.resolution_y * scene.render.resolution_percentage / 100)
    result['render_size'] = [width, height]
    if image is not None and list(image.size[:]) != [width, height]:
        errors.append('Render size differs from source size')
    cam = scene.camera
    if cam is None or cam.type != 'CAMERA' or cam.data.type != 'ORTHO':
        errors.append('Expected orthographic camera')
    if scene.render.use_border:
        errors.append('Render border is enabled')
    s = scene.bvt_studio
    if not s.scene_locks_enabled or s.photo_edit_enable or s.camera_edit_enable:
        warnings.append('Photo/camera scene-lock settings are not protected')
    for obj in (source, cam):
        if obj is not None and not (obj.hide_select and all(obj.lock_location) and all(obj.lock_rotation) and all(obj.lock_scale)):
            warnings.append(f'{obj.name}: transform/selection lock incomplete')
    if s.glass_edit_enable:
        warnings.append('Glass Edit is enabled; lock after manual alignment')
    panes = scene_glass(scene)
    result['glass'] = []
    if not panes:
        errors.append('No BVT glass surfaces')
    glass_uids = [str(o.get('bvt_glass_uid', '')) for o in panes]
    if not all(glass_uids) or len(set(glass_uids)) != len(glass_uids):
        errors.append('Missing or duplicate glass UID')
    dg = bpy.context.evaluated_depsgraph_get()
    keys = ('bvt_glass_reflection','bvt_glass_tint','bvt_glass_haze','bvt_glass_frost','bvt_glass_droplets','bvt_glass_dirt','bvt_artifact_coverage')
    for o in panes:
        materials = [slot.material.name for slot in o.material_slots if slot.material]
        values = {k: float(o.get(k, 0.0)) for k in keys}
        item = dict(name=o.name, uid=str(o.get('bvt_glass_uid','')), materials=materials,
                    hide_render=bool(o.hide_render), channels=values, preset=str(o.get('bvt_artifact_preset','')))
        result['glass'].append(item)
        if len(o.data.vertices) < 3 or not o.data.polygons:
            errors.append(f'{o.name}: invalid mesh')
        if not all(math.isfinite(x) for x in values.values()):
            errors.append(f'{o.name}: non-finite artifact settings')
        elif any(abs(x)>1e-8 for x in values.values()):
            warnings.append(f'{o.name}: nonzero saved artifact channels; runner must reset')
        if materials:
            warnings.append(f'{o.name}: existing material; inspect/reset for clean experiment')
        elif not o.hide_render:
            warnings.append(f'{o.name}: no material and visible in render; clean runner must hide or use transparent control')
        if cam and cam.type == 'CAMERA' and o.data.vertices:
            matrix = o.evaluated_get(dg).matrix_world
            coords = [world_to_camera_view(scene, cam, matrix @ v.co) for v in o.data.vertices]
            if any(v.z <= 0 or not all(math.isfinite(x) for x in v) for v in coords):
                errors.append(f'{o.name}: invalid camera projection')
            else:
                bounds = [min(v.x for v in coords), min(v.y for v in coords), max(v.x for v in coords), max(v.y for v in coords)]
                item['camera_bounds'] = bounds
                if bounds[2]-bounds[0] <= 1e-6 or bounds[3]-bounds[1] <= 1e-6:
                    errors.append(f'{o.name}: degenerate projected glass')
                if bounds[2] <= 0 or bounds[0] >= 1 or bounds[3] <= 0 or bounds[1] >= 1:
                    errors.append(f'{o.name}: glass entirely outside image')
                elif min(bounds[:2]) < -1e-5 or max(bounds[2:]) > 1.00001:
                    warnings.append(f'{o.name}: glass partially outside frame; review')
    boxes, issues, classes = collect_boxes(scene)
    errors.extend(issues)
    result['classes'] = classes
    result['boxes'] = len(boxes)
    if classes != {0:'ice_cream'}:
        errors.append('Expected pilot class map {0: ice_cream}')
    if any(not all(math.isfinite(float(b[k])) for k in ('x','y','w','h')) for b in boxes):
        errors.append('Non-finite YOLO coordinates')
    if len({b['uid'] for b in boxes}) != len(boxes):
        errors.append('Duplicate annotation UIDs')
    report = quality_report(boxes, issues, {o.name:o for o in scene_annotations(scene)}, width, height)
    warnings.extend(i['message'] for i in report['issues'] if i['severity'] == 'WARNING')
    live = parse_label_text(label_text(boxes))
    labels = sorted(p.parent.glob('labels/train/*.txt')) + sorted(p.parent.glob('labels/val/*.txt'))
    matches = []
    for label in labels:
        try:
            if same_rows(live, parse_label_text(label.read_text(encoding='utf-8-sig'))):
                matches.append(str(label))
        except (OSError, ValueError) as exc:
            warnings.append(f'{label.name}: {exc}')
    result['matching_yolo_exports'] = matches
    result['yolo_export_count'] = len(labels)
    if not labels:
        warnings.append('No exported TXT; scene geometry is the current reference')
    elif not matches:
        errors.append('None of the saved YOLO TXT files matches current scene geometry')
    elif len(matches) != len(labels):
        warnings.append('Some older exports differ; select matching reference, not arbitrary latest filename')
    result['master_sha256'] = before
    if digest(p) != before:
        errors.append('Master file changed during audit')
    result['status'] = 'FAIL' if errors else ('REVIEW' if warnings else 'PASS')
    emit(result)


def main():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--repo', default=str(REPO))
    parser.add_argument('--blender')
    parser.add_argument('--start', type=int, default=1)
    parser.add_argument('--end', type=int, default=10)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--master', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        try:
            worker(args)
        except Exception as exc:
            traceback.print_exc()
            emit(dict(id=Path(args.master).parent.name, status='FAIL', errors=[str(exc)], warnings=[]))
        return 0
    if not 1 <= args.start <= args.end <= 100:
        parser.error('Range must be within 1..100')
    blender = find_blender(args.blender)
    repo = Path(args.repo).resolve()
    if not (repo/'bvt_studio'/'__init__.py').is_file():
        raise FileNotFoundError(f'BVT-Studio package not found: {repo}')
    results = []
    for i in range(args.start, args.end+1):
        folder = Path(args.root) / f'{i:04d}'
        master = folder / f'scene_{i:04d}.blend'
        if not master.is_file():
            # Older scenes may use 0002.blend. Only accept an unambiguous exact alias.
            alias = folder / f'{i:04d}.blend'
            if alias.is_file():
                master = alias
            else:
                r = dict(id=f'{i:04d}', status='FAIL', errors=[f'Missing master: {master}'], warnings=[])
                results.append(r)
                print(f'{r["id"]}: FAIL {r["errors"][0]}', flush=True)
                continue
        print(f'--- Auditing {master} ---', flush=True)
        cmd = [blender, '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1', '--python', str(Path(__file__).resolve()), '--', '--worker', '--repo', str(repo), '--master', str(master.resolve())]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=180)
            records = [line[len(PREFIX):] for line in proc.stdout.splitlines() if line.startswith(PREFIX)]
            if proc.returncode or len(records)!=1:
                raise RuntimeError(f'Blender exit={proc.returncode}; result records={len(records)}; output: {proc.stdout[-4000:]}')
            r = json.loads(records[0])
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            r = dict(id=f'{i:04d}', status='FAIL', errors=[str(exc)], warnings=[])
        results.append(r)
        print(f'{r["id"]}: {r["status"]} | boxes={r.get("boxes", "?")} | glass={len(r.get("glass", []))} | matching TXT={len(r.get("matching_yolo_exports", []))}', flush=True)
        for k in ('errors','warnings'):
            for msg in r.get(k, []):
                print(f'  {k.upper()}: {msg}', flush=True)
    counts = {s:sum(r['status']==s for r in results) for s in ('PASS','REVIEW','FAIL')}
    print('\n=== PILOT MASTER QA SUMMARY ===')
    print(json.dumps(dict(counts=counts, total_boxes=sum(r.get('boxes',0) for r in results), scenes=results), indent=2, ensure_ascii=True))
    print(f'PASS={counts["PASS"]} REVIEW={counts["REVIEW"]} FAIL={counts["FAIL"]}')
    print('Visual alignment/annotation correctness and clean render remain manual/next-stage checks.')
    return 1 if counts['FAIL'] else (2 if counts['REVIEW'] else 0)


if __name__ == '__main__':
    sys.exit(main())
