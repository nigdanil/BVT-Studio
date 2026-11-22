"""BVT Studio Glass Gallery v0.2.1 -- matched-water QA on v0.2 gallery.

Run through Blender 5.2.3 with --python ... -- --repo ... --photo ...
All source, mask and atlas image datablocks are packed. Does not edit YOLO.
"""
import argparse
import hashlib
import html
import csv
import re
import json
import sys
from pathlib import Path


def args_parse():
    v=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p=argparse.ArgumentParser()
    p.add_argument('--repo',required=True)
    p.add_argument('--photo',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--rects-file',required=True)
    p.add_argument('--config',required=True)
    p.add_argument('--mode',required=True)
    p.add_argument('--mask-dir',default=None)
    return p.parse_args(v)


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as fd:
        for b in iter(lambda: fd.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def rects_validate(path,width,height):
    j=json.loads(path.read_text(encoding='utf-8-sig'))
    if j.get('reference_size') != [width,height]:
        raise ValueError('Rectangles do not match exact photo dimensions; no silent resizing')
    rects=j.get('glass_rectangles')
    if not isinstance(rects,list) or not rects or len(rects)>20:
        raise ValueError('Expected 1..20 glass_rectangles')
    for r in rects:
        if len(r)!=4 or not all(type(x) in (float,int) for x in r):
            raise ValueError('Each glass rectangle must contain four numeric pixel coordinates')
        x0,y0,x1,y1=r
        if not (0<=x0<x1<=width and 0<=y0<y1<=height):
            raise ValueError('Invalid glass rectangle '+str(r))
    return rects


def make_mask(path,size=512):
    import numpy as np
    import bpy
    yy,xx=np.mgrid[:size,:size]
    uvx=(xx+.5)/size;uvy=(yy+.5)/size
    distance=np.minimum.reduce((uvx,1-uvx,uvy,1-uvy))
    fade=np.clip((distance-.012)/.024,0,1).astype(np.float32)
    fade=fade*fade*(3-2*fade)
    pixels=np.ones((size,size,4),np.float32)
    pixels[:,:,:3]=fade[:,:,None]
    image=bpy.data.images.new('BVT_v02_Geometric_Test_Mask',width=size,height=size,alpha=True)
    try:
        image.pixels.foreach_set(pixels.ravel())
        image.file_format='PNG';image.filepath_raw=str(path);image.save()
    finally:
        bpy.data.images.remove(image)


def get_pixels(path):
    import bpy
    import numpy as np
    image=bpy.data.images.load(str(path),check_existing=False)
    try:
        w,h=image.size[:]
        buf=np.empty(len(image.pixels),dtype=np.float32)
        image.pixels.foreach_get(buf)
        return buf.reshape(h,w,-1)[::-1,:,:3].copy()
    finally:
        bpy.data.images.remove(image)


def visibility_qa(baseline,result,rects,glass_events,threshold=4/255,uv_shifts=None):
    """Per-generated-event LOCAL RENDER DELTA, not true perceptual detection.

    Counts distinct event footprints with a measurable change after shader;
    a manual photo review remains mandatory.
    """
    import numpy as np
    if baseline.shape!=result.shape:
        raise ValueError('QA images do not align')
    h,w,_=baseline.shape
    diff=np.max(np.abs(result-baseline),axis=2)
    changed=diff>threshold
    area=np.zeros((h,w),dtype=bool)
    padded=np.zeros((h,w),dtype=bool)
    summaries=[]
    for pane_index,(rect,events) in enumerate(zip(rects,glass_events)):
        x0,y0,x1,y1=map(int,rect)
        area[y0:y1,x0:x1]=True
        padded[max(0,y0-3):min(h,y1+3),max(0,x0-3):min(w,x1+3)]=True
        counts={'macro':{'generated':0,'visible_proxy':0},
                'micro':{'generated':0,'visible_proxy':0},
                'streak':{'generated':0,'visible_proxy':0}}
        for item in events:
            name=item['type'];counts[name]['generated']+=1
            u0,v0,u1,v1=item['uv_bbox']
            if uv_shifts is not None:
                # Shader samples REPEAT(atlasUV + seed_offsets(seed)).
                # Convert generator event UV back to displayed pane UV.
                sx,sy=uv_shifts[pane_index]
                rx=(u1-u0)*.5; ry=(v1-v0)*.5
                cx=((u0+u1)*.5-sx)%1.0
                cy=((v0+v1)*.5-sy)%1.0
                u0,u1=max(0,cx-rx),min(1,cx+rx)
                v0,v1=max(0,cy-ry),min(1,cy+ry)
            left=max(0,int(x0+u0*(x1-x0)))
            right=min(w,int(x0+u1*(x1-x0))+1)
            top=max(0,int(y1-v1*(y1-y0)))
            bottom=min(h,int(y1-v0*(y1-y0))+1)
            if bottom<=top or right<=left:continue
            roi=changed[top:bottom,left:right]
            ratio=float(np.mean(roi))
            local_delta=float(np.mean(diff[top:bottom,left:right]))
            row_support=float(np.mean(np.any(roi,axis=1)))
            # Two independent tests: nonzero local appearance and spatial
            # evidence. Long running drops must span multiple rendered rows.
            seen=(ratio > (.008 if name=='micro' else .02) and
                  local_delta > (.002 if name=='micro' else .004) and
                  (name!='streak' or row_support>.20))
            counts[name]['visible_proxy']+=int(seen)
        summaries.append(counts)
    return {'changed_ratio_in_rects':float(np.mean(changed[area])) if np.any(area) else 0.,
            'leakage_pixels_beyond_3px_geometry_guard':int(np.count_nonzero(changed & ~padded)),
            'per_glass_event_visibility_proxy':summaries,
            'warning':'Visibility uses localized RGB render-delta and spatial span; NOT human recognition or photorealism.'}



def shader_signature(obj):
    """Topology-only fingerprint: exclude texture pixels/ID and node positions.

    A/B may intentionally change PNG datablocks; it must not add/remove shader
    nodes or change socket routing. Exact node links are what matters here.
    """
    if not obj.active_material or not obj.active_material.use_nodes:
        raise AssertionError('Expected node-based water material')
    tree=obj.active_material.node_tree
    nodes=sorted((n.name,n.bl_idname) for n in tree.nodes)
    links=sorted((link.from_node.name,link.from_socket.identifier,
                  link.to_node.name,link.to_socket.identifier) for link in tree.links)
    return nodes,links


def shader_state_signature(obj):
    """Renderer-affecting BVT object controls that must remain fixed for A/B.

    Generated-map provenance and image datablock IDs intentionally excluded.
    """
    keys=('bvt_artifact_seed','bvt_artifact_preset','bvt_artifact_coverage',
          'bvt_artifact_refraction','bvt_artifact_relief',
          'bvt_glass_mask_enabled','bvt_glass_mask_image',
          'bvt_optical_water_enabled','bvt_optical_stress_test',
          'bvt_optical_lens_gain','bvt_optical_edge_gain',
          'bvt_optical_glint_gain','bvt_optical_micro_gain',
          'bvt_droplet_source_mode','bvt_droplet_map_tiling',
          'bvt_droplet_map_rotation')
    return tuple((key,obj.get(key)) for key in keys)


def assert_neutral_maps(packed):
    """Check actual *packed* atlas pixels, not metadata or event counts."""
    import numpy as np
    expected={'alpha':(0.,0.,0.),'height':(0.,0.,0.),
              'normal':(.5,.5,1.)}
    if set(packed)!=set(expected):
        raise AssertionError('Neutral map triplet incomplete')
    for key,image in packed.items():
        if not image.packed_file:
            raise AssertionError('Neutral PNG is not packed: '+key)
        pix=np.empty(len(image.pixels),dtype=np.float32)
        image.pixels.foreach_get(pix)
        rgba=pix.reshape(-1,4)
        if rgba.shape[0] < 4:
            raise AssertionError('Neutral PNG has too few pixels: '+key)
        # PNG is 8-bit and the neutral normal .5 channel quantizes near .502.
        expected_rgb=np.asarray(expected[key],dtype=np.float32)
        if np.max(np.abs(rgba[:,:3]-expected_rgb))>1.5/255.:
            raise AssertionError('Neutral PNG is not neutral: '+key)


def index_update(root):
    cards=[]
    for p in sorted(root.glob('*/render.png')):
        stem=html.escape(p.parent.name)
        cards.append(f'<article><a href="{stem}/render.png"><img src="{stem}/render.png" loading="lazy"></a>'
                     f'<h3>{stem}</h3><p><a href="{stem}/scene.blend">.blend</a> &middot; '
                     f'<a href="{stem}/manifest.json">Manifest</a></p></article>')
    html_text=('<!doctype html><html lang="ru"><meta charset="utf-8"><title>BVT Glass Gallery v0.2</title>'
               '<style>body{background:#101827;color:#eff4fa;font:15px system-ui;padding:22px}'
               'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:16px}'
               'article{background:#1e293b;padding:12px;border-radius:12px}img{width:100%}'
               'a{color:#9ed4ff}h3{font-size:16px}</style><h1>BVT Studio — Glass Gallery v0.2</h1>'
               '<p>One packed Blender scene per variant. Compare against 00_clean. '
               '<p>Not a real-world water realism certification.</p><main>'+'\n'.join(cards)+'</main></html>')
    (root/'index.html').write_text(html_text,encoding='utf-8')
    rows=[]
    for path in sorted(root.glob('*/manifest.json')):
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            quality=record.get('quality') or {}
            totals={kind:[0,0] for kind in ('macro','micro','streak')}
            for pane in quality.get('per_glass_event_visibility_proxy',[]):
                for kind in totals:
                    totals[kind][0]+=pane.get(kind,{}).get('generated',0)
                    totals[kind][1]+=pane.get(kind,{}).get('visible_proxy',0)
            rows.append({'variant':record['variant'],
                        'changed_ratio':quality.get('changed_ratio_in_rects',''),
                        'changed_ratio_vs_clean':quality.get('changed_ratio_vs_clean_in_rects',''),
                        'leakage_pixels':quality.get('leakage_pixels_beyond_3px_geometry_guard',''),
                        **{kind+'_generated':totals[kind][0] for kind in totals},
                        **{kind+'_visible_proxy':totals[kind][1] for kind in totals}})
        except (OSError,ValueError,KeyError):
            continue
    if rows:
        with (root/'summary.csv').open('w',encoding='utf-8-sig',newline='') as fd:
            writer=csv.DictWriter(fd,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)


def main():
    o=args_parse()
    repo=Path(o.repo).resolve();photo=Path(o.photo).resolve();root=Path(o.output).resolve()
    rects_file=Path(o.rects_file).resolve();config_path=Path(o.config).resolve()
    masks=Path(o.mask_dir).resolve() if o.mask_dir else None
    for p in (photo,rects_file,config_path):
        if not p.is_file():raise FileNotFoundError(p)
    if not (repo/'bvt_studio'/'__init__.py').is_file():raise FileNotFoundError('No BVT checkout at '+str(repo))
    if root in (repo,photo.parent,rects_file.parent) or root == photo or root.is_relative_to(photo.parent):
        raise ValueError('Output must be separate from input photo directory/repository root')
    if masks and not masks.is_dir():raise FileNotFoundError(masks)
    if str(repo) not in sys.path:sys.path.insert(0,str(repo))

    import bpy
    import bvt_studio
    from bvt_studio.common import get_source,image_from_mesh
    from bvt_studio.glass import scene_glass,fit_glass_to_source_uv_rect
    from bvt_studio.artifact_presets import apply_preset
    from bvt_studio.glass_mask import load_mask_for_glass
    from bvt_studio.water_effects_v02 import install_on_glass,validated_config
    from bvt_studio.droplet_maps import packed_maps_for

    config=json.loads(config_path.read_text(encoding='utf-8-sig'))
    if config.get('schema')!='bvt.glass-gallery.v02':raise ValueError('Wrong gallery schema')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',o.mode):
        raise ValueError('Unsafe variant ID')
    variants=config.get('variants')
    if not isinstance(variants,dict) or o.mode not in variants:raise ValueError('Mode missing in config: '+o.mode)
    variant=variants[o.mode]
    if not isinstance(variant,dict):raise ValueError('Variant config must be object')
    allowed={'preset','coverage','intensity','refraction','relief','water','optics','stress','seed_base','pane_overrides'}
    if set(variant)-allowed:raise ValueError('Unknown variant keys '+str(set(variant)-allowed))
    if masks:
        # Mask presence checked before starting any rendering.
        rectspec=json.loads(rects_file.read_text(encoding='utf-8'))
        for i in range(len(rectspec['glass_rectangles'])):
            if not (masks/f'mask_glass_{i+1:03}.png').is_file():
                raise FileNotFoundError(masks/f'mask_glass_{i+1:03}.png')
    if not hasattr(bpy.types.Scene,'bvt_studio'):bvt_studio.register()
    image=bpy.data.images.load(str(photo),check_existing=True)
    w,h=image.size[:]
    rects=rects_validate(rects_file,w,h)
    photo_hash=digest(photo)
    if bpy.ops.bvt_studio.load_photo(filepath=str(photo))!={'FINISHED'}:
        raise RuntimeError('Load Photo failed')
    scene=bpy.context.scene
    source=get_source(scene);image_from_mesh(source).pack()
    scene.render.engine='BLENDER_EEVEE'
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB'
    scene.render.image_settings.color_depth='8'
    scene.render.resolution_percentage=100
    scene.render.film_transparent=False
    scene.view_settings.view_transform='Standard'
    target=root/o.mode
    target.mkdir(parents=True,exist_ok=True)
    mask_root=target/'masks';mask_root.mkdir(exist_ok=True)

    glass_events=[]; manifest_panes=[]; uv_shifts=[]; pending_water=[]
    for index,rect in enumerate(rects,1):
        if bpy.ops.bvt_studio.add_glass()!={'FINISHED'}:raise RuntimeError('Glass add failed')
        obj=scene_glass(scene)[-1]
        x0,y0,x1,y1=rect
        fit_glass_to_source_uv_rect(obj,source,x0/w,1-y1/h,x1/w,1-y0/h)
        name=f'Glass_p_{index:03}'
        # read possible per-pane override, preserving each independently
        override=variant.get('pane_overrides',{}).get(name,{})
        if not isinstance(override,dict):raise ValueError('Expected pane override dict')
        spec=dict(variant);spec.update(override)
        seed=int(spec.get('seed_base',72))+index-1
        preset=spec.get('preset','HEAVY_CONDENSATION')
        apply_preset(obj,preset,intensity=spec.get('intensity',1.),
                     coverage=spec.get('coverage',.55),seed=seed,
                     refraction=spec.get('refraction',.032),relief=spec.get('relief',1.))
        mask_path=(masks/f'mask_glass_{index:03}.png') if masks else mask_root/f'mask_glass_{index:03}.png'
        if not masks:make_mask(mask_path)
        load_mask_for_glass(obj,mask_path)
        waterspec=spec.get('water')
        if waterspec is not None and preset not in ('LIGHT_CONDENSATION','HEAVY_CONDENSATION'):
            raise ValueError('Water atlas requires LIGHT/HEAVY condensation preset')
        events=[]
        if waterspec is not None:
            if not isinstance(waterspec,dict):raise ValueError('Water config must be dict')
            kind=waterspec.get('kind','COMBINED')
            cfg=validated_config(waterspec.get('params',{}))
            optics=spec.get('optics',None)
            if optics is not None and not isinstance(optics,dict):raise ValueError('Bad optics')
            pending_water.append((index,obj,name,seed,waterspec,cfg,optics,bool(spec.get('stress',False))))
        glass_events.append(events)
        from bvt_studio.artifact_config import seed_offsets
        uv_shifts.append(seed_offsets(seed)[:2])
        manifest_panes.append({'name':obj.name,'seed':seed,'preset':preset,
                    'water_kind':waterspec.get('kind','COMBINED') if waterspec else None,
                    'events_generated':{k:sum(x['type']==k for x in events) for k in ('macro','micro','streak')},
                    'mask_packed':True,'atlas_packed':bool(waterspec),'stress':bool(spec.get('stress',False))})
        bpy.context.view_layer.update()

    # v0.2.1 A/B: SAME REALISTIC_ATLAS material, mask, seed, preset and
    # optical/stress branch on both sides. Only packed pixels differ:
    # neutral alpha=0, height=0, normal=(.5,.5,1) vs. real water atlas.
    # Previously we rendered procedural glass as "water-off", which made
    # generated events appear visible from unrelated shader changes.
    water_baseline=target/'preset_without_water.png'
    zero_water_report=None
    signatures={}
    state_signatures={}
    neutral_config_by_pane={}
    if pending_water:
        from bvt_studio.water_effects_v02 import DEFAULTS
        # Counts are the only differences in neutral config. Generating with
        # zero counts uses the real v0.2 Blender PNG import/pack/shader path.
        for index,obj,name,seed,waterspec,cfg,optics,stress in pending_water:
            neutral=dict(cfg)
            for count_key in ('macro_count','micro_count','streak_count'):
                neutral[count_key]=0
            neutral_config_by_pane[name]=neutral
            empty=install_on_glass(obj,kind=waterspec.get('kind','COMBINED'),seed=seed,
                        resolution=waterspec.get('resolution',512),
                        config=neutral,tiling=waterspec.get('tiling',1.),
                        optics=optics,stress=stress)
            if empty:raise AssertionError('Neutral atlas generated water elements')
            assert_neutral_maps(packed_maps_for(obj,mode='REALISTIC_ATLAS'))
            signatures[name]=shader_signature(obj)
            state_signatures[name]=shader_state_signature(obj)
            bpy.context.view_layer.update()

        scene.render.filepath=str(water_baseline)
        bpy.ops.render.render(write_still=True)
        if not water_baseline.is_file():raise RuntimeError('Neutral water-off render missing')

        # Independent zero-water null test: REBUILD each neutral material and
        # atlas from the same inputs; the image must remain unchanged.
        for index,obj,name,seed,waterspec,cfg,optics,stress in pending_water:
            repeated=install_on_glass(obj,kind=waterspec.get('kind','COMBINED'),seed=seed,
                        resolution=waterspec.get('resolution',512),
                        config=neutral_config_by_pane[name],
                        tiling=waterspec.get('tiling',1.),optics=optics,stress=stress)
            if repeated:raise AssertionError('Repeated zero-water atlas has events')
            assert_neutral_maps(packed_maps_for(obj,mode='REALISTIC_ATLAS'))
            if signatures[name]!=shader_signature(obj):
                raise AssertionError('Neutral shader topology changed on rebuild: '+name)
            if state_signatures[name]!=shader_state_signature(obj):
                raise AssertionError('Neutral shader controls changed on rebuild: '+name)
            bpy.context.view_layer.update()
        repeated_path=target/'zero_water_rebuild.png'
        scene.render.filepath=str(repeated_path)
        bpy.ops.render.render(write_still=True)
        if not repeated_path.is_file():raise RuntimeError('Neutral rebuild render missing')
        baseline_pixels=get_pixels(water_baseline)
        repeated_pixels=get_pixels(repeated_path)
        neutral_qa=visibility_qa(baseline_pixels,repeated_pixels,rects,
                    [[] for _ in rects],threshold=4/255)
        if neutral_qa['changed_ratio_in_rects']!=0 or neutral_qa['leakage_pixels_beyond_3px_geometry_guard']!=0:
            raise AssertionError('Zero-water null render differs beyond 4/255: '+str(neutral_qa))
        max_abs=float(__import__('numpy').max(__import__('numpy').abs(repeated_pixels-baseline_pixels)))
        zero_water_report={
            'status':'PASS','baseline':'preset_without_water.png',
            'rerender':'zero_water_rebuild.png',
            'changed_pixels_gt_4_255':0,'max_abs_rgb':max_abs,
            'same_mode':'REALISTIC_ATLAS','same_shader_topology':True,'same_renderer_controls':True,
            'neutral_alpha':0.,'neutral_height':0.,
            'neutral_normal_rgb':[.5,.5,1.],
            'events_generated':0,'events_visible_proxy':0,
        }

    # Final water map: only pixel data and the generated-event provenance
    # differ from the neutral water-off control. No geometry/YOLO mutations.
    for index,obj,name,seed,waterspec,cfg,optics,stress in pending_water:
        events=install_on_glass(obj,kind=waterspec.get('kind','COMBINED'),seed=seed,
                    resolution=waterspec.get('resolution',512),
                    config=cfg,tiling=waterspec.get('tiling',1.),
                    preview_dir=target/'maps'/name,
                    optics=optics,stress=stress)
        for channel,img in packed_maps_for(obj,mode='REALISTIC_ATLAS').items():
            if not img.packed_file:raise RuntimeError(f'{name}: {channel} map not packed')
        if signatures[name]!=shader_signature(obj):
            raise AssertionError('Final water changed shader topology: '+name)
        if state_signatures[name]!=shader_state_signature(obj):
            raise AssertionError('Final water changed renderer controls: '+name)
        if not events:
            # Explicit no-water user config must have zero events, and the
            # visual metrics must remain neutral. Never invent visibility.
            pass
        glass_events[index-1]=events
        manifest_panes[index-1]['events_generated']={
            k:sum(e['type']==k for e in events) for k in ('macro','micro','streak')}
        manifest_panes[index-1]['neutral_baseline_mode']='REALISTIC_ATLAS'
        manifest_panes[index-1]['shader_topology_unchanged']=True
        manifest_panes[index-1]['renderer_controls_unchanged']=True
        bpy.context.view_layer.update()

    scene.bvt_studio.artifact_target_glass=scene_glass(scene)[0]
    scene['bvt_gallery_v02_variant']=o.mode
    scene['bvt_gallery_v02_source_sha256']=photo_hash
    scene['bvt_gallery_v02_mask_provenance']='external_not_verified' if masks else 'synthetic_geometry_not_ground_truth'
    scene.render.filepath='//render.png'
    out_blend=target/'scene.blend'
    if bpy.ops.wm.save_as_mainfile(filepath=str(out_blend),compress=True)!={'FINISHED'}:
        raise RuntimeError('Failed to save scene')
    bpy.ops.render.render(write_still=True)
    render=target/'render.png'
    if not render.exists():raise RuntimeError('No rendered PNG '+str(render))
    qa=None
    clean=root/'00_clean'/'render.png'
    if o.mode!='00_clean' and clean.is_file():
        # Non-water variants compare to clean; water variants compare to the
        # paired identical-preset control with water generator OFF.
        baseline=water_baseline if pending_water else clean
        qa=visibility_qa(get_pixels(baseline),get_pixels(render),rects,glass_events,
                         uv_shifts=uv_shifts)
        qa['comparison_baseline']='preset_without_water.png' if pending_water else '../00_clean/render.png'
        if pending_water:
            qa['baseline_mode']='REALISTIC_ATLAS_NEUTRAL_SAME_SHADER'
            qa['null_test']=zero_water_report
            qa['visibility_proxy_caveat']='Local overlapping event ROIs may share pixel changes; proxy is NOT object instance detection.'
        if pending_water:
            against_clean=visibility_qa(get_pixels(clean),get_pixels(render),rects,[[] for _ in rects])
            qa['changed_ratio_vs_clean_in_rects']=against_clean['changed_ratio_in_rects']
        if qa['leakage_pixels_beyond_3px_geometry_guard']:
            raise AssertionError('Possible glass area leakage: '+str(qa['leakage_pixels_beyond_3px_geometry_guard']))
    if photo_hash!=digest(photo):raise AssertionError('Original source photo changed')
    manifest={'schema':'bvt.glass-gallery.v02','variant':o.mode,'blender':bpy.app.version_string,
              'source_sha256':photo_hash,'source':str(photo),'rects':rects,
              'mask_provenance':scene['bvt_gallery_v02_mask_provenance'],
              'panes':manifest_panes,'quality':qa,
              'zero_water_test':zero_water_report,
              'calibration':'v0.2.1_matched_neutral_realistic_atlas',
              'warning':'No YOLO changes; 2.5D scene/render QA does not prove physical realism or detector gains.'}
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    index_update(root)
    print('BVT GALLERY v02.1 OK: '+o.mode)
    print('SCENE='+str(out_blend))
    print('RENDER='+str(render))
    if zero_water_report:
        print('ZERO_WATER_NULL_TEST=PASS')
        print('NEUTRAL_CONTROL=REALISTIC_ATLAS_SAME_SHADER')
    if qa:
        print('QA_CHANGED='+str(qa['changed_ratio_in_rects']))
        print('QA_VISIBLE_PROXY='+str(qa['per_glass_event_visibility_proxy']))


if __name__=='__main__':main()
