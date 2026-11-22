"""Annotation list and safe mass-editing operations for the active BVT scene.

The list is a persistent view of scene-owned annotation Object pointers. It is
refreshed on BVT create/register/renumber operations, and explicitly via Refresh
for objects edited/deleted outside the add-on. No scene geometry is duplicated.
"""

import bpy

from .common import scene_annotations

SUSPEND_LIST_SELECTION = False


def _object_key(obj):
    """Stable ID across Python RNA wrapper instances, usable in unit tests."""
    return obj.as_pointer() if hasattr(obj, 'as_pointer') else id(obj)


def class_name_conflicts(all_objects, targets, class_id, class_name):
    """Return preflight issues without mutating any Blender object."""
    chosen = {_object_key(obj) for obj in targets}
    conflicts = []
    for obj in all_objects:
        if _object_key(obj) in chosen:
            continue
        if int(obj.get('bvt_class_id', 0)) == int(class_id):
            name = str(obj.get('bvt_class_name', 'ice_cream')).strip() or 'ice_cream'
            if name != class_name:
                conflicts.append(f'{obj.name}: class {class_id} is named {name!r}')
    return conflicts


def _annotation_targets(context):
    """Only explicitly selected annotations belonging to the current scene."""
    allowed = {_object_key(obj): obj for obj in scene_annotations(context.scene)}
    return [allowed[_object_key(obj)] for obj in context.selected_objects
            if _object_key(obj) in allowed]


def sync_annotation_list(scene, preferred=None):
    """Rebuild list only when membership/order changed, preserving row selection."""
    global SUSPEND_LIST_SELECTION
    settings = scene.bvt_studio
    objs = scene_annotations(scene)
    previous = [item.obj for item in settings.annotation_items]
    if len(previous) == len(objs) and all(
            a is not None and _object_key(a) == _object_key(b)
            for a, b in zip(previous, objs)):
        if preferred is not None:
            idx = next((i for i, obj in enumerate(objs) if _object_key(obj) == _object_key(preferred)), None)
            if idx is not None:
                settings.annotation_index = idx
        return len(objs)

    selected = preferred
    if selected is None and 0 <= settings.annotation_index < len(previous):
        selected = previous[settings.annotation_index]
    SUSPEND_LIST_SELECTION = True
    try:
        settings.annotation_items.clear()
        for obj in objs:
            settings.annotation_items.add().obj = obj
        selected_index = next((i for i, obj in enumerate(objs) if selected is not None and _object_key(obj) == _object_key(selected)), None)
        settings.annotation_index = (selected_index if selected_index is not None
                                     else (0 if objs else -1))
    finally:
        SUSPEND_LIST_SELECTION = False
    return len(objs)


def on_annotation_index_changed(settings, context):
    """Clicking a list row selects that annotation in the Blender viewport."""
    if SUSPEND_LIST_SELECTION or context is None or context.scene is None:
        return
    if settings.as_pointer() != context.scene.bvt_studio.as_pointer():
        return
    if context.mode != 'OBJECT':
        return
    i = settings.annotation_index
    if i < 0 or i >= len(settings.annotation_items):
        return
    obj = settings.annotation_items[i].obj
    if obj is None or obj.name not in context.scene.objects or obj.hide_select:
        return
    for prev in tuple(context.selected_objects):
        if not prev.hide_select:
            prev.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


class BVTSTUDIO_UL_annotations(bpy.types.UIList):
    bl_idname = 'BVTSTUDIO_UL_annotations'

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index=0, flt_flag=0):
        obj = item.obj
        if obj is None:
            layout.label(text='Missing annotation — Refresh', icon='ERROR')
            return
        if self.layout_type == 'GRID':
            layout.label(text='', icon='MESH_PLANE')
            return
        row = layout.row(align=True)
        row.label(text=obj.name, icon='MESH_PLANE')
        cls = int(obj.get('bvt_class_id', 0))
        name = str(obj.get('bvt_class_name', 'ice_cream'))
        row.label(text=f'{cls}: {name}')
        row.label(text='', icon='CHECKBOX_HLT' if obj.get('bvt_enabled', True)
                  else 'CHECKBOX_DEHLT')


