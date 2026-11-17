"""2.5D render-only relief, crystalline frost and photo-backed droplet warping.

No geometry edits. No physical ray refraction: a copy of the source photo is
sampled at slightly displaced, photo-local UVs only inside droplet masks.
The optical component is skipped for photo planes with non-affine UV mapping.
"""
from math import isfinite
from .common import get_source, image_from_mesh


def image_uv_bounds(source):
    """Return rect UV transform only when source has the default affine XY UVs.

    Arbitrary imported photo meshes can have UV islands or perspectives; never
    silently sample those with a wrong XY projection.
    """
    if source is None or source.type != 'MESH' or not source.data.uv_layers.active:
        return None
    vertices = source.data.vertices
    if len(vertices) != 4:
        return None
    bounds = [(min(v.co[i] for v in vertices), max(v.co[i] for v in vertices))
              for i in (0, 1, 2)]
    (xmin, xmax), (ymin, ymax), (zmin, zmax) = bounds
    if not all(isfinite(float(v)) for pair in bounds for v in pair):
        return None
    if xmax - xmin < 1.e-6 or ymax - ymin < 1.e-6 or zmax - zmin > 1.e-5:
        return None
    uv = source.data.uv_layers.active.data
    for poly in source.data.polygons:
        for index in poly.loop_indices:
            vertex = vertices[source.data.loops[index].vertex_index].co
            expected = ((vertex.x - xmin) / (xmax - xmin),
                        (vertex.y - ymin) / (ymax - ymin))
            actual = uv[index].uv
            if abs(actual[0] - expected[0]) > 1.e-4 or abs(actual[1] - expected[1]) > 1.e-4:
                return None
    return ((xmin, ymin), (xmax - xmin, ymax - ymin))


def source_for_glass(obj):
    """Do not take a photo from some other scene sharing this Blender file."""
    import bpy
    for scene in bpy.data.scenes:
        if scene.objects.get(obj.name) is obj:
            source = get_source(scene)
            image = image_from_mesh(source) if source is not None else None
            if image is not None and image_uv_bounds(source) is not None:
                return source, image
    return None, None


def _math(nodes, links, op, name, left=None, right=None, value=None):
    n = nodes.new('ShaderNodeMath')
    n.name = name
    n.operation = op
    if left is not None:
        links.new(left, n.inputs[0])
    if right is not None:
        links.new(right, n.inputs[1])
    if value is not None:
        n.inputs[1].default_value = value
    return n.outputs[0]


