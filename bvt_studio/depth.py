"""Photo-relative 2.5D layer depth guards (Blender 5.2+).

A Blender Limit Location constraint in CUSTOM owner space uses the image
Plane's transform as the reference frame. This is robust to rotating the
photo object and avoids relying on WORLD Z. No depsgraph/timer handler is used.

These guards protect OBJECT origins during interactive transforms; they are
not a security boundary for external Python scripts, mesh Edit Mode or rigs.
"""
import math

import bpy
from mathutils import Vector

from .common import ensure_collection, get_source, scene_annotations
from .glass import scene_glass

DEPTH_CONSTRAINT = 'BVT_Studio_Photo_Relative_Depth'
CONSTRAINT_MARKER = '_bvt_studio_owns_depth_constraint'
FRAME_ROLE = 'bvt_studio_depth_frame'
OFFSET_KEY = 'bvt_studio_depth_offset_m'
FRAME_SOURCE_KEY = 'bvt_studio_depth_frame_source'
DEFAULT_GLASS_M = 0.012
DEFAULT_ANNOTATION_M = 0.030
MIN_AXIS_LENGTH = 1e-8


def _photo_axis(source):
    """Return unit photo normal and meters per photo-local Z unit.

    Derive the normal from transformed X/Y tangents, not the transformed Z
    axis: parent-induced shear would otherwise distort metric offsets.
    """
    basis = source.matrix_world.to_3x3()
    ex = basis @ Vector((1.0, 0.0, 0.0))
    ey = basis @ Vector((0.0, 1.0, 0.0))
    ez = basis @ Vector((0.0, 0.0, 1.0))
    normal = ex.cross(ey)
    if normal.length < MIN_AXIS_LENGTH:
        raise ValueError('Photo plane has degenerate X/Y axes')
    normal.normalize()
    z_scale = normal.dot(ez)
    if abs(z_scale) < MIN_AXIS_LENGTH:
        raise ValueError('Photo plane has degenerate Z axis')
    if z_scale < 0:
        normal.negate()
        z_scale = -z_scale
    return normal, z_scale


def _camera_side(scene, source):
    """Which sign of photo's +Z points towards the current camera?"""
    cam = scene.camera
    if cam is None:
        return 1.0
    normal, _ = _photo_axis(source)
    direction = cam.matrix_world.translation - source.matrix_world.translation
    return 1.0 if direction.dot(normal) >= 0.0 else -1.0


def _local_z(source, world_location):
    return (source.matrix_world.inverted_safe() @ world_location).z


def _world_meters_to_local_z(meters, axis_scale, side):
    """Convert distance along camera-facing photo normal to photo local Z."""
    if axis_scale <= MIN_AXIS_LENGTH or not math.isfinite(meters):
        raise ValueError('Invalid photo scale or depth offset')
    return (meters / axis_scale) * side


def _managed_object(obj, scene):
    member = scene.objects.get(obj.name) if obj is not None else None
    return (member is not None and member.as_pointer() == obj.as_pointer() and
            obj.library is None and len(obj.users_scene) <= 1)


def _get_frame(scene, source, create):
    """Frozen coordinate basis for PHOTO depth, avoiding a self-reference cycle."""
    for obj in scene.objects:
        if obj.type == 'EMPTY' and obj.get(FRAME_ROLE):
            if obj.get(FRAME_SOURCE_KEY) != source.name:
                # A different photo was explicitly registered in the scene.
                # Old photo constraints must be discarded before rebasing.
                old_source = bpy.data.objects.get(obj.get(FRAME_SOURCE_KEY, ''))
                if old_source and scene.objects.get(old_source.name) is not None:
                    old_limit = old_source.constraints.get(DEPTH_CONSTRAINT)
                    if old_limit and old_source.get(CONSTRAINT_MARKER, False):
                        old_source.constraints.remove(old_limit)
                obj.matrix_world = source.matrix_world.copy()
                obj[FRAME_SOURCE_KEY] = source.name
            return obj
    if not create:
        return None
    frame = bpy.data.objects.new('BVT_Studio_Depth_Frame', None)
    ensure_collection(scene, 'BVT_Studio_Controls').objects.link(frame)
    frame.empty_display_type = 'PLAIN_AXES'
    frame.empty_display_size = 0.002
    frame.hide_render = True
    frame.hide_select = True
    frame[FRAME_ROLE] = True
    frame[FRAME_SOURCE_KEY] = source.name
    frame.matrix_world = source.matrix_world.copy()
    # Do not hide_viewport: constraints still require a valid evaluated target.
    return frame


