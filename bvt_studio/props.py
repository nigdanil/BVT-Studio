import bpy
from bpy.props import (
    PointerProperty, StringProperty, FloatProperty, EnumProperty,
)


class BVTStudioSettings(bpy.types.PropertyGroup):
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
