"""Hybrid 2.5D condensation with masked glass area and photo resampling.

The atlas is a Blender-generated image with four independent data channels:
R droplet height, G/B encoded tangent slopes, A irregular wet film. NumPy is
bundled with Blender 5.2; no downloaded image or addon dependency is needed.
The atlas is a generated datablock stored in the .blend, not a temporary file.
"""
from math import isfinite

ATLAS_SIZE = 512
HYBRID_PRESETS = frozenset({'LIGHT_CONDENSATION', 'HEAVY_CONDENSATION'})


def validate_hybrid_settings(seed, coverage, droplet_scale, macro, micro, wetness):
    values = (coverage, droplet_scale, macro, micro, wetness)
    if not all(isfinite(float(v)) for v in values):
        raise ValueError('Hybrid condensation parameters must be finite')
    if not isinstance(seed, int) or not 0 <= seed <= 2147483647:
        raise ValueError('Seed must be in [0, 2147483647]')
    for title, value, lo, hi in (
        ('Coverage', coverage, 0., 1.),
        ('Droplet Scale', droplet_scale, .5, 2.),
        ('Macro Droplets', macro, 0., 1.),
        ('Micro Droplets', micro, 0., 1.),
        ('Wetness', wetness, 0., 1.),
    ):
        if not lo <= float(value) <= hi:
            raise ValueError(f'{title} must be in [{lo}, {hi}]')


def validate_aperture_settings(left, right, bottom, top, feather):
    values = (left, right, bottom, top, feather)
    if not all(isfinite(float(v)) for v in values):
        raise ValueError('Aperture parameters must be finite')
    left, right = float(left), float(right)
    bottom, top = float(bottom), float(top)
    feather = float(feather)
    if not 0.0 <= left < right <= 1.0:
        raise ValueError('Aperture Left/Right must satisfy 0 <= left < right <= 1')
    if not 0.0 <= bottom < top <= 1.0:
        raise ValueError('Aperture Bottom/Top must satisfy 0 <= bottom < top <= 1')
    if not 0.001 <= feather <= 0.25:
        raise ValueError('Aperture Feather must be in [0.001, 0.25]')


def _smoothstep(x):
    import numpy as np
    x = np.clip(x, 0., 1.)
    return x * x * (3. - 2. * x)


def _upsampled_field(rng, size, grid_size, lo, hi):
    import numpy as np
    grid = rng.random((grid_size + 1, grid_size + 1)).astype(np.float32)
    axis = np.linspace(0, grid_size - 1, size, dtype=np.float32)
    ix = np.floor(axis).astype(np.intp)
    w = _smoothstep(axis - ix)
    lo_g = grid[ix[:, None], ix[None, :]]
    hi_x = grid[ix[:, None] + 1, ix[None, :]]
    hi_y = grid[ix[:, None], ix[None, :] + 1]
    hi_xy = grid[ix[:, None] + 1, ix[None, :] + 1]
    field = ((lo_g * (1 - w[:, None]) + hi_x * w[:, None]) * (1 - w[None, :])
             + (hi_y * (1 - w[:, None]) + hi_xy * w[:, None]) * w[None, :])
    return _smoothstep((field - lo) / max(hi - lo, 1e-6))


