"""Verify the fixed stage-0 corpus, independently of any future product parser.

Offline by default. --online checks current ASX links without changing snapshots.
--require-human exits 2 if actual human sign-off is still outstanding.
No application imports, database writes, paid model calls or product UI changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/beta02-acceptance/samples.json'


def normalized(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def verify(manifest: Path = MANIFEST, online: bool = False) -> dict:
    data = json.loads(manifest.read_text(encoding='utf-8'))
    result = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'dataset_version': data['dataset_version'], 'online': online,
              'errors': [], 'pending_human_review': [], 'samples': []}
    errors = result['errors']
    samples = data['samples']
    ids, source_ids, families = set(), set(), set()
    if len(samples) < 8:
        errors.append('At least eight source samples are required')
    for sample in samples:
        sid = sample['sample_id']
        if sid in ids or sample['asx_announcement_id'] in source_ids:
            errors.append(f'{sid}: duplicate sample/source ID')
        ids.add(sid)
        source_ids.add(sample['asx_announcement_id'])
        for field in ('ticker', 'headline', 'asx_announcement_id', 'pdf_url',
                      'document_type', 'facts', 'must_not', 'sha256', 'source_review'):
            if not sample.get(field):
                errors.append(f'{sid}: missing {field}')
        expected = sample['expected_events']
        families.update(event['family'] for event in expected)
        if expected and not sample['summary_region']:
            errors.append(f'{sid}: core default events without a defined summary region')
        for event in expected:
            if not re.fullmatch(r'F0[1-8]', event['family']) or not event['event_type'] or not event['status']:
                errors.append(f'{sid}: invalid expected event')
        review = sample['human_review']
        if review['status'] != 'confirmed':
            result['pending_human_review'].append(sid)
        elif not review.get('reviewer') or not review.get('reviewed_at'):
            errors.append(f'{sid}: confirmed status lacks actual reviewer/date')
        path = (manifest.parent / sample['local_pdf']).resolve()
        if not path.is_relative_to(manifest.parent.resolve()) or not path.is_file():
            errors.append(f'{sid}: missing or out-of-corpus PDF')
            continue
        content = path.read_bytes()
        if not content.startswith(b'%PDF') or hashlib.sha256(content).hexdigest() != sample['sha256']:
            errors.append(f'{sid}: PDF signature/hash mismatch')
            continue
        reader = PdfReader(path)
        if len(reader.pages) != sample['page_count'] or len(content) != sample['bytes']:
            errors.append(f'{sid}: page count/byte count mismatch')
        seen_facts = set()
        page_texts = {}
        for fact in sample['facts']:
            fid = fact['fact_id']
            if fid in seen_facts:
                errors.append(f'{sid}: duplicate fact {fid}')
            seen_facts.add(fid)
            page = fact['pdf_page']
            if not 1 <= page <= len(reader.pages):
                errors.append(f'{fid}: invalid physical page')
                continue
            if page not in page_texts:
                page_texts[page] = normalized(reader.pages[page - 1].extract_text() or '')
            if normalized(fact['source_excerpt']) not in page_texts[page]:
                errors.append(f'{fid}: source excerpt not found on cited page')
            if fact['scope'] not in {'summary', 'reference_only', 'routing_only'}:
                errors.append(f'{fid}: unknown scope')
            if fact['required_in_pilot'] != (fact['scope'] == 'summary'):
                errors.append(f'{fid}: extraction scope mismatch')
            if fact['scope'] == 'summary' and not sample['summary_region']:
                errors.append(f'{fid}: summary fact without summary')
            if not fact['location'] or fact['expected_value'] is None or fact['origin'] != 'reported':
                errors.append(f'{fid}: incomplete or non-reported expectation')
        check = {'sample_id': sid, 'local_pdf': sample['local_pdf'],
                 'sha256': sample['sha256'], 'fact_count': len(sample['facts']),
                 'frozen_source_http_status': sample['http_status'],
                 'frozen_source_checked_at': sample['checked_at']}
        if online:
            import httpx

            try:
                response = httpx.get(sample['pdf_url'], follow_redirects=True, timeout=45)
                response.raise_for_status()
                if not response.content.startswith(b'%PDF'):
                    raise ValueError('Link returned a non-PDF response')
                # Some gateways regenerate PDF metadata. Keep raw and text hashes
                # distinct; never overwrite the fixed bytes when the gateway changes.
                from io import BytesIO

                live_reader = PdfReader(BytesIO(response.content))
                check.update(http_status=response.status_code,
                             live_page_count=len(live_reader.pages),
                             live_sha256=hashlib.sha256(response.content).hexdigest())
                check['byte_identical'] = check['live_sha256'] == sample['sha256']
                live_text = [normalized(page.extract_text() or '') for page in live_reader.pages]
                frozen_text = [normalized(page.extract_text() or '') for page in reader.pages]
                check['text_identical'] = live_text == frozen_text
                if not check['text_identical']:
                    errors.append(f'{sid}: live PDF text changed; review as a new source version')
            except Exception as exc:
                errors.append(f'{sid}: online link check failed: {type(exc).__name__}: {exc}')
        result['samples'].append(check)
    required_families = {f'F0{i}' for i in range(1, 9)}
    if families != required_families:
        errors.append(f'F01-F08 default-summary event coverage mismatch: {sorted(families)}')
    if not any(s.get('non_core_bucket') and not s['expected_events'] for s in samples):
        errors.append('Missing non-core negative-routing sample')
    if not any('Appendix 5B' in s['document_type'] for s in samples):
        errors.append('Missing quarterly / Appendix 5B sample')
    result['families'] = sorted(families)
    result['technical_checks_passed'] = not errors
    result['human_acceptance_passed'] = not result['pending_human_review'] and not errors
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--require-human', action='store_true')
    parser.add_argument('--report', type=Path, help='Optional new report path; never overwrites an existing report')
    args = parser.parse_args()
    result = verify(online=args.online)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if result['errors']:
        return 1
    if args.require_human and not result['human_acceptance_passed']:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
