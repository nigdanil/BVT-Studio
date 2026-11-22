"""Pure numerical and integration-contract checks; live Blender smoke is separate."""
import ast
import importlib.util
import json
from pathlib import Path
import struct
import sys
import types
import unittest
import zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if 'bvt_studio' not in sys.modules:
    pkg=types.ModuleType('bvt_studio');pkg.__path__=[str(ROOT/'bvt_studio')];sys.modules['bvt_studio']=pkg
from bvt_studio.glass_material_builtin import builtin_profile
from bvt_studio.glass_material_config import MATERIAL_IDS,load_library
from bvt_studio.glass_material_geometry import pane_rect,resize_mask
from bvt_studio.glass_material_png import decode_png,encode_rgb,chunk,SIGNATURE

class GlassMaterialBlenderContracts(unittest.TestCase):
    def test_profiles_match_repository(self):
        lib=load_library(ROOT/'configs/glass_materials')
        for key in MATERIAL_IDS:
            self.assertEqual(builtin_profile(key),lib[key])
        a=builtin_profile('clear_glass');a['appearance']['haze_mix']=1
        self.assertEqual(builtin_profile('clear_glass')['appearance']['haze_mix'],0.)
    def test_png_roundtrip_and_crc(self):
        a=np.random.default_rng(42).integers(0,256,(12,23,3),dtype=np.uint8);d=encode_rgb(a)
        np.testing.assert_array_equal(decode_png(d),a)
        for bad in (d[:-4],b'not png',d[:30]+bytes([d[30]^1])+d[31:]):
            with self.assertRaises(ValueError):decode_png(bad)
    def test_png_all_filters(self):
        rng=np.random.default_rng(2);a=rng.integers(0,256,(5,9,3),dtype=np.uint8);rows=[];prev=[0]*27
        for mode,r in enumerate(a.reshape(5,27)):
            row=list(map(int,r));encoded=[]
            for i,x in enumerate(row):
                l=row[i-3] if i>=3 else 0;u=prev[i];ul=prev[i-3] if i>=3 else 0
                preds=[0,l,u,(l+u)//2,min((l,u,ul),key=lambda t:abs(l+u-ul-t))]
                encoded.append((x-preds[mode])&255)
            rows.append(bytes([mode]+encoded));prev=row
        data=SIGNATURE+chunk(b'IHDR',struct.pack('>IIBBBBB',9,5,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
        np.testing.assert_array_equal(decode_png(data),a)
    def test_png_alpha_and_mask(self):
        data=SIGNATURE+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes([0,0,0,0,255,128,128,128,0])))+chunk(b'IEND',b'')
        with self.assertRaises(ValueError):decode_png(data)
        np.testing.assert_array_equal(decode_png(data,mask=True),[[0,128/255]])
    def test_rect_uv_and_top_down(self):
        pts=[(.1,.2,0,0),(.5,.2,1,0),(.5,.8,1,1),(.1,.8,0,1)]
        self.assertEqual(pane_rect(pts,100,200),[10,40,50,160])
        for bad in ([pts[0],pts[1],(.51,.78,1,1),pts[3]],[(.1,.2,0,1),*pts[1:]],[(0,0,0,0)]*4):
            with self.assertRaises(ValueError):pane_rect(bad,100,200)
    def test_mask_resample(self):
        a=np.array([[0.,1.],[0.,1.]])
        b=resize_mask(a,4,4);np.testing.assert_allclose(b[0],[0,.25,.75,1.]);self.assertTrue(np.all(b==b[0]))
    def test_source_hooks_and_legacy_path(self):
        common=(ROOT/'bvt_studio/common.py').read_text('utf8');real=(ROOT/'bvt_studio/glass_realism.py').read_text('utf8');init=(ROOT/'bvt_studio/__init__.py').read_text('utf8')
        self.assertIn("nodes.get('BVT_Material_Original')",common);self.assertIn('return original.image',common)
        self.assertIn('effective_source_image(source, image)',real)
        tree=ast.parse(init);self.assertTrue(any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MODULES' for t in n.targets) and isinstance(n.value,ast.Tuple) and any(isinstance(x,ast.Name) and x.id=='glass_material_ui' for x in n.value.elts) for n in tree.body))
        for file in ('glass_material_blender.py','glass_material_ui.py'):
            ast.parse((ROOT/'bvt_studio'/file).read_text('utf8'))
        ast.parse((ROOT/'scripts/blender_glass_materials_smoke.py').read_text('utf8'))
    def test_separate_panel_and_persistence_contract(self):
        ui=(ROOT/'bvt_studio/glass_material_ui.py').read_text('utf8');source=(ROOT/'bvt_studio/glass_material_blender.py').read_text('utf8')
        for x in ('3B. Glass Material Library v0.1','apply_glass_material_v01','import_glass_material_v01','rebuild_glass_materials_v01'):
            self.assertIn(x,ui)
        for x in ('original.pack()','im.pack()','original_sha256','baked_sha256','render_materials(rgb,assignments)','Overlapping glass panes','tex.image=original'):
            self.assertIn(x,source)

if __name__=='__main__':unittest.main()
