"""Exercise Blender-independent glass discovery and renumber logic with fakes."""
import ast
import re
import uuid
import unittest
from pathlib import Path
from types import SimpleNamespace

GLASS_PATH = Path(__file__).resolve().parents[1] / 'bvt_studio' / 'glass.py'


class FakeObject(dict):
    def __init__(self, name, role=None):
        super().__init__()
        self.name = name
        self.type = 'MESH'
        self.data = SimpleNamespace(polygons=[object()])
        self.library = None
        self.active_material = None
        self.matrix_world = 'unchanged-world-matrix-' + name
        if role:
            self['bvt_role'] = role

    def as_pointer(self):
        return id(self)


class FakeRegistry:
    def __init__(self, objects):
        self.objects = objects

    def get(self, name):
        return next((o for o in self.objects if o.name == name), None)


def load_pure_renumber_functions(objects):
    tree = ast.parse(GLASS_PATH.read_text(encoding='utf-8'))
    required = {'_is_glass_candidate', '_glass_sort_key', 'scene_glass',
                'renumber_glass'}
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in required]
    assert len(functions) == len(required)
    mod = ast.Module(body=functions, type_ignores=[])
    namespace = {'re': re, 'uuid': uuid,
                 'bpy': SimpleNamespace(data=SimpleNamespace(objects=FakeRegistry(objects))),
                 '_GLASS_NUMBER_RX': re.compile(r'^Glass_p_(\d+)(?:\.(\d+))?$', re.I),
                 '_LEGACY_GLASS_RX': re.compile(r'^(?:Glas|Glass)(?:[_ ]?(\d+))?(?:\.(\d+))?$', re.I),
                 'GLASS_PREFIX': 'Glass_p_'}
    exec(compile(mod, str(GLASS_PATH), 'exec'), namespace)
    return namespace


class TestGlassRenaming(unittest.TestCase):
    def test_legacy_names_and_stable_numbering(self):
        objs = [FakeObject('Glas_02'), FakeObject('Glass.001'),
                FakeObject('Glass_p_010'), FakeObject('Plane.001', 'glass_overlay'),
                FakeObject('plane_p_001', 'annotation')]
        ns = load_pure_renumber_functions(objs)
        scene = SimpleNamespace(objects=objs)
        selected = ns['scene_glass'](scene)
        self.assertEqual(len(selected), 4)
        matrices = {id(o): o.matrix_world for o in selected}
        self.assertEqual(ns['renumber_glass'](scene, selected), 4)
        self.assertEqual({o.name for o in selected},
                         {'Glass_p_001', 'Glass_p_002', 'Glass_p_003', 'Glass_p_004'})
        self.assertEqual([(o['bvt_glass_index'], bool(o.get('bvt_glass_uid')))
                          for o in selected], [(i, True) for i in range(1, 5)])
        self.assertEqual(matrices, {id(o): o.matrix_world for o in selected})
        # Rerunning doesn't add .001 suffixes or alter UIDs.
        uids = [o['bvt_glass_uid'] for o in selected]
        reselected = ns['scene_glass'](scene)
        ns['renumber_glass'](scene, reselected)
        self.assertEqual([o['bvt_glass_uid'] for o in reselected], uids)

    def test_name_conflict_preflight_makes_no_changes(self):
        source = FakeObject('Glas_001')
        unrelated = FakeObject('Glass_p_001', 'annotation')
        objs = [source, unrelated]
        ns = load_pure_renumber_functions(objs)
        scene = SimpleNamespace(objects=objs)
        with self.assertRaisesRegex(ValueError, 'unrelated object'):
            ns['renumber_glass'](scene, [source])
        self.assertEqual(source.name, 'Glas_001')


if __name__ == '__main__':
    unittest.main()
