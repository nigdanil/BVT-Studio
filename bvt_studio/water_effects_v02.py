"""Deterministic BVT 2.5D water atlas v0.2; pure NumPy core, Blender optional.

Distinct macro beads, micro beads, and gravity streaks. Measurements are
procedural geometry proxies, not physically based hydrodynamics.
"""
from __future__ import annotations

from math import isfinite

DEFAULTS = {
    "macro_count": 24, "macro_diameter_px": 42., "macro_irregularity": .13,
    "micro_count": 1000, "micro_diameter_px": 4.8,
    "streak_count": 12, "streak_length_px": 230., "streak_width_px": 7.,
    "streak_taper": .72, "relief_strength": 1.0,
}
LIMITS = {
    "macro_count": (0, 120), "macro_diameter_px": (8., 125.),
    "macro_irregularity": (0., .32), "micro_count": (0, 6000),
    "micro_diameter_px": (1.6, 12.), "streak_count": (0, 50),
    "streak_length_px": (50., 470.), "streak_width_px": (2., 26.),
    "streak_taper": (.1, .95), "relief_strength": (.3, 2.5),
}
KINDS = ("MACRO", "MICRO", "RUNNING", "COMBINED")


def validated_config(config):
    if not isinstance(config, dict):
        raise ValueError('Water config must be a JSON object')
    unknown = set(config) - set(DEFAULTS)
    if unknown:
        raise ValueError('Unknown water properties: '+', '.join(sorted(unknown)))
    cfg = DEFAULTS.copy()
    cfg.update(config)
    for key, value in cfg.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f'{key} must be a finite number')
        lo, hi = LIMITS[key]
        if not lo <= value <= hi:
            raise ValueError(f'{key} outside [{lo}, {hi}]')
        if key.endswith('_count') and (not isinstance(value, int)):
            raise ValueError(f'{key} must be integer')
    return cfg


