"""Universal glass shader for user-created mesh planes.

Adapted from BVT_Setup_Selected_Glass_Plane_v02.py; no geometry is created.
"""
import bpy
import re
import uuid
from mathutils import Matrix, Vector
from .common import (
    make_material_transparent, ensure_collection, get_source, image_from_mesh,
)

DEFAULTS = {
    'bvt_glass_reflection': (0.10, 'Artificial LED-glass reflections'),
    'bvt_glass_tint': (0.012, 'Weak cool glass tint'),
    'bvt_glass_haze': (0.012, 'Glass haze and smudges'),
    'bvt_glass_frost': (0.000, 'Patchy freezer frost'),
}


def math_node(nodes, op, loc, label, val=None):
    node = nodes.new('ShaderNodeMath')
    node.operation = op
    node.location = loc
    node.label = label
    if val is not None:
        node.inputs[1].default_value = val
    return node


def driver_socket(socket, obj, key):
    fcurve = socket.driver_add('default_value')
    driver = fcurve.driver
    driver.type = 'SCRIPTED'
    driver.expression = 'v'
    var = driver.variables.new()
    var.name = 'v'
    var.type = 'SINGLE_PROP'
    target = var.targets[0]
    target.id_type = 'OBJECT'
    target.id = obj
    target.data_path = f'["{key}"]'


def ensure_uv(obj):
    mesh = obj.data
    if mesh.uv_layers.active:
        return
    verts = [v.co for v in mesh.vertices]
    spans = [(max(c[i] for c in verts) - min(c[i] for c in verts)) for i in range(3)]
    dims = sorted(range(3), key=lambda i: spans[i], reverse=True)[:2]
    if spans[dims[1]] < 1e-10:
        raise RuntimeError('Glass needs a non-degenerate plane mesh')
    mins = [min(c[i] for c in verts) for i in range(3)]
    uv_layer = mesh.uv_layers.new(name='BVT_Glass_UV')
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            c = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
            uv_layer.data[loop_idx].uv = (
                (c[dims[0]] - mins[dims[0]]) / spans[dims[0]],
                (c[dims[1]] - mins[dims[1]]) / spans[dims[1]],
            )


def reflection_band(nodes, links, diag, center, span, y):
    sub = math_node(nodes, 'SUBTRACT', (-260, y), 'LED offset', center)
    links.new(diag, sub.inputs[0])
    distance = math_node(nodes, 'ABSOLUTE', (-70, y), 'LED distance')
    links.new(sub.outputs[0], distance.inputs[0])
    feather = nodes.new('ShaderNodeMapRange')
    feather.location = (150, y)
    feather.interpolation_type = 'SMOOTHSTEP'
    feather.clamp = True
    feather.inputs['From Min'].default_value = 0.0
    feather.inputs['From Max'].default_value = span
    feather.inputs['To Min'].default_value = 1.0
    feather.inputs['To Max'].default_value = 0.0
    links.new(distance.outputs[0], feather.inputs['Value'])
    return feather.outputs['Result']


def noise_alpha(nodes, links, uv, scale, threshold_low, threshold_high, y):
    noise = nodes.new('ShaderNodeTexNoise')
    noise.location = (-500, y)
    noise.inputs['Scale'].default_value = scale
    noise.inputs['Detail'].default_value = 2.0
    links.new(uv, noise.inputs['Vector'])
    mask = nodes.new('ShaderNodeMapRange')
    mask.location = (-270, y)
    mask.clamp = True
    mask.inputs['From Min'].default_value = threshold_low
    mask.inputs['From Max'].default_value = threshold_high
    mask.inputs['To Min'].default_value = 0.0
    mask.inputs['To Max'].default_value = 1.0
    links.new(noise.outputs['Fac'], mask.inputs['Value'])
    return mask.outputs['Result']


