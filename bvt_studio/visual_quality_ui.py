"""Display the most recent external Blender visual QA report in the sidebar."""
from pathlib import Path
import json
import bpy


class BVTSTUDIO_OT_read_visual_quality_report(bpy.types.Operator):
    bl_idname = 'bvt_studio.read_visual_quality_report'
    bl_label = 'Read Visual QA Report'
    bl_description = 'Read the calibration JSON created by the headless Visual Quality QA script'
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.bvt_studio
        try:
            path = Path(bpy.path.abspath(str(settings.visual_quality_report_path))).expanduser()
            data = json.loads(path.read_text(encoding='utf-8'))
            stage = data.get('stage')
            passed = bool(data.get('overall_accepted', False))
            if stage == 'alpha.5-step4' and isinstance(data.get('candidates'), dict):
                chosen = data.get('selected')
                message = f'PASS: {chosen}' if passed else 'QA REJECTED / REVIEW'
            elif stage == 'alpha.5-step5' and isinstance(data.get('profiles'), dict):
                profiles = data['profiles']
                if not profiles:
                    raise ValueError('Empty Quality Gate v2 profiles')
                pairs = [f'{profile.title()}={item.get("selected") or "reject"}'
                         for profile, item in profiles.items()]
                message = ('QGv2 PASS: ' if passed else 'QGv2 REJECT: ') + ', '.join(pairs)
            else:
                raise ValueError('Not a BVT Visual Quality Step 4 / Quality Gate v2 report')
            settings.visual_quality_result = message
            settings.visual_quality_status = passed
            self.report({'INFO'} if passed else {'WARNING'}, settings.visual_quality_result)
            return {'FINISHED'}
        except Exception as exc:
            settings.visual_quality_result = 'Report not loaded'
            settings.visual_quality_status = False
            self.report({'ERROR'}, f'Visual QA: {exc}')
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_read_visual_quality_report,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
