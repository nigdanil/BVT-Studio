import unittest
from io import BytesIO
from pathlib import Path
from hashlib import sha256
import json
from openpyxl import load_workbook
from scripts import build_dataset_manifests as m
from scripts import prepare_provenance_update as u
from test_dataset_manifests import workbook


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.old = workbook()
        meta = m.read_registry(self.old)
        self.rows = []
        for i in range(1,101):
            r=meta[i]
            lic = 'CC-BY-SA-4.0' if i==4 else r['license_id']
            url=next(v[1] for v in m.LICENSES.values() if v[0]==lic)
            self.rows.append(dict(image_id=f'wikimedia_{i:06d}', candidate_author='API author '+str(i),
                candidate_license_id=lic,candidate_license_url=url,checked_at='2026-11-24T14:00:00+00:00',
                page_revision={'revid':i},thumbnail_url=f'https://thumb.wikimedia.org/{i}.jpg',
                thumbnail_sha256='1'*64,evidence_sha256='2'*64,review_reasons=['registry_license_difference'] if i==4 else [],
                source_page_url=r['source_page_url'],candidate_credit='Own work',candidate_attribution=None,candidate_restrictions=None))

    def updated(self):
        return u.update_workbook(self.old,self.rows,'3'*64,'4'*64)

    def test_preserves_old_workbook_and_current_metadata(self):
        old_hash=sha256(self.old).hexdigest()
        data=self.updated(); old=m.read_registry(self.old); new=m.read_registry(data)
        self.assertEqual(len(new),100)
        self.assertEqual(sha256(self.old).hexdigest(),old_hash)
        self.assertEqual(new[100]['author'],'API author 100')
        self.assertEqual(new[4]['license_verification_status'],'manual_review_required')
        self.assertEqual(new[1]['license_verification_status'],'api_evidence_recorded')
        self.assertEqual(new[95]['scene_type'],old[95]['scene_type'])
        self.assertEqual(new[1]['license_evidence_url'],'https://commons.wikimedia.org/w/index.php?oldid=1')
        self.assertEqual(new[1]['_evidence_sha256'],'1'*64)

    def test_actual_license_change_and_previous_value(self):
        self.rows[3]['candidate_license_id']='CC0-1.0'
        self.rows[3]['candidate_license_url']=m.LICENSES['CC0 1.0'][1]
        data=self.updated(); wb=load_workbook(BytesIO(data)); self.addCleanup(wb.close)
        self.assertEqual(m.read_registry(data)[4]['license_id'],'CC0-1.0')
        self.assertEqual(wb[m.API_SHEET]['M5'].value,'CC-BY-SA-4.0')
        for row in wb['Реестр'].iter_rows(min_row=2):
            if row[0].value==4: self.assertIn('CC0 1.0',row[3].value)

    def test_metadata_sheet_mismatch_rejected(self):
        wb=load_workbook(BytesIO(self.updated())); self.addCleanup(wb.close)
        wb[m.API_SHEET]['C2']='tampered'; data=BytesIO(); wb.save(data)
        with self.assertRaisesRegex(ValueError,'API sheet metadata mismatch'): m.read_registry(data.getvalue())

    def test_literal_author_and_no_formula(self):
        self.rows[0]['candidate_author']='=1+1'
        data=self.updated(); wb=load_workbook(BytesIO(data)); self.addCleanup(wb.close)
        self.assertEqual(wb[m.API_SHEET]['C2'].data_type,'s')
        self.assertEqual(m.read_registry(data)[1]['author'],'=1+1')

    def test_bad_id_and_migrated_workbook_rejected(self):
        data=self.updated()
        with self.assertRaisesRegex(ValueError,'Already migrated'): u.update_workbook(data,self.rows,'3'*64,'4'*64)
        self.rows[0]['image_id']='wrong'
        with self.assertRaisesRegex(ValueError,'Wrong order'): self.updated()

    def test_attribution_is_not_clearance(self):
        text=u.attribution(self.rows).decode()
        self.assertIn('publication pending',text)
        self.assertIn('manual_review_required',text)
        self.assertEqual(text.count('| wikimedia_'),100)
        self.assertIn('revision 100',text)

    def test_original_notice_preserved(self):
        old=b'# Historical\nold data\n'
        self.assertTrue(u.document(old,'# New','New policy').endswith(old))

    def test_stage_with_200_fixture_images(self):
        import tempfile
        import shutil
        from unittest.mock import patch
        from collections import Counter
        from PIL import Image
        from scripts import audit_dataset_provenance as a
        from scripts import review_dataset_provenance as review_tool
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'repo'; source=root.parent/'source'
            def write(p,data):
                path=root/p; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
            write(m.REGISTRY,self.old); write(m.SYNTHETIC_DOC,b'# Synthetic\n'); write(u.THIRD,b'# Real\n')
            write(u.DOC_README,b'The real collection records individual Creative Commons licenses: 11 entries are recorded as page-reviewed and 89 require individual review and author information. Binary correspondence of record 99 to its Wikimedia source remains pending (stage 14).')
            write(m.SCHEMA,(m.ROOT/m.SCHEMA).read_bytes())
            for c,(prefix,ext,fmt,storage,_) in m.COLLECTIONS.items():
                for i in range(1,101):
                    name=f'{prefix}_{i:06d}{ext}'; path=root/f'data_local/{c}/clean/images/{name}'
                    path.parent.mkdir(parents=True,exist_ok=True)
                    Image.new('RGB',(i+8,12),(i,50,180)).save(path,format=fmt)
                    remote=source/storage/'images'/name; remote.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,remote)
            initial=m.build(root,source)
            for c,p in u.MANIFESTS.items(): write(p,m.encode(initial[c]))
            baseline={p:u.digest((root/p).read_bytes()) for p in u.BASELINE}
            records=[]
            for i,old in enumerate(initial['real_wikimedia'],1):
                key=next(k for k,v in m.LICENSES.items() if v[0]==old['license_id'])
                if i==4: key='CC0 1.0'
                url=m.LICENSES[key][1]; artist=old['author'] or 'API artist'
                if i==100: artist='New artist'
                image_id=old['image_id']; name=image_id+'.api.json'
                info=dict(descriptionurl=old['source_page_url'],url=f'https://upload.wikimedia.org/{i}.jpg',thumburl=f'https://thumb.wikimedia.org/{i}.jpg',sha1='0'*40,width=80,height=60,thumbwidth=old['width'],thumbheight=old['height'],extmetadata={'Artist':{'value':artist},'LicenseUrl':{'value':url},'LicenseShortName':{'value':key},'Credit':{'value':'Own work'}})
                rev={'revid':i}; page=dict(ns=6,title='File:'+old['original_filename'],pageid=i,revisions=[rev],imageinfo=[info]); raw=json.dumps({'query':{'pages':[page]}}).encode()
                write(u.BASE+'commons-full-002/'+name,raw)
                candidate=a.metadata_candidate(info,old)
                records.append(dict(image_id=image_id,local_sha256=old['sha256'],source_page_url=old['source_page_url'],registry_author=old['author'],registry_license_id=old['license_id'],publication_status='pending_manual_review',binary_status='thumbnail_sha256_match',evidence_file=name,evidence_sha256=u.digest(raw),page_id=i,page_revision=rev,original_url=info['url'],original_sha1=info['sha1'],original_size=[80,60],thumbnail_url=info['thumburl'],thumbnail_size=[old['width'],old['height']],thumbnail_sha256=old['sha256'],candidate_credit='Own work',candidate_attribution=None,candidate_restrictions=None,checked_at='2026-11-24T14:00:00+00:00',**candidate))
            report=dict(schema='bvt.commons-evidence.v1',audit_id='commons-full-002',stopped=False,requested=100,ready_for_publication=0,real_manifest_sha256=baseline[u.MANIFESTS['real_wikimedia']],synthetic_manifest_sha256=baseline[u.MANIFESTS['synthetic_chatgpt']],records=records,metadata_counts=dict(Counter(r['metadata_status'] for r in records)),binary_counts={'thumbnail_sha256_match':100})
            data=json.dumps(report).encode(); write(u.BASE+'commons-full-002/audit_report.json',data)
            rv=review_tool.review(root,'commons-full-002','commons-review-001')
            review_hash=u.digest((root/u.BASE/'commons-review-001/review_candidates.json').read_bytes())
            with patch.multiple(u,BASELINE=baseline,AUDIT_SHA=u.digest(data),REVIEW_SHA=review_hash,COUNTS=dict(Counter(r['candidate_license_id'] for r in records))):
                ledger=u.stage(root,source)
                self.assertEqual(len(ledger),7)
                base=root/u.BASE/'commons-update-001'
                for p,h in baseline.items(): self.assertEqual(u.digest((root/p).read_bytes()),h)
                latest=m.build(root,source,registry_data=(base/'after'/m.REGISTRY).read_bytes(),synthetic_data=(base/'after'/m.SYNTHETIC_DOC).read_bytes())
                for c,p in u.MANIFESTS.items(): self.assertEqual(m.encode(latest[c]),(base/'after'/p).read_bytes())
                self.assertEqual(latest['real_wikimedia'][3]['license_id'],'CC0-1.0')
                self.assertEqual(latest['real_wikimedia'][99]['author'],'New artist')
                self.assertTrue(all(r['redistribution_review_status']=='pending' for r in latest['real_wikimedia']))
                with self.assertRaisesRegex(ValueError,'already exists'): u.stage(root,source)
                ledger_sha=u.digest((base/'migration.json').read_bytes())
                with self.assertRaisesRegex(ValueError,'approval SHA mismatch'): u.promote(root,source,'0'*64)
                bad=base/'after'/u.ATTR; original=bad.read_bytes(); bad.write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError,'Staged file SHA mismatch'): u.promote(root,source,ledger_sha)
                bad.write_bytes(original)
                for p,h in baseline.items(): self.assertEqual(u.digest((root/p).read_bytes()),h)
                u.promote(root,source,ledger_sha)
                for p,entry in ledger.items(): self.assertEqual(u.digest((root/p).read_bytes()),entry['after'])
                m.publish(root,m.build(root,source),check=True)
                self.assertEqual(u.digest((base/'before'/m.REGISTRY).read_bytes()),baseline[m.REGISTRY])
