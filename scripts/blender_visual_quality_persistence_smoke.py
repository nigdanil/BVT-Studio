"""Reopen alpha.5-step4 scene and verify four independent packed panes."""
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

args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument('--blend', required=True)
p.add_argument('--report', default=None)
a = p.parse_args(args)
blend = Path(a.blend).resolve()
report_path = Path(a.report).resolve() if a.report else blend.with_name('visual_quality_report.json')
if not blend.is_file() or not report_path.is_file():
    raise AssertionError('Missing QA blend or report')
report = json.loads(report_path.read_text(encoding='utf-8'))
if report.get('stage') != 'alpha.5-step4':
    raise AssertionError('Unexpected report stage')
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene = bpy.context.scene
glasses = scene_glass(scene)
if len(glasses) != 4:
    raise AssertionError('Expected four saved glass surfaces')
if len({obj.get('bvt_glass_mask_image') for obj in glasses}) != 4:
    raise AssertionError('Four independent packed precision masks required')
for obj in glasses:
    mask = mask_image_for(obj)
    if not mask or not mask.packed_file:
        raise AssertionError('Missing packed mask for ' + obj.name)
    for kind, image in packed_maps_for(obj, mode='REALISTIC_ATLAS').items():
        if not image.packed_file or not image.use_fake_user:
            raise AssertionError(f'{obj.name}: missing packed {kind} atlas')
    if bool(optical_enabled(obj)) != bool(report.get('selected')):
        raise AssertionError(obj.name + ': optical status differs from report')
    nodes = obj.active_material.node_tree.nodes if obj.active_material else None
    if nodes is None or nodes.get('BVT_Precision_Final_Mask_Gate') is None:
        raise AssertionError(obj.name + ': precision mask gate missing')
    if report.get('selected') and nodes.get('BVT_Optical_Contact_Glass_Mask') is None:
        raise AssertionError(obj.name + ': optical shader missing')
print('BVT VISUAL QUALITY PERSISTENCE: OK — four packed atlas panes, masks and calibration state')
