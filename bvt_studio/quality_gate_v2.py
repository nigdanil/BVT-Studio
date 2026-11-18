"""Quality Gate v2: target-based optical selection with glass / SKU safeguards.

All image metrics are *proxies*. No OCR, trained perceptual model or physical
water simulation is implied. Images and masks use the bottom-up Blender pixel
convention. This module never reads or modifies YOLO annotation files.
"""
from math import isfinite

from .visual_quality import evaluate_candidate, _gradient

# The targets refer to optical-pass pixel change relative to the SAME atlas
# with optics disabled. Atlas density/streaks independently set water severity.
# These are initial QA policies, NOT empirically validated retail standards.
PROFILES = {
    'LIGHT': {
        'preset': 'LIGHT_CONDENSATION', 'density': .45, 'streaks': .10,
        'target_optical_changed_ratio': .0075, 'min_optical_changed_ratio': .001,
        'max_optical_changed_ratio': .018, 'max_bright_rim_ratio': .0015,
        'max_detail_loss_ratio': .30, 'max_sku_mean_delta': .09,
    },
    'MEDIUM': {
        'preset': 'HEAVY_CONDENSATION', 'density': .82, 'streaks': .30,
        'target_optical_changed_ratio': .0105, 'min_optical_changed_ratio': .002,
        'max_optical_changed_ratio': .024, 'max_bright_rim_ratio': .0025,
        'max_detail_loss_ratio': .35, 'max_sku_mean_delta': .12,
    },
    'HEAVY': {
        'preset': 'HEAVY_CONDENSATION', 'density': 1.25, 'streaks': .60,
        'target_optical_changed_ratio': .0145, 'min_optical_changed_ratio': .003,
        'max_optical_changed_ratio': .034, 'max_bright_rim_ratio': .004,
        'max_detail_loss_ratio': .40, 'max_sku_mean_delta': .15,
    },
}
OPTICAL_VARIANTS = {
    'gentle': {'lens': 1.08, 'edge': .45, 'glint': .55, 'micro': .12},
    'balanced': {'lens': 1.35, 'edge': .85, 'glint': 1.00, 'micro': .24},
    'strong': {'lens': 1.75, 'edge': 1.55, 'glint': 1.70, 'micro': .40},
}


def profile_config(name):
    if not isinstance(name, str) or name.upper() not in PROFILES:
        raise ValueError('Unknown Quality Gate profile; expected LIGHT, MEDIUM or HEAVY')
    return dict(PROFILES[name.upper()])


def validated_gate_settings(profile, overrides=None):
    """Prevent fail-open or invalid thresholds from entering a QA report."""
    result = profile_config(profile)
    editable = {'target_optical_changed_ratio', 'min_optical_changed_ratio',
                'max_optical_changed_ratio', 'max_bright_rim_ratio',
                'max_detail_loss_ratio', 'max_sku_mean_delta'}
    if overrides:
        if set(overrides) - editable:
            raise ValueError('Unknown or non-editable Quality Gate v2 threshold')
        result.update(overrides)
    for key in editable:
        value = result[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not isfinite(float(value)) or not 0 <= value <= 1):
            raise ValueError(key + ' must be a finite [0, 1] ratio')
    low, target, high = (result[x] for x in ('min_optical_changed_ratio',
                                               'target_optical_changed_ratio',
                                               'max_optical_changed_ratio'))
    if not 0 < low < target < high <= 1:
        raise ValueError('Expected 0 < minimum < target < maximum <= 1')
    if not 0 < result['max_bright_rim_ratio'] <= 1:
        raise ValueError('Bright-rim threshold must be positive')
    return result


