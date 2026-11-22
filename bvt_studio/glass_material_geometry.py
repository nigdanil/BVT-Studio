"""Pure projection and mask helpers for axis-aligned photo-local panes."""
import numpy as np

def pane_rect(points, width, height):
    # Points: normalized photo-local XY plus glass-local UV. Both must align.
    p=np.asarray(points,dtype=float)
    if p.shape!=(4,4) or not np.isfinite(p).all(): raise ValueError('Expected four affine pane corners')
    lo=p[:,:2].min(0); hi=p[:,:2].max(0)
    if np.any(lo < -1e-5) or np.any(hi > 1+1e-5) or np.any(hi-lo<1e-6): raise ValueError('Pane outside source or degenerate')
    expected=(p[:,:2]-lo)/(hi-lo)
    corners=np.rint(expected)
    if np.max(np.abs(expected-corners))>1e-5 or len(set(map(tuple,corners)))!=4 or np.max(np.abs(p[:,2:]-corners))>1e-5:
        raise ValueError('Material layer requires axis-aligned rectangular glass with aligned UVs')
    x0,x1=round(lo[0]*width),round(hi[0]*width)
    y0,y1=round((1-hi[1])*height),round((1-lo[1])*height)
    if not 0<=x0<x1<=width or not 0<=y0<y1<=height: raise ValueError('Empty/outside pixel rectangle')
    return [x0,y0,x1,y1]

def resize_mask(mask,h,w):
    if mask.shape==(h,w): return mask.copy()
    y=np.clip((np.arange(h)+.5)*mask.shape[0]/h-.5,0,mask.shape[0]-1)
    x=np.clip((np.arange(w)+.5)*mask.shape[1]/w-.5,0,mask.shape[1]-1)
    x0=x.astype(int); y0=y.astype(int); x1=np.minimum(x0+1,mask.shape[1]-1); y1=np.minimum(y0+1,mask.shape[0]-1)
    fx=(x-x0)[None,:]; fy=(y-y0)[:,None]
    return ((1-fy)*((1-fx)*mask[y0[:,None],x0]+fx*mask[y0[:,None],x1])+fy*((1-fx)*mask[y1[:,None],x0]+fx*mask[y1[:,None],x1]))
