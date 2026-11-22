"""Per-glass external droplet maps (alpha, height, tangent-space normal).

Maps are PNGs packed into the Blender file. The user supplies the assets;
this module does NOT claim a mathematically generated map is a photograph.
The existing precision mask gates the final surface after the droplet shader.
"""
from math import cos, isfinite, radians, sin
from pathlib import Path

MODES = frozenset({'PROCEDURAL', 'PHOTO_MAPS', 'REALISTIC_ATLAS'})
KINDS = ('alpha', 'height', 'normal')
MODE_KEY = 'bvt_droplet_source_mode'
TILING_KEY = 'bvt_droplet_map_tiling'
ROTATION_KEY = 'bvt_droplet_map_rotation'


def image_key(kind, mode='PHOTO_MAPS'):
    if kind not in KINDS:
        raise ValueError('Unsupported droplet map channel: ' + str(kind))
    if mode not in ('PHOTO_MAPS', 'REALISTIC_ATLAS'):
        raise ValueError('Invalid droplet map storage mode')
    prefix = 'bvt_atlas_' if mode == 'REALISTIC_ATLAS' else 'bvt_droplet_'
    return prefix + kind + '_image'


def path_key(kind, mode='PHOTO_MAPS'):
    if kind not in KINDS or mode not in ('PHOTO_MAPS', 'REALISTIC_ATLAS'):
        raise ValueError('Invalid droplet map path channel')
    return ('bvt_atlas_' if mode == 'REALISTIC_ATLAS' else 'bvt_droplet_') + kind + '_path'


def check_transform(tiling, rotation):
    if not all(isfinite(float(v)) for v in (tiling, rotation)):
        raise ValueError('Droplet map transform must be finite')
    if not .25 <= float(tiling) <= 8.:
        raise ValueError('Droplet map tiling must be between 0.25 and 8.0')
    if not -180. <= float(rotation) <= 180.:
        raise ValueError('Droplet map rotation must be between -180 and 180 degrees')


def _glass_check(obj):
    if obj is None or obj.type != 'MESH' or obj.get('bvt_role') != 'glass_overlay':
        raise ValueError('Choose a registered BVT Glass Plane')
    if obj.library is not None or obj.data.library is not None:
        raise ValueError('Cannot change linked glass objects')


def packed_maps_for(obj, mode=None):
    """Fail closed for photo mode; never silently fall back to procedural maps."""
    import bpy
    mode = mode or obj.get(MODE_KEY, 'PHOTO_MAPS')
    if mode not in ('PHOTO_MAPS', 'REALISTIC_ATLAS'):
        raise ValueError('Packed droplet maps are not enabled for this mode')
    result = {}
    for kind in KINDS:
        name = obj.get(image_key(kind, mode))
        image = bpy.data.images.get(str(name)) if name else None
        if image is None or image.source != 'FILE' or min(image.size) < 2 or not image.packed_file:
            raise ValueError(f'{obj.name}: missing packed {kind} droplet PNG for {mode}')
        result[kind] = image
    if len({tuple(image.size) for image in result.values()}) != 1:
        raise ValueError('Droplet Alpha/Height/Normal maps must have the same dimensions')
    return result


