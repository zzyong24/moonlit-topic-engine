import unittest,json,sys,os,tempfile,subprocess,shutil
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from format_output import score_from_json
DIMS=['战略匹配','用户收益','信号强度与新鲜度','角度差异','一手证据/可测试性','去重新颖度','当天制作适配','长期资产价值']
class ScoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='rubric test ');self.addCleanup(self.tmp.cleanup)
  self.rubric=Path(self.tmp.name)/'weights.json'
  self.rubric.write_text(json.dumps({q:dict(zip(DIMS,[15,15,5,15,20,10,5,15])) for q in ['Q1','Q2','Q3','Q4']}),encoding='utf-8')
  env=patch.dict(os.environ,{'MOONLIT_TOPIC_RUBRIC':str(self.rubric)});env.start();self.addCleanup(env.stop)
 def test_missing_rubric(self):
  with patch.dict(os.environ,{},clear=True):self.assertIn('error',score_from_json(self.sample()))
 def test_relocated_cli(self):
  script=Path(self.tmp.name)/'format_output.py';shutil.copy2(Path(__file__).resolve().parents[1]/'scripts/format_output.py',script)
  result=subprocess.run([sys.executable,str(script),'score','--rubric',str(self.rubric),'--json',self.sample()],cwd=self.tmp.name,capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['total'],90)
 def test_bad_weights(self):
  self.rubric.write_text(json.dumps({'Q3':dict.fromkeys(DIMS,1)}),encoding='utf-8')
  self.assertIn('error',score_from_json(self.sample()))
 def sample(self,**kw):return json.dumps({'quadrant':'Q3','scores':dict.fromkeys(DIMS,9),'dedup_complete':True,'hard_gates_passed':True,'has_evidence_plan':True,**kw})
 def test_weighted_score(self):self.assertEqual(score_from_json(self.sample())['total'],90)
 def test_incomplete_dedup_cap(self):
  r=score_from_json(self.sample(dedup_complete=False));self.assertEqual(r['total'],79);self.assertFalse(r['eligible_first_choice'])
 def test_missing_evidence_cap(self):self.assertEqual(score_from_json(self.sample(has_evidence_plan=False))['total'],69)
 def test_invalid_score(self):self.assertIn('error',score_from_json(self.sample(scores=dict.fromkeys(DIMS,11))))
 def test_legacy_rejected(self):self.assertIn('error',score_from_json('[{"dim":"情绪","score":4}]'))
 def test_unknown_gates_not_pass(self):
  d=json.loads(self.sample());d.pop('dedup_complete');self.assertFalse(score_from_json(json.dumps(d))['eligible_first_choice'])
if __name__=='__main__':unittest.main()
