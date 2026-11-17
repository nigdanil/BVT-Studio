"""Deterministic presets for 2.5D glass artifacts (no Blender imports)."""
import random

# The presets control visual density, not physical glass transmission.
# Values match the existing BVT glass shader property range [0, 1].
PRESETS = {
    'CLEAN': dict(reflection=.055, tint=.006, haze=.002, frost=.0,
                  droplets=.0, dirt=.0, coverage=.10),
    'LIGHT_CONDENSATION': dict(reflection=.09, tint=.012, haze=.055, frost=.004,
                               droplets=.14, dirt=.004, coverage=.24),
    'HEAVY_CONDENSATION': dict(reflection=.075, tint=.014, haze=.15, frost=.025,
                               droplets=.35, dirt=.016, coverage=.55),
    'FROST': dict(reflection=.06, tint=.020, haze=.075, frost=.38,
                  droplets=.065, dirt=.025, coverage=.40),
    'DIRTY_GLASS': dict(reflection=.05, tint=.018, haze=.08, frost=.005,
                        droplets=.025, dirt=.32, coverage=.58),
    'REFLECTIONS': dict(reflection=.29, tint=.012, haze=.02, frost=.0,
                        droplets=.012, dirt=.008, coverage=.12),
}

PROPERTY_BY_CHANNEL = {
    'reflection': 'bvt_glass_reflection',
    'tint': 'bvt_glass_tint',
    'haze': 'bvt_glass_haze',
    'frost': 'bvt_glass_frost',
    'droplets': 'bvt_glass_droplets',
    'dirt': 'bvt_glass_dirt',
}


def preset_values(name, intensity=1.0, coverage=None):
    """Return fresh values. No global RNG, no scene/object side effects."""
    if name not in PRESETS:
        raise ValueError('Unknown glass preset: ' + str(name))
    if not 0.0 <= float(intensity) <= 1.0:
        raise ValueError('Intensity must be in [0, 1]')
    if coverage is not None and not 0.0 <= float(coverage) <= 1.0:
        raise ValueError('Coverage must be in [0, 1]')
    source = PRESETS[name]
    result = {PROPERTY_BY_CHANNEL[ch]: round(float(v) * float(intensity), 6)
              for ch, v in source.items() if ch != 'coverage'}
    result['bvt_artifact_coverage'] = (float(source['coverage']) if coverage is None
                                       else float(coverage))
    return result


def seed_offsets(seed):
    """Stable UV offsets for procedural texture islands (not global random)."""
    seed = int(seed)
    if not 0 <= seed <= 2147483647:
        raise ValueError('Seed must be between 0 and 2147483647')
    rng = random.Random(seed)
    return (round(rng.uniform(7.0, 107.0), 6),
            round(rng.uniform(7.0, 107.0), 6),
            round(rng.uniform(7.0, 107.0), 6))
