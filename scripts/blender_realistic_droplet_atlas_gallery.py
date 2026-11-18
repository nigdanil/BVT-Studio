"""Blender 5.2+ visual smoke for multi-scale generated realistic droplet atlases.

This script compares procedural, imported synthetic photo maps and atlas modes,
seed, per-glass independence, PNG precision mask and save/open persistence.
It generates synthetic test textures; no real photographic maps are provided.
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
from bvt_studio.common import get_source
from bvt_studio.glass import scene_glass, fit_glass_to_source_uv_rect
from bvt_studio.droplet_maps import (import_droplet_maps, packed_maps_for,
                                     set_droplet_mode, MODE_KEY)
from bvt_studio.glass_mask import load_mask_for_glass
from bvt_studio.realistic_atlas import generate_realistic_atlas


def check(ok, message):
    if not ok:
        raise AssertionError(message)


argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--photo', default=None)
parser.add_argument('--output', default=str(ROOT / 'qa_renders' / 'realistic_droplets_step2'))
parser.add_argument('--save-blend', action='store_true')
options = parser.parse_args(argv)
out = Path(options.output).resolve()
out.mkdir(parents=True, exist_ok=True)

if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()


def save_test_png(path, rgb):
    h, w, _ = rgb.shape
    pixels = np.empty((h, w, 4), dtype=np.float32)
    pixels[:, :, :3] = np.clip(rgb, 0, 1)
    pixels[:, :, 3] = 1.
    img = bpy.data.images.new(path.stem, width=w, height=h, alpha=True)
    img.pixels.foreach_set(pixels.ravel())
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


# A repeatable synthetic spherical droplet pattern, not a photographic atlas.
yy, xx = np.mgrid[0:256, 0:256]
height = np.zeros((256, 256), dtype=np.float32)
for cx, cy, radius in ((44, 50, 22), (120, 135, 39), (203, 68, 26),
                       (67, 208, 18), (207, 209, 35), (151, 32, 11)):
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / radius ** 2
    height = np.maximum(height, np.sqrt(np.maximum(1. - d2, 0.)))
alpha = np.clip(height * 1.4, 0., 1.)
grad_y, grad_x = np.gradient(height)
normal = np.empty((256, 256, 3), dtype=np.float32)
normal[:, :, 0] = .5 + np.clip(grad_x * 1.6, -.5, .5)
normal[:, :, 1] = .5 + np.clip(grad_y * 1.6, -.5, .5)
normal[:, :, 2] = 1.
paths = {}
for kind, image in [('alpha', np.repeat(alpha[:, :, None], 3, 2)),
                    ('height', np.repeat(height[:, :, None], 3, 2)),
                    ('normal', normal)]:
    path = out / ('test_' + kind + '.png')
    save_test_png(path, image)
    paths[kind] = path

if options.photo:
    source_photo = Path(options.photo).resolve()
    check(source_photo.is_file(), f'Photo not found: {source_photo}')
else:
    source_photo = out / 'test_source.png'
    w, h = 480, 270
    y, x = np.mgrid[0:h, 0:w]
    rgb = np.stack((np.where((x // 28) % 2 == 0, .22, .82) * np.ones_like(y),
                    np.where((y // 32) % 2 == 0, .25, .75) * np.ones_like(x),
                    .2 + .6 * x / w), axis=-1).astype(np.float32)
    save_test_png(source_photo, rgb)

check(bpy.ops.bvt_studio.load_photo(filepath=str(source_photo)) == {'FINISHED'}, 'Import failed')
scene = bpy.context.scene
source = get_source(scene)
source.rotation_euler.x = math.radians(8.)
bpy.context.view_layer.update()
check(bpy.ops.bvt_studio.fit_camera() == {'FINISHED'}, 'Camera fitting failed')
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.view_settings.view_transform = 'Standard'
scene.render.film_transparent = False


def render(name):
    target = out / name
    scene.render.filepath = str(target)
    bpy.ops.render.render(write_still=True)
    check(target.is_file() and target.stat().st_size > 300, 'Render missing: ' + name)
    image = bpy.data.images.load(str(target), check_existing=False)
    try:
        data = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(data)
        return data.reshape((image.size[1], image.size[0], 4))[:, :, :3].copy()
    finally:
        bpy.data.images.remove(image)


def diff(a, b):
    return float(np.mean(np.abs(a - b)))


original = render('00_source.png')
check(bpy.ops.bvt_studio.add_glass() == {'FINISHED'}, 'Add first glass failed')
check(bpy.ops.bvt_studio.add_glass() == {'FINISHED'}, 'Add second glass failed')
first, second = scene_glass(scene)[:2]
fit_glass_to_source_uv_rect(first, source, .07, .12, .49, .85)
fit_glass_to_source_uv_rect(second, source, .53, .12, .95, .85)
mat_second = second.active_material
before = first.matrix_world.copy()
settings = scene.bvt_studio
settings.artifact_target_glass = first
settings.artifact_coverage = .75
settings.artifact_intensity = 1.
settings.artifact_refraction = .024
settings.artifact_relief = .95
settings.artifact_preset = 'HEAVY_CONDENSATION'
settings.artifact_seed = 72
check(bpy.ops.bvt_studio.apply_glass_preset() == {'FINISHED'}, 'Procedural preset failed')
procedural = render('01_procedural.png')
check(first.get(MODE_KEY, 'PROCEDURAL') == 'PROCEDURAL', 'Unexpected source mode')

import_droplet_maps(first, paths['alpha'], paths['height'], paths['normal'], tiling=1.8,
                    rotation=18.0)
photos = packed_maps_for(first)
check(all(image.packed_file for image in photos.values()), 'Unpacked map')
check(first.get(MODE_KEY) == 'PHOTO_MAPS', 'Photo map mode did not activate')
check(first.active_material.node_tree.nodes.get('BVT_Photo_Droplet_Normal') is not None,
      'Normal sampler not present')
check(first.active_material.node_tree.nodes.get('BVT_Precision_Final_Mask_Gate') is not None,
      'Final precision gate is missing')
photo = render('02_photo_maps.png')
# Import the same first glass as an independent synthetic atlas mode.
photo_names = {kind: image.name for kind, image in photos.items()}
generate_realistic_atlas(first, seed=72, resolution=512, density=1.15, streaks=.65,
                         tiling=1.45, rotation=0., preview_dir=out)
atlas = packed_maps_for(first, mode='REALISTIC_ATLAS')
check(first.get(MODE_KEY) == 'REALISTIC_ATLAS', 'Generated mode not active')
check({kind: image.name for kind, image in packed_maps_for(first, mode='PHOTO_MAPS').items()}
      == photo_names, 'User-imported Photo Maps were overwritten')
check(all(image.packed_file for image in atlas.values()), 'Atlas image not packed')
realistic = render('03_realistic_atlas.png')
first['bvt_artifact_seed'] = 73
from bvt_studio.glass import configure_glass
configure_glass(first)
seed73 = render('04_atlas_seed73.png')
first['bvt_artifact_seed'] = 72
configure_glass(first)

mask = np.zeros((256, 256, 3), dtype=np.float32)
mask[28:227, 28:227] = 1.0
mask_path = out / 'test_precision_mask.png'
save_test_png(mask_path, mask)
load_mask_for_glass(first, mask_path)
masked = render('05_realistic_masked.png')
check(first.active_material.node_tree.nodes.get('BVT_Precision_PNG_Mask') is not None,
      'Precision PNG mask not linked after atlas generation')

set_droplet_mode(first, 'PHOTO_MAPS')
check({kind: image.name for kind, image in packed_maps_for(first, mode='PHOTO_MAPS').items()}
      == photo_names, 'Switching modes lost the imported Photo Maps')
set_droplet_mode(first, 'PROCEDURAL')
check(first.get(MODE_KEY) == 'PROCEDURAL', 'Procedural switch failed')
check(second.active_material is mat_second, 'Second glass material changed')
check(max(abs(before[i][j] - first.matrix_world[i][j]) for i in range(4) for j in range(4)) < 1e-5,
      'Photo map import changed glass geometry')

metrics = {
    'procedural_vs_source': diff(procedural, original),
    'photo_maps_vs_procedural': diff(photo, procedural),
    'realistic_vs_procedural': diff(realistic, procedural),
    'realistic_vs_photo_maps': diff(realistic, photo),
    'realistic_seed72_vs_seed73': diff(realistic, seed73),
    'mask_effect_on_realistic_atlas': diff(realistic, masked),
}
for name, value in metrics.items():
    check(value > 1e-6, f'Image did not change: {name}')

# Restore the generated atlas mode for persistence and GUI inspection.
set_droplet_mode(first, 'REALISTIC_ATLAS', tiling=1.45, rotation=0.)
if options.save_blend:
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'realistic_droplets_smoke.blend'))
(out / 'realistic_atlas_manifest.json').write_text(json.dumps({
    'stage': 'alpha.5-step2',
    'source': str(source_photo),
    'source_maps': 'synthetic_test_only_not_photographic',
    'atlas': {'resolution':512,'seed':72,'density':1.15,'streaks':.65},
    'atlas_packed': sorted(atlas),
    'original_photo_maps_preserved': True,
    'blender': bpy.app.version_string,
    'mode_first': first.get(MODE_KEY),
    'mode_second': second.get(MODE_KEY, 'PROCEDURAL'),
    'maps_packed': sorted(photos),
    'metrics': metrics,
}, indent=2), encoding='utf-8')
print('BVT REALISTIC ATLAS: OK — three modes, packed atlas, independent photo maps, seed and mask')
print('ATLAS_QA_DIR=' + str(out))
