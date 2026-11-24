"""Stage a metadata migration, or explicitly promote an inspected bundle; never edit Drive data."""
import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
import os
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
if __package__:
    from . import build_dataset_manifests as m
    from . import audit_dataset_provenance as a
else:
    import build_dataset_manifests as m
    import audit_dataset_provenance as a

BASE = 'data_local/real_wikimedia/attribution/'
THIRD = m.DOCS / 'THIRD_PARTY_RETAIL_IMAGES.md'
ATTR = m.DOCS / 'ATTRIBUTION.md'
DOC_README = m.DOCS / 'README.md'
MANIFESTS = {c: Path(f'datasets/manifests/{c}.jsonl') for c in m.COLLECTIONS}
BASELINE = {
    m.REGISTRY: 'd81c3155dbc45fdb6e72eee0a1e9e6686cabbff5637bdf453fa5c606114f9e76',
    m.SYNTHETIC_DOC: 'ccc70585102ada3027e2239468d83c7cad8405f141a0af5fa80c02bb8b439e95',
    THIRD: '6b54c7aad75c32ffeb1715bb1706cc2fc00b7e3272c8e50d66f181f0f0fab745',
    MANIFESTS['synthetic_chatgpt']: '4e701876982d58f6fc3a63956e4ce7a28e82b3bfb36fa6271cde38d7793d6a64',
    MANIFESTS['real_wikimedia']: '9bea5990ebb9cd40978cb9b50ab002619bdee95d76984d1af9088c3de60b7e3a',
}
AUDIT_SHA = 'ece8ca40e604fbed4bcdb7efbf2a7cfd7a309f2b0bd47ef395ee10f920b279d8'
REVIEW_SHA = 'd65a4fbafff1d7ebeebd84ec6cdd22370945494438ea8a9767ce4e4145474565'
COUNTS = {'CC-BY-SA-4.0':77,'CC0-1.0':14,'CC-BY-4.0':4,'CC-BY-2.0':3,'CC-BY-SA-2.5':1,'CC-BY-SA-3.0':1}
CONFLICTS = {'wikimedia_000004':['registry_license_difference'], 'wikimedia_000100':['registry_author_difference']}


def digest(data):
    return sha256(data).hexdigest()


def need(ok, msg):
    m.require(ok, msg)


def check_review(root, old_records, report, review, audit_hash):
    need(review['schema'] == 'bvt.commons-review-candidates.v1' and review['source_audit_sha256'] == audit_hash
         and review['source_audit_id'] == 'commons-full-002' and review['review_id'] == 'commons-review-001'
         and review['ready_for_publication'] == report['ready_for_publication'] == 0, 'Wrong review snapshot')
    for key in ('real_manifest_sha256', 'synthetic_manifest_sha256'):
        need(review[key] == report[key], 'Review/ audit manifest mismatch')
    rows = review['records']
    need(len(rows) == len(report['records']) == len(old_records) == 100, 'Incomplete evidence')
    need(Counter(r['candidate_license_id'] for r in rows) == COUNTS, 'Unexpected license inventory')
    for old, saved, row in zip(old_records, report['records'], rows):
        image_id = old['image_id']
        need(row['image_id'] == saved['image_id'] == image_id, 'ID mismatch')
        need(row['review_reasons'] == CONFLICTS.get(image_id, []), f'Unexpected conflict: {image_id}')
        need(row['metadata_status'] == ('manual_review_required' if image_id in CONFLICTS else 'candidate_matches_registry'), 'Wrong metadata status')
        need(row['publication_status'] == 'pending_manual_review' and row['binary_status'] == 'thumbnail_sha256_match', 'Wrong evidence status')
        need(row['local_sha256'] == row['thumbnail_sha256'] == old['sha256'] == saved['local_sha256'], 'Image hash mismatch')
        need(row['source_page_url'] == old['source_page_url'] == saved['source_page_url'] and
             row['registry_author'] == old['author'] and row['registry_license_id'] == old['license_id'], 'Registry snapshot mismatch')
        name = image_id + '.api.json'
        need(row['evidence_file'] == saved['evidence_file'] == name, 'Evidence filename mismatch')
        raw = a.safe_path(root, BASE + 'commons-full-002/' + name).read_bytes()
        need(digest(raw) == row['evidence_sha256'] == saved['evidence_sha256'], 'Raw evidence SHA mismatch')
        page, info = a.parse_page(json.loads(raw), old)
        candidate = a.metadata_candidate(info, old)
        need(all(row[k] == v for k, v in candidate.items()), f'API candidate mismatch: {image_id}')
        need(row['page_revision'] == (page.get('revisions') or [{}])[0] == saved['page_revision'], 'Revision mismatch')
        need(row['thumbnail_url'] == info['thumburl'] == saved['thumbnail_url'] and
             row['thumbnail_size'] == [old['width'], old['height']] == [info['thumbwidth'],info['thumbheight']], 'Thumbnail mismatch')
        for key, field in [('Credit','candidate_credit'),('Attribution','candidate_attribution'),('Restrictions','candidate_restrictions')]:
            need(row[field] == a.plain(a.meta(info,key)), 'Credit/rights evidence mismatch')
        need(row['checked_at'] == saved['checked_at'], 'Audit date mismatch')
    return rows


