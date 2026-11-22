# Single-glass presets for BVT Studio v0.4.0-alpha.5-demo.2

Each JSON targets exactly `Glass_p_001`, not the active selection. The mesh must already be registered as a BVT glass overlay. These presets do not create glass, import the photograph, or modify YOLO geometry.

Choose a JSON from an effect group under `examples/freezer_planogram/configs/presets/single_glass/`.
In Blender: N > BVT Studio > 3A. Glass Target & Presets v0.2 > JSON > select one file > Import Glass Preset JSON v0.2. Expected: `Applied 1 glass pane(s)`. Render with F12.

00–12 use the existing gallery configurations for the first pane (seed 72), translated into the GUI import format. 13 is an additional normal CLEAN preset. 00 is QA_TRANSPARENT, intended as an inert reference. 12 is a QA stress preset, not a production recommendation. For 09, optics is explicitly disabled; omitting optics in the GUI would turn it on by default. The procedural presets have no water atlas request. The current importer switches REALISTIC_ATLAS back to PROCEDURAL for non-water presets, but does not explicitly reset PHOTO_MAPS; if using external PHOTO_MAPS, switch to PROCEDURAL manually first. Existing masks and photo geometry affect appearance. Old atlas metadata can remain when switching modes; the active droplet mode determines use. The JSON importer uses its own default mask inset/feather/aperture parameters, so these are gallery parameter equivalents, not guarantees of pixel-identical gallery images in arbitrary scenes.

Validation: all 14 JSON files were accepted by the extracted parse_scene_config function from the shipped Demo 1 add-on (same parser as reviewed in main); all seven water configurations also generated arrays and events with the pure NumPy generator. Blender GUI import/render was not executed for this pack.
