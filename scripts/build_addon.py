#!/usr/bin/env python3
"""Create installable legacy Blender 5.2 add-on ZIP from source files."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import ast

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'bvt_studio'
DEST = ROOT / 'dist' / 'BVT_Studio_Blender_Addon_v0.2.2.zip'

def build():
    sources = sorted(PACKAGE.rglob('*.py'))
    if not any(p.name == '__init__.py' for p in sources):
        raise RuntimeError('Expected package bvt_studio/__init__.py')
    for path in sources:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(DEST, 'w', ZIP_DEFLATED, compresslevel=9) as z:
        for path in sources:
            z.write(path, arcname=str(path.relative_to(ROOT)).replace('\\', '/'))
    with ZipFile(DEST) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError('Broken ZIP entry: ' + bad)
    print(f'Built: {DEST} ({DEST.stat().st_size} bytes, {len(sources)} Python files)')
    return DEST

if __name__ == '__main__':
    build()
