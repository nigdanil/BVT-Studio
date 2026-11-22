#!/usr/bin/env python3
"""Propagate inspected BVT reference boxes to an existing material/artifact matrix.

Output is an experimental, single-source pilot, never a train/val split.
The production CLI requires live Blender geometry validation before publishing labels.
"""
import argparse
import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'bvt.yolo-matrix-propagation.v01'
MATRIX_SCHEMA = 'bvt.material-artifact-gallery.v01'
CONTROL = 'clear_glass__00_clean'
MATERIALS = ('clear_glass','frosted_glass','tinted_glass','textured_glass','coated_glass','insulated_glass')
EFFECTS = ('00_clean','01_light_condensation','02_heavy_condensation','03_frost','04_dirty_glass','05_reflections','06_microbeads_only','07_macro_droplets_only','08_running_water_only','09_combined_water_no_optics','10_combined_water_optics','11_heavy_running_water','12_stress_optics','13_clean_glass')
QA_EFFECTS = {'00_clean','12_stress_optics','13_clean_glass'}
FIELDS = ('x','y','w','h')
TOL = 5.1e-8  # exporter uses seven decimal places
GEOMETRY_TOL_PX = 0.05


def need(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(data):
    def unique(pairs):
        out = {}
        for k,v in pairs:
            need(k not in out,'Duplicate JSON key: '+k)
            out[k]=v
        return out
    return json.loads(data,object_pairs_hook=unique,parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Nonfinite JSON: '+v)))


def read(path):
    return read_json(Path(path).read_text(encoding='utf-8-sig'))


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def safe_relative(name):
    need(isinstance(name,str) and name and '\\' not in name and ':' not in name and '\x00' not in name,'Unsafe relative path')
    p=PurePosixPath(name)
    need(not p.is_absolute() and all(s not in ('','.','..') for s in name.split('/')),'Unsafe relative path: '+name)
    return p


def existing_file(base,name):
    parts=safe_relative(name).parts
    p=base.joinpath(*parts)
    need(p.is_file() and p.resolve().is_relative_to(base.resolve()) and not any(base.joinpath(*parts[:i]).is_symlink() for i in range(1,len(parts)+1)), 'Missing or unsafe file: '+name)
    return p


def output_guard(out,inputs):
    out=out.resolve()
    need(out.is_relative_to((ROOT/'qa_renders').resolve()) and out!=(ROOT/'qa_renders').resolve(),'Output must be a fresh subfolder of qa_renders')
    need(not out.exists(),'Output exists; choose a new folder')
    need(not any(out.is_relative_to(p.resolve()) or p.resolve().is_relative_to(out) for p in inputs),'Output overlaps inputs')
    return out


def rgb(data,size=None):
    with Image.open(io.BytesIO(data)) as im:
        need(im.format=='PNG' and im.mode=='RGB','Expected RGB PNG (no alpha or palette conversion)')
        need(im.width*im.height<=8_388_608,'PNG exceeds pilot pixel limit')
        if size is not None: need(im.size==tuple(size),'PNG dimensions mismatch')
        return np.array(im)


def parse_labels(text,annotations,size):
    need(isinstance(annotations,list) and annotations,'Missing annotations')
    lines=text.splitlines(); need(len(lines)==len(annotations),'TXT/manifest count mismatch')
    classes={}; uids=set(); names=set(); boxes=[]
    for i,(line,a) in enumerate(zip(lines,annotations),1):
        tok=line.split(); need(len(tok)==5 and re.fullmatch(r'0|[1-9][0-9]*',tok[0]),f'Invalid YOLO row {i}')
        cls=int(tok[0]); vals=[float(t) for t in tok[1:]]
        need(all(math.isfinite(x) for x in vals),f'Nonfinite row {i}')
        x,y,w,h=vals; b=(x-w/2,y-h/2,x+w/2,y+h/2)
        need(w>0 and h>0 and min(b[:2])>=0 and max(b[2:])<=1,f'Out of bounds row {i}')
        need(type(a['class_id']) is int and cls==a['class_id'],f'Class mismatch row {i}')
        name=a['class_name']; uid=a['uid']; obj=a['object']
        need(isinstance(name,str) and name.strip()==name and name and '\n' not in name and '\r' not in name and isinstance(uid,str) and bool(uid) and isinstance(obj,str) and bool(obj),f'Invalid manifest row {i}')
        need(uid not in uids and obj not in names,f'Duplicate UID/object row {i}'); uids.add(uid); names.add(obj)
        need(classes.setdefault(cls,name)==name,'Conflicting class name')
        need(all(type(a[k]) in (int,float) and math.isfinite(a[k]) and abs(a[k]-v)<=TOL for k,v in zip(FIELDS,vals)),f'Coordinate mismatch row {i}')
        need(all(type(a[k]) in (int,float) and math.isfinite(a[k]) and abs(a[k]-v)<=2*TOL for k,v in zip(('xmin','ymin','xmax','ymax'),b)),f'Edge mismatch row {i}')
        px=[max(0,math.floor(b[0]*size[0])),max(0,math.floor(b[1]*size[1])),min(size[0],math.ceil(b[2]*size[0])),min(size[1],math.ceil(b[3]*size[1]))]
        need(min(px[2]-px[0],px[3]-px[1])>=3,f'Tiny box {i}')
        boxes.append({'index':i,'uid':uid,'object':obj,'class_id':cls,'class_name':name,'xywh':vals,'xyxy':list(b),'rect':px})
    need(set(classes)==set(range(len(classes))) and len(set(classes.values()))==len(classes),'Class IDs/names must be unique and contiguous')
    for i,a in enumerate(boxes):
        for b in boxes[i+1:]:
            if a['class_id']!=b['class_id']: continue
            ax,ay,aw,ah=a['xywh']; bx,by,bw,bh=b['xywh']; x0,y0,x1,y1=a['xyxy']; u0,v0,u1,v1=b['xyxy']
            inter=max(0,min(x1,u1)-max(x0,u0))*max(0,min(y1,v1)-max(y0,v0))
            need(inter/(aw*ah+bw*bh-inter)<=.95,'Near duplicate boxes: '+a['object']+' / '+b['object'])
    return boxes,classes


def validate_yaml(text,classes):
    # Deliberately accepts the built-in BVT portable YAML format only, not arbitrary YAML.
    lines=text.splitlines()
    need(lines[:4]==['train: images/train','val: images/val',f'nc: {len(classes)}','names:'] and len(lines)==4+len(classes),'Unexpected BVT data.yaml format')
    for line in lines[4:]:
        m=re.fullmatch(r'  (\d+): (.+)',line)
        need(m is not None and int(m[1]) in classes and json.loads(m[2])==classes[int(m[1])],'YAML class mismatch')
    need(len({int(line.split(':')[0]) for line in lines[4:]})==len(classes),'Duplicate YAML class')


def reference_archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist(); need(len(names)==len(set(names)),'Duplicate ZIP entries')
        manifest_names=[n for n in names if re.fullmatch(r'sample_\d{6}_manifest\.json',n)]
        need(len(manifest_names)==1,'Expected one root BVT sample manifest')
        def get(n,limit=64*1024*1024):
            safe_relative(n); i=z.getinfo(n); need(not i.is_dir() and 0<i.file_size<=limit,'Invalid ZIP entry: '+n)
            return z.read(i)
        m=read_json(get(manifest_names[0])); need(m['schema']=='bvt_studio_2d_yolo_v0.1' and m['camera_type']=='ORTHO' and m['camera_profile']=='ORIGINAL','Unsupported reference camera/schema')
        need(all(type(m[k]) is int and m[k]>0 for k in ('image_width','image_height')),'Invalid image size')
        size=[m['image_width'],m['image_height']]; stem=manifest_names[0].removesuffix('_manifest.json')
        need(m['image']==f'images/train/{stem}.png' and m['labels']==f'labels/train/{stem}.txt','Reference filename mismatch')
        need(len(m['glass'])==4 and all(g['artifact_preset']=='QA_TRANSPARENT' for g in m['glass']),'Reference must be four transparent panes')
        label=get(m['labels']); boxes,classes=parse_labels(label.decode('utf-8-sig'),m['annotations'],size)
        yaml=get('data.yaml'); validate_yaml(yaml.decode('utf-8-sig'),classes)
        image=get(m['image']); rgb(image,size)
        blend=get('scene.blend',256*1024*1024)
        return {'manifest':m,'manifest_bytes':get(manifest_names[0]),'label':label,'image':image,'image_size':size,'blend':blend,'classes':classes,'boxes':boxes,'yaml':yaml}


def matrix_jobs(base,full=True):
    p=read(existing_file(base,'plan.json')); r=read(existing_file(base,'report.json'))
    need(p['schema']==r['schema']==MATRIX_SCHEMA and r['status']=='PASS' and p['labels_status']==r['labels_status']=='UNLABELED','Matrix is not a completed unlabeled PASS run')
    source=p['source']; size=[source['width'],source['height']]; need(all(type(v) is int and v>0 for v in size),'Invalid matrix size')
    jobs=p['jobs']; rows=r['jobs']; ids=[j['id'] for j in jobs]
    need(len(ids)==len(set(ids)) and [j['id'] for j in rows]==ids and CONTROL in ids,'Matrix job mismatch')
    if full: need(set(ids)=={m+'__'+e for m in MATERIALS for e in EFFECTS},'Expected full 84-combination matrix')
    for j,row in zip(jobs,rows):
        m,e=j['material'],j['effect']; name=j['id']
        need(m in MATERIALS and e in EFFECTS and name==m+'__'+e,'Invalid job ID')
        need(j['role']==('QA_ONLY' if e in QA_EFFECTS else 'EXPERIMENTAL'),'Matrix role mismatch')
        need(all(row[k]==j[k] for k in ('id','material','effect','role','seed','material_baseline','artifact_baseline')),'Job/row mismatch')
        need(row['status']=='PASS' and row['source_sha256']==source['sha256'] and row['target']==p['target']=='Glass_p_001','Matrix row invalid: '+name)
        need(row['reopen_max_rgb']==0 and row['outside_guard_gt4']==0 and row['guard_px']==4,'Matrix numerical proof failed: '+name)
        x0,y0,x1,y1=row['rect']; need(all(type(v) is int for v in row['rect']) and 0<=x0<x1<=size[0] and 0<=y0<y1<=size[1],'Invalid target rectangle')
        need(read(existing_file(base,f'gallery/{name}/manifest.json'))==row,'Job manifest mismatch: '+name)
        persistence=read(existing_file(base,f'gallery/{name}/resource_persistence.json'))
        need(persistence['status']=='PASS' and persistence['job']==name and persistence['before']==persistence['after']==row['resources'],'Packed resource proof failed: '+name)
        need(read(existing_file(base,f'gallery/{name}/material.json'))==p['materials'][m] and read(existing_file(base,f'gallery/{name}/artifact.json'))==p['presets'][e],'Preset mismatch: '+name)
    need(len({tuple(row['rect']) for row in rows})==1,'Matrix rectangles differ')
    need(re.fullmatch('[0-9a-f]{64}',source['sha256']) is not None,'Invalid source digest')
    return p,rows


def difference(a,b):
    need(a.shape==b.shape,'Image shape mismatch')
    return np.max(np.abs(a.astype(np.int16)-b.astype(np.int16)),axis=2)


def gray(a):
    a=a.astype(np.float32)
    return .2126*a[...,0]+.7152*a[...,1]+.0722*a[...,2]


def detail(a):
    g=gray(a)
    return float((np.abs(np.diff(g,axis=0)).mean()+np.abs(np.diff(g,axis=1)).mean())/2)


def box_qa(clean,img,box,rect,guard,role):
    x0,y0,x1,y1=box['rect']; a=clean[y0:y1,x0:x1]; b=img[y0:y1,x0:x1]; d=difference(a,b)
    tx0,ty0,tx1,ty1=rect
    affected=max(x0,tx0-guard)<min(x1,tx1+guard) and max(y0,ty0-guard)<min(y1,ty1+guard)
    base=detail(a); ratio=detail(b)/base if base>1e-8 else None
    pct=float(100*(d>4).mean()); flags=[]
    if affected and np.any(d): flags.append('OPTICAL_ROI_REVIEW')
    if ratio is not None and ratio<.55: flags.append('LOW_DETAIL_PROXY')
    if pct>=50: flags.append('LARGE_RGB_CHANGE')
    if not affected and np.any(d>4): flags.append('OUTSIDE_TARGET_CHANGE')
    return {**box,'affected_roi':affected,'changed_gt4_pct':pct,'max_rgb':int(d.max()),'detail_ratio':ratio,'mean_abs_rgb_delta':float(np.abs(a.astype(np.int16)-b.astype(np.int16)).mean()),'flags':flags,'status':'QA_ONLY' if role=='QA_ONLY' else 'REVIEW' if flags else 'CANDIDATE_UNCHANGED'}


def overlay(img,rows,out):
    im=Image.fromarray(img); d=ImageDraw.Draw(im)
    for b in rows:
        x0,y0,x1,y1=b['rect']; color='#ffb143' if b['flags'] else '#00ed91'
        d.rectangle((x0,y0,x1-1,y1-1),outline=color,width=3); d.rectangle((x0,y0,x0+25,y0+15),fill='#17191c'); d.text((x0+2,y0+1),str(b['index']),fill=color)
    # Preview is separate from the clean candidate PNG. Keep full resolution for box review.
    im.save(out,format='PNG')


def check_matrix_png(base,row,size,clean):
    name=row['id']; d=f'gallery/{name}/'
    render=existing_file(base,d+'render.png'); opened=existing_file(base,d+'reopened.png')
    raw=render.read_bytes(); need(digest(raw)==row['render_sha256'],'Render SHA mismatch: '+name)
    arr=rgb(raw,size); again=rgb(opened.read_bytes(),size); need(np.array_equal(arr,again),'Reopened pixel mismatch: '+name)
    delta=difference(clean,arr); x0,y0,x1,y1=row['rect']; g=row['guard_px']; mask=np.ones(delta.shape,bool)
    mask[max(0,y0-g):min(size[1],y1+g),max(0,x0-g):min(size[0],x1+g)]=False
    need(not np.any(delta[mask]>4),'Outside ROI pixel leakage: '+name)
    need(int((delta>4).sum())==row['total_delta']['changed_gt4'] and int(delta.max())==row['total_delta']['max_rgb'],'Matrix pixel metric mismatch: '+name)
    return render,arr


def csv_write(path,rows,fields):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-zip',required=True,type=Path); p.add_argument('--matrix-dir',required=True,type=Path); p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--blender',type=Path); p.add_argument('--audit-only',action='store_true',help='No scene validation; audit PNGs only; no candidate labels or images published')
    p.add_argument('--pilot',action='store_true',help='Require the full matrix but export only nine known pilot jobs')
    a=p.parse_args(argv); refpath=a.reference_zip.resolve(); base=a.matrix_dir.resolve(); out=output_guard(a.output_dir,[base,refpath]); need(refpath.is_file() and base.is_dir(),'Missing inputs')
    need(a.audit_only or (a.blender is not None and a.blender.is_file()),'Provide Blender executable (or explicit --audit-only)')
    ref=reference_archive(refpath); plan,all_rows=matrix_jobs(base); size=ref['image_size']; need(size==[plan['source']['width'],plan['source']['height']],'Reference/matrix size mismatch')
    clean=rgb(ref['image'],size); base_control=existing_file(base,f'gallery/{CONTROL}/render.png')
    need(np.array_equal(clean,rgb(base_control.read_bytes(),size)),'Exported reference is not pixel-identical to matrix control; do not copy labels')
    rows=[r for r in all_rows if not a.pilot or (r['material'] in MATERIALS[:3] and r['effect'] in ('00_clean','07_macro_droplets_only','10_combined_water_optics'))]
    # Plan scene digests before the output is created, and bind the geometry result to these bytes.
    scenes=[]
    if not a.audit_only:
        for r in rows:
            s=existing_file(base,f'gallery/{r["id"]}/scene.blend'); need(sha(s)==r['blend_sha256'],'Scene SHA mismatch: '+r['id']); scenes.append({'id':r['id'],'path':str(s),'sha256':r['blend_sha256']})
    out.mkdir(parents=True); report={'schema':SCHEMA,'status':'ERROR','labels_status':'NOT_PUBLISHED','source_group':plan['source']['sha256'],'reference_zip_sha256':sha(refpath),'matrix_plan_sha256':sha(base/'plan.json'),'matrix_report_sha256':sha(base/'report.json'),'image_size':size,'boxes_per_image':len(ref['boxes']),'warnings':['One source group; no train/val split and no independent benchmark.','Inherited boxes describe original product positions, not measured post-refraction visible bounds.','Pixel/gradient statistics are review proxies, not a visibility ground truth or calibrated acceptance threshold.']}
    write(out/'report.json',report)
    try:
        geom_status='NOT_RUN_AUDIT_ONLY'
        if not a.audit_only:
            # Reference blend only as a temporary input to the worker; do not publish it or leak machine paths in the review ZIP.
            import tempfile
            with tempfile.TemporaryDirectory(prefix='bvt_yolo_geometry_') as tmp:
                tmp=Path(tmp); refblend=tmp/'reference.blend'; refblend.write_bytes(ref['blend']); geom_plan=tmp/'geometry_plan.json'
                write(geom_plan,{'schema':SCHEMA,'reference_blend':str(refblend),'reference_blend_sha256':digest(ref['blend']),'source_sha256':plan['source']['sha256'],'size':size,'manifest':ref['manifest'],'boxes':ref['boxes'],'scenes':scenes})
                cmd=[str(a.blender.resolve()),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(ROOT/'scripts/blender_yolo_matrix_check.py'),'--','--plan',str(geom_plan),'--report',str(out/'geometry.json')]
                with (out/'blender.log').open('w',encoding='utf-8') as log:
                    proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
                need(proc.returncode==0,'Blender geometry check failed; see blender.log')
                g=read(out/'geometry.json'); need(g['schema']==SCHEMA and g['status']=='PASS' and g['reference_blend_sha256']==digest(ref['blend']) and g['source_sha256']==plan['source']['sha256'] and g['boxes']==len(ref['boxes']) and [(j['id'],j['sha256']) for j in g['jobs']]==[(j['id'],j['sha256']) for j in scenes] and all(j['status']=='PASS' for j in g['jobs']),'Geometry result mismatch')
                geom_status='PASS'
        # Full independent pixel audit, even for a nine-job pilot. Publish nothing until all selected scenes and every PNG pair pass.
        for r in all_rows: check_matrix_png(base,r,size,clean)
        print('MATRIX_PIXEL_AUDIT=PASS '+str(len(all_rows)),flush=True)
        (out/'reference').mkdir(); (out/'reference'/'labels.txt').write_bytes(ref['label']); (out/'reference'/'manifest.json').write_bytes(ref['manifest_bytes']); (out/'reference'/'clean.png').write_bytes(ref['image']); (out/'reference'/'data.yaml').write_bytes(ref['yaml'])
        write(out/'classes.json',{str(k):v for k,v in ref['classes'].items()})
        for d in ('previews','manifests'): (out/d).mkdir()
        if not a.audit_only:
            for d in ('images/pilot','labels/pilot'): (out/d).mkdir(parents=True)
        summary=[]; review=[]
        for r in rows:
            name=r['id']; render,img=check_matrix_png(base,r,size,clean)
            if not a.audit_only: need(sha(existing_file(base,f'gallery/{name}/scene.blend'))==r['blend_sha256'],'Scene changed after geometry check')
            q=[box_qa(clean,img,b,r['rect'],r['guard_px'],r['role']) for b in ref['boxes']]
            state='QA_ONLY' if r['role']=='QA_ONLY' else 'REVIEW' if any(b['flags'] for b in q) else 'CANDIDATE_UNCHANGED'
            if not a.audit_only:
                image_path=out/'images/pilot'/f'{name}.png'; shutil.copyfile(render,image_path); need(sha(image_path)==r['render_sha256'],'Render changed during copy'); (out/'labels/pilot'/f'{name}.txt').write_bytes(ref['label'])
            overlay(img,q,out/'previews'/f'{name}.png')
            rec={'id':name,'material':r['material'],'effect':r['effect'],'role':r['role'],'status':state,'geometry_status':geom_status,'source_group':plan['source']['sha256'],'render_sha256':r['render_sha256'],'blend_sha256':r['blend_sha256'],'label_sha256':digest(ref['label']),'box_count':len(q),'review_boxes':sum(bool(b['flags']) for b in q),'affected_boxes':sum(b['affected_roi'] for b in q),'annotations':q,'labels_status':'NOT_PUBLISHED_AUDIT_ONLY' if a.audit_only else 'INHERITED_CANDIDATES_NOT_APPROVED','image':None if a.audit_only else f'images/pilot/{name}.png','labels':None if a.audit_only else f'labels/pilot/{name}.txt'}
            write(out/'manifests'/f'{name}.json',rec); summary.append({k:v for k,v in rec.items() if k!='annotations'})
            review.extend({**b,'id':name,'flags':';'.join(b['flags'])} for b in q)
            print(f'YOLO_JOB={state} {name} boxes={len(q)} review={rec["review_boxes"]}',flush=True)
        csv_write(out/'summary.csv',summary,['id','material','effect','role','status','geometry_status','box_count','affected_boxes','review_boxes','render_sha256','label_sha256'])
        csv_write(out/'box_review.csv',review,['id','index','uid','object','class_id','class_name','rect','affected_roi','changed_gt4_pct','max_rgb','detail_ratio','mean_abs_rgb_delta','status','flags'])
        html_rows=['<!doctype html><meta charset="utf-8"><title>BVT YOLO pilot review</title><style>body{font:16px system-ui;background:#17191c;color:#eee;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}article{background:#24272c;padding:12px}img{width:100%}a{color:#9bd1ff}</style><h1>YOLO inherited boxes — review only</h1><p>Orange = optical review flag. Green = no flag, not human approval. One source group. No train/val split.</p><main>']
        for r in summary:
            name=html.escape(r['id']); html_rows.append(f'<article><h3>{name}</h3><a href="previews/{name}.png"><img loading="lazy" src="previews/{name}.png"></a><p>{r["status"]} · {r["review_boxes"]} flagged boxes</p><a href="manifests/{name}.json">Manifest</a></article>')
        (out/'index.html').write_text('\n'.join(html_rows)+'</main>',encoding='utf-8')
        report.update(status='AUDIT_ONLY_PASS' if a.audit_only else 'PASS_CANDIDATES',labels_status='NOT_PUBLISHED_AUDIT_ONLY' if a.audit_only else 'INHERITED_CANDIDATES_NOT_APPROVED',geometry_status=geom_status,matrix_pixel_pairs_verified=len(all_rows),jobs=len(rows),boxes_total=len(review),qa_only=sum(r['role']=='QA_ONLY' for r in summary),experimental=sum(r['role']=='EXPERIMENTAL' for r in summary),review_images=sum(r['status']=='REVIEW' for r in summary),review_box_flags=sum(r['review_boxes'] for r in summary),reference_clean_rgb_equal=True,reference_label_sha256=digest(ref['label']),train_val_split=None,jobs_summary=summary)
        write(out/'report.json',report); print('YOLO_MATRIX='+report['status'],flush=True)
    except Exception as exc:
        report.update(status='ERROR',labels_status='INVALID_INCOMPLETE_OUTPUT',error=str(exc)); write(out/'report.json',report); raise


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('YOLO_MATRIX=ERROR: '+str(exc),file=sys.stderr); sys.exit(1)
