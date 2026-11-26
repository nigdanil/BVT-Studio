# BVT-Studio — Research Pilot 001

Date: 2026-11-26. Status: completed exploratory synthetic pilot; not a validated real-world benchmark or peer-reviewed result.

## 1. Objective and design

Assess how controlled local optical artifacts change retail package detection and counting on paired images. Ten manually annotated synthetic freezer source scenes (0001–0010), each with two glass surfaces, produce one clean control and 20 variants: five effect families at four normalized generator intensities (25, 50, 75, 100%). Each condition contains the same 285 ground-truth boxes (class 0, `ice_cream`); 210 images, 5,985 repeated annotation instances, 1672 × 941 px. Base scene is the grouping unit (n=10), not the variant or box. No model training.

Condensation is a composite HEAVY_CONDENSATION preset; droplets, frost, reflection and dirt change individual generator channels. Levels are software parameters, not calibrated physical severity. Glass seeds 42 and 43 were used; only one seed configuration was evaluated. Clean controls are rendered scenes, not assumed pixel-identical to source photos.

## 2. Dataset and evidence verification

Local QA reports PASS for 210/210 unique PNG hashes, unchanged master/source checks and label geometry, 285 source boxes, 5,985 repeated boxes, zero failures/warnings and zero changed pixels outside the union of projected glass rectangles with a two-pixel tolerance. All 50 scene/effect RGB-change series are monotonic. The compact QA archive contains labels, metadata and previews, not full-resolution PNGs; the local pixel checks are not independently repeated here. Rectangle QA is not a precise physical mask validation.

Report audit: ZIP CRC checks passed; all 210 VLM responses were parsed and matched to their CSV records, QA and YOLO image/label hashes and GT counts. All 210 QA TXT hashes and coordinates matched YOLO JSON ground truth. Re-executing the original benchmark metric functions on 46,718 saved predictions reproduced all 21 condition and 210 scene rows. No model inference was repeated during this report audit. The ten VLM clean counts, model digest, prompt, schema and options agree with the earlier preflight.

## 3. Frozen model configurations

| Setting | YOLOE | Qwen2.5-VL |
|---|---|---|
| Model | yoloe-11s-seg.pt | qwen2.5vl:3b (3.8B reported, Q4_K_M) |
| Runtime | Ultralytics 8.4.218, torch 2.14.1+cu126, CPU | Ollama 0.40.18, local GPU |
| Task | One-class box detection | Image-level package counting |
| Prompt | `ice cream package` | See exact prompt below |
| Parameters | imgsz=960, score floor=0.001, report conf=0.05, NMS IoU=0.70, match IoU=0.50, max_det=300, rect=True, half=False, augment=False | temperature=0, seed=42, num_ctx=8192, num_predict=128, randomized order seed=42 |
| Model identifier | SHA-256 `8e439445c87338b79d9ce21dec109f4621e26df67e94d26ea1a98c1e64dce3e3` | digest `fb90415cde1ef08aa669ae74b082d49b158729b6db1ab183c941417d507e71a1` |

VLM prompt (verbatim):

> Count the individual visible ice cream retail packages in this freezer image. Count each distinct package once, including partially visible packages if identifiable. Do not count the freezer, dividers, reflections or printed pictures on packages as separate items. Return only a JSON object with one nonnegative integer field named count.

JSON schema: object with one required nonnegative integer `count`; no extra properties. No labels or expected counts are sent to the VLM. Requests are stateless at the application level. Ollama reports cached prompt tokens; cache correctness and repeated-seed variability have not been independently controlled.

YOLO-World v2 Small and YOLOE were screened on the same clean scenes. Initial threshold 0.25 failed the provisional precision/recall screen. YOLOE was selected and its report threshold lowered to 0.05 after inspecting clean predictions, before the artifact benchmark. This is exploratory selection, not independent tuning. CUDA TorchVision NMS was unavailable, so both detector preflights and the benchmark ran on CPU.

## 4. Complete condition results

AP50: single-class 101-point interpolated precision-recall AP at IoU 0.50 using predictions retained above score floor, not COCO mAP50–95. Precision, recall, F1 and TP transitions use confidence 0.05. RGB: mean absolute RGB difference relative to 255, in percent, averaged across scenes. MAE is mean absolute count error in packages per scene; YOLO count is the number of predictions above threshold (TP+FP), not the count of true positives. Lower MAE is better. Delta AP in percentage points; delta MAE in packages.