def make_condensation_atlas(seed, coverage, droplet_scale=1., macro=.72, micro=.6,
                            wetness=.6, size=ATLAS_SIZE):
    """Return float32 RGBA data, bottom-to-top Blender image pixel order.

    No Blender access or global random state. Each droplet is an irregular
    hemispherical cap (not a noise threshold): a deterministic curved silhouette
    with coherent tangential height gradients. Three diameter populations and
    some gravity-elongated beads avoid a uniform Voronoi stipple.
    """
    import numpy as np
    seed = int(seed)
    validate_hybrid_settings(seed, coverage, droplet_scale, macro, micro, wetness)
    if not isinstance(size, int) or size < 128 or size > 2048:
        raise ValueError('Atlas size must be an integer in [128, 2048]')
    rng = np.random.default_rng(seed)
    height = np.zeros((size, size), dtype=np.float32)
    coverage = float(coverage)
    scale = float(droplet_scale)
    macro = float(macro)
    micro = float(micro)
    wetness = float(wetness)

    # Large, sparse water beads; medium drops; finely scattered condensate.
    groups = (
        (62 * macro, 9.0, 22.0, .94),
        (620 * max(macro, .10), 3.2, 8.4, .80),
        (4300 * micro, .65, 1.85, .58),
    )
    area_scale = (size / 512.) ** 2
    for count_base, r_min, r_max, peak in groups:
        n = int(round(float(count_base) * coverage * area_scale))
        for _ in range(n):
            radius = float(rng.uniform(r_min, r_max) * size / 512. / max(scale, .15))
            stretch = float(rng.uniform(.78, 1.22))
            if r_max > 10 and rng.random() < .25:
                stretch *= float(rng.uniform(1.45, 2.4))
            rx, ry = radius, radius * stretch
            cx = float(rng.uniform(-rx, size + rx))
            cy = float(rng.uniform(-ry, size + ry))
            x0 = max(0, int(cx - rx * 1.5 - 2))
            x1 = min(size, int(cx + rx * 1.5 + 3))
            y0 = max(0, int(cy - ry * 1.5 - 2))
            y1 = min(size, int(cy + ry * 1.5 + 3))
            if x1 <= x0 or y1 <= y0:
                continue
            yy, xx = np.ogrid[y0:y1, x0:x1]
            dx = (xx - cx) / max(rx, .3)
            dy = (yy - cy) / max(ry, .3)
            theta = np.arctan2(dy, dx)
            waviness = (1. + .055 * np.cos(3. * theta + rng.uniform(0, 6.28))
                         + .030 * np.cos(5. * theta + rng.uniform(0, 6.28)))
            d2 = (dx * dx + dy * dy) * waviness * waviness
            cap = np.sqrt(np.maximum(1. - d2, 0.)) * peak
            if r_max > 10 and rng.random() < .18:
                cap *= (1.0 - .18 * np.clip(dy + 0.20, 0., 1.))
            patch = height[y0:y1, x0:x1]
            np.maximum(patch, cap.astype(np.float32), out=patch)

    left = np.pad(height, ((0, 0), (1, 1)), mode='edge')
    top = np.pad(height, ((1, 1), (0, 0)), mode='edge')
    slope_x = (left[:, 2:] - left[:, :-2]) * 1.8
    slope_y = (top[2:, :] - top[:-2, :]) * 1.8

    # Broad wetness + finer mist give more refrigerator-like non-uniform moisture.
    film = _upsampled_field(rng, size, 22, .27, .58)
    coarse = _upsampled_field(rng, size, 11, .32, .67)
    mist = _upsampled_field(rng, size, 42, .42, .84)
    film = np.clip(film * .58 + coarse * .42, 0., 1.)
    halo = _smoothstep((height - .10) / .22) * .24
    film = np.clip((film * .72 + mist * .18 + halo) * wetness, 0., 1.)

    atlas = np.empty((size, size, 4), dtype=np.float32)
    atlas[:, :, 0] = height
    atlas[:, :, 1] = np.clip(.5 + slope_x * .5, 0., 1.)
    atlas[:, :, 2] = np.clip(.5 + slope_y * .5, 0., 1.)
    atlas[:, :, 3] = film
    return atlas


def ensure_atlas(obj):
    """Update only this object's generated image; retain it in saved .blend files."""
    import bpy
    from .artifact_config import seed_offsets
    seed = int(obj.get('bvt_artifact_seed', 0))
    seed_offsets(seed)
    settings = (seed, float(obj.get('bvt_artifact_coverage', .3)),
                float(obj.get('bvt_artifact_droplet_scale', 1.)),
                float(obj.get('bvt_hybrid_macro', .72)),
                float(obj.get('bvt_hybrid_micro', .6)),
                float(obj.get('bvt_hybrid_wetness', .6)))
    validate_hybrid_settings(*settings)
    uid = obj.get('bvt_glass_uid')
    if not uid:
        raise RuntimeError('Glass must be registered before generating atlas')
    image_name = 'BVT_Hybrid_Droplets_' + str(uid)
    signature = ','.join(f'{v:.6f}' if isinstance(v, float) else str(v) for v in settings)
    image = bpy.data.images.get(image_name)
    if image and tuple(image.size[:]) != (ATLAS_SIZE, ATLAS_SIZE):
        if image.users > 0:
            raise RuntimeError('Existing atlas has unexpected dimensions')
        bpy.data.images.remove(image)
        image = None
    if image is None:
        image = bpy.data.images.new(image_name, width=ATLAS_SIZE, height=ATLAS_SIZE,
                                    alpha=True, float_buffer=True)
        image.alpha_mode = 'CHANNEL_PACKED'
        image.colorspace_settings.name = 'Non-Color'
    if image.get('bvt_atlas_parameters') != signature:
        atlas = make_condensation_atlas(*settings)
        image.pixels.foreach_set(atlas.ravel())
        image.update()
        image['bvt_atlas_parameters'] = signature
    return image


