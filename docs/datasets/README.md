# Research collections — provenance and storage

Inventory baseline: 2026-11-24, Dataset Infrastructure stages 2–7.

| Collection | Files | Local source directory |
| --- | ---: | --- |
| Synthetic ChatGPT | 100 PNG | `data_local/synthetic_chatgpt/clean/images/` |
| Real Wikimedia | 100 JPEG | `data_local/real_wikimedia/clean/images/` |

The local inventory contains 200 distinct SHA-256 digests and 353,700,357 bytes. All files were decoded and matched to the previously downloaded Google Drive copy. This is a binary integrity check, not independent verification of original provenance or licensing. Near-duplicates have not been assessed.

## Collection documentation

- [ChatGPT-generated images](CHATGPT_GENERATED_IMAGES.md): AI provenance and usage limitations.
- [Third-party retail images](THIRD_PARTY_RETAIL_IMAGES.md): source URLs, recorded licenses and attribution requirements.
- [Current Excel registry](BVT_Studio_Registry_100_Verified.xlsx): 100 real-image records, including the replacement of record 99. The filename is retained; `Verified` does not imply that every license is verified.

The two provenance notices describe the inventory at the time of their preparation. The later local file audit established the counts and hashes above; it did not establish generation history, source rights or ground truth.

## Storage policy

GitHub holds code, tests, configuration, small demo assets (subject to redistribution approval), documentation and dataset metadata. Google Drive holds the two full source collections and synchronized copies of the collection documents. Local research inputs, labels, masks and run outputs belong in ignored `data_local/`. Private Drive links and credentials must not be committed. See [dataset setup](../../datasets/README.md).

## Rights and research status

The source-code GPLv3 license does not automatically apply to images. The synthetic collection is AI-generated and has no blanket public reuse license granted by its provenance notice. Review applicable terms and third-party rights before distribution or downstream use. The stage 14 API audit established exact thumbnail SHA-256 matches for all 100 JPEGs and obtained 100 author declarations and license candidates. Two records remain flagged for metadata discrepancies; all rights-review decisions remain pending. See [ATTRIBUTION.md](ATTRIBUTION.md) and the current Excel API sheet. Preserve attribution, source and license links, modification notices and applicable ShareAlike requirements; do not publish unreviewed assets.

Research YOLO labels, individual glass masks and dataset splits are not yet prepared. Keep each source and its augmented variants in the same split. No real-world detection improvement or full-dataset benchmark result is claimed.

## Demo versus Research

The demo uses `chatgpt_000011.png`, four sample masks and twelve sample maps. It has no verified YOLO labels. An isolated local Windows build with Blender 5.2.3 passed 281 unit tests, 13 scene renders and reopens, seven zero-water controls and four archive checks on 2026-11-24. This is a local development snapshot result, not a new published release or an ML accuracy result.