def configure_glass(obj):
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    ensure_uv(obj)
    for key, (initial, description) in DEFAULTS.items():
        if key not in obj:
            obj[key] = initial
        try:
            obj.id_properties_ui(key).update(
                min=0.0, max=1.0, soft_min=0.0, soft_max=0.35,
                description=description, precision=3)
        except (AttributeError, TypeError, ValueError):
            pass
    obj['bvt_role'] = 'glass_overlay'
    obj['bvt_surface'] = 'glass'
    obj['bvt_studio_glass_version'] = '0.2'
    if 'bvt_glass_uid' not in obj:
        obj['bvt_glass_uid'] = uuid.uuid4().hex

    mat = obj.active_material
    if mat and mat.get('bvt_studio_glass') and mat.users == 1:
        pass
    else:
        mat = bpy.data.materials.new('BVT_Studio_Glass_' + obj.name)
    mat.use_nodes = True
    mat['bvt_studio_glass'] = True
    mat['bvt_owner'] = obj.name
    make_material_transparent(mat, 'BLENDED')
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()

    tex = nodes.new('ShaderNodeTexCoord')
    tex.location = (-980, 100)
    separate = nodes.new('ShaderNodeSeparateXYZ')
    separate.location = (-780, 130)
    links.new(tex.outputs['UV'], separate.inputs[0])
    tilt = math_node(nodes, 'MULTIPLY', (-580, 225), 'Diagonal LED tilt', 0.06)
    links.new(separate.outputs['X'], tilt.inputs[0])
    diag = math_node(nodes, 'ADD', (-390, 225), 'Reflection UV')
    links.new(separate.outputs['Y'], diag.inputs[0])
    links.new(tilt.outputs[0], diag.inputs[1])
    r1 = reflection_band(nodes, links, diag.outputs[0], 0.77, 0.085, 300)
    r2 = reflection_band(nodes, links, diag.outputs[0], 0.41, 0.04, 0)
    r2_weight = math_node(nodes, 'MULTIPLY', (400, 0), 'Secondary reflection', 0.35)
    links.new(r2, r2_weight.inputs[0])
    combine = math_node(nodes, 'ADD', (600, 240), 'LED reflections')
    links.new(r1, combine.inputs[0])
    links.new(r2_weight.outputs[0], combine.inputs[1])
    strength = math_node(nodes, 'MULTIPLY', (795, 235), 'Reflection strength')
    links.new(combine.outputs[0], strength.inputs[0])
    driver_socket(strength.inputs[1], obj, 'bvt_glass_reflection')

    haze = noise_alpha(nodes, links, tex.outputs['UV'], 26, .33, .69, -400)
    haze_strength = math_node(nodes, 'MULTIPLY', (300, -410), 'Haze amount')
    links.new(haze, haze_strength.inputs[0])
    driver_socket(haze_strength.inputs[1], obj, 'bvt_glass_haze')
    frost = noise_alpha(nodes, links, tex.outputs['UV'], 7, .56, .79, -770)
    frost_strength = math_node(nodes, 'MULTIPLY', (300, -770), 'Frost amount')
    links.new(frost, frost_strength.inputs[0])
    driver_socket(frost_strength.inputs[1], obj, 'bvt_glass_frost')

    sum1 = math_node(nodes, 'ADD', (990, 235), 'Glass reflections + haze')
    links.new(strength.outputs[0], sum1.inputs[0])
    links.new(haze_strength.outputs[0], sum1.inputs[1])
    sum2 = math_node(nodes, 'ADD', (1180, 235), 'Glass + frost')
    links.new(sum1.outputs[0], sum2.inputs[0])
    links.new(frost_strength.outputs[0], sum2.inputs[1])
    sum3 = math_node(nodes, 'ADD', (1360, 235), 'Cool tint')
    links.new(sum2.outputs[0], sum3.inputs[0])
    driver_socket(sum3.inputs[1], obj, 'bvt_glass_tint')
    alpha = math_node(nodes, 'MINIMUM', (1560, 235), 'Cap glass alpha', .95)
    links.new(sum3.outputs[0], alpha.inputs[0])
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    transparent.location = (1550, -50)
    reflection = nodes.new('ShaderNodeEmission')
    reflection.location = (1550, -220)
    reflection.inputs['Color'].default_value = (.88, .95, 1.0, 1.0)
    mix = nodes.new('ShaderNodeMixShader')
    mix.location = (1780, 160)
    links.new(alpha.outputs[0], mix.inputs[0])
    links.new(transparent.outputs['BSDF'], mix.inputs[1])
    links.new(reflection.outputs['Emission'], mix.inputs[2])
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (2010, 160)
    links.new(mix.outputs[0], output.inputs['Surface'])
    if not obj.material_slots:
        obj.data.materials.append(mat)
    else:
        obj.material_slots[0].link = 'OBJECT'
        obj.material_slots[0].material = mat
    obj.active_material = mat
    for poly in obj.data.polygons:
        poly.material_index = 0
    obj.hide_render = False
    obj.hide_viewport = False
    return mat


