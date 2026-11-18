"""Blender 5.2 sidebar, split into native collapsible sub-panels.

Only presentation lives here: operators, properties and business logic remain in
existing BVT Studio modules. Blender remembers panel expansion per UI region.
"""
import bpy
from . import bl_info, BUILD_STAGE
from .common import scene_annotations
from .annotation import PREVIEW_PROP
from .glass import scene_glass


class _StudioSidebar:
    """Shared location for the parent and its children (not registered)."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BVT Studio'


class _StudioChild(_StudioSidebar):
    """All work areas are children of the original sidebar panel."""
    bl_parent_id = 'BVTSTUDIO_PT_main'
    bl_options = {'DEFAULT_CLOSED'}


class BVTSTUDIO_PT_main(_StudioSidebar, bpy.types.Panel):
    bl_label = 'BVT Studio | 2.5D'
    bl_idname = 'BVTSTUDIO_PT_main'

    def draw(self, context):
        version = '.'.join(str(v) for v in bl_info['version'])
        self.layout.label(text=f'BVT Studio v{version}-{BUILD_STAGE}', icon='INFO')
        self.layout.label(text='Expand the section you need.', icon='DOWNARROW_HLT')


class BVTSTUDIO_PT_scene_locks(_StudioChild, bpy.types.Panel):
    bl_label = '0. Scene Locks'
    bl_idname = 'BVTSTUDIO_PT_scene_locks'
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bvt_studio
        layout.label(text='Protection: ON' if settings.scene_locks_enabled else 'Protection: OFF',
                     icon='LOCKED' if settings.scene_locks_enabled else 'UNLOCKED')
        layout.operator('bvt_studio.annotation_lock_mode', text='Lock Scene for Annotation', icon='LOCKED')
        layout.operator('bvt_studio.unlock_scene', text='Unlock Scene', icon='UNLOCKED')
        fields = (
            ('photo_edit_enable', 'Photo Edit'),
            ('camera_edit_enable', 'Camera Edit'),
            ('light_edit_enable', 'Light Edit'),
            ('glass_edit_enable', 'Glass Edit'),
            ('annotations_edit_enable', 'Annotations Edit'),
        )
        col = layout.column(align=True)
        col.enabled = settings.scene_locks_enabled
        for key, label in fields:
            row = col.row(align=True)
            row.prop(settings, key, text=label)
            row.label(text='', icon='UNLOCKED' if getattr(settings, key) else 'LOCKED')
        layout.label(text='Only BVT-managed objects are protected.', icon='INFO')


class BVTSTUDIO_PT_layer_depth(_StudioChild, bpy.types.Panel):
    bl_label = '1. Layer Depth / Photo Normal'
    bl_idname = 'BVTSTUDIO_PT_layer_depth'
    bl_order = 10

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bvt_studio
        col = layout.column(align=True)
        col.prop(settings, 'photo_depth_lock')
        col.prop(settings, 'glass_depth_lock')
        col.prop(settings, 'annotations_depth_lock')
        layout.prop(settings, 'depth_target_glass', text='Glass Target')
        layout.prop(settings, 'glass_depth_offset_m', text='Depth Offset')
        layout.operator('bvt_studio.apply_glass_depth',
                        text='Apply Glass Depth Offset', icon='ARROW_LEFTRIGHT')
        layout.operator('bvt_studio.reset_layer_depth',
                        text='Reset Layer Depth', icon='FILE_REFRESH')
        layout.label(text='Relative to the rotated Photo Plane.', icon='INFO')


class BVTSTUDIO_PT_photo_scene(_StudioChild, bpy.types.Panel):
    bl_label = '2. Photo / Scene'
    bl_idname = 'BVTSTUDIO_PT_photo_scene'
    bl_order = 20

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bvt_studio
        layout.operator('bvt_studio.load_photo', text='New Scene from Photo', icon='FILE_IMAGE')
        layout.operator('bvt_studio.use_source', text='Use Selected / Current Photo', icon='EYEDROPPER')
        layout.prop(settings, 'source_object', text='Source')
        layout.label(text='Glass selection does not replace photo.', icon='INFO')
        layout.prop(settings, 'camera_profile', text='Frame')
        layout.operator('bvt_studio.fit_camera', text='Frame Camera to Photo', icon='CAMERA_DATA')
        layout.label(text='Photo stays flat; camera crops/frames it.', icon='INFO')


class BVTSTUDIO_PT_glass_surfaces(_StudioChild, bpy.types.Panel):
    bl_label = '3. Glass / Surfaces'
    bl_idname = 'BVTSTUDIO_PT_glass_surfaces'
    bl_order = 30

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        selected = context.active_object
        layout.label(text=f'Glass surfaces: {len(scene_glass(scene))}', icon='MOD_FLUIDSIM')
        layout.operator('bvt_studio.add_glass', text='Add Glass', icon='ADD')
        layout.operator('bvt_studio.setup_glass', text='Setup Selected Glass Plane', icon='MATERIAL')
        layout.operator('bvt_studio.setup_selected_glass_batch',
                        text='Setup Selected Planes (Batch)', icon='MOD_ARRAY')
        layout.operator('bvt_studio.organize_glass', text='Register / Setup Glass All', icon='OUTLINER_COLLECTION')
        layout.operator('bvt_studio.renumber_glass', text='Renumber Glass 001...N', icon='SORTALPHA')
        if selected and selected.get('bvt_role') == 'glass_overlay':
            details = layout.box()
            details.label(text='Selected glass properties:', icon='MATERIAL')
            for prop, title in (
                ('bvt_glass_reflection', 'Reflections'),
                ('bvt_glass_tint', 'Tint'),
                ('bvt_glass_haze', 'Haze'),
                ('bvt_glass_frost', 'Frost'),
                ('bvt_glass_droplets', 'Droplets'),
                ('bvt_glass_dirt', 'Dirt'),
                ('bvt_artifact_coverage', 'Coverage'),
            ):
                if prop in selected:
                    details.prop(selected, f'["{prop}"]', text=title, slider=True)
        else:
            layout.label(text='Click Add Glass, then size/move the Plane.', icon='INFO')
        layout.label(text='Stored in BVT_Glass / Glass_p_001...N', icon='OUTLINER_COLLECTION')


class BVTSTUDIO_PT_glass_artifacts(_StudioChild, bpy.types.Panel):
    bl_label = '4. Glass Artifact Engine'
    bl_idname = 'BVTSTUDIO_PT_glass_artifacts'
    bl_order = 40
    # Open by default: this is the active workflow for v0.4.
    bl_options = set()

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bvt_studio
        selected = context.active_object
        layout.prop(settings, 'artifact_target_glass', text='Glass Target')
        layout.prop(settings, 'artifact_preset', text='Preset')
        layout.prop(settings, 'artifact_intensity', slider=True)
        layout.prop(settings, 'artifact_coverage', slider=True)
        layout.prop(settings, 'artifact_droplet_scale', slider=True)
        layout.prop(settings, 'artifact_frost_edge', slider=True)
        layout.prop(settings, 'artifact_refraction', slider=True)
        layout.prop(settings, 'artifact_relief', slider=True)
        layout.label(text='Hybrid Condensation v2.2 (Light / Heavy):', icon='MOD_FLUIDSIM')
        layout.prop(settings, 'hybrid_wetness', slider=True)
        layout.prop(settings, 'hybrid_macro', slider=True)
        layout.prop(settings, 'hybrid_micro', slider=True)
        layout.prop(settings, 'artifact_mask_inset', slider=True)
        layout.prop(settings, 'artifact_mask_feather', slider=True)
        layout.label(text='Optional inner aperture (per glass):', icon='MOD_MASK')
        layout.prop(settings, 'artifact_aperture_left', slider=True)
        layout.prop(settings, 'artifact_aperture_right', slider=True)
        layout.prop(settings, 'artifact_aperture_bottom', slider=True)
        layout.prop(settings, 'artifact_aperture_top', slider=True)
        layout.prop(settings, 'artifact_aperture_feather', slider=True)
        layout.prop(settings, 'artifact_seed')
        layout.separator()
        layout.label(text='Packed PNG Precision Mask:', icon='MOD_MASK')
        layout.prop(settings, 'precision_mask_path', text='Mask PNG')
        layout.operator('bvt_studio.assign_precision_mask', text='Assign PNG Mask (Pack)', icon='IMAGE_DATA')
        if selected and selected.get('bvt_role') == 'glass_overlay':
            mask_enabled = bool(selected.get('bvt_glass_mask_enabled', False))
            layout.label(text='Assigned: ' + str(selected.get('bvt_glass_mask_image', '(none)')))
            layout.operator('bvt_studio.toggle_precision_mask',
                            text='Disable PNG Mask' if mask_enabled else 'Enable PNG Mask',
                            icon='CHECKBOX_HLT' if mask_enabled else 'CHECKBOX_DEHLT')
        layout.prop(settings, 'qa_leakage_limit')
        layout.separator()
        layout.label(text='Photographic Droplets (Light / Heavy):', icon='IMAGE_DATA')
        layout.prop(settings, 'droplet_alpha_path', text='Alpha PNG')
        layout.prop(settings, 'droplet_height_path', text='Height PNG')
        layout.prop(settings, 'droplet_normal_path', text='Normal PNG')
        layout.prop(settings, 'droplet_map_tiling', slider=True)
        layout.prop(settings, 'droplet_map_rotation')
        layout.operator('bvt_studio.assign_droplet_maps',
                        text='Import & Pack Droplet Maps', icon='IMPORT')
        droplet_target = settings.artifact_target_glass or selected
        if droplet_target and droplet_target.get('bvt_role') == 'glass_overlay':
            source_mode = droplet_target.get('bvt_droplet_source_mode', 'PROCEDURAL')
            layout.label(text='Target droplet source: ' + source_mode)
            row = layout.row(align=True)
            row.operator('bvt_studio.use_droplet_procedural', text='Procedural')
            row.operator('bvt_studio.use_droplet_photos', text='Photo Maps')
        layout.separator()
        layout.label(text='Generated Realistic Droplet Atlas:', icon='MOD_FLUIDSIM')
        layout.prop(settings, 'realistic_atlas_resolution')
        layout.prop(settings, 'realistic_atlas_density', slider=True)
        layout.prop(settings, 'realistic_atlas_streaks', slider=True)
        layout.operator('bvt_studio.generate_realistic_atlas',
                        text='Generate & Pack Atlas', icon='TEXTURE')
        if droplet_target and droplet_target.get('bvt_role') == 'glass_overlay':
            layout.operator('bvt_studio.use_realistic_atlas',
                            text='Use Saved Realistic Atlas', icon='CHECKMARK')
        layout.separator()
        layout.label(text='Optical Water (Realistic Atlas only):', icon='SHADING_RENDERED')
        layout.prop(settings, 'optical_lens_gain', slider=True)
        layout.prop(settings, 'optical_edge_gain', slider=True)
        layout.prop(settings, 'optical_glint_gain', slider=True)
        layout.prop(settings, 'optical_micro_gain', slider=True)
        if droplet_target and droplet_target.get('bvt_role') == 'glass_overlay':
            layout.label(text='Optical mode: ' + ('ON' if droplet_target.get('bvt_optical_water_enabled', False)
                                                 and droplet_target.get('bvt_droplet_source_mode') == 'REALISTIC_ATLAS'
                                                 else 'OFF'))
        row = layout.row(align=True)
        row.operator('bvt_studio.apply_optical_water', text='Enable Optics', icon='HIDE_OFF')
        row.operator('bvt_studio.disable_optical_water', text='Disable Optics', icon='HIDE_ON')
        layout.separator()
        layout.label(text='Visual Quality Calibration (Step 4):', icon='VIEWZOOM')
        layout.prop(settings, 'visual_quality_report_path', text='QA Report JSON')
        layout.operator('bvt_studio.read_visual_quality_report',
                        text='Read Visual QA Report', icon='FILE_REFRESH')
        layout.label(text=settings.visual_quality_result, icon='CHECKMARK'
                     if settings.visual_quality_status else 'INFO')
        layout.label(text='Generate QA report with headless Blender script.', icon='INFO')
        layout.operator('bvt_studio.apply_glass_preset',
                        text='Apply Glass Preset', icon='CHECKMARK')
        layout.operator('bvt_studio.refresh_glass_pattern',
                        text='Refresh Glass Pattern', icon='FILE_REFRESH')
        if selected and selected.get('bvt_role') == 'glass_overlay':
            details = layout.box()
            details.label(text='Active glass overrides:', icon='MATERIAL')
            for prop, title in (('bvt_artifact_seed', 'Object Seed'),
                                ('bvt_artifact_droplet_scale', 'Object Droplet Scale'),
                                ('bvt_artifact_frost_edge', 'Object Frost Edge'),
                                ('bvt_artifact_refraction', 'Object Refraction'),
                                ('bvt_artifact_relief', 'Object Droplet Relief'),
                                ('bvt_hybrid_wetness', 'Object Wetness'),
                                ('bvt_hybrid_macro', 'Object Macro Droplets'),
                                ('bvt_hybrid_micro', 'Object Micro Droplets'),
                                ('bvt_artifact_mask_inset', 'Object Glass Mask Inset'),
                                ('bvt_artifact_mask_feather', 'Object Mask Feather'),
                                ('bvt_artifact_aperture_left', 'Object Aperture Left'),
                                ('bvt_artifact_aperture_right', 'Object Aperture Right'),
                                ('bvt_artifact_aperture_bottom', 'Object Aperture Bottom'),
                                ('bvt_artifact_aperture_top', 'Object Aperture Top'),
                                ('bvt_artifact_aperture_feather', 'Object Aperture Feather')):
                if prop in selected:
                    details.prop(selected, f'["{prop}"]', text=title)
            details.label(text='Refresh Pattern after changing Object Seed.', icon='INFO')
        layout.label(text='Presets apply only to the Glass Target.', icon='INFO')


class BVTSTUDIO_PT_annotations(_StudioChild, bpy.types.Panel):
    bl_label = '5. YOLO Annotation Manager'
    bl_idname = 'BVTSTUDIO_PT_annotations'
    bl_order = 50

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.bvt_studio
        selected = context.active_object
        annotations = scene_annotations(scene)
        count = len(annotations)
        layout.label(text=f'Annotation Planes: {count}', icon='OUTLINER_OB_MESH')
        layout.operator('bvt_studio.add_annotation', text='Add Annotation', icon='ADD')
        layout.operator('bvt_studio.register_annotations', text='Register / Color All', icon='SHADING_WIRE')
        layout.operator('bvt_studio.renumber', text='Renumber 001...N', icon='SORTALPHA')
        show = bool(scene.get(PREVIEW_PROP, False))
        layout.operator('bvt_studio.toggle_preview',
                        text='Render Outlines: ON' if show else 'Render Outlines: OFF',
                        icon='HIDE_OFF' if show else 'HIDE_ON')
        enabled_count = sum(bool(obj.get('bvt_enabled', True)) for obj in annotations)
        layout.label(text=f'Enabled for YOLO: {enabled_count}/{count}', icon='OUTLINER_COLLECTION')
        layout.operator('bvt_studio.refresh_annotation_list', text='Refresh List', icon='FILE_REFRESH')
        layout.template_list('BVTSTUDIO_UL_annotations', '', settings,
                             'annotation_items', settings, 'annotation_index', rows=6)
        layout.operator('bvt_studio.select_all_annotations',
                        text='Select All Annotations', icon='RESTRICT_SELECT_OFF')
        batch = layout.box()
        batch.label(text='Batch edit selected annotations:')
        batch.prop(settings, 'batch_class_id')
        batch.prop(settings, 'batch_class_name')
        batch.operator('bvt_studio.batch_annotation_class',
                       text='Apply Class to Selected', icon='CHECKMARK')
        batch.prop(settings, 'batch_enabled')
        batch.operator('bvt_studio.batch_annotation_enabled',
                       text='Apply Enabled to Selected', icon='CHECKMARK')
        batch.label(text='Selection is limited to the active scene.', icon='INFO')
        if selected and (selected.get('bvt_role') == 'annotation' or selected.name.startswith('plane_p_')):
            details = layout.box()
            details.label(text='Selected annotation:')
            for key, title in (
                ('bvt_class_id', 'Class ID'),
                ('bvt_class_name', 'Class name'),
                ('bvt_enabled', 'Enabled'),
            ):
                if key in selected:
                    details.prop(selected, f'["{key}"]', text=title)
            details.label(text='Scale/move the Plane over a product.')


class BVTSTUDIO_PT_quality_gate(_StudioChild, bpy.types.Panel):
    bl_label = '6. YOLO Quality Gate'
    bl_idname = 'BVTSTUDIO_PT_quality_gate'
    bl_order = 60

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bvt_studio
        layout.operator('bvt_studio.validate', text='Validate YOLO Boxes', icon='CHECKMARK')
        if settings.quality_checked:
            layout.label(text=(f'{settings.quality_box_count} boxes  |  '
                               f'{settings.quality_error_count} errors  |  '
                               f'{settings.quality_warning_count} warnings'))
            if settings.quality_items:
                layout.template_list('BVTSTUDIO_UL_quality_issues', '', settings,
                                     'quality_items', settings, 'quality_index', rows=5)
                layout.operator('bvt_studio.focus_quality_issue',
                                text='Select Problem Annotation', icon='RESTRICT_SELECT_OFF')
            else:
                layout.label(text='No issues detected', icon='CHECKMARK')
            layout.label(text='Snapshot: rerun validation after edits.', icon='INFO')
        else:
            layout.label(text='Run validation to see errors here.', icon='INFO')


class BVTSTUDIO_PT_yolo_export(_StudioChild, bpy.types.Panel):
    bl_label = '7. YOLO Export'
    bl_idname = 'BVTSTUDIO_PT_yolo_export'
    bl_order = 70

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bvt_studio
        layout.prop(settings, 'export_dir', text='Folder')
        layout.operator('bvt_studio.export_yolo', text='Export Clean Image + YOLO', icon='FILE_TICK')
        layout.operator('bvt_studio.open_yolo_preview',
                        text='Open Last YOLO Preview', icon='IMAGE_DATA')
        layout.label(text='SVG previews use clean PNG + exported TXT.', icon='INFO')
        layout.label(text='One sample per click; val split is manual.', icon='INFO')


# Parent must register first and unregister last for Blender's child panels.
CLASSES = (
    BVTSTUDIO_PT_main,
    BVTSTUDIO_PT_scene_locks,
    BVTSTUDIO_PT_layer_depth,
    BVTSTUDIO_PT_photo_scene,
    BVTSTUDIO_PT_glass_surfaces,
    BVTSTUDIO_PT_glass_artifacts,
    BVTSTUDIO_PT_annotations,
    BVTSTUDIO_PT_quality_gate,
    BVTSTUDIO_PT_yolo_export,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
