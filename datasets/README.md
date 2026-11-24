# BVT-Studio research dataset setup

See [collection provenance and rights](../docs/datasets/README.md) before using or distributing images. The small [Demo](../examples/README.md) does not require the full Research collections.

## Local layout

```text
 datasets/
   manifests/                  # JSONL metadata (v1)
   schemas/                    # JSON Schema (v1)
 data_local/                   # ignored by Git
   synthetic_chatgpt/
     clean/images/
     labels/
     glass_masks/
     runs/
   real_wikimedia/
     downloads_staging/
     clean/images/
     labels/
     glass_masks/
     attribution/
     runs/
```

## Restore research collections from Google Drive

1. Obtain authorized access from the dataset maintainer; no private link or credential is embedded in this repository.
2. Download/extract the two collection folders outside the repository, or use an authorized Google Drive for Desktop folder with files available offline. The source root must contain `01_ChatGPT_Synthetic/images/` and `02_Wikimedia_Commons/images/` with the established filenames. Do not use an archive file as the source root.
3. Install the dependencies from the [root README](../README.md) and run from the repository root:

```bash
python scripts/prepare_research_datasets.py --source-copy /path/to/BVT-Studio-Datasets
python scripts/prepare_research_datasets.py --check
```

The restore command uses the repository JSONL manifests as the expected inventory. It creates the local directories, verifies existing images, preflights missing source files and copies only missing images. A complete cache is reused without accessing the source folder; `--check` is strictly read-only and works offline without a source path. Both modes reject unexpected files in clean image directories, bad hashes, formats, dimensions and inconsistent manifest paths. A corrupted existing image is reported, never overwritten; preserve it outside `clean/images/` for investigation before explicitly restoring the missing file. Do not run concurrent restore jobs or edit the manifests or files during restore. A failed copy attempts to remove only files created by that invocation; after a process interruption, inspect any partial file before retrying. No live Google Drive API or automatic download is implemented.

To stage collection metadata in the downloaded source copy for manual upload:

```bash
python scripts/prepare_research_datasets.py --source-copy /path/to/BVT-Studio-Datasets --export-metadata
```

This verifies the full external image inventory, then creates `manifest.jsonl` (exact repository JSONL bytes) and `SHA256SUMS.txt` (100 collection-relative `images/` paths) in each collection directory. Identical files are reused; different files cause an error, not an overwrite. Upload these four metadata files to the matching authorized Drive folders manually; do not upload backup files, credentials, or duplicate images. The three existing provenance documents remain in the Drive root for now. If the source is a synchronized Desktop folder, writing metadata there may synchronize it automatically. The export checks bytes, not licensing or live cloud availability.

Keep the six-digit IDs and actual extensions stable. Preserve `clean/images/` unchanged. The demo source is intentionally also present in the synthetic Research collection. Store reviewed YOLO annotations and glass masks separately, linked by source ID; do not fabricate them. Keep generated variants, reports and previews in per-run directories under `runs/`, never in the clean inputs. Keep each source group within one train/validation/test split.

The existing Dataset Runner currently supports the bundled demo; Research integration is planned. Do not commit research images, private metadata, bulk labels or generated outputs. Git ignore is not a substitute for checking staged files and asset rights before publication.

## Build the initial v1 manifests

Install the test dependencies listed in the [root README](../README.md). Run from the repository root, using the previously downloaded, authorized source copy outside the repository:

```bash
python scripts/build_dataset_manifests.py --source-copy /path/to/BVT-Studio-Datasets
python scripts/build_dataset_manifests.py --source-copy /path/to/BVT-Studio-Datasets --check
```

The builder reads the two local collections and compares each file byte-for-byte by SHA-256 against the downloaded copy. It reads the workbook by explicit numeric ID (not row order), validates the record schema, and writes two UTF-8 JSONL files, 100 records each, sorted by numeric ID. It refuses to overwrite a different existing manifest. `--check` never writes. Neither command downloads images or verifies a live Wikimedia page.

The v1 [record schema](schemas/dataset_manifest.schema.json) has 36 required fields. `relative_path` is collection-relative; `local_cache_path` is repository-relative; `storage_relative_path` is relative to the authorized Drive dataset root. All use forward slashes. `source_registry_version` contains the SHA-256 of the Excel workbook for real images or the provenance notice for synthetic images. `original_filename` for real images is the normalized title from the registered Commons file-page URL, not a claim about the downloaded binary filename; for synthetic images it is unknown. The real image/registry association uses the established six-digit ID convention and is not a new binary-to-live-source verification.