def import_droplet_maps(obj, alpha_path, height_path, normal_path, tiling=1., rotation=0., target_mode='PHOTO_MAPS'):
    """Atomically assign independent packed PNG datablocks to one Glass Plane."""
    import bpy
    _glass_check(obj)
    check_transform(tiling, rotation)
    if target_mode not in ('PHOTO_MAPS', 'REALISTIC_ATLAS'):
        raise ValueError('Invalid map import target')
    paths = dict(zip(KINDS, (alpha_path, height_path, normal_path)))
    fullpaths = {}
    for kind, path in paths.items():
        full = Path(bpy.path.abspath(str(path))).expanduser().resolve()
        if full.suffix.lower() != '.png' or not full.is_file():
            raise ValueError(f'{kind.capitalize()} droplet map must be an existing PNG')
        fullpaths[kind] = full
    if len(set(fullpaths.values())) != 3:
        raise ValueError('Alpha, Height and Normal require three distinct PNGs')

    all_keys = tuple(image_key(k, target_mode) for k in KINDS) + tuple(path_key(k, target_mode) for k in KINDS) + (
        MODE_KEY, TILING_KEY, ROTATION_KEY,
    )
    previous = {key: obj.get(key) for key in all_keys}
    created = {}
    try:
        for kind, full in fullpaths.items():
            image = bpy.data.images.load(str(full), check_existing=False)
            created[kind] = image
            if image.file_format != 'PNG' or min(image.size) < 2:
                raise ValueError(f'{kind}: invalid PNG or dimensions')
            image.colorspace_settings.name = 'Non-Color'
            image.alpha_mode = 'CHANNEL_PACKED'
            image.name = ('BVT_Atlas_' if target_mode == 'REALISTIC_ATLAS' else 'BVT_Droplet_') + kind + '_' + str(obj.get('bvt_glass_uid', obj.name))[:20]
            image.pack()
            if not image.packed_file:
                raise RuntimeError(f'{kind}: could not pack image into .blend')
            # The map bank not selected in the active material has zero shader
            # users. Packing stores pixels but does NOT protect an orphan ID
            # across Save/Open. Fake User preserves both PHOTO_MAPS and atlas.
            image.use_fake_user = True
        if len({tuple(image.size) for image in created.values()}) != 1:
            raise ValueError('Alpha/Height/Normal maps must have identical dimensions')
        for kind, image in created.items():
            obj[image_key(kind, target_mode)] = image.name
            obj[path_key(kind, target_mode)] = ('generated://realistic_atlas/' + kind if target_mode == 'REALISTIC_ATLAS' else str(fullpaths[kind]))
        if target_mode == 'PHOTO_MAPS':
            obj[MODE_KEY] = 'PHOTO_MAPS'
        else:
            obj[MODE_KEY] = 'REALISTIC_ATLAS'
        obj[TILING_KEY] = float(tiling)
        obj[ROTATION_KEY] = float(rotation)
        from .glass import configure_glass
        configure_glass(obj)
        # Old images remain untouched until the new material is fully valid.
        for kind in KINDS:
            old_name = previous.get(image_key(kind, target_mode))
            if old_name and old_name != obj[image_key(kind, target_mode)]:
                old_image = bpy.data.images.get(str(old_name))
                # Replacing a map must still release the old orphan image;
                # Blender counts its fake user in ID.users on some versions.
                if (old_image and old_image.users <= int(old_image.use_fake_user)
                        and old_image.name.startswith(('BVT_Droplet_', 'BVT_Atlas_'))):
                    bpy.data.images.remove(old_image)
    except Exception:
        for key, old in previous.items():
            if old is None:
                if key in obj:
                    del obj[key]
            else:
                obj[key] = old
        # Restore the previous material if the final shader rebuild failed.
        try:
            from .glass import configure_glass
            configure_glass(obj)
        except Exception:
            pass
        for image in created.values():
            if image.users <= int(image.use_fake_user):
                bpy.data.images.remove(image)
        raise
    return created


def set_droplet_mode(obj, mode, tiling=None, rotation=None):
    _glass_check(obj)
    if mode not in MODES:
        raise ValueError('Invalid droplet source mode')
    tile = float(obj.get(TILING_KEY, 1.) if tiling is None else tiling)
    angle = float(obj.get(ROTATION_KEY, 0.) if rotation is None else rotation)
    check_transform(tile, angle)
    if mode in ('PHOTO_MAPS', 'REALISTIC_ATLAS'):
        packed_maps_for(obj, mode=mode)
    old = {key: obj.get(key) for key in (MODE_KEY, TILING_KEY, ROTATION_KEY)}
    try:
        obj[MODE_KEY], obj[TILING_KEY], obj[ROTATION_KEY] = mode, tile, angle
        from .glass import configure_glass
        configure_glass(obj)
    except Exception:
        for key, value in old.items():
            if value is None:
                if key in obj:
                    del obj[key]
            else:
                obj[key] = value
        try:
            from .glass import configure_glass
            configure_glass(obj)
        except Exception:
            pass
        raise


def _math(nodes, links, op, name, a=None, b=None, const=None):
    n = nodes.new('ShaderNodeMath')
    n.name, n.operation = name, op
    if a is not None:
        links.new(a, n.inputs[0])
    if b is not None:
        links.new(b, n.inputs[1])
    if const is not None:
        n.inputs[1].default_value = float(const)
    return n.outputs[0]


