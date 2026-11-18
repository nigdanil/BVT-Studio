#!/usr/bin/env python3
"""Safe, idempotent v0.2.1 gallery QA source patch; zero git operations."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'patches'/'bvt_glass_effect_gallery_v02.py'
TARGET=ROOT/'scripts'/'bvt_glass_effect_gallery_v02.py'
OLD_SHA='647df147479ba600335783d8e00ca878328beaad35e442ab7fd6f5c01134c0de'
NEW_SHA='6ac918a017d406a5c73204c4266a9b3fe861f4759cb0cdb35860c8a4301b5056'
EXPECTED_BRANCH='feature/photorealistic-droplets-v05'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def command(*cmd):
    return subprocess.check_output(cmd,cwd=ROOT,text=True).strip()

def main():
    branch=command('git','branch','--show-current')
    head=command('git','rev-parse','--short','HEAD')
    print('BRANCH='+branch,'HEAD='+head)
    if branch!=EXPECTED_BRANCH:
        raise SystemExit('REFUSED: unexpected branch; no changes made')
    if not PATCH.is_file() or sha(PATCH)!=NEW_SHA:
        raise SystemExit('REFUSED: v0.2.1 patch file absent/modified')
    if not TARGET.is_file():
        raise SystemExit('REFUSED: v0.2 gallery script absent')
    current=sha(TARGET)
    if current==NEW_SHA:
        print('ALREADY_PATCHED=OK')
        return
    if current!=OLD_SHA:
        raise SystemExit('REFUSED: existing gallery script differs from known v0.2 version; no overwrite')
    # Backups stay under QA output, separate from the source code.
    backup=ROOT/'qa_renders'/'patch_backups'/'bvt_glass_effect_gallery_v02_pre_v021.py'
    backup.parent.mkdir(parents=True,exist_ok=True)
    if backup.exists() and sha(backup)!=OLD_SHA:
        raise SystemExit('REFUSED: backup exists but differs from source')
    if not backup.exists():
        shutil.copy2(TARGET,backup)
    TARGET.write_bytes(PATCH.read_bytes())
    if sha(TARGET)!=NEW_SHA:
        raise SystemExit('ERROR: patch copy failed hash verification')
    print('WATER_QA_V021_PATCH=OK')
    print('BACKUP='+str(backup))
    print('UPDATED='+str(TARGET))

if __name__=='__main__':main()