def _set_limit(obj, reference, local_z, enabled):
    """Own exactly one constraint; never overwrite user-authored constraints."""
    con = obj.constraints.get(DEPTH_CONSTRAINT)
    if con is not None and (con.type != 'LIMIT_LOCATION' or
                            not obj.get(CONSTRAINT_MARKER, False)):
        raise RuntimeError(f'{obj.name}: constraint name {DEPTH_CONSTRAINT} is in use')
    if con is None:
        if not enabled:
            return
        con = obj.constraints.new(type='LIMIT_LOCATION')
        con.name = DEPTH_CONSTRAINT
        obj[CONSTRAINT_MARKER] = True
    con.space_object = reference
    con.owner_space = 'CUSTOM'
    con.use_min_x = con.use_max_x = False
    con.use_min_y = con.use_max_y = False
    con.use_min_z = True
    con.use_max_z = True
    con.min_z = con.max_z = float(local_z)
    con.use_transform_limit = True
    con.influence = 1.0
    con.mute = not enabled


def _init_layer_offset(obj, scene, source, default_m):
    """Preserve legacy layer depth, rather than unexpectedly moving old scenes."""
    existing = obj.get(OFFSET_KEY)
    try:
        if existing is not None and math.isfinite(float(existing)):
            return float(existing)
    except (ValueError, TypeError):
        pass
    _, scale = _photo_axis(source)
    current = _local_z(source, obj.matrix_world.translation)
    offset = current * scale * _camera_side(scene, source)
    if abs(offset) < 0.0001:
        # Legacy coplanar objects stay at their current Z until Reset is used.
        offset = 0.0
    obj[OFFSET_KEY] = float(offset)
    obj['bvt_studio_depth_recommended_m'] = default_m
    return offset


def sync_depth_constraints(scene):
    """Apply photo-relative guards; independent of Scene Editing selection locks."""
    if not hasattr(scene, 'bvt_studio'):
        return 0
    settings = scene.bvt_studio
    source = get_source(scene)
    if source is None or not _managed_object(source, scene):
        # If source is removed, never leave our constraints targeting old photo.
        for obj in scene.objects:
            con = obj.constraints.get(DEPTH_CONSTRAINT)
            if con and obj.get(CONSTRAINT_MARKER, False):
                con.mute = True
        return 0
    _, scale = _photo_axis(source)
    side = _camera_side(scene, source)
    groups = ((scene_glass(scene), settings.glass_depth_lock, DEFAULT_GLASS_M),
              (scene_annotations(scene), settings.annotations_depth_lock,
               DEFAULT_ANNOTATION_M))
    valid = [(obj, enabled, default_m) for group, enabled, default_m in groups
             for obj in group if _managed_object(obj, scene) and obj != source]

    # Do not create a frame until it is needed. Existing frame is safe on re-runs.
    frame = _get_frame(scene, source, bool(settings.photo_depth_lock))
    if frame is not None:
        _set_limit(source, frame, 0.0, settings.photo_depth_lock)
    for obj, enabled, default_m in valid:
        offset = _init_layer_offset(obj, scene, source, default_m)
        local_z = _world_meters_to_local_z(offset, scale, side)
        _set_limit(obj, source, local_z, enabled)

    # Objects that have lost their annotation/glass role should not stay pinned.
    active_ptrs = {source.as_pointer()} | {obj.as_pointer() for obj, _, _ in valid}
    for obj in scene.objects:
        if obj.as_pointer() not in active_ptrs:
            con = obj.constraints.get(DEPTH_CONSTRAINT)
            if con and obj.get(CONSTRAINT_MARKER, False):
                con.mute = True
    return len(valid) + (1 if frame else 0)


def on_depth_settings_changed(settings, context):
    if context is not None and context.scene is not None:
        if settings.as_pointer() == context.scene.bvt_studio.as_pointer():
            sync_depth_constraints(context.scene)


