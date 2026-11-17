import bpy
from bpy.props import (
    PointerProperty, StringProperty, FloatProperty, EnumProperty, BoolProperty,
)


def on_lock_change(self, context):
    # Deferred import avoids a registration-time circular dependency.
    from .scene_lock import on_group_settings_changed
    on_group_settings_changed(self, context)


def on_depth_change(self, context):
    from .depth import on_depth_settings_changed
    on_depth_settings_changed(self, context)


class BVTStudioSettings(bpy.types.PropertyGroup):
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
    export_dir: StringProperty(
        name="Output folder", subtype='DIR_PATH', default="//bvt_studio_dataset",
    )

CLASSES = (BVTStudioSettings,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bvt_studio = PointerProperty(type=BVTStudioSettings)


def unregister():
    del bpy.types.Scene.bvt_studio
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
