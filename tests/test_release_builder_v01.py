"""Release pipeline contracts, independent of bpy."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import validate_examples as v
import build_release as b

class ReleaseBuilderTests(unittest.TestCase):
    def test_bundled_example(self):
        e=v.validate(ROOT/'examples/freezer_planogram')
        self.assertEqual(len(e['rects']),4);self.assertEqual(len(e['assets']),16)
        self.assertEqual(len(v.read(e['configs']['gallery'])['variants']),13)
    def test_reject_path_escapes(self):
        base=ROOT/'examples/freezer_planogram'
        for name in ('../README.md','C:/file.png','/tmp/x','maps\\a.png'):
            with self.subTest(name=name),self.assertRaises(ValueError): v.resolve_file(base,name)
    def test_manifest_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t)/'freezer_planogram';shutil.copytree(ROOT/'examples/freezer_planogram',d)
            m=v.read(d/'manifest.json'); m['source']['sha256']='0'*64;(d/'manifest.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'SHA-256'):v.validate(d)
    def test_release_allowlist_excludes_private_data(self):
        e=v.validate(ROOT/'examples/freezer_planogram'); entries=b.example_entries(ROOT/'examples/freezer_planogram',e)
        self.assertTrue(all(name.startswith('examples/') for _,name in entries))
        self.assertFalse(any('/local/' in name or name.endswith('.blend') for _,name in entries))
        gallery=b.gallery_entries(Path('/tmp/gallery'));qa=b.qa_entries(Path('/tmp/gallery'))
        self.assertEqual(sum(name.endswith('/scene.blend') for _,name in gallery),13)
        self.assertEqual(sum(name.endswith('/zero_water_rebuild.png') for _,name in qa),7)
        self.assertFalse(any(name.endswith('.blend') for _,name in qa))
    def test_zip_integrity_and_duplicate_refusal(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);f=d/'a';f.write_bytes(b'test'); z=d/'test.zip'
            b.zip_files(z,[(f,'demo/a')])
            with ZipFile(z) as out:self.assertEqual(out.read('demo/a'),b'test')
            with self.assertRaises(ValueError):b.zip_files(z,[(f,'same'),(f,'same')])
if __name__=='__main__':unittest.main()