def generate_water_arrays(*, kind='COMBINED', seed=72, resolution=512, config=None):
    """RGB Alpha/Height/OpenGL Normal [0,1], plus each generated event UV bbox.

    The rows use Blender's image convention: v=0 is bottom; long streaks fall
    toward smaller v. Geometry is seeded and independent per glass.
    """
    import numpy as np
    if kind not in KINDS:
        raise ValueError('Unsupported water kind: ' + str(kind))
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**31:
        raise ValueError('seed must be a nonnegative 31-bit integer')
    if resolution not in (256, 512, 1024) or isinstance(resolution, bool):
        raise ValueError('resolution must be 256, 512 or 1024')
    cfg = validated_config(config or {})
    rng = np.random.default_rng(seed)
    n = resolution
    factor = n / 512.
    height = np.zeros((n,n),dtype=np.float32)
    alpha = np.zeros((n,n),dtype=np.float32)
    events = []

    def stamp(cx, cy, rx, ry, strength, irregularity, phase):
        extent=max(rx,ry)*1.5+3
        x0=max(0,int(cx-extent)); x1=min(n,int(cx+extent)+2)
        y0=max(0,int(cy-extent)); y1=min(n,int(cy+extent)+2)
        if x0>=x1 or y0>=y1:
            return
        y,x=np.ogrid[y0:y1,x0:x1]
        u=(x-cx)/max(rx,.35); v=(y-cy)/max(ry,.35)
        a=np.arctan2(v,u)
        d=np.sqrt(u*u+v*v) / np.maximum(.75,1+irregularity*(np.sin(3*a+phase)+.45*np.sin(5*a-phase*.7)))
        shell=np.clip((1-d)*max(2.7,min(rx,ry)*.9),0,1)
        cap=np.sqrt(np.maximum(0,1-np.minimum(d,1)**2))*shell
        contact=np.exp(-((d-.84)/.10)**2)
        a_layer=shell*np.clip(.72+.18*contact,0,1)*strength
        np.maximum(alpha[y0:y1,x0:x1],a_layer,out=alpha[y0:y1,x0:x1])
        np.maximum(height[y0:y1,x0:x1],cap*strength,out=height[y0:y1,x0:x1])

    def event(name,cx,cy,rx,ry):
        events.append(dict(type=name,uv_bbox=[max(0,(cx-rx)/n),max(0,(cy-ry)/n),
                                              min(1,(cx+rx)/n),min(1,(cy+ry)/n)]))

    if kind in ('MACRO','COMBINED'):
        for _ in range(cfg['macro_count']):
            radius=.5*cfg['macro_diameter_px']*factor*rng.uniform(.70,1.35)
            shape=rng.uniform(.65,1.25)
            rx,ry=radius*shape,radius/shape
            cx=rng.uniform(rx+2,n-rx-2); cy=rng.uniform(ry+2,n-ry-2)
            stamp(cx,cy,rx,ry,rng.uniform(.82,1.),cfg['macro_irregularity'],rng.uniform(0,6.283))
            event('macro',cx,cy,rx*1.17,ry*1.17)

    if kind in ('MICRO','COMBINED'):
        for _ in range(cfg['micro_count']):
            radius=.5*cfg['micro_diameter_px']*factor*rng.uniform(.6,1.4)
            rx=radius*rng.uniform(.75,1.2);ry=radius*rng.uniform(.75,1.3)
            cx=rng.uniform(0,n); cy=rng.uniform(0,n)
            stamp(cx,cy,rx,ry,rng.uniform(.62,.92),.08,rng.uniform(0,6.283))
            event('micro',cx,cy,max(2,rx*1.2),max(2,ry*1.2))

    if kind in ('RUNNING','COMBINED'):
        for _ in range(cfg['streak_count']):
            length=cfg['streak_length_px']*factor*rng.uniform(.65,1.2)
            length=min(n*.80,length)
            width=cfg['streak_width_px']*factor*rng.uniform(.70,1.40)
            cx=rng.uniform(width*3,n-width*3)
            top=rng.uniform(length+8,n-12) if length+20<n else n-12
            # The head is at the low end of the downward-growing trickle.
            phase=rng.uniform(0,6.283)
            segments=max(16,int(length/max(2.,1.4*factor)))
            xcoords=[]
            for step in range(segments+1):
                t=step/segments
                x=cx+width*.6*np.sin(t*9+phase)+width*.25*t
                y=top-length*t
                # Tail thins toward the upper origin; a broad descending head.
                w=width*(.28 + (1.-cfg['streak_taper'])*.35 + cfg['streak_taper']*.45*t)
                stamp(x,y,w*.72,max(1.1*factor,w*.78),.60+.25*t,.025,phase)
                xcoords.append(x)
            stamp(xcoords[-1],top-length,width*1.4,width*1.9,.95,.12,phase)
            events.append(dict(type='streak',uv_bbox=[max(0,(min(xcoords)-width*2)/n),
                       max(0,(top-length-width*2)/n),min(1,(max(xcoords)+width*2)/n),
                       min(1,(top+width*2)/n)]))

    # Stronger slopes than the old small-scale atlas. Normal encodes explicit
    # curvature; shaders still clamp speculars in normal production mode.
    gy,gx=np.gradient(height)
    gx=np.clip(-gx*cfg['relief_strength']*5.,-1.2,1.2)
    gy=np.clip(-gy*cfg['relief_strength']*5.,-1.2,1.2)
    z=np.ones_like(gx)
    den=np.sqrt(gx*gx+gy*gy+z*z)
    normal=np.stack((.5+.5*gx/den,.5+.5*gy/den,.5+.5*z/den),axis=-1).astype(np.float32)
    rgb_alpha=np.repeat(np.clip(alpha,0,1)[:,:,None],3,axis=2)
    rgb_height=np.repeat(np.clip(height,0,1)[:,:,None],3,axis=2)
    return {'alpha':rgb_alpha,'height':rgb_height,'normal':normal},events


def install_on_glass(obj, *, kind='COMBINED', seed=72, resolution=512,
                     config=None, optics=None, stress=False, tiling=1.0, preview_dir=None):
    """BVT-native import + pack. No other Glass_p objects are touched."""
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from .realistic_atlas import _save_png
    from .droplet_maps import import_droplet_maps,packed_maps_for
    from .optical_water import set_optical_water
    cfg=validated_config(config or {})
    arrays,events=generate_water_arrays(kind=kind,seed=seed,resolution=resolution,config=cfg)
    if preview_dir is not None:
        path=Path(preview_dir)
        path.mkdir(parents=True,exist_ok=True)
        for channel,arr in arrays.items():
            _save_png(path/(channel+'.png'),arr)
    with TemporaryDirectory(prefix='bvt_water_v02_') as tmp:
        paths={k:Path(tmp)/(k+'.png') for k in arrays}
        for name,data in arrays.items():
            _save_png(paths[name],data)
        import_droplet_maps(obj,paths['alpha'],paths['height'],paths['normal'],
                            tiling=tiling,rotation=0.,target_mode='REALISTIC_ATLAS')
    packed_maps_for(obj, mode='REALISTIC_ATLAS')
    obj['bvt_water_v02_kind']=kind
    obj['bvt_water_v02_seed']=seed
    obj['bvt_water_v02_config_json']=__import__('json').dumps(cfg,sort_keys=True)
    obj['bvt_water_v02_event_json']=__import__('json').dumps(events,separators=(',',':'))
    obj['bvt_optical_stress_test']=bool(stress)
    if optics:
        set_optical_water(obj,True,**optics)
    else:
        set_optical_water(obj,False)
    return events