class BVTSTUDIO_OT_refresh_annotation_list(bpy.types.Operator):
    bl_idname = 'bvt_studio.refresh_annotation_list'
    bl_label = 'Refresh Annotation List'
    bl_description = 'Refresh the annotation list after external Outliner edits or deletion'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        n = sync_annotation_list(context.scene)
        self.report({'INFO'}, f'Annotation Manager: {n} objects')
        return {'FINISHED'}


class BVTSTUDIO_OT_select_all_annotations(bpy.types.Operator):
    bl_idname = 'bvt_studio.select_all_annotations'
    bl_label = 'Select All Annotation Planes'
    bl_description = 'Select all editable YOLO annotations in the current scene'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, 'Switch to Object Mode before selecting annotations')
            return {'CANCELLED'}
        objects = scene_annotations(context.scene)
        if not objects:
            self.report({'WARNING'}, 'No annotations in this scene')
            return {'CANCELLED'}
        editable = [obj for obj in objects if not obj.hide_select]
        if not editable:
            self.report({'WARNING'}, 'Annotations are locked: turn on Annotations Edit Enable')
            return {'CANCELLED'}
        for obj in tuple(context.selected_objects):
            if not obj.hide_select:
                obj.select_set(False)
        for obj in editable:
            obj.select_set(True)
        context.view_layer.objects.active = editable[0]
        self.report({'INFO'}, f'Selected {len(editable)} annotations')
        return {'FINISHED'}


class BVTSTUDIO_OT_batch_annotation_class(bpy.types.Operator):
    bl_idname = 'bvt_studio.batch_annotation_class'
    bl_label = 'Set Class for Selected Annotations'
    bl_description = 'Assign a YOLO class to selected annotation planes only'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.bvt_studio
        if settings.scene_locks_enabled and not settings.annotations_edit_enable:
            self.report({'WARNING'}, 'Enable Annotations Edit before batch changes')
            return {'CANCELLED'}
        objects = scene_annotations(context.scene)
        targets = _annotation_targets(context)
        if not targets:
            self.report({'WARNING'}, 'Select annotation planes first (or use Select All)')
            return {'CANCELLED'}
        name = settings.batch_class_name.strip()
        if not name:
            self.report({'ERROR'}, 'Class name cannot be empty')
            return {'CANCELLED'}
        class_id = int(settings.batch_class_id)
        conflicts = class_name_conflicts(objects, targets, class_id, name)
        if conflicts:
            self.report({'ERROR'}, conflicts[0] + ' (other annotations use this class ID)')
            return {'CANCELLED'}
        for obj in targets:
            obj['bvt_class_id'] = class_id
            obj['bvt_class_name'] = name
        self.report({'INFO'}, f'Updated class {class_id} ({name}) on {len(targets)} annotations')
        return {'FINISHED'}


class BVTSTUDIO_OT_batch_annotation_enabled(bpy.types.Operator):
    bl_idname = 'bvt_studio.batch_annotation_enabled'
    bl_label = 'Set Enabled for Selected Annotations'
    bl_description = 'Include or exclude selected annotations from YOLO export'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.bvt_studio
        if settings.scene_locks_enabled and not settings.annotations_edit_enable:
            self.report({'WARNING'}, 'Enable Annotations Edit before batch changes')
            return {'CANCELLED'}
        targets = _annotation_targets(context)
        if not targets:
            self.report({'WARNING'}, 'Select annotation planes first (or use Select All)')
            return {'CANCELLED'}
        for obj in targets:
            obj['bvt_enabled'] = bool(settings.batch_enabled)
        self.report({'INFO'}, f'{len(targets)} annotations enabled={bool(settings.batch_enabled)}')
        return {'FINISHED'}


CLASSES = (
    BVTSTUDIO_UL_annotations,
    BVTSTUDIO_OT_refresh_annotation_list,
    BVTSTUDIO_OT_select_all_annotations,
    BVTSTUDIO_OT_batch_annotation_class,
    BVTSTUDIO_OT_batch_annotation_enabled,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
