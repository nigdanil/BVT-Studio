#!/usr/bin/env python3
"""Verify self-contained example manifests, input paths and hashes without Blender."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
MODES = ('00_clean','01_light_condensation','02_heavy_condensation','03_frost',
         '04_dirty_glass','05_reflections','06_microbeads_only','07_macro_droplets_only',
         '08_running_water_only','09_combined_water_no_optics','10_combined_water_optics',
         '11_heavy_running_water','12_stress_optics')
WATER = MODES[6:]

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def need(condition, message):
    if not condition:
        raise ValueError(message)

def resolve_file(base, name):
    need(isinstance(name,str) and '\\' not in name and ':' not in name, 'Expected portable relative path')
    p=Path(name)
    need(not p.is_absolute() and '..' not in p.parts and bool(p.parts), f'Unsafe path: {name}')
    out=(base/p).resolve()
    need(out.is_relative_to(base.resolve()) and out.is_file() and out.stat().st_size>0, f'Missing/unsafe file: {name}')
    need(not any((base.joinpath(*p.parts[:i])).is_symlink() for i in range(1,len(p.parts)+1)), f'Symlink not allowed: {name}')
    return out

def png_size(p):
    with p.open('rb') as f: h=f.read(24)
    need(len(h)==24 and h[:8]==b'\x89PNG\r\n\x1a\n' and h[12:16]==b'IHDR', f'Invalid PNG: {p.name}')
    return struct.unpack('>II',h[16:24])

def validate(base):
    base=base.resolve(); m=read(base/'manifest.json')
    need(m.get('schema')=='bvt.example.v1' and m.get('id')==base.name,'Invalid example ID/schema')
    source=m['source']; image=resolve_file(base,source['path'])
    need(sha(image)==source['sha256'],'Source SHA-256 mismatch')
    size=png_size(image)
    need(size==(source['width'],source['height']) and min(size)>0,'Image dimensions mismatch')
    configs={k:resolve_file(base,m['configs'][k]) for k in ('rectangles','gallery','scene')}
    rc=read(configs['rectangles']); rects=rc['glass_rectangles']
    need(rc['reference_size']==list(size) and isinstance(rects,list) and bool(rects),'Invalid rectangle reference')
    for r in rects:
        need(len(r)==4 and all(type(v) is int for v in r) and 0<=r[0]<r[2]<=size[0] and 0<=r[1]<r[3]<=size[1], 'Invalid rectangle')
    g=read(configs['gallery']); s=read(configs['scene'])
    need(g.get('schema')=='bvt.glass-gallery.v02' and isinstance(g.get('variants'),dict),'Invalid gallery config')
    need(s.get('schema')=='bvt.glass-gallery.v02' and isinstance(s.get('glass'),dict),'Invalid scene config')
    names={f'Glass_p_{i:03}' for i in range(1,len(rects)+1)}
    need(set(s['glass'])==names,'Scene preset pane names mismatch')
    if base.name=='freezer_planogram':
        need(len(rects)==4 and set(g['variants'])==set(MODES),'Freezer release requires four panes and 13 variants')
    seen=set(); assets=[]
    for record in m.get('assets',{}).get('files',[]):
        rel=record['path']; p=resolve_file(base,rel)
        need(rel not in seen and sha(p)==record['sha256'], f'Duplicate/hash mismatch: {rel}')
        seen.add(rel); png_size(p); assets.append(p)
    labels=m.get('labels')
    need(labels is None,'v1 release supports no labeled examples yet; use separate dataset validation')
    if base.name=='freezer_planogram':
        expected={f'masks/mask_glass_{i:03}.png' for i in range(1,5)} | {f'maps/Glass_p_{i:03}/{k}.png' for i in range(1,5) for k in ('alpha','height','normal')}
        need(seen==expected,'Expected all 4 mask and 12 map PNGs')
    return dict(manifest=m,image=image,configs=configs,rects=rects,assets=assets)

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--root',type=Path,default=ROOT/'examples'); a=p.parse_args()
    dirs=sorted(d for d in a.root.iterdir() if d.is_dir() and d.name not in ('local','generated') and not d.name.startswith('.'))
    need(bool(dirs),'No examples')
    for d in dirs:
        need(not d.is_symlink(),'Example symlink forbidden'); validate(d); print('EXAMPLE_VALID='+d.name)
    print('EXAMPLES_VALIDATION=PASS')
if __name__=='__main__': main()
