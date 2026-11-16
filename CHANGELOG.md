# Changelog

## 0.2.0 — 2026-11-17

- Support semantic `BVT_Glass` collection alongside `BVT_Annotations`.
- Automatically rename glass planes `Glass_p_001...N`, safely avoiding naming conflicts.
- Automatically assign the glass collection and name when configuring selected Plane.
- Recognize legacy names `Glass`, `Glass_001`, `Glas_001` via Register / Setup Glass All.
- Add explicit Register / Setup All and Renumber Glass buttons to sidebar.
- Fix stable collection identity across multiple Blender scenes.
- Add standalone GitHub-ready source repository, local build script and static tests.

## 0.1.0 — 2026-11-16

- Initial 2.5D photo setup, user-authored glass overlay material, colored YOLO Plane boxes, validation and single-image export.
