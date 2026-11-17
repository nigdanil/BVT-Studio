"""Non-destructive per-group viewport selection/transform guards.

Selection/rotation/scale guards complement photo-relative depth constraints.
Normal depth uses its own constraint in depth.py rather than global Z locking.
"""

import json

import bpy

from .common import get_source, scene_annotations
from .glass import scene_glass

LOCK_MARKER = '_bvt_studio_lock_snapshot_v1'
MODES_BEFORE_ANNOTATION = '_bvt_studio_edit_modes_before_annotation'
GROUP_FIELDS = (
    ('photo', 'photo_edit_enable'),
    ('camera', 'camera_edit_enable'),
    ('light', 'light_edit_enable'),
    ('glass', 'glass_edit_enable'),
    ('annotations', 'annotations_edit_enable'),
)

# Prevent callback storms while a preset updates several RNA properties.
SUSPEND_UPDATES = False


def _is_local(obj):
    if obj is None or getattr(obj, 'library', None) is not None:
        return False
    # Blender Object lock flags are datablock-wide, not per-scene. Avoid
    # modifying shared objects visible in unrelated scenes.
    return len(getattr(obj, 'users_scene', (None,))) <= 1


def managed_groups(scene):
    """Manage BVT objects only; never touch unrelated user scene objects."""
    grouped = {key: [] for key, _ in GROUP_FIELDS}
    used = set()

    def add(group, obj):
        if obj is None or not _is_local(obj):
            return
        ptr = obj.as_pointer()
        if ptr not in used:
            used.add(ptr)
            grouped[group].append(obj)

    add('photo', get_source(scene))
    if scene.camera is not None and (
            scene.camera.name.startswith('BVT_Studio_Camera') or
            scene.camera.get('bvt_role') == 'studio_camera'):
        add('camera', scene.camera)

    for obj in scene.objects:
        if obj.type == 'LIGHT' and (
                obj.name.startswith('BVT_') or
                obj.get('bvt_role') == 'studio_light'):
            add('light', obj)

    for obj in scene_glass(scene):
        add('glass', obj)
    for obj in scene_annotations(scene):
        add('annotations', obj)
    return grouped


def _capture(obj):
    """Save the user's actual Blender restrictions before the first lock."""
    return json.dumps({
        'hide_select': bool(obj.hide_select),
        'location': [bool(v) for v in obj.lock_location],
        'rotation': [bool(v) for v in obj.lock_rotation],
        'scale': [bool(v) for v in obj.lock_scale],
        'rotation_w': bool(obj.lock_rotation_w),
        'rotations_4d': bool(obj.lock_rotations_4d),
    }, sort_keys=True)


def _restore(obj):
    saved = obj.get(LOCK_MARKER)
    if saved is None:
        return False
    data = json.loads(str(saved))
    obj.hide_select = data['hide_select']
    obj.lock_location = data['location']
    obj.lock_rotation = data['rotation']
    obj.lock_scale = data['scale']
    obj.lock_rotation_w = data['rotation_w']
    obj.lock_rotations_4d = data['rotations_4d']
    del obj[LOCK_MARKER]
    return True


def _protect(obj):
    if obj.get(LOCK_MARKER) is None:
        obj[LOCK_MARKER] = _capture(obj)
    obj.hide_select = True
    obj.lock_location = (True, True, True)
    obj.lock_rotation = (True, True, True)
    obj.lock_scale = (True, True, True)
    obj.lock_rotation_w = True
    # Keep the user's 4D rotation mode unchanged; this is a selection/transform lock.


def _sync_depth(scene):
    # Deferred import avoids a cycle between depth and scene registration.
    from .depth import sync_depth_constraints
    sync_depth_constraints(scene)


