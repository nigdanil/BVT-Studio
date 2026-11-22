"""Per-glass packed grayscale PNG masks and final shader gating.

The optional PNG belongs to the Glass object (by persistent image datablock
name). Black means no glass effect, white means full effect, intermediate gray
mixes the original unmodified photo with the glass effect. The PNG is sampled
in Glass UV space, not world space, so rotated Photo Planes also work.
"""
from pathlib import Path

MASK_IMAGE_KEY = 'bvt_glass_mask_image'
MASK_PATH_KEY = 'bvt_glass_mask_path'
MASK_ENABLED_KEY = 'bvt_glass_mask_enabled'


def mask_image_for(obj):
    """Fail closed when a requested mask is absent, never silently unmask."""
    import bpy
    if not bool(obj.get(MASK_ENABLED_KEY, False)):
        return None
    name = str(obj.get(MASK_IMAGE_KEY, ''))
    image = bpy.data.images.get(name) if name else None
    if image is None or image.source != 'FILE' or min(image.size) <= 0:
        raise ValueError(f'{obj.name}: enabled PNG glass mask is unavailable ({name})')
    return image


def load_mask_for_glass(obj, filepath):
    """Import one real PNG into an independent packed Blender image datablock.

    Stores both the source path for provenance and the packed image name for
    reliable save/reopen. Replacing a mask does not alter another glass mask.
    """
    import bpy
    if obj is None or obj.type != 'MESH' or obj.get('bvt_role') != 'glass_overlay':
        raise ValueError('Select a registered BVT Glass Plane')
    if obj.library is not None or obj.data.library is not None:
        raise ValueError('Cannot edit masks on linked library glass')
    full = Path(bpy.path.abspath(str(filepath))).expanduser().resolve()
    if full.suffix.lower() != '.png' or not full.is_file():
        raise ValueError('Glass mask must be an existing PNG file')
    image = bpy.data.images.load(str(full), check_existing=False)
    try:
        if image.file_format != 'PNG' or min(image.size) < 2:
            raise ValueError('Glass mask must be a valid PNG, at least 2x2 pixels')
        image.colorspace_settings.name = 'Non-Color'
        image.alpha_mode = 'STRAIGHT'
        image.name = 'BVT_Glass_Mask_' + str(obj.get('bvt_glass_uid', obj.name))[:20]
        image.pack()
        if not image.packed_file:
            raise RuntimeError('Mask image could not be packed into the .blend')
        # Preserve packed masks even when no shader node uses them.
        # Required for QA_TRANSPARENT and disabled masks.
        image.use_fake_user = True
        old = {key: obj.get(key) for key in (MASK_IMAGE_KEY, MASK_PATH_KEY, MASK_ENABLED_KEY)}
        try:
            obj[MASK_IMAGE_KEY] = image.name
            obj[MASK_PATH_KEY] = str(full)
            obj[MASK_ENABLED_KEY] = True
            from .glass import configure_glass
            configure_glass(obj)
        except Exception:
            for key, prev in old.items():
                if prev is None:
                    if key in obj:
                        del obj[key]
                else:
                    obj[key] = prev
            raise
        return image
    except Exception:
        bpy.data.images.remove(image)
        raise


def set_mask_enabled(obj, enabled):
    """Enable/disable without discarding the packed image. Rebuild immediately."""
    from .glass import configure_glass
    old = bool(obj.get(MASK_ENABLED_KEY, False))
    if enabled:
        name = obj.get(MASK_IMAGE_KEY)
        if not name:
            raise ValueError('Assign a PNG glass mask before enabling it')
        # Check image before changing the material.
        obj[MASK_ENABLED_KEY] = True
        try:
            mask_image_for(obj)
        except Exception:
            obj[MASK_ENABLED_KEY] = old
            raise
    else:
        obj[MASK_ENABLED_KEY] = False
    try:
        configure_glass(obj)
    except Exception:
        obj[MASK_ENABLED_KEY] = old
        raise


def _value(nodes, name, value):
    node = nodes.new('ShaderNodeValue')
    node.name = name
    node.outputs[0].default_value = float(value)
    return node.outputs[0]


