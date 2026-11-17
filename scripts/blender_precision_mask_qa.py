"""Real pixel QA for alpha.4-step4 packed PNG glass masks.

Examples (Git Bash from repository root):
  "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
    --background --factory-startup --python-exit-code 1 \
    --python scripts/blender_precision_mask_qa.py -- \
    --photo 'C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png' \
    --output 'D:/BVT-Studio/qa_renders/precision_step4' --save-blend

Uses four *independent*, deliberately synthetic PNG masks to test the mechanism.
For real freezer frame fidelity replace them with traced/segmented glass masks.
Never changes YOLO data or an existing Blender project.
"""
import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import numpy as np
import bvt_studio
from bvt_studio.common import get_source, image_from_mesh
from bvt_studio.glass import scene_glass, fit_glass_to_source_uv_rect
from bvt_studio.glass_mask import load_mask_for_glass, mask_image_for
from bvt_studio.precision_mask_qa import leakage_metrics, control_metrics


def check(ok, message):
    if not ok:
        raise AssertionError(message)


def load_rgb(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        width, height = tuple(image.size)
        buff = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(buff)
        return buff.reshape(height, width, 4)[:, :, :3].copy()
    finally:
        bpy.data.images.remove(image)


def render_to(path, scene):
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    check(path.exists() and path.stat().st_size > 200, f'Missing render: {path}')
    return load_rgb(path)


def make_test_mask(path, idx, size=256):
    """Diagnostic mask: white glass + black exclusion + gray feather band."""
    y, x = np.mgrid[0:size, 0:size]
    u = (x + .5) / size
    v = (y + .5) / size
    # Different positions ensure the four Glass objects never share a mask.
    center_x = (.42, .56, .47, .53)[idx]
    center_y = (.38, .61, .53, .44)[idx]
    distance = np.sqrt(((u - center_x) / .14)**2 + ((v - center_y) / .16)**2)
    mask = np.ones((size, size), dtype=np.float32)
    mask[distance < .75] = 0.0
    edge = (distance >= .75) & (distance < 1.05)
    mask[edge] = np.clip((distance[edge] - .75) / .30, 0, 1)
    # Explicit mid-gray stripe exercises partial (not binary) masking.
    gray = (u >= .73) & (u <= .84) & (v >= .22) & (v <= .80)
    mask[gray] = .50
    rgba = np.stack((mask, mask, mask, np.ones_like(mask)), axis=-1)
    image = bpy.data.images.new('BVT_QA_Mask_Temp_' + str(idx), width=size,
                                height=size, alpha=True)
    try:
        image.pixels.foreach_set(rgba.ravel())
        image.file_format = 'PNG'
        image.filepath_raw = str(path)
        image.save()
    finally:
        bpy.data.images.remove(image)


def mask_render(scene, glasses, names, output, source):
    """Render the *actual shader mask node* as grayscale to black background.

    All temporary material/world/view changes are restored in finally.
    Avoids inventing a second CPU-side spatial mapping inconsistent with UV.
    """
    originals = {obj: obj.active_material for obj in glasses}
    visibility = {obj: obj.hide_render for obj in scene.objects}
    old_world = scene.world
    world = bpy.data.worlds.new('BVT_QA_Mask_Black_World')
    world.use_nodes = True
    world.node_tree.nodes.get('Background').inputs['Color'].default_value = (0, 0, 0, 1)
    world.node_tree.nodes.get('Background').inputs['Strength'].default_value = 1.0
    copies = []
    try:
        scene.world = world
        for obj in scene.objects:
            obj.hide_render = obj not in glasses and obj is not scene.camera
        for obj in glasses:
            mat = obj.active_material.copy()
            copies.append(mat)
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            factor = nodes.get('BVT_Precision_QA_Mask')
            check(factor is not None, f'{obj.name}: shader mask socket missing')
            output_node = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
            emission = nodes.new('ShaderNodeEmission')
            emission.name = 'BVT_QA_Mask_Emission'
            links.new(factor.outputs[0], emission.inputs['Color'])
            links.new(emission.outputs[0], output_node.inputs['Surface'])
            obj.active_material = mat
        results = {}
        for name, active in names:
            for obj in glasses:
                obj.hide_render = active is not None and obj is not active
            results[name] = render_to(output / name, scene)
        return results
    finally:
        scene.world = old_world
        for obj, mat in originals.items():
            obj.active_material = mat
        for obj, state in visibility.items():
            obj.hide_render = state
        for mat in copies:
            bpy.data.materials.remove(mat)
        bpy.data.worlds.remove(world)


parser = argparse.ArgumentParser()
parser.add_argument('--photo', required=True, help='Real source PNG/JPG')
parser.add_argument('--output', default=str(ROOT / 'qa_renders' / 'precision_step4'))
parser.add_argument('--leakage-limit', type=float, default=.0005)
parser.add_argument('--save-blend', action='store_true', help='Write a NEW QA blend to output directory')
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
opts = parser.parse_args(args)
check(0 <= opts.leakage_limit <= 0.1, 'Invalid leakage limit')
photo = Path(opts.photo).resolve()
check(photo.is_file(), f'Missing source photo: {photo}')
out = Path(opts.output).resolve()
out.mkdir(parents=True, exist_ok=True)
if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()
check(bpy.app.version >= (5, 2, 0), 'Requires Blender 5.2+')
check(bpy.ops.bvt_studio.load_photo(filepath=str(photo)) == {'FINISHED'}, 'Photo import failed')
scene = bpy.context.scene
source = get_source(scene)
check(source is not None, 'Missing source object')
source.rotation_euler.x = math.radians(8)
bpy.context.view_layer.update()
check(bpy.ops.bvt_studio.fit_camera() == {'FINISHED'}, 'Camera fitting failed')
scene.render.engine = 'BLENDER_EEVEE'
source_image = image_from_mesh(source)
check(source_image is not None and min(source_image.size) > 0, 'Image invalid')
width, height = tuple(source_image.size)
scene.render.resolution_x = width
scene.render.resolution_y = height
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.film_transparent = False
scene.view_settings.view_transform = 'Standard'
source_rgb = render_to(out / '00_source.png', scene)

# Same UV defaults as step3: approximations, not claimed exact frame segmentation.
section_rects = ((.060, .120, .305, .840),
                 (.315, .120, .522, .840),
                 (.535, .120, .725, .840),
                 (.744, .120, .940, .840))
for _ in range(4):
    check(bpy.ops.bvt_studio.add_glass() == {'FINISHED'}, 'Cannot create Glass Plane')
glasses = scene_glass(scene)
check(len(glasses) == 4, 'Expected exactly four test glass surfaces')
for idx, (obj, rect) in enumerate(zip(glasses, section_rects)):
    fit_glass_to_source_uv_rect(obj, source, *rect)
    obj['bvt_artifact_mask_inset'] = .018
    obj['bvt_artifact_mask_feather'] = .018
    obj['bvt_artifact_aperture_left'] = .02
    obj['bvt_artifact_aperture_right'] = .98
    obj['bvt_artifact_aperture_bottom'] = .02
    obj['bvt_artifact_aperture_top'] = .98
    obj['bvt_artifact_aperture_feather'] = .015
    mask_file = out / f'input_glass_mask_{idx+1:03d}.png'
    make_test_mask(mask_file, idx)
    image = load_mask_for_glass(obj, str(mask_file))
    check(image.packed_file is not None and image.name == obj['bvt_glass_mask_image'],
          'Mask was not packed/stored on its Glass object')
check(len(set(obj['bvt_glass_mask_image'] for obj in glasses)) == 4,
      'Masks are not independent')

settings = scene.bvt_studio
settings.artifact_intensity = 1.0
settings.artifact_coverage = .68
settings.artifact_droplet_scale = 1.15
settings.artifact_refraction = .024
settings.artifact_relief = .95
settings.hybrid_wetness = .70
settings.hybrid_macro = .72
settings.hybrid_micro = .70
settings.artifact_mask_inset = .018
settings.artifact_mask_feather = .018
settings.artifact_aperture_left = .02
settings.artifact_aperture_right = .98
settings.artifact_aperture_bottom = .02
settings.artifact_aperture_top = .98
settings.artifact_aperture_feather = .015


def apply_all(preset, seed):
    settings.artifact_preset = preset
    for index, obj in enumerate(glasses):
        settings.artifact_target_glass = obj
        settings.artifact_seed = seed + index
        check(bpy.ops.bvt_studio.apply_glass_preset() == {'FINISHED'},
              f'Preset {preset} failed for {obj.name}')


apply_all('QA_TRANSPARENT', 72)
control = render_to(out / '01_control_transparent.png', scene)
control_check = control_metrics(source_rgb, control)
check(control_check['max_rgb_delta'] <= 2 / 255,
      f'QA transparent is not clean: {control_check}')
apply_all('LIGHT_CONDENSATION', 72)
render_to(out / '02_hybrid_light.png', scene)
apply_all('HEAVY_CONDENSATION', 72)
heavy = render_to(out / '03_hybrid_heavy.png', scene)

# True grayscale mask debug from the same material socket as the shader gate.
mask_names = [('06_mask_debug.png', None)] + [
    (f'mask_glass_{i+1:03d}.png', obj) for i, obj in enumerate(glasses)
]
mask_renderings = mask_render(scene, glasses, mask_names, out, source)
union_allowed = mask_renderings['06_mask_debug.png'][:, :, 0]
# Compare QA-transparent control to every effect; mask gray is permitted.
report = {'stage': 'v0.4.0-alpha.4-step4', 'blender': bpy.app.version_string,
          'source': str(photo), 'resolution': [width, height],
          'source_vs_control': control_check, 'section_rects': section_rects,
          'leakage_limit': opts.leakage_limit, 'packed_masks': [], 'qa': {}}
report['qa']['all_four'] = leakage_metrics(control, heavy, union_allowed)
check(report['qa']['all_four']['leakage_ratio'] <= opts.leakage_limit,
      f'Full-frame PNG mask leakage: {report["qa"]["all_four"]}')

for i, obj in enumerate(glasses):
    image_name = obj['bvt_glass_mask_image']
    report['packed_masks'].append({'glass': obj.name, 'image': image_name,
                                   'image_packed': bool(mask_image_for(obj).packed_file),
                                   'source_path': obj['bvt_glass_mask_path'],
                                   'seed': int(obj.get('bvt_artifact_seed', -1))})
    # Only one Glass effect at a time. Rendering other panes with QA_TRANSPARENT
    # avoids hiding geometry or changing the source material.
    originals = {other: other.hide_render for other in glasses}
    try:
        for other in glasses:
            other.hide_render = other is not obj
        isolated = render_to(out / f'07_isolated_glass_{i+1:03d}.png', scene)
    finally:
        for other, state in originals.items():
            other.hide_render = state
    mask = mask_renderings[f'mask_glass_{i+1:03d}.png'][:, :, 0]
    stats = leakage_metrics(control, isolated, mask)
    report['qa'][obj.name] = stats
    check(stats['leakage_ratio'] <= opts.leakage_limit,
          f'{obj.name} leakage: {stats}')

# Seed variation must be visible, and other Glass materials/masks stay independent.
unique_before = tuple(obj['bvt_glass_mask_image'] for obj in glasses)
apply_all('HEAVY_CONDENSATION', 73)
seed_change = render_to(out / '04_hybrid_heavy_seed73.png', scene)
check(float(np.mean(np.abs(heavy - seed_change))) > 1e-5,
      'Seed changes did not affect rendered pixels')
check(tuple(obj['bvt_glass_mask_image'] for obj in glasses) == unique_before,
      'Seed changed image-mask references')

if opts.save_blend:
    # The four uploaded mask images are already packed. Pack the source image
    # as well to allow moving the generated QA .blend to another machine.
    source_image.pack()
    target = out / 'precision_mask_qa.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    check(target.is_file(), 'QA .blend save failed')
    report['saved_blend'] = str(target)

report_file = out / 'precision_qa_report.json'
report_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
print('BVT PRECISION MASK QA: OK — control, grayscale PNG masks, four isolated panes, leakage')
print('PRECISION_QA_DIR=' + str(out))
