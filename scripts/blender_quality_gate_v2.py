"""Blender Quality Gate v2: target-based LIGHT/MEDIUM/HEAVY water QA.

Run via blender --background --python scripts/blender_quality_gate_v2.py --
   --photo PATH --output DIR [--yolo-labels PATH] [--save-blend] [--strict]

The mask fixture is synthetic; replace its masks with verified segmentation
for production photos. The gradient metric is not OCR recognition accuracy.
"""
import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import numpy as np
from bvt_studio.common import image_from_mesh
from bvt_studio.optical_water import set_optical_water
from bvt_studio.realistic_atlas import generate_realistic_atlas
from bvt_studio.quality_gate_v2 import (PROFILES, OPTICAL_VARIANTS,
                                       evaluate_quality_v2, select_optics_v2,
                                       assert_isolation)
from bvt_studio.visual_quality import yolo_roi_mask, fallback_glass_rois

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser(description='Quality Gate v2 — target-based optics QA')
parser.add_argument('--photo', required=True)
parser.add_argument('--output', default=str(ROOT / 'qa_renders' / 'quality_gate_step5'))
parser.add_argument('--yolo-labels', default=None, help='Existing YOLO Detect TXT, read-only')
parser.add_argument('--profile', default='ALL', choices=('ALL', 'LIGHT', 'MEDIUM', 'HEAVY'))
parser.add_argument('--save-blend', action='store_true')
parser.add_argument('--strict', action='store_true', help='Fail if any profile or glass QA rejects')
opts = parser.parse_args(args)
photo, out = Path(opts.photo).resolve(), Path(opts.output).resolve()
if not photo.is_file():
    parser.error('Missing photo: ' + str(photo))
out.mkdir(parents=True, exist_ok=True)

# Re-use the shader-rendered four-pane masks and 0-delta QA reference from Step 4.
# No parallel mask projection can silently disagree with the glass shader.
fixture_script = ROOT / 'scripts' / 'blender_precision_mask_qa.py'
old_argv = sys.argv[:]
try:
    sys.argv = [str(fixture_script), '--', '--photo', str(photo), '--output', str(out)]
    fixture = runpy.run_path(str(fixture_script), run_name='__main__')
finally:
    sys.argv = old_argv
scene = fixture['scene']
glasses = fixture['glasses']
render_to = fixture['render_to']
mask_renderings = fixture['mask_renderings']
control = fixture['control']
rects = fixture['section_rects']
if len(glasses) != 4:
    raise AssertionError('Quality Gate v2 requires exactly four pane masks')
allowed = mask_renderings['06_mask_debug.png'][:, :, 0]
h, w = allowed.shape
label_sha256 = None
if opts.yolo_labels:
    yolo = Path(opts.yolo_labels).resolve()
    if not yolo.is_file():
        parser.error('YOLO labels missing: ' + str(yolo))
    raw = yolo.read_bytes()
    label_sha256 = hashlib.sha256(raw).hexdigest()
    sku_roi = yolo_roi_mask(w, h, raw.decode('utf-8'))
    roi_provenance = {'source': 'existing_yolo_detect_txt', 'path': str(yolo),
                      'sha256': label_sha256}
else:
    sku_roi = fallback_glass_rois(w, h, rects)
    roi_provenance = {'source': 'central_glass_heuristic',
                      'warning': 'Not product bounding boxes: supply --yolo-labels for SKU ROI QA'}


def save_rgb(path, rgb):
    height, width, ch = rgb.shape
    if ch != 3:
        raise ValueError('Expected RGB')
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(rgb, 0, 1)
    img = bpy.data.images.new('BVT_QGv2_Export', width=width, height=height, alpha=True)
    try:
        img.pixels.foreach_set(rgba.ravel())
        img.file_format = 'PNG'
        img.filepath_raw = str(path)
        img.save()
    finally:
        bpy.data.images.remove(img)


