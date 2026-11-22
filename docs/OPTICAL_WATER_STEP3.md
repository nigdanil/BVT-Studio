# BVT Studio — Optical Water (v0.4.0-alpha.5-step3)

This is an **optional 2.5D optical approximation** for the existing generated
`REALISTIC_ATLAS` mode. It is not physically traced refraction, photogrammetry,
or a guarantee that synthetic water is photorealistic. It does not generate new
Alpha / Height / Normal maps, modify the source photo, or alter YOLO.

## What changes

- Reuses the same existing atlas and its height/normal information.
- Adds slope- and height-gated **directional contact highlights** and **opposite
  contact shadows**, bounded to avoid overwhelming retail packaging.
- Adds limited micro-bead specular accents rather than a uniform wet/white film.
- Scales existing source-photo resampling refraction by an **Optical Lens**
  multiplier. Refraction remains an approximate 2.5D image warp.
- Respects the existing analytic glass aperture and per-glass PNG Precision Mask.
- Is independent per `Glass_p_*`, saved as object custom properties in `.blend`.
- `PROCEDURAL` and `PHOTO_MAPS` retain the previous shader topology.

## Blender GUI

In 3D Viewport press `N` → **BVT Studio** → **4. Glass Artifact Engine**.
Select your **Glass Target**. Generate an atlas first if necessary, then use
**Optical Water (Realistic Atlas only)** → **Enable Optics**.

Settings: Optical Lens (default 1.45), Contact Shadow (1.0), Contact Highlight
(1.25) and Micro Glints (.35). **Disable Optics** restores the original atlas
shader without losing either bank of packed Alpha/Height/Normal images.

The optical effect appears only when the glass is using a **Light/Heavy
Condensation** preset and the `REALISTIC_ATLAS` droplet source.

## Headless A/B gallery (Windows Git Bash)

```bash
cd /d/BVT-Studio
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_optical_water_gallery.py -- \
  --photo "C:/Users/danil/Desktop/3D/Done/BVT_Freezer_Planogram_16x9_v11_eng.png" \
  --output "D:/BVT-Studio/qa_renders/optical_water_step3" --save-blend
```

The script first generates the alpha.5-step2 fixture (including its three
source modes), then renders:

- `06_optical_off.png` — masked atlas, enhancement disabled
- `07_optical_on.png` — same mask and atlas, enhancement enabled
- `08_optical_restored.png` — original atlas shader restored
- `optical_water_manifest.json` — numerical mean absolute RGB differences
- `optical_water_smoke.blend` — only when `--save-blend` is supplied

The QA script checks A/B image change, reversibility, independence of the
second glass, map bank identity and preservation of the Precision Mask.

Reopen and validate saved Blender scene:

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python-exit-code 1 \
  --python scripts/blender_optical_water_persistence_smoke.py -- \
  --blend "D:/BVT-Studio/qa_renders/optical_water_step3/optical_water_smoke.blend"
```

**Test limitations:** The fixture maps are synthetic, source-photo paths may
still be machine-specific, and optical quality requires human inspection of
full-resolution images. Neither an RGB-difference metric nor a successful smoke
test establishes visual photorealism. No YOLO files are changed.
