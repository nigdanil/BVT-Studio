"""Optional atlas-only contact-line optics for BVT Studio 2.5D glass.

Enhances an EXISTING synthetic REALISTIC_ATLAS. No camera geometry, source
images, masks, or YOLO boxes are modified. Effects are deliberately bounded:
this is an approximate screen-space lens, not physically traced water.
"""
from math import isfinite

ENABLED_KEY = 'bvt_optical_water_enabled'
LENS_KEY = 'bvt_optical_lens_gain'
EDGE_KEY = 'bvt_optical_edge_gain'
GLINT_KEY = 'bvt_optical_glint_gain'
MICRO_KEY = 'bvt_optical_micro_gain'
DEFAULTS = {LENS_KEY: 1.45, EDGE_KEY: 1.0,
            GLINT_KEY: 1.25, MICRO_KEY: .35}
LIMITS = {LENS_KEY: (.25, 2.5), EDGE_KEY: (0., 2.5),
          GLINT_KEY: (0., 2.5), MICRO_KEY: (0., 1.)}


def validate_optical(enabled, lens, edge, glint, micro):
    if type(enabled) is not bool:
        raise ValueError('Optical enable must be a bool')
    for name, value in zip((LENS_KEY, EDGE_KEY, GLINT_KEY, MICRO_KEY),
                           (lens, edge, glint, micro)):
        lo, hi = LIMITS[name]
        if not isfinite(float(value)) or not lo <= float(value) <= hi:
            raise ValueError(f'{name} must be finite and in [{lo}, {hi}]')


def optical_enabled(obj):
    from .droplet_maps import MODE_KEY
    return (obj.get(MODE_KEY) == 'REALISTIC_ATLAS'
            and bool(obj.get(ENABLED_KEY, False)))


def set_optical_water(obj, enabled, lens=1.45, edge=1.0, glint=1.25, micro=.35):
    """Atomically update one registered glass and rebuild its material.

    Existing photo map banks / precision PNG masks are not touched.
    Disabling restores the exact pre-optical node topology.
    """
    from .droplet_maps import _glass_check, packed_maps_for
    _glass_check(obj)
    validate_optical(enabled, lens, edge, glint, micro)
    if enabled:
        packed_maps_for(obj, mode='REALISTIC_ATLAS')
        if obj.get('bvt_droplet_source_mode') != 'REALISTIC_ATLAS':
            raise ValueError('Enable optical water only in REALISTIC_ATLAS mode')
    keys = (ENABLED_KEY, LENS_KEY, EDGE_KEY, GLINT_KEY, MICRO_KEY)
    old = {key: obj.get(key) for key in keys}
    try:
        for key, value in zip(keys, (enabled, lens, edge, glint, micro)):
            obj[key] = value
        from .glass import configure_glass
        configure_glass(obj)
    except Exception:
        for key, value in old.items():
            if value is None:
                if key in obj:
                    del obj[key]
            else:
                obj[key] = value
        try:
            from .glass import configure_glass
            configure_glass(obj)
        except Exception:
            pass
        raise


def _math(nodes, links, name, operation, a=None, b=None, const=None):
    node = nodes.new('ShaderNodeMath')
    node.name, node.operation = name, operation
    if a is not None:
        links.new(a, node.inputs[0])
    if b is not None:
        links.new(b, node.inputs[1])
    if const is not None:
        node.inputs[1].default_value = float(const)
    return node.outputs[0]


def _range(nodes, links, name, socket, lo, hi, invert=False):
    node = nodes.new('ShaderNodeMapRange')
    node.name = name
    node.interpolation_type = 'SMOOTHSTEP'
    node.clamp = True
    node.inputs['From Min'].default_value = float(lo)
    node.inputs['From Max'].default_value = float(hi)
    node.inputs['To Min'].default_value = 1. if invert else 0.
    node.inputs['To Max'].default_value = 0. if invert else 1.
    links.new(socket, node.inputs['Value'])
    return node.outputs['Result']


