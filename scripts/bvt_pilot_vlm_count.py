"""Local, exploratory VLM counting on the accepted BVT Pilot 001 matrix."""
import argparse
import base64
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import time
import urllib.request
import zipfile

import bvt_pilot_model_preflight as pre
import bvt_pilot_yolo_robustness as robust

ROOT = robust.ROOT
MODEL = 'qwen2.5vl:3b'
URL = 'http://127.0.0.1:11434'
PROMPT = ('Count the individual visible ice cream retail packages in this freezer image. '
          'Count each distinct package once, including partially visible packages if identifiable. '
          'Do not count the freezer, dividers, reflections or printed pictures on packages as separate items. '
          'Return only a JSON object with one nonnegative integer field named count.')
SCHEMA = {'type': 'object', 'properties': {'count': {'type': 'integer', 'minimum': 0}},
          'required': ['count'], 'additionalProperties': False}
OPTIONS = {'temperature': 0, 'seed': 42, 'num_ctx': 8192, 'num_predict': 128}


def require(ok, message):
    if not ok:
        raise ValueError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, body=None):
    # Local-only, no environment proxies, no redirects.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(URL + path, data=data, headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=600) as response:
        value = json.load(response)
    require(isinstance(value, dict) and not value.get('error'), 'Ollama returned an error')
    return value


def identity(model):
    rows = [r for r in request('/api/tags')['models'] if r.get('name') == model]
    require(len(rows) == 1, f'Install local model first: ollama pull {model}')
    row = rows[0]
    require(re.fullmatch(r'[0-9a-f]{64}', row.get('digest', '')) is not None, 'Missing model digest')
    return {'model': model, 'digest': row['digest'], 'details': row.get('details', {}),
            'ollama_version': request('/api/version')['version']}


def parse_count(response):
    if response.get('done') is not True or response.get('done_reason') != 'stop':
        return None, 'incomplete_response'
    try:
        def pairs(items):
            if len(dict(items)) != len(items):
                raise ValueError('duplicate key')
            return dict(items)
        d = json.loads(response['message']['content'], object_pairs_hook=pairs)
        if type(d) is dict and set(d) == {'count'} and type(d['count']) is int and d['count'] >= 0:
            return d['count'], 'ok'
    except (ValueError, KeyError, TypeError):
        pass
    return None, 'invalid_json_or_count'


def payload(model, data):
    return {'model': model, 'stream': False, 'format': SCHEMA, 'options': OPTIONS,
            'keep_alive': '10m', 'messages': [{'role': 'user', 'content': PROMPT,
                                             'images': [base64.b64encode(data).decode('ascii')]}]}


def summarize(rows):
    valid = [r for r in rows if r['count'] is not None]
    n = len(valid)
    errors = [r['count'] - r['gt'] for r in valid]
    return {'images': len(rows), 'valid': n, 'invalid': len(rows)-n,
            'exact': sum(e == 0 for e in errors), 'exact_rate_all': sum(e == 0 for e in errors)/len(rows),
            'mae_valid': sum(map(abs, errors))/n if n else None,
            'bias_valid': sum(errors)/n if n else None,
            'wape_valid': sum(map(abs,errors))/sum(r['gt'] for r in valid) if n else None}


def paired(rows, clean):
    pairs = [(r, clean[r['scene']]) for r in rows if r['count'] is not None and clean[r['scene']]['count'] is not None]
    deltas = [abs(r['count']-r['gt'])-abs(b['count']-b['gt']) for r,b in pairs]
    return {'paired_valid': len(pairs), 'paired_delta_mae': sum(deltas)/len(deltas) if deltas else None,
            'worse': sum(d>0 for d in deltas), 'better': sum(d<0 for d in deltas), 'same': sum(d==0 for d in deltas)}


