#!/usr/bin/env python3
"""Build a compact QA ZIP, excluding .blend and repeated full-resolution renders."""
import argparse
import io
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
from PIL import Image
from bvt_yolo_matrix_propagation import ROOT, SCHEMA, need, read, existing_file, sha, digest


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--input-dir',type=Path,required=True); p.add_argument('--archive',type=Path,required=True); a=p.parse_args(argv)
    base=a.input_dir.resolve(); archive=a.archive.resolve(); qa=(ROOT/'qa_renders').resolve()
    need(base.is_relative_to(qa) and archive.is_relative_to(qa) and archive.suffix=='.zip' and not archive.is_relative_to(base) and not archive.exists(),'Use a new QA ZIP outside the input folder, under qa_renders')
    report=read(existing_file(base,'report.json')); need(report['schema']==SCHEMA and report['status']=='PASS_CANDIDATES' and report['geometry_status']=='PASS','Only pack a completed live-geometry candidate run')
    rows=report['jobs_summary']; need(len(rows)==report['jobs'] and len({r['id'] for r in rows})==len(rows),'Incomplete summary')
    files=['report.json','geometry.json','summary.csv','box_review.csv','blender.log','classes.json','reference/labels.txt','reference/manifest.json','reference/clean.png','reference/data.yaml']
    # Validate that all full-resolution candidates still match their report before packing.
    for r in rows:
        name=r['id']; need(r['image']==f'images/pilot/{name}.png' and r['labels']==f'labels/pilot/{name}.txt','Invalid candidate paths')
        need(sha(existing_file(base,r['image']))==r['render_sha256'] and sha(existing_file(base,r['labels']))==r['label_sha256'],'Candidate changed: '+name)
        files.extend([f'manifests/{name}.json',r['labels']]); existing_file(base,f'previews/{name}.png')
    manifest={}; archive.parent.mkdir(parents=True,exist_ok=True)
    tmp=archive.with_suffix('.zip.tmp'); need(not tmp.exists(),'Temporary archive exists')
    try:
        with ZipFile(tmp,'x',ZIP_DEFLATED) as z:
            def put(name,data):
                need(name not in manifest,'Duplicate archive member'); z.writestr(name,data); manifest[name]={'sha256':digest(data),'bytes':len(data)}
            for rel in files: put(rel,existing_file(base,rel).read_bytes())
            for r in rows:
                name=r['id']
                with Image.open(existing_file(base,f'previews/{name}.png')) as im:
                    im.thumbnail((1100,1100),Image.Resampling.LANCZOS); b=io.BytesIO(); im.convert('RGB').save(b,format='JPEG',quality=90,optimize=True);put(f'preview_jpeg/{name}.jpg',b.getvalue())
            z.writestr('archive_manifest.json',json.dumps({'schema':'bvt.yolo-matrix-qa-archive.v01','report_sha256':sha(base/'report.json'),'jobs':len(rows),'files':manifest,'note':'Review previews are resized JPEGs; full candidate PNGs and .blend remain in local output.'},indent=2,sort_keys=True))
        with ZipFile(tmp) as z: need(z.testzip() is None,'QA ZIP integrity check failed')
        tmp.rename(archive)
    except Exception:
        if tmp.exists(): tmp.unlink()
        raise
    print(f'QA_ARCHIVE={archive} ({archive.stat().st_size} bytes)')
    print('YOLO_QA_ARCHIVE=PASS')


if __name__=='__main__': main()
