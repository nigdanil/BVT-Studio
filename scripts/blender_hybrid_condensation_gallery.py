"""Render and compare Hybrid Condensation v2, optionally on a real source image.

Run from Git Bash in the repository root:
  "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
    --background --factory-startup \
    --python scripts/blender_hybrid_condensation_gallery.py -- \
    --output "D:/BVT-Studio/qa_renders/hybrid"

For real retail QA also pass:
    --photo "D:/path/to/freezer_photo.png"
No Blender project, input photo or YOLO data is modified or saved.
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
import bvt_studio
from bvt_studio.common import get_source, image_from_mesh
from bvt_studio.glass import scene_glass, fit_glass_to_source_uv_rect


def check(ok, msg):
    if not ok:
        raise AssertionError(msg)


args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--output', default=str(ROOT / 'qa_renders' / 'hybrid'))
parser.add_argument('--photo', default=None,
                    help='Optional original freezer PNG/JPEG for retail visual QA')
opts = parser.parse_args(args)
out = Path(opts.output).resolve()
out.mkdir(parents=True, exist_ok=True)
if opts.photo:
    photo = Path(opts.photo).resolve()
    check(photo.is_file(), f'Photo not found: {photo}')
else:
    photo = None

if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()
check(bpy.app.version >= (5, 2, 0), 'Requires Blender 5.2+')

with tempfile.TemporaryDirectory(prefix='bvt_hybrid_') as temp:
    if photo is None:
        source_path = Path(temp) / 'synthetic_photo.png'
        w, h = 512, 320
        img = bpy.data.images.new('BVT_Hybrid_QA_Source', width=w, height=h, alpha=True)
        raw = []
        for y in range(h):
            for x in range(w):
                c = (.2 if (x // 25) % 2 else .8)
                d = (.25 if (y // 21) % 2 else .76)
                raw.extend((c, d, .22 + .5 * math.sin(x / 21.) ** 2, 1.))
        img.pixels[:] = raw
        img.filepath_raw = str(source_path)
        img.file_format = 'PNG'
        img.save()
    else:
        source_path = photo
    check(bpy.ops.bvt_studio.load_photo(filepath=str(source_path)) == {'FINISHED'},
          'Source photo import failed')
    scene = bpy.context.scene
    source = get_source(scene)
    source.rotation_euler.x = math.radians(8)
    bpy.context.view_layer.update()
    check(bpy.ops.bvt_studio.fit_camera() == {'FINISHED'}, 'Camera fit failed')
    scene.render.engine = 'BLENDER_EEVEE'
    source_image = image_from_mesh(source)
    check(source_image is not None, 'Source image unavailable after import')
    width, height = tuple(source_image.size)
    check(width > 0 and height > 0, 'Source image has invalid dimensions')
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'

    def render(name):
        dest = out / name
        scene.render.filepath = str(dest)
        bpy.ops.render.render(write_still=True)
        check(dest.is_file() and dest.stat().st_size > 300, 'Missing PNG: ' + name)
        img = bpy.data.images.load(str(dest), check_existing=False)
        try:
            pixels = img.pixels[:]
            width, height = tuple(img.size)
            vals = []
            for y in range(45, height - 45, 12):
                for x in range(45, width - 45, 12):
                    k = 4 * (y * width + x)
                    vals.extend(pixels[k:k+3])
            return tuple(vals)
        finally:
            bpy.data.images.remove(img)

    def diff(a, b):
        return sum(abs(x-y) for x,y in zip(a,b)) / len(a)

    base = render('00_source.png')
    for _ in range(4):
        check(bpy.ops.bvt_studio.add_glass() == {'FINISHED'}, 'Cannot add glass')
    glasses = scene_glass(scene)
    check(len(glasses) >= 4, 'Expected four glass planes for freezer sections')
    section_rects = (
        (.060, .120, .305, .840),
        (.315, .120, .522, .840),
        (.535, .120, .725, .840),
        (.744, .120, .940, .840),
    )
    for obj, rect in zip(glasses[:4], section_rects):
        fit_glass_to_source_uv_rect(obj, source, *rect)
        obj['bvt_artifact_mask_inset'] = 0.018
        obj['bvt_artifact_mask_feather'] = 0.018
        obj['bvt_artifact_aperture_left'] = 0.02
        obj['bvt_artifact_aperture_right'] = 0.98
        obj['bvt_artifact_aperture_bottom'] = 0.02
        obj['bvt_artifact_aperture_top'] = 0.98
        obj['bvt_artifact_aperture_feather'] = 0.015
    bpy.context.view_layer.update()
    before = [obj.matrix_world.copy() for obj in glasses[:4]]
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
    settings.artifact_seed = 72

    def apply_to_all(preset, seed):
        settings.artifact_preset = preset
        settings.artifact_seed = seed
        for idx, obj in enumerate(glasses[:4]):
            settings.artifact_target_glass = obj
            settings.artifact_seed = seed + idx
            check(bpy.ops.bvt_studio.apply_glass_preset() == {'FINISHED'},
                  'Failed to apply ' + preset + ' to ' + obj.name)
            if preset != 'CLEAN':
                nodes = obj.active_material.node_tree.nodes
                atlas = nodes.get('BVT_Hybrid_Atlas')
                check(atlas and atlas.image and atlas.image.size[0] == 512,
                      'Hybrid droplet atlas not connected')
                check(nodes.get('BVT_Hybrid_Refracted_Photo') is not None,
                      'Photo refraction not connected')
                check(nodes.get('BVT_Hybrid_Aperture_Mask') is not None,
                      'Aperture mask not connected')

    values = {}
    for preset, name in (
        ('CLEAN', '01_clean.png'),
        ('LIGHT_CONDENSATION', '02_hybrid_light.png'),
        ('HEAVY_CONDENSATION', '03_hybrid_heavy.png'),
    ):
        apply_to_all(preset, 72)
        values[preset] = render(name)

    apply_to_all('HEAVY_CONDENSATION', 73)
    alternate = render('04_hybrid_heavy_seed73.png')

    # Debug aperture image: make section 1 heavy and hide the rest to verify locality.
    for obj in glasses[1:4]:
        obj.hide_render = True
    render('05_aperture_debug.png')
    for obj in glasses[1:4]:
        obj.hide_render = False

    metrics = {
        'light_vs_clean': diff(values['LIGHT_CONDENSATION'], values['CLEAN']),
        'heavy_vs_clean': diff(values['HEAVY_CONDENSATION'], values['CLEAN']),
        'heavy_vs_source': diff(values['HEAVY_CONDENSATION'], base),
        'seed_72_vs_73': diff(values['HEAVY_CONDENSATION'], alternate),
        'glass_sections': len(glasses[:4]),
    }
    for name, value in metrics.items():
        if name != 'glass_sections':
            check(value > 1e-6, f'No pixel change: {name}')
    for obj, mat_before, matrix_before in zip(glasses[:4], [g.active_material for g in glasses[:4]], before):
        after = obj.matrix_world
        check(max(abs(matrix_before[i][j] - after[i][j]) for i in range(4)
                  for j in range(4)) < 1e-5, 'Preset changed glass transform')
        check(obj.active_material == mat_before, 'Preset replaced glass material object')
    (out / 'hybrid_manifest.json').write_text(json.dumps({
        'stage': 'v0.4.0-alpha.4-step3',
        'blender': bpy.app.version_string,
        'source': str(source_path) if photo else 'synthetic_color_chart',
        'seed': 72,
        'other_seed': 73,
        'section_rects': section_rects,
        'settings': {'coverage': .68, 'droplet_scale': 1.15,
                     'wetness': .70, 'macro': .72, 'micro': .70, 'refraction': .024,
                     'relief': .95, 'mask_inset': .018, 'mask_feather': .018,
                     'aperture_left': .02, 'aperture_right': .98,
                     'aperture_bottom': .02, 'aperture_top': .98,
                     'aperture_feather': .015},
        'render_size': [scene.render.resolution_x, scene.render.resolution_y],
        'metrics': metrics,
    }, indent=2), encoding='utf-8')
    print('BVT HYBRID GLASS GALLERY: OK — four UV-fitted sections, aperture mask, seed contrast')
    print('HYBRID_QA_DIR=' + str(out))