| Condition | RGB % | AP50 % | ΔAP pp | P % | R % | F1 % | Lost TP | Gained TP | YOLO count MAE | VLM MAE | ΔVLM MAE | VLM worse/better/same |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Clean | 0.0000 | 83.26 | +0.00 | 85.02 | 61.75 | 71.54 | 0 | 0 | 7.8 | 7.7 | +0.0 | 0/0/10 |
| Condensation 25% | 0.4002 | 83.05 | -0.21 | 83.57 | 62.46 | 71.49 | 3 | 5 | 7.2 | 7.5 | -0.2 | 0/1/9 |
| Condensation 50% | 0.7253 | 83.34 | +0.08 | 83.17 | 60.70 | 70.18 | 12 | 9 | 7.7 | 7.9 | +0.2 | 3/2/5 |
| Condensation 75% | 1.0111 | 83.38 | +0.12 | 83.57 | 62.46 | 71.49 | 14 | 16 | 7.2 | 7.7 | +0.0 | 2/2/6 |
| Condensation 100% | 1.2650 | 83.68 | +0.42 | 84.36 | 62.46 | 71.77 | 15 | 17 | 7.4 | 7.5 | -0.2 | 2/2/6 |
| Droplets 25% | 0.0255 | 82.97 | -0.29 | 84.88 | 61.05 | 71.02 | 3 | 1 | 8.0 | 8.3 | +0.6 | 2/1/7 |
| Droplets 50% | 0.0432 | 82.74 | -0.52 | 85.78 | 61.40 | 71.57 | 5 | 4 | 8.1 | 7.3 | -0.4 | 1/3/6 |
| Droplets 75% | 0.0571 | 82.85 | -0.41 | 85.85 | 61.75 | 71.84 | 5 | 5 | 8.0 | 8.1 | +0.4 | 2/2/6 |
| Droplets 100% | 0.0682 | 82.90 | -0.35 | 85.78 | 61.40 | 71.57 | 7 | 6 | 8.1 | 7.3 | -0.4 | 1/3/6 |
| Frost 25% | 0.5772 | 82.50 | -0.76 | 83.90 | 60.35 | 70.20 | 8 | 4 | 8.0 | 7.9 | +0.2 | 2/2/6 |
| Frost 50% | 1.0214 | 81.74 | -1.52 | 83.66 | 59.30 | 69.40 | 13 | 6 | 8.3 | 7.7 | +0.0 | 1/2/7 |
| Frost 75% | 1.4079 | 81.89 | -1.37 | 84.62 | 57.89 | 68.75 | 18 | 7 | 9.0 | 8.3 | +0.6 | 2/1/7 |
| Frost 100% | 1.7577 | 81.88 | -1.38 | 84.62 | 57.89 | 68.75 | 21 | 10 | 9.0 | 7.9 | +0.2 | 2/2/6 |
| Reflection 25% | 0.4946 | 84.42 | +1.17 | 84.72 | 64.21 | 73.05 | 6 | 13 | 6.9 | 8.1 | +0.4 | 2/2/6 |
| Reflection 50% | 0.8331 | 85.06 | +1.80 | 84.16 | 65.26 | 73.52 | 7 | 17 | 6.4 | 7.1 | -0.6 | 1/3/6 |
| Reflection 75% | 1.1162 | 85.12 | +1.87 | 84.16 | 65.26 | 73.52 | 10 | 20 | 6.6 | 7.9 | +0.2 | 1/0/9 |
| Reflection 100% | 1.3664 | 85.41 | +2.16 | 84.28 | 67.72 | 75.10 | 9 | 26 | 6.0 | 8.1 | +0.4 | 1/0/9 |
| Dirt 25% | 0.2734 | 83.07 | -0.19 | 84.04 | 62.81 | 71.89 | 3 | 6 | 7.2 | 7.7 | +0.0 | 2/2/6 |
| Dirt 50% | 0.4688 | 82.83 | -0.43 | 83.72 | 63.16 | 72.00 | 4 | 8 | 7.0 | 7.9 | +0.2 | 3/3/4 |
| Dirt 75% | 0.6301 | 82.72 | -0.53 | 82.03 | 62.46 | 70.92 | 7 | 9 | 6.8 | 7.5 | -0.2 | 0/1/9 |
| Dirt 100% | 0.7692 | 81.93 | -1.33 | 81.22 | 60.70 | 69.48 | 11 | 8 | 7.2 | 7.9 | +0.2 | 1/1/8 |

## 5. Main observations