def optical_sockets(obj, nodes, links, x, y, height, glass_mask):
    """Return contact-line specular, shadow, micro glint and lens scale.

    Slopes are encoded 0.5-neutral normal X/Y channels and supplied already
    decoded as (gx-.5, gy-.5). A contact line requires both nonzero slope and
    a peripheral height band. Thus flat wet areas do not become white haze.
    """
    from .glass import driver_socket
    xx = _math(nodes, links, 'BVT_Optical_Slope_X2', 'MULTIPLY', x, x)
    yy = _math(nodes, links, 'BVT_Optical_Slope_Y2', 'MULTIPLY', y, y)
    magnitude = _math(nodes, links, 'BVT_Optical_Slope_Magnitude', 'SQRT',
                      _math(nodes, links, 'BVT_Optical_Slope_Sum', 'ADD', xx, yy))
    # Narrow, slope-dependent contact arcs: a broad band drew white soap-bubble
    # outlines over product labels in the step3 gallery.  These bounds reduce
    # the potential highlighted atlas area without altering Alpha/Height maps.
    slope = _range(nodes, links, 'BVT_Optical_Contact_Slope', magnitude, .055, .17)
    outer = _range(nodes, links, 'BVT_Optical_Contact_Height_Low', height, .14, .28)
    inner = _range(nodes, links, 'BVT_Optical_Contact_Height_High', height, .35, .48, invert=True)
    band = _math(nodes, links, 'BVT_Optical_Contact_Band', 'MINIMUM', outer, inner)
    band = _math(nodes, links, 'BVT_Optical_Contact_Slope_Band', 'MULTIPLY', band, slope)
    band = _math(nodes, links, 'BVT_Optical_Contact_Glass_Mask', 'MULTIPLY', band, glass_mask)

    # Directional opposing rims approximate an oblique strip-light reflection.
    bright_x = _math(nodes, links, 'BVT_Optical_Bright_X', 'MULTIPLY', x, const=-1.15)
    bright_y = _math(nodes, links, 'BVT_Optical_Bright_Y', 'MULTIPLY', y, const=.82)
    light = _math(nodes, links, 'BVT_Optical_Bright_Vector', 'ADD', bright_x, bright_y)
    light = _math(nodes, links, 'BVT_Optical_Bright_Positive', 'MAXIMUM', light, const=0.)
    light = _range(nodes, links, 'BVT_Optical_Bright_Arc_Threshold', light, .12, .30)
    # Shadow uses the opposite direction to light (before positive clamp).
    negative = _math(nodes, links, 'BVT_Optical_Shadow_Negate', 'MULTIPLY',
                     _math(nodes, links, 'BVT_Optical_Shadow_Raw', 'ADD', bright_x, bright_y), const=-1.)
    negative = _math(nodes, links, 'BVT_Optical_Shadow_Positive', 'MAXIMUM', negative, const=0.)
    negative = _range(nodes, links, 'BVT_Optical_Shadow_Arc_Threshold', negative, .12, .30)
    highlight = _math(nodes, links, 'BVT_Optical_Specular_Contact', 'MULTIPLY', light, band)
    highlight = _math(nodes, links, 'BVT_Optical_Specular_Gain', 'MULTIPLY', highlight)
    driver_socket(highlight.node.inputs[1], obj, GLINT_KEY)
    highlight = _math(nodes, links, 'BVT_Optical_Specular_LowEnergy',
                      'MULTIPLY', highlight, const=(.19 if obj.get('bvt_optical_stress_test', False) else .095))
    highlight = _math(nodes, links, 'BVT_Optical_Specular_Limit',
                      'MINIMUM', highlight, const=(.28 if obj.get('bvt_optical_stress_test', False) else .16))
    shade = _math(nodes, links, 'BVT_Optical_Shadow_Contact', 'MULTIPLY', negative, band)
    shade = _math(nodes, links, 'BVT_Optical_Shadow_Gain', 'MULTIPLY', shade)
    driver_socket(shade.node.inputs[1], obj, EDGE_KEY)
    shade = _math(nodes, links, 'BVT_Optical_Shadow_LowEnergy',
                  'MULTIPLY', shade, const=(.14 if obj.get('bvt_optical_stress_test', False) else .070))
    shade = _math(nodes, links, 'BVT_Optical_Shadow_Limit',
                  'MINIMUM', shade, const=(.19 if obj.get('bvt_optical_stress_test', False) else .10))

    # Sparse tiny highlights in the small-height band; do not add an all-over film.
    micro_lo = _range(nodes, links, 'BVT_Optical_Micro_Low', height, .03, .17)
    micro_hi = _range(nodes, links, 'BVT_Optical_Micro_High', height, .22, .46, invert=True)
    micro = _math(nodes, links, 'BVT_Optical_Micro_Band', 'MINIMUM', micro_lo, micro_hi)
    micro = _math(nodes, links, 'BVT_Optical_Micro_Slope', 'MULTIPLY', micro, slope)
    micro = _math(nodes, links, 'BVT_Optical_Micro_Mask', 'MULTIPLY', micro, glass_mask)
    micro = _math(nodes, links, 'BVT_Optical_Micro_Amount', 'MULTIPLY', micro)
    driver_socket(micro.node.inputs[1], obj, MICRO_KEY)
    micro = _math(nodes, links, 'BVT_Optical_Micro_Clamp', 'MINIMUM', micro, const=(.06 if obj.get('bvt_optical_stress_test', False) else .025))

    return highlight, shade, micro


import bpy


class BVTSTUDIO_OT_apply_optical_water(bpy.types.Operator):
    bl_idname = 'bvt_studio.apply_optical_water'
    bl_label = 'Enable Optical Water'
    bl_description = 'Enable optional refraction/rim optics for the selected Realistic Atlas glass'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            set_optical_water(obj, True, settings.optical_lens_gain,
                              settings.optical_edge_gain, settings.optical_glint_gain,
                              settings.optical_micro_gain)
            self.report({'INFO'}, f'{obj.name}: optical water enabled')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Optical water: {exc}')
            return {'CANCELLED'}


class BVTSTUDIO_OT_disable_optical_water(bpy.types.Operator):
    bl_idname = 'bvt_studio.disable_optical_water'
    bl_label = 'Disable Optical Water'
    bl_description = 'Restore the baseline atlas shader without deleting any maps'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        settings = context.scene.bvt_studio
        try:
            obj = resolve_glass(context.scene, settings, context.active_object)
            set_optical_water(obj, False,
                              float(obj.get(LENS_KEY, DEFAULTS[LENS_KEY])),
                              float(obj.get(EDGE_KEY, DEFAULTS[EDGE_KEY])),
                              float(obj.get(GLINT_KEY, DEFAULTS[GLINT_KEY])),
                              float(obj.get(MICRO_KEY, DEFAULTS[MICRO_KEY])))
            self.report({'INFO'}, f'{obj.name}: original atlas optics restored')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Optical water: {exc}')
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_apply_optical_water, BVTSTUDIO_OT_disable_optical_water)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
