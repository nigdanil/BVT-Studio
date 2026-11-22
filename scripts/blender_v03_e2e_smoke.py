"""BVT Studio v0.3 end-to-end Blender QA — real photo, glass, depth, labels.

Run from repo root with Blender 5.2.3 LTS:
    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
      --background --factory-startup --python scripts/blender_v03_e2e_smoke.py

All data is synthesized inside a temporary directory and removed at exit.
No external images, model weights, ZIP archives or network connections needed.
"""
import json
import math
import struct
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from mathutils import Vector
import bvt_studio
from bvt_studio.common import get_source, scene_annotations
from bvt_studio.depth import DEPTH_CONSTRAINT, _photo_axis
from bvt_studio.glass import scene_glass
from bvt_studio.export_preview import parse_label_text


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def png_size(path):
    with path.open('rb') as f:
        header = f.read(24)
    check(header[:8] == b'\x89PNG\r\n\x1a\n', 'Invalid PNG signature')
    return struct.unpack('>II', header[16:24])


check(bpy.app.version >= (5, 2, 0), 'Requires Blender 5.2+')
if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

old_scene = bpy.context.scene
with tempfile.TemporaryDirectory(prefix='bvt_studio_v03_e2e_') as tmp:
    tmp = Path(tmp)
    photo_path = tmp / 'synthetic_photo.png'
    img = bpy.data.images.new('BVT_Integration_Pixels', width=256, height=160, alpha=True)
    img.pixels[:] = [0.18, 0.30, 0.42, 1.0] * (256 * 160)
    img.filepath_raw = str(photo_path)
    img.file_format = 'PNG'
    img.save()
    check(photo_path.exists(), 'Test input PNG not created')

    # Exercise exactly the button's execute code path: a new non-destructive scene.
    check(bpy.ops.bvt_studio.load_photo(filepath=str(photo_path)) == {'FINISHED'},
          'New Scene from Photo failed')
    scene = bpy.context.scene
    check(scene != old_scene, 'Photo import replaced the old scene')
    source = get_source(scene)
    check(source is not None and source.get('bvt_role') == 'planogram_image',
          'Photo source not registered')
    check(source.hide_select and scene.camera.hide_select,
          'Photo and camera must be protected after import')
    check(scene.bvt_studio.scene_locks_enabled, 'Scene locks not activated')

    # Photo-relative constraints must work when photo is NOT aligned to world XY.
    source.rotation_euler = (math.radians(18), math.radians(-11), 0.0)
    bpy.context.view_layer.update()
    check(bpy.ops.bvt_studio.fit_camera() == {'FINISHED'},
          'Camera framing failed on rotated source')
    scene.render.resolution_x = 256
    scene.render.resolution_y = 160
    scene.render.resolution_percentage = 100
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'

    for _ in range(2):
        check(bpy.ops.bvt_studio.add_glass() == {'FINISHED'}, 'Add Glass failed')
    glasses = scene_glass(scene)
    check(len(glasses) == 2, 'Expected exactly two glass surfaces')
    for obj in glasses:
        check(obj.name.startswith('Glass_p_'), 'Unexpected glass naming')
        check(obj.get('bvt_role') == 'glass_overlay', 'Glass role missing')
        check(obj.active_material is not None, 'Procedural glass material missing')
        check(obj.constraints.get(DEPTH_CONSTRAINT) is not None,
              'Glass missing normal-depth constraint')
    glasses[0]['bvt_glass_haze'] = 0.14

    for _ in range(2):
        check(bpy.ops.bvt_studio.add_annotation() == {'FINISHED'},
              'Add Annotation failed')
    anns = scene_annotations(scene)
    check(len(anns) == 2, 'Expected exactly two annotation objects')
    tangent = (source.matrix_world.to_3x3() @ Vector((1, 0, 0))).normalized()
    anns[0].location -= tangent * 0.42
    anns[1].location += tangent * 0.42
    bpy.context.view_layer.update()
    for obj in anns:
        check(obj.constraints.get(DEPTH_CONSTRAINT) is not None,
              'Annotation missing normal-depth constraint')

    # Assign class 1 through the actual Annotation Manager operator.
    check(bpy.context.view_layer.objects.active == anns[1],
          'Second annotation should be active')
    settings = scene.bvt_studio
    settings.batch_class_id = 1
    settings.batch_class_name = 'popsicle'
    check(bpy.ops.bvt_studio.batch_annotation_class() == {'FINISHED'},
          'Batch class assignment failed')
    check((anns[1].get('bvt_class_id'), anns[1].get('bvt_class_name')) ==
          (1, 'popsicle'), 'Annotation Manager did not update selected object')

    # Annotation Mode must protect everything except annotation rectangles.
    check(bpy.ops.bvt_studio.annotation_lock_mode() == {'FINISHED'},
          'Annotation Mode could not be activated')
    check(source.hide_select and scene.camera.hide_select,
          'Annotation Mode should protect photo and camera')
    check(all(g.hide_select for g in glasses), 'Annotation Mode should lock glass')
    check(all(not obj.hide_select for obj in anns),
          'Annotation Mode unexpectedly locks annotation selection')

    # Depth Offset is an explicit operation even when glass editing is disabled.
    settings.depth_target_glass = glasses[0]
    settings.glass_depth_offset_m = 0.025
    check(bpy.ops.bvt_studio.apply_glass_depth() == {'FINISHED'},
          'Depth Offset failed on a locked glass surface')
    bpy.context.view_layer.update()
    normal, _scale = _photo_axis(source)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = glasses[0].evaluated_get(depsgraph).matrix_world.translation
    actual_depth = (evaluated - source.matrix_world.translation).dot(normal)
    check(abs(actual_depth - 0.025) < 1e-4,
          f'Glass depth mismatch: {actual_depth:.6f} m')

    check(bpy.ops.bvt_studio.validate() == {'FINISHED'},
          'YOLO quality validation failed')
    check(settings.quality_box_count == 2 and settings.quality_error_count == 0,
          f'Quality Gate errors: {[i.message for i in settings.quality_items]}')

    # Force outlines visible in F12 and verify export hides/restores them.
    check(bpy.ops.bvt_studio.toggle_preview() == {'FINISHED'},
          'Could not enable annotation preview')
    before_hidden = {obj.name: obj.hide_render for obj in anns}
    before_render_path = scene.render.filepath
    before_color = scene.render.image_settings.color_mode
    before_format = scene.render.image_settings.file_format
    settings.export_dir = str(tmp / 'dataset')
    check(bpy.ops.bvt_studio.export_yolo() == {'FINISHED'},
          'End-to-end YOLO export failed')

    dataset = tmp / 'dataset'
    image_file = dataset / 'images/train/sample_000001.png'
    labels_file = dataset / 'labels/train/sample_000001.txt'
    svg_file = dataset / 'previews/sample_000001.svg'
    yaml_file = dataset / 'data.yaml'
    manifest_file = dataset / 'sample_000001_manifest.json'
    for p in (image_file, labels_file, svg_file, yaml_file, manifest_file):
        check(p.is_file() and p.stat().st_size > 0, f'Missing export: {p.name}')
    check(png_size(image_file) == (256, 160), 'Rendered PNG size changed')
    labels = parse_label_text(labels_file.read_text(encoding='utf-8'))
    check(len(labels) == 2 and {row[0] for row in labels} == {0, 1},
          f'Unexpected YOLO labels: {labels}')
    check(all(0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1
              for _, x, y, w, h in labels), 'YOLO coordinates invalid')
    yaml = yaml_file.read_text(encoding='utf-8')
    check('path:' not in yaml and 'train: images/train' in yaml and
          'val: images/val' in yaml and 'nc: 2' in yaml,
          'YAML is not portable or class count is wrong')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    check(len(manifest['annotations']) == 2 and len(manifest['glass']) == 2,
          'Manifest lost objects')
    check(manifest['preview'] == 'previews/sample_000001.svg',
          'Manifest preview path incorrect')
    check(settings.last_preview_svg == str(svg_file), 'Preview pointer not saved')
    svg_root = ET.parse(svg_file).getroot()
    ns = '{http://www.w3.org/2000/svg}'
    check(len(svg_root.findall(ns + 'rect')) == 2,
          'SVG preview does not match TXT annotation count')
    check(svg_root.find(ns + 'image').attrib['href'] ==
          '../images/train/sample_000001.png', 'SVG image URL is not portable')
    check(all(obj.hide_render == before_hidden[obj.name] for obj in anns),
          'Exporter did not restore annotation render visibility')
    check(scene.render.filepath == before_render_path and
          scene.render.image_settings.color_mode == before_color and
          scene.render.image_settings.file_format == before_format,
          'Exporter did not restore render settings')
    check(source.hide_select and all(g.hide_select for g in glasses),
          'Export unexpectedly unlocked protected scene objects')

    print('BVT V0.3 E2E SMOKE: OK — photo, locks, tilted depth, glass, '
          'annotation, quality gate, clean PNG, YOLO TXT, SVG, manifest')
