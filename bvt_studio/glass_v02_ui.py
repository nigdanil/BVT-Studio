"""Separate per-pane controls and scene JSON preset import for BVT Studio.

Standalone add-on extension registered last, after BVT's existing panel and
property groups. All changes target explicitly named Glass_p_NNN objects.
"""
import json
from pathlib import Path

import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty, IntProperty

from .water_effects_v02 import DEFAULTS,validated_config,install_on_glass,KINDS
from .glass import scene_glass
from .artifact_presets import apply_preset
from .optical_water import set_optical_water

SCHEMA = 'bvt.glass-gallery.v02'


def resolve_named(scene,name):
    for glass in scene_glass(scene):
        if glass.name == name:
            return glass
    raise ValueError('Glass does not belong to this scene: '+str(name))


def active_target(scene):
    target=scene.bvt_studio.artifact_target_glass
    if target is None or target not in scene_glass(scene):
        raise ValueError('Select a Glass_p_NNN target in the glass manager first')
    return target


def sync_scene_from_glass(scene,glass):
    p=scene.bvt_studio
    p.artifact_target_glass=glass
    p.artifact_seed=int(glass.get('bvt_artifact_seed',72))
    p.artifact_coverage=float(glass.get('bvt_artifact_coverage',.55))
    p.artifact_refraction=float(glass.get('bvt_artifact_refraction',.024))
    p.artifact_relief=float(glass.get('bvt_artifact_relief',.8))
    preset=glass.get('bvt_artifact_preset','CLEAN')
    if preset in {'CLEAN','LIGHT_CONDENSATION','HEAVY_CONDENSATION','FROST','DIRTY_GLASS','REFLECTIONS'}:
        p.artifact_preset=preset
    config=json.loads(glass.get('bvt_water_v02_config_json','{}'))
    cfg=validated_config(config)
    for key,v in cfg.items():
        setattr(scene,'bvt_v02_'+key,v)
    scene.bvt_v02_kind=glass.get('bvt_water_v02_kind','COMBINED')
    scene.bvt_v02_stress=bool(glass.get('bvt_optical_stress_test',False))
    scene.bvt_v02_optics=bool(glass.get('bvt_optical_water_enabled',False))


def parse_scene_config(path):
    config=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(config,dict) or config.get('schema') != SCHEMA:
        raise ValueError('JSON schema must be '+SCHEMA)
    if not isinstance(config.get('glass'),dict) or not config['glass']:
        raise ValueError('glass must be a nonempty object keyed by Glass_p_NNN')
    defaults=config.get('defaults',{})
    if not isinstance(defaults,dict):
        raise ValueError('defaults must be object')
    allowed={'preset','intensity','coverage','seed','refraction','relief','water','optics','stress'}
    if set(defaults)-allowed:
        raise ValueError('Unknown default keys: '+str(set(defaults)-allowed))
    prepared={}
    for name,override in config['glass'].items():
        if not isinstance(name,str) or not name.startswith('Glass_p_'):
            raise ValueError('Expected Glass_p_NNN key: '+str(name))
        if not isinstance(override,dict) or set(override)-allowed:
            raise ValueError('Invalid or unknown override fields for '+name)
        spec=dict(defaults);spec.update(override)
        if spec.get('preset','HEAVY_CONDENSATION') not in {'CLEAN','QA_TRANSPARENT','LIGHT_CONDENSATION','HEAVY_CONDENSATION','FROST','DIRTY_GLASS','REFLECTIONS'}:
            raise ValueError(name+': invalid preset')
        for key,low,high in [('intensity',0,1),('coverage',0,1),('refraction',0,.04),('relief',0,1)]:
            x=spec.get(key,{'intensity':1.,'coverage':.55,'refraction':.028,'relief':.95}[key])
            if isinstance(x,bool) or not isinstance(x,(float,int)) or not low<=x<=high:
                raise ValueError(name+': invalid '+key)
        seed=spec.get('seed',72)
        if type(seed) is not int or not 0<=seed<2**31:
            raise ValueError(name+': invalid seed')
        for flag in ('stress',):
            if flag in spec and type(spec[flag]) is not bool:
                raise ValueError(name+': '+flag+' must be boolean')
        water=spec.get('water',None)
        if water is not None:
            if spec.get('preset','HEAVY_CONDENSATION') not in ('LIGHT_CONDENSATION','HEAVY_CONDENSATION'):
                raise ValueError(name+': water needs LIGHT/HEAVY condensation preset')
            if not isinstance(water,dict) or set(water)-{'kind','resolution','tiling','params'}:
                raise ValueError(name+': bad water object')
            if water.get('kind','COMBINED') not in KINDS:
                raise ValueError(name+': invalid water kind')
            if type(water.get('resolution',512)) is not int or water.get('resolution',512) not in (256,512,1024):
                raise ValueError(name+': invalid resolution')
            if not .25<=float(water.get('tiling',1.))<=8.:
                raise ValueError(name+': invalid tiling')
            validated_config(water.get('params',{}))
        optics=spec.get('optics',None)
        if optics is not None:
            if not isinstance(optics,dict) or set(optics)-{'enabled','lens','edge','glint','micro'}:
                raise ValueError(name+': invalid optics')
            from .optical_water import validate_optical
            validate_optical(optics.get('enabled',True),optics.get('lens',1.45),
                             optics.get('edge',1.0),optics.get('glint',1.25),optics.get('micro',.35))
            if optics.get('enabled',True) and water is None:
                raise ValueError(name+': optics needs water atlas')
        prepared[name]=spec
    return prepared


