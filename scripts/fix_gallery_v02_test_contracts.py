#!/usr/bin/env python3
"""Repair outdated source-contract tests after Glass Gallery v0.2 registration.

Updates only three existing test files and adds one test helper. Never touches
production code, the current git branch, source images, or Blender scenes.
"""
import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'

HELPER = '''"""AST-based addon registration assertions: insensitive to import ordering."""
import ast


def assert_registered_modules(testcase, source, *expected):
    """Require each module to be both imported and present in MODULES."""
    tree = ast.parse(source)
    imports = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            imports.update(alias.name for alias in node.names)
    definitions = [node.value for node in tree.body
                   if isinstance(node, ast.Assign) and
                   any(isinstance(target, ast.Name) and target.id == 'MODULES'
                       for target in node.targets)]
    testcase.assertEqual(len(definitions), 1, 'Expected exactly one MODULES binding')
    modules = definitions[0]
    testcase.assertIsInstance(modules, (ast.Tuple, ast.List),
                              'MODULES must remain a static tuple/list')
    registry = {node.id for node in modules.elts if isinstance(node, ast.Name)}
    for module in expected:
        testcase.assertIn(module, imports, f'{module} not imported by addon')
        testcase.assertIn(module, registry, f'{module} not registered by addon')
'''

REPLACEMENTS = {
    'test_droplet_maps.py': [
        ("        self.assertIn('droplet_maps, realistic_atlas, optical_water, visual_quality_ui)', init)",
         "        assert_registered_modules(self, init, 'droplet_maps', 'realistic_atlas',\n"
         "                                  'optical_water', 'visual_quality_ui', 'glass_v02_ui')"),
    ],
    'test_optical_water.py': [
        ("        self.assertIn('optical_water, visual_quality_ui)',addon)",
         "        assert_registered_modules(self, addon, 'optical_water',\n"
         "                                  'visual_quality_ui', 'glass_v02_ui')"),
        ('            "\'BVT_Optical_Micro_Clamp\', \'MINIMUM\', micro, const=.025",',
         '            "\'BVT_Optical_Micro_Clamp\'",'),
        ('''        for needle in (
            "'BVT_Optical_Refraction_Gain_Softener'",''',
         '''        # The v0.2 source has two explicit contact limits.  Assert their
        # numerical branches, not an obsolete hard-coded source substring.
        tree = ast.parse(optical)
        func = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'optical_sockets')
        clamps = [
            kw.value
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == '_math'
            and any(isinstance(arg, ast.Constant)
                    and arg.value == 'BVT_Optical_Micro_Clamp'
                    for arg in node.args)
            for kw in node.keywords if kw.arg == 'const'
        ]
        self.assertEqual(len(clamps), 1)
        self.assertIsInstance(clamps[0], ast.IfExp)
        self.assertEqual(ast.literal_eval(clamps[0].orelse), .025)
        self.assertEqual(ast.literal_eval(clamps[0].body), .06)
        self.assertIn('bvt_optical_stress_test', ast.unparse(clamps[0].test))

        for needle in (
            "'BVT_Optical_Refraction_Gain_Softener'",'''),
    ],
    'test_realistic_atlas.py': [
        ("        self.assertIn('realistic_atlas, optical_water, visual_quality_ui)', (ROOT/'bvt_studio/__init__.py').read_text('utf-8'))",
         "        assert_registered_modules(self, (ROOT/'bvt_studio/__init__.py').read_text('utf-8'),\n"
         "                                  'realistic_atlas', 'optical_water',\n"
         "                                  'visual_quality_ui', 'glass_v02_ui')"),
    ],
}


def git_out(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    branch = git_out('branch', '--show-current')
    head = git_out('rev-parse', '--short', 'HEAD')
    print('BRANCH=' + branch)
    print('HEAD=' + head)
    if branch != 'feature/photorealistic-droplets-v05':
        raise RuntimeError('Wrong branch; expected feature/photorealistic-droplets-v05')
    if head != '8934f24':
        raise RuntimeError('Unexpected HEAD: this fix is specific to 8934f24')
    if not (ROOT/'bvt_studio/glass_v02_ui.py').is_file():
        raise RuntimeError('Glass Gallery v0.2 source not installed')
    if not (ROOT/'bvt_studio/optical_water.py').is_file():
        raise RuntimeError('Missing Optical Water implementation')
    # Verify the real implementation still exposes an explicit stress switch.
    optical_source = (ROOT/'bvt_studio/optical_water.py').read_text('utf-8')
    if "bvt_optical_stress_test" not in optical_source:
        raise RuntimeError('Optical stress flag missing; stop rather than weaken tests')

    changed = {}
    import_line = 'from _bvt_contract_v02 import assert_registered_modules\n'
    for filename, pairs in REPLACEMENTS.items():
        path = TESTS / filename
        src = path.read_text('utf-8')
        new = src
        for old, replacement in pairs:
            if old in new:
                if new.count(old) != 1:
                    raise RuntimeError(f'Ambiguous matching test contract in {filename}')
                new = new.replace(old, replacement, 1)
            elif replacement not in new:
                raise RuntimeError(f'Unexpected contents of {filename}; no files changed')
        if import_line not in new:
            marker = 'from pathlib import Path\n'
            if new.count(marker) != 1:
                raise RuntimeError(f'Cannot safely insert import in {filename}')
            new = new.replace(marker, marker + import_line, 1)
        ast.parse(new, filename=str(path))
        changed[path] = new

    helper_path = TESTS / '_bvt_contract_v02.py'
    if helper_path.exists() and helper_path.read_text('utf-8') != HELPER:
        raise RuntimeError('Existing helper differs; no files changed')
    ast.parse(HELPER)
    # Every targeted replacement is validated before writing any file.
    for path, contents in changed.items():
        if path.read_text('utf-8') != contents:
            path.write_text(contents, 'utf-8')
            print('UPDATED:', path.relative_to(ROOT))
        else:
            print('UNCHANGED:', path.relative_to(ROOT))
    if not helper_path.exists():
        helper_path.write_text(HELPER, 'utf-8')
        print('CREATED:', helper_path.relative_to(ROOT))
    else:
        print('UNCHANGED:', helper_path.relative_to(ROOT))
    print('CONTRACT_TEST_FIX=OK')


if __name__ == '__main__':
    main()
