"""Image-plane creation, source registration and calibrated flat-photo framing."""
import bpy
from bpy.props import StringProperty
from mathutils import Matrix, Vector
from .common import ensure_collection, image_from_mesh, get_source, source_centroid, world_size_xy

PROFILES = {
    'PHONE_4_3': (1600, 1200),
    'PHONE_3_4': (1200, 1600),
    'PHONE_16_9': (1920, 1080),
    'TABLET_4_3': (2048, 1536),
}


def configure_image_material(image):
    mat = bpy.data.materials.new('BVT_Studio_Photo_Unlit')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage')
    tex.name = 'BVT_Source_Image'
    tex.image = image
    tex.extension = 'CLIP'
    tex.location = (-500, 100)
    emission = nodes.new('ShaderNodeEmission')
    emission.location = (-220, 160)
    emission.inputs['Strength'].default_value = 1.0
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    transparent.location = (-230, -80)
    mix = nodes.new('ShaderNodeMixShader')
    mix.location = (50, 100)
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (290, 100)
    links.new(tex.outputs['Color'], emission.inputs['Color'])
    links.new(tex.outputs['Alpha'], mix.inputs[0])
    links.new(transparent.outputs['BSDF'], mix.inputs[1])
    links.new(emission.outputs['Emission'], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs['Surface'])
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'DITHERED'
    return mat


def create_photo_scene(context, image):
    iw, ih = tuple(image.size[:])
    if iw <= 0 or ih <= 0:
        raise RuntimeError('Image dimensions are missing')
    scene = bpy.data.scenes.new('BVT_Studio_2D')
    scene['bvt_studio_scene'] = True
    col = ensure_collection(scene, 'BVT_Studio_Photo')
    ensure_collection(scene, 'BVT_Glass')
    ensure_collection(scene, 'BVT_Annotations')
    width = context.scene.bvt_studio.plane_width
    height = width * (ih / iw)
    mesh = bpy.data.meshes.new('BVT_Photo_Mesh')
    mesh.from_pydata([
        (-width/2, -height/2, 0), (width/2, -height/2, 0),
        (width/2, height/2, 0), (-width/2, height/2, 0)
    ], [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name='BVT_Photo_UV')
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            uv.data[loop_index].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[vertex_index]
    plane = bpy.data.objects.new('BVT_Freezer_Image_Plane', mesh)
    col.objects.link(plane)
    plane.data.materials.append(configure_image_material(image))
    plane['bvt_role'] = 'planogram_image'

    cam_data = bpy.data.cameras.new('BVT_Studio_Camera_Data')
    cam = bpy.data.objects.new('BVT_Studio_Camera', cam_data)
    col.objects.link(cam)
    scene.camera = cam
    cam['bvt_role'] = 'studio_camera'
    scene.bvt_studio.source_object = plane
    scene.bvt_studio.camera_profile = 'ORIGINAL'
    scene.bvt_studio.plane_width = width
    # Framing is applied after window activates this scene.
    scene.render.engine = 'BLENDER_EEVEE'
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    from .scene_lock import activate_default_scene_locks
    activate_default_scene_locks(scene)
    return scene


def fit_camera_to_source(scene):
    source = get_source(scene)
    if source is None:
        raise RuntimeError('Select an Image Plane in the BVT Studio panel')
    source_image = image_from_mesh(source)
    if source_image is None:
        raise RuntimeError('Image Plane has no Image Texture node')
    iw, ih = tuple(source_image.size[:])
    if not (iw > 0 and ih > 0):
        raise RuntimeError('Image has no dimensions')
    profile = scene.bvt_studio.camera_profile
    res_x, res_y = (iw, ih) if profile == 'ORIGINAL' else PROFILES[profile]
    scene.render.resolution_x, scene.render.resolution_y = res_x, res_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'

    camera = scene.camera
    if camera is None or camera.type != 'CAMERA':
        camera_data = bpy.data.cameras.new('BVT_Studio_Camera_Data')
        camera = bpy.data.objects.new('BVT_Studio_Camera', camera_data)
        ensure_collection(scene, 'BVT_Studio_Photo').objects.link(camera)
        scene.camera = camera
        camera['bvt_role'] = 'studio_camera'
    cam_normal = (source.matrix_world.to_quaternion() @ Vector((0, 0, 1))).normalized()
    camera.location = source_centroid(source) + cam_normal * 4.0
    camera.rotation_euler = source.matrix_world.to_euler()
    camera.data.type = 'ORTHO'
    camera.data.clip_start = 0.01
    camera.data.clip_end = 100.0
    width, height = world_size_xy(source)
    ratio = res_x / res_y
    if width <= 0 or height <= 0:
        raise RuntimeError('Photo Plane has zero width/height')
    # Fill: intentional crop if camera aspect differs from source aspect.
    frame_width = min(width, height * ratio) * 0.998
    camera.data.ortho_scale = frame_width if ratio >= 1.0 else frame_width / ratio
    return (res_x, res_y)


class BVTSTUDIO_OT_load_photo(bpy.types.Operator):
    bl_idname = 'bvt_studio.load_photo'
    bl_label = 'New Scene from Photo'
    bl_description = 'Load a photo and create a separate, non-destructive 2D scene'
    bl_options = {'REGISTER', 'UNDO'}
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default='*.png;*.jpg;*.jpeg;*.webp;*.tif;*.tiff', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            image = bpy.data.images.load(self.filepath, check_existing=True)
            scene = create_photo_scene(context, image)
            context.window.scene = scene
            fit_camera_to_source(scene)
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.region_3d.view_perspective = 'CAMERA'
            self.report({'INFO'}, f'BVT Studio: imported {image.name}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def choose_source_image_plane(scene, active_object):
    """Choose a textured photo plane, never mistake a glass/annotation Plane for it.

    An already configured source remains usable when the user happens to have
    another Plane selected. Return (source_object, used_existing_source).
    """
    if (active_object is not None and active_object.type == 'MESH'
            and scene.objects.get(active_object.name) is active_object
            and image_from_mesh(active_object) is not None
            and active_object.get('bvt_role') not in {'annotation', 'glass_overlay'}):
        return active_object, False
    current = get_source(scene)
    if (current is not None and image_from_mesh(current) is not None
            and current.get('bvt_role') not in {'annotation', 'glass_overlay'}):
        return current, True
    raise ValueError(
        'Select a mesh with an Image Texture material, or import a photo first')


class BVTSTUDIO_OT_use_source(bpy.types.Operator):
    bl_idname = 'bvt_studio.use_source'
    bl_label = 'Use Selected as Photo'
    bl_description = 'Mark an existing textured mesh plane as the source photo'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            obj, used_existing = choose_source_image_plane(
                context.scene, context.active_object)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        context.scene.bvt_studio.source_object = obj
        obj['bvt_role'] = 'planogram_image'
        if used_existing:
            self.report({'INFO'}, f'Keeping existing photo source: {obj.name}')
        else:
            self.report({'INFO'}, f'BVT Studio source: {obj.name}')
        return {'FINISHED'}


class BVTSTUDIO_OT_fit_camera(bpy.types.Operator):
    bl_idname = 'bvt_studio.fit_camera'
    bl_label = 'Frame Camera to Photo'
    bl_description = 'Align orthographic camera to photo; preserve scene objects'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            dims = fit_camera_to_source(context.scene)
            self.report({'INFO'}, f'BVT Studio camera: {dims[0]}x{dims[1]}')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (BVTSTUDIO_OT_load_photo, BVTSTUDIO_OT_use_source, BVTSTUDIO_OT_fit_camera)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
