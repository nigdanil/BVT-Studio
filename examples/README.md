# BVT Studio examples

Self-contained, small reproducible inputs; source code stays in `bvt_studio/`,
canonical regression configurations in `configs/`, and generated results in
`qa_renders/` (ignored by Git). `local/` is an ignored area for private or large data.

- `freezer_planogram/`: synthetic four-pane reference fixture from Gallery v0.2.1,
  including scene and effect JSON, source image, and optional sample mask/map PNGs.
- Run `bash scripts/run_bvt_water_qa_v021.sh` from the repository or invoke it
  using its full path. It locates the repository relative to the runner.
- Override input paths with `BVT_EXAMPLE_DIR`, `BVT_PHOTO`, `BVT_RECTS`,
  `BVT_CONFIG`, and Blender with `BVT_BLENDER`. `BVT_OUTPUT_DIR` overrides the
  default output. Use absolute paths for overrides.
- Only commit images and assets you have permission to redistribute. Do not
  commit customer photos, full training datasets, or generated galleries.

The Demo fixture uses only `freezer_planogram/images/chatgpt_000011.png` as its source image. The full Research collections belong in `../data_local/`, not in examples or release archives. See [dataset setup](../datasets/README.md). The demo does not include verified YOLO labels.

For the JSON catalog see [freezer_planogram](freezer_planogram/README.md). Only `configs/presets/` files are intended for manual preset import.
