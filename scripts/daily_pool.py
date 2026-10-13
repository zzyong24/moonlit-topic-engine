#!/usr/bin/env python3
"""Validate, persist and project a reviewed daily pool through the workspace owner.

No network, models, keyword scoring, automatic adoption or separate candidate bank.
The workspace supplies its public scripts/topic_store.py maintenance implementation.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unicodedata
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
SOURCE_STATES = {'success', 'partial', 'unavailable', 'not_called', 'reused', 'failed'}
AVAILABLE_SOURCE_STATES = {'success', 'partial', 'reused'}
FIELDS = {
    'core_thesis': 'coreThesis', 'user_task': 'userTask', 'input': 'input', 'steps': 'steps',
    'output': 'output', 'verification': 'verification', 'grid_pair': 'gridPair',
    'tool_entry': 'toolEntry', 'prep_minutes': 'prepMinutes', 'author_work_ids': 'authorWorkIds',
    'author_basis': 'authorBasis', 'demand_basis': 'demandBasis', 'source_ids': 'sourceIds',
    'source_urls': 'sourceUrls', 'why_now': 'whyNow', 'timeliness': 'timeliness',
    'generated_at': 'generatedAt', 'checked_at': 'checkedAt', 'expires_at': 'expiresAt',
    'recording_status': 'recordingStatus', 'dedup_review': 'dedupReview', 'daily_rank': 'dailyRank',
    'content_brief': 'contentBrief', 'topic_analysis': 'topicAnalysis',
}


class PoolError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def read(file, fallback=None):
    try:
        return json.loads(Path(file).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return copy.deepcopy(fallback)


def write(file, value):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.resolve().relative_to(file.parent.resolve())
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if file.exists() and file.read_text(encoding='utf-8') == content:
        return
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=file.parent,
                                     prefix='.' + file.name + '.', delete=False) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        name = temporary.name
    os.replace(name, file)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('需要带时区的日期时间')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('日期时间缺少时区')
    return parsed


def clock(now=None):
    return timestamp(now) if now else dt.datetime.now(dt.timezone.utc)


def content_hash(candidate):
    # Exactly the canonical owner serializer: optimistic protection reads real contents.
    return hashlib.sha256(json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def thesis_key(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value))).casefold().strip('。.!！?？')


def confined(root, file):
    resolved = Path(file).resolve()
    try:
        resolved.relative_to(Path(root).resolve())
    except ValueError as exc:
        raise PoolError('选题记录指向工作区之外，已停止操作。', 403) from exc
    return resolved


def records(root):
    values = []
    for file in sorted((Path(root) / 'topics').glob('20[0-9][0-9]/????-??-??/topics.json')):
        file = confined(root, file)
        doc = read(file)
        if not isinstance(doc, dict) or not isinstance(doc.get('topics'), list):
            raise PoolError('选题记录无法读取，请先修复原始记录。', 503)
        for topic in doc['topics']:
            values.append((file, doc, topic))
    return values


def author_works(root):
    values = {}
    for file in sorted((Path(root) / 'works').glob('20[0-9][0-9]/W-*/work.json')):
        value = read(confined(root, file))
        if isinstance(value, dict) and value.get('id'):
            values[value['id']] = value
    return values


def configuration(root):
    config = read(confined(root, Path(root) / 'topics/personalization.json'), {})
    grids = config.get('paired_grids', {})
    audience = [c.get('id') for c in grids.get('audience', {}).get('cells', [])]
    industry = [c.get('id') for c in grids.get('industry', {}).get('cells', [])]
    if (len(audience) != 8 or len(industry) != 8 or len(set(audience)) != 8
            or len(set(industry)) != 8 or not all(isinstance(v, str) and v for v in audience + industry)):
        raise PoolError('当前双九宫格缺少有效的八个观众任务或八个能力，请先检查配置。', 503)
    return config, grids, audience, industry


def camel(value):
    if isinstance(value, list):
        return [camel(item) for item in value]
    if isinstance(value, dict):
        return {re.sub(r'_([a-z])', lambda m: m[1].upper(), key): camel(item)
                for key, item in value.items()}
    return value


def public_topic(file, topic):
    candidate = topic.get('candidate', {})
    return {'id': topic['id'], 'title': topic.get('title') or candidate.get('title'),
            'status': topic.get('status', 'unknown'), 'date': file.parent.name,
            'workId': topic.get('workId'), 'candidateHash': content_hash(candidate),
            **{public: camel(candidate.get(private)) for private, public in FIELDS.items()}}


def valid_url(value):
    return isinstance(value, str) and bool(re.fullmatch(r'https?://[^\s/]+(?:/[^\s]*)?', value))


def text(value):
    return isinstance(value, str) and bool(value.strip())


def text_list(value, allow_empty=False):
    return isinstance(value, list) and (allow_empty or bool(value)) and all(text(v) for v in value)


def _validate(root, payload, now=None):
    """Structural/source/identity validation; supplied editorial review owns meaning."""
    current = clock(now)
    config, grids, audiences, industries = configuration(root)
    known_works = author_works(root)
    old_topics = records(root)
    known_cores = {thesis_key(topic.get('candidate', {}).get('core_thesis'))
                   for _, _, topic in old_topics if text(topic.get('candidate', {}).get('core_thesis'))}
    known_cores.update(thesis_key(work['thesis']) for work in known_works.values() if text(work.get('thesis')))
    errors = []
    if not isinstance(payload, dict):
        return {'valid': False, 'errors': ['输入需要选题数组与来源快照。']}
    if payload.get('started_at') is not None:
        try:
            if timestamp(payload['started_at']) > current:
                errors.append('本轮开始时间来自未来。')
        except (ValueError, TypeError):
            errors.append('本轮开始时间无效。')
    if not text_list(payload.get('notes', []), True):
        errors.append('本轮说明需要文本数组。')
    date = payload.get('date')
    try:
        dt.date.fromisoformat(date)
        if date != current.astimezone(TZ).date().isoformat():
            errors.append('只能将本次研究发布到真实北京时间当天，不可给旧研究刷新日期。')
    except (ValueError, TypeError):
        errors.append('本轮日期无效。')
    snapshot = payload.get('source_snapshot')
    sources = {}
    source_urls = {}
    if not isinstance(snapshot, dict) or snapshot.get('date') != date:
        errors.append('需要同日的真实来源快照。')
        snapshot = {}
    for key in ['captured_at']:
        try:
            if timestamp(snapshot.get(key)) > current:
                errors.append('来源快照日期不能来自未来。')
        except (ValueError, TypeError):
            errors.append('来源快照需要真实且带时区的采集时间。')
    for source in snapshot.get('sources', []):
        if not isinstance(source, dict) or not text(source.get('id')) or source.get('id') in sources:
            errors.append('来源身份缺失或重复。')
            continue
        sid = source['id']
        sources[sid] = source
        source_urls[sid] = set(source.get('urls', [])) if isinstance(source.get('urls'), list) else set()
        if source.get('status') not in SOURCE_STATES or not text(source.get('name')) or not text(source.get('read_scope')):
            errors.append(f'来源 {sid} 缺少真实状态、名称或读取范围。')
        if not isinstance(source.get('urls'), list) or not all(valid_url(u) for u in source.get('urls', [])):
            errors.append(f'来源 {sid} 的链接无效。')
        try:
            if source.get('status') == 'not_called' and source.get('checked_at') is None:
                pass  # No access attempt means there is no source check to timestamp.
            else:
                checked = timestamp(source.get('checked_at'))
                if checked > current or checked > timestamp(snapshot.get('captured_at')):
                    errors.append(f'来源 {sid} 的检查时间不能晚于当前或本轮采集时间。')
        except (ValueError, TypeError):
            errors.append(f'来源 {sid} 缺少真实检查时间。')
    if not sources:
        errors.append('来源快照没有来源状态。')
    signal_ids = set()
    for signal in snapshot.get('signals', []):
        if not isinstance(signal, dict) or not text(signal.get('id')) or signal.get('id') in signal_ids:
            errors.append('线索身份缺失或重复。')
            continue
        signal_ids.add(signal['id'])
        sid = signal.get('source_id')
        if sid not in sources or sources[sid].get('status') not in AVAILABLE_SOURCE_STATES:
            errors.append(f'线索 {signal["id"]} 没有实际读取的来源。')
        elif valid_url(signal.get('url')):
            source_urls[sid].add(signal['url'])
        else:
            errors.append(f'线索 {signal["id"]} 的原始链接无效。')
        if not text(signal.get('title')) or not text(signal.get('summary')):
            errors.append(f'线索 {signal["id"]} 缺少真实正文摘要。')
        if not isinstance(signal.get('capability_ids'), list) or any(v not in industries for v in signal.get('capability_ids', [])):
            errors.append(f'线索 {signal["id"]} 的能力格无效。')
        try:
            if timestamp(signal.get('checked_at')) > current:
                errors.append(f'线索 {signal["id"]} 检查时间来自未来。')
            if signal.get('event_date') is not None and dt.date.fromisoformat(signal['event_date']) > current.astimezone(TZ).date():
                errors.append(f'线索 {signal["id"]} 事件日期来自未来。')
        except (ValueError, TypeError):
            errors.append(f'线索 {signal["id"]} 的日期无效；未知事件日期应为 null。')
    context = snapshot.get('context', {})
    if not isinstance(context, dict):
        errors.append('来源快照需要本人的最新状态检查范围。')
        context = {}
    for key in ['profile_checked_at', 'run_state_checked_at']:
        try:
            if timestamp(context.get(key)) > current:
                errors.append('本人状态检查时间来自未来。')
        except (ValueError, TypeError):
            errors.append('本人状态缺少带时区的检查时间。')
    if not isinstance(context.get('work_ids'), list) or any(v not in known_works for v in context.get('work_ids', [])):
        errors.append('本人状态引用了不存在的作品。')
    if context.get('day_plan_date') is not None:
        try:
            if dt.date.fromisoformat(context['day_plan_date']) > current.astimezone(TZ).date():
                errors.append('当天计划日期来自未来。')
        except (ValueError, TypeError):
            errors.append('当天计划日期无效。')
    candidates = payload.get('candidates')
    if not isinstance(candidates, list) or not candidates:
        errors.append('输入需要非空 candidates 数组。')
        candidates = []
    keys = set()
    maximum = config.get('production', {}).get('prep_minutes', 240)
    for index, candidate in enumerate(candidates):
        prefix = f'第 {index + 1} 题'
        if not isinstance(candidate, dict):
            errors.append(f'{prefix} 不是有效选题卡。')
            continue
        c = candidate
        if c.get('daily_pool') is not True:
            errors.append(f'{prefix} 未标记每日池成员。')
        for key in ['title', 'core_thesis', 'user_task', 'input', 'output', 'verification', 'author_basis', 'why_now']:
            if not text(c.get(key)):
                errors.append(f'{prefix} 缺少 {key}。')
        if any(v in c.get('title', '') for v in ['/','\\','\n','\r']) or len(c.get('title', '')) > 180:
            errors.append(f'{prefix} 标题不适合作品名称，请避免目录分隔符和过长标题。')
        if not text_list(c.get('steps')):
            errors.append(f'{prefix} 缺少可执行步骤。')
        pair = c.get('grid_pair', {})
        if not isinstance(pair, dict) or pair.get('audience_cell_id') not in audiences or pair.get('capability_cell_id') not in industries or pair.get('grid_version') != grids.get('version') or not text(pair.get('relation_reason')):
            errors.append(f'{prefix} 不属于当前已认可九宫格，或缺少组合的任务关系。')
        entry = c.get('tool_entry', {})
        if not isinstance(entry, dict) or not all(text(entry.get(k)) for k in ['name', 'language', 'cost_note']) or not valid_url(entry.get('url')) or entry.get('entry_status') not in {'planned', 'verified', 'unknown'} or not text_list(entry.get('prerequisites'), True):
            errors.append(f'{prefix} 缺少真实入口、中文使用方式、成本或前置条件。')
        prep = c.get('prep_minutes')
        if not isinstance(prep, int) or isinstance(prep, bool) or not 0 < prep <= maximum:
            errors.append(f'{prefix} 备料时间超出当前配置或无效。')
        for field in ['author_work_ids']:
            if not text_list(c.get(field), True) or any(w not in known_works for w in c.get(field, [])):
                errors.append(f'{prefix} 引用了不存在的本人作品。')
        demand = c.get('demand_basis', {})
        if not isinstance(demand, dict) or not text(demand.get('kind')) or not text(demand.get('detail')) or not text_list(demand.get('evidence_ids'), True):
            errors.append(f'{prefix} 缺少需求依据，假设应明确为假设。')
        ids = c.get('source_ids', [])
        urls = c.get('source_urls', [])
        if not text_list(ids) or any(sid not in sources or sources[sid].get('status') not in AVAILABLE_SOURCE_STATES for sid in ids):
            errors.append(f'{prefix} 来源未实际读取或无法对应来源快照。')
        if not text_list(urls) or not all(valid_url(u) for u in urls) or any(u not in set().union(*(source_urls.get(sid, set()) for sid in ids)) for u in urls):
            errors.append(f'{prefix} 证据链接不在对应来源读取范围内。')
        if c.get('timeliness') not in {'current', 'recent', 'evergreen', 'personal_now'}:
            errors.append(f'{prefix} 缺少明确的时效类型。')
        try:
            generated, checked, expires = (timestamp(c.get(key)) for key in ['generated_at', 'checked_at', 'expires_at'])
            if generated > current or checked > current or expires <= current or expires <= checked:
                errors.append(f'{prefix} 时间来自未来或已经过期。')
            if thesis_key(c.get('core_thesis')) not in known_cores and generated.astimezone(TZ).date().isoformat() != date:
                errors.append(f'{prefix} 新命题的生成日须为本次实际研究日；旧命题应保留原生成日。')
            update_id = c.get('update_topic_id')
            if update_id:
                previous = [topic for _, _, topic in old_topics if topic.get('id') == update_id]
                old_candidate = previous[0].get('candidate', {}) if len(previous) == 1 else {}
                if old_candidate.get('daily_pool') is True and generated != timestamp(old_candidate.get('generated_at')):
                    errors.append(f'{prefix} 复用原命题必须保留原生成时间；补核验只更新检查时间。')
        except (ValueError, TypeError):
            errors.append(f'{prefix} 缺少带时区的生成、检查与过期时间。')
        status = c.get('recording_status')
        if status not in {'test_first', 'record_candidate', 'observe'}:
            errors.append(f'{prefix} 录制状态无效。')
        if status == 'record_candidate':
            evidence = c.get('test_evidence', {})
            if entry.get('entry_status') != 'verified' or not isinstance(evidence, dict) or evidence.get('status') != 'passed' or not text_list(evidence.get('evidence')):
                errors.append(f'{prefix} 没有入口与实际通过的测试证据，不得标为可录候选。')
            else:
                try:
                    if timestamp(evidence.get('checked_at')) > current:
                        errors.append(f'{prefix} 实测时间来自未来。')
                except (ValueError, TypeError):
                    errors.append(f'{prefix} 实测缺少日期。')
        review = c.get('dedup_review', {})
        if not isinstance(review, dict) or not text(review.get('status')) or review.get('status') in {'duplicate', 'rejected', 'unreviewed'} or not text(review.get('detail')) or not text_list(review.get('checked_work_ids'), True) or any(w not in known_works for w in review.get('checked_work_ids', [])):
            errors.append(f'{prefix} 缺少有效的编辑去重审读。')
        rank = c.get('daily_rank')
        if rank is not None and (not isinstance(rank, int) or isinstance(rank, bool) or rank < 1):
            errors.append(f'{prefix} 今日优先顺序无效。')
        key = thesis_key(c.get('core_thesis', ''))
        if key in keys:
            errors.append(f'{prefix} 与本轮另一条核心命题完全相同。')
        keys.add(key)
        if c.get('update_topic_id') is not None and not re.fullmatch(r'T-\d{8}-\d{3}', str(c['update_topic_id'])):
            errors.append(f'{prefix} 显式更新身份无效。')
    return {'valid': not errors, 'errors': errors, 'candidate_count': len(candidates),
            'source_count': len(sources), 'configured_pairs': len(audiences) * len(industries),
            'scope': '结构、来源范围、时间和身份检查；内容判断来自本轮编辑审读。'}


def validate(root, payload, now=None):
    try:
        return _validate(root, payload, now)
    except (TypeError, AttributeError):
        # A malformed array/object is input failure, not an interpreter traceback.
        return {'valid': False, 'errors': ['选题或来源字段类型无效，请按选题卡合同提供文本、数组和对象。']}


@contextlib.contextmanager
def maintenance_lock(exclusive=True):
    runtime = os.environ.get('MOONLIT_POOL_RUNTIME_DIR')
    folder = Path(runtime) if runtime else Path.home() / '.local/share/moonlit-creator'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'maintenance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield


def backup_metadata(root, owner):
    """Production uses the original CLI backup; tests can isolate their runtime storage."""
    runtime = os.environ.get('MOONLIT_POOL_RUNTIME_DIR')
    if not runtime:
        return owner['moonlit'].snapshot(root)
    parent = Path(runtime) / 'backups'
    parent.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix='metadata-', dir=parent))
    files = list(root.glob('works/*/*/work.json')) + list(root.glob('topics/*/*/topics.json'))
    files += [root / 'works/index.json', root / 'topics/index.json']
    for file in files:
        if file.is_file():
            source = confined(root, file)
            target = destination / file.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return str(destination)


@contextlib.contextmanager
def workspace_owner(root):
    """Resolve public maintenance modules from the caller; no sibling Skill assumptions."""
    scripts = confined(root, Path(root) / 'scripts')
    names = ['workspace_core', 'topic_store', 'moonlit']
    # The caller owns task cards. Load its optional dependency in the same confined
    # module scope; a hash-pinned Skill cannot import from the caller's sys.path.
    if (scripts / 'creator_system.py').exists() or (Path(root) / '系统/模板/作品任务卡.md').exists():
        names.append('creator_system')
    previous = {name: sys.modules.get(name) for name in names}
    modules = {}
    try:
        for name in previous:
            file = confined(root, scripts / (name + '.py'))
            if not file.is_file():
                raise PoolError('工作区缺少选题维护入口，已停止写入。', 503)
            spec = importlib.util.spec_from_file_location(name, file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules[name] = module
        # The owner writes fixed projections and a work reservation; reject symlink escapes
        # before entering its older path implementation.
        for relative in ['topics', 'topics/index.json', 'works', 'works/index.json', 'WORKS.md']:
            confined(root, Path(root) / relative)
        yield modules
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def find_topic(root, tid):
    if not isinstance(tid, str) or not re.fullmatch(r'T-\d{8}-\d{3}', tid):
        raise PoolError('请选择有效的选题。')
    matches = [(file, doc, topic) for file, doc, topic in records(root) if topic.get('id') == tid]
    if len(matches) != 1:
        raise PoolError('这条选题不存在或身份重复，请刷新后检查。', 404)
    return matches[0]


def current_context_hash(root, source_snapshot, date):
    """Same inputs at publication and readback; exclude this job's own state writes."""
    personalization = read(confined(root, root / 'topics/personalization.json'), {})
    profile_path = personalization.get('profile')
    profile = read(confined(root, root / profile_path)) if isinstance(profile_path, str) else None
    releases = {}
    for file in (root / 'works').glob('20[0-9][0-9]/W-*/distribution/releases.json'):
        releases[str(file.relative_to(root))] = read(confined(root, file))
    feedback_file = confined(root, root / 'topics/selection-feedback.jsonl')
    feedback_hash = hashlib.sha256(feedback_file.read_bytes() if feedback_file.exists() else b'').hexdigest()
    topic_rows = [{'id': topic.get('id'), 'status': topic.get('status'),
                   'candidateHash': content_hash(topic.get('candidate', {}))}
                  for _, _, topic in records(root)]
    topic_rows.sort(key=lambda row: row['id'] or '')
    run = read(confined(root, root / 'research/operations/run-state.json'), {})
    health = read(confined(root, root / 'research/operations/source-health.json'), {})
    source_health = [{key: s.get(key) for key in ['id','status','valid_records','complete','reason']}
                     for s in health.get('sources', [])]
    benchmark = personalization.get('benchmark_demand', {})
    benchmark_comments, benchmark_signals = [], []
    for key in ['collection_path','signals_path']:
        relative = benchmark.get(key)
        if not relative:
            continue
        if not isinstance(relative, str) or not relative.startswith('research/'):
            raise PoolError('对标需求必须指向当前工作区研究记录。', 403)
        evidence = read(confined(root, root / relative), {})
        if evidence.get('scope_id') != benchmark.get('scope_id'):
            continue
        if key == 'collection_path':
            benchmark_comments = [{'author': p.get('url'), 'video_id': v.get('id'), 'comments': v.get('comments', []),
                                   'top_complete': v.get('top_complete'), 'reply_complete': v.get('reply_complete')}
                                  for p in evidence.get('profiles', []) for v in p.get('selected_videos', [])]
        else:
            benchmark_signals = [{k:v for k,v in s.items() if k not in {'reviewed_at','checked_at'}}
                                 for s in evidence.get('signals', [])]
    context = {'personalization': personalization, 'profile': profile, 'works': author_works(root),
               'releases': releases, 'source_snapshot': source_snapshot, 'topic_rows': topic_rows,
               'selection_feedback_hash': feedback_hash,
               'day_plan': read(confined(root, root / f'research/operations/day-plans/{date}.json')),
               'data_return': run.get('jobs', {}).get('data_return'),
               'source_health': source_health, 'benchmark_comments': benchmark_comments,
               'benchmark_signals': benchmark_signals}
    return content_hash(context)


