"""Blender 5.2+ end-to-end headless render + YOLO + portable SVG preview test.

Run from repository root:
    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
      --background --factory-startup --python scripts/blender_export_preview_smoke.py
"""
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import bvt_studio
from bvt_studio.scene_tools import configure_image_material

if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 128
scene.render.resolution_y = 128
scene.render.resolution_percentage = 100
scene.render.image_settings.color_depth = '8'
scene.render.film_transparent = False
scene.view_settings.view_transform = 'Standard'

image = bpy.data.images.new('BVT_Preview_Smoke', width=64, height=64)
image.pixels[:] = [0.3, 0.5, 0.7, 1.0] * (64 * 64)
image.update()
mesh = bpy.data.meshes.new('Smoke_Photo_Mesh')
mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)],
                 [], [(0, 1, 2, 3)])
mesh.update()
uv = mesh.uv_layers.new()
for face in mesh.polygons:
    for li in face.loop_indices:
        vi = mesh.loops[li].vertex_index
        uv.data[li].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[vi]
photo = bpy.data.objects.new('BVT_Smoke_Photo', mesh)
scene.collection.objects.link(photo)
photo.data.materials.append(configure_image_material(image))
photo['bvt_role'] = 'planogram_image'
scene.bvt_studio.source_object = photo

camera_data = bpy.data.cameras.new('BVT_Smoke_Camera_Data')
camera_data.type = 'ORTHO'
camera_data.ortho_scale = 2.0
camera = bpy.data.objects.new('BVT_Smoke_Camera', camera_data)
scene.collection.objects.link(camera)
camera.location.z = 4
scene.camera = camera

box_mesh = bpy.data.meshes.new('Box_Mesh')
box_mesh.from_pydata([(-.2, -.2, 0), (.2, -.2, 0),
                      (.2, .2, 0), (-.2, .2, 0)], [], [(0, 1, 2, 3)])
box_mesh.update()
obj = bpy.data.objects.new('plane_p_001', box_mesh)
scene.collection.objects.link(obj)
obj.location.z = 0.05
obj['bvt_role'] = 'annotation'
obj['bvt_enabled'] = True
obj['bvt_class_id'] = 0
obj['bvt_class_name'] = 'ice_cream'
obj.hide_render = False  # Test exporter hides it, then restores this state.
bpy.context.view_layer.update()

with tempfile.TemporaryDirectory(prefix='bvt_preview_smoke_') as td:
    scene.bvt_studio.export_dir = td
    result = bpy.ops.bvt_studio.export_yolo()
    assert result == {'FINISHED'}, result
    root = Path(td)
    png = root/'images/train/sample_000001.png'
    label = root/'labels/train/sample_000001.txt'
    preview = root/'previews/sample_000001.svg'
    assert png.is_file() and label.is_file() and preview.is_file()
    assert not png.stat().st_size == 0
    assert 'path:' not in (root/'data.yaml').read_text(encoding='utf-8')
    assert scene.bvt_studio.last_preview_svg == str(preview)
    assert obj.hide_render is False
    assert len(label.read_text(encoding='utf-8').splitlines()) == 1
    document = ET.parse(preview)
    ns = '{http://www.w3.org/2000/svg}'
    img = document.getroot().find(ns + 'image')
    assert img.attrib['href'] == '../images/train/sample_000001.png'
    assert len(document.getroot().findall(ns + 'rect')) == 1
print('BVT EXPORT PREVIEW SMOKE: OK — portable YAML, clean PNG, TXT, SVG, render state restored')
