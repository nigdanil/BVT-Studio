"""BVT Studio v0.4.0-alpha.5 visual review: one independent .blend per effect.

Run only from Blender 5.2.3+ with BVT-Studio repo accessible via --repo.
The source photograph and generated maps are packed into every saved .blend.
Photo-space glass rectangle coordinates are approximate visual-review geometry,
NOT verified segmentation masks and NOT real-dataset QA ground truth.

No source/label files are modified. No YOLO annotations are generated.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path


def parse_args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description='BVT Studio visual-effects .blend gallery')
    parser.add_argument('--repo', required=True, help='Path to BVT-Studio checkout')
    parser.add_argument('--photo', required=True, help='Original photo path (not mutated)')
    parser.add_argument('--output', required=True, help='Output root, separate from inputs')
    parser.add_argument('--rects-file', required=True, help='JSON photo pixel rectangles')
    parser.add_argument('--mode', required=True, help='One gallery variant ID or --list-modes')
    parser.add_argument('--mask-dir', default=None,
                        help='Optional VERIFIED per-pane grayscale mask_glass_001.png..._004.png')
    parser.add_argument('--no-mask', action='store_true', help='No PNG mask, geometry+analytic inset only')
    parser.add_argument('--atlas-resolution', type=int, choices=(256,512,1024), default=512)
    return parser.parse_args(argv)


MODES = {
    '00_clean': ('QA_TRANSPARENT', None, None),
    '01_light_condensation': ('LIGHT_CONDENSATION', None, None),
    '02_heavy_condensation': ('HEAVY_CONDENSATION', None, None),
    '03_frost': ('FROST', None, None),
    '04_dirty_glass': ('DIRTY_GLASS', None, None),
    '05_reflections': ('REFLECTIONS', None, None),
    '06_micro_droplets': ('LIGHT_CONDENSATION', None, None),
    '07_atlas_light_no_optics': ('LIGHT_CONDENSATION', (.45, .10), None),
    '08_atlas_light_optics': ('LIGHT_CONDENSATION', (.45, .10), (1.25, .85, 1.00, .25)),
    '09_atlas_medium_no_optics': ('HEAVY_CONDENSATION', (.82, .30), None),
    '10_atlas_medium_optics': ('HEAVY_CONDENSATION', (.82, .30), (1.45, 1., 1.25, .35)),
    '11_atlas_heavy_streaks': ('HEAVY_CONDENSATION', (1.25, .70), (1.45, 1., 1.25, .35)),
    '12_atlas_strong_optics_stress': ('HEAVY_CONDENSATION', (.82, .30), (1.75, 1.55, 1.70, .40)),
}


def digest(path):
    h = hashlib.sha256()
    with open(path,'rb') as stream:
        for b in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def validate_rectangles(config, image_size):
    ref = config.get('reference_size')
    rects = config.get('glass_rectangles')
    if not (isinstance(ref, list) and len(ref) == 2 and
            all(isinstance(x, int) and x > 0 for x in ref)):
        raise ValueError('reference_size must be [width,height]')
    if ref != list(image_size):
        raise ValueError(f'Photo {image_size} differs from rectangle reference {ref}. '
                         'Adjust reference_size and rectangles; do not silently stretch masks.')
    if not (isinstance(rects, list) and len(rects) == 4):
        raise ValueError('Expected exactly four glass_rectangles')
    w, h = ref
    for i, rect in enumerate(rects, 1):
        if (not isinstance(rect, list) or len(rect) != 4 or
            not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in rect)):
            raise ValueError(f'Invalid rectangle {i}')
        x0,y0,x1,y1 = rect
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise ValueError(f'Rectangle {i} outside photo: {rect}')
    return rects


def create_mask_png(path, size=512):
    # Soft 2.5% black margin to minimize antialiasing on each cut-out window.
    # This simple gradient protects an INSET rectangle only; it is not a
    # hand-segmented real glass mask or correct for nonrectangular apertures.
    import bpy
    import numpy as np
    v, u = np.mgrid[0:size, 0:size]
    u = (u + .5) / size
    v = (v + .5) / size
    min_edge = np.minimum.reduce([u, 1-u, v, 1-v])
    edge = np.clip((min_edge-.012)/.024, 0, 1).astype('float32')
    edge = edge*edge*(3-2*edge)
    rgba = np.ones((size,size,4), dtype='float32')
    rgba[:,:,:3] = edge[:,:,None]
    img = bpy.data.images.new('BVT_Gallery_Mask_Creation', width=size,height=size,alpha=True)
    try:
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = str(path)
        img.file_format = 'PNG'
        img.save()
    finally:
        bpy.data.images.remove(img)


def update_gallery_index(output):
    variants = sorted(output.glob('*/render.png'))
    cards = []
    for render in variants:
        ident = render.parent.name
        cards.append('<article><a href="{d}/render.png" target="_blank">'
                     '<img src="{d}/render.png" loading="lazy" alt="{name}"></a>'
                     '<h2>{name}</h2><p><a href="{d}/scene.blend">Blender scene</a> · '
                     '<a href="{d}/manifest.json">Manifest</a></p></article>'.format(
                         d=html.escape(ident,quote=True),name=html.escape(ident)))
    page = ('<!doctype html><html lang="ru"><meta charset="utf-8">'
            '<title>BVT Glass Effects — Visual Review</title>'
            '<style>body{font-family:system-ui;background:#111827;color:#f9fafb;'
            'max-width:1600px;margin:auto;padding:24px}p{color:#cbd5e1}'
            'a{color:#93c5fd}main{display:grid;grid-template-columns:'
            'repeat(auto-fit,minmax(420px,1fr));gap:18px}'
            'article{background:#1f2937;border-radius:10px;padding:12px}'
            'img{width:100%;border-radius:6px}h2{font-size:16px}</style>'
            '<h1>BVT Studio — Glass Effect Gallery</h1>'
            '<p>Каждый результат имеет собственную .blend-сцену и PNG. '
            'Маски — геометрические тестовые, не ground truth.</p><main>'
            + '\n'.join(cards) + '</main></html>')
    (output/'index.html').write_text(page, encoding='utf-8')


def main():
    opts = parse_args()
    repo = Path(opts.repo).resolve()
    photo = Path(opts.photo).resolve()
    output = Path(opts.output).resolve()
    rects_file = Path(opts.rects_file).resolve()
    mask_dir = Path(opts.mask_dir).resolve() if opts.mask_dir else None
    if opts.mode not in MODES:
        raise ValueError('Unknown mode: ' + opts.mode + '; valid: ' + ', '.join(MODES))
    if not (repo/'bvt_studio'/'__init__.py').is_file():
        raise FileNotFoundError('BVT Studio checkout not found: ' + str(repo))
    if not photo.is_file():
        raise FileNotFoundError('Photo not found: ' + str(photo))
    if mask_dir and opts.no_mask:
        raise ValueError('Choose --mask-dir OR --no-mask')
    if mask_dir and not mask_dir.is_dir():
        raise FileNotFoundError('Mask directory not found: '+str(mask_dir))
    if output == repo or output == photo.parent or output.is_relative_to(photo.parent):
        # Standard D:/BVT-Studio/qa_renders is under repo and thus photo.parent
        # typically lies elsewhere; restrict only truly destructive collisions.
        if output == photo.parent or output == repo:
            raise ValueError('Output must not be photo directory or repository root')
    if output == photo or output == rects_file:
        raise ValueError('Output collides with an input')
    if str(repo) not in sys.path:
        sys.path.insert(0,str(repo))
    import bpy
    import bvt_studio
    from bvt_studio.common import get_source, image_from_mesh
    from bvt_studio.glass import scene_glass, fit_glass_to_source_uv_rect
    from bvt_studio.artifact_presets import apply_preset
    from bvt_studio.realistic_atlas import generate_realistic_atlas
    from bvt_studio.glass_mask import load_mask_for_glass, mask_image_for
    from bvt_studio.droplet_maps import packed_maps_for
    from bvt_studio.optical_water import set_optical_water

    if not hasattr(bpy.types.Scene,'bvt_studio'):
        bvt_studio.register()
    config = json.loads(rects_file.read_text(encoding='utf-8'))
    image = bpy.data.images.load(str(photo),check_existing=True)
    rects = validate_rectangles(config,tuple(image.size[:]))
    source_hash = digest(photo)
    finished = bpy.ops.bvt_studio.load_photo(filepath=str(photo))
    if finished != {'FINISHED'}:
        raise RuntimeError('BVT photo import was cancelled')
    scene = bpy.context.scene
    source = get_source(scene)
    assert source is not None
    source_image = image_from_mesh(source)
    if source_image is None:
        raise AssertionError('Photo plane has no source image')
    source_image.pack()
    if not source_image.packed_file:
        raise AssertionError('Photo could not be packed')
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    # Base image is unlit and shouldn't be accidentally exposed by a lamp.
    mode_preset, atlas_params, optics = MODES[opts.mode]
    variant_dir = output / opts.mode
    variant_dir.mkdir(parents=True, exist_ok=True)
    variant_masks = variant_dir / 'masks'
    if not opts.no_mask:
        variant_masks.mkdir(parents=True, exist_ok=True)

    width, height = image.size[:]
    for idx, (x0,y0,x1,y1) in enumerate(rects, 1):
        result = bpy.ops.bvt_studio.add_glass()
        if result != {'FINISHED'}:
            raise RuntimeError(f'Glass creation failed for pane {idx}')
        glass = scene_glass(scene)[-1]
        fit_glass_to_source_uv_rect(
            glass,source,x0/width,1-y1/height,x1/width,1-y0/height)
        # A separate deterministic pattern per pane; stable across variants.
        seed = 72+idx-1
        coverage = {'QA_TRANSPARENT': 0., 'LIGHT_CONDENSATION': .35,
                    'HEAVY_CONDENSATION': .65, 'FROST': .50,
                    'DIRTY_GLASS': .58, 'REFLECTIONS': .14}[mode_preset]
        scale = 1.7 if opts.mode == '06_micro_droplets' else 1.0
        apply_preset(glass,mode_preset,intensity=1.0,coverage=coverage,
                     seed=seed,droplet_scale=scale,frost_edge=.5,
                     refraction=.024,relief=.9)
        if not opts.no_mask:
            if mask_dir:
                mask_path = mask_dir/f'mask_glass_{idx:03}.png'
                if not mask_path.is_file():
                    raise FileNotFoundError(f'Missing verified glass mask: {mask_path}')
            else:
                mask_path = variant_masks/f'mask_glass_{idx:03}.png'
                create_mask_png(mask_path)
            load_mask_for_glass(glass,mask_path)
            mask_img = mask_image_for(glass)
            if not mask_img or not mask_img.packed_file:
                raise AssertionError('Mask not packed: '+str(glass.name))
        if atlas_params is not None:
            density, streaks = atlas_params
            generate_realistic_atlas(glass,seed=seed,resolution=opts.atlas_resolution,
                                     density=density,streaks=streaks,tiling=1.,rotation=0.)
            atlas = packed_maps_for(glass, mode='REALISTIC_ATLAS')
            if set(atlas) != {'alpha','height','normal'} or not all(i.packed_file for i in atlas.values()):
                raise AssertionError('Incomplete packed realistic atlas')
            if optics is not None:
                lens,edge,glint,micro = optics
                set_optical_water(glass,True,lens=lens,edge=edge,glint=glint,micro=micro)
        glass['bvt_gallery_variant'] = opts.mode
        glass['bvt_gallery_mask_provenance'] = (
            'none' if opts.no_mask else 'user-supplied-not-verified-by-script'
            if mask_dir else 'approximate_test_rectangle_not_ground_truth')
        bpy.context.view_layer.update()

    glasses = scene_glass(scene)
    if len(glasses) != 4:
        raise AssertionError(f'Expected 4 independent glass panes; got {len(glasses)}')
    scene.bvt_studio.artifact_target_glass = glasses[0]
    scene.bvt_studio.artifact_preset = 'CLEAN' if mode_preset == 'QA_TRANSPARENT' else mode_preset
    if atlas_params:
        scene.bvt_studio.realistic_atlas_resolution = str(opts.atlas_resolution)
        scene.bvt_studio.realistic_atlas_density = atlas_params[0]
        scene.bvt_studio.realistic_atlas_streaks = atlas_params[1]
    if optics:
        (scene.bvt_studio.optical_lens_gain,
         scene.bvt_studio.optical_edge_gain,
         scene.bvt_studio.optical_glint_gain,
         scene.bvt_studio.optical_micro_gain) = optics
    scene['bvt_gallery_mode'] = opts.mode
    scene['bvt_gallery_source_sha256'] = source_hash
    scene['bvt_gallery_mask_policy'] = 'approximate test-only' if not mask_dir else 'user-supplied unverified'
    scene.render.filepath = '//render.png'
    blend = variant_dir / 'scene.blend'
    result = bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
    if result != {'FINISHED'} or not blend.is_file():
        raise RuntimeError('Scene was not saved: ' + str(blend))
    bpy.ops.render.render(write_still=True)
    render = variant_dir / 'render.png'
    if not render.is_file() or render.stat().st_size < 1024:
        raise AssertionError('Render missing/empty: '+str(render))
    if digest(photo) != source_hash:
        raise AssertionError('Source photo changed unexpectedly')
    manifest = {
        'variant':opts.mode,'blender':bpy.app.version_string,
        'source':str(photo),'source_sha256':source_hash,
        'scene_file':str(blend),'render_file':str(render),
        'glass_count':len(glasses), 'glass_rectangles_px_top_down':rects,
        'preset':mode_preset,'atlas_density_streaks':atlas_params,
        'atlas_resolution':opts.atlas_resolution if atlas_params else None,
        'optical_lens_shadow_highlight_micro':optics,
        'mask_provenance':('none' if opts.no_mask else 'supplied_must_verify_manually'
                           if mask_dir else 'generated_approximate_not_qa_truth'),
        'source_packed':bool(source_image.packed_file),
        'all_maps_packed':all(
            all(image.packed_file for image in packed_maps_for(g,mode='REALISTIC_ATLAS').values())
            for g in glasses) if atlas_params else None,
        'warning':'Visual-only BVT 2.5D simulation; NOT YOLO accuracy or real mask ground truth.',
    }
    (variant_dir/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False), encoding='utf-8')
    update_gallery_index(output)
    print('BVT GALLERY OK: '+opts.mode)
    print('BLEND_FILE='+str(blend))
    print('RENDER_FILE='+str(render))
    print('GALLERY_INDEX='+str(output/'index.html'))


if __name__ == '__main__':
    main()
