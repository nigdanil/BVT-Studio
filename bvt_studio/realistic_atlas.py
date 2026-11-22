"""Deterministic, multi-scale *synthetic* droplet atlases for Blender 5.2+.

The output is an Alpha / Height / OpenGL tangent Normal PNG triplet packed
per BVT Glass object. This is not photogrammetry and does not reproduce a
real-world photographed water surface; visual acceptance requires real renders.
No dependencies beyond NumPy included with Blender are needed.
"""
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory

ATLAS_MODE = 'REALISTIC_ATLAS'
PARAM_KEYS = ('bvt_atlas_generation_seed', 'bvt_atlas_resolution',
              'bvt_atlas_density', 'bvt_atlas_streaks')


def validate_atlas(seed, resolution, density, streaks):
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2147483647:
        raise ValueError('Atlas seed must be a 32-bit nonnegative integer')
    if isinstance(resolution, bool) or resolution not in (256, 512, 1024):
        raise ValueError('Atlas resolution must be 256, 512 or 1024')
    if not isfinite(float(density)) or not .25 <= float(density) <= 2.0:
        raise ValueError('Atlas density must be in [0.25, 2]')
    if not isfinite(float(streaks)) or not 0. <= float(streaks) <= 1.:
        raise ValueError('Atlas streaks must be in [0, 1]')


def generate_atlas_arrays(seed=42, resolution=512, density=1., streaks=.35):
    """Return repeatable float32 RGB alpha/height/normal arrays, shape SxSx3.

    Elliptical lens caps use irregular outlines and varied aspect ratios.
    Separate small beads, broad drops and meandering gravity trails create
    more realistic scale structure than identical circular stamp masks.
    Shapes are clamped to the texture; no global RNG state is changed.
    """
    validate_atlas(seed, resolution, density, streaks)
    import numpy as np

    n = resolution
    rng = np.random.default_rng(seed)
    alpha = np.zeros((n, n), dtype=np.float32)
    height = np.zeros_like(alpha)
    size = n / 512.

    def stamp(cx, cy, rx, ry, strength, phase, irregularity):
        bound = max(rx, ry) * 1.32 + 2
        x0 = max(0, int(cx-bound)); x1 = min(n, int(cx+bound)+1)
        y0 = max(0, int(cy-bound)); y1 = min(n, int(cy+bound)+1)
        if x0 >= x1 or y0 >= y1:
            return
        yy, xx = np.ogrid[y0:y1, x0:x1]
        # No allocation of a whole-image mesh for each small droplet.
        u = (xx - cx) / max(rx, .3)
        v = (yy - cy) / max(ry, .3)
        theta = np.arctan2(v, u)
        perturb = 1. + irregularity * (np.sin(3.*theta + phase)
                    + .37*np.sin(5.*theta - phase*.71))
        rr = np.sqrt(u*u + v*v) / np.maximum(perturb, .7)
        inside = np.clip((1. - rr) * max(2.2, min(rx,ry)*1.15), 0., 1.)
        # Contact line and spherical cap: transparent centre, accentuated rim
        # via height gradient and alpha falloff at the perimeter.
        lens = np.sqrt(np.maximum(0., 1. - np.minimum(rr, 1.)**2))
        rim = np.exp(-((rr - .80)/.105)**2)
        occupancy = inside * np.clip(.55 + .34*rim, 0., 1.)
        patch_a = alpha[y0:y1,x0:x1]
        patch_h = height[y0:y1,x0:x1]
        np.maximum(patch_a, occupancy * strength, out=patch_a)
        np.maximum(patch_h, lens * inside * strength, out=patch_h)

    # Micro droplets: non-uniform distribution with dense, mostly clear centres.
    for _ in range(round(370*density*size*size)):
        rad = rng.uniform(.8, 3.0)*size
        aspect = rng.uniform(.75, 1.4)
        stamp(rng.uniform(0, n), rng.uniform(0, n), rad*aspect, rad/aspect,
              rng.uniform(.32,.72), rng.uniform(-3.14,3.14), rng.uniform(.015,.1))

    # Macro droplets: sizes, tear shapes, and lens-cap relief vary per drop.
    for _ in range(round(78*density*size*size)):
        rad = rng.uniform(4.5, 18.)*size
        aspect = rng.uniform(.7, 1.32)
        stamp(rng.uniform(0,n), rng.uniform(0,n), rad*aspect, rad/aspect,
              rng.uniform(.65,1.), rng.uniform(-3.14,3.14), rng.uniform(.045,.17))

    # Gravity-aligned streaks with narrowing tails and drifting centreline.
    # Blender row 0 is bottom, so gravity follows decreasing V.
    for _ in range(round(16*streaks*size)):
        cx = rng.uniform(20, n-20)
        y0 = rng.uniform(.30*n, .94*n)
        length = rng.uniform(27., 115.) * size
        segs = max(6, int(length / max(2.5*size,1.)))
        phase = rng.uniform(0., 6.28)
        width = rng.uniform(1.1, 3.3) * size
        for k in range(segs):
            t = k / max(segs-1, 1)
            x = cx + (2.7*size)*np.sin(t*5.8+phase) + (1.9*size)*t
            y = y0 - t*length
            stamp(x,y, width*(1.15-.45*t),
                  max(width*.9,1.*size), .48*(1.-.55*t), phase, .04)
        stamp(cx+2.7*size*np.sin(phase), y0, width*2.2, width*2.7,
              .72, phase, .08)

    # Gradients produce tangent slopes. Smooth very fine changes before
    # encoding to avoid quantisation-driven false high-frequency normals.
    gy, gx = np.gradient(height)
    gx = np.clip(-gx * 3.2, -.75, .75)
    gy = np.clip(-gy * 3.2, -.75, .75)
    norm = np.sqrt(gx*gx + gy*gy + 1.)
    nx, ny, nz = gx/norm, gy/norm, 1./norm
    normal = np.stack((.5+.5*nx, .5+.5*ny, .5+.5*nz), axis=-1).astype(np.float32)
    # RGB grayscale is used by the shader, not the PNG alpha channel.
    ar = np.repeat(alpha[:,:,None],3,axis=-1)
    hr = np.repeat(height[:,:,None],3,axis=-1)
    return {"alpha":ar, "height":hr, "normal":normal}