def projection(root, current):
    config, _grids, audiences, industries = configuration(root)
    topics = [public_topic(file, topic) for file, _, topic in records(root)
              if topic.get('candidate', {}).get('daily_pool') is True]
    topics.sort(key=lambda t: (t['date'], t['id']), reverse=True)
    date = current.astimezone(TZ).date().isoformat()
    state = read(confined(root, Path(root) / 'research/operations/topic-pool-state.json'))
    source = None
    source_path = state.get('source_snapshot_path') if isinstance(state, dict) else None
    if isinstance(source_path, str) and re.fullmatch(r'topics/20\d{2}/\d{4}-\d{2}-\d{2}/source-snapshot\.json', source_path):
        source = read(confined(root, Path(root) / source_path))
    active = []
    for topic in topics:
        try:
            if topic['status'] == 'recommended' and timestamp(topic['expiresAt']) > current:
                active.append(topic)
        except (TypeError, ValueError):
            continue
    # Observation reserves remain browsable but cannot fill executable-task gaps
    # or become a daily recommendation merely because they have a stored rank.
    actionable = [topic for topic in active
                  if topic.get('recordingStatus') in {'test_first', 'record_candidate'}]
    counts = {(a, i): 0 for a in audiences for i in industries}
    for topic in actionable:
        pair = topic.get('gridPair') or {}
        key = (pair.get('audienceCellId'), pair.get('capabilityCellId'))
        if key in counts:
            counts[key] += 1
    pairs = [{'audienceId': a, 'industryId': i, 'count': count} for (a, i), count in counts.items()]
    limit = config.get('daily_pool', {}).get('shortlist_max', 3)
    ids = state.get('shortlist_topic_ids', []) if isinstance(state, dict) and state.get('date') == date else []
    shortlist = [topic for tid in ids for topic in actionable if topic['id'] == tid][:limit]
    current_hash = current_context_hash(root, source, date)
    baseline_hash = state.get('context_hash') if isinstance(state, dict) else None
    return {'topics': topics, 'state': camel(state), 'sources': camel(source), 'pairs': pairs,
            'availableCounts': {'total': len(active), 'actionable': len(actionable),
                                'observation': len(active) - len(actionable)},
            'todayShortlist': shortlist, 'currentContextHash': current_hash,
            'contextChanged': bool(baseline_hash and baseline_hash != current_hash)}


