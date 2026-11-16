## 0.2.1 — Installed-version clarity and safer photo/glass workflow

- Display the actual loaded add-on version in the sidebar (helps identify stale installs).
- Keep a configured source photo when a non-image Plane is active; avoid the
  misleading `Select a mesh with an Image Texture material` error.
- Add `Setup Selected Planes (Batch)` to register multiple untextured glass
  meshes and place them in `BVT_Glass` as `Glass_p_001...N`.
- Preserve original camera, transforms, material protection and YOLO objects.
- Add regression tests for photo source selection and UI registration.

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
