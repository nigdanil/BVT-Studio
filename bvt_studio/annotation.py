"""Manual annotation planes, renderable outlines, checks, single-frame YOLO export."""
import bpy
import json
import re
import uuid
from pathlib import Path
from bpy_extras.object_utils import world_to_camera_view
from bpy.props import BoolProperty
from mathutils import Matrix, Vector
from .common import (
    ANNOT_PREFIX, PALETTE, ensure_collection, scene_annotations,
    get_source, world_size_xy,
)

PREVIEW_PROP = 'bvt_studio_render_annotation_preview'


def next_annotation_name(scene):
    names = set(bpy.data.objects.keys())
    i = 1
    while f'{ANNOT_PREFIX}{i:03d}' in names:
        i += 1
    return f'{ANNOT_PREFIX}{i:03d}'


def annotation_color(index):
    return PALETTE[index % len(PALETTE)]


def ensure_outline_material(obj, color):
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    mat = obj.active_material
    if not (mat and mat.get('bvt_studio_outline') and mat.users == 1):
        mat = bpy.data.materials.new('BVT_Studio_Outline_' + obj.name)
    mat['bvt_studio_outline'] = True
    mat.use_nodes = True
    mat.diffuse_color = color
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    emit = nodes.new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = color
    emit.inputs['Strength'].default_value = 1.35
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(emit.outputs['Emission'], out.inputs['Surface'])
    if not obj.material_slots:
        obj.data.materials.append(mat)
    else:
        obj.material_slots[0].link = 'OBJECT'
        obj.material_slots[0].material = mat
    obj.active_material = mat
    return mat


def configure_outline(obj, index, preview):
    color = annotation_color(index)
    ensure_outline_material(obj, color)
    mod = obj.modifiers.get('BVT_Annotation_Wireframe')
    if mod is None or mod.type != 'WIREFRAME':
        if mod is not None:
            obj.modifiers.remove(mod)
        mod = obj.modifiers.new('BVT_Annotation_Wireframe', 'WIREFRAME')
    # Keep approx. 2 mm line thickness, even on scaled objects.
    basis = obj.matrix_world.to_3x3()
    sx = (basis @ Vector((1, 0, 0))).length
    sy = (basis @ Vector((0, 1, 0))).length
    mod.thickness = .002 / max(min(sx, sy), 1e-6)
    mod.use_replace = True
    mod.use_boundary = True
    mod.offset = 0.0
    mod.show_viewport = True
    mod.show_render = True
    obj['bvt_role'] = 'annotation'
    obj['bvt_annotation_type'] = 'bbox'
    obj['bvt_enabled'] = bool(obj.get('bvt_enabled', True))
    obj['bvt_class_id'] = int(obj.get('bvt_class_id', 0))
    obj['bvt_class_name'] = str(obj.get('bvt_class_name', 'ice_cream'))
    if 'bvt_annotation_uid' not in obj:
        obj['bvt_annotation_uid'] = uuid.uuid4().hex
    obj.display_type = 'TEXTURED'  # Wireframe modifier, not wire-only display.
    obj.show_in_front = True
    obj.color = color
    obj.hide_viewport = False
    obj.hide_set(False)
    obj.hide_render = not preview


def renumber(scene, objects):
    targets = [f'{ANNOT_PREFIX}{i:03d}' for i in range(1, len(objects) + 1)]
    ours = {obj.as_pointer() for obj in objects}
    for target in targets:
        existing = bpy.data.objects.get(target)
        if existing is not None and existing.as_pointer() not in ours:
            raise RuntimeError(
                f'Name {target} is used by another object; rename it first')
    old_names = [obj.name for obj in objects]
    for obj in objects:
        obj.name = f'__BVT_STUDIO_TMP_{uuid.uuid4().hex}__'
    for i, (obj, original_name, desired) in enumerate(zip(objects, old_names, targets), 1):
        obj.name = desired
        if obj.name != desired:
            raise RuntimeError(f'Could not rename {original_name} to {desired}')
        obj['bvt_annotation_index'] = i
        if 'bvt_original_annotation_name' not in obj:
            obj['bvt_original_annotation_name'] = original_name
    return len(objects)


