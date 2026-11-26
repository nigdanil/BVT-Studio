"""Independent post-render audit for BVT Research Pilot 001 (no Blender)."""
import argparse
import csv
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
CHANNELS = ('reflection', 'tint', 'haze', 'frost', 'droplets', 'dirt')
HEAVY = dict(reflection=.075, tint=.014, haze=.15, frost=.025, droplets=.35, dirt=.016)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def labels(path):
    result = []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        f = line.split()
        require(len(f) == 5 and f[0] == '0', 'Invalid class or YOLO row: ' + str(path))
        x,y,w,h = map(float,f[1:])
        require(all(map(math.isfinite,(x,y,w,h))) and w > 0 and h > 0 and
                x-w/2 >= -1e-6 and y-h/2 >= -1e-6 and x+w/2 <= 1+1e-6 and y+h/2 <= 1+1e-6,
                'Invalid YOLO bounds: ' + str(path))
        result.append((0,x,y,w,h))
    return result


def same_rows(a,b):
    b = list(b)
    for row in a:
        i = next((i for i,r in enumerate(b) if all(abs(x-y)<=1e-6 for x,y in zip(row,r))),None)
        if i is None:
            return False
        b.pop(i)
    return not b


def rgb(path, size):
    with Image.open(path) as im:
        require(im.format == 'PNG' and list(im.size) == size, 'PNG dimensions/format: '+str(path))
        im.verify()
    with Image.open(path) as im:
        return np.asarray(im.convert('RGB')).copy()


def outside_mask(ref):
    w,h = ref['resolution']
    mask = np.ones((h,w), dtype=bool)
    for g in ref['glass']:
        x0,y0,x1,y1 = g['camera_bounds']  # Blender NDC origin is bottom-left.
        left=max(0,math.floor(x0*w)-2); right=min(w,math.ceil(x1*w)+2)
        top=max(0,math.floor((1-y1)*h)-2); bottom=min(h,math.ceil((1-y0)*h)+2)
        mask[top:bottom,left:right]=False
    return mask


def validate_glass(meta,ref,c,seed):
    panes = meta['glass']
    require(len(panes)==2,'Expected two panes')
    require({(g['name'],g['uid']) for g in panes} == {(g['name'],g['uid']) for g in ref['glass']},'Glass identity mismatch')
    clean=c['id']=='00_clean'
    expected={f'bvt_glass_{k}':0.0 for k in CHANNELS}
    expected['bvt_artifact_coverage']=c['coverage']
    if c['preset']=='HEAVY_CONDENSATION':
        expected.update({f'bvt_glass_{k}':v*c['intensity'] for k,v in HEAVY.items()})
    elif c['preset']=='CUSTOM':
        expected[c['channel']]=c['channel_max']*c['intensity']
    else:
        require(clean,'Unknown condition preset')
    for i,g in enumerate(sorted(panes,key=lambda g:g['name'])):
        require(g['hide_render'] is clean,'Wrong glass visibility')
        if not clean:
            require(g['seed']==seed+i and g['preset']==c['preset'],'Wrong glass preset or seed')
        require(set(g['channels'])==set(expected) and all(math.isclose(g['channels'][k],v,abs_tol=1e-6) for k,v in expected.items()),'Wrong glass channels')


