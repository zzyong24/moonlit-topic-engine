"""Daily recommendations persist through the workspace owner, never a second bank."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/daily_pool.py'
spec = importlib.util.spec_from_file_location('daily_pool', SCRIPT)
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)


class DailyPoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='daily topic workspace ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Copy the public workspace maintenance implementation, not production data.
        source = Path(os.environ.get('MOONLIT_WORKSPACE', Path.cwd())) / 'scripts'
        if not (source / 'topic_store.py').is_file():
            self.skipTest('Set MOONLIT_WORKSPACE to a workspace with its public maintenance CLI')
        (self.root / 'scripts').mkdir()
        for name in ['workspace_core.py', 'topic_store.py', 'moonlit.py']:
            shutil.copy2(source / name, self.root / 'scripts' / name)
        self.now = '2026-10-03T23:00:00+00:00'
        self.day = '2026-10-04'
        self.config = {'paired_grids': {'version': 2,
            'audience': {'cells': [{'id': f'a{i}'} for i in range(8)]},
            'industry': {'cells': [{'id': f'i{i}'} for i in range(8)]}},
            'production': {'prep_minutes': 240}, 'daily_pool': {'target_per_pair': 2}}
        self.save('topics/personalization.json', self.config)
        self.snapshot = {'date': self.day, 'captured_at': self.now,
            'sources': [{'id': 'official', 'name': '原始文档', 'status': 'success',
                'checked_at': self.now, 'urls': ['https://example.com/docs'],
                'read_scope': '原始操作说明', 'note': '公开读取'}],
            'signals': [{'id': 's1', 'title': '实际线索', 'url': 'https://example.com/docs',
                'event_date': None, 'checked_at': self.now, 'summary': '操作入口',
                'capability_ids': ['i0'], 'source_id': 'official'}],
            'context': {'profile_checked_at': self.now, 'work_ids': [],
                'run_state_checked_at': self.now, 'day_plan_date': None}}
        self.candidate = {'daily_pool': True, 'title': '把会议笔记交成一页汇报',
            'core_thesis': '会前笔记可以变成保留来源的一页行动汇报。',
            'user_task': '上班族交一页会议汇报', 'input': '去隐私的会议笔记',
            'steps': ['上传样例', '核对要点'], 'output': '一页行动汇报',
            'verification': '逐条检查来源和责任人',
            'grid_pair': {'audience_cell_id': 'a0', 'capability_cell_id': 'i0',
                'grid_version': 2, 'relation_reason': '把资料提取用于汇报'},
            'tool_entry': {'name': '工具入口', 'url': 'https://example.com/docs',
                'language': '中文提示', 'cost_note': '账号与价格待核验',
                'prerequisites': ['可用账号'], 'entry_status': 'planned'},
            'prep_minutes': 120, 'author_work_ids': [], 'author_basis': '相邻任务的待测案例',
            'demand_basis': {'kind': 'editorial_hypothesis', 'detail': '任务假设，尚未验证频次', 'evidence_ids': []},
            'source_ids': ['official'], 'source_urls': ['https://example.com/docs'],
            'why_now': '当前工作任务可以实测', 'timeliness': 'evergreen',
            'generated_at': self.now, 'checked_at': self.now,
            'expires_at': '2026-10-11T00:00:00+00:00', 'recording_status': 'test_first',
            'dedup_review': {'status': 'reviewed', 'detail': '编辑核对已有记录', 'checked_work_ids': []},
            'daily_rank': 1}
        self.payload = {'date': self.day, 'candidates': [self.candidate], 'source_snapshot': self.snapshot,
            'started_at': self.now, 'notes': ['人工编辑审读，未承诺工具实测']}
        self.runtime_patch = patch.dict(pool.os.environ, {'MOONLIT_POOL_RUNTIME_DIR': str(self.root / 'runtime')})
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)

    def save(self, rel, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return p

    def test_current_benchmark_questions_trigger_review_but_check_clock_alone_does_not(self):
        self.config['benchmark_demand']={'scope_id':'s','collection_path':'research/benchmark/collection.json','signals_path':'research/benchmark/signals.json'}
        self.save('topics/personalization.json',self.config)
        evidence={'scope_id':'s','profiles':[{'url':'https://example.com/author','selected_videos':[{'id':'1','comments':[{'id':'c1','text':'怎么导出？'}]}]}],'checked_at':self.now}
        self.save('research/benchmark/collection.json',evidence)
        first=pool.current_context_hash(self.root,self.snapshot,self.day)
        evidence['checked_at']='2026-10-04T00:00:00Z';self.save('research/benchmark/collection.json',evidence)
        self.assertEqual(first,pool.current_context_hash(self.root,self.snapshot,self.day))
        evidence['profiles'][0]['selected_videos'][0]['comments'].append({'id':'c2','text':'普通电脑可以吗？'})
        self.save('research/benchmark/collection.json',evidence)
        self.assertNotEqual(first,pool.current_context_hash(self.root,self.snapshot,self.day))

    def test_publish_read_and_repeat_keep_identity_and_report_real_gaps(self):
        result = pool.publish(self.root, self.payload, self.now)
        self.assertEqual(result['imported'], 1)
        again = pool.publish(self.root, self.payload, self.now)
        self.assertEqual(again['imported'], 0)
        projected = pool.project(self.root, self.now)
        self.assertEqual(len(projected['topics']), 1)
        self.assertEqual(projected['state']['coverage']['pairCount'], 64)
        self.assertEqual(projected['state']['coverage']['coveredPairs'], 1)
        self.assertEqual(len(projected['state']['coverage']['missingPairs']), 64)
        self.assertEqual(projected['topics'][0]['coreThesis'], self.candidate['core_thesis'])
        self.assertEqual(projected['todayShortlist'][0]['id'], result['ids'][0])
        self.assertFalse((self.root / 'works').exists())

    def test_reject_is_idempotent_persisted_and_blocks_pick(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        h = pool.project(self.root, self.now)['topics'][0]['candidateHash']
        request = {'topicId': tid, 'action': 'reject', 'expectedCandidateHash': h, 'reason': '目前不适合我'}
        first = pool.decide(self.root, request, self.now)
        self.assertEqual(first['status'], 'rejected')
        self.assertEqual(pool.decide(self.root, request, self.now), first)
        self.assertEqual(len((self.root / 'topics/selection-feedback.jsonl').read_text().splitlines()), 1)
        with self.assertRaises(pool.PoolError) as caught:
            pool.decide(self.root, {**request, 'action': 'pick'}, self.now)
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(pool.publish(self.root, self.payload, self.now)['imported'], 0)
        self.assertEqual(pool.project(self.root, self.now)['topics'][0]['status'], 'rejected')

    def test_card_analysis_survives_incremental_update_projection_and_pick(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        original = pool.project(self.root, self.now)['topics'][0]
        self.assertIsNone(original['topicAnalysis'])
        self.assertIsNone(original['contentBrief'])
        richer = copy.deepcopy(self.payload)
        card = richer['candidates'][0]
        card['update_topic_id'] = tid
        card['content_brief'] = {'audience_situation': '需要交会议汇报的上班族',
                                 'intended_change': '能逐条核对行动项'}
        card['topic_analysis'] = {
            'schema_version': 1, 'detail_level': 'full',
            'problem_context': {'reader_question': None, 'question_source': 'hypothesis',
                                'current_approach': '手动抄笔记', 'help_step': '核对一页汇报'},
            'hooks': [{'id': f'H{i}', 'type': kind, 'title': f'示例入口{i}',
                       'status': 'pending_evidence'} for i, kind in enumerate(
                           ['痛点', '场景', '交付', '悬念', '结果'], 1)],
            'selected_hook_id': 'H3', 'series': None,
            'promise_chain': {'hook': '一页汇报', 'delivery': '来源可对回', 'next_step': None},
            'review_plan': {'goal': '实际复用', 'unavailable_signals': ['阅读完成'],
                            'hypothesis': '可核对样例比口号更能帮助尝试',
                            'next_changed_factor': '示例材料'},
            'pending_items': ['账号入口尚待实测']}
        updated = pool.publish(self.root, richer, self.now)
        self.assertEqual((updated['updated'], updated['imported']), (1, 0))
        view = pool.project(self.root, self.now)['topics'][0]
        self.assertEqual(view['id'], tid)
        self.assertEqual(view['generatedAt'], original['generatedAt'])
        self.assertEqual(view['status'], original['status'])
        self.assertEqual(view['contentBrief'], pool.camel(card['content_brief']))
        self.assertEqual(view['topicAnalysis'], pool.camel(card['topic_analysis']))
        self.assertNotEqual(view['candidateHash'], original['candidateHash'])
        self.assertFalse((self.root / 'works').exists())
        repeated = pool.publish(self.root, richer, self.now)
        self.assertEqual((repeated['updated'], repeated['imported']), (0, 0))
        chosen = pool.decide(self.root, {'topicId': tid, 'action': 'pick',
                             'expectedCandidateHash': view['candidateHash']}, self.now)
        sources = list((self.root / 'works').glob('20*/W-*/notes/source-topic.json'))
        self.assertEqual(len(sources), 1)
        saved = json.loads(sources[0].read_text())
        self.assertEqual(saved['candidate']['topic_analysis'], card['topic_analysis'])
        self.assertEqual(saved['candidate']['content_brief'], card['content_brief'])
        self.assertEqual(pool.project(self.root, self.now)['topics'][0]['workId'], chosen['workId'])

    def test_observation_reserve_does_not_fill_pair_target_or_shortlist(self):
        payload = copy.deepcopy(self.payload)
        payload['candidates'][0]['daily_rank'] = 2
        reserve = copy.deepcopy(self.candidate)
        reserve.update(title='保留未核入口的相邻问题', core_thesis='另一项任务的入口尚不可读。',
                       recording_status='observe', daily_rank=1)
        payload['candidates'].append(reserve)
        result = pool.publish(self.root, payload, self.now)
        projected = pool.project(self.root, self.now)
        self.assertEqual(len(projected['topics']), 2)
        self.assertEqual(projected['availableCounts'],
                         {'total': 2, 'actionable': 1, 'observation': 1})
        pair = next(p for p in projected['pairs'] if p['audienceId'] == 'a0' and p['industryId'] == 'i0')
        self.assertEqual(pair['count'], 1)
        gap = next(p for p in projected['state']['coverage']['missingPairs']
                   if p['audienceCellId'] == 'a0' and p['capabilityCellId'] == 'i0')
        self.assertEqual(gap['needed'], 1)
        self.assertEqual(projected['state']['status'], 'partial')
        self.assertEqual([t['id'] for t in projected['todayShortlist']], [result['ids'][0]])
        # A previously stored shortlist cannot expose an observation after refresh.
        state = json.loads((self.root / 'research/operations/topic-pool-state.json').read_text())
        state['shortlist_topic_ids'] = [result['ids'][1], result['ids'][0]]
        self.save('research/operations/topic-pool-state.json', state)
        self.assertEqual([t['id'] for t in pool.project(self.root, self.now)['todayShortlist']],
                         [result['ids'][0]])

    def test_two_testable_candidates_qualify_pair_without_being_tested_results(self):
        payload = copy.deepcopy(self.payload)
        second = copy.deepcopy(self.candidate)
        second.update(title='把另一份资料交成对照清单', core_thesis='不同输入交付可核对的对照清单。',
                      daily_rank=2)
        payload['candidates'].append(second)
        result = pool.publish(self.root, payload, self.now)
        self.assertEqual(result['state']['coverage']['qualified_pairs'], 1)
        self.assertEqual(result['state']['coverage']['total_candidates'], 2)
        self.assertEqual(result['state']['coverage']['observation_candidates'], 0)
        self.assertEqual(result['state']['coverage']['available_candidates'], 2)
        self.assertEqual(len(pool.project(self.root, self.now)['todayShortlist']), 2)

    def test_pick_original_owner_is_unique_and_reject_cannot_drop_work(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        h = pool.project(self.root, self.now)['topics'][0]['candidateHash']
        request = {'topicId': tid, 'action': 'pick', 'expectedCandidateHash': h}
        first = pool.decide(self.root, request, self.now)
        self.assertEqual(pool.decide(self.root, request, self.now)['workId'], first['workId'])
        self.assertEqual(len(list((self.root / 'works').glob('*/*/work.json'))), 1)
        work = json.loads(next((self.root / 'works').glob('*/*/work.json')).read_text())
        self.assertEqual(work['thesis'], self.candidate['core_thesis'])
        with self.assertRaises(pool.PoolError):
            pool.decide(self.root, {**request, 'action': 'reject'}, self.now)

    def test_pick_loads_callers_task_card_dependency_and_repeat_preserves_hand_edits(self):
        source = Path(os.environ['MOONLIT_WORKSPACE'])
        shutil.copy2(source / 'scripts/creator_system.py', self.root / 'scripts/creator_system.py')
        template = self.root / '系统/模板/作品任务卡.md'
        template.parent.mkdir(parents=True)
        shutil.copy2(source / '系统/模板/作品任务卡.md', template)
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        request = {'topicId': tid, 'action': 'pick', 'expectedCandidateHash': pool.project(self.root, self.now)['topics'][0]['candidateHash']}
        first = pool.decide(self.root, request, self.now)
        work = next((self.root / 'works').glob('*/*/work.json'))
        record = json.loads(work.read_text())
        self.assertIn('contentMaster', record['artifacts'])
        card = work.parent / 'content/brief/task-card-v01.md'
        self.assertIn(self.candidate['core_thesis'], card.read_text())
        card.write_text(card.read_text() + '\n本人新增的真实材料。\n')
        self.assertEqual(pool.decide(self.root, request, self.now)['workId'], first['workId'])
        self.assertIn('本人新增的真实材料。', card.read_text())

    def test_task_card_module_cannot_escape_callers_workspace(self):
        (self.root / 'scripts/creator_system.py').symlink_to(SCRIPT)
        with self.assertRaises(pool.PoolError) as caught:
            pool.publish(self.root, self.payload, self.now)
        self.assertEqual(caught.exception.status, 403)

    def test_stale_hash_and_expiry_block_write(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        h = pool.project(self.root, self.now)['topics'][0]['candidateHash']
        with self.assertRaises(pool.PoolError) as caught:
            pool.decide(self.root, {'topicId': tid, 'action': 'pick', 'expectedCandidateHash': '0' * 64}, self.now)
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(pool.PoolError):
            pool.decide(self.root, {'topicId': tid, 'action': 'pick', 'expectedCandidateHash': h}, '2026-10-12T00:00:00+00:00')
        self.assertFalse((self.root / 'works').exists())

    def test_missing_source_invalid_grid_and_false_test_status_fail(self):
        for delta in [{'source_ids': ['missing']}, {'grid_pair': {**self.candidate['grid_pair'], 'audience_cell_id': 'outside'}},
                      {'recording_status': 'record_candidate'}, {'checked_at': '2026-10-20T00:00:00+00:00'}]:
            value = copy.deepcopy(self.payload)
            value['candidates'][0].update(delta)
            report = pool.validate(self.root, value, self.now)
            self.assertFalse(report['valid'])
            with self.assertRaises(pool.PoolError):
                pool.publish(self.root, value, self.now)
        self.assertFalse((self.root / 'topics/index.json').exists())

    def test_explicit_refresh_keeps_id_and_old_hash_cannot_decide(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        old = pool.project(self.root, self.now)['topics'][0]['candidateHash']
        update = copy.deepcopy(self.payload)
        update['candidates'][0]['why_now'] = '补充今天的具体证据'
        self.assertEqual(pool.publish(self.root, update, self.now)['updated'], 0)
        update['candidates'][0]['update_topic_id'] = tid
        result = pool.publish(self.root, update, self.now)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(len(pool.project(self.root, self.now)['topics']), 1)
        with self.assertRaises(pool.PoolError):
            pool.decide(self.root, {'topicId': tid, 'action': 'pick', 'expectedCandidateHash': old}, self.now)

    def test_batch_refresh_same_file_keeps_every_update_and_user_rejection(self):
        initial = copy.deepcopy(self.payload)
        second = copy.deepcopy(self.candidate)
        second.update(title='把交接记录做成检查表', core_thesis='交接记录需要逐项核对。', daily_rank=2)
        rejected = copy.deepcopy(self.candidate)
        rejected.update(title='给旧资料补出处', core_thesis='旧资料需要补全原始出处。', daily_rank=3)
        initial['candidates'].extend([second, rejected])
        ids = pool.publish(self.root, initial, self.now)['ids']
        reject_hash = next(t['candidateHash'] for t in pool.project(self.root, self.now)['topics'] if t['id'] == ids[2])
        pool.decide(self.root, {'topicId': ids[2], 'action': 'reject',
                               'expectedCandidateHash': reject_hash, 'reason': '保留用户的暂不采用'}, self.now)
        refreshed = copy.deepcopy(self.payload)
        first = refreshed['candidates'][0]
        first.update(update_topic_id=ids[0], why_now='第一题实际补证', daily_rank=None)
        second = copy.deepcopy(second)
        second.update(update_topic_id=ids[1], why_now='第二题实际补证', daily_rank=1)
        fresh = copy.deepcopy(self.candidate)
        fresh.update(title='把截图做成迁移说明', core_thesis='迁移说明须能对回实际截图。', daily_rank=2)
        refreshed['candidates'].extend([second, fresh])
        result = pool.publish(self.root, refreshed, self.now)
        self.assertEqual(result['updated'], 2)
        self.assertEqual(result['imported'], 1)
        doc = json.loads((self.root / f'topics/2026/{self.day}/topics.json').read_text())
        stored = {t['id']: t for t in doc['topics']}
        for candidate in [first, second]:
            expected = {k: v for k, v in candidate.items() if k != 'update_topic_id'}
            topic = stored[candidate['update_topic_id']]
            self.assertEqual(topic['candidate'], expected)
            self.assertEqual(topic['candidateHash'], pool.content_hash(expected))
        self.assertEqual(stored[ids[2]]['status'], 'rejected')
        self.assertEqual(len((self.root / 'topics/selection-feedback.jsonl').read_text().splitlines()), 1)
        projected = pool.project(self.root, self.now)
        self.assertEqual([t['id'] for t in projected['todayShortlist']], [ids[1], result['ids'][0]])
        again = pool.publish(self.root, refreshed, self.now)
        self.assertEqual((again['updated'], again['imported']), (0, 0))

    def test_index_failure_reject_retry_repairs_without_duplicate_feedback(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        h = pool.project(self.root, self.now)['topics'][0]['candidateHash']
        request = {'topicId': tid, 'action': 'reject', 'expectedCandidateHash': h}
        real_owner = pool.workspace_owner
        @pool.contextlib.contextmanager
        def failing_owner(root):
            with real_owner(root) as owner:
                with patch.object(owner['topic_store'], 'sync', side_effect=OSError('模拟索引写入中断')):
                    yield owner
        with patch.object(pool, 'workspace_owner', failing_owner):
            with self.assertRaises(OSError):
                pool.decide(self.root, request, self.now)
        pool.decide(self.root, request, self.now)
        self.assertEqual(json.loads((self.root / 'topics/index.json').read_text())['topics'][0]['status'], 'rejected')
        self.assertEqual(len((self.root / 'topics/selection-feedback.jsonl').read_text().splitlines()), 1)

    def test_bad_started_time_does_not_partially_import(self):
        payload = copy.deepcopy(self.payload)
        payload['started_at'] = '2026-10-20T00:00:00+00:00'
        with self.assertRaises(pool.PoolError):
            pool.publish(self.root, payload, self.now)
        self.assertFalse((self.root / 'topics/index.json').exists())

    def test_owner_paths_cannot_escape_workspace(self):
        external = tempfile.TemporaryDirectory(prefix='foreign-workspace-')
        self.addCleanup(external.cleanup)
        (self.root / 'works').symlink_to(Path(external.name), target_is_directory=True)
        with self.assertRaises(pool.PoolError):
            pool.publish(self.root, self.payload, self.now)
        self.assertFalse((self.root / 'topics/index.json').exists())

    def test_malformed_nested_types_return_validation_failure(self):
        for change in ['title', 'source']:
            payload = copy.deepcopy(self.payload)
            if change == 'title':
                payload['candidates'][0]['title'] = {'unexpected': 'object'}
            else:
                payload['source_snapshot']['sources'][0]['urls'] = [{}]
            self.assertFalse(pool.validate(self.root, payload, self.now)['valid'])
            with self.assertRaises(pool.PoolError):
                pool.publish(self.root, payload, self.now)

    def test_actual_candidate_change_cannot_reuse_stored_hash(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        old = pool.project(self.root, self.now)['topics'][0]['candidateHash']
        file = self.root / 'topics/2026/2026-10-04/topics.json'
        doc = json.loads(file.read_text())
        doc['topics'][0]['candidate']['core_thesis'] = '模拟其他编辑尚未登记的变化'
        file.write_text(json.dumps(doc), encoding='utf-8')
        with self.assertRaises(pool.PoolError) as caught:
            pool.decide(self.root, {'topicId': tid, 'action': 'pick', 'expectedCandidateHash': old}, self.now)
        self.assertEqual(caught.exception.status, 409)
        self.assertFalse((self.root / 'works').exists())

    def test_next_day_reuses_and_refreshes_without_faking_generation_day(self):
        tid = pool.publish(self.root, self.payload, self.now)['ids'][0]
        tomorrow = '2026-10-04T23:00:00+00:00'
        value = copy.deepcopy(self.payload)
        value['date'] = value['source_snapshot']['date'] = '2026-10-05'
        value['source_snapshot']['captured_at'] = tomorrow
        value['started_at'] = tomorrow
        result = pool.publish(self.root, value, tomorrow)
        self.assertEqual(result['imported'], 0)
        self.assertEqual(result['retained_ids'], [tid])
        value['candidates'][0].update(update_topic_id=tid, checked_at=tomorrow, why_now='补核验最新的具体任务')
        self.assertEqual(pool.publish(self.root, value, tomorrow)['updated'], 1)
        topic = pool.project(self.root, tomorrow)['topics'][0]
        self.assertEqual(topic['date'], self.day)
        self.assertEqual(topic['generatedAt'], self.now)
        value['candidates'][0]['generated_at'] = tomorrow
        self.assertFalse(pool.validate(self.root, value, tomorrow)['valid'])

    def test_new_core_cannot_be_backdated_to_old_generation(self):
        value = copy.deepcopy(self.payload)
        value['candidates'][0]['generated_at'] = '2026-10-02T23:00:00+00:00'
        self.assertFalse(pool.validate(self.root, value, self.now)['valid'])

    def test_not_called_source_has_no_fabricated_check_timestamp(self):
        value = copy.deepcopy(self.payload)
        value['source_snapshot']['sources'].append({'id': 'disabled', 'name': '未调用渠道',
            'status': 'not_called', 'checked_at': None, 'urls': [], 'read_scope': '本轮未调用', 'note': '配置未启用'})
        self.assertTrue(pool.validate(self.root, value, self.now)['valid'])
        pool.publish(self.root, value, self.now)
        self.assertIsNone(pool.project(self.root, self.now)['sources']['sources'][-1]['checkedAt'])

    def test_context_detects_plans_feedback_and_profile_without_own_job_loop(self):
        result = pool.publish(self.root, self.payload, self.now)
        first = pool.project(self.root, self.now)
        self.assertFalse(first['contextChanged'])
        self.assertEqual(first['currentContextHash'], first['state']['contextHash'])
        self.save('research/operations/run-state.json', {'updated_at': 'changed', 'jobs': {
            'topic_recommendation': {'status': 'completed'}, 'weekly_review': {'status': 'scheduled'}}})
        self.assertFalse(pool.project(self.root, self.now)['contextChanged'])
        self.save(f'research/operations/day-plans/{self.day}.json', {'date': self.day, 'note': '下午有会议'})
        self.assertTrue(pool.project(self.root, self.now)['contextChanged'])
        pool.publish(self.root, self.payload, self.now)
        self.assertFalse(pool.project(self.root, self.now)['contextChanged'])
        tid = result['ids'][0]
        topic = pool.project(self.root, self.now)['topics'][0]
        pool.decide(self.root, {'topicId': tid, 'action': 'reject', 'expectedCandidateHash': topic['candidateHash']}, self.now)
        self.assertTrue(pool.project(self.root, self.now)['contextChanged'])
        pool.publish(self.root, self.payload, self.now)
        self.assertFalse(pool.project(self.root, self.now)['contextChanged'])
        self.config['profile'] = 'topics/profile.json'
        self.save('topics/personalization.json', self.config)
        self.save('topics/profile.json', {'audience': '技术小白'})
        pool.publish(self.root, self.payload, self.now)
        self.save('topics/profile.json', {'audience': '技术小白', 'recent_note': '近期案例变化'})
        self.assertTrue(pool.project(self.root, self.now)['contextChanged'])


if __name__ == '__main__':
    unittest.main()
