"""Clean-only, zero-shot detector preflight for BVT Research Pilot 001.

No Blender, no training, no modifications to dataset. Explicit execution only.
AP50 is a single-class, 101-point interpolated exploratory measure, not COCO mAP.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
import zipfile

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN = REPO / 'data_local' / 'research_runs' / 'pilot_001_full'
DEFAULT_QA = REPO / 'data_local' / 'research_runs' / 'pilot_001_full_qa'
MODELS = {'world': 'yolov8s-worldv2.pt', 'yoloe': 'yoloe-11s-seg.pt'}
PROMPT = 'ice cream package'
SCORE_FLOOR = 0.001
CONF = 0.25
NMS_IOU = 0.7
MATCH_IOU = 0.5
MAX_DET = 300
IMGSZ = 960
EXPECTED_COUNTS = [25, 31, 31, 28, 26, 29, 32, 27, 27, 29]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def load_labels(path):
    boxes = []
    for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5 or fields[0] != '0':
            raise ValueError(f'{path}:{n}: expected single class 0')
        x, y, w, h = map(float, fields[1:])
        a = [x-w/2, y-h/2, x+w/2, y+h/2]
        if not all(math.isfinite(v) for v in a) or w <= 0 or h <= 0 or min(a) < -1e-6 or max(a) > 1+1e-6:
            raise ValueError(f'{path}:{n}: invalid box')
        boxes.append([max(0., min(1., v)) for v in a])
    return boxes


def load_clean(run, qa):
    summary = read_json(qa / 'qa_summary.json')
    if (summary.get('status') != 'PASS' or summary.get('offline') is not False or
            summary.get('images_verified') != 210 or summary.get('source_boxes') != 285 or
            summary.get('scenes_passed') != 10 or summary.get('failures')):
        raise ValueError('Expected locally verified PASS QA for 10 scenes / 210 images / 285 boxes')
    with (qa / 'metrics.csv').open(encoding='utf-8', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['condition'] == '00_clean']
    if len(rows) != 10 or {r['scene'] for r in rows} != {f'{i:04d}' for i in range(1,11)}:
        raise ValueError('Expected exactly ten clean QA rows')
    by_id = {r['scene']: r for r in rows}
    samples = []
    from PIL import Image
    for i, expected in enumerate(EXPECTED_COUNTS, 1):
        sid = f'{i:04d}'
        image = run / '00_clean' / 'images' / f'scene_{sid}.png'
        label = run / '00_clean' / 'labels' / f'scene_{sid}.txt'
        meta = read_json(run / '00_clean' / 'metadata' / f'scene_{sid}.json')
        ih, lh = sha(image), sha(label)
        row = by_id[sid]
        if (ih != row['image_sha256'] or lh != row['label_sha256'] or
                ih != meta['image_sha256'] or lh != meta['label_sha256'] or
                meta['id'] != sid or meta['condition']['id'] != '00_clean' or
                meta['geometry_unchanged'] is not True):
            raise ValueError(f'{sid}: provenance mismatch')
        with Image.open(image) as im:
            im.load()
            if im.size != (1672,941):
                raise ValueError(f'{sid}: unexpected size {im.size}')
        boxes = load_labels(label)
        if len(boxes) != expected or len(boxes) != int(row['boxes']) or len(boxes) != meta['boxes']:
            raise ValueError(f'{sid}: incorrect count')
        samples.append(dict(id=sid, image=image, label=label, image_sha256=ih, label_sha256=lh, gt=boxes))
    return samples


def iou(a, b):
    intersection = max(0., min(a[2],b[2])-max(a[0],b[0])) * max(0., min(a[3],b[3])-max(a[1],b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0.


def match(gt, predictions, conf=0.):
    """Greedy one-to-one matching in score order; fixed IoU 0.5."""
    remaining = set(range(len(gt)))
    outcomes = []
    for p in sorted(predictions, key=lambda p: -p['score']):
        if p['score'] < conf:
            continue
        j = max(sorted(remaining), key=lambda k: iou(gt[k], p['xyxy']), default=None)
        hit = j is not None and iou(gt[j], p['xyxy']) >= MATCH_IOU
        if hit:
            remaining.remove(j)
        outcomes.append((p['score'], bool(hit)))
    return outcomes


def ap50(outcomes, n_gt):
    if n_gt <= 0:
        raise ValueError('No reference boxes')
    tp = 0
    points = []
    for n, (_, hit) in enumerate(sorted(outcomes, key=lambda r: -r[0]), 1):
        tp += int(hit)
        points.append((tp/n_gt, tp/n))
    return sum(max((p for r,p in points if r >= k/100), default=0.) for k in range(101))/101


def stats(outcomes, n_gt):
    tp = sum(int(hit) for _,hit in outcomes)
    fp = len(outcomes)-tp
    fn = n_gt-tp
    precision = tp/(tp+fp) if tp+fp else 0.
    recall = tp/n_gt if n_gt else 0.
    return dict(gt=n_gt, predicted=len(outcomes), tp=tp, fp=fp, fn=fn,
                precision=precision, recall=recall,
                f1=2*precision*recall/(precision+recall) if precision+recall else 0.)


def predictions_from_result(result):
    if result.boxes is None:
        raise RuntimeError('Detector did not return boxes')
    out = []
    for xyxy, score, cls in zip(result.boxes.xyxyn.cpu().tolist(), result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist()):
        if cls != 0 or not math.isfinite(score) or not 0 <= score <= 1 or len(xyxy) != 4 or not all(math.isfinite(v) for v in xyxy):
            raise ValueError('Invalid detector result; expected single class 0')
        x1,y1,x2,y2 = (max(0.,min(1.,float(v))) for v in xyxy)
        if x2 <= x1 or y2 <= y1:
            raise ValueError('Degenerate predicted box')
        out.append(dict(xyxy=[x1,y1,x2,y2], score=float(score), class_id=0))
    return out


def overlay(sample, predictions, target):
    from PIL import Image, ImageDraw
    with Image.open(sample['image']) as source:
        im = source.convert('RGB')
    im.thumbnail((1100, 800))
    draw = ImageDraw.Draw(im)
    w,h = im.size
    for box in sample['gt']:
        draw.rectangle([box[0]*w,box[1]*h,box[2]*w,box[3]*h], outline='#00ff78', width=2)
    for p in predictions:
        if p['score'] >= CONF:
            a=p['xyxy']; rect=[a[0]*w,a[1]*h,a[2]*w,a[3]*h]
            draw.rectangle(rect, outline='#ff6060', width=2)
            draw.text((rect[0], max(0,rect[1]-12)), f"{p['score']:.2f}", fill='#ff6060', stroke_width=1, stroke_fill='black')
    im.save(target, quality=83)


def run(args):
    samples = load_clean(args.run.resolve(), args.qa.resolve())
    out = args.output.resolve()
    # Restrict outputs to a new sibling directory, never a dataset descendant.
    dataset = args.run.resolve(); qa = args.qa.resolve()
    if out == dataset or dataset in out.parents or out == qa or qa in out.parents or out.exists() or out.with_suffix('.zip').exists():
        raise ValueError('Output must be new, outside dataset and QA directories')
    print(f'Clean samples: {len(samples)} | GT: {sum(len(s["gt"]) for s in samples)}')
    print(f'Model: {args.model} | Prompt: {PROMPT!r} | device={args.device} | imgsz={IMGSZ}')
    if not args.execute:
        print('DRY RUN: verified local input, no model loaded, no output written')
        return
    import torch
    import ultralytics
    if args.device == '0' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable. Install matching CUDA PyTorch or explicitly use --device cpu')
    weights = args.weights or MODELS[args.model]
    # Official Ultralytics checkpoints only by default; custom local weights must be trusted.
    model = (ultralytics.YOLOWorld(weights) if args.model == 'world' else ultralytics.YOLOE(weights))
    if args.model == 'world':
        model.set_classes([PROMPT])
    else:
        model.set_classes([PROMPT], model.get_text_pe([PROMPT]))
    # The loader resolves downloaded checkpoint paths; verify the actual bytes.
    weight_path = Path(str(getattr(model, 'ckpt_path', None) or weights)).resolve()
    if not weight_path.is_file():
        raise RuntimeError(f'Cannot fingerprint checkpoint: {weight_path}')
    options = dict(imgsz=IMGSZ, conf=SCORE_FLOOR, iou=NMS_IOU, max_det=MAX_DET,
                   device=args.device, half=False, augment=False, verbose=False, save=False,
                   agnostic_nms=False, rect=True)
    metadata = dict(model=args.model, checkpoint=weight_path.name, weights_sha256=sha(weight_path),
                    prompt=PROMPT, class_map={'0':'ice_cream'}, options=options, report_conf=CONF,
                    match_iou=MATCH_IOU, ap_method='single-class 101-point AP50 at score floor',
                    torch=torch.__version__, ultralytics=ultralytics.__version__, cuda=torch.version.cuda,
                    gpu=torch.cuda.get_device_name(0) if args.device=='0' else None,
                    python=platform.python_version(), platform=platform.platform(),
                    qa_sha256=sha(qa/'qa_summary.json'), qa_metrics_sha256=sha(qa/'metrics.csv'),
                    script_sha256=sha(Path(__file__).resolve()), scope='clean-only exploratory; no training')
    out.mkdir(parents=True, exist_ok=False)
    (out/'previews').mkdir(); (out/'predictions').mkdir()
    write_json(out/'model_config.json',metadata)
    all_fixed, all_scores, scene_rows = [], [], []
    for s in samples:
        t = time.perf_counter()
        results = model.predict(source=str(s['image']), **options)
        if len(results)!=1:
            raise RuntimeError(f'{s["id"]}: expected one result')
        preds=predictions_from_result(results[0]); elapsed=time.perf_counter()-t
        a=match(s['gt'],preds,CONF); b=match(s['gt'],preds,SCORE_FLOOR)
        all_fixed.extend(a); all_scores.extend(b)
        row=dict(scene=s['id'],**stats(a,len(s['gt'])),ap50=ap50(b,len(s['gt'])),seconds=elapsed)
        scene_rows.append(row)
        write_json(out/'predictions'/f'scene_{s["id"]}.json',dict(scene=s['id'], image_sha256=s['image_sha256'],label_sha256=s['label_sha256'],gt=s['gt'],predictions=preds))
        overlay(s,preds,out/'previews'/f'scene_{s["id"]}.jpg')
        print(f'{s["id"]}: GT={row["gt"]} pred={row["predicted"]} TP={row["tp"]} FP={row["fp"]} FN={row["fn"]} recall={row["recall"]:.3f}')
    for s in samples:
        if sha(s['image']) != s['image_sha256'] or sha(s['label']) != s['label_sha256']:
            raise RuntimeError('Dataset changed during inference')
    overall=stats(all_fixed,sum(len(s['gt']) for s in samples)); overall['ap50']=ap50(all_scores,overall['gt'])
    report=dict(status='COMPLETE',model=args.model,scenes=len(samples),metrics=overall,
                heuristic_screen=dict(precision_min=0.5,recall_min=0.4,
                    passed=overall['precision']>=0.5 and overall['recall']>=0.4,
                    note='Provisional engineering screen, not a statistical or publication criterion'),
                limitations=['10 synthetic scenes; not independent of later artifact pairs', 'AP50 is not COCO mAP50-95', 'Screening on clean test scenes is exploratory model selection', 'Not a measurement of robustness'])
    write_json(out/'summary.json',report)
    with (out/'per_scene.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(scene_rows[0]));w.writeheader();w.writerows(scene_rows)
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(out.rglob('*')):
            if path.is_file(): z.write(path,path.relative_to(out).as_posix())
    print(json.dumps(report,indent=2));print(f'QA ZIP: {archive}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,default=DEFAULT_RUN); p.add_argument('--qa',type=Path,default=DEFAULT_QA)
    p.add_argument('--model',choices=MODELS,required=True);p.add_argument('--weights',help='Trusted checkpoint path, optional')
    p.add_argument('--device',choices=['0','cpu'],default='cpu')
    p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--dry-run',action='store_true');mode.add_argument('--execute',action='store_true')
    args=p.parse_args()
    try:run(args)
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr);return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
