import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1]/'scripts/personalize_topics.py'
spec=importlib.util.spec_from_file_location('personalize',PATH);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Routing(unittest.TestCase):
    def test_visualization_preference_survives_context_assembly(self):
        with tempfile.TemporaryDirectory(prefix='visual topic space ') as tmp:
            root=Path(tmp);(root/'profile.json').write_text('{}')
            cfg={'profile':'profile.json','preferences':{},'production':{},'themes':[],
                 'sources':[], 'visualization_policy':{'default_for_topic_requests':True}}
            self.assertTrue(m.assemble(root,cfg,'2026-10-02')['visualization_policy']['default_for_topic_requests'])
            cfg.pop('visualization_policy')
            self.assertEqual(m.assemble(root,cfg,'2026-10-02')['visualization_policy'],{})

    def setUp(self):
        self.pack={'context_hash':'v1','date':'2026-10-02','themes':[{'id':'life'}],
          'evidence':[{'id':'own','status':'available','attribution':'observed','kind':'project_record'},
                      {'id':'ref','status':'available','attribution':'external','kind':'benchmark'}],
          'recent_works':[],'production':{'prep_minutes':240},'preferences':{'max_per_theme':2},
          'dedup_complete':False,'gaps':[]}
        self.candidates=[{'id':'one','title':'人生里的选择','theme_id':'life','claim_family':'choice'}]
        self.review={'candidate_id':'one','context_hash':'v1','reviewer':'author','checked_at':'2026-10-02',
          'fit_decision':'explore',
          'evidence_ids':['own'],'author_basis_evidence_ids':['own'],'core_thesis':'亲历的取舍',
          'duplicate_status':'new','evidence_state':'ready','facts_checked':True,
          'dimensions':{k:{'value':5,'reason':'Relevant sourced reason'} for k in m.WEIGHTS},
          'production_plan':{'prep_minutes':120,'access_ready':True,'task':'Compare outcomes',
            'steps':['Record source'],'visible_result':'Actual change','done_when':'Source/result agree',
            'opening':'A concrete choice','format':'Talking head'}}
    def rank(self):return m.rank(self.pack,self.candidates,[self.review])
    def test_ready_does_not_equal_approved_and_incomplete_cap(self):
        r=self.rank()['candidates'][0];self.assertEqual(r['match_queue'],'record_candidate')
        self.assertEqual(r['match_score'],79);self.assertEqual(r['recommendation_label'],'tentative')
    def test_broad_life_theme_allowed(self):self.assertEqual(self.rank()['shortlist'],['one'])
    def test_missing_semantic_review_is_not_keyword_rank(self):
        r=m.rank(self.pack,self.candidates,[])['candidates'][0];self.assertIsNone(r['match_score'])
    def test_stale_context_rejected(self):
        self.review['context_hash']='old'
        with self.assertRaises(ValueError):self.rank()
    def test_proposal_or_benchmark_cannot_prove_firsthand(self):
        self.review['evidence_ids']=['ref'];self.review['author_basis_evidence_ids']=['ref']
        with self.assertRaises(ValueError):self.rank()
    def test_same_thesis_blocks_even_different_title(self):
        self.pack['recent_works']=[{'thesis':'亲历的取舍'}]
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'skip')
    def test_pending_pool_is_not_reissued_as_new_topic(self):
        self.pack['recent_topics']=[{'id':'T-old','status':'recommended','thesis':'亲历的取舍','candidate_id':'other'}]
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'existing_pool')
        self.pack['recent_topics'][0]['candidate_id']='one'
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'record_candidate')
    def test_budget_overflow_is_future_work(self):
        self.review['production_plan']['prep_minutes']=300
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'deep_build')
    def test_unavailable_access_observe(self):
        self.review['production_plan']['access_ready']=False
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'observe')
    def test_unknown_fit_cannot_enter_recording_queue(self):
        self.review['fit_decision']='unknown'
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'observe')
    def test_planned_test_does_not_turn_into_firsthand(self):
        self.review['evidence_state']='planned';self.review['facts_checked']=False
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'test_first')
    def test_fabricated_evidence_and_nan_rejected(self):
        self.review['evidence_ids']=['fake']
        with self.assertRaises(ValueError):self.rank()
        self.review['evidence_ids']=['own'];self.review['dimensions']['interest']['value']=float('nan')
        with self.assertRaises(ValueError):self.rank()
    def test_whole_context_budget_and_project_isolation(self):
        with tempfile.TemporaryDirectory(prefix='topic context ') as tmp:
            root=Path(tmp);(root/'profile.json').write_text('{}')
            cfg={'profile':'profile.json','preferences':{},'production':{},'themes':[],
                 'sources':[],'memory_scope':{'project_keys':['allowed'],'frameworks':['life_map']}}
            with self.assertRaises(ValueError):m.assemble(root,cfg,'2026-10-02',[{'project_key':'other'}])
            with self.assertRaises(ValueError):m.assemble(root,cfg,'2026-10-02',max_chars=1)
            r=m.assemble(root,cfg,'2026-10-02');self.assertFalse(r['dedup_complete'])
    def test_theme_diversity_limits_duplicate_family(self):
        self.candidates += [{'id':'two','title':'另一个标题','theme_id':'life','claim_family':'choice'}]
        other=copy.deepcopy(self.review);other['candidate_id']='two'
        r=m.rank(self.pack,self.candidates,[self.review,other]);self.assertEqual(len(r['shortlist']),1)
    def test_feedback_cannot_invent_topic_or_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):m.feedback(tmp,'unknown','can_explain','Reason','2026-10-02')
            with self.assertRaises(ValueError):m.feedback(tmp,'unknown','published','Reason','2026-10-02')
            root=Path(tmp);p=root/'topics/2026/2026-10-02';p.mkdir(parents=True)
            (p/'topics.json').write_text(json.dumps({'topics':[{'id':'T-20261002-001'}]}))
            m.feedback(root,'T-20261002-001','can_explain','用户说愿意讲','2026-10-02')
            self.assertEqual(len((root/'topics/selection-feedback.jsonl').read_text().splitlines()),1)

    def practical(self):
        self.pack['profile']={'audience_contract':{'version':2,'practical_required':True}}
        self.review['audience_review']={
            'contract_version':2,'audience_fit':'pass','practical_fit':'pass',
            'reason':'输入为录音，输出为待办表；观众使用浏览器，不需要开发知识',
            'viewer_task':'整理会议待办','input':'一段示例录音','output':'待办表格',
            'steps':['上传音频','整理并核对'], 'verification':'逐项核对人名、日期和任务',
            'viewer_entry':{'status':'verified','instructions':'打开已核对入口并上传示例',
                            'prerequisites':'浏览器和音频','cost':'当前免费额度已核对','language':'支持中文'},
            'demand_basis':{'kind':'agent_hypothesis','detail':'演示需求假设，未声称评论高频'}}
    def test_high_interest_cannot_override_wrong_audience(self):
        self.practical();self.review['audience_review']['audience_fit']='fail'
        r=self.rank();self.assertEqual(r['shortlist'],[])
        self.assertEqual(r['candidates'][0]['match_queue'],'skip')
    def test_author_ready_does_not_prove_viewer_entry(self):
        self.practical();self.review['audience_review']['viewer_entry']['status']='unknown'
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'observe')
    def test_existing_review_without_audience_check_stays_out(self):
        self.practical();del self.review['audience_review']
        self.assertEqual(self.rank()['shortlist'],[])
    def test_viewer_entry_planned_needs_test_and_remains_test_first(self):
        self.practical();self.review['audience_review']['viewer_entry'].update(
            status='planned',test_actions=['从零打开入口验证中文与导出'])
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'test_first')
        del self.review['audience_review']['viewer_entry']['test_actions']
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'observe')
    def test_real_practical_task_can_record_without_comment_popularity(self):
        self.practical();self.assertEqual(self.rank()['candidates'][0]['match_queue'],'record_candidate')
    def test_rewording_title_without_result_does_not_pass(self):
        self.practical();self.candidates[0]['title']='技术小白必看干货'
        del self.review['audience_review']['output']
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'observe')
    def test_audience_version_change_requires_review(self):
        self.practical();self.review['audience_review']['contract_version']=1
        with self.assertRaises(ValueError):self.rank()
    def test_claimed_question_needs_actual_evidence(self):
        self.practical();self.review['audience_review']['demand_basis']['kind']='observed_question'
        with self.assertRaises(ValueError):self.rank()
    def test_rejected_thesis_cannot_return_with_a_new_title(self):
        self.pack['recent_topics']=[{'id':'T-rejected','status':'rejected','thesis':'亲历的取舍','candidate_id':'old'}]
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'skip')
        self.review['duplicate_status']='substantive_update';self.review['changed_evidence']='新的观众任务与实测'
        self.assertEqual(self.rank()['candidates'][0]['match_queue'],'record_candidate')
    def test_grid_ids_and_roles_are_real_references(self):
        self.pack['paired_grids']={'version':1,'audience':{'cells':[{'id':'meeting'}]},
                                 'industry':{'cells':[{'id':'organize'}]}}
        self.candidates[0]['grid_pair']={'grid_version':1,'audience_cell_id':'meeting',
            'capability_cell_id':'organize','relation_reason':'Audio to task table'}
        self.assertEqual(self.rank()['shortlist'],['one'])
        self.candidates[0]['grid_pair']['audience_cell_id']='organize'
        with self.assertRaises(ValueError):self.rank()

    def test_enabled_pair_method_cannot_shortlist_an_unpaired_candidate(self):
        self.pack['selection_method']={'mode':'paired_grids','require_grid_pair':True}
        with self.assertRaisesRegex(ValueError,'requires a grid relation'):self.rank()
        self.assertEqual(m.rank(self.pack,self.candidates,[])['shortlist'],[])

    def test_pair_method_accepts_current_pair_and_rejects_stale_or_empty_reason(self):
        self.pack['selection_method']={'mode':'paired_grids','require_grid_pair':True}
        self.pack['paired_grids']={'version':2,'audience':{'cells':[{'id':'learning'}]},
                                 'industry':{'cells':[{'id':'extract'}]}}
        pair={'grid_version':2,'audience_cell_id':'learning','capability_cell_id':'extract',
              'relation_reason':'将教程材料整理成可以亲手完成的步骤'}
        self.candidates[0]['grid_pair']=pair
        self.assertEqual(self.rank()['shortlist'],['one'])
        pair['grid_version']=1
        with self.assertRaises(ValueError):self.rank()
        pair['grid_version']=2;pair['relation_reason']='  '
        with self.assertRaises(ValueError):self.rank()

    def test_context_preserves_account_method_without_enabling_it_for_other_accounts(self):
        with tempfile.TemporaryDirectory(prefix='paired grid context ') as tmp:
            root=Path(tmp);(root/'profile.json').write_text('{}')
            cfg={'profile':'profile.json','preferences':{},'production':{},'themes':[],
                 'sources':[],'selection_method':{'mode':'paired_grids','require_grid_pair':True}}
            pack=m.assemble(root,cfg,'2026-10-02')
            self.assertEqual(pack['selection_method'],cfg['selection_method'])
            del cfg['selection_method']
            self.assertEqual(m.assemble(root,cfg,'2026-10-02')['selection_method'],{})

if __name__=='__main__':unittest.main()
