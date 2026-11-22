"""Four-glass Optical Water A/B calibration with real PNG and JSON evidence.

Runs the existing precision mask gallery as a fixture, then creates four
independent REALISTIC_ATLAS layers and compares *optics only* on one common
seed/atlas. YOLO TXT (optional) is read-only and used solely for detail ROI.
The tests are numerical proxies, NOT OCR or proof of physical realism.
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
from bvt_studio.realistic_atlas import generate_realistic_atlas
from bvt_studio.optical_water import set_optical_water
from bvt_studio.visual_quality import (evaluate_candidate, rank_candidates,
                                       validated_limits, yolo_roi_mask,
                                       fallback_glass_rois)
from bvt_studio.precision_mask_qa import leakage_metrics
from bvt_studio.common import image_from_mesh

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--photo', required=True)
parser.add_argument('--output', default=str(ROOT / 'qa_renders' / 'visual_quality_step4'))
parser.add_argument('--yolo-labels', default=None, help='Optional existing YOLO Detect TXT; read only')
parser.add_argument('--halo-limit', type=float, default=.06)
parser.add_argument('--detail-loss-limit', type=float, default=.45)
parser.add_argument('--leakage-limit', type=float, default=.0005)
parser.add_argument('--save-blend', action='store_true')
parser.add_argument('--strict', action='store_true', help='Exit nonzero when nothing passes')
opts = parser.parse_args(argv)
photo = Path(opts.photo).resolve()
if not photo.is_file():
    parser.error('Missing photo: ' + str(photo))
output = Path(opts.output).resolve()
output.mkdir(parents=True, exist_ok=True)
limits = validated_limits({
    'max_bright_halo_ratio': opts.halo_limit,
    'max_sku_detail_loss_ratio': opts.detail_loss_limit,
    'max_leakage_ratio': opts.leakage_limit,
})

# Reuse the actual four-pane grayscale shader masks, not a second approximate
# UV projection. It creates synthetic test apertures; real freezer segmentation
# must replace them for a production dataset.
fixture_script = ROOT / 'scripts' / 'blender_precision_mask_qa.py'
old_argv = sys.argv[:]
try:
    sys.argv = [str(fixture_script), '--', '--photo', str(photo),
                '--output', str(output), '--leakage-limit', str(opts.leakage_limit)]
    fixture = runpy.run_path(str(fixture_script), run_name='__main__')
finally:
    sys.argv = old_argv
scene = fixture['scene']
glasses = fixture['glasses']
render_to = fixture['render_to']
mask_renderings = fixture['mask_renderings']
rects = fixture['section_rects']
source = fixture['source']
source_rgb = fixture['source_rgb']
control = fixture['control']
allowed = mask_renderings['06_mask_debug.png'][:, :, 0]
if len(glasses) != 4:
    raise AssertionError('Expected four independent Glass objects')
h, w, _ = control.shape
if opts.yolo_labels:
    label_path = Path(opts.yolo_labels).resolve()
    if not label_path.is_file():
        raise FileNotFoundError('YOLO TXT not found: ' + str(label_path))
    sku_roi = yolo_roi_mask(w, h, label_path.read_text(encoding='utf-8'))
    roi_provenance = {'kind': 'existing_yolo_detect_txt', 'path': str(label_path)}
else:
    sku_roi = fallback_glass_rois(w, h, rects)
    roi_provenance = {'kind': 'central_glass_heuristic', 'warning': 'Not actual SKU annotations'}

settings = scene.bvt_studio
settings.artifact_preset = 'HEAVY_CONDENSATION'
fixture['apply_all']('HEAVY_CONDENSATION', 72)
for i, glass in enumerate(glasses):
    generate_realistic_atlas(glass, seed=72+i, resolution=256,
                             density=1.05, streaks=.45, tiling=1.45)
    set_optical_water(glass, False)
    if glass.active_material.node_tree.nodes.get('BVT_Precision_Final_Mask_Gate') is None:
        raise AssertionError(glass.name + ': lost Precision Mask gate')
base = render_to(output / '10_atlas_optics_off.png', scene)

# Variants affect only optical gains; the water atlas, seeds, glass placement
# and the four PNG precision masks remain identical throughout the comparison.
variants = {
    'gentle': {'lens': 1.08, 'edge': .45, 'glint': .55, 'micro': .12},
    'balanced': {'lens': 1.35, 'edge': .85, 'glint': 1.00, 'micro': .24},
    'strong': {'lens': 1.75, 'edge': 1.55, 'glint': 1.70, 'micro': .40},
}
results = {}
images = [base]
for i, (name, params) in enumerate(variants.items(), 11):
    for glass in glasses:
        set_optical_water(glass, True, **params)
    frame = render_to(output / f'{i:02d}_{name}.png', scene)
    images.append(frame)
    results[name] = {'optics': params, **evaluate_candidate(
        base, frame, allowed, sku_roi=sku_roi, limits=limits)}

selected = rank_candidates(results)
selected_config = variants[selected] if selected else None
for glass in glasses:
    set_optical_water(glass, False)

# For each section compare optics OFF/ON while every other pane is hidden.
# Use exact shader-mask grayscale PNG already produced by the earlier script.
per_glass = {}
for i, glass in enumerate(glasses, 1):
    old_hidden = {o: o.hide_render for o in glasses}
    try:
        for obj in glasses:
            obj.hide_render = (obj is not glass)
        isolated_off = render_to(output / f'20_isolated_off_{i:03d}.png', scene)
        if selected_config is not None:
            set_optical_water(glass, True, **selected_config)
        isolated_on = render_to(output / f'21_isolated_on_{i:03d}.png', scene)
        pane_mask = mask_renderings[f'mask_glass_{i:03d}.png'][:, :, 0]
        stats = leakage_metrics(isolated_off, isolated_on, pane_mask)
        per_glass[glass.name] = {
            'seed': 71+i, 'mask_image': glass.get('bvt_glass_mask_image'),
            'leakage': stats,
            'accepted': stats['leakage_ratio'] <= limits['max_leakage_ratio'],
        }
    finally:
        set_optical_water(glass, False)
        for obj, prior in old_hidden.items():
            obj.hide_render = prior

# Comparison montage and difference visualization; no Pillow required.
def save_rgb(path, rgb):
    height, width, channels = rgb.shape
    if channels != 3:
        raise ValueError('Expected RGB image')
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(rgb, 0, 1)
    image = bpy.data.images.new(path.stem, width=width, height=height, alpha=True)
    try:
        image.pixels.foreach_set(rgba.ravel())
        image.filepath_raw = str(path)
        image.file_format = 'PNG'
        image.save()
    finally:
        bpy.data.images.remove(image)

small = [img[::2, ::2] for img in images]
montage = np.concatenate((np.concatenate(small[:2], axis=1),
                          np.concatenate(small[2:], axis=1)), axis=0)
save_rgb(output / '30_visual_calibration_montage.png', montage)
if selected:
    candidate = images[1 + list(variants).index(selected)]
    heat = np.max(np.abs(base - candidate), axis=2)
    heat = np.clip(heat * 5, 0, 1)
    save_rgb(output / '31_selected_difference_5x.png',
             np.stack((heat, heat * .35, np.zeros_like(heat)), axis=2))

report = {
    'stage': 'alpha.5-step4',
    'base_commit': 'e9e56fb',
    'blender': bpy.app.version_string,
    'photo': str(photo), 'resolution': [w, h],
    'mask_provenance': 'synthetic_four_apertures_from_precision_mask_qa',
    'mask_warning': 'Not production segmentation of the actual refrigerator frame',
    'sku_roi': roi_provenance,
    'metrics_warning': 'Brightness/edge proxies are not OCR accuracy or perceptual realism scores',
    'limits': limits,
    'candidates': results,
    'selected': selected,
    'all_four_isolated_pass': all(r['accepted'] for r in per_glass.values()),
    'overall_accepted': bool(selected is not None and all(r['accepted'] for r in per_glass.values())),
    'per_glass': per_glass,
    'source_to_qa_control_max_rgb': float(np.max(np.abs(source_rgb-control))),
    'saved_blend': None,
}
if selected:
    for glass in glasses:
        set_optical_water(glass, True, **selected_config)
if opts.save_blend:
    image = image_from_mesh(source)
    if image:
        image.pack()
    filepath = output / 'visual_quality_smoke.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(filepath))
    report['saved_blend'] = str(filepath)
report_path = output / 'visual_quality_report.json'
report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
if not report['overall_accepted']:
    print('BVT VISUAL QUALITY: REJECT — inspect visual_quality_report.json')
    if opts.strict:
        raise AssertionError('No acceptable visual calibration or isolation leakage')
else:
    print('BVT VISUAL QUALITY: OK — selected=' + selected + ', four isolated panes checked')
print('VISUAL_QA_DIR=' + str(output))