def _math(nodes, links, operation, name, left=None, right=None, constant=None):
    node = nodes.new('ShaderNodeMath')
    node.name = name
    node.operation = operation
    if left is not None:
        links.new(left, node.inputs[0])
    if right is not None:
        links.new(right, node.inputs[1])
    if constant is not None:
        node.inputs[1].default_value = constant
    return node.outputs[0]


def _map_range(nodes, links, name, value, from_min, from_max, to_min=0., to_max=1.,
               clamp=True, interpolation='SMOOTHSTEP'):
    node = nodes.new('ShaderNodeMapRange')
    node.name = name
    node.clamp = clamp
    node.interpolation_type = interpolation
    node.inputs['From Min'].default_value = from_min
    node.inputs['From Max'].default_value = from_max
    node.inputs['To Min'].default_value = to_min
    node.inputs['To Max'].default_value = to_max
    links.new(value, node.inputs['Value'])
    return node.outputs['Result']


def _rect_mask(nodes, links, name, separate, left, right, bottom, top, feather):
    feather = max(float(feather), 1e-4)
    width = max(float(right) - float(left), feather * 2.0 + 1e-4)
    height = max(float(top) - float(bottom), feather * 2.0 + 1e-4)
    feather = min(feather, width * 0.49, height * 0.49)
    left_mask = _map_range(nodes, links, name + '_Left',
                           separate.outputs['X'], float(left), float(left) + feather)
    right_mask = _map_range(nodes, links, name + '_Right',
                            separate.outputs['X'], float(right) - feather, float(right),
                            to_min=1., to_max=0.)
    bottom_mask = _map_range(nodes, links, name + '_Bottom',
                             separate.outputs['Y'], float(bottom), float(bottom) + feather)
    top_mask = _map_range(nodes, links, name + '_Top',
                          separate.outputs['Y'], float(top) - feather, float(top),
                          to_min=1., to_max=0.)
    lr = _math(nodes, links, 'MINIMUM', name + '_LR', left=left_mask, right=right_mask)
    bt = _math(nodes, links, 'MINIMUM', name + '_BT', left=bottom_mask, right=top_mask)
    return _math(nodes, links, 'MINIMUM', name, left=lr, right=bt)


def _glass_area_mask(obj, nodes, links, uv_socket):
    inset = float(obj.get('bvt_artifact_mask_inset', .045))
    feather = max(float(obj.get('bvt_artifact_mask_feather', .030)), 1e-4)
    separate = nodes.new('ShaderNodeSeparateXYZ')
    separate.name = 'BVT_Hybrid_Glass_Mask_UV'
    links.new(uv_socket, separate.inputs['Vector'])
    return _rect_mask(nodes, links, 'BVT_Hybrid_Glass_Mask', separate,
                      inset, 1.0 - inset, inset, 1.0 - inset, feather)


def _glass_aperture_mask(obj, nodes, links, uv_socket):
    separate = nodes.new('ShaderNodeSeparateXYZ')
    separate.name = 'BVT_Hybrid_Aperture_UV'
    links.new(uv_socket, separate.inputs['Vector'])
    left = float(obj.get('bvt_artifact_aperture_left', 0.0))
    right = float(obj.get('bvt_artifact_aperture_right', 1.0))
    bottom = float(obj.get('bvt_artifact_aperture_bottom', 0.0))
    top = float(obj.get('bvt_artifact_aperture_top', 1.0))
    feather = float(obj.get('bvt_artifact_aperture_feather', 0.020))
    validate_aperture_settings(left, right, bottom, top, feather)
    return _rect_mask(nodes, links, 'BVT_Hybrid_Aperture_Mask', separate,
                      left, right, bottom, top, feather)


