"""Dependency-free regression tests for per-glass aperture masks.

The shader is rendered by Blender; these tests make sure invalid apertures
are rejected and all hybrid effect branches are masked before Blender QA.
"""
import ast
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYBRID = ROOT / 'bvt_studio' / 'hybrid_condensation.py'
GLASS = ROOT / 'bvt_studio' / 'glass.py'
UI = ROOT / 'bvt_studio' / 'ui.py'
PRESETS = ROOT / 'bvt_studio' / 'artifact_presets.py'
GALLERY = ROOT / 'scripts' / 'blender_hybrid_condensation_gallery.py'


class GlassApertureMaskTests(unittest.TestCase):
    def test_aperture_bounds_validation(self):
        tree = ast.parse(HYBRID.read_text(encoding='utf-8'))
        func = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'validate_aperture_settings')
        scope = {'isfinite': math.isfinite}
        exec(compile(ast.Module(body=[func], type_ignores=[]), str(HYBRID), 'exec'), scope)
        validate = scope['validate_aperture_settings']
        validate(0.0, 1.0, 0.0, 1.0, 0.02)
        validate(0.1, 0.9, 0.15, 0.85, 0.015)
        for values in ((0.8, 0.3, 0, 1, 0.02),
                       (0, 1, 0.5, 0.5, 0.02),
                       (-0.1, 1, 0, 1, 0.02),
                       (0, 1, 0, 1.2, 0.02),
                       (0, 1, 0, 1, 0),
                       (0, 1, 0, 1, float('nan'))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate(*values)

    def test_per_glass_mask_pipeline_and_gallery_contract(self):
        hybrid = HYBRID.read_text(encoding='utf-8')
        glass = GLASS.read_text(encoding='utf-8')
        ui = UI.read_text(encoding='utf-8')
        presets = PRESETS.read_text(encoding='utf-8')
        gallery = GALLERY.read_text(encoding='utf-8')
        for source in (hybrid, glass, ui, presets, gallery):
            ast.parse(source)
        self.assertIn("glass_mask = _combined_glass_mask(obj, nodes, links, tex.outputs['UV'])", hybrid)
        for node in ('BVT_Hybrid_Droplet_Masked', 'BVT_Hybrid_Wet_Masked',
                     'BVT_Hybrid_Center_Masked', 'BVT_Hybrid_Aperture_Mask'):
            self.assertIn(node, hybrid)
        for key in ('aperture_left', 'aperture_right', 'aperture_bottom',
                    'aperture_top', 'aperture_feather'):
            self.assertIn('artifact_' + key, ui)
            self.assertIn('artifact_' + key, presets)
        self.assertIn('def fit_glass_to_source_uv_rect', glass)
        self.assertIn('image_uv_bounds(source)', glass)
        self.assertIn('source.matrix_world @ Matrix.Translation', glass)
        self.assertIn('section_rects = (', gallery)
        self.assertIn('for _ in range(4)', gallery)
        self.assertIn('05_aperture_debug.png', gallery)
        self.assertIn('source_image.size', gallery)


if __name__ == '__main__':
    unittest.main()