def index(ws):
    result = {}
    for row in ws.iter_rows(min_row=2):
        i = row[0].value
        if i is None:
            continue
        need(type(i) is int and i not in result, 'Invalid workbook ID')
        result[i] = row[0].row
    return result


def put(ws, r, c, value):
    cell = ws.cell(r,c)
    cell.value = value
    if isinstance(value,str):
        cell.data_type = 's'  # API text must never become a formula.
    if cell.hyperlink and isinstance(value,str) and value.startswith('https://'):
        cell.hyperlink = value


def update_workbook(data, rows, audit_sha, review_sha):
    original = m.read_registry(data)
    wb = load_workbook(BytesIO(data))
    try:
        need(m.API_SHEET not in wb.sheetnames, 'Already migrated')
        r,audit,d = (wb[x] for x in ('Реестр','Аудит BVT','Новые 6 — источники'))
        ri,ai,di = map(index,(r,audit,d))
        need(set(ri)==set(ai)==set(range(1,101)) and set(di)==set(range(95,101)), 'Invalid workbook inventory')
        evidence = wb.create_sheet(m.API_SHEET,0)
        evidence.append(m.API_HEADERS)
        for c in evidence[1]:
            c.fill=PatternFill('solid',fgColor='24465A'); c.font=Font(bold=True,color='FFFFFF')
        for n, row in enumerate(rows,1):
            need(row['image_id']==f'wikimedia_{n:06d}', 'Wrong order')
            prev=original[n]; key=next(k for k,v in m.LICENSES.items() if v==(row['candidate_license_id'],row['candidate_license_url']))
            author=row['candidate_author']; lic=row['candidate_license_id']; url=row['candidate_license_url']
            status='manual_review_required' if row['review_reasons'] else 'api_evidence_recorded'
            ar=ai[n]; rr=ri[n]
            values=(n,prev['source_page_url'],author,lic,url,row['checked_at'],row['page_revision']['revid'],
                    row['thumbnail_url'],row['thumbnail_sha256'],row['evidence_sha256'],status,prev['author'],prev['license_id'],
                    r.cell(rr,4).value,audit.cell(ar,10).value,row['candidate_credit'],row['candidate_attribution'],
                    row['candidate_restrictions'],audit_sha,review_sha)
            for col,val in enumerate(values,1): put(evidence,n+1,col,val)
            put(audit,ar,11,author); put(audit,ar,3,key); put(audit,ar,14,url)
            # Preserve historical page-review values; record current API evidence separately.
            put(audit,ar,16,'Проверить условия использования и права третьих лиц; публикация не одобрена.' + (' Расхождение: '+', '.join(row['review_reasons']) if row['review_reasons'] else ''))
            if lic != prev['license_id']:
                label=f'{key} — заявлено в Commons API 24.11.2026; расхождение требует ручной проверки.'
                put(r,rr,4,label); put(audit,ar,15,label)
                conditions = ('ShareAlike для распространяемых адаптаций; ' if lic.startswith('CC-BY-SA-') else '')
                put(audit,ar,8,'Условно: '+conditions+'соблюдение указанной лицензии; проверка прав не завершена.')
                put(audit,ar,9,'Автор, источник, лицензия и описание изменений.' if lic!='CC0-1.0' else 'Рекомендуется указывать источник и автора.')
                put(audit,ar,12,str(audit.cell(ar,12).value or '')+'; '+conditions+'расхождение прежней и текущей заявленной лицензии требует проверки.')
            if n in di:
                put(d,di[n],8,author); put(d,di[n],9,key); put(d,di[n],13,url)
        for col,val in enumerate(m.API_AUDIT_HEADERS,1): put(audit,1,col,val)
        evidence.freeze_panes='B2'; evidence.auto_filter.ref=evidence.dimensions
        for i,width in enumerate((8,55,28,20,48,30,18,55,30,30,30,28,22,50,32,25,30,30,30,30),1):
            evidence.column_dimensions[get_column_letter(i)].width=width
        if 'Сводка' in wb.sheetnames:
            put(wb['Сводка'],1,1,'ИСТОРИЧЕСКАЯ СВОДКА — до аудита Commons API; актуальные данные: Commons API 2026-11-24')
        summary=wb.create_sheet('Сводка API',1)
        for vals in [('Показатель','Значение'),('Изображения',100),('Совпадение SHA256 миниатюр',100),('Авторы по API',100),('Расхождения — ручная проверка',2),('Готово к публикации',0),*sorted(COUNTS.items())]: summary.append(vals)
        summary.freeze_panes='A2'; summary.column_dimensions['A'].width=45; summary.column_dimensions['B'].width=18
        for c in summary[1]: c.font=Font(bold=True)
        wb.active=0
        output=BytesIO(); wb.save(output)
        return output.getvalue()
    finally:
        wb.close()