def apply_scene_config(scene,prepared):
    """Preflight names/constraints before mutation. Application is sequential."""
    targets={name:resolve_named(scene,name) for name in prepared}
    for name,spec in prepared.items():
        obj=targets[name]
        seed=spec.get('seed',72)
        apply_preset(obj,spec.get('preset','HEAVY_CONDENSATION'),
                     intensity=spec.get('intensity',1.),coverage=spec.get('coverage',.55),
                     seed=seed,refraction=spec.get('refraction',.028),
                     relief=spec.get('relief',.95))
        water=spec.get('water')
        optics=spec.get('optics') or {}
        if water is not None:
            gains={'lens':optics.get('lens',1.45),'edge':optics.get('edge',1.),
                   'glint':optics.get('glint',1.25),'micro':optics.get('micro',.35)} if optics.get('enabled',True) else None
            install_on_glass(obj,kind=water.get('kind','COMBINED'),seed=seed,
                             resolution=water.get('resolution',512),
                             tiling=water.get('tiling',1.),config=water.get('params',{}),
                             optics=gains,stress=spec.get('stress',False))
        else:
            # Explicitly disable old 2.5D optical atlas only on this pane.
            obj['bvt_optical_stress_test']=False
            if obj.get('bvt_droplet_source_mode')=='REALISTIC_ATLAS':
                from .droplet_maps import set_droplet_mode
                set_droplet_mode(obj,'PROCEDURAL')
    return len(targets)