# Glass objects are semantically different from YOLO rectangles. Each scene has
# its own BVT_Glass collection; glass never goes in BVT_Annotations.
GLASS_COLLECTION = 'BVT_Glass'
GLASS_PREFIX = 'Glass_p_'

# The automatically created surface is an initial editable guide, not a
# reconstruction of the refrigerator lid. Fine tune its corners in the viewport.
DEFAULT_GLASS_WIDTH_FRACTION = 0.38
DEFAULT_GLASS_HEIGHT_FRACTION = 0.76
DEFAULT_GLASS_CAMERA_OFFSET_M = 0.02


def default_glass_rect(xmin, xmax, ymin, ymax, slot):
    """Return local width, height and center for an initial glass rectangle.

    First two clicks target approximate left/right halves of a top-down photo.
    Further surfaces start near center. The user positions every glass Plane.
    This function is deliberately Blender-independent for unit testing.
    """
    width = xmax - xmin
    height = ymax - ymin
    if width <= 1e-8 or height <= 1e-8:
        raise ValueError('Source Image Plane has invalid bounds')
    fraction_x = (-0.215, 0.215, 0.0)[slot % 3]
    center_x = (xmin + xmax) / 2.0 + fraction_x * width
    center_y = (ymin + ymax) / 2.0
    return (width * DEFAULT_GLASS_WIDTH_FRACTION,
            height * DEFAULT_GLASS_HEIGHT_FRACTION, center_x, center_y)


def next_glass_name():
    """Object names are global across .blend scenes, so check bpy.data."""
    i = 1
    while bpy.data.objects.get(f'{GLASS_PREFIX}{i:03d}') is not None:
        i += 1
    return f'{GLASS_PREFIX}{i:03d}', i

_GLASS_NUMBER_RX = re.compile(r'^Glass_p_(\d+)(?:\.(\d+))?$', re.I)
_LEGACY_GLASS_RX = re.compile(
    r'^(?:Glas|Glass)(?:[_ ]?(\d+))?(?:\.(\d+))?$', re.I)


def _is_glass_candidate(obj):
    if obj.type != 'MESH' or not obj.data.polygons:
        return False
    if obj.get('bvt_role') in {'annotation', 'planogram_image'}:
        return False
    if obj.name.lower().startswith('plane_p_') or obj.name.startswith('BVT_Freezer_Image_Plane'):
        return False
    return (obj.get('bvt_role') == 'glass_overlay' or
            _GLASS_NUMBER_RX.fullmatch(obj.name) is not None or
            _LEGACY_GLASS_RX.fullmatch(obj.name) is not None or
            obj.name.startswith('BVT_Glass_'))


def _glass_sort_key(obj):
    match = _GLASS_NUMBER_RX.fullmatch(obj.name)
    if match:
        return (0, int(match.group(1)), int(match.group(2) or 0), obj.name.lower())
    match = _LEGACY_GLASS_RX.fullmatch(obj.name)
    if match:
        return (1, int(match.group(1) or 0), int(match.group(2) or 0), obj.name.lower())
    return (2, 0, 0, obj.name.lower())


def scene_glass(scene):
    return sorted((o for o in scene.objects if _is_glass_candidate(o)),
                  key=_glass_sort_key)


def validate_glass_target(obj):
    if obj is None or obj.type != 'MESH' or not obj.data.polygons:
        raise ValueError('Select a mesh Plane to become glass')
    if obj.get('bvt_role') in {'annotation', 'planogram_image'} or \
            obj.name.startswith('plane_p_') or obj.name.startswith('BVT_Freezer_Image_Plane'):
        raise ValueError('Cannot overwrite a photo or annotation plane')
    mat = obj.active_material
    if mat is not None and mat.use_nodes and not mat.get('bvt_studio_glass'):
        textured = any(n.type == 'TEX_IMAGE' and n.image for n in mat.node_tree.nodes)
        if textured:
            raise ValueError('Selected Plane has an image texture: choose a separate glass Plane')
    if obj.library is not None or obj.data.library is not None:
        raise ValueError('Linked library mesh cannot be modified. Make it local first.')


def organize_glass(scene, objects):
    """Put user-owned glass meshes in a scene collection, never move/scale them."""
    col = ensure_collection(scene, GLASS_COLLECTION)
    for obj in objects:
        if scene.objects.get(obj.name) is None:
            raise ValueError(f'{obj.name} does not belong to the active scene')
        if obj.name not in col.objects:
            col.objects.link(obj)
        # Keep a clean Outliner; do not unlink from collections used in OTHER scenes.
        scene_cols = {c.as_pointer() for c in scene.collection.children_recursive}
        scene_cols.add(scene.collection.as_pointer())
        for old in list(obj.users_collection):
            if old != col and old.as_pointer() in scene_cols:
                old.objects.unlink(obj)
    return col