`integrity_status: verified` means only local decode and matching SHA-256 against the downloaded copy. `registry_page_reviewed` records the workbook's individual page-review claim, not new verification or permission to publish. Direct source URLs, independent evidence snapshots and unknown copyright notices remain null. Attribution strings for reviewed records are drafts, not complete clearance. Rights-review statuses remain pending. Scene/viewpoint/packaging fields are taken only from the workbook's detailed six-record sheet where present; other per-image descriptions remain null until separately mapped and reviewed. Source group IDs initially equal image IDs, pending near-duplicate/group review before splitting. Labels, masks and splits remain unassigned. A future audited metadata update must be reviewed separately; this initial builder intentionally refuses to overwrite a different existing JSONL.

### Audited metadata revision (stage 14D)

The descriptions above refer to the initial inventory. After promotion of the
reviewed migration bundle (see [license audit](../docs/datasets/LICENSE_AUDIT.md)),
real records additionally contain the API thumbnail URL, recorded check date,
page revision URL and attribution draft. `api_evidence_recorded` means the
source declaration was collected and matched to the image, not verified legal
rights. `manual_review_required` retains an unresolved metadata discrepancy.
The 36-field contract is unchanged apart from these two additional enum values.
The builder still refuses to replace a different JSONL. Synchronize revised
metadata using an explicit backed-up migration, not the initial exporter.

## Research run storage (v1)

Research runs are separate from the existing single-example Demo Runner (`qa_renders/`). Stage 12 provides a run registry, not an artifact renderer or a claim of verified annotations. A run belongs to one collection and has one declared preset, seed and parameter set. Use separate runs for different effects or replicates. Each selected source has at most one output in a run. The future research runner will supply effective per-image parameters when integrated.

```text
data_local/<collection>/runs/<run_id>/
  augmented/images/<image_id>.png
  previews/
  reports/
  run_manifest.json
```

From the repository root, after preparing the research cache, create a new run. Supply a JSON object containing the actual intended effect parameters (`params.json`) and, optionally, a JSON object of engine/version strings (`versions.json`). Do not commit local parameter files containing secrets. An omitted run ID produces a UUID-based ID; explicit IDs are lowercase ASCII and cannot reuse an existing run directory in either collection.

```bash
python scripts/manage_research_runs.py init --collection synthetic_chatgpt --run-id pilot-001 --preset-id 01_light_condensation --seed 42 --effect-parameters /path/to/params.json --tool-versions /path/to/versions.json --image-id chatgpt_000011
python scripts/manage_research_runs.py check --collection synthetic_chatgpt --run-id pilot-001
```

Omit `--image-id` for the whole collection; repeat the option to select multiple IDs. The prepared manifest records the dataset manifest SHA-256, Git HEAD, dirty-tree flag, hash of the actual source/config/schema files, manager and dependency versions, declared effect settings and per-source SHA-256. The code hash identifies a working-tree snapshot but does not archive it. Preserve the matching source revision/diff and renderer configuration separately for reproduction. The run starts with null output hashes, label/mask paths and generation timestamps, and pending QA. It never creates dummy output images or annotations.

After an external renderer has written the actual PNG outputs into the run's `augmented/images/`, register them (one PNG per selected source, same pixel dimensions, source ID as stem):

```bash
python scripts/manage_research_runs.py record --collection synthetic_chatgpt --run-id pilot-001
python scripts/manage_research_runs.py check --collection synthetic_chatgpt --run-id pilot-001
```

`record` validates all inputs, rejects missing/extra outputs, checks PNG decoding and dimensions, and registers output SHA-256. It refuses changed code/HEAD or dataset manifest. A successful registration is not evidence that the intended effect was actually applied, that image geometry is unchanged beyond dimensions, or that rights/labels/masks are approved. `--generated-at` optionally records a declared actual generation timestamp (ISO 8601 including timezone); otherwise it remains null and `recorded_at` records registration time. The actual renderer version is supplied by the caller, not inferred. `check` is read-only and distinguishes `prepared` from `outputs_recorded`. An existing recorded run is verified, never rewritten; use a new run ID for different results.

Optional QA input: before registration, an external QA process can write `reports/qa_results.json` with `schema: bvt.research-run.qa.v1` and a `records` array of objects containing exactly `image_id`, `input_sha256`, `output_sha256`, `qa_status` (PASS, REVIEW, REJECT or ERROR). Include every selected source, and use the actual input/output hashes. The registry binds the reported statuses and SHA-256 of this report to the run; it does not itself execute or endorse QA. Without the report, QA stays pending. Other previews/reports are caller-owned and not covered by this contract. The existing Real Dataset QA adapter and rendering integration are later stages. No existing dataset manifest or clean image is modified. Label/mask paths remain null until the annotation contract is implemented.

See [run manifest schema](schemas/run_manifest.schema.json). Do not run concurrent writers, change source files during a run, or modify registered outputs/reports. If initialization is interrupted, retain the partial run for inspection and choose a new ID. Stage 12 does not assign splits, publish data, or generate real research effects.

