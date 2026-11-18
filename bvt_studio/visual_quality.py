"""Image-based visual gate for optical water on retail glass.

Pure NumPy logic, callable from Blender or regular Python. The `detail_loss`
score is a gradient/edge proxy for package legibility, NOT text recognition.
The `bright_halo_ratio` score is a high-luminance outlier proxy, NOT a
geometric detector of circular halos. Report both limitations explicitly.
"""
from math import isfinite

DEFAULT_LIMITS = {
    'max_leakage_ratio': .0005,
    'max_bright_halo_ratio': .06,
    'max_sku_detail_loss_ratio': .45,
    'max_sku_mean_rgb_delta': .14,
    'min_effect_changed_ratio': .00005,
}


def validated_limits(overrides=None):
    result = dict(DEFAULT_LIMITS)
    if overrides:
        if set(overrides) - set(result):
            raise ValueError('Unknown visual QA threshold(s)')
        result.update(overrides)
    for name, value in result.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{name} must be a finite numeric ratio')
        if not isfinite(float(value)) or not 0.0 <= value <= 1.0:
            raise ValueError(f'{name} must be in [0, 1]')
    return result


def yolo_roi_mask(width, height, text):
    """Parse existing YOLO Detect TXT (class cx cy w h) into a screen ROI.

    Blender image pixel arrays use bottom-up rows, YOLO labels top-down y.
    No classes, coordinates or annotation files are ever modified.
    """
    import numpy as np
    if width < 1 or height < 1:
        raise ValueError('Invalid image size')
    result = np.zeros((height, width), dtype=bool)
    found = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f'YOLO line {lineno} needs class cx cy w h')
        try:
            label = int(fields[0])
            cx, cy, bw, bh = map(float, fields[1:])
        except ValueError as exc:
            raise ValueError(f'Invalid YOLO box on line {lineno}') from exc
        if label < 0 or any(not isfinite(x) for x in (cx, cy, bw, bh)):
            raise ValueError(f'Invalid YOLO box on line {lineno}')
        if not (0 < bw <= 1 and 0 < bh <= 1 and
                bw/2 <= cx <= 1-bw/2 and bh/2 <= cy <= 1-bh/2):
            raise ValueError(f'Out-of-bounds YOLO box on line {lineno}')
        x0 = max(0, int((cx - bw/2) * width))
        x1 = min(width, int((cx + bw/2) * width + .999999))
        # Convert top-down image coordinate into bottom-up Blender pixels.
        y0 = max(0, int((1. - cy - bh/2) * height))
        y1 = min(height, int((1. - cy + bh/2) * height + .999999))
        result[y0:y1, x0:x1] = True
        found += 1
    if found == 0:
        raise ValueError('No YOLO boxes in supplied labels')
    return result


def fallback_glass_rois(width, height, rects, inset=.07):
    """Heuristic central part of each glass, for QA without YOLO boxes."""
    import numpy as np
    mask = np.zeros((height, width), dtype=bool)
    for x0, y0, x1, y1 in rects:
        dx = (x1 - x0) * inset
        dy = (y1 - y0) * inset
        xa, xb = int((x0 + dx) * width), int((x1 - dx) * width)
        ya, yb = int((y0 + dy) * height), int((y1 - dy) * height)
        mask[ya:yb, xa:xb] = True
    return mask


def _gradient(image):
    import numpy as np
    y = np.asarray(image, dtype=np.float32)
    result = np.zeros(y.shape, dtype=np.float32)
    result[:, 1:] = np.maximum(result[:, 1:], np.abs(y[:, 1:] - y[:, :-1]))
    result[1:, :] = np.maximum(result[1:, :], np.abs(y[1:, :] - y[:-1, :]))
    return result


