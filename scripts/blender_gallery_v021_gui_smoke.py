"""Run INSIDE the Blender GUI Python Console with Gallery v0.2.1 scene open.

Non-destructive to disk: tests operators on current in-memory scene;
DO NOT SAVE this opened scene after the test unless intended.
The user's actual manual clicks and visual appearance still need inspection.
"""
import json
import os
import bpy
from pathlib import Path

def main():
    if bpy.app.background:
        raise RuntimeError('Must run in interactive Blender GUI, not --background')
    import bvt_studio
    from bvt_studio.glass import scene_glass
    from bvt_studio.droplet_maps import packed_maps_for
    from bvt_studio.glass_v02_ui import parse_scene_config
    scene=bpy.context.scene
    glasses=scene_glass(scene)
    names=[f'Glass_p_{i:03}' for i in range(1,5)]
    actual=[obj.name for obj in glasses]
    if actual!=names:
        raise AssertionError('Open a four-glass v0.2.1 scene; found '+repr(actual))
    if not hasattr(scene,'bvt_v02_config_path'):
        raise AssertionError('BVT Studio v0.2 UI operators not registered; reinstall latest addon')
    source_file=Path(bpy.data.filepath)
    if not source_file.is_file():
        raise AssertionError('Open a saved Gallery .blend scene, do not test unsaved scene')
    if 'effects_gallery_v021' not in str(source_file):
        raise AssertionError('Open scene.blend from effects_gallery_v021 to avoid modifying unrelated work')
    # Operators invoked in the real GUI context, independent of active
    # mesh selection. Selecting Target must not mutate any object settings.
    before={obj.name:(obj.get('bvt_water_v02_seed'),obj.get('bvt_water_v02_kind'))
             for obj in glasses}
    records=[]
    for name in names:
        status=bpy.ops.bvt_studio.select_glass_v02(glass_name=name)
        if status!={'FINISHED'}:
            raise AssertionError('Glass selection operator failed: '+name)
        obj=scene.objects[name]
        if scene.bvt_studio.artifact_target_glass != obj:
            raise AssertionError('Selection target is wrong: '+name)
        if scene.bvt_studio.artifact_seed != obj.get('bvt_artifact_seed'):
            raise AssertionError('UI seed not loaded from selected glass: '+name)
        records.append({'name':name,'selected':True,'seed':scene.bvt_studio.artifact_seed})
    after={obj.name:(obj.get('bvt_water_v02_seed'),obj.get('bvt_water_v02_kind'))
            for obj in glasses}
    if before!=after:
        raise AssertionError('Changing selected target modified glass data')

    repo=Path(os.environ.get('BVT_REPO_ROOT', str(source_file.parents[3])))
    example=Path(os.environ.get('BVT_EXAMPLE_DIR', str(repo/'examples/freezer_planogram')))
    config=example/'configs/scene_four_glasses_v02.json'
    if not config.is_file():raise FileNotFoundError(config)
    prepared=parse_scene_config(config)
    if set(prepared)!=set(names):
        raise AssertionError('JSON preset does not target exact 4 glass panes')
    scene.bvt_v02_config_path=str(config)
    status=bpy.ops.bvt_studio.import_glass_config_v02()
    if status!={'FINISHED'}:
        raise AssertionError('JSON import operator returned '+str(status))
    if scene.bvt_v02_config_result!='Applied 4 glass pane(s)':
        raise AssertionError('Unexpected JSON import feedback: '+scene.bvt_v02_config_result)
    atlas_id_names=[]
    for name in names:
        obj=scene.objects[name]
        expected=prepared[name]
        if obj.get('bvt_water_v02_kind')!=expected['water']['kind']:
            raise AssertionError('Imported water type mismatch: '+name)
        if obj.get('bvt_water_v02_seed')!=expected['seed']:
            raise AssertionError('Imported seed mismatch: '+name)
        bank=packed_maps_for(obj,mode='REALISTIC_ATLAS')
        atlas_id_names.append(bank['alpha'].name)
        if not all(im.packed_file for im in bank.values()):
            raise AssertionError('Packed image lost after JSON import: '+name)
    if len(set(atlas_id_names))!=4:
        raise AssertionError('Water atlas not independent per pane')
    report={'status':'PASS','mode':'interactive_gui_runtime',
            'file_tested':str(source_file),'glass_count':4,
            'selected_glasses':records,'json_path':str(config),
            'json_import':scene.bvt_v02_config_result,
            'water_kinds':{o.name:o.get('bvt_water_v02_kind') for o in glasses},
            'atlas_independent':True,
            'warning':'Operator runtime validated in GUI; human must still click UI and inspect render.'}
    output=source_file.parents[1]/'ui_gui_smoke_report.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print('GUI_GLASS_SELECT=PASS')
    print('GUI_JSON_IMPORT=PASS')
    print('GUI_SMOKE_REPORT='+str(output))
    print('SCENE_IN_MEMORY_MODIFIED=YES; REOPEN WITHOUT SAVING TO DISCARD CHANGES')

if __name__=='__main__':main()
