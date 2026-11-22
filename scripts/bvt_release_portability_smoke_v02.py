#!/usr/bin/env python3
"""Read-only smoke test for the BVT Demo Release. Run with standard Python.
Extracts only copies of scene.blend to temporary isolated directories, checks
packed PNG bytes using bpy and renders each scene again. Never saves a blend.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

MODES = ('00_clean','01_light_condensation','02_heavy_condensation','03_frost',
         '04_dirty_glass','05_reflections','06_microbeads_only','07_macro_droplets_only',
         '08_running_water_only','09_combined_water_no_optics','10_combined_water_optics',
         '11_heavy_running_water','12_stress_optics')
PREFIX = 'BVT_Studio_Effects_Gallery/'

def need(ok, msg):
    if not ok:
        raise RuntimeError(msg)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

def worker(spec_path, result_path):
    import bpy
    import numpy as np
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    blend = Path(spec['blend'])
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    rows = []
    for rel, expected in spec['assets'].items():
        images = [i for i in bpy.data.images if i.filepath.replace('\\','/') == rel]
        need(len(images)==1, f'{rel}: expected exactly one image, found {len(images)}')
        im = images[0]
        need(im.packed_file is not None, f'{rel}: no packed data')
        actual = digest(bytes(im.packed_file.data))
        need(actual==expected, f'{rel}: packed SHA-256 mismatch')
        need(min(im.size)>=2, f'{rel}: invalid image size')
        if rel.startswith('//atlases/'):
            need(bytes(im.packed_file.data)[:4]==b'\x76\x2f\x31\x01',f'{rel}: not EXR')
            need(im.alpha_mode=='CHANNEL_PACKED' and im.colorspace_settings.name=='Non-Color',f'{rel}: atlas channel settings changed')
        if rel.startswith(('//masks/', '//maps/')):
            need(im.use_fake_user, f'{rel}: fake user missing')
        # Never change the saved scene. Report original metadata for privacy review.
        packed_paths = [str(getattr(p,'filepath','')) for p in getattr(im,'packed_files',())]
        rows.append({'relative_path':rel,'sha256':actual,'packed_paths_absolute_count':sum(':' in p[:3] or p.startswith(chr(92)) or (p.startswith('/') and not p.startswith('//')) for p in packed_paths), 'packed_paths_nonrelative_count':sum(not p.startswith('//') for p in packed_paths)})
    need(scene.camera is not None,'No camera')
    need(len([o for o in scene.objects if o.get('bvt_role')=='glass_overlay'])==4,'Expected 4 panes')
    need(scene.get('bvt_gallery_v02_variant')==spec['mode'],'Wrong saved variant')
    need(scene.render.filepath=='//render.png','Unexpected render path')
    out = blend.parent/'rerender.png'
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    need(out.is_file(),'Rerender did not produce a PNG')
    def read_rgb(path):
        im=bpy.data.images.load(str(path),check_existing=False)
        try:
            im.colorspace_settings.name='Non-Color'
            w,h=im.size[:]
            arr=np.empty(w*h*4,dtype=np.float32)
            im.pixels.foreach_get(arr)
            return arr.reshape(h,w,4)[...,:3].copy()
        finally:
            bpy.data.images.remove(im)
    old=read_rgb(Path(spec['reference'])); new=read_rgb(out)
    need(old.shape==new.shape,'Render dimension mismatch')
    d=np.max(np.abs(old-new),axis=2)
    changed=int(np.count_nonzero(d>4.0001/255.0))
    relative_ok=all(row['packed_paths_nonrelative_count']==0 for row in rows)
    report={'variant':spec['mode'],'blender':bpy.app.version_string,'packed_assets':rows,'asset_count':len(rows),'rerender_max_rgb_delta':float(d.max()),'pixels_gt_4_255':changed,'status':'PASS' if changed==0 and relative_ok else 'REVIEW'}
    write_json(result_path,report)
    print('PORTABILITY='+report['status']+' '+spec['mode'],flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',type=Path,required=True,help='Directory containing the four release ZIPs and manifest')
    p.add_argument('--blender',required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args(); release=a.release.resolve(); report=a.report.resolve()
    manifest=json.loads((release/'release_manifest.json').read_text(encoding='utf-8'))
    meta=next(x for x in manifest['archives'] if x['name']=='BVT_Studio_Effects_Gallery.zip')
    gallery=release/meta['name']; need(gallery.stat().st_size==meta['bytes'] and digest(gallery.read_bytes())==meta['sha256'],'Gallery ZIP does not match release manifest')
    report.parent.mkdir(parents=True,exist_ok=True)
    results=[]
    qa_meta=next(x for x in manifest['archives'] if x['name']=='BVT_Studio_QA_Reports.zip')
    qa=release/qa_meta['name']
    need(qa.stat().st_size==qa_meta['bytes'] and digest(qa.read_bytes())==qa_meta['sha256'],'QA ZIP does not match release manifest')
    with tempfile.TemporaryDirectory(prefix='bvt_release_isolated_') as tmp, ZipFile(gallery) as z, ZipFile(qa) as q:
        need(z.testzip() is None and q.testzip() is None,'Gallery or QA CRC failed')
        root=Path(tmp); ref=root/'reference';ref.mkdir(); (root/'isolated').mkdir()
        source_hash=digest(z.read(PREFIX+'source.png'))
        need(source_hash==manifest['source_sha256'],'Source SHA mismatch')
        for mode in MODES:
            d=root/'isolated'/mode; d.mkdir(); (d/'scene.blend').write_bytes(z.read(PREFIX+mode+'/scene.blend'))
            # PNG references are intentionally not siblings of the isolated .blend.
            refpath=ref/(mode+'.png');refpath.write_bytes(z.read(PREFIX+mode+'/render.png'))
            assets={'//../source.png':source_hash}
            paths=[f'masks/mask_glass_{i:03}.png' for i in range(1,5)]
            if mode in MODES[6:]:
                paths += [f'maps/Glass_p_{i:03}/{k}.png' for i in range(1,5) for k in ('alpha','height','normal')]
            for rel in paths:assets['//'+rel]=digest(z.read(PREFIX+mode+'/'+rel))
            if mode in MODES[1:3]:
                reopen=json.loads(q.read('BVT_Studio_QA_Reports/'+mode+'/reopen.json'))
                need(reopen['status']=='PASS' and reopen['variant']==mode,'Invalid reopen report')
                panes=reopen['panes']
                need([x['name'] for x in panes]==[f'Glass_p_{i:03}' for i in range(1,5)],'Procedural pane list mismatch')
                for pane in panes:
                    assets['//atlases/'+pane['name']+'.exr']=pane['procedural_atlas_sha256']
            spec=root/'spec.json'; result=root/'result.json'
            if result.exists():result.unlink()
            write_json(spec,{'mode':mode,'blend':str(d/'scene.blend'),'reference':str(refpath),'assets':assets})
            print('CHECK_SCENE='+mode,flush=True)
            cmd=[a.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(Path(__file__).resolve()),'--','--worker',str(spec),str(result)]
            r=subprocess.run(cmd,check=False)
            if r.returncode==0 and result.is_file():results.append(json.loads(result.read_text(encoding='utf-8')))
            else:results.append({'variant':mode,'status':'ERROR','blender_exit':r.returncode})
            write_json(report,{'release':manifest['version'],'commit':manifest['commit'],'scene_results':results,'complete':len(results)==13})
    ok=(all(x['status']=='PASS' for x in results) and len(results)==13
        and sum(x.get('asset_count',0) for x in results)==157)
    print('PORTABILITY_SMOKE='+('PASS' if ok else 'REVIEW_OR_ERROR'))
    print('REPORT='+str(report))
    return 0 if ok else 2

if __name__=='__main__':
    tail=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    if tail and tail[0]=='--worker':worker(Path(tail[1]),Path(tail[2]))
    else:raise SystemExit(main())
