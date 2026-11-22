"""Blender 5.2+ smoke: independent seeded presets, depth-safe, no ZIP output.

Run from BVT-Studio repository root:
  "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
    --background --factory-startup --python scripts/blender_glass_artifacts_smoke.py
"""
import sys
import math
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import bvt_studio
from bvt_studio.common import get_source
from bvt_studio.glass import scene_glass
from bvt_studio.artifact_presets import apply_preset
from bvt_studio.artifact_config import seed_offsets


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def active_seed_offset(obj):
    # configure_glass() rebuilds its node tree and can replace the material.
    # A cached nodes collection may belong to an obsolete material.
    mat = obj.active_material
    check(mat is not None and mat.use_nodes, 'Active glass material is missing')
    node = mat.node_tree.nodes.get('BVT_Artifact_Seed_Offset')
    check(node is not None, 'Seed offset node missing from active material')
    return tuple(node.inputs[1].default_value[:])


check(bpy.app.version >= (5, 2, 0), 'Requires Blender 5.2+')
if not hasattr(bpy.types.Scene, 'bvt_studio'):
    bvt_studio.register()

with tempfile.TemporaryDirectory(prefix='bvt_studio_v04_glass_') as temp:
    photo = Path(temp)/'test_photo.png'
    img = bpy.data.images.new('BVT_Artifact_Test', width=100, height=80, alpha=True)
    img.pixels[:] = [0.18, 0.24, 0.33, 1.0] * (100*80)
    img.filepath_raw = str(photo)
    img.file_format = 'PNG'
    img.save()
    check(bpy.ops.bvt_studio.load_photo(filepath=str(photo)) == {'FINISHED'},
          'Photo scene import failed')
    scene = bpy.context.scene
    source = get_source(scene)
    source.rotation_euler.x = math.radians(23)
    bpy.context.view_layer.update()
    check(bpy.ops.bvt_studio.fit_camera() == {'FINISHED'}, 'Photo framing failed')

    for _ in range(2):
        check(bpy.ops.bvt_studio.add_glass() == {'FINISHED'}, 'Add Glass failed')
    first, second = scene_glass(scene)
    first_world = first.matrix_world.copy()
    second_world = second.matrix_world.copy()
    second_material = second.active_material
    check(bpy.ops.bvt_studio.annotation_lock_mode() == {'FINISHED'},
          'Lock Annotation Mode failed')
    check(first.hide_select and second.hide_select, 'Glass not protected')

    settings = scene.bvt_studio
    settings.artifact_target_glass = first  # target selectable even when locked
    settings.artifact_preset = 'HEAVY_CONDENSATION'
    settings.artifact_intensity = .75
    settings.artifact_coverage = .37
    settings.artifact_seed = 72
    settings.artifact_droplet_scale = 1.35
    settings.artifact_frost_edge = .62
    check(bpy.ops.bvt_studio.apply_glass_preset() == {'FINISHED'},
          'Apply Preset failed')
    check(first['bvt_glass_droplets'] > 0, 'Droplet property missing')
    check(abs(first['bvt_artifact_coverage'] - .37) < 1e-7, 'Coverage not stored')
    check(first['bvt_artifact_seed'] == 72, 'Seed not stored')
    check(first['bvt_artifact_preset'] == 'HEAVY_CONDENSATION', 'Preset ID missing')
    nodes = first.active_material.node_tree.nodes
    check(abs(first['bvt_artifact_droplet_scale'] - 1.35) < 1e-6, 'Droplet Scale not stored')
    check(abs(first['bvt_artifact_frost_edge'] - .62) < 1e-6, 'Frost Edge not stored')
    for name in ('BVT_Droplets_Voronoi', 'BVT_Droplets_Voronoi_Fine',
                 'BVT_Droplets_Voronoi_Large', 'BVT_Droplets_Warp_Noise',
                 'BVT_Droplets_Large_Gate', 'BVT_Frost_Islands',
                 'BVT_Frost_Crystals', 'BVT_Frost_Edge_Mask'):
        check(nodes.get(name) is not None, f'Multi-scale node missing: {name}')
    # Validate that glass-specific controls drive all three scales and the edge mask.
    for suffix in ('', '_Fine', '_Large'):
        vor = nodes['BVT_Droplets_Voronoi' + suffix]
        check(vor.inputs['Scale'].is_linked, f'Unlinked scale for {suffix}')
        scale_driver = next(link.from_node for link in first.active_material.node_tree.links
                            if link.to_socket == vor.inputs['Scale'])
        drivers = first.active_material.node_tree.animation_data.drivers
        scale_path = scale_driver.inputs[0].path_from_id('default_value')
        check(any(fc.data_path == scale_path and
                  any(target.data_path == '["bvt_artifact_droplet_scale"]'
                      for var in fc.driver.variables for target in var.targets)
                  for fc in drivers),
              f'Droplet Scale driver missing: {suffix}')
    edge = nodes['BVT_Frost_Edge_Mask']
    check(edge.outputs['Result'].is_linked, 'Frost edge mask is disconnected')
    check(nodes.get('BVT_Droplets_Voronoi') is not None, 'Droplet Voronoi node missing')
    offset = active_seed_offset(first)
    # Blender vector sockets store float32, while Python seed_offsets uses
    # double-precision floats. Compare the exact float32 representations.
    expected_offset = tuple(
        struct.unpack('<f', struct.pack('<f', value))[0]
        for value in seed_offsets(72)
    )
    check(tuple(offset) == expected_offset,
          f'Expected deterministic float32 offset: {tuple(offset)} != {expected_offset}')
    check(second.active_material == second_material, 'Other glass material replaced')
    check(second.get('bvt_artifact_preset') == 'CUSTOM', 'Other glass preset changed')
    check(max(abs(first.matrix_world[r][c] - first_world[r][c])
              for r in range(4) for c in range(4)) < 1e-6,
          'Preset altered glass transform')
    check(max(abs(second.matrix_world[r][c] - second_world[r][c])
              for r in range(4) for c in range(4)) < 1e-6,
          'Preset altered other glass transform')

    check(bpy.ops.bvt_studio.apply_glass_preset() == {'FINISHED'},
          'Reapply same preset failed')
    new_offset = active_seed_offset(first)
    check(new_offset == offset, 'Same seed changed procedural pattern')
    first['bvt_artifact_seed'] = 73
    check(bpy.ops.bvt_studio.refresh_glass_pattern() == {'FINISHED'},
          'Refresh pattern failed')
    # Read the actual shader currently assigned to the object, not the old
    # nodes collection captured before one or more material rebuilds.
    changed = active_seed_offset(first)
    expected_changed = tuple(
        struct.unpack('<f', struct.pack('<f', value))[0]
        for value in seed_offsets(73)
    )
    check(changed == expected_changed,
          f'Active shader has wrong seed=73 pattern: {changed} != {expected_changed}')
    check(changed != offset, 'Seed refresh did not change UV pattern')
    check(first['bvt_artifact_seed'] == 73, 'Object seed reverted during refresh')
    check(second.active_material == second_material,
          'Refreshing first glass affected second glass material')
    print('BVT GLASS ARTIFACTS SMOKE: OK — seeded presets, independent targets, locked scene, geometry unchanged')
