"""Per-glass, non-destructive procedural presets; no mesh transform changes."""
import bpy
from .artifact_config import PRESETS, preset_values, seed_offsets, validate_shape_params
from .glass import configure_glass


def resolve_glass(scene, settings, active):
    target = settings.artifact_target_glass
    if target is None and active is not None and active.get('bvt_role') == 'glass_overlay':
        target = active
    if target is None or target.name not in scene.objects:
        raise ValueError('Choose a Glass Target in the BVT Studio panel')
    if target.type != 'MESH' or target.get('bvt_role') != 'glass_overlay':
        raise ValueError('Glass Target must be a registered BVT glass mesh')
    if target.library is not None or target.data.library is not None:
        raise ValueError('Cannot edit a linked glass surface')
    return target


def apply_preset(obj, name, intensity, coverage, seed, droplet_scale=1.0, frost_edge=0.35,
                 refraction=0.016, relief=0.80, wetness=0.60, macro=0.72, micro=0.60,
                 mask_inset=0.045, mask_feather=0.030, aperture_left=0.0, aperture_right=1.0,
                 aperture_bottom=0.0, aperture_top=1.0, aperture_feather=0.020):
    """Update only this object's appearance. Geometry and other glass remain unchanged."""
    # Keep existing CLEAN visually intact; QA_TRANSPARENT is truly inert.
    values = (preset_values('CLEAN', 0.0, 0.0) if name == 'QA_TRANSPARENT'
              else preset_values(name, intensity, coverage))
    seed_offsets(seed)  # Validate before touching any object material.
    size, edge = validate_shape_params(droplet_scale, frost_edge)
    values['bvt_artifact_droplet_scale'] = size
    values['bvt_artifact_frost_edge'] = edge
    from math import isfinite
    if not isfinite(float(refraction)) or not 0.0 <= float(refraction) <= 0.04:
        raise ValueError('Refraction Strength must be in [0, 0.04]')
    if not isfinite(float(relief)) or not 0.0 <= float(relief) <= 1.0:
        raise ValueError('Droplet Relief must be in [0, 1]')
    values['bvt_artifact_refraction'] = float(refraction)
    values['bvt_artifact_relief'] = float(relief)
    from .hybrid_condensation import validate_hybrid_settings
    if not isfinite(float(mask_inset)) or not 0.0 <= float(mask_inset) <= 0.25:
        raise ValueError('Glass Mask Inset must be in [0, 0.25]')
    if not isfinite(float(mask_feather)) or not 0.001 <= float(mask_feather) <= 0.25:
        raise ValueError('Mask Feather must be in [0.001, 0.25]')
    if not isfinite(float(aperture_left)) or not isfinite(float(aperture_right)):
        raise ValueError('Aperture Left/Right must be finite')
    if not isfinite(float(aperture_bottom)) or not isfinite(float(aperture_top)):
        raise ValueError('Aperture Bottom/Top must be finite')
    if not 0.0 <= float(aperture_left) < float(aperture_right) <= 1.0:
        raise ValueError('Aperture Left/Right must satisfy 0 <= left < right <= 1')
    if not 0.0 <= float(aperture_bottom) < float(aperture_top) <= 1.0:
        raise ValueError('Aperture Bottom/Top must satisfy 0 <= bottom < top <= 1')
    if not isfinite(float(aperture_feather)) or not 0.001 <= float(aperture_feather) <= 0.25:
        raise ValueError('Aperture Feather must be in [0.001, 0.25]')
    validate_hybrid_settings(int(seed), values['bvt_artifact_coverage'], droplet_scale, macro, micro, wetness)
    values['bvt_hybrid_wetness'] = float(wetness)
    values['bvt_hybrid_macro'] = float(macro)
    values['bvt_hybrid_micro'] = float(micro)
    values['bvt_artifact_mask_inset'] = float(mask_inset)
    values['bvt_artifact_mask_feather'] = float(mask_feather)
    values['bvt_artifact_aperture_left'] = float(aperture_left)
    values['bvt_artifact_aperture_right'] = float(aperture_right)
    values['bvt_artifact_aperture_bottom'] = float(aperture_bottom)
    values['bvt_artifact_aperture_top'] = float(aperture_top)
    values['bvt_artifact_aperture_feather'] = float(aperture_feather)
    # Ensure the target has a usable material before touching any stored properties.
    if obj.type != 'MESH' or obj.get('bvt_role') != 'glass_overlay':
        raise ValueError('Target is not a registered glass mesh')
    old_values = {key: obj.get(key) for key in (*values, 'bvt_artifact_seed',
                                                'bvt_artifact_preset')}
    try:
        for key, value in values.items():
            obj[key] = value
        obj['bvt_artifact_seed'] = int(seed)
        obj['bvt_artifact_preset'] = name
        configure_glass(obj)
    except Exception:
        # Undo covers material rebuilds; roll back object parameters as well.
        for key, old in old_values.items():
            if old is None:
                if key in obj:
                    del obj[key]
            else:
                obj[key] = old
        raise


class BVTSTUDIO_OT_apply_glass_preset(bpy.types.Operator):
    bl_idname = 'bvt_studio.apply_glass_preset'
    bl_label = 'Apply Glass Artifact Preset'
    bl_description = 'Apply seeded procedural glass effects to one BVT Glass Plane only'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            apply_preset(obj, settings.artifact_preset, settings.artifact_intensity,
                         settings.artifact_coverage, settings.artifact_seed,
                         settings.artifact_droplet_scale, settings.artifact_frost_edge,
                         settings.artifact_refraction, settings.artifact_relief,
                         settings.hybrid_wetness, settings.hybrid_macro, settings.hybrid_micro,
                         settings.artifact_mask_inset, settings.artifact_mask_feather,
                         settings.artifact_aperture_left, settings.artifact_aperture_right,
                         settings.artifact_aperture_bottom, settings.artifact_aperture_top,
                         settings.artifact_aperture_feather)
            context.view_layer.update()
            self.report({'INFO'}, f'{obj.name}: {settings.artifact_preset}, seed={settings.artifact_seed}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Glass preset: {exc}')
            return {'CANCELLED'}


class BVTSTUDIO_OT_refresh_glass_pattern(bpy.types.Operator):
    bl_idname = 'bvt_studio.refresh_glass_pattern'
    bl_label = 'Refresh Glass Pattern'
    bl_description = 'Rebuild seeded glass pattern after editing custom Seed on the object'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            obj = resolve_glass(context.scene, context.scene.bvt_studio, context.active_object)
            configure_glass(obj)
            context.view_layer.update()
            self.report({'INFO'}, f'Updated glass shader for {obj.name}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Glass pattern: {exc}')
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_apply_glass_preset, BVTSTUDIO_OT_refresh_glass_pattern)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