def sheet_add(sheet,idx,arr,condition,metric):
    # Row 0 is the control, subsequent rows are effect families, 4 levels each.
    row,col = (0,0) if idx==0 else (1+(idx-1)//4,(idx-1)%4)
    x,y=col*340,row*218
    im=Image.fromarray(arr); im.thumbnail((332,187))
    sheet.paste(im,(x+4,y+23))
    draw=ImageDraw.Draw(sheet)
    draw.text((x+4,y+3),condition,fill='white')
    draw.text((x+4,y+204),f'MAE RGB {metric:.4f}%',fill='white')


def audit(run, out, ids, offline=False):
    matrix_path=REPO/'configs/research/pilot_001.json'
    ref_path=REPO/'configs/research/pilot_001_master_reference.json'
    matrix=load(matrix_path); conditions=matrix['conditions']; seed=matrix['seed']
    refs={s['id']:s for s in load(ref_path)['scenes']}
    plan=load(run/'run_plan.json'); summary=load(run/'run_summary.json')
    jobs={j['id']:j for j in plan['jobs']}; results={s['id']:s for s in summary['scenes']}
    require(len(jobs)==len(plan['jobs'])==len(results)==len(summary['scenes'])==len(ids) and set(jobs)==set(results)==set(ids),'Unexpected or duplicate scene IDs')
    require(summary['status']=='PASS' and summary['passed']==summary['total']==len(ids),'Runner did not report all scenes PASS')
    require(plan['matrix_sha256']==sha(matrix_path),'Matrix hash changed')
    if not offline:
        require(plan['runner_sha256']==sha(REPO/'scripts/bvt_pilot_batch_runner.py'),'Runner hash changed')
    expected={f"{c['id']}/{sub}/scene_{sid}.{ext}" for c in conditions for sid in ids for sub,ext in [('images','png'),('labels','txt'),('metadata','json')]}
    actual={p.relative_to(run).as_posix() for p in run.rglob('*') if p.is_file() and p.parent.name in ('images','labels','metadata')}
    require(actual==expected,f'Missing files: {sorted(expected-actual)}; unexpected files: {sorted(actual-expected)}')
    out.mkdir(parents=True,exist_ok=False)
    preview=out/'previews'; preview.mkdir()
    rows=[]; failures=[]; warnings=[]; counts={}; image_hashes=set()
    for sid in ids:
        try:
            j=jobs[sid]; ref=refs[sid]; res=results[sid]
            require(j['conditions']==conditions and j['seed']==seed,'Plan conditions/seed mismatch')
            require(res['status']=='PASS','Scene result not PASS')
            records={r['condition']['id']:r for r in res['records']}
            require(len(records)==len(res['records'])==len(conditions),'Missing/duplicate summary records')
            for k in ('master_sha256','source_sha256'):
                require(j[k]==ref[k],k+' differs from preflight')
            if not offline:
                for key in ('master','source'):
                    require(sha(Path(j[key]))==j[key+'_sha256'],key+' changed on disk')
                for item in j['labels']:
                    require(sha(Path(item['path']))==item['sha256'],'Reference TXT changed on disk')
            clean_arr=None; clean_bytes=None; outside=outside_mask(ref)
            sheet=Image.new('RGB',(1360,1308),'#202020')
            means={}; seen=set()
            for idx,c in enumerate(conditions):
                cid=c['id']; stem=f'scene_{sid}'
                img=run/cid/'images'/(stem+'.png'); txt=run/cid/'labels'/(stem+'.txt'); mp=run/cid/'metadata'/(stem+'.json')
                m=load(mp)
                require(m==records[cid],cid+': metadata differs from summary')
                require(m['id']==sid and m['condition']==c and m['resolution']==ref['resolution'],cid+': wrong condition/id/size')
                for key,p in [('image',img),('label',txt)]:
                    require(m[key].replace('\\','/')==p.relative_to(run).as_posix(),cid+': wrong metadata path')
                    require(sha(p)==m[key+'_sha256'],cid+': '+key+' hash mismatch')
                require(m['geometry_unchanged'] is True and m['master_sha256']==ref['master_sha256'] and m['source_sha256']==ref['source_sha256'],cid+': geometry/provenance mismatch')
                require(m['blender']=='5.2.3 LTS' and m['bvt_build']=='alpha.5-step5',cid+': unexpected software build')
                validate_glass(m,ref,c,seed)
                ll=labels(txt); require(len(ll)==m['boxes']==ref['boxes'],cid+': wrong annotation count')
                arr=rgb(img,ref['resolution']); raw=txt.read_bytes()
                if idx==0:
                    clean_arr=arr; clean_bytes=raw
                    if not offline:
                        require(any(same_rows(ll,labels(Path(r['path']))) for r in j['labels']),'Clean TXT differs from all reference exports')
                require(raw==clean_bytes,cid+': paired labels not byte-identical')
                # Cast before subtraction; uint8 subtraction would wrap.
                delta=np.abs(arr.astype(np.int16)-clean_arr.astype(np.int16))
                changed=np.any(delta!=0,axis=2)
                leak=int(np.count_nonzero(changed & outside))
                mean=float(delta.mean()/255*100); fraction=float(changed.mean()*100)
                ph=hashlib.sha256(arr.tobytes()).hexdigest()
                require(ph not in seen,cid+': duplicate decoded RGB in scene'); seen.add(ph)
                require(leak==0,f'{cid}: {leak} changed pixels outside pane rectangles (+2px)')
                image_hashes.add(m['image_sha256'])
                rows.append(dict(scene=sid,condition=cid,intensity=c['intensity'],boxes=len(ll),mean_abs_rgb_pct=mean,changed_pixels_pct=fraction,outside_changed_pixels=leak,image_sha256=m['image_sha256'],label_sha256=m['label_sha256']))
                sheet_add(sheet,idx,arr,cid,mean)
                if idx:
                    family=cid.rsplit('_',1)[0]; means.setdefault(family,[]).append(mean)
            for family,values in means.items():
                if any(a>=b for a,b in zip(values,values[1:])):
                    warnings.append(f'{sid} {family}: non-increasing RGB MAE {values}')
            sheet.save(preview/f'scene_{sid}.jpg',quality=87,optimize=True)
            counts[sid]=ref['boxes']; print(f'{sid}: PASS | {len(conditions)} PNG | {ref["boxes"]} boxes | outside=0',flush=True)
        except Exception as e:
            failures.append(f'{sid}: {e}'); print('FAIL:',failures[-1],flush=True)
    if len(image_hashes)!=len(rows):
        warnings.append('Duplicate PNG byte hashes across audited scene/condition records')
    fields=['scene','condition','intensity','boxes','mean_abs_rgb_pct','changed_pixels_pct','outside_changed_pixels','image_sha256','label_sha256']
    with (out/'metrics.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    aggregates=[]
    for c in conditions:
        group=[r for r in rows if r['condition']==c['id']]
        if group:
            aggregates.append(dict(condition=c['id'],scenes=len(group),mean_abs_rgb_pct=sum(r['mean_abs_rgb_pct'] for r in group)/len(group),changed_pixels_pct=sum(r['changed_pixels_pct'] for r in group)/len(group),outside_changed_pixels=sum(r['outside_changed_pixels'] for r in group)))
    report=dict(status='FAIL' if failures else 'REVIEW' if warnings else 'PASS',offline=offline,scenes_passed=len(counts),scenes_expected=len(ids),images_verified=len(rows),expected_images=len(ids)*len(conditions),unique_png_hashes=len(image_hashes),source_boxes=sum(counts.values()),variant_boxes=sum(r['boxes'] for r in rows),failures=failures,warnings=warnings,aggregates=aggregates,limitations=['Rectangular camera bounds, not exact physical glass masks','Visual correctness and model accuracy not assessed','No Blender rerender; geometry evidence from Runner and frozen QA hashes','Offline mode skips current input and runner file hashes'])
    (out/'qa_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    # Include original run evidence but omit full-size PNG and bulky logs.
    bundle=out.with_suffix('.zip')
    require(not bundle.exists(),'QA ZIP already exists')
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(out))
        for p in (run/'run_plan.json',run/'run_summary.json',matrix_path,ref_path):
            z.write(p,'evidence/'+p.name)
        for p in sorted(run.rglob('*')):
            if p.is_file() and p.parent.name in ('labels','metadata'):
                z.write(p,'evidence/'+p.relative_to(run).as_posix())
    print(json.dumps({k:v for k,v in report.items() if k not in ('aggregates','limitations')},indent=2)); print('QA ZIP:',bundle)
    return 1 if failures else 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,default=REPO/'data_local/research_runs/pilot_001_full')
    p.add_argument('--output',type=Path,help='New report directory, outside original run')
    p.add_argument('--ids',nargs='+',type=int,default=list(range(1,11)))
    p.add_argument('--offline',action='store_true',help='Archive-only audit; skips live source/master/runner checks')
    a=p.parse_args(); run=a.run.resolve(); out=(a.output or run.with_name(run.name+'_qa')).resolve()
    require(len(set(a.ids))==len(a.ids) and all(1<=i<=10 for i in a.ids),'Unique scene IDs 1..10 required')
    require(run.is_dir() and not out.exists() and not out.with_suffix('.zip').exists() and run not in out.parents and out not in run.parents,'Use a new output directory separate from input run')
    return audit(run,out,[f'{i:04d}' for i in a.ids],a.offline)


if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc:
        print('AUDIT ERROR:',exc,file=sys.stderr); sys.exit(1)
