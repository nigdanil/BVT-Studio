#!/usr/bin/env python3
"""Idempotent source integration for BVT Studio commit 8934f24 descendants.

Makes only small targeted edits to registered modules and existing UI.
No git operations, deletions, dataset mutations or binary file changes.
Review git diff after applying. Fail closed if anchor changed upstream.
"""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
EXPECTED=('feature/photorealistic-droplets-v05',)


def cmd(*argv):
    return subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()


def edit(path,transform):
    original=path.read_text(encoding='utf-8')
    new=transform(original)
    if new!=original:
        path.write_text(new,encoding='utf-8')
        print('PATCHED',path.relative_to(ROOT))
    else:
        print('ALREADY PATCHED',path.relative_to(ROOT))


def require_once(source,old,new):
    if new in source:return source
    if source.count(old)!=1:
        raise RuntimeError('Upstream anchor is absent/ambiguous: '+repr(old[:90]))
    return source.replace(old,new,1)


def init_patch(s):
    # Both references are on separate lines. Do not register modules twice.
    s=require_once(s,'from . import props, scene_tools,',
                   'from . import glass_v02_ui, props, scene_tools,')
    s=require_once(s,'realistic_atlas, optical_water, visual_quality_ui)\n',
                   'realistic_atlas, optical_water, visual_quality_ui, glass_v02_ui)\n')
    return s


def ui_patch(s):
    start=s.index('class BVTSTUDIO_PT_glass_artifacts(')
    end=s.index('class BVTSTUDIO_PT_annotations(',start)
    old=s[start:end]
    # UI bug: the mask status/details used the active object even if a Glass
    # Target was explicitly chosen via the panel. Fix only this panel.
    new=require_once(old,'selected = context.active_object',
                     'selected = settings.artifact_target_glass or context.active_object')
    return s[:start]+new+s[end:]


def optics_patch(s):
    replacements=[
        ("'MULTIPLY', highlight, const=.095)",
         "'MULTIPLY', highlight, const=(.19 if obj.get('bvt_optical_stress_test', False) else .095))"),
        ("'MINIMUM', highlight, const=.16)",
         "'MINIMUM', highlight, const=(.28 if obj.get('bvt_optical_stress_test', False) else .16))"),
        ("'MULTIPLY', shade, const=.070)",
         "'MULTIPLY', shade, const=(.14 if obj.get('bvt_optical_stress_test', False) else .070))"),
        ("'MINIMUM', shade, const=.10)",
         "'MINIMUM', shade, const=(.19 if obj.get('bvt_optical_stress_test', False) else .10))"),
        ("'MINIMUM', micro, const=.025)",
         "'MINIMUM', micro, const=(.06 if obj.get('bvt_optical_stress_test', False) else .025))"),
    ]
    for old,new in replacements:
        s=require_once(s,old,new)
    return s


def main():
    try:
        branch=cmd('git','branch','--show-current')
        head=cmd('git','rev-parse','--short','HEAD')
        status=cmd('git','status','--short')
    except Exception as exc:
        raise SystemExit('Run inside Git repository: '+str(exc))
    if branch not in EXPECTED:
        raise SystemExit('Refusing to patch branch '+repr(branch)+'; expected feature/photorealistic-droplets-v05')
    is_ancestor=subprocess.run(['git','merge-base','--is-ancestor','8934f24','HEAD'],cwd=ROOT).returncode==0
    if not is_ancestor:
        raise SystemExit('Refusing to patch: HEAD is not descendant of 8934f24')
    required=['bvt_studio/water_effects_v02.py','bvt_studio/glass_v02_ui.py']
    if any(not (ROOT/p).is_file() for p in required):
        raise SystemExit('Extract ZIP into repo root first (missing v02 module)')
    print('Branch:',branch,'HEAD:',head)
    print('Uncommitted before patch:',status[:500] if status else '(none)')
    # Precompute ALL changes before writing a single modified file.
    edits=[(ROOT/'bvt_studio'/'__init__.py',init_patch),
           (ROOT/'bvt_studio'/'ui.py',ui_patch),
           (ROOT/'bvt_studio'/'optical_water.py',optics_patch)]
    proposals=[]
    for path,func in edits:
        old=path.read_text(encoding='utf-8')
        new=func(old)
        compile(new,str(path),'exec')
        proposals.append((path,old,new))
    for path,old,new in proposals:
        if old!=new:
            path.write_text(new,encoding='utf-8')
            print('PATCHED',path.relative_to(ROOT))
        else:
            print('ALREADY PATCHED',path.relative_to(ROOT))
    print('PATCH_SOURCE=OK')
    print('Please run blender tests and gallery before committing.')

if __name__=='__main__':main()