def png_mask_socket(obj, nodes, links, uv_socket):
    """Return a grayscale ShaderNode socket in [0,1], or a constant one.

    Alpha is deliberately ignored: user semantics refer to grayscale RGB
    luminance, so PNGs with opaque or transparent alpha work consistently.
    """
    image = mask_image_for(obj)
    if image is None:
        return _value(nodes, 'BVT_PNG_Mask_Disabled', 1.0)
    sample = nodes.new('ShaderNodeTexImage')
    sample.name = 'BVT_Precision_PNG_Mask'
    sample.image = image
    sample.extension = 'CLIP'
    sample.interpolation = 'Linear'
    links.new(uv_socket, sample.inputs['Vector'])
    bw = nodes.new('ShaderNodeRGBToBW')
    bw.name = 'BVT_Precision_PNG_Luminance'
    links.new(sample.outputs['Color'], bw.inputs['Color'])
    return bw.outputs['Val']


def apply_precision_mask(obj, nodes, links, output, uv_socket, hybrid=False):
    """Gate the *final* shader, including reflections, haze, frost, and refraction.

    Hybrid already applies the analytic inset/aperture inside every channel.
    It receives the external PNG once on final output, preventing gray values
    (e.g. 0.5) from being squared by a second analytic mask. For all other
    presets the analytic aperture and PNG both gate the final output.
    """
    from .hybrid_condensation import _combined_glass_mask
    analytic = (nodes.get('BVT_Hybrid_Combined_Mask').outputs[0] if hybrid else
                _combined_glass_mask(obj, nodes, links, uv_socket))
    png = png_mask_socket(obj, nodes, links, uv_socket)
    masked = nodes.new('ShaderNodeMath')
    masked.name = 'BVT_Precision_QA_Mask'
    masked.operation = 'MULTIPLY'
    links.new(analytic, masked.inputs[0])
    links.new(png, masked.inputs[1])

    old_surface = output.inputs['Surface'].links[0].from_socket
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    transparent.name = 'BVT_Precision_Transparent_Outside'
    gate = nodes.new('ShaderNodeMixShader')
    gate.name = 'BVT_Precision_Final_Mask_Gate'
    # Hybrid channels already contain the analytic mask; gate only the PNG
    # once at the output. Non-hybrid has no channel-local analytic mask.
    links.new(png if hybrid else masked.outputs[0], gate.inputs[0])
    links.new(transparent.outputs[0], gate.inputs[1])
    links.new(old_surface, gate.inputs[2])
    links.new(gate.outputs[0], output.inputs['Surface'])
    return masked.outputs[0]


def force_transparent_control(nodes, links, output):
    """Independent QA baseline; original CLEAN retains legacy weak reflections."""
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    transparent.name = 'BVT_QA_Transparent_Control'
    links.new(transparent.outputs['BSDF'], output.inputs['Surface'])

# Operator registration stays in this independent module, not in YOLO/export.
import bpy


class BVTSTUDIO_OT_assign_precision_mask(bpy.types.Operator):
    bl_idname = 'bvt_studio.assign_precision_mask'
    bl_label = 'Assign Packed PNG Glass Mask'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        try:
            obj = resolve_glass(context.scene, context.scene.bvt_studio,
                                context.active_object)
            img = load_mask_for_glass(obj, context.scene.bvt_studio.precision_mask_path)
            self.report({'INFO'}, f'{obj.name}: packed mask {img.name} ({img.size[0]}x{img.size[1]})')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'PNG mask: {exc}')
            return {'CANCELLED'}


class BVTSTUDIO_OT_toggle_precision_mask(bpy.types.Operator):
    bl_idname = 'bvt_studio.toggle_precision_mask'
    bl_label = 'Toggle Glass PNG Mask'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .artifact_presets import resolve_glass
        try:
            obj = resolve_glass(context.scene, context.scene.bvt_studio,
                                context.active_object)
            set_mask_enabled(obj, not bool(obj.get(MASK_ENABLED_KEY, False)))
            self.report({'INFO'}, f'{obj.name}: PNG mask enabled={bool(obj[MASK_ENABLED_KEY])}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'PNG mask: {exc}')
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_assign_precision_mask, BVTSTUDIO_OT_toggle_precision_mask)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
