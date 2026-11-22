# Reference rebase v0.1

A changed pane in the manually annotated reference is not evidence of a changed
product box, but cannot be accepted as the geometry baseline. Use the immutable
SHA-verified `clear_glass__00_clean` as a new reference. The old propagation
worker and its strict matrix geometry/pixel gates remain unchanged.

The rebase CLI validates the source export, original box projection, camera/photo
fingerprint, exact RGB identity with control, and copies only raw evaluated
annotation vertices and faces into a newly saved scene. It recreates outline
materials and preserves names, UIDs and class IDs. It checks all boxes before
and after save/reopen, full control geometry after save/reopen, and re-renders
the scene with outlines hidden. The host requires exact clean RGB equality and
unchanged input hashes before publishing a new ZIP. The original annotation
manifest coordinates and label bytes are retained; the glass metadata comes
from the new reference. The original SVG preview is copied unchanged.

Run from the repository root (existing Step 5 and depth hotfix required):

```
python scripts/bvt_yolo_reference_rebase.py --reference-zip qa_renders/yolo_export_v1.zip --matrix-dir qa_renders/material_artifact_full_v03 --output-dir qa_renders/yolo_reference_rebase_v01 --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
```

Use `qa_renders/yolo_reference_rebase_v01/yolo_export_rebased_v02.zip` as the
new `--reference-zip` for existing pilot/full propagation commands. On failure,
inspect report.json, geometry.json and blender.log. Never edit the original
matrix or its hashes. The rebased scene is an annotation reference, not a new
independent source group or proof of visible bounds through refractive glass.
