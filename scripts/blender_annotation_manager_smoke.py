"""Run in Blender 5.2.3 background with --factory-startup.

From repository root (Git Bash):
    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
      --background --factory-startup --python scripts/blender_annotation_manager_smoke.py

Tests real RNA registration, list synchronisation, selection, batch class and enabled.
No render, dataset file, ZIP or .blend changes are created.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
import bvt_studio
from bvt_studio import annotation_manager

if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

scene = bpy.context.scene
mesh = bpy.data.meshes.new('BVT_Annotation_Manager_Smoke_PhotoMesh')
mesh.from_pydata([(-1, -1, 0), (1, -1, 0),
                  (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
mesh.update()
photo = bpy.data.objects.new('BVT_Freezer_Image_Plane', mesh)
scene.collection.objects.link(photo)
photo['bvt_role'] = 'planogram_image'
scene.bvt_studio.source_object = photo

for _ in range(3):
    assert bpy.ops.bvt_studio.add_annotation() == {'FINISHED'}
assert len(scene.bvt_studio.annotation_items) == 3
assert len({item.obj.name for item in scene.bvt_studio.annotation_items}) == 3

# Click a list row: only that annotation becomes active in Blender.
scene.bvt_studio.annotation_index = 0
first = scene.bvt_studio.annotation_items[0].obj
assert bpy.context.view_layer.objects.active == first
assert first.select_get()

# Batch class change must refuse to introduce a class-ID/name conflict.
scene.bvt_studio.batch_class_id = 0
scene.bvt_studio.batch_class_name = 'sundae'
original_classes = [
    (item.obj['bvt_class_id'], item.obj['bvt_class_name'])
    for item in scene.bvt_studio.annotation_items
]
try:
    result = bpy.ops.bvt_studio.batch_annotation_class()
except RuntimeError as exc:
    # bpy.ops raises for an operator that reports ERROR, even when it
    # intentionally returns CANCELLED. This is an expected validation error.
    assert 'class 0' in str(exc) and 'ice_cream' in str(exc), str(exc)
else:
    assert result == {'CANCELLED'}, result
assert [
    (item.obj['bvt_class_id'], item.obj['bvt_class_name'])
    for item in scene.bvt_studio.annotation_items
] == original_classes, 'Rejected batch operation mutated annotation classes'

# Select all annotations, then edit them as one batch.
assert bpy.ops.bvt_studio.select_all_annotations() == {'FINISHED'}
scene.bvt_studio.batch_class_id = 1
scene.bvt_studio.batch_class_name = 'popsicle'
assert bpy.ops.bvt_studio.batch_annotation_class() == {'FINISHED'}
assert all(item.obj['bvt_class_id'] == 1 for item in scene.bvt_studio.annotation_items)
assert all(item.obj['bvt_class_name'] == 'popsicle' for item in scene.bvt_studio.annotation_items)
scene.bvt_studio.batch_enabled = False
assert bpy.ops.bvt_studio.batch_annotation_enabled() == {'FINISHED'}
assert all(not item.obj['bvt_enabled'] for item in scene.bvt_studio.annotation_items)

# External deletion must be repairable by Refresh.
bpy.data.objects.remove(scene.bvt_studio.annotation_items[1].obj, do_unlink=True)
assert bpy.ops.bvt_studio.refresh_annotation_list() == {'FINISHED'}
assert len(scene.bvt_studio.annotation_items) == 2
assert all(item.obj is not None for item in scene.bvt_studio.annotation_items)

print('BVT ANNOTATION MANAGER SMOKE: OK — list/select/batch class/enabled/refresh')
