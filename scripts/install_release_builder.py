#!/usr/bin/env python3
"""Wire example validation into existing CI and add release instructions to README."""
from pathlib import Path
import hashlib
import shutil
import subprocess
from validate_examples import ROOT, validate, need

MARKER='<!-- bvt-demo-release-v1 -->'
SECTION='''
<!-- bvt-demo-release-v1 -->
## Ready-to-open demo and release downloads

See [GitHub Releases](https://github.com/nigdanil/BVT-Studio/releases) for published
pre-release packages (when available). Install the add-on ZIP, extract the gallery
ZIP, then open `BVT_Studio_Effects_Gallery/index.html` or any `scene.blend` in
Blender 5.2.3. The gallery has 13 independently reopenable scenes; the source image,
glass masks and water maps are packed in the scenes. All inputs are also available
under [`examples/freezer_planogram/`](examples/freezer_planogram/).

Build the full demo with `python scripts/build_release.py --version <new-tag> --blender <path>`.
See [Release Builder](docs/RELEASE_BUILDER_V01.md) for QA, checksums and publishing a
**draft** prerelease. The synthetic fixture is not real-world photorealism or YOLO
accuracy validation. Generated runs stay in `qa_renders/`; released ZIPs are not
committed to the source tree.
<!-- /bvt-demo-release-v1 -->
'''

def main():
    validate(ROOT/'examples/freezer_planogram')
    workflow=ROOT/'.github/workflows/check.yml'; readme=ROOT/'README.md'
    old=workflow.read_text('utf-8'); anchor='      - name: Static and numerical tests\n'
    step='      - name: Validate bundled examples\n        run: python scripts/validate_examples.py\n'
    if step not in old:
        need(old.count(anchor)==1,'CI anchor missing/ambiguous; inspect workflow manually')
        new=old.replace(anchor,step+anchor,1)
    else: new=old
    text=readme.read_text('utf-8'); updated=text if MARKER in text else text.rstrip()+'\n\n'+SECTION.lstrip()
    for p,s,prev in ((workflow,new,old),(readme,updated,text)):
        if s!=prev:
            backup=ROOT/'qa_renders/patch_backups/release_builder_v01'/p.relative_to(ROOT)
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): shutil.copy2(p,backup)
            p.write_text(s,encoding='utf-8',newline='\n'); print('UPDATED='+str(p.relative_to(ROOT)))
    duplicate=ROOT/'scripts/setup_bvt_examples copy.py'; canonical=ROOT/'scripts/setup_bvt_examples.py'
    if duplicate.exists():
        if canonical.exists() and duplicate.read_bytes()==canonical.read_bytes(): duplicate.unlink();print('DUPLICATE_REMOVED=OK')
        else: print('DUPLICATE_DIFFERS=REVIEW_MANUALLY')
    print('RELEASE_SETUP=OK')
if __name__=='__main__':main()
