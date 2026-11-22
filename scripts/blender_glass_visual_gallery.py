"""Render real PNG reference gallery for v0.4 glass presets in Blender 5.2+.

Run from Git Bash at the BVT-Studio repo root:
  "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
    --background --factory-startup \
    --python scripts/blender_glass_visual_gallery.py -- \
    --output "D:/BVT-Studio/qa_renders/glass"

The gallery is *rendered* by Blender. It does not fetch stock imagery or
create a ZIP.  PNGs persist in the chosen folder for visual inspection.
"""
import argparse
import json
import hashlib
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import bvt_studio
from bvt_studio.common import get_source
from bvt_studio.glass import scene_glass


def check(ok, error):
    if not ok:
        raise AssertionError(error)


args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--output', default=str(ROOT / 'qa_renders' / 'glass'))
output = Path(parser.parse_args(args).output).resolve()
output.mkdir(parents=True, exist_ok=True)

check(bpy.app.version >= (5, 2, 0), 'Blender 5.2+ required')
if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

with tempfile.TemporaryDirectory(prefix='bvt_glass_visual_') as tmp:
    photo = Path(tmp) / 'photo.png'
    w, h = 384, 256
    img = bpy.data.images.new('BVT_Visual_Gallery_Source', width=w, height=h, alpha=True)
    rgba = []
    for y in range(h):
        for x in range(w):
            # Clear edges and high-contrast lines expose the degree of warping.
            stripe = 0.25 if (x // 18) % 2 == 0 else .85
            bar = 0.15 if (y // 23) % 2 == 0 else .78
            rgba.extend((.12 + stripe * .75, .16 + bar * .67,
                         .12 + .35 * abs(math.sin(x / 19.0)), 1.0))
    img.pixels[:] = rgba
    img.filepath_raw = str(photo)
    img.file_format = 'PNG'
    img.save()
    check(bpy.ops.bvt_studio.load_photo(filepath=str(photo)) == {'FINISHED'},
          'Photo import failed')
    scene = bpy.context.scene
    source = get_source(scene)
    source.rotation_euler.x = math.radians(12)
    bpy.context.view_layer.update()
    check(bpy.ops.bvt_studio.fit_camera() == {'FINISHED'}, 'Camera fit failed')
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 768, 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = '8'
    scene.view_settings.view_transform = 'Standard'

    def render(name):
        path = output / name
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        check(path.exists() and path.stat().st_size > 200, 'No PNG: ' + name)
        # Compare *decoded pixel colors*, not PNG byte hashes: PNG ancillary
        # chunks could differ even when the rendered image is unchanged.
        result = bpy.data.images.load(str(path), check_existing=False)
        try:
            width, height = result.size[:]
            check((width, height) == (768, 512), 'Unexpected render dimensions')
            pixels = result.pixels[:]
            # Dense, deterministic sampling of the painted glass area.
            signature = []
            for y in range(32, height - 32, 11):
                for x in range(30, width - 30, 11):
                    i = 4 * (y * width + x)
                    signature.extend(pixels[i:i + 3])
            return tuple(signature)
        finally:
            bpy.data.images.remove(result)

    def pixel_difference(a, b):
        check(len(a) == len(b), 'Signature size mismatch')
        return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

    base_signature = render('00_source.png')
    check(bpy.ops.bvt_studio.add_glass() == {'FINISHED'}, 'Add Glass failed')
    target = scene_glass(scene)[0]
    # Enlarge the generated guide to cover most of the photo for comparing PNGs.
    target.scale.x *= 2.4
    target.scale.y *= 1.20
    # Keep photo-relative depth; moving only in the source-plane tangent.
    tangent = source.matrix_world.to_3x3() @ __import__('mathutils').Vector((1, 0, 0))
    target.location += tangent * 0.43
    bpy.context.view_layer.update()
    before = target.matrix_world.copy()
    settings = scene.bvt_studio
    settings.artifact_target_glass = target
    settings.artifact_intensity = 1.0
    settings.artifact_coverage = .68
    settings.artifact_droplet_scale = 1.15
    settings.artifact_frost_edge = .85
    settings.artifact_refraction = .024
    settings.artifact_relief = .95
    settings.artifact_seed = 72

    cases = [
        ('CLEAN', '01_clean.png'),
        ('LIGHT_CONDENSATION', '02_light_condensation.png'),
        ('HEAVY_CONDENSATION', '03_heavy_condensation.png'),
        ('FROST', '04_frost.png'),
        ('DIRTY_GLASS', '05_dirty_glass.png'),
        ('REFLECTIONS', '06_reflections.png'),
    ]
    signatures = {}
    for preset, filename in cases:
        settings.artifact_preset = preset
        check(bpy.ops.bvt_studio.apply_glass_preset() == {'FINISHED'},
              'Preset failed: ' + preset)
        mat = target.active_material
        names = mat.node_tree.nodes
        for node_name in ('BVT_Droplet_Relief_Overlay',
                          'BVT_Condensation_Overlay', 'BVT_Crystalline_Overlay',
                          'BVT_Local_Photo_Refraction', 'BVT_Refracted_Source_Photo'):
            check(names.get(node_name) is not None,
                  'Live shader is missing ' + node_name)
        signatures[preset] = render(filename)

    settings.artifact_preset = 'HEAVY_CONDENSATION'
    settings.artifact_seed = 73
    check(bpy.ops.bvt_studio.apply_glass_preset() == {'FINISHED'},
          'Alternate seed failed')
    alternate = render('07_heavy_seed_73.png')
    seed_delta = pixel_difference(alternate, signatures['HEAVY_CONDENSATION'])
    heavy_delta = pixel_difference(signatures['HEAVY_CONDENSATION'], signatures['CLEAN'])
    frost_delta = pixel_difference(signatures['FROST'], signatures['CLEAN'])
    source_delta = pixel_difference(base_signature, signatures['HEAVY_CONDENSATION'])
    check(seed_delta > 1e-6, 'Seed change did not alter decoded pixels')
    check(heavy_delta > 1e-5, 'Heavy condensation did not alter decoded pixels')
    check(frost_delta > 1e-5, 'Frost did not alter decoded pixels')
    check(source_delta > 1e-5, 'Glass is not visible in rendered pixels')
    after = target.matrix_world
    check(max(abs(before[i][j] - after[i][j]) for i in range(4)
              for j in range(4)) < 1e-5, 'Presets changed object transform')
    metrics = dict(seed_delta=seed_delta, heavy_vs_clean=heavy_delta,
                   frost_vs_clean=frost_delta, heavy_vs_source=source_delta)
    manifest = dict(stage='v0.4.0-alpha.3', render_engine=scene.render.engine,
                    blender_version=bpy.app.version_string, input='synthetic_checker_photo',
                    seed=72, second_seed=73, refraction=.024, relief=.95,
                    metrics=metrics)
    (output / 'gallery_manifest.json').write_text(
        json.dumps(manifest, indent=2), encoding='utf-8')
    print('Pixel differences:', metrics)
    print('BVT REALISTIC GLASS GALLERY: OK — 8 PNGs rendered, seed changes pixels, geometry stable')
    print('VISUAL_QA_DIR=' + str(output))
