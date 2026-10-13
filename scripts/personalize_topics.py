#!/usr/bin/env python3
"""Explicit local context assembly and evidence-backed editorial routing. No model/network."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re

WEIGHTS = {'interest': 15, 'audience_value': 20, 'author_basis': 20,
           'recordability': 20, 'distinctiveness': 15, 'lasting_value': 10}
ATTRIBUTIONS = {'user_statement', 'observed', 'external', 'agent_proposal', 'unknown'}

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)

def norm(text):
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', text.lower())

def local_path(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Local evidence must remain in the selected workspace')
    return path

def assemble(root, config, day, memory=None, max_chars=50000):
    root = Path(root).resolve(); today = dt.date.fromisoformat(day)
    pack = {'schema_version': 1, 'date': day, 'profile': read(local_path(root, config['profile'])),
            'preferences': config['preferences'], 'production': config['production'],
            'themes': config['themes'], 'sources': config['sources'], 'evidence': [],
            'paired_grids': config.get('paired_grids'),
            'selection_method': config.get('selection_method', {}),
            'visualization_policy': config.get('visualization_policy', {}),
            'recent_works': [], 'recent_topics': [], 'gaps': [], 'memory_versions': [],
            'feedback': [],
            'dedup_complete': False, 'notice': 'Local snapshot, not a verified personality profile.'}
    for ref in config.get('evidence', []):
        if ref['attribution'] not in ATTRIBUTIONS:
            raise ValueError('Unknown evidence attribution')
        path = local_path(root, ref['path'])
        row = dict(ref)
        if path.is_file():
            blob = path.read_bytes()
            row.update(status='available', sha256=hashlib.sha256(blob).hexdigest())
        else:
            row['status'] = 'missing'; pack['gaps'].append('missing:' + ref['id'])
        # The curated summary preserves provenance; arbitrary document text is not injected.
        pack['evidence'].append(row)
    if memory:
        allowed = set(config.get('memory_scope', {}).get('project_keys', []))
        seen = set()
        for exported in memory:
            if exported.get('project_key') not in allowed:
                raise ValueError('Memory project is outside the explicit scope')
            if exported.get('omitted_ids'):
                pack['gaps'].append('memory_omitted:' + ','.join(exported['omitted_ids']))
            if exported.get('missing_ids'):
                pack['gaps'].append('memory_missing:' + ','.join(exported['missing_ids']))
            if exported.get('candidate_limit_reached') is True:
                pack['gaps'].append('memory_candidate_limit_reached:' + exported['project_key'])
            if exported.get('unknown') is True:
                pack['gaps'].append('memory_unknown:' + exported['project_key'])
            for card in exported.get('contexts', []):
                key = (card['id'], card['version'])
                if key in seen: continue
                seen.add(key)
                if card.get('project_key') not in allowed:
                    raise ValueError('Cross-project context detected')
                permitted = config['memory_scope'].get('context_ids')
                if permitted and card['id'] not in permitted:
                    raise ValueError('Context ID is outside the explicit scope')
                if card.get('status') != 'active': continue
                expires = card.get('valid_until')
                if expires:
                    expiration = (dt.datetime.fromtimestamp(expires, dt.timezone.utc) if type(expires) in (int, float)
                                  else dt.datetime.fromisoformat(expires.replace('Z', '+00:00')))
                    if expiration.date() < today:
                        pack['gaps'].append('expired:' + card['id']); continue
                framework = card.get('payload', {}).get('framework')
                if not framework: continue
                if framework['kind'] not in config['memory_scope']['frameworks']: continue
                eid = f"context:{card['id']}@v{card['version']}"
                pack['evidence'].append({'id': eid, 'status': 'available', 'attribution': 'agent_proposal',
                    'kind': framework['kind'], 'framework': framework,
                    'sources': card['payload'].get('sources', []), 'source_uri': card.get('source_uri'),
                    'constraints': card['payload'].get('constraints', []),
                    'uncertainties': card['payload'].get('uncertainties', [])})
                pack['memory_versions'].append({'id': card['id'], 'version': card['version'],
                                               'project_key': card['project_key']})
    else:
        pack['gaps'].append('memory_not_recalled')
    index = root/'works/index.json'
    for row in read(index).get('works', []) if index.is_file() else []:
        try: age = (today - dt.date.fromisoformat(row['createdAt'][:10])).days
        except (ValueError, KeyError): continue
        if not 0 <= age <= 30: continue
        meta = local_path(root, row['path'])/'work.json'
        data = read(meta) if meta.is_file() else {}
        pack['recent_works'].append({'id': row['id'], 'title': row['title'],
            'thesis': data.get('thesis'), 'date': row['createdAt'], 'status': row.get('status'),
            'path': row['path'], 'artifacts': list(data.get('artifacts', {})),
            'distribution_status': row.get('distributionStatus', {}), 'case_review': 'not_checked'})
    for path in sorted((root/'topics').glob('*/*/topics.json')):
        data = read(path)
        try: age = (today-dt.date.fromisoformat(data['date'])).days
        except (ValueError, KeyError): continue
        if not 0 <= age <= 30: continue
        pack['recent_topics'].extend({'id': r['id'], 'title': r['title'], 'status': r['status'],
            'thesis': r.get('candidate', {}).get('core_thesis'), 'workId': r.get('workId'),
            'candidate_id': r.get('candidate', {}).get('id')}
            for r in data.get('topics', []))
    pack['gaps'].append('Recent metadata loaded; full thesis/case/feedback semantic dedup still required.')
    feedback = local_path(root, config.get('feedback_path', 'topics/selection-feedback.jsonl'))
    if feedback.is_file():
        pack['feedback'] = [json.loads(line) for line in feedback.read_text(encoding='utf-8').splitlines() if line.strip()][-50:]
    else:
        pack['gaps'].append('No accumulated selection feedback yet; weights are initial editorial settings.')
    ids = [x['id'] for x in pack['evidence']]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate evidence IDs')
    # Whole entries only. Constraints/preferences are never silently cut to meet the budget.
    size = len(json.dumps(pack, ensure_ascii=False))
    if size > max_chars:
        raise ValueError(f'Context budget exceeded ({size}>{max_chars}); select fewer evidence entries explicitly')
    pack['context_hash'] = hashlib.sha256(json.dumps(pack, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return pack

def feedback(root, topic_id, outcome, reason, day):
    root = Path(root).resolve(); dt.date.fromisoformat(day)
    if outcome not in {'can_explain', 'not_interested', 'too_hard', 'duplicate', 'test_completed', 'needs_material',
                       'audience_mismatch', 'entry_unavailable'}:
        raise ValueError('Unknown selection feedback outcome')
    if not reason.strip(): raise ValueError('Feedback needs a concrete reason')
    found = any(topic_id == topic['id'] for p in (root/'topics').glob('*/*/topics.json')
                for topic in read(p).get('topics', []))
    if not found: raise ValueError('Unknown topic ID; import candidates first')
    event = {'topic_id': topic_id, 'outcome': outcome, 'reason': reason, 'date': day,
             'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat(),
             'attribution': 'user_statement', 'notice': 'Selection feedback, not verified publication results.'}
    path=root/'topics/selection-feedback.jsonl'
    # One append per invocation. No profile edits or implicit weight changes.
    with path.open('a', encoding='utf-8') as stream: stream.write(json.dumps(event, ensure_ascii=False)+'\n')
    return {'output': str(path), 'topic_id': topic_id, 'outcome': outcome}

def audience_gate(pack, review, evidence, refs):
    """Validate an explicit model/author verdict; never infer meaning from words or titles."""
    contract = pack.get('profile', {}).get('audience_contract', {})
    if contract.get('practical_required') is not True:
        return 'not_required', []
    audit = review.get('audience_review')
    if not audit:
        return 'unknown', ['Current audience/task review is missing']
    if audit.get('contract_version') != contract.get('version'):
        raise ValueError('Audience contract changed; review the current audience again')
    for key in ['audience_fit', 'practical_fit']:
        if audit.get(key) not in {'pass', 'fail', 'unknown'}:
            raise ValueError('Explicit audience and practical-task verdicts required')
    if 'fail' in {audit['audience_fit'], audit['practical_fit']}:
        return 'fail', ['Audience/practical-task mismatch: ' + str(audit.get('reason', ''))]
    if not audit.get('reason') or 'unknown' in {audit['audience_fit'], audit['practical_fit']}:
        return 'unknown', ['Audience or practical-task fit remains unknown']
    required = ['viewer_task', 'input', 'output', 'verification']
    if not all(isinstance(audit.get(k), str) and audit[k].strip() for k in required):
        return 'unknown', ['Viewer task/input/output/verification is incomplete']
    if not isinstance(audit.get('steps'), list) or not audit['steps'] or not all(
            isinstance(step, str) and step.strip() for step in audit['steps']):
        return 'unknown', ['Viewer steps are incomplete']
    basis = audit.get('demand_basis', {})
    if basis.get('kind') not in {'user_request', 'observed_question', 'agent_hypothesis'} or not basis.get('detail'):
        raise ValueError('Demand must distinguish a sourced request/question from a hypothesis')
    if basis['kind'] != 'agent_hypothesis':
        demand_refs = basis.get('evidence_ids', [])
        if not demand_refs or any(ref not in refs or ref not in evidence for ref in demand_refs):
            raise ValueError('Claimed demand must cite available evidence in this review')
        if basis['kind'] == 'observed_question' and any(
                evidence[ref].get('kind') != 'audience_question' or
                evidence[ref].get('attribution') not in {'observed', 'external', 'user_statement'} for ref in demand_refs):
            raise ValueError('Observed questions need actual question material, not a framework/proposal')
    entry = audit.get('viewer_entry', {})
    if not all(isinstance(entry.get(k), str) and entry[k].strip() for k in
               ['instructions', 'prerequisites', 'cost', 'language']):
        return 'unknown', ['Viewer entry conditions are incomplete']
    if entry.get('status') == 'verified':
        return 'pass', []
    if entry.get('status') == 'planned' and isinstance(entry.get('test_actions'), list) and entry['test_actions']:
        return 'planned', ['Viewer entry still needs its explicit test']
    return 'unknown', ['Author access does not prove a usable viewer entry']

def rank(pack, candidates, reviews, count=3):
    ids = [x['id'] for x in candidates]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate candidate IDs')
    review_ids = [x['candidate_id'] for x in reviews]
    if len(review_ids) != len(set(review_ids)) or not set(review_ids) <= set(ids):
        raise ValueError('Invalid/duplicate review candidate IDs')
    if any(r.get('context_hash') != pack['context_hash'] for r in reviews):
        raise ValueError('Review refers to stale or different context; review again')
    evidence = {x['id']: x for x in pack['evidence'] if x['status'] == 'available'}
    lookup = {x['candidate_id']: x for x in reviews}; result = []
    historical = {norm(r['thesis']) for r in pack['recent_works'] if r.get('thesis')}
    budget = pack['production']['prep_minutes']
    for candidate in candidates:
        row = dict(candidate); review = lookup.get(candidate['id'])
        if review is None:
            result.append(dict(row, match_queue='unreviewed', match_score=None,
                               next_action='Read evidence and complete semantic review.')); continue
        refs = review.get('evidence_ids', [])
        if not refs or any(ref not in evidence for ref in refs):
            raise ValueError('Review must cite available context evidence IDs')
        if not review.get('reviewer') or not review.get('checked_at'):
            raise ValueError('Review needs reviewer and date')
        fit = review.get('fit_decision')
        if fit not in {'relevant', 'explore', 'mismatch', 'unknown'}:
            raise ValueError('Explicit task/author fit decision required')
        scores = review.get('dimensions', {})
        if set(scores) != set(WEIGHTS): raise ValueError('Six editorial dimensions required')
        points = 0
        for name, weight in WEIGHTS.items():
            dim = scores[name]; value = dim.get('value')
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 5 or not dim.get('reason'):
                raise ValueError('Each dimension needs a finite 0..5 score and evidence-based reason')
            points += value * weight / 5
        premise = review.get('core_thesis') or candidate.get('core_thesis', '')
        duplicate = review.get('duplicate_status')
        if duplicate not in {'new', 'substantive_update', 'duplicate', 'unknown'}:
            raise ValueError('Explicit semantic duplicate judgment required')
        exact = bool(premise and norm(premise) in historical)
        existing = [t['id'] for t in pack.get('recent_topics', []) if t.get('thesis')
                    and norm(t['thesis']) == norm(premise) and t.get('candidate_id') != candidate['id']
                    and t.get('status') in {'recommended', 'picking', 'picked'}]
        rejected = [t['id'] for t in pack.get('recent_topics', []) if t.get('thesis')
                    and norm(t['thesis']) == norm(premise) and t.get('status') == 'rejected']
        if duplicate == 'substantive_update' and not review.get('changed_evidence'):
            raise ValueError('Substantive update needs changed evidence, not a new title')
        plan = review.get('production_plan', {})
        minutes = plan.get('prep_minutes')
        if minutes is not None and (type(minutes) not in (int, float) or not math.isfinite(minutes) or minutes < 0):
            raise ValueError('Invalid preparation minutes')
        ready = review.get('evidence_state') == 'ready' and review.get('facts_checked') is True
        basis = review.get('author_basis_evidence_ids', [])
        own_basis = bool(basis) and all(ref in refs and evidence[ref]['attribution'] in {'observed', 'user_statement'}
                                        and evidence[ref].get('kind') in {'direct_asset', 'project_record', 'user_experience'} for ref in basis)
        if ready and not own_basis:
            raise ValueError('Ready-to-record requires available first-hand basis, not benchmark/proposal')
        if candidate.get('theme_id') not in {x['id'] for x in pack['themes']}:
            raise ValueError('Unknown theme ID')
        pair = candidate.get('grid_pair')
        method = pack.get('selection_method', {})
        if method.get('mode') == 'paired_grids' and method.get('require_grid_pair') is True and not pair:
            raise ValueError('Current selection method requires a grid relation')
        if pair is not None:
            if not isinstance(pair, dict):
                raise ValueError('Grid relation must be an explicit object')
            grids = pack.get('paired_grids') or {}
            reason = pair.get('relation_reason')
            if pair.get('grid_version') != grids.get('version') or not isinstance(reason, str) or not reason.strip():
                raise ValueError('Grid relation needs the current version and an explicit reason')
            for role, key in [('audience', 'audience_cell_id'), ('industry', 'capability_cell_id')]:
                if pair.get(key) not in {cell['id'] for cell in grids.get(role, {}).get('cells', [])}:
                    raise ValueError('Grid relation refers to a missing/wrong-role cell')
        for link in review.get('memory_links', []):
            key = f"context:{link['context_id']}@v{link['version']}"
            if key not in refs or key not in evidence:
                raise ValueError('Memory link must cite the recalled card/version')
            framework = evidence[key].get('framework', {})
            if framework.get('kind') == 'life_map' and link.get('event_id') not in {e['id'] for e in framework.get('events', [])}:
                raise ValueError('Life-map link needs a real event ID, not a grid slot')
            if framework.get('kind') == 'topic_grid' and link.get('slot') not in {c['slot'] for c in framework.get('cells', [])}:
                raise ValueError('Topic-grid link needs a real surrounding slot')
        actionable = all(plan.get(k) for k in ['task', 'steps', 'visible_result', 'done_when', 'opening', 'format'])
        audience, reasons = audience_gate(pack, review, evidence, refs)
        if fit == 'mismatch' or review.get('audience_mismatch') is True or duplicate == 'duplicate' or (exact and duplicate != 'substantive_update'):
            queue = 'skip'; reasons.append('Audience mismatch or repeated thesis')
        elif audience == 'fail':
            queue = 'skip'
        elif rejected and duplicate != 'substantive_update':
            queue = 'skip'; reasons.append('Previously rejected thesis needs substantive changes: ' + ','.join(rejected))
        elif existing and duplicate != 'substantive_update':
            queue = 'existing_pool'; reasons.append('Already in topic pool: ' + ','.join(existing))
        elif fit == 'unknown' or audience == 'unknown':
            queue = 'observe'; reasons.append('Author/task fit has not been resolved')
        elif not actionable or minutes is None or plan.get('access_ready') is not True:
            queue = 'observe'; reasons.append('Preparation/action/access not sufficiently known')
        elif minutes > budget:
            queue = 'deep_build'; reasons.append('Exceeds current preparation budget')
        elif audience == 'planned' and review.get('evidence_state') in {'ready', 'planned'}:
            queue = 'test_first'
        elif ready:
            queue = 'record_candidate'
        elif review.get('evidence_state') == 'planned':
            queue = 'test_first'
        else:
            queue = 'observe'; reasons.append('Evidence not ready; plan incomplete')
        if pack.get('dedup_complete') is not True or duplicate == 'unknown':
            points = min(points, 79); reasons.append('Full recent-content dedup incomplete; capped at 79')
        row.update(core_thesis=premise, match_queue=queue, match_score=round(points, 2),
            match_review=review, match_limits=reasons, production_plan=plan,
            next_action=review.get('next_action', plan.get('task')), status='recommended',
            recommendation_label='tentative', evidence_status=review.get('evidence_state'),
            audience_gate=audience,
            memory_links=review.get('memory_links', []), benchmark_links=review.get('benchmark_links', []))
        result.append(row)
    priorities = {'record_candidate': 0, 'test_first': 1, 'deep_build': 2, 'observe': 3, 'existing_pool': 4, 'unreviewed': 5, 'skip': 6}
    result.sort(key=lambda r: (priorities[r['match_queue']], -(r['match_score'] or 0), r['id']))
    # Diversify by theme/claim family, not platform or title. Quotas are editorial experiment settings.
    picked = []; themes = {}; families = set(); per_theme = pack['preferences'].get('max_per_theme', 2)
    for row in result:
        if row['match_queue'] not in {'record_candidate', 'test_first'}: continue
        theme = row.get('theme_id', 'unknown'); family = row.get('claim_family', row['id'])
        if themes.get(theme, 0) >= per_theme or family in families: continue
        picked.append(row['id']); themes[theme] = themes.get(theme, 0)+1; families.add(family)
        if len(picked) == count: break
    return {'schema_version': 1, 'context_hash': pack['context_hash'], 'date': pack['date'],
            'shortlist': picked, 'candidates': result, 'gaps': pack['gaps'],
            'notice': 'Editorial reviews are author judgments. Queue/score is not user approval or audience validation.'}

def main():
    p = argparse.ArgumentParser(description=__doc__); commands = p.add_subparsers(dest='command', required=True)
    c = commands.add_parser('context'); c.add_argument('--workspace', type=Path, required=True)
    c.add_argument('--config', type=Path, required=True); c.add_argument('--date', required=True)
    c.add_argument('--memory-export', type=Path, action='append'); c.add_argument('--max-chars', type=int, default=50000)
    c.add_argument('--output', type=Path, required=True)
    m = commands.add_parser('rank'); m.add_argument('--context', type=Path, required=True)
    m.add_argument('--input', type=Path, required=True); m.add_argument('--reviews', type=Path, required=True)
    m.add_argument('--count', type=int, default=3); m.add_argument('--output', type=Path, required=True)
    f=commands.add_parser('feedback'); f.add_argument('--workspace',type=Path,required=True)
    f.add_argument('--topic-id',required=True); f.add_argument('--outcome',required=True)
    f.add_argument('--reason',required=True); f.add_argument('--date',required=True)
    args = p.parse_args()
    try:
        if args.command == 'context':
            data = assemble(args.workspace, read(args.config), args.date,
                            [read(x) for x in args.memory_export or []], args.max_chars)
        elif args.command == 'rank':
            if not 1 <= args.count <= 20: raise ValueError('Count must be in 1..20')
            payload = read(args.input)
            data = rank(read(args.context), payload['candidates'] if isinstance(payload, dict) else payload,
                        read(args.reviews), args.count)
            if isinstance(payload, dict): data['sources'] = payload.get('sources', {})
        else:
            print(json.dumps(feedback(args.workspace,args.topic_id,args.outcome,args.reason,args.date),ensure_ascii=False))
            return 0
        write(args.output, data)
        print(json.dumps({'output': str(args.output), 'context_hash': data['context_hash'],
                          'shortlist': data.get('shortlist'), 'gaps': data.get('gaps')}, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'error': type(exc).__name__, 'reason': str(exc)}, ensure_ascii=False)); return 2

if __name__ == '__main__': raise SystemExit(main())
