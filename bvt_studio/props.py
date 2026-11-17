import bpy
from bpy.props import (
    PointerProperty, StringProperty, FloatProperty, EnumProperty, BoolProperty,
    CollectionProperty, IntProperty,
)


def on_lock_change(self, context):
    # Deferred import avoids a registration-time circular dependency.
    from .scene_lock import on_group_settings_changed
    on_group_settings_changed(self, context)


def on_depth_change(self, context):
    from .depth import on_depth_settings_changed
    on_depth_settings_changed(self, context)


def on_annotation_selection_change(self, context):
    from .annotation_manager import on_annotation_index_changed
    on_annotation_index_changed(self, context)


class BVTStudioAnnotationItem(bpy.types.PropertyGroup):
    obj: PointerProperty(name='Annotation', type=bpy.types.Object)


class BVTStudioQualityItem(bpy.types.PropertyGroup):
    severity: StringProperty(name='Severity')
    code: StringProperty(name='Code')
    message: StringProperty(name='Message')
    obj: PointerProperty(name='Annotation', type=bpy.types.Object)


class BVTStudioSettings(bpy.types.PropertyGroup):
    artifact_target_glass: PointerProperty(
        name='Glass Target', type=bpy.types.Object,
        description='Glass material target, even if the glass object is selection-locked',
    )
    artifact_preset: EnumProperty(
        name='Glass Preset',
        items=[
            ('CLEAN', 'Clean', 'Minimal artifact baseline'),
            ('LIGHT_CONDENSATION', 'Light Condensation', 'Gentle condensed moisture'),
            ('HEAVY_CONDENSATION', 'Heavy Condensation', 'Strong condensation and droplets'),
            ('FROST', 'Frost', 'Patchy cold freezer frost'),
            ('DIRTY_GLASS', 'Dirty Glass', 'Smudges and dirt'),
            ('REFLECTIONS', 'Reflections', 'Pronounced cool LED reflections'),
        ],
        default='LIGHT_CONDENSATION',
    )
    artifact_intensity: FloatProperty(
        name='Intensity', default=1.0, min=0.0, max=1.0,
        description='Multiplier applied to all selected preset channels',
    )
    artifact_coverage: FloatProperty(
        name='Coverage', default=0.30, min=0.0, max=1.0,
        description='Relative droplet density; controlled independently of strength',
    )
    artifact_droplet_scale: FloatProperty(
        name='Droplet Scale', default=1.0, min=0.5, max=2.0,
        description='Higher values produce smaller and more numerous droplets',
    )
    artifact_frost_edge: FloatProperty(
        name='Frost Edge', default=0.35, min=0.0, max=1.0,
        description='Additional irregular frost near the perimeter of this glass',
    )
    artifact_refraction: FloatProperty(
        name='Refraction Strength', default=0.016, min=0.0, max=0.04,
        precision=3, description='Approximate local UV distortion inside drops',
    )
    artifact_relief: FloatProperty(
        name='Droplet Relief', default=0.80, min=0.0, max=1.0,
        description='Contrast of bright and dark droplet rims',
    )
    artifact_seed: IntProperty(
        name='Seed', default=42, min=0, max=2147483647,
        description='Deterministic microstructure seed for the selected glass plane',
    )
    quality_items: CollectionProperty(type=BVTStudioQualityItem)
    quality_index: IntProperty(name='Issue row', default=-1)
    quality_checked: BoolProperty(name='Quality report available', default=False)
    quality_box_count: IntProperty(name='Validated boxes', default=0)
    quality_error_count: IntProperty(name='Validation errors', default=0)
    quality_warning_count: IntProperty(name='Validation warnings', default=0)

    annotation_items: CollectionProperty(type=BVTStudioAnnotationItem)
    annotation_index: IntProperty(name='Annotation row', default=-1,
                                  update=on_annotation_selection_change)
    batch_class_id: IntProperty(name='Class ID', default=0, min=0)
    batch_class_name: StringProperty(name='Class Name', default='ice_cream')
    batch_enabled: BoolProperty(name='Enabled for YOLO', default=True)

    scene_locks_enabled: BoolProperty(
        name='Scene protection active', default=False, update=on_lock_change,
        description='Apply BVT selection and transform locks to this scene',
    )
    photo_edit_enable: BoolProperty(
        name='Photo Edit Enable', default=False, update=on_lock_change)
    camera_edit_enable: BoolProperty(
        name='Camera Edit Enable', default=False, update=on_lock_change)
    light_edit_enable: BoolProperty(
        name='Light Edit Enable', default=False, update=on_lock_change)
    glass_edit_enable: BoolProperty(
        name='Glass Edit Enable', default=True, update=on_lock_change)
    annotations_edit_enable: BoolProperty(
        name='Annotations Edit Enable', default=True, update=on_lock_change)

    photo_depth_lock: BoolProperty(
        name='Photo - Lock Depth', default=True, update=on_depth_change,
        description='Keep photo origin in its initial reference plane',
    )
    glass_depth_lock: BoolProperty(
        name='Glass - Lock Depth', default=True, update=on_depth_change,
        description='Keep glass inside a plane parallel to source photo',
    )
    annotations_depth_lock: BoolProperty(
        name='Annotations - Lock Depth', default=True, update=on_depth_change,
        description='Keep YOLO annotation origins at fixed photo-relative depth',
    )
    depth_target_glass: PointerProperty(
        name='Glass Surface', type=bpy.types.Object,
        description='Glass to reposition, even if viewport selection is locked',
    )
    glass_depth_offset_m: FloatProperty(
        name='Depth Offset', default=0.012, min=0.001, max=0.150,
        precision=4, subtype='DISTANCE', unit='LENGTH',
        description='Distance to photo towards camera for the chosen Glass Plane',
    )

    source_object: PointerProperty(
        name="Image Plane", type=bpy.types.Object,
        description="Image plane used for camera fitting and initial annotation placement",
    )
    plane_width: FloatProperty(
        name="Plane width", default=2.0, min=0.1, max=100.0,
        subtype='DISTANCE', unit='LENGTH',
    )
    camera_profile: EnumProperty(
        name="Frame profile",
        items=[
            ('ORIGINAL', 'Original image', 'Render at source image dimensions'),
            ('PHONE_4_3', 'Phone 4:3', 'Landscape mobile image, 1600x1200'),
            ('PHONE_3_4', 'Phone 3:4', 'Portrait mobile image, 1200x1600'),
            ('PHONE_16_9', 'Phone 16:9', 'Wide mobile image, 1920x1080'),
            ('TABLET_4_3', 'Tablet 4:3', 'Tablet framing, 2048x1536'),
        ],
        default='ORIGINAL',
    )
    last_preview_svg: StringProperty(
        name='Last exported SVG preview', subtype='FILE_PATH', default='',
        description='Full path to the last exported YOLO overlay',
    )
    export_dir: StringProperty(
        name="Output folder", subtype='DIR_PATH', default="//bvt_studio_dataset",
    )

CLASSES = (BVTStudioAnnotationItem, BVTStudioQualityItem, BVTStudioSettings)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bvt_studio = PointerProperty(type=BVTStudioSettings)


def unregister():
    del bpy.types.Scene.bvt_studio
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
