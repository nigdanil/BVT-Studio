#!/usr/bin/env python3
"""Read-only manifest acceptance for v0.2.1 render/artifact QA; no Blender."""
import argparse
import json
from pathlib import Path
import sys

REQUIRED=('06_microbeads_only','07_macro_droplets_only','08_running_water_only',
          '09_combined_water_no_optics','10_combined_water_optics',
          '11_heavy_running_water','12_stress_optics')
EVENT_EXPECTED={
    '06_microbeads_only':('micro',),
    '07_macro_droplets_only':('macro',),
    '08_running_water_only':('streak',),
    '09_combined_water_no_optics':('macro','micro','streak'),
    '10_combined_water_optics':('macro','micro','streak'),
    '11_heavy_running_water':('streak',),
    '12_stress_optics':('macro','micro','streak'),
}

def inspect(root):
    problems=[]
    for mode in REQUIRED:
        folder=root/mode
        for name in ('render.png','scene.blend','preset_without_water.png',
                     'zero_water_rebuild.png','manifest.json'):
            p=folder/name
            if not p.is_file() or p.stat().st_size==0:
                problems.append(mode+': missing '+name)
        path=folder/'manifest.json'
        if not path.is_file():continue
        try: j=json.loads(path.read_text('utf8'))
        except Exception as e:
            problems.append(mode+': invalid manifest '+str(e));continue
        z=j.get('zero_water_test') or {}
        q=j.get('quality') or {}
        if z.get('status')!='PASS' or z.get('changed_pixels_gt_4_255')!=0:
            problems.append(mode+': zero-water null test missing/failing')
        if j.get('calibration')!='v0.2.1_matched_neutral_realistic_atlas':
            problems.append(mode+': manifest calibration is not v0.2.1')
        if q.get('baseline_mode')!='REALISTIC_ATLAS_NEUTRAL_SAME_SHADER':
            problems.append(mode+': incorrect comparison baseline')
        if q.get('leakage_pixels_beyond_3px_geometry_guard')!=0:
            problems.append(mode+': leakage detected')
        panes=q.get('per_glass_event_visibility_proxy') or []
        if len(panes)!=4:
            problems.append(mode+': expected 4 glass panes')
            continue
        for kind in EVENT_EXPECTED[mode]:
            total=sum(p[kind]['generated'] for p in panes)
            visible=sum(p[kind]['visible_proxy'] for p in panes)
            if total<=0:problems.append(mode+': generated no '+kind)
            if visible<=0:problems.append(mode+': no locally visible '+kind)
            print('QA_EVENT',mode,kind,visible,'/',total)
        if mode=='12_stress_optics':
            if not all(p['stress'] for p in j.get('panes',[])):
                problems.append(mode+': stress flag not recorded')
        if any(not p.get('shader_topology_unchanged') for p in j.get('panes',[])):
            problems.append(mode+': shader topology mismatch')
            if any(not p.get('renderer_controls_unchanged') for p in j.get('panes',[])):
                problems.append(mode+': renderer controls mismatch')
        print('QA',mode,'change_ratio=',q.get('changed_ratio_in_rects'),
              'null=',z.get('status'))
    return problems

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',default='D:/BVT-Studio/qa_renders/effects_gallery_v021')
    a=p.parse_args()
    problems=inspect(Path(a.output))
    for issue in problems:print('FAILED:',issue,file=sys.stderr)
    if problems:raise SystemExit(2)
    print('GALLERY_V021_MANIFEST_QA=PASS')
if __name__=='__main__':main()
