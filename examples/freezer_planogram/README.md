# Freezer planogram reference (1672 x 941)

- `images/`: `chatgpt_000011.png`, the exact synthetic source image from the calibrated gallery.
- `configs/`: editable example copies of the canonical regression JSON files.
  The rectangles are approximate, not verified real-glass ground truth.
- `masks/`: optional generated per-pane precision-mask PNG examples.
- `maps/`: optional generated Alpha/Height/Normal PNG triplets (synthetic,
  not photographs); no external maps are necessary for REALISTIC_ATLAS.
- `labels/`: reserved for genuine YOLO annotations; no labels are fabricated.
- `scenes/`: reserved for small manually curated example .blend files.
  Bulk .blend/PNG outputs belong in ignored `qa_renders/`.

Default run: `bash scripts/run_bvt_water_qa_v021.sh`.
For GUI preset import, use `configs/presets/scenes/scene_four_glasses_v02.json` **in this example**.
Generated test masks and maps, if copied, originate from
`effects_gallery_v021/10_combined_water_optics`. The gallery regenerates them;
these example PNGs are provided for manual UI testing only.

### Configuration directories

- `configs/geometry/`: rectangle positions (not GUI presets).
- `configs/gallery/`: batch gallery configuration (not a GUI preset).
- `configs/presets/scenes/`: one-, two- and four-pane scene presets.
- `configs/presets/single_glass/`: 14 presets grouped by effect.

The GUI importer targets explicit object names; single-glass presets require `Glass_p_001`. The example manifest allowlists the catalog for validation and future release ZIPs.