def evaluate_quality_v2(optics_off_rgb, optics_on_rgb, glass_mask, *,
                        profile='MEDIUM', sku_roi=None, overrides=None,
                        enforce_target=True):
    """Assess one optics variant against target + leakage + detail/halo guards.

    The reference MUST be the same water atlas with optics OFF. This detects
    damage introduced by the optics pass but cannot certify real-world realism
    or total SKU legibility through the underlying water atlas.
    """
    import numpy as np
    cfg = validated_gate_settings(profile, overrides)
    # Reuse previous validated RGB/shape checks and the mask-aware leakage QA.
    legacy = evaluate_candidate(optics_off_rgb, optics_on_rgb, glass_mask,
                                sku_roi=sku_roi, limits={
                                    'max_bright_halo_ratio': 1.,
                                    'max_sku_detail_loss_ratio': 1.,
                                    'max_sku_mean_rgb_delta': 1.,
                                    'min_effect_changed_ratio': 0.,
                                    'max_leakage_ratio': .0005,
                                })
    old = np.asarray(optics_off_rgb, dtype=np.float32)
    new = np.asarray(optics_on_rgb, dtype=np.float32)
    active = np.asarray(glass_mask) > .02
    roi = active if sku_roi is None else (active & np.asarray(sku_roi, dtype=bool))
    ref_luma = np.dot(old, [0.2126, 0.7152, 0.0722])
    out_luma = np.dot(new, [0.2126, 0.7152, 0.0722])
    positive = out_luma - ref_luma
    # Much more sensitive than Step 4's .16 brightness delta: detects bright
    # contact arcs on already medium-bright product backgrounds.
    rim = (positive > .018) & (out_luma > .50) & active
    rim_ratio = float(np.count_nonzero(rim) / np.count_nonzero(active))
    g0, g1 = _gradient(ref_luma), _gradient(out_luma)
    significant = roi & (g0 >= max(.035, float(np.quantile(g0[roi], .70))))
    if np.any(significant):
        # A local 3x3 maximum allows ~1 px optical displacement. The metric
        # remains a gradient proxy, NOT OCR or SKU detection.
        h, w = g1.shape
        padded = np.pad(g1, 1, mode='edge')
        local = np.maximum.reduce([padded[dy:dy+h, dx:dx+w]
                                   for dy in range(3) for dx in range(3)])
        detail_loss = float(np.count_nonzero(significant & (local < g0 * .72)) /
                            np.count_nonzero(significant))
    else:
        detail_loss = 0.0
    changed = legacy['metrics']['effect_changed_ratio']
    sku_delta = legacy['metrics']['sku_mean_rgb_delta']
    leakage = legacy['metrics']['leakage_ratio']
    reasons = []
    if leakage > .0005:
        reasons.append(f'leakage_ratio={leakage:.6f} > 0.000500')
    if rim_ratio > cfg['max_bright_rim_ratio']:
        reasons.append(f'bright_rim_ratio={rim_ratio:.6f} > {cfg["max_bright_rim_ratio"]:.6f}')
    if detail_loss > cfg['max_detail_loss_ratio']:
        reasons.append(f'local_detail_loss_ratio={detail_loss:.6f} > {cfg["max_detail_loss_ratio"]:.6f}')
    if sku_delta > cfg['max_sku_mean_delta']:
        reasons.append(f'sku_mean_rgb_delta={sku_delta:.6f} > {cfg["max_sku_mean_delta"]:.6f}')
    if enforce_target and not cfg['min_optical_changed_ratio'] <= changed <= cfg['max_optical_changed_ratio']:
        reasons.append(f'optical_changed_ratio={changed:.6f} outside '
                       f'[{cfg["min_optical_changed_ratio"]:.6f}, {cfg["max_optical_changed_ratio"]:.6f}]')
    target = cfg['target_optical_changed_ratio']
    # A stronger effect is no longer rewarded automatically. Distance from the
    # calibrated target dominates; image-damage proxies break near ties.
    target_distance = abs(changed - target) / target
    score = (1. - target_distance
             - .18 * (rim_ratio / cfg['max_bright_rim_ratio'])
             - .18 * (detail_loss / max(cfg['max_detail_loss_ratio'], 1e-6))
             - .10 * (sku_delta / max(cfg['max_sku_mean_delta'], 1e-6))
             - 20. * leakage)
    metrics = dict(legacy['metrics'])
    metrics.update({
        'bright_rim_ratio_v2': rim_ratio,
        'local_detail_loss_ratio_v2': detail_loss,
        'optical_target_changed_ratio': target,
        'optical_target_distance_ratio': target_distance,
        'optical_target_band': [cfg['min_optical_changed_ratio'],
                                cfg['max_optical_changed_ratio']],
        'significant_sku_edge_pixels_v2': int(np.count_nonzero(significant)),
    })
    return {'profile': profile.upper(), 'accepted': not reasons,
            'reasons': reasons, 'score': float(score), 'metrics': metrics,
            'limits': cfg,
            'method_warning': 'Optics-only pixel/gradient proxies: not OCR, nor physical realism'}


def select_optics_v2(candidates):
    """Choose accepted, target-matched variant with deterministic tie-break."""
    passed = [(name, item) for name, item in candidates.items() if item['accepted']]
    passed.sort(key=lambda pair: (-pair[1]['score'], pair[0]))
    return passed[0][0] if passed else None


def assert_isolation(reference, candidate, pane_mask, *, limit=.0005):
    """Independently fail a leaked optical pass outside the pane's own mask."""
    from .precision_mask_qa import leakage_metrics
    if isinstance(limit, bool) or not isfinite(float(limit)) or not 0 <= limit <= 1:
        raise ValueError('Invalid isolation leakage limit')
    result = leakage_metrics(reference, candidate, pane_mask, guard_pixels=2)
    return {'accepted': result['leakage_ratio'] <= limit, **result}
