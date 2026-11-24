# Dataset provenance and license audit — evidence collection v1

This is the first part of stage 14. It collects evidence, not legal clearance.
The initial 100 real and 100 synthetic manifest records remain unchanged.

## Commons evidence

From the repository root, with the existing manifest dependencies installed:

```sh
python scripts/prepare_research_datasets.py --check
python scripts/audit_dataset_provenance.py --audit-id commons-pilot-099 --image-id wikimedia_000099
python scripts/audit_dataset_provenance.py --audit-id commons-full-001
```

Use a new audit ID for every attempt. Run the full audit only after a pilot
returns successfully with usable evidence. URL-policy violations and unexpected
redirects stop the remaining requests; diagnostic messages identify the request,
response, original or thumbnail URL stage. Do not relax the HTTPS/host policy
without inspecting the actual response. Raw API evidence, if already written,
is linked from error records too; its presence does not imply validation.
The script checks the local source against
its manifest before requesting public Commons metadata. The sequential Action
API requests request the current file page, revision, original hash, license
metadata and thumbnail at the local width. The API may return a different size.
Only exact HTTPS authorities are accepted: commons.wikimedia.org for API requests,
upload.wikimedia.org for original metadata URLs, and upload.wikimedia.org or
thumb.wikimedia.org for thumbnail downloads. Requests and responses must match
the selected host exactly; no redirects, credentials, explicit ports, fragments,
private Drive URLs or uploads of image bytes. Existing query parameters are preserved. Requests are paced;
403, 429, 503 or maxlag/rate-limit errors stop the remaining requests. Respect
server limits and Retry-After; do not retry repeatedly. The repository URL is
the public contact in the User-Agent. Network errors are reported, not cleared.

Evidence is written under the ignored directory
`data_local/real_wikimedia/attribution/<audit-id>/` as raw API JSON and
`audit_report.json`. Keep the raw evidence alongside the report. The report is
bound to both manifest SHA-256 values and records candidate authors, license
URLs, original file metadata, page revision and binary comparison results.

- `original_sha1_match`: local bytes match the original file hash reported by API.
- `thumbnail_sha256_match`: exact SHA-256 match with the fetched thumbnail.
- `decoded_rgb_match_review`: decoded RGB pixels match, but bytes differ; review.
- `unresolved_thumbnail_difference`: no exact match; check actual thumbnail size,
  original revision, preprocessing and source manually. Not proof of a wrong source.
- `unresolved_no_thumbnail`, `unresolved`, `not_checked`: no binary confirmation.
- `candidate_matches_registry`: supported license URL and short name agree with
  the registry and an artist is present; if a known author exists it agrees too.
  This is candidate metadata, not individual legal approval.
- `manual_review_required`, `error`, `not_checked`: no automatic promotion.

A completed request set is not a completed rights audit. The publication-ready
count stays zero. Source files, Excel, JSONL, and existing provenance documents
are not rewritten by the collector. Inspect the original Commons pages and any
multiple-license or attribution templates before accepting candidates. Preserve
copyright notices, credit and source links, identify any modifications, check
trademarks and other third-party rights, and record explicit decisions. Update
Excel, provenance documents, attribution and manifests together in a later
reviewed migration, with backups and deterministic regeneration. Do not use
output hashes from a prior manifest version as if they were the new version.

## Rights policy

CC BY generally allows sharing and adaptation, including commercial use, with
required attribution and license conditions. CC BY-SA additionally requires
applicable ShareAlike terms for distributed adaptations; verify the exact version.
CC0 is a public-domain dedication with limitations; it does not eliminate all
third-party rights. A Commons page is not a warranty of all rights. Review
logos, packaging, persons, and jurisdiction-specific restrictions separately.

Synthetic images are described as generated using ChatGPT (OpenAI) under the
direction of the BVT-Studio author. Do not infer a public license, copyright
status, or third-party rights clearance from output ownership terms or project
code licensing. Confirm the applicable account terms and intended uses before
public distribution. The demo asset requires its own redistribution decision.

References:
- https://www.mediawiki.org/wiki/API:Imageinfo
- https://commons.wikimedia.org/wiki/Commons:Machine-readable_data
- https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
- https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/licenses
- https://www.mediawiki.org/wiki/API:Etiquette
- https://openai.com/policies/terms-of-use/

## Offline candidate review (stage 14C)

Localized Creative Commons deed URLs such as `/publicdomain/zero/1.0/deed.en/`
are normalized only to supported canonical licenses. `CC0` and `CC0 1.0`
are recognized as the same declaration; URL/name conflicts and author or
registry differences remain review flags.

For a complete saved 100-image audit, without any additional network requests:

```sh
python scripts/review_dataset_provenance.py --audit-id commons-full-002 --review-id commons-review-001
```

The review checks both manifest hashes, all local real image hashes/dimensions,
record IDs, saved API evidence hashes, page/revision, recorded binary evidence,
license and author metadata. It writes only new `review_candidates.json` and
`ATTRIBUTION_CANDIDATES.md` under the ignored review directory. The original audit
is immutable. The draft is not the final attribution document or a grant of
rights. Review the exact revision and third-party rights before changing the
Excel, provenance notes or published manifests. Offline checks validate the
recorded thumbnail hash; they do not independently download a fresh thumbnail.

## Stage 14D — staged metadata migration

The one-time migration is bound to the accepted stage 14C report hashes and
baseline registry/manifest hashes. Run from the repository root:

```sh
python scripts/prepare_provenance_update.py --source-copy /path/to/BVT-Studio-Datasets
```

It rechecks saved API evidence and local/Drive image hashes, and generates an
isolated `data_local/real_wikimedia/attribution/commons-update-001/` bundle
with `before/`, `after/` and `migration.json`. The working metadata is not
replaced. Inspect the new workbook and manifest differences before promotion.
The original workbook is retained in `before/`; the new workbook adds an
API evidence sheet and current summary. Historical source notices are kept
verbatim under an explicit historical heading. Record 004 uses the API's
CC BY-SA 4.0 declaration instead of CC0; record 100 uses the API name Andy Li
instead of Andy Li (Onthewings). Both retain a manual review flag and prior
values. The other 98 are `api_evidence_recorded`, not legal clearance.
All rights-review decisions remain pending. No images or annotation state
change. The updated builder can regenerate manifests from the revised
workbook; it still refuses to overwrite existing differing JSONL files.
The evidence sheet binds thumbnail SHA-256 and page revision to each record.
Only after explicit review should the bundle be promoted and synchronized.

After inspecting the workbook, attribution and ledger, explicitly promote with
`--promote <reviewed migration SHA256>` in addition to `--source-copy`.
Promotion verifies all original and staged files and regenerates both manifests
before replacing the seven metadata files. The before bundle is retained.
Each file is replaced atomically; the entire bundle is not a filesystem
transaction. Do not use concurrent writers; after abrupt interruption inspect
all ledger hashes and restore the before copies if needed. Drive copies are not
updated by this command.
