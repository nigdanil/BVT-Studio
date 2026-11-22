# BVT YOLO Benchmark Engine v0.1

Step 6 measures **exploratory detection robustness on inherited candidate labels**. It does not train a model, create a validation split, approve annotations or claim independent generalization. The 84 images are derived from one reference source; bbox geometry is inherited, not independently measured after refraction. Some manually annotated rectangles may cover collections of products; confirm annotation semantics and completeness before interpreting model results. The affected group is fixed by Step 5 ROI membership (7 boxes); the remaining 21 are an internal control, not independent observations. Contextual detector changes can occur even outside the modified ROI.

## Inputs / dependencies

- Complete Step 5 folder `qa_renders/yolo_matrix_full_v04` (including **original PNGs** in `images/pilot`, not the QA ZIP's resized overlays). All 84 records, live geometry report, UID/class/coordinate identity, PNG/TXT hashes and decoded clean RGB are checked even in `--pilot` mode. Exactly one class `0: ice_cream` and 28 boxes are supported by v0.1.
- Existing Python environment with NumPy and Pillow for smoke/tests. No ML dependency is imported by smoke or unit tests.
- Real inference: locally installed Ultralytics and PyTorch, plus a **trusted, local detection `.pt`** trained externally with compatible annotation semantics. `--model-class` is the exact class name in model metadata; `ice_cream` is default, `product` is an explicit alternative ONLY if semantically appropriate. One selected model class is mapped to dataset class 0; other classes are filtered before scoring. No automatic model downloads. Official COCO checkpoints do not provide an ice_cream class. Do not train/evaluate on variants of this same source and claim independent performance. Record the training sources and model selection outside this engine.

## CLI

From the repository root, use new output folders under `qa_renders`:

```bash
python scripts/bvt_yolo_benchmark.py run --dataset-dir qa_renders/yolo_matrix_full_v04 --output-dir qa_renders/yolo_benchmark_smoke_v01 --smoke
python scripts/bvt_yolo_benchmark.py pack --input-dir qa_renders/yolo_benchmark_smoke_v01 --archive qa_renders/BVT_YOLO_Benchmark_Smoke_v01.zip
```

`--smoke` uses deliberately fabricated predictions from GT, with one known missing target per non-global-control image. It measures only software correctness; no model is invoked. `PASS_SMOKE` is not an inference result. In the default smoke, the global clear has 28 matches; each noncontrol has 27 (6/7 affected and 21/21 control). All 66 experimental images pooled: 1848 GT, 1782 TP, 66 FN, zero FP. The control recall drop is 0 pp; the affected recall drop vs global clear is -100/7 pp. All these values are synthetic expectations.

Real run, once a compatible model exists (replace path with the actual checkpoint; CPU default, GPU `--device 0` only if CUDA-enabled PyTorch is available):

```bash
python scripts/bvt_yolo_benchmark.py run --dataset-dir qa_renders/yolo_matrix_full_v04 --output-dir qa_renders/yolo_benchmark_model_pilot_v01 --weights /d/models/best.pt --model-class ice_cream --device cpu --pilot
```

`--pilot` selects 9 jobs and all necessary baselines (three materials x three effects), while the input audit remains 84/84. Omit `--pilot` and use a fresh output folder for full model inference. Both runs use fixed default `imgsz=960`, score floor .001, NMS IoU .7, max-det 300, operating confidence .25, matching IoU .50. Use identical values across comparisons. Set `--score-floor`, `--conf`, `--nms-iou`, `--imgsz`, `--max-det` explicitly when needed. The maximum-detections limit is flagged when reached. Output includes model SHA256, versions, class mapping, input hashes, parameters and per-image timing. The selected model's class set is filtered before matching; this is single-target detection, not multiclass evaluation. A class mismatch blocks execution. A `.pt` can contain executable pickle: trust its origin.

## Metrics and pairing

- All predicted rectangles are normalized xyxy, validated, retained after detector NMS and score floor. Confidence-ordered greedy one-to-one matching uses the highest IoU among unused same-class GT within each image, stable ties. At fixed `conf` and IoU .50: TP/FP/FN, precision, recall, F1 and mean IoU of matched boxes. Undefined denominators are null, not zero. Per-image and pooled experimental metrics. AP50 and mean AP for IoU .50:.05:.95 use 101-point interpolated precision-recall, all retained scores (not fixed operating threshold). This is a documented single-class AP implementation, not official COCOeval (no size/crowd/ignore rules) or Ultralytics val parity claim; NMS, score floor and max-det limit attainable AP. Stable ties may depend on image ordering.
- Three paired baselines for each variant: `global_clear` (clear + 00_clean), `material_only` (same material + 00_clean), `same_artifact_clear` (clear + same effect). Match full image first, then group GT by region and pair **by UID**. Report matched-both confidence delta and separately score delta treating missing detection as zero; the latter is a composite, not raw confidence. Lost = detected baseline but not variant; gained = opposite; drop = lost / baseline detected (null if none); recall delta percentage points. Region-level **recall** is meaningful, FP assignment to regions is not assumed. Do not derive precision/AP for the regions by ignoring FPs elsewhere. Material-only and same-artifact comparisons are descriptive contrasts, not physical causal isolation.
- Exclude all 18 QA-only images from pooled experimental groups, but keep them as controls/stress results in outputs. All 66 experimental scenes remain REVIEW; metrics against candidate labels can conflate real detection failure and changed visibility/label semantics. No confidence intervals/p-values: one source and one generation seed.

## Outputs and acceptance

`report.json`, `scenes.csv` (full-frame metrics plus regional recall), `groups.csv` (pooled single-class AP by material/effect), `paired_objects.csv` (UID-level, 3 comparisons), `paired_summary.csv` (per scene/region/comparison), `paired_groups.csv` (experimental aggregate per region/comparison), `predictions/*.json` (normalized boxes and operating matches), `previews/*.jpg` (GT orange/green, predictions blue), `index.html` (heatmaps and gallery). QA-only cells are identified by hover and scene role. `pack` requires a completed run, produces SHA256 manifest and ZIP CRC check, does not include model checkpoints or original PNGs. Input data is read-only. On errors run in a new output folder after diagnosis; incomplete output is not packable. `PASS_EXPLORATORY_INFERENCE` indicates technical completion only, not model quality. Review the 462 flagged experimental boxes and manually verify reference annotation granularity before interpreting/training. Later independent multi-source splits and real photos are required for scientific conclusions.
