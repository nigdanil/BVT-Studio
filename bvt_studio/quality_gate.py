"""Blender UI for quality checks; never changes annotation geometry or class IDs."""
import bpy

from .common import scene_annotations
from .annotation import collect_boxes
from .validation import quality_report


def evaluate_quality(scene):
    """Recompute and persist report, returning (report, errors, boxes, classes)."""
    boxes, errors, classes = collect_boxes(scene)
    size = (
        round(scene.render.resolution_x * scene.render.resolution_percentage / 100),
        round(scene.render.resolution_y * scene.render.resolution_percentage / 100),
    )
    objects = {obj.name: obj for obj in scene_annotations(scene)}
    report = quality_report(boxes, errors, objects, *size)
    settings = scene.bvt_studio
    settings.quality_items.clear()
    for issue in report['issues']:
        entry = settings.quality_items.add()
        entry.severity = issue['severity']
        entry.code = issue['code']
        entry.message = issue['message']
        entry.obj = objects.get(issue['object_name'])
    settings.quality_checked = True
    settings.quality_box_count = report['boxes']
    settings.quality_error_count = report['errors']
    settings.quality_warning_count = report['warnings']
    settings.quality_index = 0 if report['issues'] else -1
    return report, errors, boxes, classes


class BVTSTUDIO_UL_quality_issues(bpy.types.UIList):
    bl_idname = 'BVTSTUDIO_UL_quality_issues'

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index=0, flt_flag=0):
        row = layout.row(align=True)
        row.label(text='Error' if item.severity == 'ERROR' else 'Review',
                  icon='ERROR' if item.severity == 'ERROR' else 'INFO')
        row.label(text=item.message)


class BVTSTUDIO_OT_focus_quality_issue(bpy.types.Operator):
    bl_idname = 'bvt_studio.focus_quality_issue'
    bl_label = 'Select Problem Annotation'
    bl_description = 'Select the annotation related to the highlighted issue'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.bvt_studio
        idx = settings.quality_index
        if not 0 <= idx < len(settings.quality_items):
            self.report({'WARNING'}, 'Select an issue in the report first')
            return {'CANCELLED'}
        obj = settings.quality_items[idx].obj
        if obj is None or obj.name not in context.scene.objects:
            self.report({'WARNING'}, 'Issue has no scene object, or it was deleted. Revalidate.')
            return {'CANCELLED'}
        if context.mode != 'OBJECT' or obj.hide_select:
            self.report({'WARNING'}, 'Enable Annotations Edit and switch to Object Mode')
            return {'CANCELLED'}
        for selected in tuple(context.selected_objects):
            if not selected.hide_select:
                selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report({'INFO'}, f'Selected {obj.name}')
        return {'FINISHED'}


CLASSES = (BVTSTUDIO_UL_quality_issues, BVTSTUDIO_OT_focus_quality_issue)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
