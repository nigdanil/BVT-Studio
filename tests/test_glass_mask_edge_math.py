"""Regression guard for the combined edge and aperture hybrid glass masks."""
from pathlib import Path
import ast
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'bvt_studio' / 'hybrid_condensation.py')


class GlassMaskEdgeTests(unittest.TestCase):
    def test_combined_mask_contract_present(self):
        src = SOURCE.read_text(encoding='utf-8')
        ast.parse(src)
        for label in ('_glass_area_mask', '_glass_aperture_mask', '_combined_glass_mask',
                      'BVT_Hybrid_Glass_Mask', 'BVT_Hybrid_Aperture_Mask',
                      'validate_aperture_settings', "_combined_glass_mask(obj, nodes, links, tex.outputs['UV'])"):
            self.assertIn(label, src)


if __name__ == '__main__':
    unittest.main()