def collect_boxes(scene):
    """Return sorted YOLO rectangles, issues, class index map.

    Uses RAW mesh vertices (not evaluated modifier meshes), so rendered wire
    thickness cannot change annotations. Coordinates are camera-normalized.
    """
    issues, boxes, classes = [], [], {}
    cam = scene.camera
    if cam is None or cam.type != 'CAMERA':
        return boxes, ['No active scene camera'], classes
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = [obj for obj in scene_annotations(scene) if obj.get('bvt_enabled', True)]
    if not objects:
        return boxes, ['No enabled annotation planes'], classes
    for obj in objects:
        cls = int(obj.get('bvt_class_id', 0))
        name = str(obj.get('bvt_class_name', 'ice_cream')).strip() or 'ice_cream'
        if cls < 0:
            issues.append(f'{obj.name}: negative class ID')
            continue
        if cls in classes and classes[cls] != name:
            issues.append(f'Class {cls}: conflicting names {classes[cls]} / {name}')
        classes[cls] = name
        if not obj.data.vertices:
            issues.append(f'{obj.name}: empty mesh')
            continue
        # Use original vertices (not Wireframe-modified geometry), but the
        # evaluated object transform so constraints and YOLO export agree.
        evaluated_matrix = obj.evaluated_get(depsgraph).matrix_world
        ndc = [world_to_camera_view(scene, cam, evaluated_matrix @ v.co)
               for v in obj.data.vertices]
        if any(p.z <= 0 for p in ndc):
            issues.append(f'{obj.name}: plane behind camera')
            continue
        xs = [p.x for p in ndc]
        ys = [1.0 - p.y for p in ndc]  # YOLO origin is top-left
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmin < -1e-5 or ymin < -1e-5 or xmax > 1.00001 or ymax > 1.00001:
            issues.append(f'{obj.name}: part of bbox is outside frame')
            continue
        xmin, xmax = max(0.0, xmin), min(1.0, xmax)
        ymin, ymax = max(0.0, ymin), min(1.0, ymax)
        w, h = xmax - xmin, ymax - ymin
        if w < 1e-5 or h < 1e-5:
            issues.append(f'{obj.name}: zero or tiny projected bbox')
            continue
        boxes.append(dict(
            object=obj.name, uid=str(obj.get('bvt_annotation_uid', obj.name)),
            class_id=cls, class_name=name,
            x=(xmin + xmax) / 2.0, y=(ymin + ymax) / 2.0,
            w=w, h=h, xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
        ))
    if classes and set(classes) != set(range(max(classes) + 1)):
        issues.append('Class IDs must be contiguous 0..N-1 for data.yaml')
    # Check near-duplicate boxes of same class; overlaps are otherwise allowed.
    for i, a in enumerate(boxes):
        for b in boxes[i+1:]:
            if a['class_id'] != b['class_id']:
                continue
            ix = max(0, min(a['xmax'], b['xmax']) - max(a['xmin'], b['xmin']))
            iy = max(0, min(a['ymax'], b['ymax']) - max(a['ymin'], b['ymin']))
            intersection = ix * iy
            union = a['w'] * a['h'] + b['w'] * b['h'] - intersection
            if union > 0 and intersection / union > 0.95:
                issues.append(f'Near-duplicate boxes: {a["object"]} and {b["object"]}')
    return boxes, issues, classes


