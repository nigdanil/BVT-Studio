"""Pure numerical QA metrics for glass mask leakage, independent of Blender.

All images/masks are expected to be normalized linear RGB arrays as read from
bpy image pixels; display PNGs can be read with Blender's image loader.
"""


def leakage_metrics(control_rgb, affected_rgb, allowed, difference_threshold=3/255,
                    forbidden_threshold=1/255, guard_pixels=2):
    """Count changed pixels outside mask, with a small AA-safe boundary guard.

    A gray mask pixel (>forbidden_threshold) is considered permitted; the
    excluded region is eroded by guard_pixels to suppress raster-AA seams.
    The returned ratio is leak pixels / tested forbidden pixels, not all pixels.
    """
    import numpy as np
    control = np.asarray(control_rgb, dtype=np.float32)
    affected = np.asarray(affected_rgb, dtype=np.float32)
    mask = np.asarray(allowed, dtype=np.float32)
    if control.shape != affected.shape or control.ndim != 3 or control.shape[-1] != 3:
        raise ValueError('Control and effect must be identically-sized RGB images')
    if mask.shape != control.shape[:2]:
        raise ValueError('Allowed mask must have matching height and width')
    if not (0 <= difference_threshold <= 1 and 0 <= forbidden_threshold <= 1):
        raise ValueError('Invalid QA thresholds')
    if not isinstance(guard_pixels, int) or not 0 <= guard_pixels <= 20:
        raise ValueError('Guard pixels must be an integer from 0 to 20')
    if not np.isfinite(control).all() or not np.isfinite(affected).all() or not np.isfinite(mask).all():
        raise ValueError('Input contains NaN/Infinity')
    excluded = mask <= forbidden_threshold
    if guard_pixels:
        # Protect against antialiased mask/render boundaries: a forbidden
        # pixel is tested only if no allowed pixel lies within the guard.
        h, w = excluded.shape
        padded = np.pad(excluded, guard_pixels, constant_values=False)
        core = np.ones_like(excluded, dtype=bool)
        for dy in range(2 * guard_pixels + 1):
            for dx in range(2 * guard_pixels + 1):
                core &= padded[dy:dy+h, dx:dx+w]
        excluded = core
    delta = np.max(np.abs(affected - control), axis=2)
    leaked = excluded & (delta > difference_threshold)
    forbidden_n = int(np.count_nonzero(excluded))
    leakage_n = int(np.count_nonzero(leaked))
    ys, xs = np.nonzero(leaked)
    return {
        'forbidden_pixels': forbidden_n,
        'leakage_pixels': leakage_n,
        'leakage_ratio': leakage_n / max(forbidden_n, 1),
        'leakage_bbox_xyxy': [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                             if leakage_n else None,
        'max_forbidden_rgb_delta': float(np.max(delta[excluded])) if forbidden_n else 0.0,
    }


def control_metrics(source_rgb, qa_rgb):
    import numpy as np
    a = np.asarray(source_rgb, dtype=np.float32)
    b = np.asarray(qa_rgb, dtype=np.float32)
    if a.shape != b.shape or a.ndim != 3 or a.shape[-1] != 3:
        raise ValueError('Source and control size mismatch')
    diffs = np.abs(a - b)
    return {'max_rgb_delta': float(np.max(diffs)),
            'mean_rgb_delta': float(np.mean(diffs))}