def renumber_glass(scene, objects):
    """Collision-safe sequential names with stable object UIDs and transforms."""
    ordered = sorted(objects, key=_glass_sort_key)
    targets = [f'{GLASS_PREFIX}{i:03d}' for i in range(1, len(ordered) + 1)]
    ours = {o.as_pointer() for o in ordered}
    for target in targets:
        existing = bpy.data.objects.get(target)
        if existing is not None and existing.as_pointer() not in ours:
            raise ValueError(f'Name {target} belongs to an unrelated object. Rename it first.')
    if any(o.library is not None for o in ordered):
        raise ValueError('A linked glass object cannot be renamed')
    # Short circuit for idempotent reruns.
    if [o.name for o in ordered] != targets:
        for obj in ordered:
            obj.name = '__BVT_GLASS_TMP_' + uuid.uuid4().hex
        for obj, name in zip(ordered, targets):
            obj.name = name
            if obj.name != name:
                raise RuntimeError(f'Failed to assign {name}; got {obj.name}')
    for i, obj in enumerate(ordered, 1):
        obj['bvt_glass_index'] = i
        obj['bvt_role'] = 'glass_overlay'
        obj['bvt_surface'] = 'glass'
        if 'bvt_glass_uid' not in obj:
            obj['bvt_glass_uid'] = uuid.uuid4().hex
        mat = obj.active_material
        if mat and mat.get('bvt_studio_glass') and mat.users == 1:
            mat['bvt_owner'] = obj.name
    return len(ordered)


class BVTSTUDIO_OT_add_glass(bpy.types.Operator):
    bl_idname = 'bvt_studio.add_glass'
    bl_label = 'Add Glass Plane'
    bl_description = ('Create and configure a movable glass Plane in front of '
                      'the source photo, inside BVT_Glass')
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and hasattr(context.scene, 'bvt_studio')

    def execute(self, context):
        scene = context.scene
        if (scene.bvt_studio.scene_locks_enabled and
                not scene.bvt_studio.glass_edit_enable):
            self.report({'WARNING'}, 'Enable Glass Edit before adding a glass Plane')
            return {'CANCELLED'}
        source = get_source(scene)
        if source is None or source.type != 'MESH' or image_from_mesh(source) is None:
            self.report({'ERROR'}, 'First import a photo or assign a textured Source Plane')
            return {'CANCELLED'}
        if not source.data.vertices or not source.data.polygons:
            self.report({'ERROR'}, 'Source Image Plane has no valid mesh')
            return {'CANCELLED'}
        try:
            coords = [v.co for v in source.data.vertices]
            xmin, xmax = min(p.x for p in coords), max(p.x for p in coords)
            ymin, ymax = min(p.y for p in coords), max(p.y for p in coords)
            existing_count = len(scene_glass(scene))
            width, height, center_x, center_y = default_glass_rect(
                xmin, xmax, ymin, ymax, existing_count)
            name, index = next_glass_name()
            mesh = bpy.data.meshes.new('BVT_Glass_Plane_Mesh')
            mesh.from_pydata(
                [(-width / 2, -height / 2, 0),
                 (width / 2, -height / 2, 0),
                 (width / 2, height / 2, 0),
                 (-width / 2, height / 2, 0)],
                [], [(0, 1, 2, 3)])
            mesh.update()
            obj = bpy.data.objects.new(name, mesh)
            ensure_collection(scene, GLASS_COLLECTION).objects.link(obj)

            # Preserve the photo plane's orientation/scale; move it slightly
            # toward the actual active camera so glass composites over photo.
            matrix = source.matrix_world @ Matrix.Translation(
                (center_x, center_y, 0.0))
            camera = scene.camera
            if camera is not None:
                front = (camera.matrix_world.to_quaternion() @
                         Vector((0, 0, 1))).normalized()
            else:
                front = (source.matrix_world.to_quaternion() @
                         Vector((0, 0, 1))).normalized()
            matrix.translation += front * DEFAULT_GLASS_CAMERA_OFFSET_M
            obj.matrix_world = matrix
            obj['bvt_glass_index'] = index
            configure_glass(obj)
            from .scene_lock import apply_scene_locks
            apply_scene_locks(scene)

            # Select only the newly created surface for immediate resizing.
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            context.view_layer.update()
            self.report({'INFO'},
                        f'Created {obj.name}; adjust size and position over glass')
            return {'FINISHED'}
        except Exception as exc:
            # The operation is undoable; don't leave a half-configured Plane.
            if 'obj' in locals():
                bpy.data.objects.remove(obj, do_unlink=True)
            elif 'mesh' in locals():
                bpy.data.meshes.remove(mesh)
            self.report({'ERROR'}, f'Add Glass failed: {exc}')
            return {'CANCELLED'}