class BVTSTUDIO_OT_add_annotation(bpy.types.Operator):
    bl_idname = 'bvt_studio.add_annotation'
    bl_label = 'Add Annotation Plane'
    bl_description = 'Create an annotation rectangle in front of the source photo'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.bvt_studio
        if settings.scene_locks_enabled and not settings.annotations_edit_enable:
            self.report({'WARNING'}, 'Enable Annotations Edit before adding a box')
            return {'CANCELLED'}
        source = get_source(context.scene)
        if source is None:
            self.report({'ERROR'}, 'First set a source Image Plane')
            return {'CANCELLED'}
        width, height = world_size_xy(source)
        if min(width, height) < .0001:
            self.report({'ERROR'}, 'Source photo size is invalid')
            return {'CANCELLED'}
        # Mesh dimensions in local plane coordinates; source transform includes scale.
        coords = [Vector(v) for v in source.bound_box]
        wloc = max(v.x for v in coords) - min(v.x for v in coords)
        hloc = max(v.y for v in coords) - min(v.y for v in coords)
        w, h = wloc * .075, hloc * .15
        mesh = bpy.data.meshes.new('BVT_Annotation_Rect_Mesh')
        mesh.from_pydata([(-w/2, -h/2, 0), (w/2, -h/2, 0),
                          (w/2, h/2, 0), (-w/2, h/2, 0)], [], [(0, 1, 2, 3)])
        mesh.update()
        obj = bpy.data.objects.new(next_annotation_name(context.scene), mesh)
        ensure_collection(context.scene, 'BVT_Annotations').objects.link(obj)
        cam = context.scene.camera
        source_normal = (source.matrix_world.to_quaternion() @ Vector((0, 0, 1))).normalized()
        signed = 1.0
        if cam is not None:
            if source_normal.dot(cam.location - source.matrix_world.translation) < 0:
                signed = -1.0
        obj.matrix_world = source.matrix_world @ Matrix.Translation((0, 0, signed * 0.03))
        configure_outline(obj, len(scene_annotations(context.scene)) - 1,
                          bool(context.scene.get(PREVIEW_PROP, False)))
        from .scene_lock import apply_scene_locks
        apply_scene_locks(context.scene)
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report({'INFO'}, f'Created {obj.name}; position and scale over an SKU')
        return {'FINISHED'}


class BVTSTUDIO_OT_register_annotations(bpy.types.Operator):
    bl_idname = 'bvt_studio.register_annotations'
    bl_label = 'Style / Register Annotation Planes'
    bl_description = 'Style all plane_p_* objects and registered annotation objects'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objs = scene_annotations(context.scene)
        if not objs:
            self.report({'ERROR'}, 'No plane_p_* objects in current scene')
            return {'CANCELLED'}
        for idx, obj in enumerate(objs):
            configure_outline(obj, idx, bool(context.scene.get(PREVIEW_PROP, False)))
        from .scene_lock import apply_scene_locks
        apply_scene_locks(context.scene)
        self.report({'INFO'}, f'Configured {len(objs)} annotations')
        return {'FINISHED'}


class BVTSTUDIO_OT_renumber(bpy.types.Operator):
    bl_idname = 'bvt_studio.renumber'
    bl_label = 'Renumber 001...N'
    bl_description = 'Safely renumber annotation objects by numeric order'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = scene_annotations(context.scene)
        if not objects:
            self.report({'ERROR'}, 'No registered annotations')
            return {'CANCELLED'}
        try:
            count = renumber(context.scene, objects)
            for i, obj in enumerate(objects):
                configure_outline(obj, i, bool(context.scene.get(PREVIEW_PROP, False)))
            self.report({'INFO'}, f'Renumbered {count} annotations')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BVTSTUDIO_OT_toggle_preview(bpy.types.Operator):
    bl_idname = 'bvt_studio.toggle_preview'
    bl_label = 'Toggle Rendered Outlines'
    bl_description = 'Enable annotation outlines in F12 preview; dataset export is always clean'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        new_state = not bool(context.scene.get(PREVIEW_PROP, False))
        context.scene[PREVIEW_PROP] = new_state
        for obj in scene_annotations(context.scene):
            obj.hide_render = not new_state
        self.report({'INFO'}, 'Preview outlines ON' if new_state else 'Clean render ON')
        return {'FINISHED'}


class BVTSTUDIO_OT_validate(bpy.types.Operator):
    bl_idname = 'bvt_studio.validate'
    bl_label = 'Validate YOLO Boxes'
    bl_description = 'Check projected bboxes, classes and duplicates'

    def execute(self, context):
        boxes, errors, classes = collect_boxes(context.scene)
        for msg in errors:
            print('[BVT Studio] Annotation validation:', msg)
        if errors:
            self.report({'WARNING'}, f'{len(errors)} issue(s); {len(boxes)} boxes; see Blender console')
        else:
            self.report({'INFO'}, f'Valid: {len(boxes)} boxes, {len(classes)} classes')
        return {'FINISHED'}