def run(args):
    run_dir, qa, base, out = (p.resolve() for p in (args.run, args.qa, args.baseline, args.output))
    archive = out.with_suffix('.zip')
    require(out.suffix == '' and not out.exists() and not archive.exists() and
            all(out != x and x not in out.parents and out not in x.parents and
                archive != x and x not in archive.parents for x in (run_dir, qa, base)),
            'Output must be new and separate from inputs')
    jobs, _, _ = robust.load_inputs(run_dir, qa, base)
    if args.clean_only:
        jobs = [j for j in jobs if j['condition'] == '00_clean']
    random.Random(42).shuffle(jobs)
    print(f'Verified {len(jobs)} images | model={args.model} | local counting | clean_only={args.clean_only}')
    if not args.execute:
        print('DRY RUN: no model called, no files written'); return
    ident = identity(args.model)
    out.mkdir(parents=True, exist_ok=False)
    raw = out / 'responses'; raw.mkdir()
    config = {'identity': ident, 'prompt': PROMPT, 'schema': SCHEMA, 'options': OPTIONS,
              'order_seed': 42, 'order': [[j['condition'], j['id']] for j in jobs],
              'qa_sha256': pre.sha(qa/'qa_summary.json'), 'qa_metrics_sha256': pre.sha(qa/'metrics.csv'),
              'script_sha256': pre.sha(Path(__file__)), 'clean_only': args.clean_only}
    pre.write_json(out/'model_config.json', config)
    rows = []
    for i,j in enumerate(jobs,1):
        # Send only original image bytes and a constant prompt, never GT or artifact name.
        data = j['image'].read_bytes()
        require(hashlib.sha256(data).hexdigest() == j['image_sha256'], 'Image changed before inference')
        start = time.perf_counter()
        reply = request('/api/chat', payload(args.model, data))
        require(reply.get('model') == args.model, 'Unexpected response model')
        count, status = parse_count(reply)
        row = {'condition':j['condition'], 'scene':j['id'], 'image_sha256':j['image_sha256'],
               'label_sha256':j['label_sha256'], 'gt':len(j['gt']), 'count':count, 'status':status,
               'error': count-len(j['gt']) if count is not None else None,
               'seconds':time.perf_counter()-start}
        pre.write_json(raw/f"{j['condition']}__{j['id']}.json", {'result':row,'response':reply})
        rows.append(row)
        print(f"{i}/{len(jobs)} {j['condition']}/{j['id']}: GT={row['gt']} count={count} {status}", flush=True)
    require(identity(args.model) == ident, 'Model identity changed during run')
    for j in jobs:
        require(pre.sha(j['image']) == j['image_sha256'] and pre.sha(j['label']) == j['label_sha256'], 'Input changed during inference')
    require(pre.sha(qa/'qa_summary.json') == config['qa_sha256'] and pre.sha(qa/'metrics.csv') == config['qa_metrics_sha256'], 'QA changed during run')
    rows.sort(key=lambda r:(r['condition'],r['scene']))
    clean = {r['scene']:r for r in rows if r['condition']=='00_clean'}
    conditions = []
    for c in sorted({r['condition'] for r in rows}):
        selected = [r for r in rows if r['condition']==c]
        conditions.append({'condition':c, **summarize(selected), **paired(selected,clean)})
    robust.write_csv(out/'per_scene.csv',rows); robust.write_csv(out/'conditions.csv',conditions)
    report = {'status':'COMPLETE', 'images':len(rows), 'independent_scenes':10, 'results':conditions,
              'limitations':['Count accuracy is not detection AP or object correspondence.',
                             'One local quantized model, one prompt and one generation per image.',
                             'MAE excludes invalid responses; report coverage and exact rate over all images.',
                             'Synthetic-only exploratory pilot; generation seed is not a determinism guarantee.']}
    pre.write_json(out/'summary.json',report)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(out).as_posix())
    print(json.dumps(report,indent=2)); print(f'ZIP: {archive}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,default=ROOT/'pilot_001_full')
    p.add_argument('--qa',type=Path,default=ROOT/'pilot_001_full_qa')
    p.add_argument('--baseline',type=Path,default=ROOT/'pilot_001_preflight_yoloe_cpu')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',default=MODEL,choices=[MODEL])
    p.add_argument('--clean-only',action='store_true')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run',action='store_true'); mode.add_argument('--execute',action='store_true')
    try: run(p.parse_args())
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr); return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
