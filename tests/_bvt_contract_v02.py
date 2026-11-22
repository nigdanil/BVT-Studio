"""AST-based addon registration assertions: insensitive to import ordering."""
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
