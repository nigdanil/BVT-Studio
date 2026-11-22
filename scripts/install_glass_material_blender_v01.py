#!/usr/bin/env python3
"""Guarded integration of the new material module into the Step 1/2 checkout."""
from pathlib import Path
import argparse
import ast
import shutil
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
CHANGES={
'bvt_studio/__init__.py':[
('optical_water, visual_quality_ui\n','optical_water, visual_quality_ui, glass_material_ui\n'),
('visual_quality_ui, glass_v02_ui)','visual_quality_ui, glass_v02_ui, glass_material_ui)')],
'bvt_studio/common.py':[("            for node in mat.node_tree.nodes:\n                if node.type == 'TEX_IMAGE' and node.image is not None:","            # Keep dataset/export source provenance on the immutable original.\n            original = mat.node_tree.nodes.get('BVT_Material_Original')\n            if (obj.get('bvt_role') == 'planogram_image' and original is not None\n                    and original.type == 'TEX_IMAGE' and original.image is not None\n                    and original.get('bvt_material_original_v01') == 1):\n                return original.image\n            for node in mat.node_tree.nodes:\n                if node.type == 'TEX_IMAGE' and node.image is not None:")],
'bvt_studio/glass_realism.py':[("                return source, image\n","                from .glass_material_blender import effective_source_image\n                return source, effective_source_image(source, image)\n")],
}

def apply(root,dry=False):
    for name in ('glass_material_config.py','glass_materials.py','glass_material_builtin.py','glass_material_png.py','glass_material_geometry.py','glass_material_blender.py','glass_material_ui.py'):
        p=root/'bvt_studio'/name
        if not p.is_file(): raise ValueError('Missing Step 2 or Step 3 file: '+name)
        ast.parse(p.read_text('utf8'),filename=str(p))
    pending=[]
    for name,edits in CHANGES.items():
        p=root/name; before=p.read_text('utf8'); after=before
        for old,new in edits:
            if new in after: continue
            if after.count(old)!=1: raise ValueError('Refused unexpected source: '+name)
            after=after.replace(old,new,1)
        ast.parse(after,filename=name)
        if before!=after: pending.append((p,after))
    if pending and not dry:
        backup=root/'qa_renders/patch_backups'/('material_step3_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        for p,_ in pending:
            q=backup/p.relative_to(root);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        for p,after in pending: p.write_text(after,encoding='utf8',newline='\n')
        print('BACKUP='+str(backup))
    for p,_ in pending: print(('WOULD_UPDATE=' if dry else 'UPDATED=')+p.relative_to(root).as_posix())
    print('MATERIAL_INTEGRATION_PATCH='+('DRY_RUN_PASS' if dry else 'PASS'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dry-run',action='store_true');a=p.parse_args();apply(ROOT,a.dry_run)