def _combined_glass_mask(obj, nodes, links, uv_socket):
    area = _glass_area_mask(obj, nodes, links, uv_socket)
    aperture = _glass_aperture_mask(obj, nodes, links, uv_socket)
    return _math(nodes, links, 'MINIMUM', 'BVT_Hybrid_Combined_Mask', left=area, right=aperture)


def build_hybrid_shader(obj, nodes, links, output, tex):
    """Use source-photo resampling + masked atlas normals; no legacy speckle overlays."""
    from .glass import driver_socket
    from .glass_realism import image_uv_bounds, source_for_glass

    from .droplet_maps import MODE_KEY, droplet_photo_channels
    if obj.get(MODE_KEY, 'PROCEDURAL') == 'PHOTO_MAPS' or obj.get(MODE_KEY) == 'REALISTIC_ATLAS':
        height, gx, gy, wet_film = droplet_photo_channels(
            obj, nodes, links, tex.outputs['UV'])
    else:
        atlas = ensure_atlas(obj)
        atlas_sample = nodes.new('ShaderNodeTexImage')
        atlas_sample.name = 'BVT_Hybrid_Atlas'
        atlas_sample.image = atlas
        atlas_sample.extension = 'CLIP'
        atlas_sample.interpolation = 'Linear'
        links.new(tex.outputs['UV'], atlas_sample.inputs['Vector'])
        channels = nodes.new('ShaderNodeSeparateColor')
        channels.name = 'BVT_Hybrid_Channels'
        links.new(atlas_sample.outputs['Color'], channels.inputs['Color'])
        height, gx, gy = (channels.outputs[s] for s in ('Red', 'Green', 'Blue'))
        wet_film = atlas_sample.outputs['Alpha']

    glass_mask = _combined_glass_mask(obj, nodes, links, tex.outputs['UV'])

    # Optional alpha.5-step3 optics only for the generated realistic atlas.
    # Existing procedural/photo-map shaders retain their exact original graph.
    from .optical_water import optical_enabled, optical_sockets
    optical = optical_enabled(obj)

    x = _math(nodes, links, 'SUBTRACT', 'BVT_Hybrid_Normal_X', left=gx, constant=.5)
    y = _math(nodes, links, 'SUBTRACT', 'BVT_Hybrid_Normal_Y', left=gy, constant=.5)
    glint_x = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Glint_X', left=x, constant=-1.28)
    glint_y = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Glint_Y', left=y, constant=1.10)
    glint = _math(nodes, links, 'ADD', 'BVT_Hybrid_Glint_Direction', left=glint_x, right=glint_y)
    glint = _math(nodes, links, 'MAXIMUM', 'BVT_Hybrid_Glint_Positive', left=glint, constant=0.)

    opposite = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Opposite_X', left=x, constant=1.28)
    opposite_y = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Opposite_Y', left=y, constant=-1.10)
    opposite = _math(nodes, links, 'ADD', 'BVT_Hybrid_Opposite_Direction', left=opposite, right=opposite_y)
    dark = _math(nodes, links, 'MAXIMUM', 'BVT_Hybrid_Opposite_Clamp', left=opposite, constant=0.)

    droplet_amount = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Droplet_Amount', left=height)
    driver_socket(droplet_amount.node.inputs[1], obj, 'bvt_glass_droplets')
    droplet_amount = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Droplet_Masked',
                           left=droplet_amount, right=glass_mask)
    relief_amount = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Relief_Amount', left=droplet_amount)
    driver_socket(relief_amount.node.inputs[1], obj, 'bvt_artifact_relief')

    rim_outer = _map_range(nodes, links, 'BVT_Hybrid_Rim_Outer', height, .02, .42)
    rim_inner = _map_range(nodes, links, 'BVT_Hybrid_Rim_Inner', height, .54, .96)
    rim_factor = _math(nodes, links, 'SUBTRACT', 'BVT_Hybrid_Rim_Factor', left=rim_outer, right=rim_inner)
    rim_factor = _math(nodes, links, 'MAXIMUM', 'BVT_Hybrid_Rim_Factor_Clamp', left=rim_factor, constant=0.)
    center_factor = _map_range(nodes, links, 'BVT_Hybrid_Center_Factor', height, .14, .78)
    center_factor = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Center_Masked',
                          left=center_factor, right=glass_mask)

    highlight_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Highlight_Alpha', left=glint, right=rim_factor)
    highlight_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Highlight_Relief', left=highlight_alpha, right=relief_amount)
    highlight_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Highlight_Contrast', left=highlight_alpha, constant=1.65)
    highlight_alpha = _math(nodes, links, 'MINIMUM', 'BVT_Hybrid_Highlight_Clamp', left=highlight_alpha, constant=.34)

    dark_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Dark_Alpha', left=dark, right=rim_factor)
    dark_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Dark_Relief', left=dark_alpha, right=relief_amount)
    dark_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Dark_Contrast', left=dark_alpha, constant=1.18)
    dark_alpha = _math(nodes, links, 'MINIMUM', 'BVT_Hybrid_Dark_Clamp', left=dark_alpha, constant=.22)

    if optical:
        optical_hi, optical_shadow, optical_micro = optical_sockets(
            obj, nodes, links, x, y, height, glass_mask)
        highlight_alpha = _math(nodes, links, 'ADD', 'BVT_Optical_Highlight_Sum',
                                left=highlight_alpha, right=optical_hi)
        highlight_alpha = _math(nodes, links, 'ADD', 'BVT_Optical_Micro_Specular_Sum',
                                left=highlight_alpha, right=optical_micro)
        highlight_alpha = _math(nodes, links, 'MINIMUM', 'BVT_Optical_Highlight_Safe_Clamp',
                                left=highlight_alpha, constant=.39)
        dark_alpha = _math(nodes, links, 'ADD', 'BVT_Optical_Shadow_Sum',
                           left=dark_alpha, right=optical_shadow)
        dark_alpha = _math(nodes, links, 'MINIMUM', 'BVT_Optical_Shadow_Safe_Clamp',
                           left=dark_alpha, constant=.28)

    transparent = nodes.new('ShaderNodeBsdfTransparent')
    transparent.name = 'BVT_Hybrid_Clear_Glass'
    shader = transparent.outputs['BSDF']

    haze = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Wet_Amount', left=wet_film)
    driver_socket(haze.node.inputs[1], obj, 'bvt_glass_haze')
    haze = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Wet_Opacity', left=haze, constant=.50)
    haze = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Wet_Masked', left=haze, right=glass_mask)
    film_emit = nodes.new('ShaderNodeEmission')
    film_emit.name = 'BVT_Hybrid_Wet_Emission'
    film_emit.inputs['Color'].default_value = (.61, .69, .75, 1.)
    wet_mix = nodes.new('ShaderNodeMixShader')
    wet_mix.name = 'BVT_Hybrid_Wet_Film'
    links.new(haze, wet_mix.inputs[0])
    links.new(shader, wet_mix.inputs[1])
    links.new(film_emit.outputs[0], wet_mix.inputs[2])
    shader = wet_mix.outputs[0]

    source, image = source_for_glass(obj)
    if source is not None:
        (xmin, ymin), (width, height_range) = image_uv_bounds(source)
        photo_coord = nodes.new('ShaderNodeTexCoord')
        photo_coord.name = 'BVT_Hybrid_Photo_Coordinates'
        photo_coord.object = source
        scale = nodes.new('ShaderNodeVectorMath')
        scale.name = 'BVT_Hybrid_Photo_UV_Scale'
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = (1. / width, 1. / height_range, 0.)
        links.new(photo_coord.outputs['Object'], scale.inputs[0])
        shift = nodes.new('ShaderNodeVectorMath')
        shift.name = 'BVT_Hybrid_Photo_UV_Shift'
        shift.operation = 'ADD'
        shift.inputs[1].default_value = (-xmin / width, -ymin / height_range, 0.)
        links.new(scale.outputs['Vector'], shift.inputs[0])

        normal_xy = nodes.new('ShaderNodeCombineXYZ')
        normal_xy.name = 'BVT_Hybrid_Normal_Vector'
        links.new(x, normal_xy.inputs['X'])
        links.new(y, normal_xy.inputs['Y'])
        warp = nodes.new('ShaderNodeVectorMath')
        warp.name = 'BVT_Hybrid_Normal_Refraction'
        warp.operation = 'SCALE'
        links.new(normal_xy.outputs['Vector'], warp.inputs['Vector'])
        if optical:
            from .optical_water import LENS_KEY
            # Blend the requested gain toward 1.0. Large refraction warps
            # made frozen shelf edges look like luminous circular halos.
            user_gain = _math(nodes, links, 'SUBTRACT',
                              'BVT_Optical_Refraction_Gain_Offset', constant=1.)
            driver_socket(user_gain.node.inputs[0], obj, LENS_KEY)
            delta = _math(nodes, links, 'MULTIPLY',
                          'BVT_Optical_Refraction_Gain_Softener',
                          left=user_gain, constant=.35)
            gain = _math(nodes, links, 'ADD', 'BVT_Optical_Refraction_SoftGain',
                         left=delta, constant=1.)
            lens_scale = _math(nodes, links, 'MULTIPLY',
                               'BVT_Optical_Refraction_Gain', right=gain)
            driver_socket(lens_scale.node.inputs[0], obj, 'bvt_artifact_refraction')
            links.new(lens_scale, warp.inputs['Scale'])
        else:
            driver_socket(warp.inputs['Scale'], obj, 'bvt_artifact_refraction')
        uv = nodes.new('ShaderNodeVectorMath')
        uv.name = 'BVT_Hybrid_Photo_UV_Warp'
        uv.operation = 'ADD'
        links.new(shift.outputs['Vector'], uv.inputs[0])
        links.new(warp.outputs['Vector'], uv.inputs[1])
        photo = nodes.new('ShaderNodeTexImage')
        photo.name = 'BVT_Hybrid_Refracted_Photo'
        photo.image = image
        photo.extension = 'CLIP'
        photo.interpolation = 'Linear'
        links.new(uv.outputs['Vector'], photo.inputs['Vector'])
        warped = nodes.new('ShaderNodeEmission')
        warped.name = 'BVT_Hybrid_Warped_Emission'
        links.new(photo.outputs['Color'], warped.inputs['Color'])
        opacity = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Photo_Opacity',
                        left=center_factor, right=droplet_amount)
        opacity = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Photo_Opacity_Contrast',
                        left=opacity, constant=1.85)
        opacity = _math(nodes, links, 'MINIMUM', 'BVT_Hybrid_Photo_Clamp',
                        left=opacity, constant=.42)
        opacity = _math(nodes, links, 'MULTIPLY', 'BVT_Hybrid_Photo_Within_Source',
                        left=opacity, right=photo.outputs['Alpha'])
        refr_mix = nodes.new('ShaderNodeMixShader')
        refr_mix.name = 'BVT_Hybrid_Refraction_Overlay'
        links.new(opacity, refr_mix.inputs[0])
        links.new(shader, refr_mix.inputs[1])
        links.new(warped.outputs[0], refr_mix.inputs[2])
        shader = refr_mix.outputs[0]

    shade = nodes.new('ShaderNodeEmission')
    shade.name = 'BVT_Hybrid_Dark_Rim'
    shade.inputs['Color'].default_value = (.050, .070, .090, 1.)
    shade_mix = nodes.new('ShaderNodeMixShader')
    shade_mix.name = 'BVT_Hybrid_Dark_Rim_Overlay'
    links.new(dark_alpha, shade_mix.inputs[0])
    links.new(shader, shade_mix.inputs[1])
    links.new(shade.outputs[0], shade_mix.inputs[2])
    shader = shade_mix.outputs[0]

    shine = nodes.new('ShaderNodeEmission')
    shine.name = 'BVT_Hybrid_Specular_Rim'
    shine.inputs['Color'].default_value = (.92, .97, 1., 1.)
    shine_mix = nodes.new('ShaderNodeMixShader')
    shine_mix.name = 'BVT_Hybrid_Specular_Overlay'
    links.new(highlight_alpha, shine_mix.inputs[0])
    links.new(shader, shine_mix.inputs[1])
    links.new(shine.outputs[0], shine_mix.inputs[2])
    links.new(shine_mix.outputs[0], output.inputs['Surface'])
