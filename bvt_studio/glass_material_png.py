"""Bounded 8-bit non-interlaced PNG codec for the material bake; NumPy only."""
import struct
import zlib
import numpy as np

SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_PIXELS = 8_388_608

def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data)&0xffffffff)

def decode_png(data, *, mask=False):
    if not data.startswith(SIGNATURE):
        raise ValueError('Material layer currently requires an 8-bit PNG')
    p=8; meta=None; pieces=[]; ended=False
    while p+12<=len(data):
        n,kind=struct.unpack('>I4s',data[p:p+8]); end=p+n+12
        if end>len(data): raise ValueError('Truncated PNG')
        payload=data[p+8:end-4]
        if zlib.crc32(kind+payload)&0xffffffff != struct.unpack('>I',data[end-4:end])[0]:
            raise ValueError('PNG CRC mismatch')
        if kind==b'IHDR':
            if meta is not None or p!=8 or n!=13: raise ValueError('Invalid IHDR')
            meta=struct.unpack('>IIBBBBB',payload)
        elif kind==b'IDAT': pieces.append(payload)
        elif kind==b'IEND':
            if n!=0: raise ValueError('Invalid IEND')
            ended=True; p=end; break
        elif kind in (b'tRNS',b'acTL') or (not mask and kind==b'iCCP'):
            raise ValueError('Transparent, animated or ICC-profile PNG unsupported')
        elif not mask and kind==b'gAMA' and (n!=4 or abs(struct.unpack('>I',payload)[0]-45455)>100):
            raise ValueError('Source PNG must use standard sRGB gamma')
        elif kind not in (b'PLTE',) and kind[0]&32==0:
            raise ValueError('Unsupported critical PNG chunk')
        p=end
    if meta is None or not ended or p!=len(data) or not pieces: raise ValueError('Incomplete PNG')
    w,h,depth,typ,comp,filt,inter=meta
    channels={0:1,2:3,4:2,6:4}.get(typ)
    if not (0<w and 0<h and w*h<=MAX_PIXELS and depth==8 and channels and comp==filt==inter==0):
        raise ValueError('Expected non-interlaced 8-bit gray/RGB/RGBA PNG, up to 8 Mi pixels')
    stride=w*channels; size=h*(stride+1)
    obj=zlib.decompressobj(); raw=obj.decompress(b''.join(pieces),size+1)
    if len(raw)!=size or not obj.eof or obj.unused_data or obj.unconsumed_tail:
        raise ValueError('Invalid PNG decompressed size')
    out=np.empty((h,stride),dtype=np.uint8); prev=np.zeros(stride,dtype=np.uint8)
    for y in range(h):
        off=y*(stride+1); mode=raw[off]; row=np.frombuffer(raw,dtype=np.uint8,count=stride,offset=off+1).copy()
        if mode==1:
            for c in range(channels): row[c::channels]=np.cumsum(row[c::channels],dtype=np.uint32).astype(np.uint8)
        elif mode==2: row+=prev
        elif mode in (3,4):
            # Paeth and Average depend on the reconstructed left sample.
            a=row.tolist(); b=prev.tolist()
            for x in range(stride):
                left=a[x-channels] if x>=channels else 0; up=b[x]; ul=b[x-channels] if x>=channels else 0
                if mode==3: pred=(left+up)//2
                else:
                    p0=left+up-ul; pa=abs(p0-left); pb=abs(p0-up); pc=abs(p0-ul)
                    pred=left if pa<=pb and pa<=pc else up if pb<=pc else ul
                a[x]=(a[x]+pred)&255
            row=np.asarray(a,dtype=np.uint8)
        elif mode!=0: raise ValueError('Invalid PNG filter')
        out[y]=row; prev=row
    pix=out.reshape(h,w,channels)
    rgb=np.repeat(pix[:,:,:1],3,axis=2) if typ in (0,4) else pix[:,:,:3].copy()
    if mask:
        if not (np.array_equal(rgb[:,:,0],rgb[:,:,1]) and np.array_equal(rgb[:,:,0],rgb[:,:,2])):
            raise ValueError('Material masks must be grayscale RGB; alpha is ignored')
        return rgb[:,:,0].astype(np.float64)/255.
    if typ in (4,6) and not np.all(pix[:,:,-1]==255): raise ValueError('Material source PNG must be opaque')
    return rgb

def encode_rgb(rgb):
    if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8 or not 0<rgb.shape[0]*rgb.shape[1]<=MAX_PIXELS:
        raise ValueError('Invalid RGB image')
    h,w=rgb.shape[:2]
    raw=b''.join(b'\0'+row.tobytes() for row in rgb)
    return SIGNATURE+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(raw,6))+chunk(b'IEND',b'')
