# ChatGPT synthetic collection — current policy (2026-11-24)

100 synthetic images. Generated using ChatGPT (OpenAI) under the direction of the BVT-Studio author. No blanket image license is assigned. Code licensing does not cover these images automatically. Account terms, third-party rights, packaging and trademarks require review before publication; no publication approval, ground truth or verified annotation is implied.

---

## Historical source notice (before stage 14D)

# ChatGPT-Generated Freezer Images — Provenance, Use and Distribution

> **AI-generated content notice:** The BVT-Studio project author reports a collection of **100 synthetic retail freezer images created with ChatGPT (OpenAI)** under human direction. These images are AI-generated illustrations, **not photographs of real retail stores**.

| Item | Description |
|---|---|
| Project | [BVT-Studio](https://github.com/nigdanil/BVT-Studio) |
| Asset collection | Synthetic supermarket chest-freezer scenes |
| Reported quantity | **100 images** — author-reported, not yet file-by-file audited |
| Origin | **ChatGPT (OpenAI), image-generation functionality** |
| Human contribution | Scene requirements, reference selection, prompting, review and curation by the project author |
| Primary application | Controlled 2.5D image augmentation, glass-surface effects and computer-vision research |
| Source-code license | BVT-Studio source code: **GNU GPLv3** (separate from image-asset permissions) |
| Asset-license status | **No separate public reuse license is granted by this document**; see Section 5 |
| Document version | 1.0 — 2026-11-24 |

## 1. Origin and scope

The project author states that **100 images were generated using ChatGPT (OpenAI)** in an interactive workflow to support the BVT-Studio project. The images depict open-top supermarket freezers containing fictional or stylized packaged ice creams, frozen desserts and related retail products.

They were generated under the author's creative direction, which included variation in camera angle, basket arrangement, product density, packaging shape, fictional manufacturer names and visual design. They are **synthetic source images**, not scans, photographs collected from actual shops or independently measured retail scenes.

**Important verification boundary:** The reported count of 100 is a provenance statement supplied by the project author. This Markdown document does **not** establish that exactly 100 distinct original files have been deposited in the repository, or that their hashes, prompts, timestamps, models, identities or rights have been individually verified. Such verification requires an asset inventory (Section 8).

This notice applies **only** to the ChatGPT-generated freezer-image collection. It does not relicense or otherwise cover third-party photographs, Wikimedia Commons assets, reference images, source code, trademarks or separately produced media.

## 2. Image characteristics

The collection is intended to vary across multiple scene dimensions:

- **Camera framing:** near-vertical top-down views and oblique views from the left, right and front at different elevations.
- **Planograms:** ordered stocking, dense and sparse stocking, partially obscured products, diagonally placed packs and irregular assortments.
- **Packaging:** wrapped ice-cream bars, cone wrappers, stick ice pops, ice-cream sandwiches, multipack cartons, round tubs, paper cups, dessert cups and alternative package geometries.
- **Appearance:** different colors, typography, fictional labels, flavors, illustrations and packaging designs.
- **Freezer geometry:** white/gray chest freezers, four-section wire baskets, rails, internal walls, frost around freezer rims and retail floor surroundings.

Not every characteristic is present in every image. Packaging labels, apparent manufacturer names, pack sizes, temperatures and product geometry are generated visual details and may be erroneous or inconsistent. A fictional-sounding label may accidentally resemble a real trademark.

## 3. Intended BVT-Studio workflows

The images are intended as input for **controlled visual-artifact experiments** using BVT-Studio, including:

- Glass-pane masks and independent glass overlays in a 2.5D scene.
- Condensation, water droplets, microdroplets and running-water effects.
- Frost, fogging, dirt, reflections, glare and other optical obstructions.
- Reproducible artifact parameters, random seeds and before/after comparisons.
- Manually created and verified YOLO Detect bounding-box annotations.
- Quality checks, object-visibility analysis and computer-vision evaluation or benchmarking within applicable terms and policies.

**These images do not come with reliable ground-truth annotations.** AI-generated product pictures, visible text and apparent object boundaries are not a substitute for verified SKU identities, bounding boxes, masks or labels.

Research outcomes from synthetic imagery alone must not be represented as proven real-world detection performance. Where a claim concerns real-store performance, use independently sourced, suitably licensed, held-out real-world images to test it.

**Dataset splitting:** Keep an original image and all artifact-augmented variants of that original in the **same** train/validation/test split. Do not place variants of the same source scene in both training and evaluation sets.

## 4. Use, modification, publication and commercial applications

OpenAI's applicable terms generally provide that, **as between the user and OpenAI and to the extent permitted by law**, the user owns the Output and OpenAI assigns any rights it may have in that Output. OpenAI also states that ChatGPT output may be used for commercial purposes, subject to its terms and policies. This does **not** guarantee exclusive copyright protection, that a generated image is unique or that it does not implicate someone else's rights.

Subject to the checks and conditions below, the project author may generally:

| Activity | Position |
|---|---|
| Use images internally in BVT-Studio | Generally permitted |
| Add glass effects, artifact overlays, crops and other transformations | Generally permitted |
| Create reviewed YOLO annotations and manifests | Generally permitted |
| Publish selected images, originals and modifications on GitHub | Generally permitted, with rights review and clear AI disclosure |
| Publish research findings, metrics and selected illustrations | Generally permitted, with appropriate disclosure and scientific qualification |
| Use images in demos, commercial software, client work or marketing | Generally permitted, subject to applicable law, third-party rights and OpenAI terms |
| Sell or license the images, where rights exist | Potentially permitted; confirm scope of rights, any input-image restrictions and terms before doing so |
| Use OpenAI output to train or develop a model intended to substitute for or compete with OpenAI models/services | **Restricted by OpenAI terms/policies; do not assume permission** |

**Model-training clarification (policy in effect as of 2026-11-24):** OpenAI's Usage Policies, effective **2026-11-20**, restrict using OpenAI outputs to create, prepare, select or supply training materials or signals for models intended as alternatives or substitutes for OpenAI models or services. The policies separately recognize research, software development, model evaluation and benchmarking **within those boundaries**. BVT-Studio's ordinary visual-artifact research is not automatically forbidden, but each downstream model-training use must be checked against this distinction. A commercial-use permission does not override a separate use restriction.

**Publication procedure:** Before uploading any generated image publicly, review it for accidental real logos or protected content, sensitive data, misleading realism, and any restrictions arising from reference/input materials. Identify the image visibly in the accompanying README, caption or dataset description as **AI-generated**; do not suggest it is a real shop photograph or that OpenAI endorses BVT-Studio.

## 5. Repository licensing and third-party reuse

### 5.1 Source code is separate from media assets

BVT-Studio's `LICENSE` file licenses **the software source code** under **GNU GPLv3**. Merely placing PNG files in the same repository does **not automatically** make those files GPLv3, CC0, CC BY, CC BY-SA or any other separately named open-content license.

### 5.2 Status of this image collection

**This document records provenance and the author's intended use; it is not itself a grant of a blanket copyright license to third parties.** The project author has **not specified a separate public reuse license for these 100 images in this document**.

A GitHub visitor can view publicly published assets under the platform's applicable terms and any rights conferred by law, but **public availability must not be described as an express CC0, Creative Commons or GPL asset license**. Whether a particular AI-generated image qualifies for copyright protection, and which rights can be granted, may vary with jurisdiction and human creative contributions.

If the author wants others to copy, modify, redistribute or use the assets commercially on defined terms, the author should **explicitly select and publish a separate asset policy/license** after an appropriate rights review. Do not silently apply a license chosen by an assistant or infer it from BVT-Studio's source-code license.

Suggested future structure (not a statement that the files already exist):

```text
BVT-Studio/
  LICENSE                               # Existing software license (GPLv3)
  docs/
    CHATGPT_GENERATED_IMAGES.md          # This provenance and usage notice
  assets/
    synthetic/
      chatgpt_freezers/
        README.md                        # Link to this notice and asset status
        manifest.csv                     # Validated file-by-file inventory
        originals/                       # Source PNGs, if publication is approved
        augmented/                       # Outputs, optionally kept outside Git
```

Do not add license headers to individual images implying that a specific Creative Commons license has been adopted unless the project author has actually made that licensing decision.

### 5.3 Other datasets are not covered

Any collection of real third-party retail photographs (including Wikimedia Commons images) must retain **per-image attribution, author, source URL, exact license and version, modification notice and any ShareAlike requirements**. Third-party material must never be described as generated with ChatGPT merely because it is processed by BVT-Studio. Nor does ChatGPT generation remove rights attached to reference/input images.

## 6. Risks, limitations and review requirements

| Risk or limitation | Recommended action |
|---|---|
| Accidental similarity to real brands, logos or protected designs | Review visible marks; replace questionable imagery when needed |
| Third-party reference/input images | Check permissions for those inputs and whether derivative publication is allowed |
| Nonexclusive or potentially unprotected AI output | Avoid claims of uniqueness, exclusive copyright or guaranteed ability to sublicense |
| Incorrect package text, geometry and object counts | Human review; do not infer ground truth from appearance |
| No verified bounding boxes, masks or SKU IDs | Create and validate annotations separately |
| Dataset leakage among augmented variants | Group splits by original source image |
| Synthetic-to-real domain gap | Validate on separate real-world samples before claiming field performance |
| GitHub publication and future downstream redistribution | Publish explicit provenance, applicable rights information and any adopted asset policy |
| Model training with OpenAI outputs | Recheck current OpenAI policies and whether a trained model competes with/substitutes OpenAI offerings |
| Changing legal/policy conditions | Review applicable rules before new commercial releases or relicensing |

No certification is implied concerning trademark clearance, authorship, copyright registration, fair use, originality, freedom from third-party claims or the scientific accuracy of these images.

## 7. Mandatory public attribution / disclosure

Use a short, prominent statement alongside any publicly released image gallery, dataset README or research figure. For example:

> **AI-generated image dataset.** This set comprises 100 synthetic retail freezer images reported by the BVT-Studio project author as generated with ChatGPT (OpenAI), with human-directed prompting, selection and curation. The images are not photographs of real stores. They are used as source scenes for controlled visual-artifact experiments.

For individual figures:

> Synthetic freezer scene generated with ChatGPT (OpenAI); artifact effects and annotation review performed in BVT-Studio. Not a real retail photograph.

These are **provenance statements**, not a claim of sponsorship, certification or endorsement by OpenAI. The user/project author remains responsible for reviewing and publishing the materials.

## 8. Dataset manifest and verification

A complete release should have **one reviewed record for each actual image file**, with a stable name and verifiable hash. Recommended fields:

| Field | Meaning |
|---|---|
| `image_id` | Stable unique identifier (e.g., `freezer_0001`) |
| `file_path` | Repository-relative path of the original image |
| `origin` | `chatgpt_generated` |
| `generator` | `ChatGPT (OpenAI)` |
| `source_group_id` | Original scene shared by its augmented variants |
| `sha256` | SHA-256 checksum of the exact released file |
| `width_px`, `height_px` | Actual pixel dimensions |
| `viewpoint` | Verified view category (top-down/oblique/etc.) |
| `packaging_types` | Reviewed categories visible in the image |
| `created_at` | Verified creation date, when available; otherwise leave blank |
| `generation_reference` | Generation ID / prompt reference when retained and publishable |
| `annotation_status` | `unlabeled`, `draft` or `verified` |
| `reference_inputs_reviewed` | `yes`, `no` or `not_applicable` |
| `rights_review_status` | `pending`, `reviewed` or `needs_attention` |
| `asset_license` | Exact adopted license if any, otherwise `not_specified` |
| `notes` | Visual anomalies and any corrective action |

Do **not** fabricate missing prompts, model names, timestamps, labels or legal authorizations. If generation records were not retained, state this explicitly rather than reconstructing them as facts.

### Publication checklist

- [ ] Confirm exactly 100 intended source images exist in the release location.
- [ ] Confirm the 100 files are distinct; record SHA-256 hashes and inspect visually similar images.
- [ ] Check that each file is AI-generated rather than a third-party retail photograph.
- [ ] Inspect all images for trademarks, recognizable protected artwork and problematic reference-derived content.
- [ ] Record image dimensions, camera viewpoint and annotation status without guessing.
- [ ] Record source/augmented relationships and ensure leakage-safe splits.
- [ ] Add prominent AI-generation disclosure to repository and dataset descriptions.
- [ ] Keep GPLv3 code licensing distinct from any separately adopted media-license terms.
- [ ] Confirm whether downstream third-party reuse is intended; publish an explicit asset policy if so.
- [ ] Review current OpenAI terms and intended model-training use before public or commercial release.

**Status at document creation:** This checklist is a release gate, **not a claim that any of these checks have already passed**.

## 9. Primary references (checked 2026-11-24)

These URLs are provided for review. The applicable agreement and policy versions depend on user location, account/service and time:

1. [OpenAI — Europe Terms of Use](https://openai.com/policies/eu-terms-of-use/) (updated 2026-01-16).
2. [OpenAI — Terms of Use (outside the EEA, UK and Switzerland)](https://openai.com/policies/terms-of-use/) (2026 edition).
3. [OpenAI — Usage Policies](https://openai.com/policies/usage-policies/) (relevant training restriction effective 2026-11-20).
4. [OpenAI — Sharing & Publication Policy](https://openai.com/policies/sharing-publication-policy/).
5. [OpenAI Help — Commercial use of ChatGPT output](https://help.openai.com/en/articles/6783457-what-is-chatgpt).
6. [BVT-Studio — Source code license](https://github.com/nigdanil/BVT-Studio/blob/main/LICENSE).

## 10. Maintenance and disclaimer

Update this document when the image set changes, a manifest is verified, a separate asset license is adopted or relevant usage terms change. Where there is a conflict, binding law, applicable third-party rights and applicable OpenAI terms prevail over this project document.

This is **a technical provenance and project-usage notice**, not a warranty of ownership or a formal legal opinion. It does not grant rights the project author does not possess and does not replace legal review for high-value commercial distribution.

---

*Prepared for BVT-Studio on 2026-11-24. Generation count and history: reported by the project author; full asset inventory: pending verification.*
