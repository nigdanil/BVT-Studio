"""Stable payload metadata and actionable persistence diagnostics."""
import struct
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from bvt_matrix_resource_qa import PNG, EXR, packed_layout,validate_runtime_size,snapshot_delta,canonical_resource_path


def png(w=512,h=128):
    return PNG+struct.pack('>I4sII5B',13,b'IHDR',w,h,8,2,0,0,0)+b'\0'*4


def exr(w=512,h=128):
    return EXR+struct.pack('<I',2)+b'dataWindow\0box2i\0'+struct.pack('<Iiiii',16,4,-3,3+w,h-4)+b'\0'


class MatrixResourceQATests(unittest.TestCase):
    def test_png_header(self):
        self.assertEqual(packed_layout(png()),('.png',[512,128]))
    def test_exr_data_window_nonzero_origin(self):
        self.assertEqual(packed_layout(exr()),('.exr',[512,128]))
    def test_reject_bad_header(self):
        for raw in (b'',PNG,png(0),EXR,exr()[:-2],exr(0),EXR+struct.pack('<I',0x1002)+b'\0'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):packed_layout(raw)
    def test_runtime_unloaded_or_matching(self):
        validate_runtime_size([0,0],[512,128]);validate_runtime_size([512,128],[512,128])
        for runtime in ([512,0],[128,512],[-1,128]):
            with self.assertRaises(ValueError):validate_runtime_size(runtime,[512,128])
    def test_diff_identifies_changes(self):
        a={'one':{'sha256':'a','path':'//x','size':[1,2]},'gone':{}}
        b={'one':{'sha256':'b','path':'//x','size':[1,2]},'new':{}}
        self.assertEqual(snapshot_delta(a,b),{'removed':['gone'],'added':['new'],'changed':{'one':{'sha256':{'before':'a','after':'b'}}}})
        self.assertEqual(snapshot_delta(a,a),{'removed':[],'added':[],'changed':{}})
    def test_worker_keeps_strict_byte_and_rgb_checks(self):
        import ast
        text=(ROOT/'scripts/blender_material_artifact_gallery.py').read_text('utf-8');ast.parse(text)
        for expr in ('packed_layout(raw)','validate_runtime_size(runtime,size)','need(after==resources','r_delta[\'max_rgb\']==0',"'resource_persistence.json'","'packed_paths':paths"):
            self.assertIn(expr,text)


    def test_windows_slash_only(self):
        rel='//resources/'+'a'*64+'.png'
        self.assertEqual(canonical_resource_path(rel,rel),rel)
        self.assertEqual(canonical_resource_path(rel.replace('resources/','resources\\'),rel),rel)
    def test_wrong_paths_rejected(self):
        rel='//resources/'+'a'*64+'.png'
        for path in (r'C:\resources\a.png','/resources/a.png',r'\\resources\a.png',
                     '//resources/../'+rel[2:], '//resources//'+rel.split('/')[-1],
                     rel.upper(),rel+'.bak',rel.replace('resources','other'),
                     rel.replace('a'*64,'b'*64)):
            with self.subTest(path=path), self.assertRaises(ValueError):
                canonical_resource_path(path,rel)
    def test_normalized_snapshot_keeps_sha_size_and_membership_strict(self):
        import copy
        rel='//resources/'+'a'*64+'.png'
        win=rel.replace('resources/','resources\\')
        before={'photo':{'path':canonical_resource_path(rel,rel),'packed_paths':[rel],'sha256':'a'*64,'size':[1672,941]}}
        after={'photo':{'path':canonical_resource_path(win,rel),'packed_paths':[canonical_resource_path(win,rel)],'sha256':'a'*64,'size':[1672,941]}}
        self.assertEqual(before,after)
        for field,val in [('sha256','b'*64),('size',[941,1672])]:
            changed=copy.deepcopy(after);changed['photo'][field]=val
            self.assertNotEqual(before,changed)
            self.assertIn(field,snapshot_delta(before,changed)['changed']['photo'])
        self.assertEqual(snapshot_delta(before,{})['removed'],['photo'])
    def test_worker_normalizes_both_paths_retains_raw_diagnostics(self):
        text=(ROOT/'scripts/blender_material_artifact_gallery.py').read_text('utf-8')
        for expr in ('canonical_resource_path(im.filepath,rel)',
                     'canonical_resource_path(p,rel) for p in raw_paths',
                     "'comparison_path_raw'", "'comparison_packed_paths_raw'",
                     'need(after==resources', "r_delta['max_rgb']==0"):
            self.assertIn(expr,text)

if __name__=='__main__':unittest.main()
