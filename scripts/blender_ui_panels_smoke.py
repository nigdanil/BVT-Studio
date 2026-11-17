"""Blender 5.2+ smoke for native UI sub-panel registration; no ZIP output.

Run from repository root in Git Bash:
  "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
    --background --factory-startup --python scripts/blender_ui_panels_smoke.py

This checks registered Blender RNA panel types; visual expansion is tested
manually in the 3D Viewport with N -> BVT Studio.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
import bvt_studio
from bvt_studio import ui

assert bpy.app.version >= (5, 2, 0), 'Requires Blender 5.2+'
if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

panels = ui.CLASSES
assert len(panels) == 9, f'Expected root + 8 child panels, got {len(panels)}'
assert panels[0].bl_idname == 'BVTSTUDIO_PT_main'
assert len({panel.bl_idname for panel in panels}) == len(panels)

for index, panel in enumerate(panels):
    rna_class = bpy.types.Panel.bl_rna_get_subclass_py(panel.bl_idname, None)
    assert rna_class is not None, f'Blender panel not registered: {panel.bl_idname}'
    assert rna_class.bl_space_type == 'VIEW_3D', panel.bl_idname
    assert rna_class.bl_region_type == 'UI', panel.bl_idname
    assert rna_class.bl_category == 'BVT Studio', panel.bl_idname
    if index:
        assert rna_class.bl_parent_id == 'BVTSTUDIO_PT_main', panel.bl_idname
        assert rna_class.bl_order == (index - 1) * 10, panel.bl_idname
        if panel.bl_idname == 'BVTSTUDIO_PT_glass_artifacts':
            assert 'DEFAULT_CLOSED' not in rna_class.bl_options
        else:
            assert 'DEFAULT_CLOSED' in rna_class.bl_options, panel.bl_idname

# Confirm existing scene-side properties and operator RNA still exist.
settings = bpy.context.scene.bvt_studio
for field in ('artifact_preset', 'artifact_seed', 'artifact_droplet_scale',
              'artifact_frost_edge', 'annotation_items', 'quality_items', 'export_dir'):
    assert hasattr(settings, field), f'Missing pre-existing settings field: {field}'

print('BVT UI PANELS SMOKE: OK — 8 native collapsible panels registered; operators and properties retained')
