"""Real Blender EEVEE comparison: same atlas with optics OFF / ON / OFF.

Uses the alpha.5-step2 synthetic atlas gallery as a fixture, then renders a
strict A/B comparison with identical glass, seed, mask and illumination.
"""
import argparse
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import numpy as np
from bvt_studio.optical_water import set_optical_water, optical_enabled
from bvt_studio.droplet_maps import MODE_KEY, packed_maps_for, set_droplet_mode

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--photo', default=None)
parser.add_argument('--output', default=str(ROOT / 'qa_renders' / 'optical_water_step3'))
parser.add_argument('--save-blend', action='store_true')
options = parser.parse_args(args)
out = Path(options.output).resolve()
out.mkdir(parents=True, exist_ok=True)

# Reuse the already-tested photo ingestion, atlas generation and mask setup.
# Inner gallery does not save the scene; we save the final optical scene below.
script = ROOT / 'scripts' / 'blender_realistic_droplet_atlas_gallery.py'
old_argv = sys.argv[:]
try:
    sys.argv = [str(script), '--', '--output', str(out)]
    if options.photo:
        sys.argv.extend(['--photo', str(options.photo)])
    fixture = runpy.run_path(str(script), run_name='__main__')
finally:
    sys.argv = old_argv

first, second = fixture['first'], fixture['second']
render = fixture['render']
diff = fixture['diff']
assert first.get(MODE_KEY) == 'REALISTIC_ATLAS'
assert not optical_enabled(first)
other_material = second.active_material
other_matrix = second.matrix_world.copy()
map_names = {mode: {kind: image.name for kind, image in packed_maps_for(first, mode).items()}
             for mode in ('PHOTO_MAPS', 'REALISTIC_ATLAS')}
mask_name = first.get('bvt_glass_mask_image')

baseline = render('06_optical_off.png')
set_optical_water(first, True, lens=1.75, edge=1.55, glint=1.7, micro=.4)
assert optical_enabled(first)
assert first.active_material.node_tree.nodes.get('BVT_Optical_Contact_Glass_Mask')
assert first.active_material.node_tree.nodes.get('BVT_Optical_Refraction_Gain')
optical = render('07_optical_on.png')

# Disable must recover the exact old graph/material result, not just a weak effect.
set_optical_water(first, False, lens=1.75, edge=1.55, glint=1.7, micro=.4)
assert not optical_enabled(first)
assert first.active_material.node_tree.nodes.get('BVT_Optical_Contact_Glass_Mask') is None
restored = render('08_optical_restored.png')

change = diff(baseline, optical)
restore_delta = diff(baseline, restored)
if not change > 1e-6:
    raise AssertionError('Optical water ON did not change the render')
if restore_delta > (1.5 / 255.):
    raise AssertionError('Optical OFF did not restore the original render')
if second.active_material is not other_material:
    raise AssertionError('Optical water mutated the other glass material')
if any(abs(other_matrix[i][j] - second.matrix_world[i][j]) > 1e-6
       for i in range(4) for j in range(4)):
    raise AssertionError('Optical water changed the other glass geometry')
if first.get('bvt_glass_mask_image') != mask_name:
    raise AssertionError('Precision Mask changed')
for mode in map_names:
    if {kind: image.name for kind, image in packed_maps_for(first, mode).items()} != map_names[mode]:
        raise AssertionError('Optical water overwrote the ' + mode + ' bank')

# Mode isolation: optics are explicitly skipped for the user-supplied PHOTO_MAPS.
set_droplet_mode(first, 'PHOTO_MAPS')
if first.active_material.node_tree.nodes.get('BVT_Optical_Contact_Glass_Mask'):
    raise AssertionError('Optical material leaked into PHOTO_MAPS')
set_droplet_mode(first, 'REALISTIC_ATLAS')
set_optical_water(first, True, lens=1.75, edge=1.55, glint=1.7, micro=.4)
if first.active_material.node_tree.nodes.get('BVT_Optical_Contact_Glass_Mask') is None:
    raise AssertionError('Optical material not restored after mode switching')

report = {'stage':'v0.4.0-alpha.5-step3',
          'source': str(options.photo) if options.photo else 'synthetic_checker',
          'atlas_unchanged': True, 'precision_mask_unchanged': True,
          'photo_bank_unchanged': True, 'other_glass_unchanged': True,
          'optical_parameters':{'lens':1.75,'edge':1.55,'glint':1.7,'micro':.4},
          'metrics':{'optical_vs_baseline_mean_abs_rgb':change,
                     'restored_vs_baseline_mean_abs_rgb':restore_delta},
          'no_real_photo_atlas': True,
          'blender': bpy.app.version_string}
(out / 'optical_water_manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
if options.save_blend:
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'optical_water_smoke.blend'))
print('BVT OPTICAL WATER: OK — atlas-only optics, reversible A/B, packed maps, precision mask')
print('OPTICAL_QA_DIR=' + str(out))
