#!/usr/bin/env python3
"""Collect Commons evidence, never clear rights or change source metadata."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha1, sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from PIL import Image
if __package__:
    from .prepare_research_datasets import ROOT, read_manifests, safe_path, verified_bytes, require
    from .build_dataset_manifests import LICENSES, commons_title
else:
    from prepare_research_datasets import ROOT, read_manifests, safe_path, verified_bytes, require
    from build_dataset_manifests import LICENSES, commons_title

API = 'https://commons.wikimedia.org/w/api.php'
THUMBNAIL_HOSTS = ('upload.wikimedia.org', 'thumb.wikimedia.org')
HOSTS = {'commons.wikimedia.org', *THUMBNAIL_HOSTS}
UA = 'BVT-Studio-Provenance/1.0 (https://github.com/nigdanil/BVT-Studio)'


def now():
    return datetime.now(timezone.utc).isoformat()


class URLPolicyError(ValueError):
    """Unexpected URL or redirect: stop the batch and inspect the evidence."""


def official(url, host, *, stage='url'):
    allowed = (host,) if isinstance(host, str) else tuple(host)
    expected = ' or '.join('https://' + name for name in allowed)
    try:
        u = urlsplit(url)
        actual_host = u.hostname
        valid = (u.scheme == 'https' and u.netloc in allowed and not u.fragment)
    except (ValueError, TypeError, AttributeError) as exc:
        raise URLPolicyError(f'{stage}: malformed Wikimedia URL; expected {expected}') from exc
    if not valid:
        raise URLPolicyError(
            f'{stage}: Unexpected Wikimedia URL; expected {expected}; '
            f'scheme={u.scheme!r}; host={actual_host!r}; '
            f'authority_exact={u.netloc in allowed}; fragment={bool(u.fragment)}')
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise URLPolicyError(f'response_redirect: HTTP {code}; inspect manually')


class Client:
    def __init__(self):
        self.opener = build_opener(NoRedirect())
        self.last = None

    def get(self, url, host, limit):
        official(url, host, stage='request')
        require(host in HOSTS, 'Unexpected host')
        if self.last is not None:
            time.sleep(max(0, 2 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        with self.opener.open(Request(url, headers={'User-Agent': UA}), timeout=40) as response:
            official(response.geturl(), host, stage='response')
            data = response.read(limit + 1)
            require(len(data) <= limit, 'Response exceeds byte limit')
            return data


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    if not isinstance(value, str):
        return None
    parser = PlainText()
    parser.feed(value)
    parser.close()
    return ' '.join(' '.join(parser.parts).split()) or None


def meta(info, key):
    entry = info.get('extmetadata', {}).get(key, {})
    return entry.get('value') if isinstance(entry, dict) else None


def normalized_license(url):
    if not isinstance(url, str):
        return None
    try:
        u = urlsplit(url)
    except ValueError:
        return None
    if u.scheme not in ('http', 'https') or u.netloc != 'creativecommons.org' or u.query or u.fragment:
        return None
    path = u.path.rstrip('/') + '/'
    # A localized CC deed is a presentation of the same license, not a new license.
    # Only accept known license paths and explicit deed language suffixes.
    path = re.sub(r'/deed(?:\.[a-z]{2,3}(?:[-_][a-zA-Z0-9]{2,8})*)?/$', '/', path)
    canonical = 'https://creativecommons.org' + path
    return canonical if canonical in {v[1] for v in LICENSES.values()} else None


def license_candidate(url, short_name):
    canonical = normalized_license(url)
    license_id = next((i for i, u in LICENSES.values() if u == canonical), None)
    # Commons reports CC0 as either CC0 or CC0 1.0.
    name = 'CC0 1.0' if short_name == 'CC0' else short_name
    declared_id = next((i for key, (i, _) in LICENSES.items() if key == name), None)
    return canonical, license_id, declared_id


def metadata_candidate(info, record):
    artist = plain(meta(info, 'Artist'))
    short_name = plain(meta(info, 'LicenseShortName'))
    license_url, license_id, declared_id = license_candidate(meta(info, 'LicenseUrl'), short_name)
    reasons = []
    if not license_id or license_id != declared_id:
        reasons.append('license_metadata_unrecognized_or_inconsistent')
    if license_id != record['license_id']:
        reasons.append('registry_license_difference')
    if not artist:
        reasons.append('author_missing')
    elif record['author'] is not None and artist != record['author']:
        reasons.append('registry_author_difference')
    return dict(candidate_author=artist, candidate_license_short_name=short_name,
                candidate_license_url=license_url, candidate_license_id=license_id,
                metadata_status='manual_review_required' if reasons else 'candidate_matches_registry',
                review_reasons=reasons)


def parse_page(payload, record):
    require('error' not in payload, f"API error: {payload.get('error', {}).get('code', 'unknown')}")
    pages = payload['query']['pages']
    require(len(pages) == 1, 'Expected exactly one file page')
    page = pages[0]
    require(page.get('ns') == 6 and 'missing' not in page and 'invalid' not in page,
            'Commons file page unavailable')
    title = commons_title(record['source_page_url'])
    require(page['title'].replace('_', ' ') == 'File:' + title, 'File title changed')
    info = page['imageinfo'][0]
    require(commons_title(info['descriptionurl']) == title, 'Description page mismatch')
    official(info['url'], 'upload.wikimedia.org', stage='original_url')
    return page, info


def compare_bytes(local, remote):
    if sha256(local).digest() == sha256(remote).digest():
        return 'thumbnail_sha256_match'
    with Image.open(BytesIO(local)) as a, Image.open(BytesIO(remote)) as b:
        a.load(); b.load()
        if a.size == b.size and a.convert('RGB').tobytes() == b.convert('RGB').tobytes():
            return 'decoded_rgb_match_review'
    return 'unresolved_thumbnail_difference'


def original_matches(local, remote_sha):
    if not isinstance(remote_sha, str):
        return False
    h = sha1(local).hexdigest()
    # MediaWiki API normally uses hex; accept an explicitly valid base36 value too.
    if re.fullmatch(r'[0-9a-fA-F]{40}', remote_sha):
        return h == remote_sha.lower()
    if re.fullmatch(r'[0-9a-z]{1,31}', remote_sha):
        return int(h, 16) == int(remote_sha, 36)
    return False


def save_json(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def audit_one(record, local, client, folder):
    image_id = record['image_id']
    title = commons_title(record['source_page_url'])
    url = API + '?' + urlencode(dict(action='query', format='json', formatversion=2,
        titles='File:' + title, prop='imageinfo|revisions', rvprop='ids|timestamp',
        iiprop='url|size|sha1|mime|timestamp|extmetadata', iiextmetadatalanguage='en',
        iiurlwidth=record['width'], maxlag=5))
    raw = client.get(url, 'commons.wikimedia.org', 4_000_000)
    evidence = folder / (image_id + '.api.json')
    with evidence.open('xb') as stream:
        stream.write(raw)
    payload = json.loads(raw)
    page, info = parse_page(payload, record)
    candidate = metadata_candidate(info, record)
    binary_status = 'unresolved_no_thumbnail'
    remote_hash = None
    if original_matches(local, info.get('sha1')):
        binary_status = 'original_sha1_match'
    elif info.get('thumburl'):
        # Commons may serve thumbnails from either official media host.
        # Bind the actual request and response to the selected exact host.
        thumbnail_url = official(info['thumburl'], THUMBNAIL_HOSTS, stage='thumbnail_url')
        thumbnail_host = urlsplit(thumbnail_url).netloc
        thumb = client.get(thumbnail_url, thumbnail_host, 25_000_000)
        remote_hash = sha256(thumb).hexdigest()
        binary_status = compare_bytes(local, thumb)
    return dict(image_id=image_id, local_sha256=record['sha256'], checked_at=now(),
        source_page_url=record['source_page_url'], api_url=url,
        evidence_file=evidence.name, evidence_sha256=sha256(raw).hexdigest(),
        page_id=page.get('pageid'), page_revision=(page.get('revisions') or [{}])[0],
        original_url=info['url'], original_sha1=info.get('sha1'),
        original_size=[info.get('width'), info.get('height')],
        original_timestamp=info.get('timestamp'), thumbnail_url=info.get('thumburl'),
        thumbnail_size=[info.get('thumbwidth'), info.get('thumbheight')],
        thumbnail_sha256=remote_hash, binary_status=binary_status,
        registry_author=record['author'],
        candidate_credit=plain(meta(info, 'Credit')),
        candidate_attribution=plain(meta(info, 'Attribution')),
        candidate_restrictions=plain(meta(info, 'Restrictions')),
        registry_license_id=record['license_id'],
        publication_status='pending_manual_review', **candidate)


def collect(root, run_id, ids, client):
    root = Path(root).resolve()
    require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', run_id), 'Invalid audit ID')
    groups = read_manifests(root)
    records, manifest_bytes = groups['real_wikimedia']
    require(not ids or (len(set(ids)) == len(ids) and set(ids) <= {r['image_id'] for r in records}),
            'Invalid or duplicate image IDs')
    selected = [r for r in records if not ids or r['image_id'] in ids]
    # Full local preflight before creating any evidence or contacting Commons.
    for r in selected:
        verified_bytes(safe_path(root, r['local_cache_path']), r)
        commons_title(r['source_page_url'])
    folder = safe_path(root, f'data_local/real_wikimedia/attribution/{run_id}')
    folder.mkdir(parents=True, exist_ok=False)
    rows, stopped = [], False
    for r in selected:
        if stopped:
            row = dict(image_id=r['image_id'], metadata_status='not_checked',
                       binary_status='not_checked', publication_status='pending_manual_review')
        else:
            try:
                local = verified_bytes(safe_path(root, r['local_cache_path']), r)
                row = audit_one(r, local, client, folder)
            except Exception as exc:
                row = dict(image_id=r['image_id'], local_sha256=r['sha256'], checked_at=now(),
                           metadata_status='error', binary_status='unresolved',
                           publication_status='pending_manual_review', source_page_url=r['source_page_url'],
                           error_type=type(exc).__name__, error=str(exc))
                # Raw API evidence may already exist even if parsing or the
                # subsequent thumbnail request failed. Retain its identity.
                evidence = folder / (r['image_id'] + '.api.json')
                if evidence.is_file():
                    row['evidence_file'] = evidence.name
                    row['evidence_sha256'] = sha256(evidence.read_bytes()).hexdigest()
                if isinstance(exc, URLPolicyError):
                    stopped = True
                if isinstance(exc, HTTPError) and exc.code in (403, 429, 503):
                    stopped = True
                if 'API error: maxlag' in str(exc) or 'API error: ratelimited' in str(exc):
                    stopped = True
        rows.append(row)
        print(f"{row['image_id']} METADATA={row['metadata_status']} BINARY={row['binary_status']}", flush=True)
    report = dict(schema='bvt.commons-evidence.v1', audit_id=run_id, completed_at=now(),
                  real_manifest_sha256=sha256(manifest_bytes).hexdigest(),
                  synthetic_manifest_sha256=sha256(groups['synthetic_chatgpt'][1]).hexdigest(),
                  requested=len(selected), stopped=stopped,
                  metadata_counts=dict(Counter(r['metadata_status'] for r in rows)),
                  binary_counts=dict(Counter(r['binary_status'] for r in rows)),
                  ready_for_publication=0, records=rows)
    save_json(folder / 'audit_report.json', report)
    print('METADATA_COUNTS=' + json.dumps(report['metadata_counts'], sort_keys=True))
    print('BINARY_COUNTS=' + json.dumps(report['binary_counts'], sort_keys=True))
    print('REPORT=' + str(folder.relative_to(root) / 'audit_report.json'))
    print('READY_FOR_PUBLICATION=0')
    print('COMMONS_EVIDENCE_COLLECTION=' + ('PARTIAL' if stopped or any(r['metadata_status'] == 'error' for r in rows) else 'COMPLETE'))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-id', required=True)
    p.add_argument('--image-id', action='append', help='Select a specific Wikimedia ID; default all 100')
    a = p.parse_args()
    report = collect(ROOT, a.audit_id, a.image_id, Client())
    return 2 if report['stopped'] or report['metadata_counts'].get('error') else 0


if __name__ == '__main__':
    raise SystemExit(main())
