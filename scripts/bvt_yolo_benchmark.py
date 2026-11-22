#!/usr/bin/env python3
"""Single-source BVT paired detection benchmark. No training or input mutation."""
import argparse
import csv
import html
import json
import math
import platform
from pathlib import Path
import statistics
import sys
import time
import zipfile

from PIL import Image, ImageDraw
import numpy as np
from bvt_yolo_matrix_propagation import (
    SCHEMA as INPUT_SCHEMA, CONTROL, MATERIALS, EFFECTS, QA_EFFECTS,
    need, sha, read, write, existing_file, output_guard, rgb, parse_labels,
)

SCHEMA = 'bvt.yolo-benchmark.v01'
THRESHOLDS = tuple(i / 100 for i in range(50, 100, 5))


def load_dataset(root):
    """Require complete live-geometry Step 5, exact PNG/TXT and stable UIDs."""
    root = root.resolve()
    report = read(existing_file(root, 'report.json'))
    geom = read(existing_file(root, 'geometry.json'))
    need(report['schema'] == INPUT_SCHEMA and report['status'] == 'PASS_CANDIDATES'
         and report['geometry_status'] == geom['status'] == 'PASS', 'Step 5 not complete')
    need(report['labels_status'] == 'INHERITED_CANDIDATES_NOT_APPROVED'
         and report['train_val_split'] is None and report['reference_clean_rgb_equal'] is True,
         'Unexpected reference policy')
    ids = {m+'__'+e for m in MATERIALS for e in EFFECTS}
    rows = report['jobs_summary']; geometry = {j['id']:j for j in geom['jobs']}
    need(len(rows)==len(geom['jobs'])==report['jobs']==report['matrix_pixel_pairs_verified']==len(ids)
         and {j['id'] for j in rows}==set(geometry)==ids, 'Expected full matrix 84/84')
    need(report['experimental']==66 and report['qa_only']==18, 'Incorrect role totals')
    size = report['image_size']; need(len(size)==2 and all(type(x) is int and x>0 for x in size), 'Invalid size')
    ref = read(existing_file(root, 'reference/manifest.json'))
    need([ref['image_width'],ref['image_height']]==size, 'Reference dimensions mismatch')
    label = existing_file(root, 'reference/labels.txt')
    need(sha(label)==report['reference_label_sha256'], 'Reference TXT hash mismatch')
    boxes, classes = parse_labels(label.read_text(encoding='utf-8'), ref['annotations'], size)
    need(classes=={0:'ice_cream'} and read(existing_file(root,'classes.json'))=={'0':'ice_cream'}, 'v01 supports ice_cream only')
    need(len(boxes)==report['boxes_per_image']==28 and report['boxes_total']==28*84, 'Unexpected box count')
    source=report['source_group']; need(geom['source_sha256']==source, 'Geometry source mismatch')
    jobs={}; membership=None
    for row in rows:
        jid=row['id']; material,effect=jid.split('__'); manifest_path=existing_file(root,f'manifests/{jid}.json'); m=read(manifest_path)
        need(all(m.get(k)==v for k,v in row.items()), 'Manifest/report mismatch: '+jid)
        need(row['material']==material and row['effect']==effect and row['role']==('QA_ONLY' if effect in QA_EFFECTS else 'EXPERIMENTAL'), 'Job role mismatch: '+jid)
        need(row['source_group']==source and row['geometry_status']=='PASS' and row['box_count']==len(boxes), 'Source/geometry mismatch: '+jid)
        g=geometry[jid]; need(g['status']=='PASS' and g['sha256']==row['blend_sha256'] and g['box_count']==len(boxes)
             and 0<=g['max_box_delta_px']<=.05 and 0<=g['max_geometry_delta_px']<=.05,'Geometry proof mismatch: '+jid)
        need(row['image']==f'images/pilot/{jid}.png' and row['labels']==f'labels/pilot/{jid}.txt','Unexpected file names: '+jid)
        image=existing_file(root,row['image']); labels=existing_file(root,row['labels'])
        need(sha(image)==row['render_sha256'] and sha(labels)==row['label_sha256']==report['reference_label_sha256'], 'PNG/TXT hash mismatch: '+jid)
        rgb(image.read_bytes(),size)
        ann=m['annotations']; need(len(ann)==len(boxes),'Annotation count mismatch: '+jid)
        for a,b in zip(ann,boxes):
            need(all(a[k]==b[k] for k in ('index','uid','object','class_id','class_name','xywh','xyxy','rect')), 'Inherited box mismatch: '+jid)
            need(type(a['affected_roi']) is bool and isinstance(a['flags'],list), 'Invalid ROI flags: '+jid)
        group=tuple(a['affected_roi'] for a in ann)
        if membership is None: membership=group
        need(group==membership and sum(group)==row['affected_boxes']==7,'ROI membership mismatch: '+jid)
        jobs[jid]={'row':row,'annotations':ann,'path':image,'manifest_sha256':sha(manifest_path)}
    need(np.array_equal(rgb(existing_file(root,'reference/clean.png').read_bytes(),size),rgb(jobs[CONTROL]['path'].read_bytes(),size)), 'Clean reference RGB mismatch')
    return jobs,report