## Research annotation contract (v1)

Stage 13 defines the local, read-only annotation audit; it does not generate or approve any real labels or masks. Both collections use the same class taxonomy, defined by the annotator in `data_local/classes.json` (UTF-8 JSON object with `schema: "bvt.research-classes.v1"` and `classes`: an ordered nonempty list of unique class names). The zero-based list index is the YOLO class ID. No class names are assigned by this tool.

```text
data_local/classes.json
data_local/<collection>/labels/<image_id>.txt
data_local/<collection>/labels/<image_id>.json
data_local/<collection>/glass_masks/<image_id>.png
data_local/<collection>/glass_masks/<image_id>.json
```

Labels use UTF-8 YOLO Detect rows `class_id cx cy width height` with normalized top-down coordinates, finite positive extents and boxes fully inside the source image. Empty labels (including negative samples), segmentation, pose and rotated boxes are not supported by the current research QA contract. Masks are individually drawn, single-channel 8-bit grayscale PNG, source-sized, with only 0 (outside glass) and 255 (glass); empty and full-frame masks are rejected in v1. Never transplant demo masks or annotations to unrelated images. A valid format does not establish semantic correctness.

After a human inspects the source and artifact, the optional JSON sidecar (same stem, adjacent to the artifact) records exactly these fields:

| Field | Value |
| --- | --- |
| `schema` | `bvt.research-annotation-review.v1` |
| `kind` | `annotation` or `glass_mask` |
| `image_id` | Exact source ID |
| `input_sha256` | Source bytes SHA-256 from inventory |
| `artifact_sha256` | Label TXT or mask PNG bytes SHA-256 |
| `class_catalog_sha256` | Exact classes.json bytes SHA-256 for labels; null for masks |
| `decision` | `approved` or `rejected` |
| `reviewer` | Nonempty reviewer identifier supplied by reviewer |

The tool checks SHA-256 and file formats and refuses mismatched reviews. A reviewer declaration is not authenticated or independently endorsed by the tool. Missing artifacts and structurally valid but unreviewed artifacts are `pending`, with different reasons. Approved structurally valid artifacts are `verified` in the local audit only; rejected artifacts are `rejected`, invalid files are `invalid`. A canonical manifest status of `verified` or `rejected` inconsistent with evidence is an error. The initial dataset JSONL remains unchanged (both annotation fields pending); later deliberate versioned updates must use reviewed evidence, not automatic status promotion. Preserve local sidecars and class catalog separately; they are ignored by Git.

```bash
python scripts/check_research_annotations.py audit
python scripts/check_research_annotations.py audit --collection real_wikimedia --json
```

An audit with missing annotations can pass structural checks, but it is not training or QA readiness. Invalid artifacts, unexpected entries, stale declarations or corrupt inputs fail with a nonzero exit code. The JSON report goes to stdout; the tool writes no files. The audit checks source SHA-256, decoded dimensions and formats against both collection manifests.

### Geometry-preserving inheritance

A registered run must retain the original pixel coordinate system (no crop, resize, flip, warp or object displacement). Matching dimensions alone are insufficient. A human or trusted upstream review must explicitly attest geometry for each registered pair in `runs/<run_id>/reports/geometry_review.json`. This JSON object has `schema: "bvt.research-geometry-review.v1"` and `records`, a list with exactly one object per selected source. Each record has `image_id`, `input_sha256`, `output_sha256`, `transform` (`identity_pixel_grid`, `changed` or `unknown`), and nonempty `reviewer`. Input and output hashes must match the registered run. A declaration is evidence supplied by the caller, not an automatic registration or visibility test.

```bash
python scripts/check_research_annotations.py inherit --collection synthetic_chatgpt --run-id pilot-001
```

The read-only JSON result provides eligible label/mask paths and artifact/review hashes separately only if the corresponding reviewed artifact is valid and the geometry declaration is `identity_pixel_grid`. Otherwise those paths and hashes are null. The result binds the geometry review and class catalog hashes. No labels are copied, no existing manifests or runs are modified, and no split is assigned. The run registry and Demo Runner are unchanged; the later Research integration must consume this evidence and perform artifact/visibility QA separately. Preserve the report and exact artifacts for reproducibility; do not run concurrent writers.

## Dataset Validator (v1)

Run the read-only aggregate validation before preparing research experiments:

```bash
python -B scripts/validate_research_dataset.py
python -B scripts/validate_research_dataset.py --json
python -B scripts/validate_research_dataset.py --require-ready qa
python -B scripts/validate_research_dataset.py --require-ready publication
```

