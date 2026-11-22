"""Strict versioned glass-material profiles, not measured optical constants."""
import copy
import json
from math import isfinite
from pathlib import Path

SCHEMA = 'bvt.glass-material.v01'
MATERIAL_IDS = ('clear_glass', 'frosted_glass', 'tinted_glass', 'textured_glass',
                'coated_glass', 'insulated_glass')
OPTICAL_RANGES = {
    'scatter_mix': (0., 1.), 'scatter_radius_fraction': (0., .08),
    'haze_mix': (0., 1.), 'distortion_fraction': (0., .04),
    'texture_cycles': (1., 80.), 'reflection_mix': (0., .35),
    'ghost_mix': (0., .35), 'ghost_offset_fraction': (0., .04),
    'edge_feather_fraction': (0., .1),
}
RGB_KEYS = ('transmission_rgb', 'haze_rgb', 'reflection_rgb')
META_KEYS = {'construction', 'layers', 'nominal_thickness_mm', 'nominal_ior'}
TOP_KEYS = {'schema', 'id', 'title', 'description', 'physical_metadata', 'appearance', 'status'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def number(value, low, high, field):
    require(type(value) in (int, float) and isfinite(value) and low <= value <= high,
            f'{field}: expected finite number in [{low}, {high}]')
    return float(value)


def rgb(value, key):
    require(isinstance(value, list) and len(value) == 3, key + ': expected RGB triplet')
    return [number(v, 0., 1., key) for v in value]


def neutral_appearance(appearance):
    """No optical appearance change, regardless of descriptive metadata."""
    return (appearance['transmission_rgb'] == [1., 1., 1.] and
            all(appearance[k] == 0. for k in ('scatter_mix', 'haze_mix',
                'distortion_fraction', 'reflection_mix', 'ghost_mix')))


def validate_material(doc):
    require(isinstance(doc, dict) and set(doc) == TOP_KEYS, 'Invalid material fields')
    require(doc['schema'] == SCHEMA, 'Invalid glass material schema')
    require(doc['id'] in MATERIAL_IDS, 'Unknown material ID')
    require(doc['status'] == 'EXPERIMENTAL_UNCALIBRATED', 'Invalid material status')
    for key in ('title', 'description'):
        require(isinstance(doc[key], str) and bool(doc[key].strip()), 'Missing ' + key)
    meta = doc['physical_metadata']
    require(isinstance(meta, dict) and set(meta) == META_KEYS, 'Invalid physical metadata')
    require(isinstance(meta['construction'], str) and bool(meta['construction'].strip()), 'Missing construction')
    require(type(meta['layers']) is int and 1 <= meta['layers'] <= 4, 'Invalid layer count')
    number(meta['nominal_thickness_mm'], .1, 100., 'nominal_thickness_mm')
    number(meta['nominal_ior'], 1., 2.5, 'nominal_ior')
    a = doc['appearance']
    require(isinstance(a, dict) and set(a) == set(OPTICAL_RANGES) | set(RGB_KEYS), 'Invalid appearance fields')
    result = copy.deepcopy(doc)
    for key, (low, high) in OPTICAL_RANGES.items():
        result['appearance'][key] = number(a[key], low, high, key)
    for key in RGB_KEYS:
        result['appearance'][key] = rgb(a[key], key)
    require(a['scatter_mix'] == 0 or a['scatter_radius_fraction'] > 0, 'Scatter requires positive radius')
    require(a['ghost_mix'] == 0 or a['ghost_offset_fraction'] > 0, 'Ghost requires positive offset')
    require(doc['id'] != 'clear_glass' or neutral_appearance(result['appearance']), 'Clear glass must remain an exact no-op')
    return result


def read_material(path):
    def no_duplicates(pairs):
        out = {}
        for k, v in pairs:
            require(k not in out, 'Duplicate JSON field: ' + k)
            out[k] = v
        return out
    return validate_material(json.loads(Path(path).read_text(encoding='utf-8-sig'),
                                        object_pairs_hook=no_duplicates))


def load_library(directory):
    directory = Path(directory)
    require(directory.is_dir(), 'Missing material library')
    expected = {name + '.json' for name in MATERIAL_IDS}
    require({p.name for p in directory.glob('*.json')} == expected, 'Material catalog incomplete or unexpected')
    out = {}
    for name in MATERIAL_IDS:
        path = directory / (name + '.json')
        require(path.is_file() and not path.is_symlink(), 'Invalid material file: ' + name)
        mat = read_material(path)
        require(mat['id'] == name, 'Material filename/ID mismatch')
        out[name] = mat
    return out