profiles_to_run = list(PROFILES) if opts.profile == 'ALL' else [opts.profile]
all_reports = {}
selected_gallery = [control]
last_profile = None
for profile in profiles_to_run:
    cfg = PROFILES[profile]
    # Each dataset severity has its own atlas density/streaks, while the seed,
    # glass geometry, camera, image, and Precision Masks stay fixed.
    fixture['apply_all'](cfg['preset'], 72)
    for idx, glass in enumerate(glasses):
        generate_realistic_atlas(glass, seed=72+idx, resolution=256,
                                 density=cfg['density'], streaks=cfg['streaks'],
                                 tiling=1.45)
        set_optical_water(glass, False)
        if glass.active_material.node_tree.nodes.get('BVT_Precision_Final_Mask_Gate') is None:
            raise AssertionError(glass.name + ': precision mask bypassed')

    root = profile.lower()
    baseline = render_to(out / (root + '_00_optics_off.png'), scene)
    condensation_changed = float(np.count_nonzero(
        (np.max(abs(baseline-control), axis=2) > 4/255) & (allowed > .02)) /
        np.count_nonzero(allowed > .02))
    candidate_reports = {}
    frames = {}
    for i, (name, params) in enumerate(OPTICAL_VARIANTS.items(), 1):
        for glass in glasses:
            set_optical_water(glass, True, **params)
        candidate = render_to(out / f'{root}_{i:02d}_{name}.png', scene)
        frames[name] = candidate
        candidate_reports[name] = evaluate_quality_v2(
            baseline, candidate, allowed, profile=profile, sku_roi=sku_roi)

    selected = select_optics_v2(candidate_reports)
    for glass in glasses:
        set_optical_water(glass, False)

    # Four isolated render pairs for the chosen setting: no other glass may
    # contribute, and leakage is assessed against this pane's REAL mask PNG.
    isolation = {}
    for idx, glass in enumerate(glasses, 1):
        hidden_before = {item: item.hide_render for item in glasses}
        try:
            for item in glasses:
                item.hide_render = item is not glass
            off = render_to(out / f'{root}_20_glass_{idx:03d}_off.png', scene)
            if selected is not None:
                set_optical_water(glass, True, **OPTICAL_VARIANTS[selected])
            on = render_to(out / f'{root}_21_glass_{idx:03d}_on.png', scene)
            own_mask = mask_renderings[f'mask_glass_{idx:03d}.png'][:, :, 0]
            qa = assert_isolation(off, on, own_mask)
            # Detail, local brightness and optical intensity inside THIS pane.
            # Do not enforce a global target on a single section: its SKU mix
            # and density can differ. Still flag any halo/detail violations.
            if selected is not None:
                try:
                    detail = evaluate_quality_v2(off, on, own_mask,
                        profile=profile, sku_roi=sku_roi & (own_mask > .02),
                        enforce_target=False)
                    qa['local_quality'] = detail
                    qa['accepted'] = bool(qa['accepted'] and detail['accepted'])
                except ValueError as exc:
                    qa['local_quality'] = {'accepted': False, 'reasons': [str(exc)]}
                    qa['accepted'] = False
            isolation[glass.name] = {'seed': 71+idx, **qa}
        finally:
            set_optical_water(glass, False)
            for item, hidden in hidden_before.items():
                item.hide_render = hidden

    accepted = bool(selected and all(x['accepted'] for x in isolation.values()))
    all_reports[profile] = {
        'condensation_preset': cfg['preset'], 'density': cfg['density'],
        'streaks': cfg['streaks'], 'seed_per_glass': [72,73,74,75],
        'condensation_changed_ratio_vs_qa_control': condensation_changed,
        'reference_image': f'{root}_00_optics_off.png',
        'candidates': candidate_reports, 'selected': selected,
        'selected_optics': OPTICAL_VARIANTS[selected] if selected else None,
        'per_glass': isolation, 'accepted': accepted,
    }
    selected_gallery.append(frames[selected] if selected else baseline)
    if selected:
        for glass in glasses:
            set_optical_water(glass, True, **OPTICAL_VARIANTS[selected])
    last_profile = profile
    print('BVT QUALITY GATE V2 PROFILE: ' + profile + ' — ' +
          ('PASS' if accepted else 'REJECT') + ' selected=' + str(selected))

# Compact independent selected-per-profile comparison; black padding for
# single-profile runs. No UI dependencies or extra pip packages.
small = [np.asarray(image, dtype=np.float32)[::2,::2] for image in selected_gallery]
while len(small) < 4:
    small.append(np.zeros_like(small[0]))
comparison = np.concatenate((np.concatenate(small[:2], axis=1),
                             np.concatenate(small[2:4], axis=1)), axis=0)
save_rgb(out / '40_quality_gate_v2_montage.png', comparison)

if opts.yolo_labels:
    if hashlib.sha256(yolo.read_bytes()).hexdigest() != label_sha256:
        raise AssertionError('YOLO annotation changed during read-only QA')

report = {
    'stage': 'alpha.5-step5', 'base_commit': 'e44e213',
    'blender': bpy.app.version_string, 'photo': str(photo),
    'resolution': [w,h], 'mask_source': 'shader-derived four-pane grayscale PNG',
    'mask_warning': 'Fixture apertures are synthetic; not verified product-frame segmentation',
    'sku_roi': roi_provenance, 'metric_warning':
        'Pixel/brightness/gradient proxies are not OCR recognition or perceptual realism',
    'selection_policy': 'target_distance_penalized_with_bright_rims_detail_loss_leakage',
    'profiles': all_reports,
    'overall_accepted': all(item['accepted'] for item in all_reports.values()),
    'saved_blend': None,
}
# Persist only the final profile's atlas, masks and selection in .blend.
scene['bvt_quality_gate_v2_profile'] = last_profile or ''
scene['bvt_quality_gate_v2_selection'] = all_reports[last_profile]['selected'] or ''
scene['bvt_quality_gate_v2_accepted'] = bool(all_reports[last_profile]['accepted'])
if opts.save_blend:
    image = image_from_mesh(fixture['source'])
    if image:
        image.pack()
    file_path = out / 'quality_gate_v2_smoke.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(file_path))
    report['saved_blend'] = str(file_path)
(out / 'quality_gate_v2_report.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
if report['overall_accepted']:
    print('BVT QUALITY GATE V2: OK — target-based profiles, four-pane QA')
else:
    print('BVT QUALITY GATE V2: REJECT — inspect quality_gate_v2_report.json')
    if opts.strict:
        raise AssertionError('Some Quality Gate v2 profiles rejected')
print('QUALITY_GATE_V2_DIR=' + str(out))