def droplet_photo_channels(obj, nodes, links, glass_uv):
    """Return height, encoded Gx/Gy and wet-film sockets from packed maps.

    Normal RGB is OpenGL tangent convention: R=X, G=Y (0.5 neutral).
    Alpha is grayscale RGB, not PNG file transparency, and gates relief/warp.
    UV transform is stable for each glass and works for rotated photo planes.
    """
    from .artifact_config import seed_offsets
    maps = packed_maps_for(obj, mode=obj.get(MODE_KEY, 'PHOTO_MAPS'))
    tiling = float(obj.get(TILING_KEY, 1.))
    rotation = float(obj.get(ROTATION_KEY, 0.))
    check_transform(tiling, rotation)
    seed = int(obj.get('bvt_artifact_seed', 0))

    rotate = nodes.new('ShaderNodeVectorRotate')
    rotate.name = 'BVT_Photo_Droplet_UV_Rotate'
    rotate.rotation_type = 'AXIS_ANGLE'
    rotate.inputs['Center'].default_value = (.5, .5, 0.)
    rotate.inputs['Axis'].default_value = (0., 0., 1.)
    rotate.inputs['Angle'].default_value = radians(rotation)
    links.new(glass_uv, rotate.inputs['Vector'])
    tile = nodes.new('ShaderNodeVectorMath')
    tile.name, tile.operation = 'BVT_Photo_Droplet_UV_Tiling', 'SCALE'
    tile.inputs['Scale'].default_value = tiling
    links.new(rotate.outputs['Vector'], tile.inputs['Vector'])
    shift = nodes.new('ShaderNodeVectorMath')
    shift.name, shift.operation = 'BVT_Photo_Droplet_UV_Seed', 'ADD'
    shift.inputs[1].default_value = seed_offsets(seed)
    links.new(tile.outputs['Vector'], shift.inputs[0])

    samples = {}
    for kind, image in maps.items():
        n = nodes.new('ShaderNodeTexImage')
        n.name = 'BVT_Photo_Droplet_' + kind.title()
        n.image = image
        n.extension = 'REPEAT'
        n.interpolation = 'Linear'
        links.new(shift.outputs['Vector'], n.inputs['Vector'])
        samples[kind] = n

    alpha = nodes.new('ShaderNodeRGBToBW')
    alpha.name = 'BVT_Photo_Droplet_Alpha_Grayscale'
    links.new(samples['alpha'].outputs['Color'], alpha.inputs['Color'])
    a = alpha.outputs['Val']

    height = nodes.new('ShaderNodeRGBToBW')
    height.name = 'BVT_Photo_Droplet_Height_Grayscale'
    links.new(samples['height'].outputs['Color'], height.inputs['Color'])
    h = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Height_Masked', height.outputs['Val'], a)
    normal = nodes.new('ShaderNodeSeparateColor')
    normal.name = 'BVT_Photo_Droplet_Normal_Channels'
    links.new(samples['normal'].outputs['Color'], normal.inputs['Color'])

    # Unpack normal map XY, gate by droplet alpha, then rotate slopes with UV.
    nx = _math(nodes, links, 'SUBTRACT', 'BVT_Photo_Droplet_Nx', normal.outputs['Red'], const=.5)
    ny = _math(nodes, links, 'SUBTRACT', 'BVT_Photo_Droplet_Ny', normal.outputs['Green'], const=.5)
    cos_t, sin_t = cos(radians(rotation)), sin(radians(rotation))
    xx = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Nxx', nx, const=cos_t)
    xy = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Nxy', ny, const=-sin_t)
    yx = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Nyx', nx, const=sin_t)
    yy = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Nyy', ny, const=cos_t)
    rx = _math(nodes, links, 'ADD', 'BVT_Photo_Droplet_Rotated_X', xx, xy)
    ry = _math(nodes, links, 'ADD', 'BVT_Photo_Droplet_Rotated_Y', yx, yy)
    rx = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Rotated_X_Masked', rx, a)
    ry = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Rotated_Y_Masked', ry, a)
    gx = _math(nodes, links, 'ADD', 'BVT_Photo_Droplet_Gx_Encoded', rx, const=.5)
    gy = _math(nodes, links, 'ADD', 'BVT_Photo_Droplet_Gy_Encoded', ry, const=.5)
    wet = _math(nodes, links, 'MULTIPLY', 'BVT_Photo_Droplet_Wet_Film', a, const=.22)
    return h, gx, gy, wet


# Blender operators stay in this module so photo-map support does not touch YOLO.
import bpy


class BVTSTUDIO_OT_assign_droplet_maps(bpy.types.Operator):
    bl_idname = 'bvt_studio.assign_droplet_maps'
    bl_label = 'Import & Pack Droplet Maps'
    bl_description = 'Import three registered Alpha/Height/Normal PNG maps for selected glass only'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            import_droplet_maps(obj, settings.droplet_alpha_path,
                                settings.droplet_height_path,
                                settings.droplet_normal_path,
                                settings.droplet_map_tiling,
                                settings.droplet_map_rotation)
            self.report({'INFO'}, f'{obj.name}: packed Alpha/Height/Normal; mode=PHOTO_MAPS')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Droplet maps: {exc}')
            return {'CANCELLED'}


class BVTSTUDIO_OT_use_droplet_photos(bpy.types.Operator):
    bl_idname = 'bvt_studio.use_droplet_photos'
    bl_label = 'Use Photographic Droplet Maps'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            set_droplet_mode(obj, 'PHOTO_MAPS', settings.droplet_map_tiling,
                             settings.droplet_map_rotation)
            self.report({'INFO'}, f'{obj.name}: photographic maps enabled')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Photo droplet maps: {exc}')
            return {'CANCELLED'}


class BVTSTUDIO_OT_use_droplet_procedural(bpy.types.Operator):
    bl_idname = 'bvt_studio.use_droplet_procedural'
    bl_label = 'Use Procedural Droplets'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            set_droplet_mode(obj, 'PROCEDURAL')
            self.report({'INFO'}, f'{obj.name}: procedural droplets enabled')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Procedural droplets: {exc}')
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_assign_droplet_maps,
           BVTSTUDIO_OT_use_droplet_photos,
           BVTSTUDIO_OT_use_droplet_procedural)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
