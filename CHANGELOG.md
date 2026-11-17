# Changelog

## 0.3.0-alpha.5 — YOLO Preview / Portable Export

- Export a browser-viewable SVG bounding-box preview aligned with the actual YOLO TXT and clean PNG.
- Use dataset-relative `train`/`val` references in `data.yaml`, removing machine-specific absolute paths.
- Keep validation split empty for single-photo export; warn in documentation before model training.
- Add Open Last YOLO Preview in sidebar; preserve clean training images.
- Add Python tests and a Blender render/export smoke test.


## 0.3.0-alpha.4 — YOLO Quality Gate

- Show a structured validation report in the BVT Studio sidebar (blocking errors and review warnings).
- Select affected annotation objects directly from the report.
- Warn about small projected boxes and high overlap without blocking clean exports.
- Recompute validation on every export; keep existing geometry/class error rules blocking.
- Add dependency-free checks and a Blender 5.2+ headless smoke test.


## 0.3.0-alpha.3 — Annotation Manager

- Add a persistent annotation list with Blender UIList and click-to-select behavior.
- Refresh list after Add/Register/Renumber and on demand after Outliner deletions.
- Add Select All Annotations and batch class ID/name editing for selected boxes.
- Add batch Enabled toggle for including/excluding selected boxes in YOLO.
- Prevent batch class assignments that conflict with names of an existing class ID.
- Add unit tests and a Blender 5.2+ headless annotation manager smoke test.


## 0.3.0-alpha.2 — 2026-11-17

- Add Photo-relative layer depth constraints in the source image coordinate system.
- Protect Photo, Glass and YOLO annotation depth independently of selection locks.
- Support photo object rotations, parent transforms and non-uniform scale.
- Add selected Glass Depth Offset (camera-facing) and Reset Layer Depth.
- Preserve existing positions for previously configured glass/annotation meshes.
- Project original YOLO mesh vertices through evaluated object transforms (including depth constraints).
- New depth controls are added to the sidebar; future Blender smoke test required.


## 0.3.0-alpha.1 — 2026-11-17

- Add Scene Editing / Locks group and per-group Edit Enable toggles.
- Add Lock Scene for Annotation and confirmation-based Unlock Scene.
- Snapshot and restore original Blender selection/transform locks per managed object.
- Auto-protect newly imported photo scene; keep glass and annotations editable initially.
- Reapply BVT locks when new glass/annotation planes are registered.
- No depth constraints yet: rotated-photo normal constraints are separate roadmap item 1.0.1.

## 0.2.2 — 2026-11-17

- Add **Add Glass** button directly to Blender's BVT Studio glass panel.
- Auto-create a reusable Glass_p_### mesh, procedural material and BVT_Glass registration.
- Place the new Plane slightly in front of the photo; default left/right guides on first two clicks.
- Select the generated glass automatically for quick move/scale; keep camera and source unchanged.
- Add geometry, registration and UI unit tests without Blender runtime dependencies.

## 0.2.1 — Installed-version clarity and safer photo/glass workflow

- Display the actual loaded add-on version in the sidebar (helps identify stale installs).
- Keep a configured source photo when a non-image Plane is active; avoid the
  misleading `Select a mesh with an Image Texture material` error.
- Add `Setup Selected Planes (Batch)` to register multiple untextured glass
  meshes and place them in `BVT_Glass` as `Glass_p_001...N`.
- Preserve original camera, transforms, material protection and YOLO objects.
- Add regression tests for photo source selection and UI registration.

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
