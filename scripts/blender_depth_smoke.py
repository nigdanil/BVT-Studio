"""Manual headless Blender 5.2 smoke: photo-relative depth on a rotated plane.

Run from repository root:
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
      --background --factory-startup --python scripts/blender_depth_smoke.py

Requires Blender's bpy; NOT part of CPython CI tests.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from mathutils import Matrix, Vector
import bvt_studio
from bvt_studio import depth

if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

scene = bpy.context.scene
mesh = bpy.data.meshes.new('Smoke_Photo_Mesh')
mesh.from_pydata([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)], [], [(0,1,2,3)])
mesh.update()
photo = bpy.data.objects.new('BVT_Smoke_Photo', mesh)
scene.collection.objects.link(photo)
photo['bvt_role'] = 'planogram_image'
photo.rotation_euler = (math.radians(30), math.radians(20), 0.0)
photo.scale = (1.7, 0.9, 2.5)
scene.bvt_studio.source_object = photo

cam_data = bpy.data.cameras.new('Smoke_Camera_Data')
cam = bpy.data.objects.new('BVT_Studio_Camera', cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
bpy.context.view_layer.update()
normal, axis_scale = depth._photo_axis(photo)
cam.location = photo.location + normal * 4.0
bpy.context.view_layer.update()

layer_mesh = mesh.copy()
glass = bpy.data.objects.new('Glass_p_001', layer_mesh)
scene.collection.objects.link(glass)
glass['bvt_role'] = 'glass_overlay'
glass.matrix_world = photo.matrix_world @ Matrix.Translation(
    (0.25, -0.20, 0.012 / axis_scale))
annotation = bpy.data.objects.new('plane_p_001', mesh.copy())
scene.collection.objects.link(annotation)
annotation['bvt_role'] = 'annotation'
annotation.matrix_world = photo.matrix_world @ Matrix.Translation(
    (-0.30, 0.15, 0.030 / axis_scale))
bpy.context.view_layer.update()

depth.sync_depth_constraints(scene)
for obj, expected in ((glass, 0.012), (annotation, 0.030)):
    con = obj.constraints.get(depth.DEPTH_CONSTRAINT)
    assert con and con.owner_space == 'CUSTOM' and con.space_object == photo
    assert con.use_transform_limit and con.use_min_z and con.use_max_z
    depsgraph = bpy.context.evaluated_depsgraph_get()
    measured = (obj.evaluated_get(depsgraph).matrix_world.translation -
                photo.matrix_world.translation).dot(normal)
    assert abs(measured - expected) < 1e-4, (obj.name, measured, expected)

# Attempt to move through the photo plane; evaluated result must remain pinned.
glass.location += normal * 0.20
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
actual = (glass.evaluated_get(depsgraph).matrix_world.translation -
          photo.matrix_world.translation).dot(normal)
assert abs(actual - 0.012) < 1e-4, actual

# Move along a tangent. The annotation should remain in its original layer.
tangent = (photo.matrix_world.to_3x3() @ Vector((1, 0, 0))).normalized()
annotation.location += tangent * 0.15
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
actual = (annotation.evaluated_get(depsgraph).matrix_world.translation -
          photo.matrix_world.translation).dot(normal)
assert abs(actual - 0.030) < 1e-4, actual

# Per-Glass camera-facing distance is an explicit BVT operation.
scene.bvt_studio.depth_target_glass = glass
scene.bvt_studio.glass_depth_offset_m = 0.025
result = bpy.ops.bvt_studio.apply_glass_depth()
assert result == {'FINISHED'}, result
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
actual = (glass.evaluated_get(depsgraph).matrix_world.translation -
          photo.matrix_world.translation).dot(normal)
assert abs(actual - 0.025) < 1e-4, actual

print('BVT DEPTH SMOKE: OK — tilted photo, glass/annotation normal locks, offset')