class BVTSTUDIO_OT_select_glass_v02(bpy.types.Operator):
    bl_idname='bvt_studio.select_glass_v02'
    bl_label='Edit Glass Target'
    bl_description='Choose the exact pane and load its saved parameters into BVT Studio fields'
    glass_name: StringProperty()
    def execute(self,context):
        try:
            sync_scene_from_glass(context.scene,resolve_named(context.scene,self.glass_name))
            self.report({'INFO'},'Selected '+self.glass_name)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class BVTSTUDIO_OT_generate_water_v02(bpy.types.Operator):
    bl_idname='bvt_studio.generate_water_v02'
    bl_label='Generate Water v0.2 (Selected Pane)'
    def execute(self,context):
        scene=context.scene
        try:
            obj=active_target(scene)
            cfg={k:getattr(scene,'bvt_v02_'+k) for k in DEFAULTS}
            kind=scene.bvt_v02_kind
            if obj.get('bvt_artifact_preset') not in ('LIGHT_CONDENSATION','HEAVY_CONDENSATION'):
                apply_preset(obj,'HEAVY_CONDENSATION',intensity=1.,coverage=.65,
                             seed=scene.bvt_studio.artifact_seed,refraction=.032,relief=1.)
            optics={'lens':scene.bvt_studio.optical_lens_gain,
                    'edge':scene.bvt_studio.optical_edge_gain,
                    'glint':scene.bvt_studio.optical_glint_gain,
                    'micro':scene.bvt_studio.optical_micro_gain} if scene.bvt_v02_optics else None
            events=install_on_glass(obj,kind=kind,seed=scene.bvt_studio.artifact_seed,
                                   resolution=int(scene.bvt_studio.realistic_atlas_resolution),
                                   config=cfg,optics=optics,stress=scene.bvt_v02_stress)
            self.report({'INFO'},f'{obj.name}: {kind}, {len(events)} water elements')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class BVTSTUDIO_OT_import_glass_config_v02(bpy.types.Operator):
    bl_idname='bvt_studio.import_glass_config_v02'
    bl_label='Import Glass Preset JSON v0.2'
    def execute(self,context):
        try:
            path=Path(bpy.path.abspath(context.scene.bvt_v02_config_path)).expanduser().resolve()
            if not path.is_file():
                raise ValueError('Choose an existing JSON preset file')
            prepared=parse_scene_config(path)
            count=apply_scene_config(context.scene,prepared)
            context.scene.bvt_v02_config_result=f'Applied {count} glass pane(s)'
            self.report({'INFO'},context.scene.bvt_v02_config_result)
            return {'FINISHED'}
        except Exception as exc:
            context.scene.bvt_v02_config_result='ERROR: '+str(exc)[:200]
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class BVTSTUDIO_PT_glass_manager_v02(bpy.types.Panel):
    bl_label='3A. Glass Target & Presets v0.2'
    bl_idname='BVTSTUDIO_PT_glass_manager_v02'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='BVT Studio'
    bl_parent_id='BVTSTUDIO_PT_main'
    bl_options={'DEFAULT_CLOSED'}
    bl_order=35

    def draw(self,context):
        layout=self.layout
        scene=context.scene
        p=scene.bvt_studio
        glasses=scene_glass(scene)
        layout.label(text=f'Independent panes: {len(glasses)}')
        target=p.artifact_target_glass
        for obj in glasses:
            line=layout.row(align=True)
            op=line.operator('bvt_studio.select_glass_v02',text=obj.name,
                             icon='RADIOBUT_ON' if obj == target else 'RADIOBUT_OFF',depress=obj == target)
            op.glass_name=obj.name
            line.label(text=str(obj.get('bvt_water_v02_kind',obj.get('bvt_artifact_preset','custom')))[:16])
        if target is not None and target in glasses:
            box=layout.box()
            box.label(text='Editing only: '+target.name)
            box.label(text='Mask: '+('ON' if target.get('bvt_glass_mask_enabled',False) else 'OFF'))
            box.label(text='Mode: '+str(target.get('bvt_droplet_source_mode','PROCEDURAL')))
            box.prop(scene,'bvt_v02_kind',text='Water Type')
            for field in ('macro_count','macro_diameter_px','macro_irregularity',
                          'micro_count','micro_diameter_px','streak_count',
                          'streak_length_px','streak_width_px','streak_taper','relief_strength'):
                box.prop(scene,'bvt_v02_'+field)
            box.prop(scene,'bvt_v02_optics',text='Optical Water')
            box.prop(scene,'bvt_v02_stress',text='Stress (QA Only)')
            box.operator('bvt_studio.generate_water_v02',icon='MOD_FLUIDSIM')
            box.label(text='Water switches non-condensation preset to Heavy',icon='INFO')
        layout.separator()
        layout.label(text='Apply preset to explicitly named panes:')
        layout.prop(scene,'bvt_v02_config_path',text='JSON')
        layout.operator('bvt_studio.import_glass_config_v02',icon='IMPORT')
        if scene.bvt_v02_config_result:
            layout.label(text=scene.bvt_v02_config_result[:80])
        layout.label(text='Other BVT glass controls live in section 4.',icon='INFO')


CLASSES=(BVTSTUDIO_OT_select_glass_v02,BVTSTUDIO_OT_generate_water_v02,
         BVTSTUDIO_OT_import_glass_config_v02,BVTSTUDIO_PT_glass_manager_v02)


def register():
    bpy.types.Scene.bvt_v02_config_path=StringProperty(name='Glass preset JSON',subtype='FILE_PATH')
    bpy.types.Scene.bvt_v02_config_result=StringProperty(name='Glass preset status',default='')
    bpy.types.Scene.bvt_v02_kind=EnumProperty(name='Water Type',items=[(x,x,x) for x in KINDS],default='MACRO')
    bpy.types.Scene.bvt_v02_stress=BoolProperty(name='Stress QA',default=False)
    bpy.types.Scene.bvt_v02_optics=BoolProperty(name='Optical Water',default=True)
    for key,val in DEFAULTS.items():
        kw={'name':key.replace('_',' ').title(),'default':val,'min':__import__('bvt_studio.water_effects_v02',fromlist=['LIMITS']).LIMITS[key][0],
            'max':__import__('bvt_studio.water_effects_v02',fromlist=['LIMITS']).LIMITS[key][1]}
        prop=IntProperty(**kw) if isinstance(val,int) else FloatProperty(**kw)
        setattr(bpy.types.Scene,'bvt_v02_'+key,prop)
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    for key in ('config_path','config_result','kind','stress','optics',*DEFAULTS.keys()):
        delattr(bpy.types.Scene,'bvt_v02_'+key)
