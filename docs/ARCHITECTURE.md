# BVT Studio Architecture (0.2)

**Standalone Blender Add-on** for photo-backed 2.5D scenes.

- `scene_tools.py` — photo import, image plane, camera framing and resolution profiles
- `glass.py` — glass material drivers, legacy glass detection, scene collection organization, stable glass naming
- `annotation.py` — independent annotation plane collection, colored outline preview and YOLO export
- `common.py` — shared Blender scene helpers and semantic collections
- `props.py` — UI settings and camera profiles
- `ui.py` — viewport sidebar

Naming and scene collections:

- `BVT_Glass` holds `Glass_p_001 ... Glass_p_N` user-authored glass surfaces. These are renderable.
- `BVT_Annotations` holds `plane_p_001 ... plane_p_N` annotation guides. They are hidden during clean dataset export.
- Each glass object has `bvt_glass_uid` and `bvt_glass_index`, plus driver-backed reflection/tint/haze/frost properties.
- Never treat a rendered Wireframe modifier as a YOLO bbox. Export should project original mesh vertices.
- Never overwrite a textured source/photo plane to create glass.
- Phone/tablet v0.2 profiles are currently framing only; mobile sensor simulation is not yet supported.

Integration with the main BVT project is a separate future milestone, not a dependency for the standalone add-on.
