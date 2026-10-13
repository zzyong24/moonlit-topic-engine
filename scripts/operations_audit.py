#!/usr/bin/env python3
"""Read-only operational evidence audit. No network, scoring, or metadata mutations."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import re
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def stamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def rate(metrics, numerator):
    denominator, value = metrics.get('views'), metrics.get(numerator)
    if (type(denominator) not in (int, float) or denominator <= 0
            or type(value) not in (int, float) or value < 0):
        return None
    return {'numerator': value, 'denominator': denominator, 'value': value / denominator}


def audit(root, account, data_root, as_of):
    root, data_root = Path(root).resolve(), Path(data_root).resolve()
    now = stamp(as_of)
    if not now:
        raise ValueError('as-of must contain a timezone')
    if not account or '/' in account or account in ('.', '..'):
        raise ValueError('explicit account alias required')
    marker = data_root / '_account.json'
    if not marker.is_file() or read(marker).get('accountId') != account:
        raise ValueError('data-root must have the matching account ownership marker')
    index = read(data_root / '_index.json')
    if index.get('accountId') != account:
        raise ValueError('index account mismatch')
    gaps, work_rows, owners = [], [], defaultdict(set)
    for path in sorted((root / 'works').glob('20*/W-*/work.json')):
        work = read(path)
        wid = work.get('id')
        if not wid:
            gaps.append({'kind': 'work_without_id', 'path': str(path)})
            continue
        work_rows.append({'work_id': wid, 'title': work.get('title'), 'status': work.get('status')})
        ids = work.get('platformIds', {}).get('douyin', [])
        ids += work.get('distributionIds', {}).get('douyin', [])
        for value in ids:
            owners[str(value)].add(wid)
        releases = path.parent / 'distribution/releases.json'
        if releases.is_file():
            ledger = read(releases)
            if ledger.get('workId', wid) != wid:
                gaps.append({'kind': 'foreign_release_ledger', 'path': str(releases)})
            else:
                for event in ledger.get('records', []):
                    if (event.get('platform', event.get('channel')) != 'douyin'
                            or event.get('accountId', account) != account):
                        continue
                    value = event.get('platformPostId') or event.get('awemeId')
                    match = re.fullmatch(r'https://www\.douyin\.com/video/(\d+)(?:\?.*)?',
                                         event.get('publicUrl') or '')
                    if value or match:
                        owners[str(value or match.group(1))].add(wid)
        # The actual account-specific distribution directory is also stable-ID evidence.
        for child in (path.parent / 'distribution/douyin' / account).glob('*'):
            if child.is_dir() and child.name.isdigit():
                owners[child.name].add(wid)

    entries = {}
    for row in index.get('works', []):
        ident = str(row.get('awemeId', ''))
        if not ident:
            gaps.append({'kind': 'index_without_platform_id'})
            continue
        if ident in entries:
            gaps.append({'kind': 'duplicate_index_id', 'publication_id': ident})
        entries[ident] = row
        linked = row.get('path')
        if not linked or not (data_root / linked).is_dir():
            gaps.append({'kind': 'broken_index_path', 'publication_id': ident, 'path': linked})

    files = set(p.resolve() for p in data_root.glob('**/metrics.json'))
    files.update(p.resolve() for p in (root / 'works').glob(
        '20*/W-*/distribution/douyin/' + account + '/*/metrics.json'))
    snapshots, metas, comments = defaultdict(dict), {}, {}
    for path in sorted(files):
        payload = read(path)
        ident = str(payload.get('awemeId', path.parent.name))
        meta_path = path.with_name('meta.json')
        meta = read(meta_path) if meta_path.is_file() else {}
        if meta.get('accountId', account) != account:
            gaps.append({'kind': 'foreign_account_record', 'path': str(path)})
            continue
        if str(meta.get('awemeId', ident)) != ident:
            gaps.append({'kind': 'platform_id_mismatch', 'path': str(path)})
            continue
        if stamp(meta.get('publishedAt')):
            metas[ident] = meta
        comment_path = path.with_name('comments.json')
        if comment_path.is_file():
            c = read(comment_path)
            if stamp(c.get('collectedAt')) and stamp(c['collectedAt']) <= now:
                old = comments.get(ident)
                if old is None or stamp(c['collectedAt']) > stamp(old['collectedAt']):
                    comments[ident] = c
        for sample in [*payload.get('history', []), payload.get('latest')]:
            if not isinstance(sample, dict):
                continue
            captured = stamp(sample.get('capturedAt'))
            if not captured or captured > now:
                gaps.append({'kind': 'invalid_or_future_capture', 'publication_id': ident})
                continue
            if str(sample.get('awemeId', ident)) != ident:
                gaps.append({'kind': 'snapshot_id_mismatch', 'publication_id': ident})
                continue
            source = sample.get('source')
            if not source:
                gaps.append({'kind': 'unknown_metric_source', 'publication_id': ident})
            key = (captured.isoformat(), source)
            metrics = sample.get('metrics') or {}
            if key in snapshots[ident] and snapshots[ident][key]['metrics'] != metrics:
                gaps.append({'kind': 'conflicting_snapshot', 'publication_id': ident,
                             'captured_at': captured.isoformat()})
                # Conflicting duplicates are excluded rather than resolved arbitrarily.
                snapshots[ident][key]['conflicted'] = True
            else:
                snapshots[ident].setdefault(key, {'captured_at': captured.isoformat(),
                    'source': source, 'metrics': metrics, 'evidence_path': str(path)})

    rows = []
    windows = {24: 6, 72: 12, 168: 24}
    for ident in sorted(set(entries) | set(snapshots)):
        samples = sorted((s for s in snapshots[ident].values() if not s.get('conflicted')),
                         key=lambda s: s['captured_at'])
        row = entries.get(ident, {})
        published = stamp(metas.get(ident, {}).get('publishedAt') or row.get('publishedAt'))
        owner = sorted(owners.get(ident, []))
        if len(owner) != 1:
            gaps.append({'kind': 'unmapped' if not owner else 'ambiguous_work_mapping',
                         'publication_id': ident, 'work_ids': owner})
        observations = {}
        for target, tolerance in windows.items():
            eligible = [(abs((stamp(s['captured_at']) - published).total_seconds()/3600 - target), s)
                        for s in samples if published and s['source'] and
                        abs((stamp(s['captured_at']) - published).total_seconds()/3600 - target) <= tolerance]
            chosen = min(eligible, key=lambda item: item[0])[1] if eligible else None
            observations[str(target)] = {'status': 'observed' if chosen else 'missing',
                'tolerance_hours': tolerance,
                'age_hours': round((stamp(chosen['captured_at']) - published).total_seconds()/3600, 2) if chosen else None,
                'snapshot': chosen}
        latest = samples[-1] if samples else None
        c = comments.get(ident)
        rows.append({'account_id': account, 'platform': 'douyin', 'publication_id': ident,
            'work_id': owner[0] if len(owner) == 1 else None,
            'title': row.get('title') or metas.get(ident, {}).get('title'),
            'published_at': published.isoformat() if published else None,
            'latest': latest, 'snapshot_count': len(samples), 'windows': observations,
            'favorites_per_view': rate(latest['metrics'], 'favorites') if latest else None,
            'shares_per_view': rate(latest['metrics'], 'shares') if latest else None,
            'comments': {'captured_at': c['collectedAt'], 'count': len(c.get('items', [])),
                         'incomplete': c.get('incomplete')} if c else None})
    newest = max((stamp(r['latest']['captured_at']) for r in rows if r['latest']), default=None)
    return {'schema_version': 1, 'as_of': now.isoformat(), 'account_id': account,
        'data_root': str(data_root), 'work_count': len(work_rows),
        'work_status_counts': dict(Counter(w['status'] for w in work_rows)),
        'publication_count': len(rows), 'mapped_publications': sum(bool(r['work_id']) for r in rows),
        'latest_capture_at': newest.isoformat() if newest else None,
        'newest_data_age_hours': round((now-newest).total_seconds()/3600, 2) if newest else None,
        'metric_keys': sorted({k for r in rows if r['latest'] for k in r['latest']['metrics']}),
        'window_coverage': {str(w): sum(r['windows'][str(w)]['status']=='observed' for r in rows) for w in windows},
        'gap_counts': dict(Counter(g['kind'] for g in gaps)), 'gaps': gaps, 'publications': rows,
        'notice': 'Coverage projection only; no causal claims or content-quality ranking.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'account', 'data-root', 'as-of', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    report = audit(args.root, args.account, args.data_root, args.as_of)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(output.suffix + '.tmp')
    pending.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(output)
    print(json.dumps({k: v for k, v in report.items() if k not in ('publications', 'gaps')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