def _move_to_offset(obj, source, distance_m, side):
    """Translate along the *true* normal only, preserving photo-parallel XY."""
    normal, _ = _photo_axis(source)
    original = obj.matrix_world.copy()
    current = (original.translation - source.matrix_world.translation).dot(normal)
    wanted = distance_m * side
    original.translation += normal * (wanted - current)
    obj.matrix_world = original


class BVTSTUDIO_OT_apply_glass_depth(bpy.types.Operator):
    bl_idname = 'bvt_studio.apply_glass_depth'
    bl_label = 'Apply Glass Depth Offset'
    bl_description = 'Set selected glass origin along the photo normal without changing its XY'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        settings = scene.bvt_studio
        obj = settings.depth_target_glass or context.active_object
        if obj is None or obj not in scene_glass(scene):
            self.report({'ERROR'}, 'Choose a Glass Plane in Depth Target')
            return {'CANCELLED'}
        source = get_source(scene)
        if source is None or not _managed_object(obj, scene):
            self.report({'ERROR'}, 'Missing photo or glass belongs to another scene')
            return {'CANCELLED'}
        try:
            value = float(settings.glass_depth_offset_m)
            side = _camera_side(scene, source)
            # Custom constraint may be active; snap target and source transforms.
            own_limit = obj.constraints.get(DEPTH_CONSTRAINT)
            if own_limit and obj.get(CONSTRAINT_MARKER, False):
                own_limit.mute = True
            try:
                obj[OFFSET_KEY] = value
                _move_to_offset(obj, source, value, side)
            finally:
                sync_depth_constraints(scene)
            context.view_layer.update()
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'{obj.name}: glass offset = {value:.4f} m')
        return {'FINISHED'}


class BVTSTUDIO_OT_reset_layer_depth(bpy.types.Operator):
    bl_idname = 'bvt_studio.reset_layer_depth'
    bl_label = 'Reset Layer Depth'
    bl_description = 'Restore Photo/Glass/Annotation depth without changing their in-plane position'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        source = get_source(scene)
        if source is None or not _managed_object(source, scene):
            self.report({'ERROR'}, 'Missing editable source photo')
            return {'CANCELLED'}
        try:
            frame = _get_frame(scene, source, True)
            layers = [o for o in scene_glass(scene) + scene_annotations(scene)
                      if _managed_object(o, scene)]
            for obj in [source] + layers:
                c = obj.constraints.get(DEPTH_CONSTRAINT)
                if c and obj.get(CONSTRAINT_MARKER, False):
                    c.mute = True
            try:
                # Undo accidental drift normal to the ORIGINAL photo reference.
                ref_normal, _ = _photo_axis(frame)
                matrix = source.matrix_world.copy()
                delta = (matrix.translation - frame.matrix_world.translation).dot(ref_normal)
                matrix.translation -= ref_normal * delta
                source.matrix_world = matrix
                # Rebase normal after an intentional rotation of the photo.
                frame.matrix_world = source.matrix_world.copy()
                side = _camera_side(scene, source)
                glass_ptrs = {obj.as_pointer() for obj in scene_glass(scene)}
                for obj in layers:
                    default_m = (DEFAULT_GLASS_M if obj.as_pointer() in glass_ptrs
                                 else DEFAULT_ANNOTATION_M)
                    old = obj.get(OFFSET_KEY)
                    try:
                        offset = float(old)
                        if not math.isfinite(offset) or abs(offset) < 0.0001:
                            offset = default_m
                    except (ValueError, TypeError):
                        offset = default_m
                    obj[OFFSET_KEY] = offset
                    _move_to_offset(obj, source, offset, side)
            finally:
                sync_depth_constraints(scene)
            context.view_layer.update()
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'BVT layer depths restored relative to photo')
        return {'FINISHED'}


CLASSES = (BVTSTUDIO_OT_apply_glass_depth, BVTSTUDIO_OT_reset_layer_depth)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    # Do not remove our constraints on disable; mute them so saved scenes can
    # still be opened without permanently clamping transforms in Blender.
    for obj in bpy.data.objects:
        con = obj.constraints.get(DEPTH_CONSTRAINT)
        if con is not None and obj.get(CONSTRAINT_MARKER, False):
            con.mute = True
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
