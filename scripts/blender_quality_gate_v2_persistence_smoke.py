"""Open Step5 .blend and verify four independent packed masks and atlas banks."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
from bvt_studio.droplet_maps import packed_maps_for
from bvt_studio.glass_mask import mask_image_for
from bvt_studio.glass import scene_glass
from bvt_studio.optical_water import optical_enabled

argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument('--blend', required=True)
p.add_argument('--report', default=None)
opts = p.parse_args(argv)
blend = Path(opts.blend).resolve()
report_path = Path(opts.report).resolve() if opts.report else blend.with_name('quality_gate_v2_report.json')
if not blend.is_file() or not report_path.is_file():
    raise AssertionError('Missing Quality Gate v2 blend or JSON report')
report = json.loads(report_path.read_text(encoding='utf-8'))
if report.get('stage') != 'alpha.5-step5':
    raise AssertionError('Unexpected Quality Gate report stage')
if not report.get('profiles'):
    raise AssertionError('No tested profiles in report')
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene = bpy.context.scene
profile = next(reversed(report['profiles']))
chosen = report['profiles'][profile].get('selected')
if (scene.get('bvt_quality_gate_v2_profile') != profile or
        scene.get('bvt_quality_gate_v2_selection') != (chosen or '') or
        bool(scene.get('bvt_quality_gate_v2_accepted')) != bool(report['profiles'][profile]['accepted'])):
    raise AssertionError('Saved profile / selection does not match report')
glasses = scene_glass(scene)
if len(glasses) != 4 or len({o.get('bvt_glass_mask_image') for o in glasses}) != 4:
    raise AssertionError('Expected four independently masked panes')
for glass in glasses:
    mask = mask_image_for(glass)
    if mask is None or mask.packed_file is None:
        raise AssertionError(glass.name + ': precision mask not packed')
    bank = packed_maps_for(glass, mode='REALISTIC_ATLAS')
    if len(bank) != 3 or any(not x.packed_file or not x.use_fake_user for x in bank.values()):
        raise AssertionError(glass.name + ': atlas bank missing after reopen')
    if bool(optical_enabled(glass)) != bool(chosen):
        raise AssertionError(glass.name + ': optical state not restored')
    nodes = glass.active_material.node_tree.nodes if glass.active_material else None
    if nodes is None or nodes.get('BVT_Precision_Final_Mask_Gate') is None:
        raise AssertionError(glass.name + ': missing precision mask gate')
print('BVT QUALITY GATE V2 PERSISTENCE: OK — four packed atlas panes, masks and selected profile')
