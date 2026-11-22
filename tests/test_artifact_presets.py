"""Presets and deterministic UV offsets are portable to CPython without Blender."""
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / 'bvt_studio' / 'artifact_config.py'
spec = importlib.util.spec_from_file_location('bvt_artifact_config', CONF)
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


class TestGlassArtifacts(unittest.TestCase):
    def test_presets_are_nonempty_and_unique(self):
        self.assertEqual(len(artifact.PRESETS), 6)
        self.assertEqual(len({tuple(sorted(p.items())) for p in artifact.PRESETS.values()}), 6)

    def test_all_channels_are_complete_and_in_range(self):
        expected = {'reflection', 'tint', 'haze', 'frost', 'droplets', 'dirt', 'coverage'}
        for name, preset in artifact.PRESETS.items():
            with self.subTest(name=name):
                self.assertEqual(set(preset), expected)
                self.assertTrue(all(0 <= value <= 1 for value in preset.values()))

    def test_own_intensity_not_shared(self):
        x = artifact.preset_values('HEAVY_CONDENSATION', intensity=1.0)
        y = artifact.preset_values('HEAVY_CONDENSATION', intensity=0.5)
        self.assertEqual(y['bvt_glass_droplets'], x['bvt_glass_droplets']/2)
        self.assertEqual(y['bvt_artifact_coverage'], x['bvt_artifact_coverage'])

    def test_coverage_override(self):
        p = artifact.preset_values('FROST', coverage=.74)
        self.assertEqual(p['bvt_artifact_coverage'], .74)

    def test_no_mutation_of_preset_source(self):
        before = dict(artifact.PRESETS['CLEAN'])
        x = artifact.preset_values('CLEAN')
        x['bvt_glass_haze'] = 1.0
        self.assertEqual(before, artifact.PRESETS['CLEAN'])

    def test_reject_unknown_or_invalid_inputs(self):
        for args in [('MISSING', 1.0, None), ('FROST', -0.1, None),
                     ('FROST', 1.1, None), ('FROST', 1.0, -0.2),
                     ('FROST', 1.0, 1.2)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                artifact.preset_values(*args)

    def test_seed_is_deterministic_and_independent(self):
        a = artifact.seed_offsets(42)
        self.assertEqual(a, artifact.seed_offsets(42))
        self.assertNotEqual(a, artifact.seed_offsets(43))

    def test_invalid_seed_rejected(self):
        for seed in (-1, 2147483648):
            with self.assertRaises(ValueError):
                artifact.seed_offsets(seed)

    def test_shader_has_seeded_dirt_and_droplet_masks(self):
        src = (ROOT/'bvt_studio'/'glass.py').read_text(encoding='utf-8')
        for marker in ('BVT_Artifact_Seed_Offset', 'BVT_Droplets_Voronoi',
                       'BVT_Droplets_Mask', 'BVT_Dirt_Mask', 'BVT_Dirt_Tint',
                       'bvt_artifact_coverage', 'bvt_artifact_seed'):
            self.assertIn(marker, src)

    def test_registered_ui_and_operator(self):
        init=(ROOT/'bvt_studio'/'__init__.py').read_text(encoding='utf-8')
        ui=(ROOT/'bvt_studio'/'ui.py').read_text(encoding='utf-8')
        op=(ROOT/'bvt_studio'/'artifact_presets.py').read_text(encoding='utf-8')
        self.assertIn('artifact_presets, ui', init)
        self.assertIn('bvt_studio.apply_glass_preset', ui)
        self.assertIn('bvt_studio.refresh_glass_pattern', ui)
        self.assertIn("'REGISTER', 'UNDO'", op)

    def test_manifest_records_reproduction_inputs(self):
        src=(ROOT/'bvt_studio'/'annotation.py').read_text(encoding='utf-8')
        for marker in ('artifact_seed=', 'artifact_preset=', 'artifact_coverage=',
                       'droplets=', 'dirt='):
            self.assertIn(marker,src)

    def test_blender_smoke_script_valid_python(self):
        file=ROOT/'scripts'/'blender_glass_artifacts_smoke.py'
        ast.parse(file.read_text(encoding='utf-8'))
        self.assertIn('BVT GLASS ARTIFACTS SMOKE: OK', file.read_text(encoding='utf-8'))
