"""Independent material selection in the BVT sidebar."""
import json
import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from .glass_material_builtin import builtin_profile
from .glass_material_config import MATERIAL_IDS, read_material
from .glass_material_blender import rebuild_materials, PROFILE_KEY, SEED_KEY, BAKE_KEY


def _target(context):
    from .artifact_presets import resolve_glass
    return resolve_glass(context.scene,context.scene.bvt_studio,context.active_object)

class BVTSTUDIO_OT_apply_glass_material_v01(bpy.types.Operator):
    bl_idname='bvt_studio.apply_glass_material_v01'
    bl_label='Apply Glass Material'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            scene=context.scene; obj=_target(context)
            profile=builtin_profile(scene.bvt_material_choice_v01)
            context.view_layer.update()
            rebuild_materials(scene,obj,profile,scene.bvt_material_seed_v01)
            self.report({'INFO'},obj.name+': '+profile['title'])
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}

class BVTSTUDIO_OT_import_glass_material_v01(bpy.types.Operator):
    bl_idname='bvt_studio.import_glass_material_v01'
    bl_label='Apply Material JSON to Target'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            scene=context.scene; obj=_target(context)
            path=scene.bvt_material_json_v01
            if not path: raise ValueError('Choose a bvt.glass-material.v01 JSON file')
            profile=read_material(bpy.path.abspath(path))
            context.view_layer.update()
            rebuild_materials(scene,obj,profile,scene.bvt_material_seed_v01)
            self.report({'INFO'},obj.name+': '+profile['title'])
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}

class BVTSTUDIO_OT_rebuild_glass_materials_v01(bpy.types.Operator):
    bl_idname='bvt_studio.rebuild_glass_materials_v01'
    bl_label='Rebuild Material Layer'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            context.view_layer.update(); rebuild_materials(context.scene)
            self.report({'INFO'},'Material layer rebuilt from original source')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}

class BVTSTUDIO_PT_glass_materials_v01(bpy.types.Panel):
    bl_label='3B. Glass Material Library v0.1'
    bl_idname='BVTSTUDIO_PT_glass_materials_v01'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='BVT Studio'
    bl_parent_id='BVTSTUDIO_PT_main'
    bl_options={'DEFAULT_CLOSED'}
    bl_order=36
    def draw(self,context):
        from .glass import scene_glass
        from .common import get_source
        scene=context.scene; layout=self.layout
        layout.prop(scene.bvt_studio,'artifact_target_glass',text='Glass Target')
        target=scene.bvt_studio.artifact_target_glass
        if target in scene_glass(scene):
            try:
                doc=json.loads(target.get(PROFILE_KEY,'null'))
                layout.label(text='Current: '+(doc['title'] if doc else 'Clear / legacy'))
                layout.label(text='Saved material seed: '+str(target.get(SEED_KEY,72)))
            except (ValueError,TypeError,KeyError): layout.label(text='Invalid stored material',icon='ERROR')
        else: layout.label(text='Select a registered glass target',icon='INFO')
        layout.prop(scene,'bvt_material_choice_v01',text='Material')
        layout.prop(scene,'bvt_material_seed_v01',text='Material Seed')
        layout.operator('bvt_studio.apply_glass_material_v01')
        layout.prop(scene,'bvt_material_json_v01',text='Material JSON')
        layout.operator('bvt_studio.import_glass_material_v01')
        layout.separator()
        layout.operator('bvt_studio.rebuild_glass_materials_v01')
        source=get_source(scene)
        if source is not None and source.get(BAKE_KEY): layout.label(text='Packed material layer active')
        layout.label(text='Rebuild after moving panes or editing masks.',icon='INFO')
        layout.label(text='Experimental 2.5D; opaque sRGB PNG only.')

CLASSES=(BVTSTUDIO_OT_apply_glass_material_v01,BVTSTUDIO_OT_import_glass_material_v01,BVTSTUDIO_OT_rebuild_glass_materials_v01,BVTSTUDIO_PT_glass_materials_v01)

def register():
    bpy.types.Scene.bvt_material_choice_v01=EnumProperty(name='Glass Material',items=[(i,builtin_profile(i)['title'],builtin_profile(i)['description']) for i in MATERIAL_IDS],default='clear_glass')
    bpy.types.Scene.bvt_material_seed_v01=IntProperty(name='Material Seed',default=72,min=0,max=2147483647)
    bpy.types.Scene.bvt_material_json_v01=StringProperty(name='Material JSON',subtype='FILE_PATH')
    for cls in CLASSES: bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
    for name in ('bvt_material_choice_v01','bvt_material_seed_v01','bvt_material_json_v01'): delattr(bpy.types.Scene,name)
