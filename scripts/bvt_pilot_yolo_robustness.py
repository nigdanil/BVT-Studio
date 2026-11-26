"""Exploratory paired YOLOE robustness pilot; fixed CPU operating point.

Uses the accepted 210-frame QA and clean preflight configuration. No training,
no modification to dataset, no re-tuning on corrupted images.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import time
import zipfile

import bvt_pilot_model_preflight as pre

ROOT = pre.REPO / 'data_local' / 'research_runs'
CONF = 0.05
SIDS = tuple(f'{i:04d}' for i in range(1, 11))
CONDITIONS = ('00_clean',) + tuple(
    f'{family}_{level:03d}' for family in (
        '01_condensation', '02_droplets', '03_frost', '04_reflection', '05_dirt'
    ) for level in (25, 50, 75, 100))
EXPECTED_OPTIONS = dict(imgsz=960, conf=0.001, iou=0.7, max_det=300,
                        device='cpu', half=False, augment=False, verbose=False,
                        save=False, agnostic_nms=False, rect=True)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_inputs(run, qa, baseline):
    clean = pre.load_clean(run, qa)
    config = pre.read_json(baseline / 'model_config.json')
    summary = pre.read_json(baseline / 'summary.json')
    require(config.get('model') == 'yoloe' and config.get('prompt') == pre.PROMPT
            and config.get('class_map') == {'0': 'ice_cream'}
            and config.get('options') == EXPECTED_OPTIONS
            and config.get('match_iou') == 0.5 and config.get('report_conf') == 0.25
            and summary.get('status') == 'COMPLETE' and summary.get('model') == 'yoloe',
            'Expected completed original CPU YOLOE preflight')
    require(config['qa_sha256'] == pre.sha(qa / 'qa_summary.json') and
            config['qa_metrics_sha256'] == pre.sha(qa / 'metrics.csv'),
            'QA changed since model preflight')
    by_id = {s['id']: s for s in clean}
    old_predictions = {}
    for sid in SIDS:
        d = pre.read_json(baseline / 'predictions' / f'scene_{sid}.json')
        s = by_id[sid]
        require(d['scene'] == sid and d['image_sha256'] == s['image_sha256'] and
                d['label_sha256'] == s['label_sha256'] and d['gt'] == s['gt'],
                f'{sid}: clean preflight provenance mismatch')
        validate_predictions(d['predictions'])
        old_predictions[sid] = d['predictions']
    old_ap = aggregate([(by_id[sid]['gt'], old_predictions[sid]) for sid in SIDS])['ap50']
    require(math.isclose(old_ap, summary['metrics']['ap50'], abs_tol=1e-12),
            'Preflight AP50 does not reproduce')
    with (qa / 'metrics.csv').open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    lookup = {(r['condition'], r['scene']): r for r in rows}
    require(len(rows) == len(lookup) == 210 and set(lookup) ==
            {(c, s) for c in CONDITIONS for s in SIDS}, 'Incomplete QA matrix')
    require(len({r['image_sha256'] for r in rows}) == 210, 'Duplicate image hashes')
    from PIL import Image
    jobs = []
    for condition in CONDITIONS:
        for sid in SIDS:
            row = lookup[condition, sid]
            stem = f'scene_{sid}'
            image = run / condition / 'images' / (stem + '.png')
            label = run / condition / 'labels' / (stem + '.txt')
            meta = pre.read_json(run / condition / 'metadata' / (stem + '.json'))
            ih, lh = pre.sha(image), pre.sha(label)
            s = by_id[sid]
            gt = pre.load_labels(label)
            require(ih == row['image_sha256'] == meta['image_sha256'] and
                    lh == row['label_sha256'] == meta['label_sha256'] == s['label_sha256']
                    and gt == s['gt'] and len(gt) == int(row['boxes']) == meta['boxes']
                    and meta['id'] == sid and meta['condition']['id'] == condition
                    and meta['geometry_unchanged'] is True and int(row['outside_changed_pixels']) == 0,
                    f'{condition}/{sid}: integrity or annotation mismatch')
            with Image.open(image) as im:
                require(im.size == (1672, 941), f'{condition}/{sid}: unexpected size')
                im.load()
            jobs.append(dict(id=sid, condition=condition, image=image, label=label, gt=gt,
                             image_sha256=ih, label_sha256=lh,
                             intensity=float(row['intensity']), rgb_delta=float(row['mean_abs_rgb_pct'])))
    return jobs, config, old_predictions


def validate_predictions(preds):
    require(isinstance(preds, list) and len(preds) <= 300, 'Invalid predictions count')
    for p in preds:
        a = p['xyxy']; score = p['score']
        require(p['class_id'] == 0 and len(a) == 4 and all(math.isfinite(v) and 0 <= v <= 1 for v in a)
                and a[2] > a[0] and a[3] > a[1] and math.isfinite(score) and 0 <= score <= 1,
                'Invalid predicted box or score')


def aggregate(pairs):
    """Pool predictions within condition, keeping matching image-local."""
    outcomes = []
    n = 0
    for gt, preds in pairs:
        n += len(gt)
        outcomes.extend(pre.match(gt, preds, pre.SCORE_FLOOR))
    metrics = pre.stats([r for r in outcomes if r[0] >= CONF], n)
    metrics['ap50'] = pre.ap50(outcomes, n)
    return metrics


def matched_ids(gt, preds):
    """Stable ground-truth row indices under the same greedy matching rule."""
    remaining = set(range(len(gt)))
    for p in sorted(preds, key=lambda p: -p['score']):
        if p['score'] < CONF:
            continue
        j = max(sorted(remaining), key=lambda k: pre.iou(gt[k], p['xyxy']), default=None)
        if j is not None and pre.iou(gt[j], p['xyxy']) >= pre.MATCH_IOU:
            remaining.remove(j)
    return set(range(len(gt))) - remaining


def summarize(jobs, predictions):
    per_scene, conditions = [], []
    clean_metrics = {}
    clean_hits = {}
    for c in CONDITIONS:
        selected = [s for s in jobs if s['condition'] == c]
        require(len(selected) == 10, f'{c}: expected 10 scenes')
        pairs = []
        lost = gained = 0
        for s in selected:
            sid = s['id']; preds = predictions[c, sid]
            metrics = aggregate([(s['gt'], preds)])
            hits = matched_ids(s['gt'], preds)
            require(len(hits) == metrics['tp'], 'Matching inconsistency')
            if c == '00_clean':
                clean_metrics[sid] = metrics
                clean_hits[sid] = hits
            base = clean_metrics[sid]
            l = len(clean_hits[sid] - hits); g = len(hits - clean_hits[sid])
            lost += l; gained += g
            per_scene.append(dict(condition=c, scene=sid, intensity=s['intensity'],
                                  rgb_delta=s['rgb_delta'], **metrics,
                                  delta_ap50=metrics['ap50']-base['ap50'],
                                  delta_recall=metrics['recall']-base['recall'],
                                  lost_clean_tp=l, gained_tp=g))
            pairs.append((s['gt'], preds))
        m = aggregate(pairs)
        if c == '00_clean':
            baseline = m.copy()
        conditions.append(dict(condition=c, intensity=selected[0]['intensity'], scenes=10,
                               **m, delta_ap50=m['ap50']-baseline['ap50'],
                               delta_recall=m['recall']-baseline['recall'],
                               lost_clean_tp=lost, gained_tp=gained))
    return conditions, per_scene


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def run(args):
    run_dir, qa, base, out = (p.resolve() for p in (args.run, args.qa, args.baseline, args.output))
    require(not out.exists() and not out.with_suffix('.zip').exists() and
            all(out != x and x not in out.parents and out not in x.parents for x in (run_dir, qa, base)),
            'Output must be new and separate from inputs')
    jobs, config, old = load_inputs(run_dir, qa, base)
    print(f'Verified {len(jobs)} images | {len(CONDITIONS)} conditions | 10 scenes')
    print(f'YOLOE CPU | {config["prompt"]!r} | confidence={CONF} | IoU=0.5')
    if not args.execute:
        print('DRY RUN: no model loaded or output written'); return
    import torch
    import ultralytics
    require(torch.__version__ == config['torch'] and ultralytics.__version__ == config['ultralytics'],
            'Environment changed since preflight; do not mix model runs')
    weights = args.weights.resolve()
    require(weights.is_file() and pre.sha(weights) == config['weights_sha256'], 'Checkpoint hash mismatch')
    model = ultralytics.YOLOE(str(weights))
    model.set_classes([config['prompt']], model.get_text_pe([config['prompt']]))
    out.mkdir(parents=True, exist_ok=False)
    (out / 'predictions').mkdir()
    pre.write_json(out / 'model_config.json', dict(preflight=config, report_conf=CONF,
        preflight_config_sha256=pre.sha(base/'model_config.json'),
        benchmark_script_sha256=pre.sha(Path(__file__).resolve()),
        preflight_helper_sha256=pre.sha(Path(pre.__file__).resolve()),
        scope='exploratory paired pilot; operating point selected on clean scenes'))
    predictions = {}; elapsed = []
    for s in jobs:
        c, sid = s['condition'], s['id']
        t = time.perf_counter()
        results = model.predict(source=str(s['image']), **EXPECTED_OPTIONS)
        require(len(results) == 1, f'{c}/{sid}: expected one prediction result')
        preds = pre.predictions_from_result(results[0]); validate_predictions(preds)
        elapsed.append(time.perf_counter()-t)
        predictions[c, sid] = preds
        folder = out / 'predictions' / c; folder.mkdir(exist_ok=True)
        pre.write_json(folder / f'scene_{sid}.json', dict(condition=c, scene=sid,
            image_sha256=s['image_sha256'], label_sha256=s['label_sha256'], gt=s['gt'], predictions=preds))
        if sid == '0010':
            m = aggregate([(j['gt'], predictions[c,j['id']]) for j in jobs if j['condition']==c])
            print(f'{c}: AP50={m["ap50"]:.4f} P={m["precision"]:.4f} R={m["recall"]:.4f}')
            if c == '00_clean':
                previous = aggregate([(j['gt'], old[j['id']]) for j in jobs if j['condition']==c])
                # Small numerical variation tolerated, no silent baseline drift.
                require(abs(m['ap50']-previous['ap50']) <= .005 and
                        abs(m['recall']-previous['recall']) <= .01 and
                        abs(m['precision']-previous['precision']) <= .01,
                        'Clean baseline changed; stop before artifact inference')
    for s in jobs:
        require(pre.sha(s['image']) == s['image_sha256'] and pre.sha(s['label']) == s['label_sha256'],
                'Input changed during inference')
    conditions, per_scene = summarize(jobs, predictions)
    write_csv(out/'conditions.csv', conditions); write_csv(out/'per_scene.csv', per_scene)
    report = dict(status='COMPLETE', model='yoloe', images=210, independent_scenes=10,
                  conditions=21, report_conf=CONF, score_floor=pre.SCORE_FLOOR,
                  inference_seconds=sum(elapsed), baseline=conditions[0],
                  results=conditions, limitations=[
                    'Exploratory synthetic-only pilot; threshold selected on these clean scenes',
                    'One model, one prompt, one seed pair; no population-level inference',
                    'AP50 is pooled single-class 101-point AP at score floor, not COCO mAP',
                    'Intensity is a generator parameter, not calibrated physical severity'])
    pre.write_json(out/'summary.json', report)
    archive = out.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p, p.relative_to(out).as_posix())
    print(f'COMPLETE: 210 images / 21 conditions | ZIP: {archive}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, default=ROOT/'pilot_001_full')
    p.add_argument('--qa', type=Path, default=ROOT/'pilot_001_full_qa')
    p.add_argument('--baseline', type=Path, default=ROOT/'pilot_001_preflight_yoloe_cpu')
    p.add_argument('--weights', type=Path, default=pre.REPO/'yoloe-11s-seg.pt')
    p.add_argument('--output', type=Path, default=ROOT/'pilot_001_yoloe_robustness_cpu')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true'); mode.add_argument('--execute', action='store_true')
    try: run(p.parse_args())
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
