#!/usr/bin/env python3
"""BVT-Studio alpha.5-step5: create independent .blend master scenes with editable, material-free glass.
Run with normal Python; this launcher starts a fresh Blender process per photo.
No repo edits, annotation export, renders, or overwrites of existing scenes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

ROOT = Path.home() / 'Desktop' / 'YOLO'
REPO = Path(__file__).resolve().parents[1]
SOURCE_REL = Path('data_local/synthetic_chatgpt/clean/images')
BUILD = 'alpha.5-step5'


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _sha_fallback(f)


def _sha_fallback(f):
    h = hashlib.sha256()
    for chunk in iter(lambda: f.read(1024 * 1024), b''):
        h.update(chunk)
    return h.hexdigest()


def find_blender(explicit):
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f'Blender not found: {p}')
        return p.resolve()
    candidates = []
    for root in (os.environ.get('ProgramFiles'), os.environ.get('ProgramW6432'), os.environ.get('LOCALAPPDATA')):
        if root:
            base = Path(root)
            for vendor in (base / 'Blender Foundation', base / 'Programs' / 'Blender Foundation', base / 'Programs'):
                candidates += sorted(vendor.glob('Blender 5.2*/blender.exe'), reverse=True)
    found = shutil.which('blender') or shutil.which('blender.exe')
    if found:
        candidates.append(Path(found))
    for p in candidates:
        if p.is_file():
            return p.resolve()
    raise FileNotFoundError('Specify Blender 5.2 using --blender "C:\\path\\to\\blender.exe"')


def ensure_finished(result, action):
    if 'FINISHED' not in result:
        raise RuntimeError(f'{action}: {result}')


def worker(job_path):
    # Imports here allow the launcher to run under normal Python without bpy.
    import bpy
    job = json.loads(Path(job_path).read_text(encoding='utf-8'))
    repo = Path(job['repo'])
    source_path = Path(job['source'])
    temp = Path(job['temp'])
    if bpy.app.version[:2] != (5, 2):
        raise RuntimeError(f'Expected Blender 5.2.x, found {bpy.app.version_string}')
    if sha256(source_path) != job['source_sha256']:
        raise RuntimeError('Source image changed after preflight')
    sys.path.insert(0, str(repo))
    import bvt_studio
    if Path(bvt_studio.__file__).resolve().parent != (repo / 'bvt_studio').resolve():
        raise RuntimeError(f'Unexpected BVT module: {bvt_studio.__file__}')
    if getattr(bvt_studio, 'BUILD_STAGE', None) != BUILD:
        raise RuntimeError(f'Expected BVT {BUILD}, got {getattr(bvt_studio, "BUILD_STAGE", None)}')
    if not hasattr(bpy.types.Scene, 'bvt_studio'):
        bvt_studio.register()
    from bvt_studio.scene_tools import create_photo_scene, fit_camera_to_source
    from bvt_studio.common import get_source, image_from_mesh, scene_annotations
    from bvt_studio.glass import scene_glass
    from bvt_studio.artifact_config import PROPERTY_BY_CHANNEL
    from bvt_studio.scene_lock import apply_scene_locks

    ctx = bpy.context
    if ctx.window is None:
        raise RuntimeError('Blender has no window context for BVT scene operators')
    old_scenes = list(bpy.data.scenes)
    # Factory startup contains only default data, never the user's existing work.
    image = bpy.data.images.load(str(source_path), check_existing=False)
    scene = create_photo_scene(ctx, image)
    ctx.window.scene = scene
    for old in old_scenes:
        bpy.data.scenes.remove(old)
    scene.name = job['scene_name']
    ctx.view_layer.update()
    fit_camera_to_source(scene)
    ctx.view_layer.update()
    if job['pack_source']:
        image.pack()
        if not image.packed_file:
            raise RuntimeError('Source image packing failed')
    settings = scene.bvt_studio
    settings.glass_edit_enable = True
    # Create independent, registered BVT glass planes through the native operator.
    for _ in range(job['glass_count']):
        ensure_finished(bpy.ops.bvt_studio.add_glass(), 'Add Glass Plane')
    panes = scene_glass(scene)
    if len(panes) != job['glass_count']:
        raise RuntimeError('Incorrect glass count')
    # The native Add Glass operator registers the plane, UVs, UID and depth
    # guards, and creates a temporary service shader. Strip that shader before
    # saving: master scenes contain geometry only, no glass material at all.
    zero_keys = (*PROPERTY_BY_CHANNEL.values(), 'bvt_artifact_coverage',
                 'bvt_artifact_refraction', 'bvt_artifact_relief', 'bvt_hybrid_wetness')
    for pane in panes:
        if not pane.get('bvt_glass_uid'):
            raise RuntimeError(f'{pane.name}: missing glass UID')
        old_materials = {slot.material.name for slot in pane.material_slots if slot.material}
        pane.data.materials.clear()
        for name in old_materials:
            material = bpy.data.materials.get(name)
            if material is not None and material.users == 0 and material.get('bvt_studio_glass'):
                bpy.data.materials.remove(material)
        for key in zero_keys:
            pane[key] = 0.0
        pane['bvt_artifact_preset'] = 'CUSTOM'
        pane['bvt_artifact_seed'] = 0
        # No material means an opaque default surface in material preview.
        # Wire display keeps photo visible for manual positioning; hide_render
        # prevents unconfigured geometry from obscuring the clean render.
        # Native configure_glass sets hide_render=False when a shader is built.
        pane.display_type = 'WIRE'
        pane.show_wire = True
        pane.show_all_edges = True
        pane.hide_render = True
        pane.hide_viewport = False
        pane['bvt_master_glass_review_required'] = True
        if len(pane.material_slots) != 0 or pane.active_material is not None:
            raise RuntimeError(f'{pane.name}: glass material was not removed')
    settings.artifact_target_glass = panes[0]
    settings.artifact_intensity = 0.0
    settings.artifact_coverage = 0.0
    settings.artifact_refraction = 0.0
    settings.artifact_relief = 0.0
    settings.hybrid_wetness = 0.0
    settings.artifact_seed = 0
    # Native group flags: keep photo/camera/light protected, allow glass and
    # annotations. Retain the photo-relative depth guard (in-plane movement).
    settings.scene_locks_enabled = True
    settings.photo_edit_enable = False
    settings.camera_edit_enable = False
    settings.light_edit_enable = False
    settings.glass_edit_enable = True
    settings.annotations_edit_enable = True
    apply_scene_locks(scene)
    ctx.view_layer.update()
    if (not settings.scene_locks_enabled or not settings.glass_edit_enable
            or not settings.annotations_edit_enable or not settings.glass_depth_lock):
        raise RuntimeError('Incorrect BVT lock mode')
    for obj in [get_source(scene), scene.camera]:
        if obj is None or not (obj.hide_select and all(obj.lock_location) and all(obj.lock_rotation) and all(obj.lock_scale)):
            raise RuntimeError('Expected photo/camera protection is missing')
    for pane in panes:
        if (pane.hide_select or any(pane.lock_location) or any(pane.lock_rotation)
                or any(pane.lock_scale) or len(pane.material_slots) != 0
                or not pane.hide_render or pane.display_type != 'WIRE'):
            raise RuntimeError(f'{pane.name}: expected editable material-free glass')
    for obj in list(ctx.selected_objects):
        obj.select_set(False)
    panes[0].select_set(True)
    ctx.view_layer.objects.active = panes[0]
    ctx.view_layer.update()
    if scene_annotations(scene):
        raise RuntimeError('New scene must not contain YOLO labels')
    if scene.camera.data.type != 'ORTHO' or (scene.render.resolution_x, scene.render.resolution_y) != tuple(image.size[:]):
        raise RuntimeError('Camera or source resolution mismatch')
    if image_from_mesh(get_source(scene)) != image:
        raise RuntimeError('Source texture mismatch')
    if len({p['bvt_glass_uid'] for p in panes}) != len(panes):
        raise RuntimeError('Duplicate glass UIDs')
    # Provenance and explicit draft status, not fake annotation/mask approval.
    scene['bvt_master_source_id'] = source_path.stem
    scene['bvt_master_source_sha256'] = job['source_sha256']
    scene['bvt_master_glass_review_required'] = True
    scene['bvt_master_annotation_pending'] = True
    scene['bvt_master_glass_material_pending'] = True
    # Open directly in camera view. Do not change the user's global preferences.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                if space.region_3d:
                    space.region_3d.view_perspective = 'CAMERA'
                space.shading.type = 'MATERIAL'
    # Do not create .blend1 backups, and keep the original image path intact.
    bpy.context.preferences.filepaths.save_version = 0
    ensure_finished(bpy.ops.wm.save_as_mainfile(filepath=str(temp), relative_remap=False, compress=True), 'Save scene')
    if not temp.is_file() or temp.stat().st_size == 0:
        raise RuntimeError('Saved .blend missing or empty')
    print(f'BVT_WORKER_OK {job["scene_name"]}: {len(panes)} editable material-free draft panes, zero labels', flush=True)


def publish_new(temp, target):
    # Windows rename refuses an existing destination. POSIX rename would replace
    # it, so use an atomic exclusive hard link there instead.
    if os.name == 'nt':
        os.rename(temp, target)
    else:
        os.link(temp, target)
        temp.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start', type=int, default=6)
    p.add_argument('--end', type=int, default=100)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--repo', type=Path, default=REPO)
    p.add_argument('--source-dir', type=Path, help='Override synthetic ChatGPT image folder')
    p.add_argument('--blender', help='Explicit path to Blender 5.2 executable')
    p.add_argument('--glass-count', type=int, choices=(1, 2), default=2, help='Initial approximate panes per scene')
    p.add_argument('--no-pack', action='store_true', help='Keep external image instead of packing into each .blend')
    p.add_argument('--dry-run', action='store_true', help='Check paths and print plan; no changes')
    a = p.parse_args()
    if not 6 <= a.start <= a.end <= 100:
        p.error('Range must satisfy 6 <= start <= end <= 100; scenes 0001-0005 are protected')
    root, repo = a.root.resolve(), a.repo.resolve()
    source_dir = (a.source_dir or repo / SOURCE_REL).resolve()
    if not root.is_dir() or not source_dir.is_dir() or not (repo / 'bvt_studio' / '__init__.py').is_file():
        raise FileNotFoundError(f'Check paths: root={root}; source={source_dir}; repo={repo}')
    blender = find_blender(a.blender)
    plan = []
    missing = []
    for i in range(a.start, a.end + 1):
        folder = root / f'{i:04d}'
        target = folder / f'scene_{i:04d}.blend'
        if target.exists():
            print(f'SKIP existing: {target}')
            continue
        # Protect older differently named scenes and backups as well.
        if folder.is_dir() and any(x.is_file() and (x.name.lower().endswith('.blend') or x.name.lower().endswith('.blend1')) for x in folder.iterdir()):
            print(f'SKIP folder with existing Blender file: {folder}')
            continue
        source = source_dir / f'chatgpt_{i:06d}.png'
        if not source.is_file() or source.stat().st_size == 0:
            missing.append(str(source))
        else:
            plan.append((i, source, target))
            print(f'PLAN {source.name} -> {target}')
    if missing:
        raise FileNotFoundError('Missing/empty sources; nothing generated:\n' + '\n'.join(missing))
    print(f'Blender: {blender}\nNew scenes: {len(plan)}; editable material-free glass count: {a.glass_count}; pack: {not a.no_pack}', flush=True)
    if a.dry_run or not plan:
        return 0
    script = Path(__file__).resolve()
    created = 0
    for i, source, target in plan:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            print(f'SKIP existing: {target}')
            continue
        print(f'[{created + 1}/{len(plan)}] Preparing {target.name}', flush=True)
        with tempfile.TemporaryDirectory(prefix='.bvt_build_', dir=target.parent) as tmpdir:
            temp = Path(tmpdir) / target.name
            job_path = Path(tmpdir) / 'job.json'
            job = dict(repo=str(repo), source=str(source), source_sha256=sha256(source),
                       temp=str(temp), scene_name=target.stem, glass_count=a.glass_count,
                       pack_source=not a.no_pack)
            job_path.write_text(json.dumps(job), encoding='utf-8')
            command = [str(blender), '--background', '--factory-startup', '--python-exit-code', '17',
                       '--python', str(script), '--', '--worker', str(job_path)]
            subprocess.run(command, check=True)
            if not temp.is_file() or temp.stat().st_size == 0:
                raise RuntimeError(f'Blender did not save {target.name}')
            publish_new(temp, target)
        created += 1
        print(f'OK {target}', flush=True)
    print(f'COMPLETE: {created} scenes created; no YOLO labels fabricated.')
    return 0


if __name__ == '__main__':
    try:
        if '--' in sys.argv and sys.argv[sys.argv.index('--') + 1:][:1] == ['--worker']:
            worker(sys.argv[sys.argv.index('--') + 2])
        else:
            sys.exit(main())
    except Exception:
        traceback.print_exc()
        raise
