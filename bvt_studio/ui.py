"""Blender sidebar panel; no geometry or render business logic."""
import bpy
from . import bl_info, BUILD_STAGE
from .common import scene_annotations
from .annotation import PREVIEW_PROP
from .glass import scene_glass


class BVTSTUDIO_PT_main(bpy.types.Panel):
    bl_label = 'BVT Studio | 2.5D'
    bl_idname = 'BVTSTUDIO_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BVT Studio'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.bvt_studio
        selected = context.active_object
        version = '.'.join(str(v) for v in bl_info['version'])
        layout.label(text=f'BVT Studio v{version}-{BUILD_STAGE}', icon='INFO')

        box = layout.box()
        box.label(text='0. Scene Editing / Locks', icon='RESTRICT_SELECT_OFF')
        box.label(text='Protection: ON' if settings.scene_locks_enabled else 'Protection: OFF',
                  icon='LOCKED' if settings.scene_locks_enabled else 'UNLOCKED')
        box.operator('bvt_studio.annotation_lock_mode', text='Lock Scene for Annotation', icon='LOCKED')
        box.operator('bvt_studio.unlock_scene', text='Unlock Scene', icon='UNLOCKED')
        fields = (
            'photo_edit_enable', 'camera_edit_enable', 'light_edit_enable',
            'glass_edit_enable', 'annotations_edit_enable',
        )
        col = box.column(align=True)
        col.enabled = settings.scene_locks_enabled
        for key in fields:
            row = col.row(align=True)
            row.prop(settings, key)
            enabled = bool(getattr(settings, key))
            row.label(text='Editable' if enabled else 'Locked',
                      icon='UNLOCKED' if enabled else 'LOCKED')
        box.label(text='Only BVT-managed objects are protected.', icon='INFO')

        depth_box = layout.box()
        depth_box.label(text='0.1 Layer Depth / Photo Normal', icon='CONSTRAINT')
        depth_box.prop(settings, 'photo_depth_lock')
        depth_box.prop(settings, 'glass_depth_lock')
        depth_box.prop(settings, 'annotations_depth_lock')
        depth_box.prop(settings, 'depth_target_glass', text='Glass Target')
        depth_box.prop(settings, 'glass_depth_offset_m', text='Depth Offset')
        depth_box.operator('bvt_studio.apply_glass_depth',
                           text='Apply Glass Depth Offset', icon='ARROW_LEFTRIGHT')
        depth_box.operator('bvt_studio.reset_layer_depth',
                           text='Reset Layer Depth', icon='FILE_REFRESH')
        depth_box.label(text='Depth is relative to rotated Photo Plane.', icon='INFO')

        box = layout.box()
        box.label(text='1. Photo / Scene', icon='IMAGE_DATA')
        box.operator('bvt_studio.load_photo', text='New Scene from Photo', icon='FILE_IMAGE')
        box.operator('bvt_studio.use_source', text='Use Selected / Current Photo', icon='EYEDROPPER')
        box.prop(settings, 'source_object', text='Source')
        box.label(text='Photo source is retained if a Glass Plane is selected.')
        box.prop(settings, 'camera_profile', text='Frame')
        box.operator('bvt_studio.fit_camera', text='Frame Camera to Photo', icon='CAMERA_DATA')
        box.label(text='Photo stays flat; camera crops/frames it.', icon='INFO')

        box = layout.box()
        box.label(text=f'2. Glass / Artifacts ({len(scene_glass(scene))})', icon='MOD_FLUIDSIM')
        box.operator('bvt_studio.add_glass', text='Add Glass', icon='ADD')
        box.operator('bvt_studio.setup_glass', text='Setup Selected Glass Plane', icon='MATERIAL')
        box.operator('bvt_studio.setup_selected_glass_batch',
                     text='Setup Selected Planes (Batch)', icon='MOD_ARRAY')
        box.operator('bvt_studio.organize_glass', text='Register / Setup Glass All', icon='OUTLINER_COLLECTION')
        box.operator('bvt_studio.renumber_glass', text='Renumber Glass 001...N', icon='SORTALPHA')
        if selected and selected.get('bvt_role') == 'glass_overlay':
            for prop, title in (
                ('bvt_glass_reflection', 'Reflections'),
                ('bvt_glass_tint', 'Tint'),
                ('bvt_glass_haze', 'Haze'),
                ('bvt_glass_frost', 'Frost'),
            ):
                if prop in selected:
                    box.prop(selected, f'["{prop}"]', text=title, slider=True)
        else:
            box.label(text='Click Add Glass, then size/move the Plane.', icon='INFO')
        box.label(text='Stored in BVT_Glass / Glass_p_001...N', icon='OUTLINER_COLLECTION')

        box = layout.box()
        count = len(scene_annotations(scene))
        box.label(text=f'3. Annotation Planes ({count})', icon='OUTLINER_OB_MESH')
        box.operator('bvt_studio.add_annotation', text='Add Annotation', icon='ADD')
        box.operator('bvt_studio.register_annotations', text='Register / Color All', icon='SHADING_WIRE')
        box.operator('bvt_studio.renumber', text='Renumber 001...N', icon='SORTALPHA')
        show = bool(scene.get(PREVIEW_PROP, False))
        box.operator('bvt_studio.toggle_preview',
                     text='Render Outlines: ON' if show else 'Render Outlines: OFF',
                     icon='HIDE_OFF' if show else 'HIDE_ON')
        # List is refreshed by BVT add/register/renumber and manually after
        # external Outliner deletions/renames. It never duplicates scene objects.
        manager = box.box()
        enabled_count = sum(bool(obj.get('bvt_enabled', True))
                            for obj in scene_annotations(scene))
        manager.label(text=f'Annotation Manager: {enabled_count}/{count} enabled',
                      icon='OUTLINER_COLLECTION')
        manager.operator('bvt_studio.refresh_annotation_list',
                         text='Refresh List', icon='FILE_REFRESH')
        manager.template_list('BVTSTUDIO_UL_annotations', '', settings,
                              'annotation_items', settings, 'annotation_index', rows=6)
        manager.operator('bvt_studio.select_all_annotations',
                         text='Select All Annotations', icon='RESTRICT_SELECT_OFF')
        manager.label(text='Batch edit selected annotation objects:')
        manager.prop(settings, 'batch_class_id')
        manager.prop(settings, 'batch_class_name')
        manager.operator('bvt_studio.batch_annotation_class',
                         text='Apply Class to Selected', icon='CHECKMARK')
        manager.prop(settings, 'batch_enabled')
        manager.operator('bvt_studio.batch_annotation_enabled',
                         text='Apply Enabled to Selected', icon='CHECKMARK')
        manager.label(text='Selection is limited to the active scene.', icon='INFO')

        if selected and (selected.get('bvt_role') == 'annotation' or selected.name.startswith('plane_p_')):
            sub = box.box()
            sub.label(text='Selected annotation:')
            for key, label in (
                ('bvt_class_id', 'Class ID'),
                ('bvt_class_name', 'Class name'),
                ('bvt_enabled', 'Enabled'),
            ):
                if key in selected:
                    sub.prop(selected, f'["{key}"]', text=label)
            sub.label(text='Scale/move the Plane over a product.')

        quality = layout.box()
        quality.label(text='4. YOLO Quality Gate', icon='CHECKMARK')
        quality.operator('bvt_studio.validate', text='Validate YOLO Boxes', icon='CHECKMARK')
        if settings.quality_checked:
            quality.label(text=(f"{settings.quality_box_count} boxes  |  "
                                f"{settings.quality_error_count} errors  |  "
                                f"{settings.quality_warning_count} warnings"))
            if settings.quality_items:
                quality.template_list('BVTSTUDIO_UL_quality_issues', '', settings,
                                      'quality_items', settings, 'quality_index', rows=5)
                quality.operator('bvt_studio.focus_quality_issue',
                                 text='Select Problem Annotation', icon='RESTRICT_SELECT_OFF')
            else:
                quality.label(text='No issues detected', icon='CHECKMARK')
            quality.label(text='Snapshot: rerun validation after edits.', icon='INFO')
        else:
            quality.label(text='Run validation to see errors here.', icon='INFO')

        box = layout.box()
        box.label(text='5. YOLO Export', icon='EXPORT')
        box.prop(settings, 'export_dir', text='Folder')
        box.operator('bvt_studio.export_yolo', text='Export Clean Image + YOLO', icon='FILE_TICK')
        box.label(text='One sample per click; val split is manual.', icon='INFO')

CLASSES = (BVTSTUDIO_PT_main,)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
