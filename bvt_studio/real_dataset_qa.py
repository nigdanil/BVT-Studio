"""Read-only YOLO Detect image-pair QA for real retail datasets (alpha.5-step6).

Compare the ORIGINAL photograph with a geometrically aligned augmentation.
The measurements are image/edge proxies, NOT detector accuracy, OCR, or proof
of physical realism. Arrays must be top-down float RGB in [0, 1].
NumPy is imported lazily so BVT Studio imports without external pip installs.
"""
from math import ceil, floor, isfinite

POLICIES = {
    'LIGHT': dict(target=.035, min_changed=.002, max_changed=.10,
                  max_bright=.08, max_detail_loss=.30, max_mean_delta=.12),
    'MEDIUM': dict(target=.12, min_changed=.03, max_changed=.30,
                   max_bright=.12, max_detail_loss=.40, max_mean_delta=.18),
    'HEAVY': dict(target=.28, min_changed=.10, max_changed=.65,
                  max_bright=.18, max_detail_loss=.50, max_mean_delta=.24),
}
PIXEL_CHANGE_EPS = 4 / 255
MAX_FAR_LEAKAGE_RATIO = 0.0  # No far-outside-glass changes by default.


def policy_for(profile):
    if not isinstance(profile, str) or profile.upper() not in POLICIES:
        raise ValueError('Expected LIGHT, MEDIUM or HEAVY dataset profile')
    return dict(POLICIES[profile.upper()])


def parse_yolo_detect(text, width, height):
    """Strict YOLO Detect parser returning top-down pixel boxes and originals.

    Segmentation polygons, pose/keypoint, rotated boxes and truncated boxes
    deliberately fail closed. Class IDs are numeric, not class names.
    """
    if isinstance(width, bool) or isinstance(height, bool) or not (
            isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        raise ValueError('Expected positive integer image dimensions')
    if not isinstance(text, str):
        raise ValueError('Labels must be decoded UTF-8 text')
    boxes = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 5:
            raise ValueError(f'YOLO Detect line {line_no}: expected class cx cy w h')
        if not parts[0].isdigit():
            raise ValueError(f'YOLO Detect line {line_no}: invalid class ID')
        cls = int(parts[0])
        try:
            cx, cy, bw, bh = [float(x) for x in parts[1:]]
        except ValueError as exc:
            raise ValueError(f'YOLO Detect line {line_no}: invalid coordinate') from exc
        vals = (cx, cy, bw, bh)
        if not all(isfinite(x) for x in vals) or not (0 < bw <= 1 and 0 < bh <= 1):
            raise ValueError(f'YOLO Detect line {line_no}: invalid box size or nonfinite value')
        eps = 1e-8
        if not (bw/2 - eps <= cx <= 1 - bw/2 + eps and
                bh/2 - eps <= cy <= 1 - bh/2 + eps):
            raise ValueError(f'YOLO Detect line {line_no}: box outside image')
        x0 = max(0, floor(max(0., cx-bw/2)*width))
        y0 = max(0, floor(max(0., cy-bh/2)*height))
        x1 = min(width, ceil(min(1., cx+bw/2)*width))
        y1 = min(height, ceil(min(1., cy+bh/2)*height))
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f'YOLO Detect line {line_no}: empty raster box')
        boxes.append({'index': len(boxes), 'line': line_no, 'class_id': cls,
                      'yolo_xywh': [cx, cy, bw, bh],
                      'bbox_xyxy_px': [x0, y0, x1, y1]})
    if not boxes:
        raise ValueError('No objects in YOLO Detect label file')
    return boxes


def _gradient(image):
    """Max absolute horizontal/vertical first difference, top-down."""
    import numpy as np
    y = np.asarray(image, dtype=np.float32)
    result = np.zeros(y.shape, dtype=np.float32)
    result[:, 1:] = np.maximum(result[:, 1:], np.abs(y[:, 1:] - y[:, :-1]))
    result[1:, :] = np.maximum(result[1:, :], np.abs(y[1:, :] - y[:-1, :]))
    return result


