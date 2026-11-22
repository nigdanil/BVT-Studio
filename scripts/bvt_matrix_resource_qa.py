"""Stable packed-image metadata for matrix persistence checks (no Blender import)."""
import struct

PNG = b'\x89PNG\r\n\x1a\n'
EXR = b'\x76\x2f\x31\x01'


def packed_layout(raw):
    """Return extension and dimensions from the packed payload, not a GPU cache.

    Only the formats used by the BVT gallery are supported. EXR is limited to
    single-part, non-deep images. This is a header check, not a full decoder.
    """
    if raw.startswith(PNG):
        if len(raw) < 33 or raw[8:16] != b'\x00\x00\x00\x0dIHDR':
            raise ValueError('Invalid packed PNG header')
        size = list(struct.unpack_from('>II', raw, 16))
        ext = '.png'
    elif raw.startswith(EXR):
        if len(raw) < 9:
            raise ValueError('Truncated packed EXR header')
        version = struct.unpack_from('<I', raw, 4)[0]
        # Version 2, single-part, non-deep (allow tiled and long names).
        if version & 0xff != 2 or version & (0x800 | 0x1000):
            raise ValueError('Unsupported packed EXR version/flags')
        pos = 8
        size = None
        seen = set()
        def cstring(start):
            end = raw.find(b'\0', start, min(len(raw),start+256))
            if end < 0:
                raise ValueError('Malformed packed EXR attribute')
            return raw[start:end], end+1
        while True:
            name, pos = cstring(pos)
            if not name:
                break
            kind, pos = cstring(pos)
            if not kind or pos+4 > len(raw) or name in seen:
                raise ValueError('Invalid packed EXR attribute')
            seen.add(name)
            n = struct.unpack_from('<I', raw, pos)[0]
            pos += 4
            if pos+n > len(raw):
                raise ValueError('Truncated packed EXR attribute')
            if name == b'dataWindow':
                if kind != b'box2i' or n != 16:
                    raise ValueError('Invalid EXR dataWindow')
                x0,y0,x1,y1 = struct.unpack_from('<iiii',raw,pos)
                size = [x1-x0+1,y1-y0+1]
            pos += n
        if size is None:
            raise ValueError('Packed EXR has no dataWindow')
        ext = '.exr'
    else:
        raise ValueError('Expected packed PNG or EXR')
    if min(size) <= 0 or max(size) > 2**31-1:
        raise ValueError('Invalid packed image dimensions')
    return ext,size


def validate_runtime_size(runtime, encoded):
    """An unloaded Blender image can report zero; other disagreements fail."""
    if list(runtime) not in ([0,0],list(encoded)):
        raise ValueError(f'Runtime image size {list(runtime)} differs from packed header {list(encoded)}')


def snapshot_delta(before, after):
    common = set(before) & set(after)
    changed = {}
    for name in sorted(common):
        fields = {key:{'before':before[name].get(key),'after':after[name].get(key)}
                  for key in sorted(set(before[name]) | set(after[name]))
                  if before[name].get(key) != after[name].get(key)}
        if fields:
            changed[name]=fields
    return {'removed':sorted(set(before)-set(after)),
            'added':sorted(set(after)-set(before)), 'changed':changed}



def canonical_resource_path(path, expected):
    """Allow only slash spelling differences in a known Blender-relative path.

    Preserve case, filename, folder and relative prefix. Do not resolve paths
    against the host filesystem or accept traversal/absolute paths.
    """
    if not isinstance(path, str) or not path.startswith('//'):
        raise ValueError(f'Expected Blender-relative resource path: {path!r}')
    normalized = '//' + path[2:].replace('\\', '/')
    if normalized != expected:
        raise ValueError(f'Unexpected resource path: {path!r}; expected {expected!r}')
    return normalized