The validator expects both fixed v1 inventories (100 synthetic PNG and 100 real JPEG), validates JSONL records against the existing schema, checks stable IDs, paths, registry-document hashes, directories, exact inventory, SHA-256, image decoding, format and dimensions. It reuses the annotation contract to check YOLO and individual glass masks including review sidecars. The full `bvt.research-dataset-validation.v1` JSON report is emitted to stdout even on structural validation failure; save it outside the clean image folders, for example under ignored `data_local/`. No report file is written by the validator itself.

Each collection reports `expected`, `present`, `missing`, `unique_sha256`, `bad_format`, `unverified`, `ready_for_qa`, `ready_for_publication` and status distributions. `present` counts expected regular files reachable through safe paths; `unique_sha256` counts actual readable file hashes (including damaged files), `bad_format` counts wrong formats or decode failures and `unverified` counts images not successfully matched to verified manifest records. Unexpected entries, duplicate IDs/hashes, missing or invalid records/directories, stale registry versions and invalid annotations are structural errors. Both declared and actual SHA-256 duplicates are prohibited in v1; no duplicate exception mechanism is provided.

The split check rejects a declared source group or normalized Commons file title spanning different assigned train/val/test splits. Null splits are reported as `unassigned` and do not fail an infrastructure audit. This does not establish absence of semantic or near-duplicate leakage; source groups must be reviewed before training. Run outputs are outside this inventory audit and use the run registry/inheritance contracts.

Missing or unreviewed annotations, unresolved rights and unassigned splits are not structural errors. QA readiness requires a verified clean image and individually reviewed valid YOLO labels and glass mask; it does not require an assigned split and is not a training-readiness or completed render-QA claim. Publication readiness is only a conservative declared metadata gate: verified license, a supported canonical license pair, author, attribution, evidence URL/date, and all four rights review fields explicitly approved. Pending/conditional rights and API evidence alone never qualify. The supported license set is the current registry's six CC variants; extend deliberately if required. The gate does not authenticate reviewers or establish legal clearance. Known real license IDs must agree with canonical URLs, and recorded API/verified status requires evidence fields. Any structural error suppresses all readiness counts. The default exit code is 0 for structural PASS, 1 for FAIL; optional `--require-ready` additionally returns 1 unless every expected image passes the selected readiness gate. No files, annotations, splits or rights statuses are created or modified; do not run concurrent writers during validation.

## Research Dataset Runner (v1)

The existing Demo Runner command and output policy remain unchanged. Use the
explicit `research` subcommand for local research collections:

```bash
python scripts/bvt_dataset_runner.py research --collection synthetic_chatgpt --run-id pilot-plan --effect 01_light_condensation --image-id chatgpt_000011 --dry-run
python scripts/bvt_dataset_runner.py research --collection real_wikimedia --run-id clean-real --effect 00_clean --image-id wikimedia_000099 --execute
```

The default is a read-only JSON plan. Repeat `--image-id` to select multiple
images, or specify `--all` and explicitly increase `--max-images` to 100. The
initial cap is five; a fresh Run ID is required for each execution. The seed is
base seed plus numeric image ID minus one (matched across effects). One preset
per run; the existing normal presets come from `configs/effects_gallery_v02.json`.
Stress is excluded. A structurally invalid dataset blocks planning and execution.

`00_clean` writes a decoded RGB PNG identity control (not a Blender artifact
render; original JPEG bytes are never replaced). Other effects require a reviewed
individual binary glass mask for every selected image, and `--blender` pointing
to an executable. Missing/unreviewed masks appear as blockers in dry-run; actual
execution fails before creating a run. Missing labels are allowed for local
unlabeled render experiments, not ML QA. No geometry declaration or inherited
annotation is fabricated. The adapter invokes the existing v0.2.1 Blender gallery
and scene reopen checks for the transparent control and selected preset. It uses
one bounding rectangle enclosing the full mask and a cropped PNG mask in pane UV
space, not the four-pane Demo geometry. This is a single-plane approximation, not
individual pane calibration. The final RGB PNG composites the raw effect render
inside the exact reviewed full-frame mask and the decoded source outside it. This
post-render composition guarantees unchanged outside-mask RGB pixels, not optical
fidelity or preservation of object visibility. Raw scenes and renders are retained
under `previews/<image_id>/`; the registered output is the composite, not the raw
scene render. Non-identity EXIF orientation, unsupported source color modes and
nonopaque alpha are rejected rather than silently changing the pixel grid.

Run Registry stores the exact plan, source group, preset, seed, manifest/catalog
and mask/review hashes, engine version and code snapshot. Outputs and runner
reports are under `data_local/<collection>/runs/<run_id>/`. `qa_status` stays
`pending`; no automatic label transfer, split assignment, publication approval or
rights change. `PASS` refers to the execution/registration contract only. A failed
run can retain partial outputs and a prepared manifest; inspect the report/logs,
use a new run ID and never overwrite a previous run. Run single-writer, offline
except for any independent setup; the runner does not fetch data or publish it.
