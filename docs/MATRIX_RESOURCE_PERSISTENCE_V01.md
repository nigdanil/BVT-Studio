# Matrix packed resource persistence v0.1

The original Step 4 worker compared live `Image.size` along with packed SHA-256 and paths. A reopened image may have no loaded pixel buffer, so runtime dimensions are not a stable serialized-resource identifier. The failure reported on the clear control did not show which field differed.

This patch obtains PNG dimensions from IHDR and EXR dimensions from dataWindow. It keeps exact equality of named resources, packed bytes (SHA-256), canonical dimensions, image paths and packed-file paths, and requires exact RGB equality on rerender. A nonzero runtime dimension mismatch is still an error. Header parsing is not full image decoding. Only single-payload PNG and single-part non-deep EXR are supported.

Each job writes `resource_persistence.json` with before/after resource records, raw runtime dimensions, differences, and rerender metrics. Missing, changed or nonportable packed data is never silently accepted. If the check fails, keep the failing job and send this JSON and blender.log. No changes to the add-on or rendering engine are made. Repeat the single clear control before running the pilot or full matrix.

## Windows path spelling hotfix v0.2

The clear-control diagnostic showed identical names, bytes and dimensions for all five resources. Blender changed only `Image.filepath` from `//resources/<sha>.png` to the Windows spelling `//resources\<sha>.png`; packed-file paths stayed unchanged. Both path fields now normalize only separators after the literal Blender-relative prefix `//` and must equal the exact expected content-addressed path. Case, filename, folder, digest, dimensions, resource membership and exact decoded RGB checks remain strict. Absolute paths, traversal and wrong filenames fail. Raw paths at comparison time are included in diagnostics.
