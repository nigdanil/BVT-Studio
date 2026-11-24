#!/usr/bin/env python3
"""Dataset Runner v0.1 / step 1: deterministic, unlabeled example rendering."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

from validate_examples import ROOT, MODES, read, sha, need, png_size, validate

DEFAULT_EFFECTS = ('07_macro_droplets_only', '10_combined_water_optics')
NORMAL_EFFECTS = MODES[1:-1]  # Clean is mandatory; stress is not training data.
SCHEMA = 'bvt.dataset-run.v01'


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def make_plan(example, gallery, effects, count, seed):
    """Pure planner. Matched replicate seeds across effects are intentional."""
    rects = example['rects']
    need(type(count) is int and 1 <= count <= 100, 'count must be 1..100 per effect')
    need(bool(effects) and len(set(effects)) == len(effects) and set(effects) <= set(NORMAL_EFFECTS), 'Choose unique normal effects; clean is automatic and stress is excluded')
    need(type(seed) is int and 0 <= seed and seed + count*len(rects)-1 < 2**31, 'Seed range exceeds Blender limit')
    need(gallery.get('schema') == 'bvt.glass-gallery.v02', 'Wrong gallery schema')
    variants = gallery['variants']
    need(set(('00_clean', *effects)) <= set(variants), 'Effect not in example gallery')
    need(example['manifest'].get('labels') is None, 'Step 1 accepts unlabeled example only')
    jobs, resolved = [], {}
    def add(job_id, effect, replicate, base_seed):
        spec = copy.deepcopy(variants[effect])
        need(not spec.get('pane_overrides'), 'Step 1 does not accept pane overrides')
        need(not spec.get('stress'), 'Stress preset excluded from dataset pilot')
        spec['seed_base'] = base_seed
        resolved[job_id] = spec
        jobs.append({'id': job_id, 'effect': effect, 'replicate': replicate,
                     'seed_base': base_seed, 'pane_seeds': [base_seed+i for i in range(len(rects))],
                     'render': f'gallery/{job_id}/render.png', 'manifest': f'gallery/{job_id}/manifest.json',
                     'control': None if effect == '00_clean' else '00_clean',
                     'source_group': example['manifest']['source']['sha256'], 'labels': None})
    add('00_clean', '00_clean', 0, seed)
    for effect in sorted(effects):
        for replicate in range(1, count+1):
            add(f'{effect}__r{replicate:04d}', effect, replicate, seed + (replicate-1)*len(rects))
    plan = {'schema': SCHEMA, 'example': example['manifest']['id'], 'source': example['manifest']['source'],
            'rectangles': rects, 'seed': seed, 'count_per_effect': count, 'effects': sorted(effects),
            'jobs': jobs, 'labels_status': 'UNLABELED', 'severity_status': 'NATIVE_PRESET_NOT_CALIBRATED',
            'mask_provenance': 'synthetic_geometry_not_ground_truth',
            'seed_policy': 'same replicate seed block across effects; consecutive per-pane seeds',
            'warning': 'All renders derive from one source; not independent observations or a YOLO training dataset.'}
    return plan, {'schema': 'bvt.glass-gallery.v02', 'variants': resolved}


def input_snapshot(example, root):
    paths = [example['image'], *example['configs'].values(), *example['assets'], *example['extra_files'],
             root/'examples'/example['manifest']['id']/'manifest.json',
             root/'scripts/bvt_dataset_runner.py', root/'scripts/bvt_glass_effect_gallery_v02.py',
             root/'scripts/blender_release_reopen.py', root/'scripts/validate_examples.py',
             *sorted((root/'bvt_studio').rglob('*.py'))]
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(set(paths))}


def output_path(root, path):
    base = root/'qa_renders'
    target = path if path.is_absolute() else root/path
    need(target.resolve().is_relative_to(base.resolve()) and target.resolve() != base.resolve(), 'Output must be a new subdirectory of qa_renders')
    need(not base.is_symlink(), 'qa_renders must not be a symlink')
    relative = target.resolve().relative_to(base.resolve())
    for i in range(1, len(relative.parts)+1):
        need(not base.joinpath(*relative.parts[:i]).is_symlink(), 'Output symlinks forbidden')
    need(not target.exists() and not target.is_symlink(), 'Output already exists; choose a new run directory')
    # Resolve after rejecting aliases through the supplied path.
    need(target.absolute() == target.resolve(), 'Output must use a direct, canonical path')
    return target.resolve()


def check_render(gallery_root, job, plan, variant):
    d = gallery_root/job['id']
    m = read(d/'manifest.json')
    need(m.get('schema') == 'bvt.glass-gallery.v02' and m.get('variant') == job['id'], 'Wrong variant manifest')
    need(m.get('source_sha256') == plan['source']['sha256'] and m.get('rects') == plan['rectangles'], 'Source/geometry changed')
    need(m.get('mask_provenance') == plan['mask_provenance'], 'Wrong mask provenance')
    need(png_size(d/'render.png') == (plan['source']['width'], plan['source']['height']), 'Wrong render dimensions')
    need((d/'scene.blend').stat().st_size > 0, 'Missing scene')
    panes = m['panes']
    need([p['name'] for p in panes] == [f'Glass_p_{i+1:03d}' for i in range(len(job['pane_seeds']))], 'Wrong panes')
    need([p['seed'] for p in panes] == job['pane_seeds'], 'Wrong pane seeds')
    water = variant.get('water')
    need(all(p['preset'] == variant['preset'] and p.get('water_kind') == (water.get('kind','COMBINED') if water else None) for p in panes), 'Wrong pane preset')
    if job['control']:
        q = m.get('quality')
        need(isinstance(q, dict) and q.get('leakage_pixels_beyond_3px_geometry_guard') == 0, 'Missing QA or geometry guard leakage')
        need(isinstance(q.get('changed_ratio_in_rects'), (int,float)) and 0 <= q['changed_ratio_in_rects'] <= 1, 'Invalid QA change ratio')
    else:
        need(m.get('quality') is None, 'Unexpected baseline QA')
    if water:
        n = m.get('zero_water_test') or {}
        need(n.get('status') == 'PASS' and n.get('changed_pixels_gt_4_255') == 0 and n.get('same_shader_topology') is True and n.get('same_renderer_controls') is True, 'Water null control failed')
        for name in ('preset_without_water.png','zero_water_rebuild.png'):
            need(png_size(d/name) == (plan['source']['width'], plan['source']['height']), 'Invalid water control dimensions')
    return m


def run(argv, cwd, log):
    with log.open('w', encoding='utf-8') as f:
        result = subprocess.run([str(x) for x in argv], cwd=cwd, stdout=f, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(encoding='utf-8', errors='replace')[-4000:], flush=True)
        raise RuntimeError(f'Blender failed ({result.returncode}); see {log}')


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == 'research':
        from run_research_dataset import main as research_main
        return research_main(args[1:])
    p = argparse.ArgumentParser(description=__doc__, epilog='Research mode: bvt_dataset_runner.py research --help')
    p.add_argument('--example', default='freezer_planogram', choices=['freezer_planogram'])
    p.add_argument('--effects', nargs='+', default=DEFAULT_EFFECTS, choices=NORMAL_EFFECTS)
    p.add_argument('--count', type=int, default=2, help='Replicates per effect, plus one clean control')
    p.add_argument('--seed', type=int, default=72)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--blender', type=Path)
    p.add_argument('--dry-run', action='store_true', help='Write plan only; no render, no Blender needed')
    a = p.parse_args(argv)
    if not a.dry_run:
        need(a.blender is not None and a.blender.is_file(), 'Provide --blender executable')
    out = output_path(ROOT, a.output_dir)
    e = validate(ROOT/'examples'/a.example)
    plan, variants = make_plan(e, read(e['configs']['gallery']), a.effects, a.count, a.seed)
    snapshot = input_snapshot(e, ROOT)
    plan['input_sha256'] = snapshot
    out.mkdir(parents=True, exist_ok=False)
    config = out/'resolved_gallery.json'
    write_json(config, variants)
    plan['resolved_gallery_sha256'] = sha(config)
    write_json(out/'plan.json', plan)
    print(f"RUN_PLAN={len(plan['jobs'])} JOBS; LABELS=UNLABELED", flush=True)
    if a.dry_run:
        print('DATASET_RUNNER=PLAN_ONLY', flush=True)
        return 0
    gallery = out/'gallery'; gallery.mkdir()
    logs = out/'logs'; logs.mkdir()
    shutil.copyfile(e['image'], gallery/'source.png')
    report = {'schema': SCHEMA, 'status':'RUNNING', 'planned':len(plan['jobs']), 'jobs':[], 'labels_status':'UNLABELED'}
    write_json(out/'run_report.json', report)
    try:
        for job in plan['jobs']:
            jid = job['id']; d = gallery/jid
            print('RUN_JOB='+jid, flush=True)
            base = [a.blender.resolve(), '--background', '--factory-startup', '--python-exit-code', '1', '--python']
            run([*base, ROOT/'scripts/bvt_glass_effect_gallery_v02.py', '--', '--repo', ROOT,
                 '--photo', e['image'], '--output', gallery, '--rects-file', e['configs']['rectangles'],
                 '--config', config, '--mode', jid], ROOT, logs/(jid+'.render.log'))
            m = check_render(gallery, job, plan, variants['variants'][jid])
            run([*base, ROOT/'scripts/blender_release_reopen.py', '--', '--blend', d/'scene.blend',
                 '--manifest', d/'manifest.json', '--report', d/'reopen.json'], ROOT, logs/(jid+'.reopen.log'))
            reopen = read(d/'reopen.json')
            need(reopen.get('status') == 'PASS' and reopen.get('variant') == jid, 'Reopen check failed')
            m['source'] = '../source.png'
            write_json(d/'manifest.json', m)
            row = {'id':jid, 'status':'PASS', 'render_sha256':sha(d/'render.png'),
                   'scene_sha256':sha(d/'scene.blend'), 'manifest_sha256':sha(d/'manifest.json'),
                   'quality':m.get('quality'), 'zero_water_test':m.get('zero_water_test')}
            report['jobs'].append(row)
            write_json(out/'run_report.json', report)
            print('JOB_PASS='+jid, flush=True)
        need(input_snapshot(e, ROOT) == snapshot and sha(config) == plan['resolved_gallery_sha256'], 'Inputs changed during run')
        need(sha(gallery/'source.png') == plan['source']['sha256'], 'Source copy changed')
        report['status'] = 'PASS'
    except (Exception, KeyboardInterrupt) as exc:
        report['status'] = 'ERROR'
        report['error'] = str(exc)
        write_json(out/'run_report.json', report)
        raise
    write_json(out/'run_report.json', report)
    print(f"DATASET_RUNNER=PASS {len(report['jobs'])}/{report['planned']}", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
