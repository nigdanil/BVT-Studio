"""Regression tests for object-linked and mesh-linked material ownership."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'bvt_studio/glass_material_blender.py'


class ID:
    def __init__(self, name, data=None, library=None, users=1):
        self.name, self.data, self.library, self.users = name, data, library, users


def require(ok, message):
    if not ok:
        raise ValueError(message)


class MaterialOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.mesh = ID('mesh')
        self.obj = ID('glass', self.mesh)
        self.mat = ID('material', users=2)
        self.owners = {self.obj, self.mesh}
        self.objects = [self.obj]
        def user_map(*, subset):
            self.assertEqual(list(subset), [self.mat])
            return {self.mat: self.owners}
        data = SimpleNamespace(user_map=user_map, objects=self.objects)
        tree = ast.parse(SOURCE.read_text('utf8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_require_private_material')
        env = {'bpy': SimpleNamespace(data=data), 'require': require}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), env)
        self.check = lambda: env['_require_private_material'](self.obj, self.mat)

    def test_object_and_mesh_same_material(self):
        self.check()

    def test_mesh_only_and_object_only(self):
        for owner in (self.mesh, self.obj):
            self.owners = {owner}
            self.check()

    def test_other_owner_rejected(self):
        for other in (ID('another glass'), ID('another mesh'), ID('another ID')):
            self.owners = {self.obj, self.mesh, other}
            with self.assertRaisesRegex(ValueError, 'shared material'):
                self.check()

    def test_shared_mesh_rejected_even_if_other_object_not_in_scene(self):
        self.objects.append(ID('outside scene', self.mesh))
        with self.assertRaisesRegex(ValueError, 'shared mesh'):
            self.check()

    def test_empty_owners_and_linked_material_rejected(self):
        self.owners = set()
        with self.assertRaises(ValueError): self.check()
        self.owners = {self.obj, self.mesh}
        self.mat.library = object()
        with self.assertRaises(ValueError): self.check()

    def test_both_preflight_sites_use_owner_guard(self):
        source = SOURCE.read_text('utf8')
        self.assertIn('_require_private_material(source, mat)', source)
        self.assertIn('_require_private_material(o, gm)', source)
        self.assertNotIn('gm.users==1', source)
        self.assertNotIn('mat.users==1', source)


if __name__ == '__main__': unittest.main()
