"""Pure Python export preview and portable YOLO metadata tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'bvt_export_preview', ROOT/'bvt_studio'/'export_preview.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ExportPreviewTests(unittest.TestCase):
    def test_yaml_is_portable_without_absolute_path(self):
        out = helper.portable_data_yaml({0: 'ice_cream', 1: 'popsicle'})
        self.assertNotIn('path:', out)
        self.assertIn('train: images/train', out)
        self.assertIn('val: images/val', out)
        self.assertIn('  1: "popsicle"', out)
        self.assertNotIn('C:', out)

    def test_reject_gapped_classes(self):
        with self.assertRaises(ValueError):
            helper.portable_data_yaml({0: 'ice_cream', 2: 'popsicle'})

    def test_svg_from_exported_txt_exact_normalized_box(self):
        boxes = [dict(class_id=0, x=.5, y=.5, w=.25, h=.2)]
        txt = helper.label_text(boxes)
        svg = helper.svg_from_labels(txt, {0: 'ice_cream'},
                                     1200, 1000, 'sample_000001.png')
        ns = '{http://www.w3.org/2000/svg}'
        document = ET.fromstring(svg)
        rect = document.find(ns + 'rect')
        self.assertAlmostEqual(float(rect.attrib['x']), 450)
        self.assertAlmostEqual(float(rect.attrib['y']), 400)
        self.assertAlmostEqual(float(rect.attrib['width']), 300)
        self.assertAlmostEqual(float(rect.attrib['height']), 200)
        image = document.find(ns + 'image')
        self.assertEqual(image.attrib['href'], '../images/train/sample_000001.png')

    def test_escaping_of_user_class_labels(self):
        svg = helper.svg_from_labels('0 0.5 0.5 0.1 0.1\n',
                                     {0: 'SKU & <test> "glass"'},
                                     300, 200, 'test.png')
        ET.fromstring(svg)
        self.assertIn('SKU &amp; &lt;test&gt;', svg)

    def test_no_unsafe_filename_in_svg(self):
        with self.assertRaises(ValueError):
            helper.svg_from_labels('0 0.5 0.5 0.1 0.1\n',
                                   {0: 'ice_cream'}, 300, 200, '../wrong.png')

    def test_no_geometry_mutation_by_serialization(self):
        boxes = [dict(class_id=0, x=.500000019, y=.45, w=.2, h=.3)]
        before = [b.copy() for b in boxes]
        text = helper.label_text(boxes)
        helper.svg_from_labels(text, {0: 'ice_cream'}, 800, 600, 'test.png')
        self.assertEqual(before, boxes)

    def test_filename_spaces_are_uri_escaped(self):
        svg = helper.svg_from_labels('0 0.5 0.5 0.1 0.1\n',
                                     {0: 'ice_cream'}, 200, 100, 'sample test.png')
        self.assertIn('sample%20test.png', svg)

    def test_addon_registers_preview_operator_and_button(self):
        annotation = (ROOT/'bvt_studio'/'annotation.py').read_text(encoding='utf-8')
        ui = (ROOT/'bvt_studio'/'ui.py').read_text(encoding='utf-8')
        self.assertIn("bl_idname = 'bvt_studio.open_yolo_preview'", annotation)
        self.assertIn("bvt_studio.open_yolo_preview", ui)
        self.assertIn('portable_data_yaml(classes)', annotation)
        self.assertIn('svg_from_labels(', annotation)


if __name__ == '__main__':
    unittest.main()
