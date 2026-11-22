"""Experimental image-space reference renderer; not Blender shader integration.

RGB input is uint8 sRGB, geometry is top-down pixel rectangles. All optical
operations (apart from final quantization) use linear RGB. A pane samples
only its own original ROI. No geometry or annotation files are modified.
"""
from math import pi
import numpy as np
from .glass_material_config import validate_material, neutral_appearance, require


def _linear(rgb):
    f = rgb.astype(np.float64) / 255.
    return np.where(f <= .04045, f / 12.92, ((f + .055) / 1.055) ** 2.4)


def _srgb(linear):
    f = np.clip(linear, 0., 1.)
    return np.rint(np.where(f <= .0031308, 12.92 * f, 1.055 * f ** (1/2.4) - .055) * 255).astype(np.uint8)


def _box_axis(a, radius, axis):
    if radius == 0:
        return a
    pads = [(0, 0)] * a.ndim
    pads[axis] = (radius, radius)
    padded = np.pad(a, pads, mode='edge')
    prefix = np.cumsum(padded, axis=axis, dtype=np.float64)
    pads[axis] = (1, 0)
    prefix = np.pad(prefix, pads, mode='constant')
    lo, hi = [slice(None)] * a.ndim, [slice(None)] * a.ndim
    size = 2 * radius + 1
    lo[axis], hi[axis] = slice(None, -size), slice(size, None)
    return (prefix[tuple(hi)] - prefix[tuple(lo)]) / size


def _scatter(a, radius):
    # Three separable box passes approximating a smooth scattering kernel.
    for _ in range(3):
        a = _box_axis(_box_axis(a, radius, 0), radius, 1)
    return a


def _sample(a, x, y):
    h, w = a.shape[:2]
    x, y = np.clip(x, 0., w-1.), np.clip(y, 0., h-1.)
    x0, y0 = np.floor(x).astype(np.intp), np.floor(y).astype(np.intp)
    x1, y1 = np.minimum(x0+1, w-1), np.minimum(y0+1, h-1)
    fx, fy = (x-x0)[..., None], (y-y0)[..., None]
    return (a[y0,x0]*(1-fx)*(1-fy) + a[y0,x1]*fx*(1-fy) +
            a[y1,x0]*(1-fx)*fy + a[y1,x1]*fx*fy)


def _render_pane(source, a, seed, mask=None):
    if neutral_appearance(a):
        # Exact identity, not a round trip through colour-space transforms.
        return source.copy()
    h, w = source.shape[:2]
    scale = min(h, w)
    yy, xx = np.mgrid[:h, :w].astype(np.float64)
    # RNG isolated per pane and per specimen; no global RNG/scene state.
    rng = np.random.default_rng(seed)
    phases = rng.uniform(0., 2*pi, 3)
    src = _linear(source)
    out = src.copy()
    amp = a['distortion_fraction'] * scale
    if amp:
        theta = 2*pi*a['texture_cycles']*(xx+.5)/w + phases[0]
        dx = amp * np.sin(theta)
        dy = .20 * amp * np.sin(2*pi*(yy+.5)/h + phases[1]) * np.cos(theta)
        out = _sample(src, xx+dx, yy+dy)
    if a['ghost_mix']:
        offset = a['ghost_offset_fraction'] * scale
        ghost = _sample(out, xx+offset, yy+.25*offset)
        out = (1-a['ghost_mix'])*out + a['ghost_mix']*ghost
    if a['scatter_mix']:
        radius = max(1, round(a['scatter_radius_fraction']*scale))
        out = (1-a['scatter_mix'])*out + a['scatter_mix']*_scatter(out, radius)
    out *= np.asarray(a['transmission_rgb'])
    if a['haze_mix']:
        out = (1-a['haze_mix'])*out + a['haze_mix']*np.asarray(a['haze_rgb'])
    if a['reflection_mix']:
        # Synthetic illumination band, not an actual view-dependent reflection.
        band = .35 + .65 * np.exp(-((xx/max(w-1,1)-.48 + .20*(yy/max(h-1,1)-.5))/.17)**2)
        weight = (a['reflection_mix']*band)[..., None]
        out = (1-weight)*out + weight*np.asarray(a['reflection_rgb'])
    feather = a['edge_feather_fraction']*scale
    if feather:
        dist = np.minimum(np.minimum(xx+.5,w-.5-xx), np.minimum(yy+.5,h-.5-yy))
        weight = np.clip(dist/feather, 0., 1.)
        weight = weight*weight*(3-2*weight)
    else:
        weight = np.ones((h,w), dtype=np.float64)
    if mask is not None:
        weight *= mask
    result = _srgb(src*(1-weight[...,None])+out*weight[...,None])
    result[weight == 0] = source[weight == 0]
    return result


def render_materials(rgb, assignments):
    """Render independent, non-overlapping panes. Return a new uint8 array.

    assignments: list of {rect:[x0,y0,x1,y1], material: validated JSON,
                          seed:int, mask?: HxW float coverage within pane}.
    Physical metadata is descriptive and does not drive this reference model.
    """
    require(isinstance(rgb,np.ndarray) and rgb.dtype == np.uint8 and rgb.ndim == 3 and
            rgb.shape[2] == 3 and min(rgb.shape[:2]) > 0, 'Expected nonempty uint8 HxWx3 RGB image')
    require(isinstance(assignments,(list,tuple)) and bool(assignments), 'Expected pane assignments')
    h,w = rgb.shape[:2]
    seen, prepared = [], []
    for p in assignments:
        require(isinstance(p,dict) and {'rect','material','seed'} <= set(p) <= {'rect','material','seed','mask'}, 'Invalid pane fields')
        r = p['rect']
        require(isinstance(r,(list,tuple)) and len(r)==4 and all(type(v) is int for v in r), 'Expected integer rectangle')
        x0,y0,x1,y1 = r
        require(0<=x0<x1<=w and 0<=y0<y1<=h, 'Pane outside image')
        require(not any(x0<b[2] and x1>b[0] and y0<b[3] and y1>b[1] for b in seen), 'Overlapping panes')
        seen.append(r)
        seed = p['seed']
        require(type(seed) is int and 0<=seed<2**31, 'Invalid material seed')
        a = validate_material(p['material'])['appearance']
        mask = p.get('mask')
        if mask is not None:
            require(isinstance(mask,np.ndarray) and mask.shape==(y1-y0,x1-x0) and mask.dtype.kind in 'bfiu', 'Bad pane mask shape/type')
            require(np.isfinite(mask).all() and np.min(mask)>=0. and np.max(mask)<=1., 'Pane mask outside [0,1]')
            mask = mask.astype(np.float64)
        prepared.append((r,a,seed,mask))
    # Validate all panes before doing any rendering.
    out = rgb.copy()
    for (x0,y0,x1,y1),a,seed,mask in prepared:
        out[y0:y1,x0:x1] = _render_pane(rgb[y0:y1,x0:x1],a,seed,mask)
    return out