def evaluate_candidate(reference_rgb, candidate_rgb, allowed, *, sku_roi=None, limits=None):
    """Calculate bounded, interpretable proxy scores and pass/fail reasons.

    `reference_rgb` is the SAME atlas with optics disabled, not the raw source;
    this isolates damage from the optical pass. A 2-pixel guard on forbidden
    mask edges avoids false rasterization leaks, without hiding interior leaks.
    """
    import numpy as np
    from .precision_mask_qa import leakage_metrics
    thresholds = validated_limits(limits)
    reference = np.asarray(reference_rgb, dtype=np.float32)
    image = np.asarray(candidate_rgb, dtype=np.float32)
    glass = np.asarray(allowed, dtype=np.float32)
    if reference.ndim != 3 or reference.shape[-1] != 3 or image.shape != reference.shape:
        raise ValueError('Reference and candidate must be identical RGB shapes')
    if glass.shape != reference.shape[:2]:
        raise ValueError('Allowed glass mask shape mismatch')
    if not (np.isfinite(reference).all() and np.isfinite(image).all() and
            np.isfinite(glass).all()):
        raise ValueError('NaN/Inf is not allowed')
    if np.min(reference) < 0 or np.max(reference) > 1 or np.min(image) < 0 or np.max(image) > 1:
        raise ValueError('Expected RGB values in [0, 1]')
    if np.min(glass) < 0 or np.max(glass) > 1:
        raise ValueError('Expected mask values in [0, 1]')
    active = glass > .02
    if not np.any(active):
        raise ValueError('Glass allowed mask has no active pixels')
    if sku_roi is None:
        roi = active.copy()
        roi_source = 'active_glass_proxy'
    else:
        roi = np.asarray(sku_roi, dtype=bool)
        if roi.shape != active.shape:
            raise ValueError('SKU ROI shape mismatch')
        roi = roi & active
        roi_source = 'provided_yolo_or_heuristic_roi'
    if not np.any(roi):
        raise ValueError('SKU ROI does not overlap an active glass area')

    delta = np.max(np.abs(image - reference), axis=2)
    changed = delta > 4 / 255
    changed_ratio = float(np.count_nonzero(changed & active) / np.count_nonzero(active))
    ref_luma = np.dot(reference, [0.2126, 0.7152, 0.0722])
    out_luma = np.dot(image, [0.2126, 0.7152, 0.0722])
    # A measurable brightening over the same water atlas; these are candidates
    # for overly strong highlights, not necessarily circular halos.
    bright = (out_luma - ref_luma > .16) & (out_luma > .72) & active
    bright_ratio = float(np.count_nonzero(bright) / np.count_nonzero(active))

    baseline_grad = _gradient(ref_luma)
    candidate_grad = _gradient(out_luma)
    # Select the sharper baseline pixels inside product regions, to avoid
    # counting large blank glass areas as perfect retention.
    cutoff = max(.035, float(np.quantile(baseline_grad[roi], .7)))
    significant = roi & (baseline_grad >= cutoff)
    if np.any(significant):
        # Allow small one-pixel warps of product glyph edges.
        padded = np.pad(candidate_grad, 1, mode='edge')
        h, w = candidate_grad.shape
        local = np.maximum.reduce([padded[dy:dy+h, dx:dx+w]
                                   for dy in range(3) for dx in range(3)])
        lost = significant & (local < baseline_grad * .52)
        detail_loss = float(np.count_nonzero(lost) / np.count_nonzero(significant))
    else:
        detail_loss = 0.0
    sku_delta = float(np.mean(np.abs(image[roi] - reference[roi])))
    leakage = leakage_metrics(reference, image, glass, guard_pixels=2)

    metrics = {
        'effect_changed_ratio': changed_ratio,
        'bright_halo_proxy_ratio': bright_ratio,
        'sku_detail_loss_proxy_ratio': detail_loss,
        'sku_mean_rgb_delta': sku_delta,
        'sku_test_pixels': int(np.count_nonzero(roi)),
        'sku_edge_pixels': int(np.count_nonzero(significant)),
        'roi_source': roi_source,
        **leakage,
    }
    reasons = []
    for value_key, threshold_key, comparator in (
        ('leakage_ratio', 'max_leakage_ratio', '>'),
        ('bright_halo_proxy_ratio', 'max_bright_halo_ratio', '>'),
        ('sku_detail_loss_proxy_ratio', 'max_sku_detail_loss_ratio', '>'),
        ('sku_mean_rgb_delta', 'max_sku_mean_rgb_delta', '>'),
        ('effect_changed_ratio', 'min_effect_changed_ratio', '<'),
    ):
        value, bound = metrics[value_key], thresholds[threshold_key]
        if (value > bound if comparator == '>' else value < bound):
            reasons.append(f'{value_key}={value:.6f} {comparator} {bound:.6f}')
    # Ranking is useful only among passing candidates; a no-effect setting
    # can't win because the minimum visible change is enforced above.
    score = (changed_ratio * .35 - bright_ratio * 3. - detail_loss * .7
             - sku_delta * .5 - leakage['leakage_ratio'] * 20.)
    return {'accepted': not reasons, 'reasons': reasons,
            'score': float(score), 'metrics': metrics, 'limits': thresholds}


def rank_candidates(reports):
    """Select a passing optical configuration, or explicitly reject all."""
    passed = [(name, result) for name, result in reports.items() if result['accepted']]
    passed.sort(key=lambda pair: (-pair[1]['score'], pair[0]))
    return passed[0][0] if passed else None
