#!/usr/bin/env python3
"""Plan and run the experimental single-pane Material x Artifact Gallery."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = ('clear_glass', 'frosted_glass', 'tinted_glass', 'textured_glass', 'coated_glass', 'insulated_glass')
EFFECTS = ('00_clean','01_light_condensation','02_heavy_condensation','03_frost','04_dirty_glass','05_reflections','06_microbeads_only','07_macro_droplets_only','08_running_water_only','09_combined_water_no_optics','10_combined_water_optics','11_heavy_running_water','12_stress_optics','13_clean_glass')
PILOT_MATERIALS = MATERIALS[:3]
PILOT_EFFECTS = (EFFECTS[0], EFFECTS[7], EFFECTS[10])
SCHEMA = 'bvt.material-artifact-gallery.v01'
TARGET = 'Glass_p_001'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read_json(path):
    def unique(pairs):
        d = {}
        for key, value in pairs:
            need(key not in d, 'Duplicate JSON key: '+key)
            d[key] = value
        return d
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')


def material_validator(root):
    # This module is pure Python. Avoid importing the Blender-only package in the CLI.
    spec = importlib.util.spec_from_file_location('_bvt_matrix_material_contract', root/'bvt_studio/glass_material_config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_plan(root, blend, materials, effects, seed):
    root, blend = Path(root).resolve(), Path(blend).resolve()
    need(blend.is_file() and blend.suffix.lower()=='.blend', 'Expected an existing clean .blend file')
    need(type(seed) is int and 0<=seed<2**31, 'Seed outside Blender range')
    for name, values, allowed in [('materials',materials,MATERIALS),('effects',effects,EFFECTS)]:
        need(bool(values) and len(set(values))==len(values) and set(values)<=set(allowed), 'Invalid/duplicate '+name)
    # Both control axes are mandatory; use canonical order for reproducible plans.
    selected_m = [m for m in MATERIALS if m in materials or m=='clear_glass']
    selected_e = [e for e in EFFECTS if e in effects or e=='00_clean']
    example = root/'examples/freezer_planogram'
    manifest_path = example/'manifest.json'
    m = read_json(manifest_path)
    need(m['id']=='freezer_planogram' and m['schema']=='bvt.example.v1' and m.get('labels') is None, 'Expected unlabeled freezer example')
    original = (example/m['source']['path']).resolve()
    need(original.is_relative_to(example) and sha(original)==m['source']['sha256'], 'Example source hash mismatch')
    profiles = material_validator(root).load_library(root/'configs/glass_materials')
    preset_dir = example/'configs/presets/single_glass'
    catalog = list(preset_dir.rglob('*.json'))
    need(len(catalog)==len(EFFECTS) and {p.stem for p in catalog}==set(EFFECTS), 'Unexpected/missing single-glass preset')
    paths = {p.stem:p for p in catalog}
    resolved = {}
    for e in selected_e:
        raw = read_json(paths[e])
        need(raw.get('schema')=='bvt.glass-gallery.v02' and set(raw['glass'])=={TARGET}, 'Wrong preset schema or target: '+e)
        merged = {**raw.get('defaults',{}), **raw['glass'][TARGET]}
        need(bool(merged.get('stress', False)) == (e=='12_stress_optics'), 'Stress designation mismatch: '+e)
        if e=='00_clean':
            need(merged.get('preset')=='QA_TRANSPARENT' and not merged.get('water') and not (merged.get('optics') or {}).get('enabled'), 'Invalid transparent control')
        cfg = copy.deepcopy(raw)
        cfg['glass'][TARGET]['seed'] = seed
        resolved[e] = cfg
    jobs=[]
    for mat in selected_m:
        for effect in selected_e:
            job_id = mat+'__'+effect
            jobs.append({'id':job_id, 'material':mat, 'effect':effect,
                         'material_baseline':mat+'__00_clean', 'artifact_baseline':'clear_glass__'+effect,
                         'role':'QA_ONLY' if effect in ('00_clean','12_stress_optics','13_clean_glass') else 'EXPERIMENTAL',
                         'seed':seed})
    files = [manifest_path, original, *[root/'configs/glass_materials'/f'{x}.json' for x in selected_m], *[paths[x] for x in selected_e]]
    return {'schema':SCHEMA,'target':TARGET,'seed':seed,'input_blend_sha256':sha(blend),
            'source':m['source'],'materials':{x:profiles[x] for x in selected_m},'presets':resolved,
            'inputs':{p.relative_to(root).as_posix():sha(p) for p in files},'jobs':jobs,
            'labels_status':'UNLABELED','warning':'Synthetic 2.5D visual QA; not a training dataset or calibrated glass optics. Artifact deltas use transparent material-only controls, not matched-topology zero-water controls.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--blend',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--blender',type=Path)
    p.add_argument('--materials',nargs='+',choices=MATERIALS)
    p.add_argument('--effects',nargs='+',choices=EFFECTS)
    p.add_argument('--all',action='store_true',help='All 84 combinations, including QA-only controls')
    p.add_argument('--seed',type=int,default=72)
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(argv)
    try:
        need(not (a.all and (a.materials or a.effects)), '--all cannot combine with explicit selection')
        out=a.output_dir.resolve(); blend=a.blend.resolve()
        need(not out.exists() and not blend.is_relative_to(out), 'Choose a new output directory')
        blender=a.blender.resolve() if a.blender else None
        need(a.dry_run or (blender is not None and blender.is_file()), 'Specify the Blender executable')
        plan=make_plan(ROOT,blend,MATERIALS if a.all else (a.materials or PILOT_MATERIALS),EFFECTS if a.all else (a.effects or PILOT_EFFECTS),a.seed)
        out.mkdir(parents=True,exist_ok=False); write_json(out/'plan.json',plan)
        print(f'MATRIX_PLAN={len(plan["jobs"])} JOBS; LABELS=UNLABELED',flush=True)
        if a.dry_run:
            print('MATERIAL_ARTIFACT_GALLERY=PLAN_ONLY'); return 0
        args=[str(blender),'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'scripts/blender_material_artifact_gallery.py'),'--','--blend',str(blend),'--plan',str(out/'plan.json')]
        with (out/'blender.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
            for line in process.stdout:
                print(line,end='',flush=True); log.write(line); log.flush()
            code=process.wait()
        if code:
            print('MATERIAL_ARTIFACT_GALLERY=ERROR; BLENDER_EXIT='+str(code)); return 1
        report=read_json(out/'report.json')
        need([r['id'] for r in report['jobs']]==[j['id'] for j in plan['jobs']], 'Incomplete matrix report')
        need(report['status'] in ('PASS','REVIEW'), 'Invalid report status')
        print('MATERIAL_ARTIFACT_GALLERY='+report['status']); return 0 if report['status']=='PASS' else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('MATERIAL_ARTIFACT_GALLERY=ERROR: '+str(exc),file=sys.stderr); return 1


if __name__=='__main__':
    raise SystemExit(main())