def project(root, now=None):
    with maintenance_lock(False):
        return projection(Path(root).resolve(), clock(now))


def publish(root, payload, now=None):
    root = Path(root).resolve()
    current = clock(now)
    with maintenance_lock():
        result = validate(root, payload, current.isoformat())
        if not result['valid']:
            raise PoolError('选题池校验未通过：' + '；'.join(result['errors']))
        date = payload['date']
        existing = records(root)
        by_core = {}
        for file, doc, topic in existing:
            c = topic.get('candidate', {})
            if text(c.get('core_thesis')):
                by_core.setdefault(thesis_key(c['core_thesis']), []).append((file, doc, topic))
        work_cores = {thesis_key(w['thesis']): wid for wid, w in author_works(root).items() if text(w.get('thesis'))}
        fresh, retained, updates, skipped = [], [], [], []
        for raw in payload['candidates']:
            candidate = copy.deepcopy(raw)
            update_id = candidate.pop('update_topic_id', None)
            matches = by_core.get(thesis_key(candidate['core_thesis']), [])
            if update_id:
                file, doc, topic = find_topic(root, update_id)
                if thesis_key(topic.get('candidate', {}).get('core_thesis')) != thesis_key(candidate['core_thesis']):
                    raise PoolError('更新必须保留原核心命题；新命题应形成新候选。', 409)
                if topic.get('status') != 'recommended' or topic.get('workId'):
                    retained.append(topic['id'])
                    continue
                if topic.get('candidateHash') != content_hash(topic.get('candidate', {})):
                    raise PoolError('原选题内容与版本标记不一致，请先修复记录。', 409)
                if content_hash(candidate) != content_hash(topic['candidate']):
                    updates.append((file, doc, topic, candidate))
                retained.append(topic['id'])
                continue
            if matches:
                # Never resurrect rejected/picked cores, even under a new title or date.
                retained.extend(topic['id'] for _, _, topic in matches)
                continue
            known_work = work_cores.get(thesis_key(candidate['core_thesis']))
            if known_work:
                skipped.append({'title': candidate['title'], 'reason': '核心命题已属于作品', 'work_id': known_work})
                continue
            fresh.append(candidate)
        with workspace_owner(root) as owner:
            owner['moonlit'].assert_projection_clean(root)
            if fresh or updates:
                backup_metadata(root, owner)
            # find_topic reads each update independently. Merge all changes into one
            # current document per file; stale document copies lose earlier updates.
            changed_documents = {}
            for file, _old_doc, original, candidate in updates:
                if file not in changed_documents:
                    changed_documents[file] = read(file)
                doc = changed_documents[file]
                matches = [t for t in doc['topics'] if t.get('id') == original['id']]
                if len(matches) != 1:
                    raise PoolError('更新身份已变化，未覆盖原选题记录。', 409)
                topic = matches[0]
                if (topic.get('status') != 'recommended' or topic.get('workId')
                        or content_hash(topic.get('candidate', {})) != content_hash(original['candidate'])):
                    raise PoolError('原选题在写入前已变化，请读回后重审。', 409)
                topic['candidate'] = candidate
                topic['candidateHash'] = content_hash(candidate)
                topic['title'] = candidate['title'].strip()
                topic['updatedAt'] = current.isoformat()
            for file, doc in changed_documents.items():
                write(file, doc)
            if fresh:
                with tempfile.TemporaryDirectory(prefix='moonlit-daily-import-') as temporary:
                    source = Path(temporary) / 'reviewed-candidates.json'
                    write(source, {'candidates': fresh, 'sources': payload['source_snapshot']['sources']})
                    imported = owner['topic_store'].ingest(root, source, date)
            else:
                owner['topic_store'].sync(root)
                imported = {'imported': 0, 'ids': []}
        snapshot_path = f'topics/{date[:4]}/{date}/source-snapshot.json'
        previous_snapshot = read(confined(root, root / snapshot_path))
        if previous_snapshot and previous_snapshot != payload['source_snapshot']:
            archive = f'topics/{date[:4]}/{date}/archive/source-snapshot-{content_hash(previous_snapshot)}.json'
            write(confined(root, root / archive), previous_snapshot)
        write(confined(root, root / snapshot_path), payload['source_snapshot'])
        projected = projection(root, current)
        config, _, audiences, industries = configuration(root)
        target = config.get('daily_pool', {}).get('target_per_pair', 2)
        counts = projected['pairs']
        coverage = {'pair_count': len(audiences) * len(industries),
                    'covered_pairs': sum(p['count'] > 0 for p in counts),
                    'qualified_pairs': sum(p['count'] >= target for p in counts),
                    'total_candidates': sum(p['count'] for p in counts), 'target_per_pair': target,
                    'available_candidates': projected['availableCounts']['total'],
                    'observation_candidates': projected['availableCounts']['observation'],
                    'missing_pairs': [{'audience_cell_id': p['audienceId'], 'capability_cell_id': p['industryId'],
                                       'count': p['count'], 'needed': max(0, target - p['count'])}
                                      for p in counts if p['count'] < target]}
        active = [topic for topic in projected['topics'] if topic['status'] == 'recommended'
                  and topic.get('recordingStatus') in {'test_first', 'record_candidate'}
                  and topic.get('dailyRank') is not None and timestamp(topic['expiresAt']) > current]
        active.sort(key=lambda t: (t['dailyRank'], t['id']))
        current_payload_ids = set(imported.get('ids', []) + retained)
        shortlist = [t['id'] for t in active if t['id'] in current_payload_ids][:config.get('daily_pool', {}).get('shortlist_max', 3)]
        started = payload.get('started_at') or current.isoformat()
        state = {'date': date, 'status': 'partial' if coverage['missing_pairs'] else 'completed',
                 'started_at': started, 'completed_at': current.isoformat(), 'coverage': coverage,
                 'source_snapshot_path': snapshot_path,
                 'context_hash': current_context_hash(root, payload['source_snapshot'], date),
                 'shortlist_topic_ids': shortlist, 'notes': payload.get('notes', [])}
        write(confined(root, root / 'research/operations/topic-pool-state.json'), state)
        return {**imported, 'ids': imported.get('ids', []), 'updated': len(updates),
                'retained_ids': sorted(set(retained)), 'skipped': skipped, 'state': state}


