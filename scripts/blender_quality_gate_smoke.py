"""Blender 5.2+ headless quality-gate smoke test; does not render or write files.

From Git Bash at repository root:
    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
      --background --factory-startup --python scripts/blender_quality_gate_smoke.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import bvt_studio

if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

scene = bpy.context.scene
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
cam_data = bpy.data.cameras.new('QA_Camera_Data')
cam = bpy.data.objects.new('QA_Camera', cam_data)
scene.collection.objects.link(cam)
cam.location = (0, 0, 5)
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 2.0
scene.camera = cam


def make_box(name, center_x, w=.3, h=.3):
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata([(-w/2, -h/2, 0), (w/2, -h/2, 0),
                      (w/2, h/2, 0), (-w/2, h/2, 0)], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.location = (center_x, 0, 0.1)
    obj['bvt_role'] = 'annotation'
    obj['bvt_class_id'] = 0
    obj['bvt_class_name'] = 'ice_cream'
    obj['bvt_enabled'] = True
    return obj


first = make_box('plane_p_001', -.3)
second = make_box('plane_p_002', .3)
bpy.context.view_layer.update()
assert bpy.ops.bvt_studio.validate() == {'FINISHED'}
settings = scene.bvt_studio
assert settings.quality_checked
assert (settings.quality_box_count, settings.quality_error_count,
        settings.quality_warning_count) == (2, 0, 0)

# Same-class duplicate must block export and have a selectable target.
second.location.x = first.location.x
bpy.context.view_layer.update()
assert bpy.ops.bvt_studio.validate() == {'FINISHED'}
assert settings.quality_error_count >= 1, [(it.code, it.message) for it in settings.quality_items]
idx = next(i for i, issue in enumerate(settings.quality_items)
           if issue.code == 'DUPLICATE_BOX')
settings.quality_index = idx
assert settings.quality_items[idx].obj == first
assert bpy.ops.bvt_studio.focus_quality_issue() == {'FINISHED'}
assert bpy.context.view_layer.objects.active == first

# Overlap 71%-ish is a warning, not an error.  We can still use class 0.
second.location.x = first.location.x + .04
bpy.context.view_layer.update()
assert bpy.ops.bvt_studio.validate() == {'FINISHED'}
assert settings.quality_error_count == 0
assert any(issue.code == 'HIGH_OVERLAP' for issue in settings.quality_items)

# Tiny projected size warns without making it a hard export error.
second.location.x = .5
second.data.vertices[0].co = (-.003, -.003, 0)
second.data.vertices[1].co = (.003, -.003, 0)
second.data.vertices[2].co = (.003, .003, 0)
second.data.vertices[3].co = (-.003, .003, 0)
second.data.update()
bpy.context.view_layer.update()
assert bpy.ops.bvt_studio.validate() == {'FINISHED'}
assert settings.quality_error_count == 0
assert any(issue.code == 'TINY_OBJECT' for issue in settings.quality_items)

print('BVT QUALITY GATE SMOKE: OK — errors, warnings, focus, no geometry mutation')