def apply_scene_locks(scene):
    """Apply or restore locks for objects belonging to the active BVT scene.

    Blender lock flags block manual transforms, not direct Python modification.
    Therefore camera framing, glass shaders and YOLO export remain callable.
    """
    settings = scene.bvt_studio
    groups = managed_groups(scene)
    active = bool(settings.scene_locks_enabled)
    touched = set()
    for group, prop in GROUP_FIELDS:
        edit_enabled = bool(getattr(settings, prop))
        for obj in groups[group]:
            touched.add(obj.as_pointer())
            if active and not edit_enabled:
                _protect(obj)
            else:
                _restore(obj)

    # A formerly registered object can be moved to another collection / role.
    # Do not leave it accidentally locked in the scene.
    for obj in scene.objects:
        if obj.as_pointer() not in touched and _is_local(obj) and obj.get(LOCK_MARKER) is not None:
            _restore(obj)
    # Scene selection guards and normal-depth guards are independent. New
    # glass/annotation objects are registered through this central pathway.
    _sync_depth(scene)
    return groups


def on_group_settings_changed(settings, context):
    if SUSPEND_UPDATES or context is None or context.scene is None:
        return
    scene = context.scene
    if scene.bvt_studio.as_pointer() != settings.as_pointer():
        return
    apply_scene_locks(scene)


def _set_preset(scene, flag_values, enabled):
    global SUSPEND_UPDATES
    SUSPEND_UPDATES = True
    try:
        for prop, value in flag_values.items():
            setattr(scene.bvt_studio, prop, bool(value))
        scene.bvt_studio.scene_locks_enabled = bool(enabled)
    finally:
        SUSPEND_UPDATES = False
    apply_scene_locks(scene)


def activate_default_scene_locks(scene):
    """Automatically guard a newly imported photo and its studio camera."""
    defaults = {
        'photo_edit_enable': False,
        'camera_edit_enable': False,
        'light_edit_enable': False,
        'glass_edit_enable': True,
        'annotations_edit_enable': True,
    }
    _set_preset(scene, defaults, True)


class BVTSTUDIO_OT_annotation_lock_mode(bpy.types.Operator):
    bl_idname = 'bvt_studio.annotation_lock_mode'
    bl_label = 'Lock Scene for Annotation'
    bl_description = 'Protect the BVT photo, camera, lights and glass; leave annotation planes editable'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if MODES_BEFORE_ANNOTATION not in scene:
            scene[MODES_BEFORE_ANNOTATION] = json.dumps({
                prop: bool(getattr(scene.bvt_studio, prop))
                for _, prop in GROUP_FIELDS
            })
        _set_preset(scene, {
            'photo_edit_enable': False,
            'camera_edit_enable': False,
            'light_edit_enable': False,
            'glass_edit_enable': False,
            'annotations_edit_enable': True,
        }, True)
        self.report({'INFO'}, 'Annotation Mode: background locked; annotations editable')
        return {'FINISHED'}


class BVTSTUDIO_OT_unlock_scene(bpy.types.Operator):
    bl_idname = 'bvt_studio.unlock_scene'
    bl_label = 'Unlock Scene'
    bl_description = 'Restore original Blender selection and transform locks on BVT objects'
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        scene = context.scene
        try:
            previous = json.loads(str(scene.get(MODES_BEFORE_ANNOTATION, '{}')))
        except (TypeError, ValueError):
            previous = {}
        _set_preset(scene, previous, False)
        if MODES_BEFORE_ANNOTATION in scene:
            del scene[MODES_BEFORE_ANNOTATION]
        self.report({'INFO'}, 'Scene protection disabled; original object locks restored')
        return {'FINISHED'}


CLASSES = (BVTSTUDIO_OT_annotation_lock_mode, BVTSTUDIO_OT_unlock_scene)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    # Disabling/upgrading the add-on must not strand the user with unselectable
    # BVT objects and no panel available to unlock them.
    global SUSPEND_UPDATES
    SUSPEND_UPDATES = True
    try:
        for obj in bpy.data.objects:
            if _is_local(obj) and obj.get(LOCK_MARKER) is not None:
                _restore(obj)
        for scene in bpy.data.scenes:
            if hasattr(scene, 'bvt_studio'):
                scene.bvt_studio.scene_locks_enabled = False
    finally:
        SUSPEND_UPDATES = False
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
