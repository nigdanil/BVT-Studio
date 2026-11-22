"""Shared helpers; no operators or UI dependencies."""
import bpy
from mathutils import Vector

ANNOT_PREFIX = 'plane_p_'
COLLECTION_NAME = 'BVT_Annotations'
PALETTE = (
    (0.98, 0.14, 0.18, 1.0),
    (0.10, 0.95, 0.28, 1.0),
    (0.12, 0.65, 1.00, 1.0),
    (1.00, 0.68, 0.10, 1.0),
    (0.88, 0.25, 0.95, 1.0),
    (0.99, 0.90, 0.16, 1.0),
    (0.16, 0.92, 0.85, 1.0),
    (0.99, 0.38, 0.60, 1.0),
)


def ensure_collection(scene, name):
    # Names are GLOBAL in Blender. A second scene can have BVT_Glass.001:
    # keep returning its own collection rather than creating .002, .003, ...
    for col in scene.collection.children:
        if col.get('bvt_studio_collection_role') == name or col.name == name:
            col['bvt_studio_collection_role'] = name
            return col
    # Support collections previously created by this add-on in another scene
    # before semantic collection markers were introduced.
    for col in scene.collection.children:
        if col.name.startswith(name + '.') and col.name[len(name) + 1:].isdigit():
            col['bvt_studio_collection_role'] = name
            return col
    col = bpy.data.collections.new(name)
    col['bvt_studio_collection_role'] = name
    scene.collection.children.link(col)
    return col


def scene_annotations(scene):
    """Prefer semantic metadata; accept older manually created plane_p_* objects."""
    import re
    rx = re.compile(r'^plane_p_\d+(?:\.\d+)?$', re.I)
    objects = [o for o in scene.objects if o.type == 'MESH' and
               (o.get('bvt_role') == 'annotation' or rx.fullmatch(o.name))]
    def sortkey(obj):
        m = rx.fullmatch(obj.name)
        if m:
            nm = re.search(r'plane_p_(\d+)(?:\.(\d+))?$', obj.name, re.I)
            return (0, int(nm.group(1)), -1 if nm.group(2) is None else int(nm.group(2)))
        return (1, obj.name.lower(), 0)
    return sorted(objects, key=sortkey)


def get_source(scene):
    settings = scene.bvt_studio
    obj = settings.source_object
    if obj is not None and scene.objects.get(obj.name) is not None and obj.type == 'MESH':
        return obj
    # Existing images created by previous prototypes.
    for obj in scene.objects:
        if obj.type == 'MESH' and (obj.get('bvt_role') == 'planogram_image' or
                                   obj.name.startswith('BVT_Freezer_Image_Plane')):
            return obj
    return None


def image_from_mesh(obj):
    if obj is None or obj.type != 'MESH':
        return None
    for slot in obj.material_slots:
        mat = slot.material
        if mat is not None and mat.use_nodes:
            # Keep dataset/export source provenance on the immutable original.
            original = mat.node_tree.nodes.get('BVT_Material_Original')
            if (obj.get('bvt_role') == 'planogram_image' and original is not None
                    and original.type == 'TEX_IMAGE' and original.image is not None
                    and original.get('bvt_material_original_v01') == 1):
                return original.image
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image is not None:
                    return node.image
    return None


def make_material_transparent(mat, method='DITHERED'):
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = method


def world_size_xy(obj):
    """Approximate length of local X and Y bbox edges transformed to world."""
    coords = [Vector(v) for v in obj.bound_box]
    dx = max(c.x for c in coords) - min(c.x for c in coords)
    dy = max(c.y for c in coords) - min(c.y for c in coords)
    basis = obj.matrix_world.to_3x3()
    return ((basis @ Vector((dx, 0, 0))).length,
            (basis @ Vector((0, dy, 0))).length)


def source_centroid(obj):
    return sum((obj.matrix_world @ Vector(c) for c in obj.bound_box), Vector()) / 8.0