def document(original, heading, body):
    return (heading+'\n\n'+body+'\n\n---\n\n## Historical source notice (before stage 14D)\n\n').encode('utf-8')+original


def attribution(rows):
    lines=['# Wikimedia attribution register — API-reported metadata; publication pending','',
           'Audit: commons-full-002 (2026-11-24); offline review: commons-review-001.',
           'All local JPEGs matched Commons thumbnails by SHA-256. This register is not rights clearance.',
           'The two flagged records retain their prior values in the Excel evidence sheet. Review third-party rights and disclose modifications; apply ShareAlike where required.', '',
           '| ID | API author | License | Source / revision | Credit / requested attribution / restrictions | Status |','|---|---|---|---|---|---|']
    def cell(v): return str(v or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','&#124;').replace('\n',' ').replace('\r',' ')
    for row in rows:
        rev=row['page_revision']['revid']; status='manual_review_required' if row['review_reasons'] else 'api_evidence_recorded'
        lines.append(f'| {row["image_id"]} | {cell(row["candidate_author"])} | [{row["candidate_license_id"]}]({row["candidate_license_url"]}) | [file page](<{row["source_page_url"]}>) / [revision {rev}](https://commons.wikimedia.org/w/index.php?oldid={rev}) | {cell(row["candidate_credit"])} / {cell(row["candidate_attribution"])} / {cell(row["candidate_restrictions"])} | {status} |')
    return ('\n'.join(lines)+'\n').encode('utf-8')


def stage(root, source):
    root=Path(root).resolve()
    output=a.safe_path(root,BASE+'commons-update-001')
    need(not output.exists(),'Update already exists; do not overwrite')
    old={p:a.safe_path(root,p).read_bytes() for p in BASELINE}
    old[DOC_README]=a.safe_path(root,DOC_README).read_bytes()
    need(all(digest(old[p])==h for p,h in BASELINE.items()),'Baseline metadata SHA mismatch')
    need(not a.safe_path(root,ATTR).exists(),'Attribution already exists')
    report_data=a.safe_path(root,BASE+'commons-full-002/audit_report.json').read_bytes()
    review_data=a.safe_path(root,BASE+'commons-review-001/review_candidates.json').read_bytes()
    need(digest(report_data)==AUDIT_SHA and digest(review_data)==REVIEW_SHA,'Evidence report SHA mismatch')
    report,review=map(json.loads,(report_data,review_data))
    initial=m.build(root,source)
    need(all(m.encode(initial[c])==old[p] for c,p in MANIFESTS.items()),'Baseline regeneration mismatch')
    need(report['real_manifest_sha256']==BASELINE[MANIFESTS['real_wikimedia']] and report['synthetic_manifest_sha256']==BASELINE[MANIFESTS['synthetic_chatgpt']],'Stale audit')
    rows=check_review(root,initial['real_wikimedia'],report,review,AUDIT_SHA)
    new={m.REGISTRY:update_workbook(old[m.REGISTRY],rows,AUDIT_SHA,REVIEW_SHA),
         ATTR:attribution(rows)}
    new[THIRD]=document(old[THIRD], '# Wikimedia retail images — current evidence (2026-11-24)',
        '100/100 local JPEGs match Commons thumbnails. API-reported authors: 100; licenses: '+', '.join(f'{k}: {v}' for k,v in sorted(COUNTS.items()))+'.\n\nSee [ATTRIBUTION.md](ATTRIBUTION.md) and the Commons API sheet in the Excel registry. The following historical notice is preserved but its former license/author counts and verification status are superseded. Record 004: CC BY-SA 4.0 reported instead of CC0; record 100: Andy Li instead of Andy Li (Onthewings). Both remain flagged for manual review. No publication approval.')
    new[m.SYNTHETIC_DOC]=document(old[m.SYNTHETIC_DOC], '# ChatGPT synthetic collection — current policy (2026-11-24)',
        '100 synthetic images. Generated using ChatGPT (OpenAI) under the direction of the BVT-Studio author. No blanket image license is assigned. Code licensing does not cover these images automatically. Account terms, third-party rights, packaging and trademarks require review before publication; no publication approval, ground truth or verified annotation is implied.')
    old_sentence = ('The real collection records individual Creative Commons licenses: 11 entries are recorded as page-reviewed and 89 require individual review and author information. Binary correspondence of record 99 to its Wikimedia source remains pending (stage 14).')
    doc = old[DOC_README].decode('utf-8')
    need(doc.count(old_sentence)==1,'Unexpected provenance README version')
    new[DOC_README]=doc.replace(old_sentence, 'The stage 14 API audit established exact thumbnail SHA-256 matches for all 100 JPEGs and obtained 100 author declarations and license candidates. Two records remain flagged for metadata discrepancies; all rights-review decisions remain pending. See [ATTRIBUTION.md](ATTRIBUTION.md) and the current Excel API sheet.').encode('utf-8')
    latest=m.build(root,source,registry_data=new[m.REGISTRY],synthetic_data=new[m.SYNTHETIC_DOC])
    allowed={'author','license_id','license_url','license_verification_status','license_checked_at','license_evidence_url','source_url','attribution_text','source_registry_version'}
    for collection,path in MANIFESTS.items():
        for before,after in zip(initial[collection],latest[collection]):
            permitted=allowed if collection=='real_wikimedia' else {'source_registry_version'}
            need({k for k in before if before[k]!=after[k]}<=permitted,'Unexpected manifest mutation')
        new[path]=m.encode(latest[collection])
    # All validation precedes writes; all working inputs remain unchanged.
    output.mkdir(exist_ok=False)
    for name,files in [('before',old),('after',new)]:
        for p,data in files.items():
            dest=output/name/p; dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as f: f.write(data)
    ledger={p.as_posix():{'before':digest(old[p]) if p in old else None,'after':digest(data)} for p,data in new.items()}
    (output/'migration.json').write_text(json.dumps(ledger,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    need(all(digest((output/'after'/p).read_bytes())==digest(data) for p,data in new.items()),'Staged output mismatch')
    need(all(a.safe_path(root,p).read_bytes()==data for p,data in old.items()),'Working metadata changed')
    print('STAGED_REAL_AUTHORS=100\nSTAGED_METADATA_MATCHES=98\nSTAGED_MANUAL_REVIEW=2\nREADY_FOR_PUBLICATION=0')
    print('WORKING_METADATA_UNCHANGED=PASS\nPROVENANCE_UPDATE_STAGED=PASS')
    print('BUNDLE='+str(output.relative_to(root)))
    print('MIGRATION_SHA256='+digest((output/'migration.json').read_bytes()))
    return ledger


def replace_bytes(path, data):
    # Atomic per-file replacement. The complete multi-file operation needs no
    # concurrent writers; backups remain available after a process interruption.
    fd, temp = tempfile.mkstemp(prefix='.bvt-metadata-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def promote(root, source, approved_sha):
    root=Path(root).resolve(); bundle=BASE+'commons-update-001/'
    ledger_bytes=a.safe_path(root,bundle+'migration.json').read_bytes()
    need(digest(ledger_bytes)==approved_sha,'Migration approval SHA mismatch')
    ledger=json.loads(ledger_bytes)
    expected=set(BASELINE)|{DOC_README,ATTR}
    need(set(ledger)=={p.as_posix() for p in expected},'Unexpected migration paths')
    before={}; after={}
    for p in sorted(expected):
        entry=ledger[p.as_posix()]; target=a.safe_path(root,p)
        if p==ATTR:
            need(entry['before'] is None and not target.exists(),'Unexpected existing attribution')
        else:
            old=a.safe_path(root,bundle+'before/'+p.as_posix()).read_bytes()
            need(digest(old)==entry['before'] and target.read_bytes()==old,'Working metadata differs from backup: '+str(p))
            if p in BASELINE: need(entry['before']==BASELINE[p],'Unexpected original metadata SHA')
            before[p]=old
        data=a.safe_path(root,bundle+'after/'+p.as_posix()).read_bytes()
        need(digest(data)==entry['after'],'Staged file SHA mismatch: '+str(p))
        after[p]=data
    current=m.build(root,source)
    proposed=m.build(root,source,registry_data=after[m.REGISTRY],synthetic_data=after[m.SYNTHETIC_DOC])
    for collection,p in MANIFESTS.items():
        need(m.encode(current[collection])==before[p] and m.encode(proposed[collection])==after[p],'Manifest regeneration mismatch')
        allowed={'author','license_id','license_url','license_verification_status','license_checked_at','license_evidence_url','source_url','attribution_text','source_registry_version'} if collection=='real_wikimedia' else {'source_registry_version'}
        for old,new in zip(current[collection],proposed[collection]):
            need({k for k in old if old[k]!=new[k]}<=allowed,'Unexpected manifest change')
    real=proposed['real_wikimedia']
    need(Counter(r['license_id'] for r in real)==COUNTS and all(r['author'] for r in real),'Unexpected updated metadata')
    need({r['image_id'] for r in real if r['license_verification_status']=='manual_review_required'}==set(CONFLICTS),'Unexpected review flags')
    need(all(r['license_verification_status']=='api_evidence_recorded' for r in real if r['image_id'] not in CONFLICTS),'Unexpected evidence status')
    changed=[]
    try:
        for p in sorted(expected):
            target=a.safe_path(root,p)
            need(target.read_bytes()==before[p] if p in before else not target.exists(),'Concurrent metadata change')
            replace_bytes(target,after[p]); changed.append(p)
        need(all(a.safe_path(root,p).read_bytes()==after[p] for p in expected),'Promotion verification failed')
    except Exception:
        for p in reversed(changed):
            target=a.safe_path(root,p)
            if p in before: replace_bytes(target,before[p])
            else: target.unlink()
        raise
    print('PROMOTED_METADATA_FILES=7\nBACKUPS_RETAINED=PASS\nREADY_FOR_PUBLICATION=0\nPROVENANCE_UPDATE_PROMOTED=PASS')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-copy',required=True,type=Path)
    parser.add_argument('--promote',metavar='REVIEWED_MIGRATION_SHA256',help='Explicitly promote a previously inspected bundle')
    args=parser.parse_args()
    if args.promote: promote(m.ROOT,args.source_copy,args.promote)
    else: stage(m.ROOT,args.source_copy)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