def build_realistic_glass(obj, nodes, links, base_shader, output, uv_texture,
                          seeded_uv, droplet_strength, frost_union, frost_amount):
    """Add lighting-independent visual cues and optional source-image warp.

    Drivers read per-object properties; preset changes do not touch image,
    camera, other glass materials or YOLO annotations.
    """
    from .glass import driver_socket

    # Voronoi distance transitions give smooth rings. A ring is strongest near
    # the mask's edge; the core and exterior remain clear.
    ring_sockets = []
    mask_sockets = []
    for suffix, weight in (('', .72), ('_Fine', .26), ('_Large', .95)):
        mask = nodes['BVT_Droplets_Mask' + suffix].outputs['Result']
        mask_sockets.append(mask)
        inv = _math(nodes, links, 'SUBTRACT', 'BVT_Rim_Inverse' + suffix, right=mask)
        inv.node.inputs[0].default_value = 1.0
        ring = _math(nodes, links, 'MULTIPLY', 'BVT_Rim_Band' + suffix,
                     left=mask, right=inv)
        weighted = _math(nodes, links, 'MULTIPLY', 'BVT_Rim_Weight' + suffix,
                         left=ring, value=4.0 * weight)
        ring_sockets.append(weighted)
    ring = _math(nodes, links, 'ADD', 'BVT_Rim_MediumFine',
                 left=ring_sockets[0], right=ring_sockets[1])
    ring = _math(nodes, links, 'ADD', 'BVT_Rim_All',
                 left=ring, right=ring_sockets[2])
    relief = _math(nodes, links, 'MULTIPLY', 'BVT_Rim_Relief', left=ring)
    driver_socket(relief.node.inputs[1], obj, 'bvt_artifact_relief')
    rim_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Rim_Visible',
                      left=relief, right=droplet_strength)
    rim_alpha = _math(nodes, links, 'MINIMUM', 'BVT_Rim_AlphaClamp',
                      left=rim_alpha, value=.92)

    # Color contrast gives an apparent bevel even in the unlit, orthographic
    # BVT photo setup. This is a visual relief cue, not true geometric bump.
    rim_color = nodes.new('ShaderNodeMixRGB')
    rim_color.name = 'BVT_Rim_HighlightShadow'
    rim_color.blend_type = 'MIX'
    rim_color.inputs['Color1'].default_value = (.12, .20, .29, 1.0)
    rim_color.inputs['Color2'].default_value = (.92, .97, 1.0, 1.0)
    links.new(mask_sockets[0], rim_color.inputs['Fac'])
    rim_emission = nodes.new('ShaderNodeEmission')
    rim_emission.name = 'BVT_Rim_Emission'
    links.new(rim_color.outputs['Color'], rim_emission.inputs['Color'])

    # Crystalline branching: nearest-cell edge network at two spatial scales,
    # gated by existing frost islands/edge so clean glass stays clean.
    veins = []
    for suffix, scale, width in (('', 26.0, .055), ('_Fine', 81.0, .028)):
        v = nodes.new('ShaderNodeTexVoronoi')
        v.name = 'BVT_Frost_Branches' + suffix
        v.feature = 'DISTANCE_TO_EDGE'
        v.inputs['Scale'].default_value = scale
        links.new(seeded_uv, v.inputs['Vector'])
        band = nodes.new('ShaderNodeMapRange')
        band.name = 'BVT_Frost_Branch_Mask' + suffix
        band.clamp = True
        band.interpolation_type = 'SMOOTHSTEP'
        band.inputs['From Min'].default_value = .004
        band.inputs['From Max'].default_value = width
        band.inputs['To Min'].default_value = 1.0
        band.inputs['To Max'].default_value = 0.0
        links.new(v.outputs['Distance'], band.inputs['Value'])
        veins.append(band.outputs['Result'])
    web = _math(nodes, links, 'MAXIMUM', 'BVT_Frost_Branches_Merge',
                left=veins[0], right=veins[1])
    web = _math(nodes, links, 'MULTIPLY', 'BVT_Frost_Branches_Gated',
                left=web, right=frost_union)
    frost_web_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Frost_Branches_Alpha',
                            left=web, right=frost_amount)
    frost_web_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Frost_Branches_Contrast',
                            left=frost_web_alpha, value=.85)
    frost_emission = nodes.new('ShaderNodeEmission')
    frost_emission.name = 'BVT_Frost_Crystal_Glint'
    frost_emission.inputs['Color'].default_value = (.80, .91, 1.0, 1.0)
    with_frost = nodes.new('ShaderNodeMixShader')
    with_frost.name = 'BVT_Crystalline_Overlay'
    links.new(frost_web_alpha, with_frost.inputs[0])
    links.new(base_shader, with_frost.inputs[1])
    links.new(frost_emission.outputs[0], with_frost.inputs[2])
    base_shader = with_frost.outputs[0]

    # Soft moisture islands interrupt the otherwise regular micro-droplet field.
    # Their broad, seeded silhouette gives cold fog some spatial structure.
    moisture = nodes.new('ShaderNodeTexNoise')
    moisture.name = 'BVT_Condensation_Wet_Patches'
    moisture.inputs['Scale'].default_value = 7.0
    moisture.inputs['Detail'].default_value = 4.0
    links.new(seeded_uv, moisture.inputs['Vector'])
    damp_mask = nodes.new('ShaderNodeMapRange')
    damp_mask.name = 'BVT_Condensation_Wet_Mask'
    damp_mask.interpolation_type = 'SMOOTHSTEP'
    damp_mask.clamp = True
    damp_mask.inputs['From Min'].default_value = .47
    damp_mask.inputs['From Max'].default_value = .74
    links.new(moisture.outputs['Fac'], damp_mask.inputs['Value'])
    wet_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Condensation_Amount',
                      left=damp_mask.outputs['Result'])
    driver_socket(wet_alpha.node.inputs[1], obj, 'bvt_glass_haze')
    wet_alpha = _math(nodes, links, 'MULTIPLY', 'BVT_Condensation_Contrast',
                      left=wet_alpha, value=1.5)
    wet_emission = nodes.new('ShaderNodeEmission')
    wet_emission.name = 'BVT_Condensation_Emission'
    wet_emission.inputs['Color'].default_value = (.67, .78, .85, 1.0)
    wet_overlay = nodes.new('ShaderNodeMixShader')
    wet_overlay.name = 'BVT_Condensation_Overlay'
    links.new(wet_alpha, wet_overlay.inputs[0])
    links.new(base_shader, wet_overlay.inputs[1])
    links.new(wet_emission.outputs[0], wet_overlay.inputs[2])
    base_shader = wet_overlay.outputs[0]

    source, image = source_for_glass(obj)
    if source is not None:
        (xmin, ymin), (width, height) = image_uv_bounds(source)
        # Object coordinates are computed in the Photo Plane's local frame,
        # including rotated/transformed photos and non-default glass positions.
        photo_coordinates = nodes.new('ShaderNodeTexCoord')
        photo_coordinates.name = 'BVT_Photo_Object_Coordinates'
        photo_coordinates.object = source
        scale = nodes.new('ShaderNodeVectorMath')
        scale.name = 'BVT_Photo_UV_Scale'
        scale.operation = 'MULTIPLY'
        scale.inputs[1].default_value = (1.0/width, 1.0/height, 0.0)
        links.new(photo_coordinates.outputs['Object'], scale.inputs[0])
        shift = nodes.new('ShaderNodeVectorMath')
        shift.name = 'BVT_Photo_UV_Offset'
        shift.operation = 'ADD'
        shift.inputs[1].default_value = (-xmin/width, -ymin/height, 0.0)
        links.new(scale.outputs['Vector'], shift.inputs[0])

        # Reproject a *single source photo*, not the previous glass pass;
        # locally perturb it only within condensate/droplet footprints.
        noise = nodes.new('ShaderNodeTexNoise')
        noise.name = 'BVT_Refraction_Noise'
        noise.inputs['Scale'].default_value = 36.0
        noise.inputs['Detail'].default_value = 3.0
        links.new(seeded_uv, noise.inputs['Vector'])
        center = nodes.new('ShaderNodeVectorMath')
        center.name = 'BVT_Refraction_Centered_Noise'
        center.operation = 'SUBTRACT'
        center.inputs[1].default_value = (.5, .5, .5)
        links.new(noise.outputs['Color'], center.inputs[0])
        refr_amp = nodes.new('ShaderNodeVectorMath')
        refr_amp.name = 'BVT_Refraction_Amplitude'
        refr_amp.operation = 'SCALE'
        links.new(center.outputs['Vector'], refr_amp.inputs['Vector'])
        driver_socket(refr_amp.inputs['Scale'], obj, 'bvt_artifact_refraction')
        mask_union = _math(nodes, links, 'MAXIMUM', 'BVT_Refraction_Mask_1',
                           left=mask_sockets[0], right=mask_sockets[1])
        mask_union = _math(nodes, links, 'MAXIMUM', 'BVT_Refraction_Mask_2',
                           left=mask_union, right=mask_sockets[2])
        photo_warp = nodes.new('ShaderNodeVectorMath')
        photo_warp.name = 'BVT_Refraction_Masked_Warp'
        photo_warp.operation = 'SCALE'
        links.new(refr_amp.outputs['Vector'], photo_warp.inputs['Vector'])
        links.new(mask_union, photo_warp.inputs['Scale'])
        uv_warped = nodes.new('ShaderNodeVectorMath')
        uv_warped.name = 'BVT_Refraction_Source_UV'
        uv_warped.operation = 'ADD'
        links.new(shift.outputs['Vector'], uv_warped.inputs[0])
        links.new(photo_warp.outputs['Vector'], uv_warped.inputs[1])
        sample = nodes.new('ShaderNodeTexImage')
        sample.name = 'BVT_Refracted_Source_Photo'
        sample.image = image
        sample.extension = 'CLIP'
        sample.interpolation = 'Linear'
        links.new(uv_warped.outputs['Vector'], sample.inputs['Vector'])
        warped_emission = nodes.new('ShaderNodeEmission')
        warped_emission.name = 'BVT_Refraction_Emission'
        links.new(sample.outputs['Color'], warped_emission.inputs['Color'])
        refr_mask = _math(nodes, links, 'MULTIPLY', 'BVT_Refraction_Mask_Strength',
                          left=mask_union, right=droplet_strength)
        refr_mask = _math(nodes, links, 'MULTIPLY', 'BVT_Refraction_Visibility',
                          left=refr_mask, value=1.8)
        refr_mask = _math(nodes, links, 'MINIMUM', 'BVT_Refraction_AlphaClamp',
                          left=refr_mask, value=.9)
        # Photo pixels outside the image are never rendered as black/glass.
        refr_mask = _math(nodes, links, 'MULTIPLY', 'BVT_Refraction_ImageAlpha',
                          left=refr_mask, right=sample.outputs['Alpha'])
        refr_mix = nodes.new('ShaderNodeMixShader')
        refr_mix.name = 'BVT_Local_Photo_Refraction'
        links.new(refr_mask, refr_mix.inputs[0])
        links.new(base_shader, refr_mix.inputs[1])
        links.new(warped_emission.outputs[0], refr_mix.inputs[2])
        base_shader = refr_mix.outputs[0]

    rim_overlay = nodes.new('ShaderNodeMixShader')
    rim_overlay.name = 'BVT_Droplet_Relief_Overlay'
    links.new(rim_alpha, rim_overlay.inputs[0])
    links.new(base_shader, rim_overlay.inputs[1])
    links.new(rim_emission.outputs[0], rim_overlay.inputs[2])
    links.new(rim_overlay.outputs[0], output.inputs['Surface'])