class BVTSTUDIO_OT_export_yolo(bpy.types.Operator):
    bl_idname = 'bvt_studio.export_yolo'
    bl_label = 'Export Clean Image + YOLO'
    bl_description = 'Render an image without annotation overlays and export YOLO bbox labels'

    def execute(self, context):
        scene = context.scene
        boxes, errors, classes = collect_boxes(scene)
        if errors:
            for e in errors:
                print('[BVT Studio] Export blocked:', e)
            self.report({'ERROR'}, f'{len(errors)} validation issue(s); see Blender console')
            return {'CANCELLED'}
        if not bpy.data.filepath and scene.bvt_studio.export_dir.startswith('//'):
            self.report({'ERROR'}, 'Save your .blend first, or choose an absolute output folder')
            return {'CANCELLED'}
        try:
            root = Path(bpy.path.abspath(scene.bvt_studio.export_dir))
            train_images = root / 'images' / 'train'
            train_labels = root / 'labels' / 'train'
            val_images = root / 'images' / 'val'
            val_labels = root / 'labels' / 'val'
            for folder in (train_images, train_labels, val_images, val_labels):
                folder.mkdir(parents=True, exist_ok=True)
            index = 1
            while (train_images / f'sample_{index:06d}.png').exists() or (train_labels / f'sample_{index:06d}.txt').exists():
                index += 1
            stem = f'sample_{index:06d}'
            image_path = train_images / (stem + '.png')
            label_path = train_labels / (stem + '.txt')
            objs = scene_annotations(scene)
            old_hidden = {obj: obj.hide_render for obj in objs}
            old_path = scene.render.filepath
            old_format = scene.render.image_settings.file_format
            old_color = scene.render.image_settings.color_mode
            try:
                # Never bake annotation outlines into exported training images.
                for obj in objs:
                    obj.hide_render = True
                scene.render.filepath = str(image_path)
                scene.render.image_settings.file_format = 'PNG'
                scene.render.image_settings.color_mode = 'RGB'
                bpy.ops.render.render(write_still=True)
            finally:
                for obj, old in old_hidden.items():
                    obj.hide_render = old
                scene.render.filepath = old_path
                scene.render.image_settings.file_format = old_format
                scene.render.image_settings.color_mode = old_color
            if not image_path.exists():
                raise RuntimeError('Blender did not write the expected image file')
            lines = [
                f'{b["class_id"]} {b["x"]:.7f} {b["y"]:.7f} {b["w"]:.7f} {b["h"]:.7f}'
                for b in boxes
            ]
            label_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            # YAML maps numeric class IDs to names. Val dir is created empty by design.
            yaml_lines = [
                'path: ' + json.dumps(root.as_posix(), ensure_ascii=False),
                'train: images/train', 'val: images/val',
                f'nc: {len(classes)}', 'names:',
            ]
            for class_id in sorted(classes):
                yaml_lines.append(f'  {class_id}: {json.dumps(classes[class_id], ensure_ascii=False)}')
            (root / 'data.yaml').write_text('\n'.join(yaml_lines) + '\n', encoding='utf-8')
            source = get_source(scene)
            manifest = dict(
                schema='bvt_studio_2d_yolo_v0.1',
                scene=scene.name,
                image=f'images/train/{stem}.png',
                labels=f'labels/train/{stem}.txt',
                image_width=round(scene.render.resolution_x * scene.render.resolution_percentage / 100),
                image_height=round(scene.render.resolution_y * scene.render.resolution_percentage / 100),
                camera=scene.camera.name if scene.camera else None,
                camera_type=scene.camera.data.type if scene.camera else None,
                source_image=source.name if source else None,
                camera_profile=scene.bvt_studio.camera_profile,
                annotations=boxes,
                glass=[
                    dict(object=o.name, reflection=o.get('bvt_glass_reflection', 0),
                         tint=o.get('bvt_glass_tint', 0), haze=o.get('bvt_glass_haze', 0),
                         frost=o.get('bvt_glass_frost', 0))
                    for o in scene.objects if o.get('bvt_role') == 'glass_overlay'
                ],
                note='One scene photo, no automatic validation split; val is empty',
            )
            (root / (stem + '_manifest.json')).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            self.report({'INFO'}, f'YOLO exported: {len(boxes)} boxes -> {image_path}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Export failed: {exc}')
            print('[BVT Studio] Export error:', repr(exc))
            return {'CANCELLED'}


CLASSES = (
    BVTSTUDIO_OT_add_annotation, BVTSTUDIO_OT_register_annotations,
    BVTSTUDIO_OT_renumber, BVTSTUDIO_OT_toggle_preview,
    BVTSTUDIO_OT_validate, BVTSTUDIO_OT_export_yolo,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