class BVTSTUDIO_OT_setup_glass(bpy.types.Operator):
    bl_idname = 'bvt_studio.setup_glass'
    bl_label = 'Setup Selected Glass'
    bl_description = 'Configure selected Plane, move it to BVT_Glass and number Glass_p_001...N'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        try:
            validate_glass_target(obj)
            configure_glass(obj)
            objects = scene_glass(context.scene)
            organize_glass(context.scene, objects)
            renumber_glass(context.scene, objects)
            from .scene_lock import apply_scene_locks
            apply_scene_locks(context.scene)
            context.view_layer.update()
            self.report({'INFO'}, f'Glass: {obj.name} (collection {GLASS_COLLECTION})')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BVTSTUDIO_OT_setup_selected_glass_batch(bpy.types.Operator):
    bl_idname = 'bvt_studio.setup_selected_glass_batch'
    bl_label = 'Setup Selected Glass Planes (Batch)'
    bl_description = 'Turn all selected untextured mesh planes into Glass_p_001...N'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Exclude other types; do not treat the photo or YOLO planes as glass.
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected:
            self.report({'ERROR'}, 'Select one or more empty glass mesh Planes')
            return {'CANCELLED'}
        # Validate ALL selected objects before changing any of them.
        try:
            for obj in selected:
                validate_glass_target(obj)
            for obj in selected:
                configure_glass(obj)
            all_glass = scene_glass(context.scene)
            organize_glass(context.scene, all_glass)
            renumber_glass(context.scene, all_glass)
            from .scene_lock import apply_scene_locks
            apply_scene_locks(context.scene)
            context.view_layer.update()
            self.report({'INFO'},
                        f'Configured {len(selected)} selected glass Plane(s) in {GLASS_COLLECTION}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BVTSTUDIO_OT_organize_glass(bpy.types.Operator):
    bl_idname = 'bvt_studio.organize_glass'
    bl_label = 'Register / Setup Glass Planes'
    bl_description = 'Find Glass/Glas/Glass_p_* meshes; apply glass shader and organize them'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = scene_glass(context.scene)
        if not objects:
            self.report({'WARNING'}, 'No glass-looking meshes found. Select a Plane and click Setup Selected Glass.')
            return {'CANCELLED'}
        valid, problems = [], []
        for obj in objects:
            try:
                validate_glass_target(obj)
                valid.append(obj)
            except Exception as exc:
                problems.append(f'{obj.name}: {exc}')
        if not valid:
            self.report({'ERROR'}, 'No safe glass meshes to configure; check System Console')
            for issue in problems:
                print('[BVT Studio][Glass]', issue)
            return {'CANCELLED'}
        try:
            organize_glass(context.scene, valid)
            renumber_glass(context.scene, valid)
            for obj in valid:
                configure_glass(obj)
            from .scene_lock import apply_scene_locks
            apply_scene_locks(context.scene)
            context.view_layer.update()
            for issue in problems:
                print('[BVT Studio][Glass] skipped', issue)
            self.report({'INFO'}, f'Configured {len(valid)} glass Plane(s) in {GLASS_COLLECTION}; skipped {len(problems)}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BVTSTUDIO_OT_renumber_glass(bpy.types.Operator):
    bl_idname = 'bvt_studio.renumber_glass'
    bl_label = 'Renumber Glass 001...N'
    bl_description = 'Renumber detected Glass planes; preserve all world transforms and materials'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = scene_glass(context.scene)
        if not objects:
            self.report({'WARNING'}, 'No glass planes found')
            return {'CANCELLED'}
        try:
            organize_glass(context.scene, objects)
            n = renumber_glass(context.scene, objects)
            self.report({'INFO'}, f'Renumbered {n} glass planes')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_add_glass, BVTSTUDIO_OT_setup_glass,
           BVTSTUDIO_OT_setup_selected_glass_batch,
           BVTSTUDIO_OT_organize_glass, BVTSTUDIO_OT_renumber_glass)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
