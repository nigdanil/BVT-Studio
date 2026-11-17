"""Scene-lock tests that run on CPython without Blender installed.

We execute the real pure locking functions via AST; Blender-only operators are
covered by static registration checks and manual Blender acceptance tests.
"""
import ast
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'bvt_studio' / 'scene_lock.py'


class FakeObject(dict):
    def __init__(self, name, role=None, hidden=False):
        super().__init__()
        self.name = name
        self.type = 'MESH'
        self.library = None
        self.hide_select = hidden
        self.lock_location = (False, False, True)
        self.lock_rotation = (False, True, False)
        self.lock_scale = (False, False, False)
        self.lock_rotation_w = False
        self.lock_rotations_4d = False
        if role:
            self['bvt_role'] = role

    def as_pointer(self):
        return id(self)


class TestSceneLock(unittest.TestCase):
    def setUp(self):
        root = ast.parse(SOURCE.read_text(encoding='utf-8'))
        functions = [node for node in root.body if isinstance(node, ast.FunctionDef)
                     and node.name in {'_capture', '_restore', '_protect', '_is_local',
                                       'managed_groups', 'apply_scene_locks'}]
        env = {'json': json, 'LOCK_MARKER': '_bvt_studio_lock_snapshot_v1',
               'GROUP_FIELDS': (('photo', 'photo_edit_enable'),
                                ('camera', 'camera_edit_enable'),
                                ('light', 'light_edit_enable'),
                                ('glass', 'glass_edit_enable'),
                                ('annotations', 'annotations_edit_enable'))}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), env)
        self.ns = env

    def test_lock_restores_preexisting_user_restrictions(self):
        obj = FakeObject('Photo', hidden=True)
        orig = dict(hidden=obj.hide_select, loc=obj.lock_location,
                    rot=obj.lock_rotation, scale=obj.lock_scale)
        self.ns['_protect'](obj)
        self.assertEqual(obj.lock_location, (True, True, True))
        self.assertTrue(obj.hide_select)
        old_snapshot = obj[self.ns['LOCK_MARKER']]
        self.ns['_protect'](obj)
        self.assertEqual(obj[self.ns['LOCK_MARKER']], old_snapshot)
        self.assertTrue(self.ns['_restore'](obj))
        self.assertEqual(obj.hide_select, orig['hidden'])
        self.assertEqual(tuple(obj.lock_location), tuple(orig['loc']))
        self.assertEqual(tuple(obj.lock_rotation), tuple(orig['rot']))
        self.assertEqual(tuple(obj.lock_scale), tuple(orig['scale']))
        self.assertNotIn(self.ns['LOCK_MARKER'], obj)

    def test_group_editability_and_unrelated_objects(self):
        photo = FakeObject('BVT_Freezer_Image_Plane', role='planogram_image')
        camera = FakeObject('BVT_Studio_Camera')
        camera.type = 'CAMERA'
        glass = FakeObject('Glass_p_001', role='glass_overlay')
        annotation = FakeObject('plane_p_001', role='annotation')
        unrelated = FakeObject('UserCube')
        light = FakeObject('BVT_Softbox')
        light.type = 'LIGHT'
        items = [photo, camera, glass, annotation, unrelated, light]
        settings = SimpleNamespace(scene_locks_enabled=True,
                                   photo_edit_enable=False, camera_edit_enable=False,
                                   light_edit_enable=False, glass_edit_enable=False,
                                   annotations_edit_enable=True)
        scene = SimpleNamespace(objects=items, camera=camera, bvt_studio=settings)
        self.ns['get_source'] = lambda scene: photo
        self.ns['scene_glass'] = lambda scene: [glass]
        self.ns['scene_annotations'] = lambda scene: [annotation]
        self.ns['apply_scene_locks'](scene)
        for obj in (photo, camera, glass, light):
            self.assertTrue(obj.hide_select)
        self.assertFalse(annotation.hide_select)
        self.assertFalse(unrelated.hide_select)
        settings.glass_edit_enable = True
        self.ns['apply_scene_locks'](scene)
        self.assertFalse(glass.hide_select)
        self.assertTrue(photo.hide_select)
        settings.scene_locks_enabled = False
        self.ns['apply_scene_locks'](scene)
        for obj in items:
            self.assertFalse(obj.hide_select)
            self.assertNotIn(self.ns['LOCK_MARKER'], obj)

    def test_unregistered_object_cannot_remain_locked(self):
        old = FakeObject('Glass_p_001', role='glass_overlay')
        scene = SimpleNamespace(objects=[old], camera=None,
                                bvt_studio=SimpleNamespace(scene_locks_enabled=True,
                                    photo_edit_enable=False, camera_edit_enable=False,
                                    light_edit_enable=False, glass_edit_enable=False,
                                    annotations_edit_enable=True))
        self.ns['get_source'] = lambda scene: None
        self.ns['scene_glass'] = lambda scene: [old] if old.get('bvt_role') == 'glass_overlay' else []
        self.ns['scene_annotations'] = lambda scene: []
        self.ns['apply_scene_locks'](scene)
        self.assertTrue(old.hide_select)
        del old['bvt_role']
        self.ns['apply_scene_locks'](scene)
        self.assertFalse(old.hide_select)


if __name__ == '__main__':
    unittest.main()
