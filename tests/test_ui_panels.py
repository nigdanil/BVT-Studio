"""Dependency-free contracts for Blender's native collapsible BVT sidebar."""
import ast
from collections import Counter
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bvt_studio' / 'ui.py'

EXPECTED = {
    'BVTSTUDIO_PT_scene_locks': ('annotation_lock_mode', 'unlock_scene'),
    'BVTSTUDIO_PT_layer_depth': ('apply_glass_depth', 'reset_layer_depth'),
    'BVTSTUDIO_PT_photo_scene': ('load_photo', 'use_source', 'fit_camera'),
    'BVTSTUDIO_PT_glass_surfaces': (
        'add_glass', 'setup_glass', 'setup_selected_glass_batch',
        'organize_glass', 'renumber_glass',
    ),
    'BVTSTUDIO_PT_glass_artifacts': ('apply_glass_preset', 'refresh_glass_pattern',
                                      'assign_precision_mask', 'toggle_precision_mask',
                                      'assign_droplet_maps', 'use_droplet_photos',
                                      'use_droplet_procedural', 'generate_realistic_atlas',
                                      'use_realistic_atlas', 'apply_optical_water',
                                      'disable_optical_water', 'read_visual_quality_report'),
    'BVTSTUDIO_PT_annotations': (
        'add_annotation', 'register_annotations', 'renumber', 'toggle_preview',
        'refresh_annotation_list', 'select_all_annotations',
        'batch_annotation_class', 'batch_annotation_enabled',
    ),
    'BVTSTUDIO_PT_quality_gate': ('validate', 'focus_quality_issue'),
    'BVTSTUDIO_PT_yolo_export': ('export_yolo', 'open_yolo_preview'),
}


def parse_ui():
    return ast.parse(SOURCE.read_text('utf-8'))


def assignments(klass):
    return {
        target.id: stmt.value
        for stmt in klass.body if isinstance(stmt, ast.Assign)
        for target in stmt.targets if isinstance(target, ast.Name)
    }


def operator_ids(klass):
    ids = []
    for node in ast.walk(klass):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'operator' and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            ids.append(node.args[0].value)
    return ids


class TestCollapsibleSidebar(unittest.TestCase):
    def test_native_parent_and_eight_children(self):
        classes = {node.name: node for node in parse_ui().body
                   if isinstance(node, ast.ClassDef)}
        self.assertIn('BVTSTUDIO_PT_main', classes)
        self.assertIn('_StudioChild', classes)
        self.assertEqual(len(EXPECTED), 8)
        self.assertEqual(set(EXPECTED), set(classes) - {
            'BVTSTUDIO_PT_main', '_StudioChild', '_StudioSidebar'})
        self.assertEqual(ast.literal_eval(assignments(classes['_StudioChild'])['bl_parent_id']),
                         'BVTSTUDIO_PT_main')
        self.assertEqual(ast.literal_eval(assignments(classes['_StudioChild'])['bl_options']),
                         {'DEFAULT_CLOSED'})
        self.assertEqual(ast.literal_eval(assignments(classes['_StudioSidebar'])['bl_space_type']),
                         'VIEW_3D')
        self.assertEqual(ast.literal_eval(assignments(classes['_StudioSidebar'])['bl_region_type']),
                         'UI')
        for name in EXPECTED:
            with self.subTest(name=name):
                self.assertEqual(ast.literal_eval(assignments(classes[name])['bl_idname']), name)
                self.assertTrue(any(isinstance(base, ast.Name) and base.id == '_StudioChild'
                                    for base in classes[name].bases))
        self.assertEqual(ast.literal_eval(assignments(classes['BVTSTUDIO_PT_glass_artifacts'])['bl_options']), set())

    def test_panel_order_and_registration_reverse(self):
        tree = parse_ui()
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        orders = [ast.literal_eval(assignments(classes[k])['bl_order']) for k in EXPECTED]
        self.assertEqual(orders, list(range(0, 80, 10)))
        block = next(node for node in tree.body
                     if isinstance(node, ast.Assign) and any(
                         isinstance(t, ast.Name) and t.id == 'CLASSES' for t in node.targets))
        self.assertEqual([elt.id for elt in block.value.elts],
                         ['BVTSTUDIO_PT_main', *EXPECTED])
        source = SOURCE.read_text('utf-8')
        self.assertIn('bpy.utils.register_class(cls)', source)
        self.assertIn('for cls in reversed(CLASSES)', source)
        self.assertIn('bpy.utils.unregister_class(cls)', source)

    def test_every_existing_operator_retained_once_in_correct_panel(self):
        classes = {node.name: node for node in parse_ui().body
                   if isinstance(node, ast.ClassDef)}
        all_ids = []
        for name, expected in EXPECTED.items():
            found = operator_ids(classes[name])
            with self.subTest(panel=name):
                self.assertCountEqual(found, ['bvt_studio.' + name for name in expected])
            all_ids.extend(found)
        self.assertEqual(len(all_ids), len(set(all_ids)), Counter(all_ids))
        self.assertEqual(len(all_ids), 36)
        self.assertEqual(operator_ids(classes['BVTSTUDIO_PT_main']), [])

    def test_existing_properties_and_lists_still_available(self):
        source = SOURCE.read_text('utf-8')
        for property_name in (
            'photo_edit_enable', 'camera_edit_enable', 'light_edit_enable',
            'glass_edit_enable', 'annotations_edit_enable',
            'photo_depth_lock', 'glass_depth_lock', 'annotations_depth_lock',
            'depth_target_glass', 'glass_depth_offset_m',
            'source_object', 'camera_profile', 'artifact_target_glass',
            'artifact_preset', 'artifact_intensity', 'artifact_coverage',
            'artifact_seed', 'artifact_droplet_scale', 'artifact_frost_edge',
            'annotation_items', 'annotation_index', 'batch_class_id',
            'batch_class_name', 'batch_enabled', 'quality_items', 'quality_index',
            'export_dir', 'bvt_artifact_seed', 'bvt_artifact_droplet_scale',
            'bvt_artifact_frost_edge',
        ):
            with self.subTest(property=property_name):
                self.assertIn(property_name, source)
        self.assertIn('BVTSTUDIO_UL_annotations', source)
        self.assertIn('BVTSTUDIO_UL_quality_issues', source)
        self.assertIn("bl_info['version']", source)
        self.assertIn('scene_annotations(', source)
        self.assertIn('scene_glass(', source)

    def test_smoke_is_syntax_valid_and_does_not_build_zip(self):
        script = (ROOT / 'scripts' / 'blender_ui_panels_smoke.py').read_text('utf-8')
        ast.parse(script)
        self.assertIn('BVT UI PANELS SMOKE: OK', script)
        self.assertNotIn('build_addon(', script)


if __name__ == '__main__':
    unittest.main()