def _dilate(mask, pixels=2):
    import numpy as np
    h, w = mask.shape
    pad = np.pad(mask, pixels, constant_values=False)
    return np.logical_or.reduce([pad[y:y+h, x:x+w]
                                 for y in range(pixels*2+1)
                                 for x in range(pixels*2+1)])


def _rgb(arr, name):
    import numpy as np
    a = np.asarray(arr, dtype=np.float32)
    if a.ndim != 3 or a.shape[-1] != 3 or not np.isfinite(a).all() or (
            a.size == 0 or a.min() < 0 or a.max() > 1):
        raise ValueError(f'{name}: expected finite nonempty RGB [0,1]')
    return a


def evaluate_dataset_pair(clean_rgb, augmented_rgb, labels_text, *,
                          profile='MEDIUM', glass_mask=None):
    """Evaluate aligned original/augmented photos per YOLO SKU and glass ROI.

    No-glass-mask examples are REVIEW (never PASS). Scores are provisional
    engineering heuristics; validate downstream detector recall independently.
    """
    import numpy as np
    cfg = policy_for(profile)
    clean = _rgb(clean_rgb, 'clean image')
    augmented = _rgb(augmented_rgb, 'augmented image')
    if clean.shape != augmented.shape:
        raise ValueError('Original/augmented image sizes must match exactly')
    h, w, _ = clean.shape
    boxes = parse_yolo_detect(labels_text, w, h)
    mask_provenance = 'missing_review_required'
    mask = None
    if glass_mask is not None:
        mask = np.asarray(glass_mask, dtype=np.float32)
        if (mask.shape != (h, w) or not np.isfinite(mask).all() or
                np.min(mask) < 0 or np.max(mask) > 1):
            raise ValueError('Glass mask must be finite grayscale [0,1] matching image')
        mask = mask > .02
        if not np.any(mask):
            raise ValueError('Glass mask has no active pixels')
        mask_provenance = 'user_supplied_glass_mask'

    delta = np.max(np.abs(augmented-clean), axis=2)
    changed = delta > PIXEL_CHANGE_EPS
    overlap_mask = np.ones((h, w), dtype=bool) if mask is None else mask
    changed_fraction = float(np.mean(changed[overlap_mask]))
    lum0 = np.dot(clean, [0.2126, 0.7152, 0.0722])
    lum1 = np.dot(augmented, [0.2126, 0.7152, 0.0722])
    bright = (lum1-lum0 > .16) & (lum1 > .72)
    grad0 = _gradient(lum0)
    grad1 = _gradient(lum1)
    padded = np.pad(grad1, 1, mode='edge')
    local_grad1 = np.maximum.reduce([padded[dy:dy+h, dx:dx+w]
                                     for dy in range(3) for dx in range(3)])
    glass_dilated = _dilate(mask) if mask is not None else None
    outside = ~glass_dilated if mask is not None else None
    global_bright_ratio = float(np.mean(bright[overlap_mask]))
    leakage_pixels = int(np.count_nonzero(changed & outside)) if mask is not None else None
    leakage_ratio = (float(leakage_pixels / max(1, int(np.count_nonzero(outside))))
                     if mask is not None else None)

    issues = []
    if not cfg['min_changed'] <= changed_fraction <= cfg['max_changed']:
        issues.append(f'changed_ratio={changed_fraction:.6f} outside '
                      f'[{cfg["min_changed"]:.6f}, {cfg["max_changed"]:.6f}]')
    if global_bright_ratio > cfg['max_bright']:
        issues.append(f'global_bright_ratio={global_bright_ratio:.6f} > {cfg["max_bright"]:.6f}')
    if leakage_pixels is not None and leakage_ratio > MAX_FAR_LEAKAGE_RATIO:
        issues.append(f'far_glass_leakage_pixels={leakage_pixels}')
    objects, by_class = [], {}
    for box in boxes:
        x0, y0, x1, y1 = box['bbox_xyxy_px']
        # An object outside glass must remain unchanged, but does not need a
        # water effect. Per-SKU metrics apply only where its box meets glass.
        roi = np.ones((y1-y0, x1-x0), dtype=bool) if mask is None else mask[y0:y1, x0:x1]
        scope = 'unverified_no_mask' if mask is None else (
            'glass_intersection' if np.any(roi) else 'outside_glass')
        if scope == 'outside_glass':
            object_issues = []
            metrics = dict(changed_ratio=0., bright_ratio=0., detail_loss_ratio=0.,
                           mean_rgb_delta=0., significant_edge_pixels=0,
                           measured_pixels=0)
        else:
            curr_changed = changed[y0:y1, x0:x1][roi]
            curr_bright = bright[y0:y1, x0:x1][roi]
            clean_g = grad0[y0:y1, x0:x1]
            augmented_g = local_grad1[y0:y1, x0:x1]
            cutoff = max(.035, float(np.quantile(clean_g[roi], .70)))
            edges = roi & (clean_g >= cutoff)
            edge_count = int(np.count_nonzero(edges))
            detail_loss = (float(np.count_nonzero(edges & (augmented_g < clean_g*.65)) / edge_count)
                           if edge_count else None)
            absdiff = np.abs(augmented[y0:y1, x0:x1] - clean[y0:y1, x0:x1])
            metrics = dict(changed_ratio=float(np.mean(curr_changed)),
                           bright_ratio=float(np.mean(curr_bright)),
                           detail_loss_ratio=detail_loss,
                           mean_rgb_delta=float(np.mean(absdiff[roi])),
                           significant_edge_pixels=edge_count,
                           measured_pixels=int(np.count_nonzero(roi)))
            object_issues = []
            for key, bound in [('bright_ratio','max_bright'),
                               ('detail_loss_ratio','max_detail_loss'),
                               ('mean_rgb_delta','max_mean_delta')]:
                value = metrics[key]
                if value is not None and value > cfg[bound]:
                    object_issues.append(f'{key}={value:.6f} > {cfg[bound]:.6f}')
        status = 'REJECT' if object_issues else ('REVIEW' if mask is None or
                    (scope != 'outside_glass' and metrics['significant_edge_pixels'] == 0)
                    else 'PASS')
        result = dict(box, scope=scope, status=status, metrics=metrics, reasons=object_issues)
        objects.append(result)
        key = str(box['class_id'])
        entry = by_class.setdefault(key, {'count':0, 'pass':0, 'review':0, 'reject':0})
        entry['count'] += 1
        entry[status.lower()] += 1
    has_glass_sku = any(obj['scope'] == 'glass_intersection' for obj in objects)
    if any(obj['status'] == 'REJECT' for obj in objects) or issues:
        status = 'REJECT'
    elif mask is None or not has_glass_sku or any(obj['status'] == 'REVIEW' for obj in objects):
        status = 'REVIEW'
    else:
        status = 'PASS'
    warnings = []
    if mask is None:
        warnings.append('No verified glass mask: leakage QA unavailable; manual REVIEW required')
    elif not has_glass_sku:
        warnings.append('No YOLO SKU intersects the glass mask; SKU visibility unverified')
    if any(obj['scope'] != 'outside_glass' and obj['metrics']['significant_edge_pixels'] == 0
           for obj in objects):
        warnings.append('Some SKU ROIs contain no measurable edges: detail retention unverifiable')
    return {
        'status': status, 'accepted': status == 'PASS', 'profile': profile.upper(),
        'image_size': [w, h], 'annotations_count': len(boxes),
        'mask_provenance': mask_provenance,
        'metrics': {
            'changed_ratio_in_glass_or_full_image': changed_fraction,
            'global_bright_ratio_in_glass_or_full_image': global_bright_ratio,
            'far_glass_leakage_pixels': leakage_pixels,
            'far_glass_leakage_ratio': leakage_ratio,
            'target_changed_ratio': cfg['target'],
            'distance_from_target_ratio': abs(changed_fraction - cfg['target']) / cfg['target'],
        }, 'objects': objects, 'classes': by_class,
        'reasons': issues, 'warnings': warnings,
        'limits': cfg, 'metric_warning': (
            'Original-vs-augmentation RGB/gradient proxies. Not detector AP, OCR, '
            'image alignment verification or physical-water photorealism.'),
    }
