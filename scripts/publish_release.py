#!/usr/bin/env python3
"""Explicitly create a GitHub draft release from a verified local build; never push or publish automatically."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from validate_examples import ROOT, need, sha
from build_release import ARCHIVES

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--version',required=True);p.add_argument('--approve-assets',action='store_true');a=p.parse_args()
    need(a.approve_assets,'Confirm rights to redistribute the example assets with --approve-assets')
    need(re.fullmatch(r'v[0-9](?:[0-9A-Za-z.-]{0,62}[0-9A-Za-z])?',a.version) is not None,'Invalid version')
    d=ROOT/'dist/releases'/a.version;m=json.loads((d/'release_manifest.json').read_text('utf-8'))
    need(m['version']==a.version and m['scenes_rendered']==m['scenes_reopened']==13 and m['water_null_pass']==7,'Incomplete release manifest')
    need({x['name'] for x in m['archives']}==set(ARCHIVES),'Archive list mismatch')
    for x in m['archives']: need(sha(d/x['name'])==x['sha256'] and (d/x['name']).stat().st_size==x['bytes'],'Archive hash mismatch: '+x['name'])
    repo='nigdanil/BVT-Studio'; env=None
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    need(git('rev-parse','HEAD')==m['commit'] and not git('status','--porcelain'),'HEAD/working tree differs from release')
    branch=git('branch','--show-current');need(bool(branch),'Detached HEAD is not supported for local publication')
    remote=git('ls-remote','origin','refs/heads/'+branch).split();need(bool(remote) and remote[0]==m['commit'],'Push release commit first')
    need(not git('ls-remote','--tags','origin','refs/tags/'+a.version),'Tag already exists; refuse to overwrite')
    files=[d/n for n in (*ARCHIVES,'release_manifest.json','SHA256SUMS.txt')]
    subprocess.run(['gh','release','create',a.version,*map(str,files),'--repo',repo,'--target',m['commit'],'--title','BVT Studio '+a.version,'--notes','Experimental synthetic demo: 13 ready-to-open Blender scenes, seven calibrated water modes, packed resources. No real-data or YOLO accuracy validation.','--draft','--prerelease'],cwd=ROOT,check=True)
    print('DRAFT_RELEASE_CREATED=OK')
if __name__=='__main__':main()