def _save_png(path, rgb):
    """Write arrays via Blender so no Pillow installation is needed."""
    import bpy
    import numpy as np
    h, w, channels = rgb.shape
    if channels != 3:
        raise ValueError('Atlas texture must be RGB')
    pixels = np.ones((h, w, 4), dtype=np.float32)
    pixels[:,:,:3] = np.clip(rgb, 0., 1.)
    image = bpy.data.images.new('BVT_Atlas_Export_Tmp', width=w, height=h, alpha=True)
    try:
        image.pixels.foreach_set(pixels.ravel())
        image.filepath_raw = str(path)
        image.file_format = 'PNG'
        image.save()
    finally:
        bpy.data.images.remove(image)


def generate_realistic_atlas(obj, seed=42, resolution=512, density=1., streaks=.35,
                             tiling=1., rotation=0., preview_dir=None):
    """Generate, import, pack, and activate atlas for exactly one glass plane.

    User-imported PHOTO_MAPS slots are not overwritten. A temporary PNG triplet
    is imported and packed before deleting the temporary files, making the
    resulting saved .blend portable. Parameters persist as object properties.
    """
    from .droplet_maps import (_glass_check, check_transform,
                               import_droplet_maps, packed_maps_for)
    _glass_check(obj)
    validate_atlas(seed, resolution, density, streaks)
    check_transform(tiling, rotation)
    textures = generate_atlas_arrays(seed, resolution, density, streaks)
    old = {key: obj.get(key) for key in PARAM_KEYS}
    with TemporaryDirectory(prefix='bvt_atlas_') as tmp:
        paths = {kind: Path(tmp) / ('atlas_' + kind + '.png') for kind in textures}
        for kind, texture in textures.items():
            _save_png(paths[kind], texture)
        if preview_dir is not None:
            folder = Path(preview_dir)
            folder.mkdir(parents=True, exist_ok=True)
            for kind, texture in textures.items():
                _save_png(folder / ('atlas_' + kind + '.png'), texture)
        try:
            imported = import_droplet_maps(obj, paths['alpha'],paths['height'],paths['normal'],
                                          tiling,rotation,target_mode=ATLAS_MODE)
            for key, value in zip(PARAM_KEYS, (seed,resolution,float(density),float(streaks))):
                obj[key] = value
        except Exception:
            for key,value in old.items():
                if value is None:
                    if key in obj:
                        del obj[key]
                else:
                    obj[key] = value
            raise
    packed_maps_for(obj, mode=ATLAS_MODE)
    return imported


import bpy


class BVTSTUDIO_OT_generate_realistic_atlas(bpy.types.Operator):
    bl_idname = 'bvt_studio.generate_realistic_atlas'
    bl_label = 'Generate Realistic Water Droplet Atlas'
    bl_description = 'Create an independent synthetic multi-scale atlas for the selected glass'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            generate_realistic_atlas(obj, int(settings.artifact_seed),
                                     int(settings.realistic_atlas_resolution),
                                     settings.realistic_atlas_density,
                                     settings.realistic_atlas_streaks,
                                     settings.droplet_map_tiling,
                                     settings.droplet_map_rotation)
            self.report({'INFO'}, f'{obj.name}: realistic synthetic atlas packed')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Realistic atlas: {exc}')
            return {'CANCELLED'}


class BVTSTUDIO_OT_use_realistic_atlas(bpy.types.Operator):
    bl_idname = 'bvt_studio.use_realistic_atlas'
    bl_label = 'Use Saved Realistic Atlas'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        from .droplet_maps import set_droplet_mode
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            set_droplet_mode(obj, ATLAS_MODE, settings.droplet_map_tiling,
                             settings.droplet_map_rotation)
            self.report({'INFO'}, f'{obj.name}: realistic atlas enabled')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Realistic atlas: {exc}')
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_generate_realistic_atlas, BVTSTUDIO_OT_use_realistic_atlas)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
