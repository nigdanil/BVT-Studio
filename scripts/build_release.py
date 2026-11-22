#!/usr/bin/env python3
"""Build a fresh 13-scene BVT demo release and four ZIPs, without publishing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED
from validate_examples import ROOT, MODES, WATER, validate, sha, read, need, png_size

ARCHIVES=('BVT_Studio_Addon.zip','BVT_Studio_Examples.zip','BVT_Studio_Effects_Gallery.zip','BVT_Studio_QA_Reports.zip')

def run(*cmd):
    subprocess.run([str(x) for x in cmd],cwd=ROOT,check=True)

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()

def zip_files(dest, entries):
    entries=list(entries); names=[name for _,name in entries]
    need(len(names)==len(set(names)),f'Duplicate paths in {dest.name}')
    with ZipFile(dest,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in sorted(entries,key=lambda x:x[1]):
            need(p.is_file() and not p.is_symlink(),f'Missing/unsafe archive file: {p}')
            z.write(p,name)
    with ZipFile(dest) as z: need(z.testzip() is None,'ZIP CRC failure')

def check_gallery(gallery, example):
    from check_gallery_v021_outputs import inspect
    problems=inspect(gallery)
    need(not problems,'; '.join(problems))
    size=(example['manifest']['source']['width'],example['manifest']['source']['height'])
    for mode in MODES:
        d=gallery/mode; m=read(d/'manifest.json')
        need(m['variant']==mode and m['source_sha256']==example['manifest']['source']['sha256'] and m['rects']==example['rects'],f'{mode}: input mismatch')
        need(m['calibration']=='v0.2.1_matched_neutral_realistic_atlas',f'{mode}: wrong calibration')
        need(m['blender'].startswith('5.2.3'),f'{mode}: wrong Blender version')
        need((d/'scene.blend').stat().st_size>0 and png_size(d/'render.png')==size,f'{mode}: missing scene/render')
        need(len(m['panes'])==4 and all(p['mask_packed'] for p in m['panes']),f'{mode}: pane/mask manifest mismatch')
        if mode!='00_clean':
            q=m['quality']; need(q['leakage_pixels_beyond_3px_geometry_guard']==0,f'{mode}: leakage')
        if mode in WATER:
            z=m['zero_water_test']
            need(z['same_shader_topology'] and z['same_renderer_controls'] and z['events_generated']==0 and z['events_visible_proxy']==0,f'{mode}: invalid null control')
            need(all(p['shader_topology_unchanged'] and p['renderer_controls_unchanged'] and p['atlas_packed'] for p in m['panes']),f'{mode}: control mismatch')
            need(all(png_size(d/f)==size for f in ('preset_without_water.png','zero_water_rebuild.png')),f'{mode}: control dimensions')
    need((gallery/'index.html').is_file() and (gallery/'summary.csv').is_file(),'Missing gallery index/summary')

def example_entries(base, example):
    # Explicit manifest allowlist; never package examples/local or arbitrary .blend files.
    paths=[base/'manifest.json',base/'README.md',base.parent/'README.md',example['image'],*example['configs'].values(),*example['assets']]
    extra=base/'configs/bvt_freezer_glass_rects_v02_default.json'
    if extra.is_file(): paths.append(extra)
    return [(p,p.relative_to(ROOT).as_posix()) for p in paths]

def gallery_entries(gallery):
    files=[gallery/x for x in ('index.html','summary.csv','source.png')]
    for mode in MODES:
        d=gallery/mode
        files.extend(d/f for f in ('scene.blend','render.png','manifest.json'))
        files.extend(d/'masks'/f'mask_glass_{i:03}.png' for i in range(1,5))
        if mode in WATER: files.extend(d/'maps'/f'Glass_p_{i:03}'/(k+'.png') for i in range(1,5) for k in ('alpha','height','normal'))
    return [(p,'BVT_Studio_Effects_Gallery/'+p.relative_to(gallery).as_posix()) for p in files]

def qa_entries(gallery):
    paths=[gallery/'summary.csv',gallery/'source.png']
    for mode in MODES:
        d=gallery/mode; paths.extend(d/f for f in ('manifest.json','reopen.json','render.png'))
        if mode in WATER: paths.extend(d/f for f in ('preset_without_water.png','zero_water_rebuild.png'))
    return [(p,'BVT_Studio_QA_Reports/'+p.relative_to(gallery).as_posix()) for p in paths]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--version',required=True);p.add_argument('--blender',default=os.environ.get('BVT_BLENDER') or shutil.which('blender') or r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe');a=p.parse_args()
    need(re.fullmatch(r'v[0-9](?:[0-9A-Za-z.-]{0,62}[0-9A-Za-z])?',a.version) is not None,'Expected safe v-prefixed version')
    # Release must be tied to committed source, not a dirty working copy.
    need(not git('status','--porcelain'),'Working tree is not clean; commit/review sources first')
    commit=git('rev-parse','HEAD'); base=ROOT/'examples/freezer_planogram'; example=validate(base)
    version=subprocess.check_output([a.blender,'--version'],text=True).splitlines()[0]
    need(re.match(r'^Blender 5\.2\.3(?:\s|$)',version) is not None,'Requires Blender 5.2.3: '+version)
    work=ROOT/'qa_renders'/'release_builds'/a.version; out=ROOT/'dist/releases'/a.version
    need(not work.exists() and not out.exists(),'Build directories already exist: use a new version or archive/remove only this failed build explicitly')
    work.mkdir(parents=True); gallery=work/'gallery'; gallery.mkdir(); shutil.copyfile(example['image'],gallery/'source.png')
    # The original calibrated generator is retained byte-for-byte, no shader changes.
    run(sys.executable,ROOT/'scripts/validate_examples.py')
    run(sys.executable,'-m','unittest','discover','-s','tests','-v')
    for mode in MODES:
        print('RELEASE_RENDER='+mode,flush=True)
        run(a.blender,'--background','--factory-startup','--python-exit-code','1','--python',ROOT/'scripts/bvt_glass_effect_gallery_v02.py','--','--repo',ROOT,'--photo',example['image'],'--output',gallery,'--rects-file',example['configs']['rectangles'],'--config',example['configs']['gallery'],'--mode',mode)
    check_gallery(gallery,example)
    for mode in MODES:
        d=gallery/mode
        run(a.blender,'--background','--factory-startup','--python-exit-code','1','--python',ROOT/'scripts/blender_release_reopen.py','--','--blend',d/'scene.blend','--manifest',d/'manifest.json','--report',d/'reopen.json')
        report=read(d/'reopen.json');need(report['status']=='PASS' and report['variant']==mode,f'{mode}: reopen failed')
        m=read(d/'manifest.json');m['source']='../source.png';(d/'manifest.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    # Build from existing builder rather than hardcode its historical filename.
    from build_addon import build
    addon=build(); staging=work/'archives';staging.mkdir();shutil.copyfile(addon,staging/ARCHIVES[0])
    zip_files(staging/ARCHIVES[1],example_entries(base,example))
    zip_files(staging/ARCHIVES[2],gallery_entries(gallery))
    zip_files(staging/ARCHIVES[3],qa_entries(gallery))
    need(git('rev-parse','HEAD')==commit and not git('status','--porcelain'),'Repository changed during build')
    manifest={'schema':'bvt.release.v1','version':a.version,'commit':commit,'blender':version,'example':'freezer_planogram','source_sha256':example['manifest']['source']['sha256'],'scenes_rendered':13,'scenes_reopened':13,'water_null_pass':7,'archives':[{ 'name':n,'bytes':(staging/n).stat().st_size,'sha256':sha(staging/n)} for n in ARCHIVES], 'limitations':'Synthetic fixture, not validated real photographs or YOLO gains. No dataset labels. Redistribution permission must be confirmed before publication.'}
    (staging/'release_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (staging/'SHA256SUMS.txt').write_text(''.join(f"{x['sha256']}  {x['name']}\n" for x in manifest['archives']),encoding='utf-8')
    out.parent.mkdir(parents=True,exist_ok=True);staging.rename(out)
    print('RELEASE_BUILD=PASS\nRELEASE_OUTPUT='+str(out))
if __name__=='__main__':main()
