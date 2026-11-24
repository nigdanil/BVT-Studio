#!/usr/bin/env python3
"""Reclassify a complete saved Commons audit offline; produce review candidates only."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

if __package__:
    from . import audit_dataset_provenance as audit
else:
    import audit_dataset_provenance as audit


def digest(data):
    return sha256(data).hexdigest()


def review(root, audit_id, review_id):
    root = Path(root).resolve()
    for value in (audit_id, review_id):
        audit.require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', value), 'Invalid ID')
    base = 'data_local/real_wikimedia/attribution/'
    folder = audit.safe_path(root, base + audit_id)
    output = audit.safe_path(root, base + review_id)
    audit.require(not output.exists(), 'Review ID already exists')
    data = audit.safe_path(root, base + audit_id + '/audit_report.json').read_bytes()
    report = json.loads(data)
    groups = audit.read_manifests(root)
    real, real_bytes = groups['real_wikimedia']
    rows = report['records']
    audit.require(report['schema'] == 'bvt.commons-evidence.v1' and report['audit_id'] == audit_id
                  and report['stopped'] is False and report['requested'] == 100
                  and report['ready_for_publication'] == 0, 'Expected complete audit')
    audit.require(report['real_manifest_sha256'] == digest(real_bytes)
                  and report['synthetic_manifest_sha256'] == digest(groups['synthetic_chatgpt'][1]),
                  'Audit manifest SHA mismatch')
    audit.require(len(real) == len(rows) == 100 and
                  [r['image_id'] for r in rows] == [r['image_id'] for r in real], 'Audit ID mismatch')
    for field, summary in [('metadata_status', 'metadata_counts'), ('binary_status', 'binary_counts')]:
        audit.require(dict(Counter(r[field] for r in rows)) == report[summary], 'Audit counts mismatch')
    candidates = []
    for record, old in zip(real, rows):
        image_id = record['image_id']
        def need(condition, message):
            audit.require(condition, f'{image_id}: {message}')
        need(old['metadata_status'] in ('candidate_matches_registry', 'manual_review_required')
             and old['publication_status'] == 'pending_manual_review', 'Unexpected audit status')
        local = audit.verified_bytes(audit.safe_path(root, record['local_cache_path']), record)
        need(old['local_sha256'] == record['sha256'] == digest(local), 'Local SHA mismatch')
        need(old['source_page_url'] == record['source_page_url'] and
             old['registry_author'] == record['author'] and old['registry_license_id'] == record['license_id'],
             'Registry snapshot mismatch')
        name = image_id + '.api.json'
        need(old['evidence_file'] == name, 'Evidence filename mismatch')
        raw = audit.safe_path(root, base + audit_id + '/' + name).read_bytes()
        need(digest(raw) == old['evidence_sha256'], 'Evidence SHA mismatch')
        page, info = audit.parse_page(json.loads(raw), record)
        revision = (page.get('revisions') or [{}])[0]
        need(type(revision.get('revid')) is int and page.get('pageid') == old['page_id']
             and revision == old['page_revision'], 'Page revision mismatch')
        need(info['url'] == old['original_url'] and info.get('sha1') == old['original_sha1']
             and [info.get('width'), info.get('height')] == old['original_size'], 'Original evidence mismatch')
        if old['binary_status'] == 'thumbnail_sha256_match':
            url = audit.official(info['thumburl'], audit.THUMBNAIL_HOSTS, stage='thumbnail_url')
            need(url == old['thumbnail_url'] and old['thumbnail_sha256'] == record['sha256']
                 and [info.get('thumbwidth'), info.get('thumbheight')] == old['thumbnail_size']
                 == [record['width'], record['height']], 'Thumbnail evidence mismatch')
        elif old['binary_status'] == 'original_sha1_match':
            need(audit.original_matches(local, info.get('sha1')), 'Original SHA mismatch')
        else:
            need(False, 'Binary origin unresolved')
        candidate = audit.metadata_candidate(info, record)
        need(candidate['candidate_author'] == old['candidate_author'] and
             candidate['candidate_license_short_name'] == old['candidate_license_short_name'] and
             candidate['candidate_license_url'] == audit.normalized_license(old['candidate_license_url']),
             'Candidate metadata mismatch')
        for key, field in [('Credit', 'candidate_credit'), ('Attribution', 'candidate_attribution'),
                           ('Restrictions', 'candidate_restrictions')]:
            need(audit.plain(audit.meta(info, key)) == old[field], 'Credit/restrictions mismatch')
        row = dict(old)
        row['previous_metadata_status'] = old['metadata_status']
        row['previous_candidate_license_id'] = old['candidate_license_id']
        row['previous_candidate_license_url'] = old['candidate_license_url']
        row.update(candidate)
        row['publication_status'] = 'pending_manual_review'
        candidates.append(row)
    result = dict(schema='bvt.commons-review-candidates.v1', review_id=review_id,
                  source_audit_id=audit_id, source_audit_sha256=digest(data),
                  real_manifest_sha256=report['real_manifest_sha256'],
                  synthetic_manifest_sha256=report['synthetic_manifest_sha256'],
                  metadata_counts=dict(Counter(r['metadata_status'] for r in candidates)),
                  license_counts=dict(Counter(r['candidate_license_id'] or 'unknown' for r in candidates)),
                  ready_for_publication=0, records=candidates)
    # No files are written until every input record and raw evidence file is checked.
    output.mkdir(exist_ok=False)
    audit.save_json(output / 'review_candidates.json', result)
    lines = ['# Commons attribution candidates — NOT publication clearance', '',
             f'Source audit: `{audit_id}`; SHA-256: `{digest(data)}`.', '',
             'API-reported names and licenses are candidates, not verified rights decisions.',
             'The local images matched the recorded remote hashes during the source audit;',
             'this offline review does not download thumbnails again.',
             'All records remain pending manual review for publication, including third-party rights.', '',
             '| Image ID | API author | API license | Source / revision | Metadata comparison |',
             '|---|---|---|---|---|']
    def cell(value):
        return str(value or 'unknown').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')
    for r in candidates:
        revision = r['page_revision']['revid']
        source = f'https://commons.wikimedia.org/w/index.php?oldid={revision}'
        license_text = cell(r['candidate_license_id'])
        if r['candidate_license_url']:
            license_text = f'[{license_text}]({r["candidate_license_url"]})'
        lines.append(f'| {r["image_id"]} | {cell(r["candidate_author"])} | {license_text} | '
                     f'[revision {revision}]({source}) | {cell(", ".join(r["review_reasons"]) or "candidate_matches_registry")} |')
    with (output / 'ATTRIBUTION_CANDIDATES.md').open('x', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print('METADATA_COUNTS=' + json.dumps(result['metadata_counts'], sort_keys=True))
    print('LICENSE_COUNTS=' + json.dumps(result['license_counts'], sort_keys=True))
    print('RAW_EVIDENCE_VERIFIED=100')
    print('READY_FOR_PUBLICATION=0')
    print('OFFLINE_PROVENANCE_REVIEW=PASS')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-id', required=True)
    parser.add_argument('--review-id', required=True)
    args = parser.parse_args()
    review(audit.ROOT, args.audit_id, args.review_id)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