def decide(root, request, now=None):
    root = Path(root).resolve()
    current = clock(now)
    if not isinstance(request, dict) or request.get('action') not in {'pick', 'reject'}:
        raise PoolError('请选择采用或暂不采用这条选题。')
    if not isinstance(request.get('expectedCandidateHash'), str) or not re.fullmatch(r'[a-f0-9]{64}', request['expectedCandidateHash']):
        raise PoolError('选题版本缺失，请刷新后重新选择。', 409)
    reason = request.get('reason') or '本人在后台选择暂不采用'
    if not isinstance(reason, str) or len(reason) > 2000:
        raise PoolError('请将不采用理由控制在 2000 字以内。')
    direction = request.get('direction')
    if direction is not None and (not isinstance(direction, str) or len(direction) > 4000):
        raise PoolError('方向备注需要在 4000 字以内。')
    with maintenance_lock():
        file, doc, topic = find_topic(root, request.get('topicId'))
        candidate = topic.get('candidate', {})
        if candidate.get('daily_pool') is not True:
            raise PoolError('这条记录不是每日选题池候选，请从每日池中选择。', 409)
        actual = content_hash(candidate)
        if actual != request['expectedCandidateHash'] or topic.get('candidateHash') != actual:
            raise PoolError('这条选题已经更新，未执行本次选择。请刷新后重新查看。', 409)
        action, status = request['action'], topic.get('status')
        if action == 'reject' and status in {'picking', 'picked'}:
            raise PoolError('这条选题已关联作品，请到作品库安排后续，不能按未选候选删除。', 409)
        if action == 'pick' and status == 'rejected':
            raise PoolError('这条选题已被你暂不采用，未重新创建作品。请挑选其他题。', 409)
        if action == 'reject' and status == 'rejected':
            with workspace_owner(root) as owner:
                owner['topic_store'].sync(root)
            return {'topicId': topic['id'], 'status': 'rejected'}
        if action == 'pick' and status not in {'recommended', 'picking', 'picked'}:
            raise PoolError('这条选题当前不可采用，请刷新后检查状态。', 409)
        if status == 'recommended':
            try:
                if timestamp(candidate.get('expires_at')) <= current:
                    raise PoolError('这条选题已过期，未创建作品。请先更新事实或选择有效选题。', 409)
            except (ValueError, TypeError) as exc:
                if isinstance(exc, PoolError):
                    raise
                raise PoolError('这条选题缺少有效期限，请先补核事实。', 409) from exc
        if action == 'pick' and status in {'picking', 'picked'} and direction is not None and direction.strip() != topic.get('userDirection', ''):
            raise PoolError('已确认方向不同，请到已确认选题提交新方向，不重复建立作品。', 409)
        with workspace_owner(root) as owner:
            if action == 'pick':
                year = str(current.astimezone(TZ).year)
                confined(root, root / 'works' / year)
                if topic.get('workPath'):
                    confined(root, root / topic['workPath'])
                owner['moonlit'].assert_projection_clean(root)
                backup_metadata(root, owner)
                result = owner['topic_store'].pick(root, topic['id'], candidate['core_thesis'],
                                                  current.astimezone(TZ).date().isoformat(), direction=direction)
                return {'topicId': topic['id'], 'status': result['status'], 'workId': result['id']}
            # Persist one explicit user feedback event. Recovery reuses its identity.
            feedback_file = confined(root, root / 'topics/selection-feedback.jsonl')
            decision_id = f'reject:{topic["id"]}:{actual}'
            feedback_file.parent.mkdir(parents=True, exist_ok=True)
            existing_feedback = feedback_file.read_text(encoding='utf-8') if feedback_file.exists() else ''
            present = any(read_event.get('decision_id') == decision_id
                          for line in existing_feedback.splitlines() if line.strip()
                          for read_event in [json.loads(line)])
            if not present:
                event = {'decision_id': decision_id, 'topic_id': topic['id'], 'outcome': 'rejected',
                         'reason': reason.strip() or '本人在后台选择暂不采用',
                         'date': current.astimezone(TZ).date().isoformat(),
                         'recorded_at': current.isoformat(), 'attribution': 'user_dashboard_action',
                         'candidate_hash': actual, 'notice': 'Selection feedback, not verified publication results.'}
                with feedback_file.open('a', encoding='utf-8') as feedback:
                    feedback.write(json.dumps(event, ensure_ascii=False) + '\n')
                    feedback.flush()
                    os.fsync(feedback.fileno())
            topic.update(status='rejected', rejectedAt=current.isoformat(), rejectionReason=reason)
            write(file, doc)
            owner['topic_store'].sync(root)
            return {'topicId': topic['id'], 'status': 'rejected'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--as-of', help='Explicit timezone-aware clock for reproducible checks')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['validate', 'publish', 'decide']:
        sub.add_parser(name).add_argument('--input', type=Path, help='JSON file; omit to read stdin')
    sub.add_parser('project')
    args = parser.parse_args(argv)
    try:
        if args.command == 'project':
            result = project(args.root, args.as_of)
        else:
            payload = read(args.input) if args.input else json.load(sys.stdin)
            result = globals()[args.command](args.root, payload, args.as_of)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if args.command != 'validate' or result['valid'] else 1
    except (PoolError, ValueError, OSError, KeyError) as exc:
        print(json.dumps({'message': str(exc), 'status': getattr(exc, 'status', 503)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
