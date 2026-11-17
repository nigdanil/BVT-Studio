"""Annotation Manager pure-function and structural regression tests, no bpy."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bvt_studio' / 'annotation_manager.py'


class FakeObject(dict):
    def __init__(self, name, class_id=0, class_name='ice_cream'):
        super().__init__(bvt_class_id=class_id, bvt_class_name=class_name)
        self.name = name

    def as_pointer(self):
        return id(self)


class FakeItem:
    def __init__(self):
        self.obj = None


class FakeItems(list):
    def add(self):
        obj = FakeItem()
        self.append(obj)
        return obj


class FakeSettings:
    def __init__(self):
        self.annotation_items = FakeItems()
        self.annotation_index = -1


class FakeScene:
    def __init__(self, objects):
        self.objects = objects
        self.bvt_studio = FakeSettings()


class TestAnnotationManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = SOURCE.read_text(encoding='utf-8')
        tree = ast.parse(text)
        needed = {'_object_key', 'class_name_conflicts',
                  '_annotation_targets', 'sync_annotation_list'}
        nodes = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in needed]
        env = {'SUSPEND_LIST_SELECTION': False,
               'scene_annotations': lambda scene: sorted(scene.objects, key=lambda o: o.name)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), env)
        cls.fn = env

    def test_batch_conflict_detects_preexisting_class_name(self):
        a, b = FakeObject('plane_p_001', 0, 'ice_cream'), FakeObject('plane_p_002', 0, 'ice_cream')
        issues = self.fn['class_name_conflicts']([a, b], [a], 0, 'sundae')
        self.assertEqual(len(issues), 1)
        self.assertIn('plane_p_002', issues[0])
        self.assertEqual(b['bvt_class_name'], 'ice_cream')

    def test_no_conflict_when_all_existing_class_owners_selected(self):
        a, b = FakeObject('plane_p_001'), FakeObject('plane_p_002')
        self.assertEqual(self.fn['class_name_conflicts']([a, b], [a, b], 0, 'sundae'), [])
        self.assertEqual(self.fn['class_name_conflicts']([a, b], [a], 1, 'sundae'), [])

    def test_scene_scoped_targets_ignore_unrelated_objects(self):
        a, b = FakeObject('plane_p_001'), FakeObject('plane_p_002')
        other = FakeObject('BVT_Freezer_Image_Plane')
        class Context: pass
        c = Context()
        c.scene = FakeScene([a, b])
        c.selected_objects = [a, other]
        self.assertEqual(self.fn['_annotation_targets'](c), [a])

    def test_refresh_preserves_selected_pointer_after_renaming(self):
        a, b = FakeObject('plane_p_002'), FakeObject('plane_p_001')
        scene = FakeScene([a, b])
        sync = self.fn['sync_annotation_list']
        self.assertEqual(sync(scene), 2)
        self.assertIs(scene.bvt_studio.annotation_items[0].obj, b)
        self.assertEqual(scene.bvt_studio.annotation_index, 0)
        sync(scene, preferred=a)
        self.assertEqual(scene.bvt_studio.annotation_index, 1)
        a.name, b.name = 'plane_p_001', 'plane_p_002'
        sync(scene)
        self.assertEqual(scene.bvt_studio.annotation_index, 0)
        self.assertIs(scene.bvt_studio.annotation_items[0].obj, a)

    def test_refresh_removes_deleted_and_no_duplicate_entries(self):
        objs = [FakeObject(f'plane_p_{i:03d}') for i in range(1, 101)]
        scene = FakeScene(objs)
        sync = self.fn['sync_annotation_list']
        self.assertEqual(sync(scene), 100)
        self.assertEqual(sync(scene), 100)
        self.assertEqual(len(scene.bvt_studio.annotation_items), 100)
        scene.objects.pop(23)
        self.assertEqual(sync(scene), 99)
        self.assertEqual(len(scene.bvt_studio.annotation_items), 99)

    def test_ui_operators_and_registration(self):
        ui = (ROOT / 'bvt_studio' / 'ui.py').read_text(encoding='utf-8')
        annotation = (ROOT / 'bvt_studio' / 'annotation.py').read_text(encoding='utf-8')
        settings = (ROOT / 'bvt_studio' / 'props.py').read_text(encoding='utf-8')
        init = (ROOT / 'bvt_studio' / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('annotation_manager, scene_lock', init)
        self.assertIn("manager.template_list('BVTSTUDIO_UL_annotations'", ui)
        for op in ('refresh_annotation_list', 'select_all_annotations',
                   'batch_annotation_class', 'batch_annotation_enabled'):
            self.assertIn('bvt_studio.' + op, ui)
            self.assertIn("bl_idname = 'bvt_studio." + op + "'", SOURCE.read_text())
        self.assertIn('CollectionProperty(type=BVTStudioAnnotationItem)', settings)
        self.assertIn('on_annotation_selection_change', settings)
        self.assertEqual(annotation.count('sync_annotation_list(context.scene'), 3)
        self.assertIn('BUILD_STAGE = "alpha.3"', init)


if __name__ == '__main__':
    unittest.main()
