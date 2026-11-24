import json
from hashlib import sha1, sha256
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from PIL import Image
from scripts import audit_dataset_provenance as a


def image(color=(10, 20, 30), fmt='JPEG'):
    out = BytesIO()
    Image.new('RGB', (8, 6), color).save(out, format=fmt)
    return out.getvalue()


class Client:
    def __init__(self, payload, thumb):
        self.payload = payload
        self.thumb = thumb
        self.calls = []
    def get(self, url, host, limit):
        self.calls.append((url, host))
        if host == 'commons.wikimedia.org':
            return json.dumps(self.payload).encode()
        return self.thumb


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = image()
        self.record = dict(image_id='wikimedia_000099', width=8, height=6,
            file_format='JPEG', sha256=sha256(self.data).hexdigest(),
            source_page_url='https://commons.wikimedia.org/wiki/File:Fixture.jpg',
            license_id='CC-BY-4.0', author='Example Author',
            local_cache_path='data_local/real_wikimedia/clean/images/wikimedia_000099.jpg')
        self.info = dict(descriptionurl=self.record['source_page_url'],
            url='https://upload.wikimedia.org/wikipedia/commons/a/ab/Fixture.jpg',
            thumburl='https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Fixture.jpg/8px-Fixture.jpg',
            width=80, height=60, thumbwidth=8, thumbheight=6, sha1='0'*40,
            extmetadata={'Artist': {'value':'<a>Example Author</a>'},
                         'LicenseUrl': {'value':'https://creativecommons.org/licenses/by/4.0/'},
                         'LicenseShortName': {'value':'CC BY 4.0'}})
        self.payload = {'query': {'pages': [{'ns':6, 'title':'File:Fixture.jpg',
                       'pageid':5, 'imageinfo':[self.info], 'revisions':[{'revid':8}]}]}}

    def test_thumbnail_match_and_evidence(self):
        r = a.audit_one(self.record, self.data, Client(self.payload, self.data), self.root)
        self.assertEqual(r['binary_status'], 'thumbnail_sha256_match')
        self.assertEqual(r['metadata_status'], 'candidate_matches_registry')
        self.assertEqual(r['candidate_author'], 'Example Author')
        self.assertEqual(r['publication_status'], 'pending_manual_review')
        self.assertEqual(r['evidence_sha256'], sha256((self.root/r['evidence_file']).read_bytes()).hexdigest())

    def test_dedicated_thumbnail_host_with_tracking_query(self):
        query = '?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail'
        self.info['thumburl'] = self.info['thumburl'].replace('upload.wikimedia.org', 'thumb.wikimedia.org') + query
        client = Client(self.payload, self.data)
        row = a.audit_one(self.record, self.data, client, self.root)
        self.assertEqual(row['binary_status'], 'thumbnail_sha256_match')
        self.assertEqual(row['metadata_status'], 'candidate_matches_registry')
        self.assertEqual(row['thumbnail_url'], self.info['thumburl'])
        self.assertEqual(client.calls[1], (self.info['thumburl'], 'thumb.wikimedia.org'))
        self.assertEqual(row['publication_status'], 'pending_manual_review')

    def test_thumbnail_allowlist_rejects_aliases(self):
        for url in ('http://thumb.wikimedia.org/x', 'https://thumb.wikimedia.org.evil/x',
                    'https://user@thumb.wikimedia.org/x', 'https://thumb.wikimedia.org:443/x',
                    'https://thumb.wikimedia.org/x#fragment', 'https://commons.wikimedia.org/x'):
            with self.subTest(url=url), self.assertRaises(a.URLPolicyError):
                a.official(url, a.THUMBNAIL_HOSTS, stage='thumbnail_url')

    def test_original_host_not_relaxed(self):
        self.info['url'] = self.info['url'].replace('upload.wikimedia.org', 'thumb.wikimedia.org')
        with self.assertRaisesRegex(a.URLPolicyError, 'original_url:'):
            a.parse_page(self.payload, self.record)

    def test_thumbnail_client_binds_response_to_selected_host(self):
        client = a.Client()
        url = 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Fixture.jpg/8px-Fixture.jpg'
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = url
        response.read.return_value = self.data
        with patch.object(client.opener, 'open', return_value=response) as open_mock:
            self.assertEqual(client.get(url, 'thumb.wikimedia.org', 10000), self.data)
            self.assertEqual(open_mock.call_count, 1)
            response.geturl.return_value = url.replace('thumb.wikimedia.org', 'upload.wikimedia.org')
            client.last = None
            with self.assertRaisesRegex(a.URLPolicyError, 'response:'):
                client.get(url, 'thumb.wikimedia.org', 10000)

    def test_original_match_no_thumbnail_request(self):
        self.info['sha1'] = sha1(self.data).hexdigest()
        c = Client(self.payload, b'bad')
        self.assertEqual(a.audit_one(self.record, self.data, c, self.root)['binary_status'], 'original_sha1_match')
        self.assertEqual(len(c.calls), 1)

    def test_binary_difference_unresolved(self):
        r = a.audit_one(self.record, self.data, Client(self.payload, image((255,0,0))), self.root)
        self.assertEqual(r['binary_status'], 'unresolved_thumbnail_difference')
        self.assertEqual(r['publication_status'], 'pending_manual_review')

    def test_missing_author_or_disagreeing_license(self):
        self.info['extmetadata'].pop('Artist')
        self.info['extmetadata']['LicenseShortName']['value'] = 'CC BY-SA 4.0'
        r = a.audit_one(self.record, self.data, Client(self.payload, self.data), self.root)
        self.assertIsNone(r['candidate_author'])
        self.assertEqual(r['metadata_status'], 'manual_review_required')

    def test_missing_page_and_title_change(self):
        page = self.payload['query']['pages'][0]
        page['missing'] = True
        with self.assertRaises(ValueError): a.parse_page(self.payload, self.record)
        del page['missing']; page['title'] = 'File:Other.jpg'
        with self.assertRaisesRegex(ValueError, 'title changed'): a.parse_page(self.payload, self.record)

    def test_untrusted_urls(self):
        for url in ('http://upload.wikimedia.org/x','https://upload.wikimedia.org.evil/x',
                    'https://user@upload.wikimedia.org/x','https://upload.wikimedia.org:443/x'):
            with self.assertRaises(ValueError): a.official(url, 'upload.wikimedia.org')
        self.assertIsNone(a.normalized_license('https://evil.example/licenses/by/4.0/'))

    def test_http_client_validates_actual_response_url(self):
        client = a.Client()
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = a.API + '?format=json'
        response.read.return_value = b'{}'
        with patch.object(client.opener, 'open', return_value=response) as open_mock:
            self.assertEqual(client.get(a.API, 'commons.wikimedia.org', 10), b'{}')
            self.assertEqual(open_mock.call_count, 1)
            response.geturl.return_value = 'http://commons.wikimedia.org/w/api.php'
            client.last = None
            with self.assertRaisesRegex(a.URLPolicyError, 'response:.*scheme='):
                client.get(a.API, 'commons.wikimedia.org', 10)
        with self.assertRaisesRegex(a.URLPolicyError, 'request:'):
            client.get('https://example.invalid/w/api.php', 'commons.wikimedia.org', 10)

    def test_original_url_stage_and_evidence(self):
        self.info['url'] = 'http://upload.wikimedia.org/a.jpg'
        with self.assertRaisesRegex(a.URLPolicyError, 'original_url:'):
            a.audit_one(self.record, self.data, Client(self.payload, self.data), self.root)
        self.assertTrue((self.root / 'wikimedia_000099.api.json').is_file())

    def test_thumbnail_url_stage(self):
        self.info['thumburl'] = 'https://example.invalid/a.jpg'
        client = Client(self.payload, self.data)
        with self.assertRaisesRegex(a.URLPolicyError, 'thumbnail_url:'):
            a.audit_one(self.record, self.data, client, self.root)
        self.assertEqual(len(client.calls), 1)

    def test_url_failure_stops_and_preserves_raw_evidence(self):
        path = self.root / self.record['local_cache_path']
        path.parent.mkdir(parents=True); path.write_bytes(self.data)
        other = dict(self.record, image_id='wikimedia_000100',
                     local_cache_path=self.record['local_cache_path'].replace('099','100'))
        (self.root/other['local_cache_path']).write_bytes(self.data)
        groups = {'real_wikimedia': ([self.record, other], b'real'),
                  'synthetic_chatgpt': ([], b'synthetic')}
        self.info['url'] = 'https://example.invalid/a.jpg'
        client = Client(self.payload, self.data)
        with patch.object(a, 'read_manifests', return_value=groups):
            report = a.collect(self.root, 'url-failure', None, client)
        self.assertTrue(report['stopped'])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(report['metadata_counts'], {'error':1,'not_checked':1})
        row = report['records'][0]
        self.assertEqual(row['error_type'], 'URLPolicyError')
        self.assertIn('original_url:', row['error'])
        raw = self.root / 'data_local/real_wikimedia/attribution/url-failure' / row['evidence_file']
        self.assertEqual(row['evidence_sha256'], sha256(raw.read_bytes()).hexdigest())
        self.assertEqual(report['ready_for_publication'], 0)
        self.assertEqual(path.read_bytes(), self.data)

    def test_rgb_equality_only_candidate(self):
        with Image.open(BytesIO(self.data)) as im:
            out = BytesIO(); im.convert('RGB').save(out, format='PNG')
        self.assertEqual(a.compare_bytes(self.data, out.getvalue()), 'decoded_rgb_match_review')

    def test_collect_read_only_and_collision(self):
        path = self.root / self.record['local_cache_path']
        path.parent.mkdir(parents=True); path.write_bytes(self.data)
        groups = {'real_wikimedia': ([self.record], b'real'), 'synthetic_chatgpt': ([], b'synthetic')}
        with patch.object(a, 'read_manifests', return_value=groups):
            report = a.collect(self.root, 'pilot', None, Client(self.payload, self.data))
            self.assertEqual(report['ready_for_publication'], 0)
            self.assertEqual(report['real_manifest_sha256'], sha256(b'real').hexdigest())
            self.assertEqual(path.read_bytes(), self.data)
            with self.assertRaises(FileExistsError): a.collect(self.root, 'pilot', None, Client(self.payload, self.data))

    def test_throttle_stops_without_retry(self):
        path = self.root / self.record['local_cache_path']
        path.parent.mkdir(parents=True); path.write_bytes(self.data)
        other = dict(self.record, image_id='wikimedia_000100', local_cache_path=self.record['local_cache_path'].replace('099','100'))
        (self.root/other['local_cache_path']).write_bytes(self.data)
        groups = {'real_wikimedia': ([self.record, other], b'real'), 'synthetic_chatgpt': ([], b'synthetic')}
        class Throttle:
            def get(self, url, host, limit):
                raise HTTPError(url,429,'Too Many Requests',{},None)
        with patch.object(a, 'read_manifests', return_value=groups):
            report = a.collect(self.root, 'throttle', None, Throttle())
        self.assertTrue(report['stopped'])
        self.assertEqual(report['metadata_counts'], {'error':1,'not_checked':1})


if __name__ == '__main__':
    unittest.main()
