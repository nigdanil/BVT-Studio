"""Static and dependency-free geometry contracts; runtime shader tested in Blender."""
import ast
import math
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLASS = (ROOT / 'bvt_studio' / 'glass_realism.py').read_text(encoding='utf8')
UI = (ROOT / 'bvt_studio' / 'ui.py').read_text(encoding='utf8')
PRESETS = (ROOT / 'bvt_studio' / 'artifact_presets.py').read_text(encoding='utf8')


def mapping_func():
    tree = ast.parse(GLASS)
    f = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == 'image_uv_bounds')
    ns = {'isfinite': math.isfinite}
    exec(compile(ast.Module(body=[f], type_ignores=[]), '<uv>', 'exec'), ns)
    return ns['image_uv_bounds']


class Coord(tuple):
    x = property(lambda self: self[0])
    y = property(lambda self: self[1])
    z = property(lambda self: self[2])


def photo(uv_override=None, tilted_mesh=False):
    pts = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
    if tilted_mesh:
        pts[-1] = (0, 1, .3)
    uv = uv_override or [(0, 0), (1, 0), (1, 1), (0, 1)]
    mesh = types.SimpleNamespace(
        vertices=[types.SimpleNamespace(co=Coord(p)) for p in pts],
        uv_layers=types.SimpleNamespace(active=types.SimpleNamespace(
            data=[types.SimpleNamespace(uv=p) for p in uv])),
        polygons=[types.SimpleNamespace(loop_indices=range(4))],
        loops=[types.SimpleNamespace(vertex_index=i) for i in range(4)])
    return types.SimpleNamespace(type='MESH', data=mesh)


class TestGlassRealism(unittest.TestCase):
    def test_affine_photo_uv_bounds(self):
        self.assertEqual(mapping_func()(photo()), ((0, 0), (2, 1)))

    def test_refuse_nonlinear_uv(self):
        self.assertIsNone(mapping_func()(photo(uv_override=[(0, 0), (.4, 0),
                                                           (1, 1), (0, 1)])))

    def test_refuse_noncoplanar_geometry(self):
        self.assertIsNone(mapping_func()(photo(tilted_mesh=True)))

    def test_refraction_samples_source_in_photo_local_coordinates(self):
        for value in ('ShaderNodeTexCoord', "photo_coordinates.object = source",
                      'BVT_Photo_UV_Scale', 'BVT_Photo_UV_Offset',
                      'BVT_Refracted_Source_Photo', 'BVT_Refraction_Source_UV',
                      'BVT_Local_Photo_Refraction', "sample.extension = 'CLIP'"):
            self.assertIn(value, GLASS)
        self.assertIn('if source is not None:', GLASS)

    def test_relief_frost_and_moisture_are_on_output_path(self):
        for value in ('BVT_Rim_HighlightShadow', 'BVT_Droplet_Relief_Overlay',
                      'BVT_Frost_Branches', 'BVT_Crystalline_Overlay',
                      'BVT_Condensation_Overlay', 'BVT_Condensation_Wet_Patches',
                      "links.new(rim_overlay.outputs[0], output.inputs['Surface'])"):
            self.assertIn(value, GLASS)
        self.assertIn("v.feature = 'DISTANCE_TO_EDGE'", GLASS)

    def test_no_mesh_transform_changes(self):
        tree = ast.parse(GLASS)
        forbidden = ('location', 'rotation_euler', 'scale', 'matrix_world',
                     'vertices.new', 'mesh.from_pydata', 'bpy.ops.object')
        for val in forbidden:
            self.assertNotIn('obj.' + val + ' =', GLASS)
        self.assertNotIn('bpy.ops.', GLASS)

    def test_controls_preset_manifest_and_build_version(self):
        for field in ('artifact_refraction', 'artifact_relief'):
            self.assertIn(field, UI)
            self.assertIn(field, (ROOT / 'bvt_studio/props.py').read_text())
            self.assertIn(field, (ROOT / 'bvt_studio/annotation.py').read_text())
            self.assertIn(field, PRESETS)
        self.assertIn('v0.4.0-alpha.4-step4.zip', (ROOT / 'scripts/build_addon.py').read_text())
        self.assertIn('BUILD_STAGE = "alpha.4-step4"', (ROOT / 'bvt_studio/__init__.py').read_text())

    def test_visual_gallery_exports_real_pngs_without_zip(self):
        path = ROOT / 'scripts/blender_glass_visual_gallery.py'
        script = path.read_text(encoding='utf8')
        ast.parse(script)
        self.assertIn('bpy.ops.render.render(write_still=True)', script)
        self.assertIn('--output', script)
        self.assertIn('07_heavy_seed_73.png', script)
        self.assertIn('VISUAL_QA_DIR=', script)
        self.assertNotIn('ZipFile', script)


if __name__ == '__main__':
    unittest.main()