def iou(a,b):
    intersection=max(0.,min(a[2],b[2])-max(a[0],b[0]))*max(0.,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0.


def validate_predictions(preds):
    for p in preds:
        b=p['xyxy']; c=p['confidence']
        need(len(b)==4 and all(type(v) in (int,float) and math.isfinite(v) for v in b) and 0<=b[0]<b[2]<=1 and 0<=b[1]<b[3]<=1,'Invalid prediction bounds')
        need(type(c) in (int,float) and math.isfinite(c) and 0<=c<=1,'Invalid prediction confidence')
        need(type(p['class_id']) is int and p['class_id']==0,'Unexpected mapped prediction class')
    return preds


def match(gt,preds,threshold=.5,conf=0.):
    """Confidence-ordered greedy one-to-one matching; ties use input index, then GT index."""
    unused=set(range(len(gt))); outcomes=[]; matched={}
    for idx,p in sorted(enumerate(preds),key=lambda t:(-t[1]['confidence'],t[0])):
        if p['confidence']<conf: continue
        possibilities=[(iou(p['xyxy'],gt[i]['xyxy']),i) for i in unused if p['class_id']==gt[i]['class_id']]
        best=max(possibilities,key=lambda t:(t[0],-t[1]),default=(0.,-1))
        if best[1]>=0 and best[0]>=threshold:
            unused.remove(best[1]); matched[gt[best[1]]['uid']]={'prediction_index':idx,'confidence':p['confidence'],'iou':best[0]}
            outcomes.append((p['confidence'],True,idx))
        else: outcomes.append((p['confidence'],False,idx))
    return outcomes,matched


def ap101(outcomes,n_gt):
    if not n_gt: return None
    if not outcomes: return 0.
    ranked=sorted(outcomes,key=lambda x:-x[0]); tp=0; points=[]
    for rank,(_,hit,*_) in enumerate(ranked,1):
        tp+=int(hit); points.append((tp/n_gt,tp/rank))
    return sum(max((p for r,p in points if r>=k/100),default=0.) for k in range(101))/101


def ratio(a,b): return a/b if b else None


def metrics(samples,conf):
    """Pool predictions across images, matching separately in each image."""
    n=sum(len(g) for g,_ in samples); tp=fp=0; matched_ious=[]; aps=[]
    for g,p in samples:
        outcome,m=match(g,p,.5,conf); tp+=len(m); fp+=len(outcome)-len(m); matched_ious.extend(x['iou'] for x in m.values())
    for threshold in THRESHOLDS:
        all_out=[]
        for g,p in samples: all_out.extend(match(g,p,threshold)[0])
        aps.append(ap101(all_out,n))
    precision=ratio(tp,tp+fp); recall=ratio(tp,n)
    return {'images':len(samples),'gt':n,'tp':tp,'fp':fp,'fn':n-tp,'precision':precision,'recall':recall,
            'f1':ratio(2*tp,2*tp+fp+n-tp),'mean_matched_iou':statistics.mean(matched_ious) if matched_ious else None,
            'ap50':aps[0],'ap50_95':statistics.mean(aps) if n else None,'ap_by_iou':{f'{t:.2f}':a for t,a in zip(THRESHOLDS,aps)}}


class SmokeAdapter:
    metadata={'adapter':'SMOKE_SYNTHETIC','scientific_result':False,'description':'GT-derived synthetic predictions; deliberate misses, not model inference'}
    def predict(self,job):
        # Test a known change: first affected target disappears for every noncontrol.
        # No random variation, no images or learned model consulted by this adapter.
        return [{'class_id':0,'confidence':.9 if job['row']['id']==CONTROL or not a['affected_roi'] else .65,'xyxy':a['xyxy'][:]} for a in job['annotations'] if not (job['row']['id']!=CONTROL and a['index']==1)]


class YoloAdapter:
    def __init__(self,weights,model_class,device,imgsz,score_floor,nms_iou,max_det):
        need(weights.is_file() and weights.suffix.lower()=='.pt','Use an existing trusted local .pt checkpoint')
        import ultralytics
        import torch
        self.model=ultralytics.YOLO(str(weights),task='detect')
        need(self.model.task=='detect','Detection model required')
        names=self.model.names
        names=dict(enumerate(names)) if isinstance(names,list) else names
        hits=[int(k) for k,v in names.items() if v==model_class]
        need(len(hits)==1,'Requested model class absent/ambiguous: '+model_class+'; names='+str(names))
        self.class_id=hits[0]
        self.options=dict(device=device,imgsz=imgsz,conf=score_floor,iou=nms_iou,max_det=max_det,classes=[self.class_id],verbose=False,save=False,augment=False,half=False)
        self.metadata={'adapter':'ultralytics','scientific_result':False,'description':'Exploratory inference on inherited labels; not validated model performance',
            'weights_sha256':sha(weights),'weights_name':weights.name,'model_class':model_class,'model_class_id':self.class_id,'dataset_class_id':0,'model_names':names,
            'ultralytics':ultralytics.__version__,'torch':torch.__version__,'cuda_available':torch.cuda.is_available(),'cuda_version':torch.version.cuda,'options':self.options}
    def predict(self,job):
        result=self.model.predict(source=str(job['path']),**self.options)
        need(len(result)==1 and result[0].boxes is not None,'Expected one detection result')
        with Image.open(job['path']) as im: need(tuple(result[0].orig_shape)==(im.height,im.width),'Inference image size mismatch')
        b=result[0].boxes
        coords=b.xyxyn.detach().cpu().tolist(); conf=b.conf.detach().cpu().tolist(); cls=b.cls.detach().cpu().tolist()
        need(len(coords)==len(conf)==len(cls),'Inconsistent prediction tensors')
        need(all(v==self.class_id for v in cls),'Unexpected detector class')
        return validate_predictions([{'class_id':0,'confidence':c,'xyxy':xy} for xy,c in zip(coords,conf)])


def pair_rows(jid,baseline,kind,gt,now,base):
    rows=[]
    for a in gt:
        uid=a['uid']; x=now.get(uid); y=base.get(uid)
        rows.append({'id':jid,'baseline':baseline,'comparison':kind,'uid':uid,'index':a['index'],'group':'affected' if a['affected_roi'] else 'control',
            'detected':int(x is not None),'baseline_detected':int(y is not None),'lost':int(y is not None and x is None),'gained':int(y is None and x is not None),
            'confidence':x['confidence'] if x else None,'baseline_confidence':y['confidence'] if y else None,
            'confidence_delta_both':x['confidence']-y['confidence'] if x and y else None,
            'score_delta_with_miss_zero':(x['confidence'] if x else 0.)-(y['confidence'] if y else 0.),'iou':x['iou'] if x else None,'baseline_iou':y['iou'] if y else None,'qa_flags':'|'.join(a['flags'])})
    return rows


def summarize_pair(rows):
    both=[r['confidence_delta_both'] for r in rows if r['confidence_delta_both'] is not None]
    n=len(rows); b=sum(r['baseline_detected'] for r in rows); d=sum(r['detected'] for r in rows); lost=sum(r['lost'] for r in rows)
    return {'gt':n,'baseline_detected':b,'detected':d,'baseline_recall':ratio(b,n),'recall':ratio(d,n),'recall_delta_pp':100*(d-b)/n if n else None,
            'lost':lost,'gained':sum(r['gained'] for r in rows),'detection_drop_rate':ratio(lost,b),'both_detected':len(both),
            'confidence_delta_both':statistics.mean(both) if both else None,'score_delta_with_miss_zero':statistics.mean(r['score_delta_with_miss_zero'] for r in rows) if rows else None}


def csv_write(path,rows):
    need(bool(rows),'Empty CSV: '+str(path))
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def overlay(job,preds,out,conf):
    with Image.open(job['path']) as im:
        im=im.copy(); im.thumbnail((1000,1000)); w,h=im.size; d=ImageDraw.Draw(im)
        def rect(box): return tuple(round(v*s) for v,s in zip(box,(w,h,w,h)))
        for a in job['annotations']:
            b=rect(a['xyxy']); d.rectangle(b,outline='#ffb000' if a['affected_roi'] else '#00e693',width=2); d.text((b[0]+2,b[1]+2),str(a['index']),fill='white',stroke_width=1,stroke_fill='black')
        for p in preds:
            if p['confidence']>=conf:
                b=rect(p['xyxy']); d.rectangle(b,outline='#43baff',width=2); d.text((b[0]+2,max(0,b[3]-12)),f"{p['confidence']:.2f}",fill='#43baff',stroke_width=1,stroke_fill='black')
        im.save(out,quality=87)


def make_html(out,scene_rows,groups,mode):
    esc=html.escape; lookup={r['id']:r for r in scene_rows}
    s=['<!doctype html><meta charset="utf-8"><title>BVT benchmark</title><style>body{font:15px system-ui;margin:24px;background:#fafafa;color:#182535}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px;text-align:right}th:first-child{text-align:left}img{width:100%;max-width:560px}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}article{background:white;padding:12px}</style>',f'<h1>BVT benchmark — {esc(mode)}</h1>', '<p>Single source; inherited candidates; not independently validated. SMOKE is synthetic, never model performance. QA_ONLY excluded from aggregate experimental metrics.</p>']
    for field,title in [('affected_recall_delta_pp','Affected recall delta (pp) vs global clear'),('control_recall_delta_pp','Control recall delta (pp) vs global clear'),('ap50','AP50 (candidate labels)')]:
        s.append('<h2>'+title+'</h2><table><tr><th>Material</th>'+''.join(f'<th title="{esc(e)}">{e[:2]}</th>' for e in EFFECTS)+'</tr>')
        for mat in MATERIALS:
            s.append('<tr><th>'+esc(mat)+'</th>')
            for e in EFFECTS:
                r=lookup.get(mat+'__'+e); v=r.get(field) if r else None
                if v is None: s.append('<td>—</td>'); continue
                q=max(-100,min(100,v if field.endswith('pp') else v*100)); color=f'rgba({"205,65,50" if q<0 else "35,150,95"},{abs(q)/125:.3f})'
                s.append(f'<td style="background:{color}" title="{esc(r["role"])}">{v:.2f}</td>')
            s.append('</tr>')
        s.append('</table>')
    s.append('<h2>Experimental groups</h2><table><tr><th>Group</th><th>N</th><th>AP50</th><th>AP50–95</th><th>Recall</th></tr>')
    for r in groups:
        s.append(f'<tr><th>{esc(r["group"])}</th><td>{r["images"]}</td><td>{r["ap50"]:.3f}</td><td>{r["ap50_95"]:.3f}</td><td>{r["recall"]:.3f}</td></tr>')
    s.append('</table><h2>Predictions</h2><p>Orange: affected GT; green: control GT; blue: predicted box at operating confidence.</p><div class="gallery">')
    for r in scene_rows:
        jid=r['id']; s.append(f'<article><h3>{esc(jid)}</h3><p>{esc(r["role"])} · TP {r["tp"]} FP {r["fp"]} FN {r["fn"]}</p><a href="predictions/{jid}.json">JSON</a><img loading="lazy" src="previews/{jid}.jpg"></article>')
    s.append('</div>'); (out/'index.html').write_text('\n'.join(s),encoding='utf-8')


def run(args):
    root=Path(args.dataset_dir).resolve(); out=output_guard(Path(args.output_dir),[root]+([Path(args.weights)] if args.weights else []))
    jobs,source=load_dataset(root)
    need(0<args.score_floor<=args.conf<=1 and 0<args.nms_iou<=1 and args.imgsz>=32 and args.max_det>=28,'Invalid inference settings')
    if args.smoke: adapter=SmokeAdapter()
    else: adapter=YoloAdapter(Path(args.weights).resolve(),args.model_class,args.device,args.imgsz,args.score_floor,args.nms_iou,args.max_det)
    ids=[m+'__'+e for m in MATERIALS for e in EFFECTS if not args.pilot or (m in MATERIALS[:3] and e in (EFFECTS[0],EFFECTS[7],EFFECTS[10]))]
    out.mkdir(parents=True); (out/'predictions').mkdir(); (out/'previews').mkdir(); predictions={}; matches={}; scene_rows=[]; pairs=[]; pair_summary=[]
    report={'schema':SCHEMA,'status':'ERROR_INCOMPLETE','mode':adapter.metadata['adapter'],'model':adapter.metadata,'source_group':source['source_group'],'input_report_sha256':sha(root/'report.json'),'input_geometry_sha256':sha(root/'geometry.json'),'candidate_labels':True,'independent_source_count':1,'python':platform.python_version(),'platform':platform.platform(),'numpy':np.__version__, 'operating_confidence':args.conf,'match_iou':.5,'prediction_score_floor':args.score_floor,'ap_definition':'single class; confidence-greedy one-to-one per image; 101-point interpolation; post-NMS and score-floor limited; not official COCOeval','qa_only_in_experimental_aggregates':False,'pilot':args.pilot,'warnings':source['warnings']}
    write(out/'report.json',report)
    try:
        for jid in ids:
            job=jobs[jid]; t=time.perf_counter(); p=validate_predictions(adapter.predict(job)); duration=time.perf_counter()-t
            need(all(x['confidence']>=args.score_floor-1e-7 for x in p),'Prediction below score floor')
            need(len(p)<=args.max_det,'Prediction count beyond max_det')
            predictions[jid]=p; matches[jid]=match(job['annotations'],p,.5,args.conf)[1]
            write(out/'predictions'/f'{jid}.json',{'id':jid,'mode':report['mode'],'render_sha256':job['row']['render_sha256'],'manifest_sha256':job['manifest_sha256'],'predictions':p,'matches_iou50_at_conf':matches[jid]})
            overlay(job,p,out/'previews'/f'{jid}.jpg',args.conf)
            print('BENCHMARK_JOB='+jid+' predictions='+str(len(p)),flush=True)
            job['seconds']=duration
        for jid in ids:
            job=jobs[jid]; material,effect=jid.split('__'); m=metrics([(job['annotations'],predictions[jid])],args.conf); m.pop('ap_by_iou')
            row={'id':jid,'material':material,'effect':effect,'role':job['row']['role'],**m,'predict_seconds':job['seconds'],'max_det_reached':len(predictions[jid])==args.max_det}
            for kind,base in [('global_clear',CONTROL),('material_only',material+'__00_clean'),('same_artifact_clear','clear_glass__'+effect)]:
                rr=pair_rows(jid,base,kind,job['annotations'],matches[jid],matches[base]); pairs.extend(rr)
                for group in ('affected','control'):
                    summary=summarize_pair([r for r in rr if r['group']==group]); pair_summary.append({'id':jid,'role':job['row']['role'],'comparison':kind,'baseline':base,'group':group,**summary})
                    if kind=='global_clear':
                        row[group+'_recall']=summary['recall']; row[group+'_recall_delta_pp']=summary['recall_delta_pp']; row[group+'_lost']=summary['lost']
            scene_rows.append(row)
        experimental=[j for j in ids if jobs[j]['row']['role']=='EXPERIMENTAL']; groups=[]
        for name,selected in [('all_experimental',experimental)]+[(m,[j for j in experimental if jobs[j]['row']['material']==m]) for m in MATERIALS]+[(e,[j for j in experimental if jobs[j]['row']['effect']==e]) for e in EFFECTS if e not in QA_EFFECTS]:
            if not selected: continue
            m=metrics([(jobs[j]['annotations'],predictions[j]) for j in selected],args.conf); m.pop('ap_by_iou'); groups.append({'group':name,**m})
        group_pairs=[]
        for label,selected in [('all_experimental',experimental)]+[(m,[j for j in experimental if jobs[j]['row']['material']==m]) for m in MATERIALS]+[(e,[j for j in experimental if jobs[j]['row']['effect']==e]) for e in EFFECTS if e not in QA_EFFECTS]:
            if not selected: continue
            selected=set(selected)
            for kind in ('global_clear','material_only','same_artifact_clear'):
                for group in ('affected','control'):
                    rr=[r for r in pairs if r['id'] in selected and r['comparison']==kind and r['group']==group]
                    group_pairs.append({'aggregate':label,'comparison':kind,'group':group,**summarize_pair(rr)})
        csv_write(out/'scenes.csv',scene_rows); csv_write(out/'groups.csv',groups); csv_write(out/'paired_objects.csv',pairs); csv_write(out/'paired_summary.csv',pair_summary); csv_write(out/'paired_groups.csv',group_pairs)
        need(all(sha(jobs[j]['path'])==jobs[j]['row']['render_sha256'] for j in ids),'Input PNG changed during benchmark')
        if not args.smoke: need(sha(Path(args.weights))==adapter.metadata['weights_sha256'],'Weights changed during benchmark')
        make_html(out,scene_rows,groups,report['mode'])
        report.update(status='PASS_SMOKE' if args.smoke else 'PASS_EXPLORATORY_INFERENCE',images=len(ids),experimental=len(experimental),qa_only=len(ids)-len(experimental),objects=sum(len(jobs[j]['annotations']) for j in ids),predictions=sum(len(p) for p in predictions.values()),metrics=groups[0],max_det_reached_images=sum(r['max_det_reached'] for r in scene_rows))
        write(out/'report.json',report); print('YOLO_BENCHMARK='+report['status']); return 0
    except Exception as exc:
        report['error']=str(exc); write(out/'report.json',report); raise


def pack(root,archive):
    root=root.resolve(); archive=archive.resolve()
    need(not archive.exists() and not archive.is_relative_to(root) and archive.parent==root.parent,'Use a fresh sibling ZIP')
    r=read(existing_file(root,'report.json')); need(r['schema']==SCHEMA and r['status'] in ('PASS_SMOKE','PASS_EXPLORATORY_INFERENCE'),'Only pack completed benchmark')
    files=[existing_file(root,n) for n in ('report.json','scenes.csv','groups.csv','paired_objects.csv','paired_summary.csv','paired_groups.csv','index.html')]
    for folder,suffix in [('predictions','.json'),('previews','.jpg')]:
        names=sorted((root/folder).glob('*'+suffix)); need(len(names)==r['images'],'Output count mismatch: '+folder); files.extend(existing_file(root,f'{folder}/{p.name}') for p in names)
    manifest={'schema':SCHEMA,'files':{p.relative_to(root).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in files}}
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in files: z.write(p,p.relative_to(root).as_posix())
        z.writestr('archive_manifest.json',json.dumps(manifest,indent=2,sort_keys=True))
    with zipfile.ZipFile(archive) as z: need(z.testzip() is None,'ZIP CRC error')
    print('BENCHMARK_ARCHIVE='+str(archive))


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('run'); r.add_argument('--dataset-dir',required=True); r.add_argument('--output-dir',required=True); mode=r.add_mutually_exclusive_group(required=True); mode.add_argument('--smoke',action='store_true'); mode.add_argument('--weights'); r.add_argument('--model-class',default='ice_cream'); r.add_argument('--device',default='cpu'); r.add_argument('--imgsz',type=int,default=960); r.add_argument('--score-floor',type=float,default=.001); r.add_argument('--conf',type=float,default=.25); r.add_argument('--nms-iou',type=float,default=.7); r.add_argument('--max-det',type=int,default=300); r.add_argument('--pilot',action='store_true')
    k=sub.add_parser('pack'); k.add_argument('--input-dir',required=True,type=Path); k.add_argument('--archive',required=True,type=Path)
    a=p.parse_args()
    try:
        if a.command=='run': return run(a)
        pack(a.input_dir,a.archive); return 0
    except Exception as exc: print('YOLO_BENCHMARK=ERROR: '+str(exc),file=sys.stderr); return 1


if __name__=='__main__': raise SystemExit(main())