- Clean YOLOE: AP50 83.26%, precision 85.02%, recall 61.75%, 176 TP, 31 FP, 109 FN. Reflection AP50 increases at all four levels, reaching 85.41% (+2.16 pp) at 100%; frost reaches 81.88% (-1.38 pp), dirt 81.93% (-1.33 pp). Condensation has mixed small effects; droplets produce small decreases. These are observed differences, not significance claims. Reflection may modify contrast or features, but the mechanism is untested.
- At 100% condensation, 15 previously detected ground-truth objects are lost and 17 new ones are detected, a net gain of two but 32 detection-status changes. One-to-one matching by label row makes those transitions measurable; they are not tracking identities inferred by the VLM.
- Qwen produces 210/210 valid JSON responses, 0 exact counts and 210 undercounts. Clean count 208 vs GT 285; MAE 7.7, WAPE 27.02%, bias -7.7. Across all repeated variants absolute error 1,633 / 5,985 (WAPE 27.28%), mean MAE 7.776. Count distribution: 18 (23), 20 (142), 24 (42), 30 (3). On 200 artifact pairs, 35 errors improve, 31 worsen and 134 stay the same. No monotonic severity/error response is apparent.
- On the shared counting endpoint, clean YOLOE count MAE 7.8 vs Qwen 7.7; at 100% reflection 6.0 vs 8.1; at 100% frost 9.0 vs 7.9. Detection AP is not comparable to VLM MAE. Counting errors can cancel FP and FN; this comparison is not evidence that one architecture is universally superior.
- A retrospective constant count of 29 has MAE 1.9 on these ten scenes; it exploits the narrow observed count distribution and is not an independent baseline. The VLM output concentration and high baseline error may mask sensitivity to visual corruption.

## 6. Limitations and next experiment

Only ten synthetic base scenes, one detector and one quantized VLM configuration, one prompt per task, one artifact seed configuration, no external real-image holdout and no repeated inference noise estimate across variants. The synthetic source selection and manual GT are not independently validated for all physical objects. Droplet RGB change is particularly weak. The 100% levels do not mean physical opacity or total occlusion. The clean threshold selection is post hoc on the same scene groups. No confidence intervals, multiple-comparison adjustment or inferential tests were prespecified; numerical differences must not be generalized to real stores or all YOLO/VLM architectures. The VLM model reports prefix caching; check cached vs fresh context / process and image-dependent behavior before interpreting unchanged counts as robustness.

Recommended next phase (not executed): expand annotated base scenes with distinct layouts, broader object counts and real photographs with documented rights; reserve scene-disjoint calibration and evaluation sets; add stronger severity controls, multiple artifact seeds, repeated VLM runs and a stronger VLM; use scene-level paired bootstrap intervals and preregister primary contrasts. Add matched real glass images and validate optical realism; evaluate per-object effects for detectors and shared count metrics for both model families.

## 7. Reproduction and provenance

Branch: `feature/dataset-runner-v01` (as reported by terminal logs; local uncommitted patches are not represented by a verified final commit). Python scripts: `scripts/bvt_pilot_batch_runner.py`, `scripts/bvt_pilot_dataset_qa.py`, `scripts/bvt_pilot_model_preflight.py`, `scripts/bvt_pilot_yolo_robustness.py`, `scripts/bvt_pilot_vlm_count.py`. Matrix: `configs/research/pilot_001.json`. Full dataset is local under `data_local/research_runs/pilot_001_full`. Preserve original outputs; use fresh output directories for reruns. No images, personal paths, raw logs, or model weights are added by this report patch.

Evidence archive names and SHA-256 (private/local evidence, not bundled with report):

| Archive | SHA-256 |
|---|---|
| `pilot_001_full_qa.zip` | `120ab4d0df969ded07a85c1b040f15ff7766d28f3ebc9468d6f9c978a93147e4` |
| `pilot_001_yoloe_robustness_cpu.zip` | `94e0084eef2547e1a669f8c2c735313bbdc1d7ce6a0d5ba0648eeeb6022db1e8` |
| `pilot_001_vlm_preflight.zip` | `bca075961f6189082b7434e7589ba03b703554afe6cb4b509602755260d3b75d` |
| `pilot_001_vlm_full.zip` | `7e3fe4ca2637ce14dd440214e28ce084c5252ae2f869d529822b1d08a242f8f7` |

## 8. Conclusion

BVT-Studio has demonstrated an end-to-end paired artifact generation and evaluation workflow for this synthetic pilot. Optical effects change detector outcomes in different directions; a universal degradation hypothesis is not supported. The tested small VLM undercounts and exhibits limited count diversity, with small mixed paired differences. These are exploratory results and a basis for a larger controlled study, not a confirmed real-world accuracy or robustness claim.
