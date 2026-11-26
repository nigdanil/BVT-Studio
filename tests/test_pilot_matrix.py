"""Pilot matrix contract tests (ordinary Python; no Blender required)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pilot_runner", ROOT / "scripts/bvt_pilot_batch_runner.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
MATRIX = ROOT / "configs/research/pilot_001.json"


class PilotMatrixTests(unittest.TestCase):
    def test_matrix_contract(self):
        conditions, seed, raw = runner.load_matrix(MATRIX)
        self.assertEqual(raw, MATRIX.read_bytes())
        self.assertEqual(seed, 42)
        self.assertEqual(len(conditions), 21)
        self.assertEqual(conditions[0]["id"], "00_clean")
        self.assertEqual(len({c["id"] for c in conditions}), 21)
        families = {}
        for c in conditions[1:]:
            families.setdefault(c["id"].rsplit("_", 1)[0], []).append(c)
        self.assertEqual(len(families), 5)
        for rows in families.values():
            self.assertEqual([r["intensity"] for r in rows], [.25, .5, .75, 1.])
            self.assertEqual(len({r["coverage"] for r in rows}), 1)
            self.assertEqual(len({r["preset"] for r in rows}), 1)

    def test_bad_conditions(self):
        good = json.loads(MATRIX.read_text(encoding="utf-8"))["conditions"]
        for patch in ({"id": "00_clean"}, {"id": "../escape"}, {"intensity": float("nan")},
                      {"coverage": 2}, {"preset": "UNKNOWN"}, {"channel": "unknown", "channel_max": .5},
                      {"preset": "CUSTOM"}, {"intensity": True}):
            rows = [dict(c) for c in good]
            rows[1].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                runner.validate_conditions(rows)
        with self.assertRaises(ValueError):
            runner.validate_conditions(list(reversed(good)))

    def test_seed_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            obj = json.loads(MATRIX.read_text(encoding="utf-8"))
            obj["seed"] = 2147483647
            p.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(ValueError):
                runner.load_matrix(p)

    def test_plan_matrix_and_legacy_smoke_are_read_only(self):
        conditions, seed, _ = runner.load_matrix(MATRIX)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "masters"
            repo = Path(tmp) / "repo"
            (repo / "bvt_studio").mkdir(parents=True)
            (repo / "bvt_studio/__init__.py").touch()
            images = repo / "data_local/synthetic_chatgpt/clean/images"
            images.mkdir(parents=True)
            for i in range(1, 11):
                folder = root / f"{i:04d}"
                (folder / "labels/train").mkdir(parents=True)
                (folder / f"scene_{i:04d}.blend").write_bytes(b"fixture")
                (folder / "labels/train/sample_000001.txt").write_text("0 .5 .5 .1 .1\\n")
                (images / f"chatgpt_{i:06d}.png").write_bytes(b"fixture")
            out, jobs = runner.plan(repo, root, list(range(1, 11)), "pilot", conditions, seed)
            self.assertFalse(out.exists())
            self.assertEqual(sum(len(j["conditions"]) for j in jobs), 210)
            self.assertTrue(all(j["seed"] == 42 for j in jobs))
            out, smoke = runner.plan(repo, root, [1, 6], "smoke")
            self.assertFalse(out.exists())
            self.assertEqual(sum(len(j["conditions"]) for j in smoke), 6)
            out.mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                runner.plan(repo, root, [1, 6], "smoke")


if __name__ == "__main__":
    unittest.main()
