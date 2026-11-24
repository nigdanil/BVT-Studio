import contextlib
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from scripts import audit_dataset_provenance as a
from scripts import review_dataset_provenance as r


class ReviewTests(unittest.TestCase):
    def test_cc0_deed_and_alias(self):
        url = 'https://creativecommons.org/publicdomain/zero/1.0/'
        for suffix in ('', 'deed.en/', 'deed.zh-Hant', 'deed'):
            self.assertEqual(a.license_candidate(url + suffix, 'CC0'), (url, 'CC0-1.0', 'CC0-1.0'))

    def test_license_url_policy(self):
        for url in ('https://creativecommons.org.evil/publicdomain/zero/1.0/deed.en/',
                    'https://user@creativecommons.org/publicdomain/zero/1.0/deed.en/',
                    'https://creativecommons.org/publicdomain/zero/1.0/deed.en/?x=1',
                    'https://creativecommons.org/publicdomain/zero/1.0/deed.evilthing/',
                    'https://creativecommons.org/licenses/by/9.0/', 'https://[broken'):
            self.assertIsNone(a.normalized_license(url))

    def test_author_and_license_conflicts_remain(self):
        info = {'extmetadata': {'Artist': {'value': 'Andy Li'},
                'LicenseShortName': {'value': 'CC0'},
                'LicenseUrl': {'value': 'https://creativecommons.org/publicdomain/zero/1.0/deed.en/'}}}
        result = a.metadata_candidate(info, {'author':'Andy Li (Onthewings)', 'license_id':'CC-BY-4.0'})
        self.assertEqual(result['review_reasons'], ['registry_license_difference', 'registry_author_difference'])
        self.assertEqual(result['metadata_status'], 'manual_review_required')
        info['extmetadata']['LicenseShortName']['value'] = 'CC BY 4.0'
        self.assertIn('license_metadata_unrecognized_or_inconsistent', a.metadata_candidate(info, {'author':None, 'license_id':'CC0-1.0'})['review_reasons'])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.base = self.root/'data_local/real_wikimedia/attribution'
        self.folder = self.base/'source'; self.folder.mkdir(parents=True)
        self.records = []; rows = []
        for i in range(1,101):
            image_id = f'wikimedia_{i:06d}'
            rel = f'data_local/real_wikimedia/clean/images/{image_id}.jpg'
            path = self.root/rel; path.parent.mkdir(parents=True, exist_ok=True)
            out = BytesIO(); Image.new('RGB',(8,6),(i,2,3)).save(out,format='JPEG'); data=out.getvalue(); path.write_bytes(data)
            record = dict(image_id=image_id, local_cache_path=rel, sha256=sha256(data).hexdigest(), width=8,height=6,file_format='JPEG',source_page_url=f'https://commons.wikimedia.org/wiki/File:Fixture_{i}.jpg',author=None,license_id='CC0-1.0')
            if i==100: record['author']='Old author'
            self.records.append(record)
            info = dict(descriptionurl=record['source_page_url'], url=f'https://upload.wikimedia.org/{i}.jpg', thumburl=f'https://thumb.wikimedia.org/{i}.jpg',sha1='0'*40,width=80,height=60,thumbwidth=8,thumbheight=6,extmetadata={'Artist':{'value':'Author'},'LicenseUrl':{'value':'https://creativecommons.org/publicdomain/zero/1.0/deed.en/'},'LicenseShortName':{'value':'CC0'}})
            revision={'revid':i}; page=dict(ns=6,title=f'File:Fixture {i}.jpg',pageid=i,revisions=[revision],imageinfo=[info]); raw=json.dumps({'query':{'pages':[page]}}).encode(); name=image_id+'.api.json'; (self.folder/name).write_bytes(raw)
            rows.append(dict(image_id=image_id,local_sha256=record['sha256'],source_page_url=record['source_page_url'],registry_author=record['author'],registry_license_id=record['license_id'],metadata_status='manual_review_required',publication_status='pending_manual_review',binary_status='thumbnail_sha256_match',evidence_file=name,evidence_sha256=sha256(raw).hexdigest(),page_id=i,page_revision=revision,original_url=info['url'],original_sha1=info['sha1'],original_size=[80,60],thumbnail_url=info['thumburl'],thumbnail_size=[8,6],thumbnail_sha256=record['sha256'],candidate_author='Author',candidate_license_short_name='CC0',candidate_license_url=info['extmetadata']['LicenseUrl']['value'],candidate_license_id=None,candidate_credit=None,candidate_attribution=None,candidate_restrictions=None))
        self.report=dict(schema='bvt.commons-evidence.v1',audit_id='source',stopped=False,requested=100,ready_for_publication=0,real_manifest_sha256=r.digest(b'real'),synthetic_manifest_sha256=r.digest(b'synthetic'),records=rows,metadata_counts={'manual_review_required':100},binary_counts={'thumbnail_sha256_match':100})
        self.path=self.folder/'audit_report.json'; self.write_report()
        self.groups={'real_wikimedia':(self.records,b'real'),'synthetic_chatgpt':([],b'synthetic')}

    def write_report(self): self.path.write_text(json.dumps(self.report))

    def run_review(self):
        with patch.object(a,'read_manifests',return_value=self.groups), contextlib.redirect_stdout(StringIO()):
            return r.review(self.root,'source','review')

    def test_full_review_and_no_overwrite(self):
        before=self.path.read_bytes(); result=self.run_review()
        self.assertEqual(result['metadata_counts'],{'candidate_matches_registry':99,'manual_review_required':1})
        self.assertEqual(result['license_counts'],{'CC0-1.0':100})
        self.assertEqual(result['ready_for_publication'],0)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertTrue((self.base/'review/ATTRIBUTION_CANDIDATES.md').is_file())
        with self.assertRaisesRegex(ValueError,'already exists'): self.run_review()

    def test_raw_tamper_rejected(self):
        (self.folder/'wikimedia_000100.api.json').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'Evidence SHA mismatch'): self.run_review()
        self.assertFalse((self.base/'review').exists())

    def test_stale_manifest_rejected(self):
        self.report['real_manifest_sha256']='0'*64; self.write_report()
        with self.assertRaisesRegex(ValueError,'manifest SHA mismatch'): self.run_review()
        self.assertFalse((self.base/'review').exists())

    def test_thumbnail_tamper_rejected(self):
        self.report['records'][-1]['thumbnail_sha256']='0'*64; self.write_report()
        with self.assertRaisesRegex(ValueError,'Thumbnail evidence mismatch'): self.run_review()
        self.assertFalse((self.base/'review').exists())
