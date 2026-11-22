"""Opt-in material bake on the source texture; glass shaders sample the same bake.

The source image node and its links remain intact. An unlinked image node owns
an immutable reference to the original, which image_from_mesh returns for exports.
No geometry or artifact parameters are edited. Explicit rebake after geometry/mask edits.
"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import bpy
from .glass_material_config import validate_material, neutral_appearance, require
from .glass_material_builtin import builtin_profile
from .glass_materials import render_materials
from .glass_material_png import decode_png, encode_rgb
from .glass_material_geometry import pane_rect, resize_mask

ORIGINAL_NODE='BVT_Material_Original'
SOURCE_NODE='BVT_Source_Image'
PROFILE_KEY='bvt_material_profile_v01'
SEED_KEY='bvt_material_seed_v01'
BAKE_KEY='bvt_material_bake_v01'


def source_nodes(source):
    require(source is not None and source.get('bvt_role')=='planogram_image', 'Choose a registered BVT source photo')
    require(len(source.material_slots)==1, 'Material bake supports the standard BVT photo material')
    mat=source.material_slots[0].material
    require(mat and mat.use_nodes and mat.node_tree, 'Missing source material')
    nodes=mat.node_tree.nodes; tex=nodes.get(SOURCE_NODE); original=nodes.get(ORIGINAL_NODE)
    require(tex and tex.type=='TEX_IMAGE' and tex.image, 'Load Photo with BVT before using materials')
    if original is not None:
        require(original.type=='TEX_IMAGE' and original.image and original.get('bvt_material_original_v01')==1 and not any(s.is_linked for s in original.outputs), 'Invalid original image backup')
        require(tex.image.get('bvt_material_baked_v01')==1, 'Source bake was edited; restore the standard source first')
    else:
        require(not tex.image.get('bvt_material_baked_v01'), 'Missing original image backup; refuse cumulative bake')
    return mat,tex,original


def effective_source_image(source, fallback):
    # Legacy scenes do not enter the new path at all.
    if source is not None:
        for slot in source.material_slots:
            mat=slot.material
            if mat and mat.use_nodes and mat.node_tree.nodes.get(ORIGINAL_NODE) is not None:
                return source_nodes(source)[1].image
    return fallback


def image_bytes(image):
    require(image.source=='FILE', 'Material layer requires a file-based PNG')
    if image.packed_file: return bytes(image.packed_file.data)
    path=Path(bpy.path.abspath(image.filepath,library=image.library))
    require(path.is_file(), 'Original source PNG is missing')
    return path.read_bytes()


def _corners(obj, source, bounds):
    require(len(obj.data.vertices)==4 and len(obj.data.polygons)==1 and len(obj.data.polygons[0].loop_indices)==4 and obj.data.uv_layers.active, obj.name+': expected a single rectangular UV quad')
    require(not obj.modifiers, obj.name+': modifiers not supported by material bake')
    matrix=source.matrix_world.inverted() @ obj.matrix_world
    (xmin,ymin),(dx,dy)=bounds
    points=[]; zs=[]
    for loop in obj.data.polygons[0].loop_indices:
        co=matrix @ obj.data.vertices[obj.data.loops[loop].vertex_index].co
        uv=obj.data.uv_layers.active.data[loop].uv
        points.append(((co.x-xmin)/dx,(co.y-ymin)/dy,float(uv.x),float(uv.y))); zs.append(co.z)
    require(max(zs)-min(zs)<1e-5, obj.name+': pane must be parallel to source')
    return points


def _settings(obj, override=None):
    if override is not None: doc,seed=override
    else:
        raw=obj.get(PROFILE_KEY)
        doc=json.loads(raw) if raw else builtin_profile('clear_glass')
        seed=obj.get(SEED_KEY,72)
    require(type(seed) is int and 0<=seed<2**31, 'Invalid material seed')
    return validate_material(doc),seed


def _require_private_material(obj, mat):
    """A single object can own a material via both Object and Mesh slots.

    ID.users counts references, not distinct owners. Check all datablocks,
    including objects outside the current scene, before mutating shader nodes.
    """
    require(not mat.library, obj.name + ': linked material')
    owners = bpy.data.user_map(subset=[mat]).get(mat, set())
    require(bool(owners) and owners.issubset({obj, obj.data}),
            obj.name + ': shared material (other datablock owns it)')
    require(not any(other != obj and getattr(other, 'data', None) == obj.data
                    for other in bpy.data.objects),
            obj.name + ': shared mesh (another object uses it)')


def _scene_data(scene, target=None, override=None):
    from .common import get_source
    from .glass import scene_glass
    from .glass_realism import image_uv_bounds
    source=get_source(scene); mat,tex,backup=source_nodes(source)
    original=backup.image if backup is not None else tex.image
    # Refuse multiple photo layers, shared scene objects/materials and linked data.
    others=[o for o in scene.objects if o!=source and o.get('bvt_role')=='planogram_image']
    require(not others, 'Material layer v0.1 requires one registered source per scene')
    require(len(source.users_scene)==1 and not source.library and not source.data.library, 'Material layer requires a private local photo object')
    _require_private_material(source, mat)
    glasses=[o for o in scene_glass(scene) if o.get('bvt_role')=='glass_overlay']
    if target is not None: require(target in glasses, 'Target must be a registered glass in this scene')
    settings=[(o,*_settings(o,override if o==target else None)) for o in glasses]
    active=[(o,d,s) for o,d,s in settings if not neutral_appearance(d['appearance'])]
    # Capture old effective-source reference slots. No shader rebuild is necessary;
    # future artifact builds use effective_source_image via source_for_glass.
    refs=[]
    for o in glasses:
        require(len(o.users_scene)==1 and not o.library and not o.data.library, o.name+': shared or linked glass')
        for sl in o.material_slots:
            gm=sl.material
            if gm and gm.use_nodes:
                for n in gm.node_tree.nodes:
                    if n.type=='TEX_IMAGE' and n.image is not None and n.image in (tex.image,original):
                        _require_private_material(o, gm)
                        refs.append(n)
    if not active: return source,tex,backup,original,refs,[],None
    bounds=image_uv_bounds(source)
    require(bounds is not None and not source.modifiers,'Source requires standard affine rectangular UVs')
    require(original.colorspace_settings.name=='sRGB','Material source must use sRGB color space')
    raw=image_bytes(original); rgb=decode_png(raw)
    h,w=rgb.shape[:2]; require(tuple(original.size)==(w,h),'Source image size mismatch')
    all_rects=[]; assignments=[]; records=[]
    from .glass_mask import mask_image_for
    for o,doc,seed in settings:
        r=pane_rect(_corners(o,source,bounds),w,h)
        x0,y0,x1,y1=r
        require(not any(x0<b[2] and x1>b[0] and y0<b[3] and y1>b[1] for b in all_rects),'Overlapping glass panes are unsupported by material bake')
        all_rects.append(r)
        if neutral_appearance(doc['appearance']): continue
        a={'rect':r,'material':doc,'seed':seed}
        mask=mask_image_for(o); digest=None
        if mask is not None:
            mdata=image_bytes(mask); digest=hashlib.sha256(mdata).hexdigest()
            a['mask']=resize_mask(decode_png(mdata,mask=True),y1-y0,x1-x0)
        assignments.append(a); records.append({'name':o.name,'rect':r,'material':doc,'seed':seed,'mask_sha256':digest})
    baked=encode_rgb(render_materials(rgb,assignments))
    state={'schema':'bvt.glass-material-bake.v01','original_sha256':hashlib.sha256(raw).hexdigest(),'baked_sha256':hashlib.sha256(baked).hexdigest(),'panes':records,'status':'EXPERIMENTAL_UNCALIBRATED'}
    return source,tex,backup,original,refs,settings,(baked,state)


def _packed_bake(data,state):
    with TemporaryDirectory(prefix='bvt_material_v01_') as tmp:
        path=Path(tmp)/('material_'+state['baked_sha256'][:16]+'.png'); path.write_bytes(data)
        im=bpy.data.images.load(str(path),check_existing=False)
        try:
            im.colorspace_settings.name='sRGB'; im.pack()
            require(im.packed_file and hashlib.sha256(bytes(im.packed_file.data)).hexdigest()==state['baked_sha256'],'Material PNG pack mismatch')
            relative='//'+path.name; im.filepath_raw=relative
            for p in im.packed_files: p.filepath=relative
            im['bvt_material_baked_v01']=1
            return im
        except Exception:
            bpy.data.images.remove(im); raise


def _remove_unused(im):
    if im is not None and im.get('bvt_material_baked_v01') and im.users==0:
        bpy.data.images.remove(im)


def rebuild_materials(scene, target=None, profile=None, seed=72):
    """Apply one profile or refresh all stored profiles from immutable original.

    No cumulative image manipulation. Geometry/mask preflight precedes publication
    of a new bake. Clear leaves/restores the original source image object.
    """
    require(target is None or profile is not None,'Target requires a material')
    override=(validate_material(profile),seed) if target is not None else None
    if target is not None: require(type(seed) is int and 0<=seed<2**31,'Invalid seed')
    source,tex,backup,original,refs,settings,result=_scene_data(scene,target,override)
    old=tex.image; old_refs=[(n,n.image) for n in refs]
    old_state=source.get(BAKE_KEY); old_profile=target.get(PROFILE_KEY) if target is not None else None; old_seed=target.get(SEED_KEY) if target is not None else None
    new=None; created=None; nodes=tex.id_data.nodes
    def restore(obj,k,value):
        if value is None:
            if k in obj: del obj[k]
        else: obj[k]=value
    try:
        if result is not None:
            data,state=result
            if not original.packed_file: original.pack()
            require(original.packed_file and hashlib.sha256(bytes(original.packed_file.data)).hexdigest()==state['original_sha256'],'Original PNG packing changed bytes')
            new=_packed_bake(data,state)
            if backup is None:
                created=nodes.new('ShaderNodeTexImage'); created.name=ORIGINAL_NODE; created.label='BVT immutable original (do not edit)'; created.hide=True; created.image=original; created['bvt_material_original_v01']=1
                require(created.name==ORIGINAL_NODE,'Original node name collision')
            tex.image=new
            for n in refs: n.image=new
            source[BAKE_KEY]=json.dumps(state,sort_keys=True,separators=(',',':'))
        else:
            tex.image=original
            for n in refs: n.image=original
            if BAKE_KEY in source: del source[BAKE_KEY]
        if target is not None:
            target[PROFILE_KEY]=json.dumps(override[0],sort_keys=True,separators=(',',':')); target[SEED_KEY]=seed
        if result is None and backup is not None: nodes.remove(backup)
    except Exception:
        tex.image=old
        for n,im in old_refs: n.image=im
        if created is not None: nodes.remove(created)
        restore(source,BAKE_KEY,old_state)
        if target is not None: restore(target,PROFILE_KEY,old_profile); restore(target,SEED_KEY,old_seed)
        _remove_unused(new); raise
    _remove_unused(old)
    return result[1] if result is not None else None
