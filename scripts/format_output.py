#!/usr/bin/env python3
"""Topic rubric scorer and advisory output checks. Scores are not predictions."""
import argparse,json,math,os,sys
from pathlib import Path
CHECKLIST=['按用户要求的选题数量和形态输出','每题一个受众任务、命题和收益','来源与已有证据/计划分开','去重范围与缺口明确','CTA与入口就绪状态对应','按象限评分，暂定优先不冒充验证首选']
def checklist():return '\n'.join('- [ ] '+x for x in CHECKLIST)
def score_from_json(text, rubric=None):
 try:
  data=json.loads(text)
  if not isinstance(data,dict):raise ValueError('Use quadrant/scores object; legacy 40-point format is retired')
  source=rubric or os.environ.get('MOONLIT_TOPIC_RUBRIC')
  if not source:raise ValueError('Missing rubric: pass --rubric from the active moonlit-topic-radar references/scoring-weights.json')
  weights=json.loads(Path(source).read_text(encoding='utf-8'))[data['quadrant']];scores=data['scores']
  if not isinstance(weights,dict) or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in weights.values()) or not math.isclose(sum(weights.values()),100):raise ValueError('Rubric weights must be finite non-negative numbers summing to 100')
  if set(scores)!=set(weights):raise ValueError('Provide exactly the eight current dimensions')
  if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=10 for v in scores.values()):raise ValueError('Scores must be finite numbers in 0..10')
  raw=round(sum(scores[k]*w/10 for k,w in weights.items()),2);total=raw;caps=[]
  dedup=data.get('dedup_complete') is True;gates=data.get('hard_gates_passed') is True
  if not dedup:total=min(total,79);caps.append('dedup_incomplete')
  if data['quadrant'] in ('Q2','Q3') and data.get('has_evidence_plan') is not True:total=min(total,69);caps.append('evidence_plan_missing')
  if data.get('platform_only') is True:total=min(total,69);caps.append('platform_signal_only')
  if data['quadrant']=='Q1' and scores['信号强度与新鲜度']==0:gates=False;caps.append('no_fresh_event')
  eligible=total>=80 and dedup and gates
  return {'raw_total':raw,'total':total,'eligible_first_choice':eligible,'grade':'首选候选' if eligible else ('暂定候选/观察' if total>=65 else '淘汰'),'caps':caps,'note':'人工评价辅助；未验证传播或成交效果'}
 except (KeyError,TypeError,ValueError,OSError) as e:return {'error':str(e)}
def validate(text):
 checks={k:k in text for k in ['受众','证据','去重','CTA']}
 return {'checks':checks,'missing':[k for k,v in checks.items() if not v],'note':'仅提示字段，不能证明内容质量或语义合格'}
def main():
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='cmd');s.add_parser('checklist');s.add_parser('validate');q=s.add_parser('score');q.add_argument('--json',required=True);q.add_argument('--rubric',type=Path);a=p.parse_args()
 if a.cmd in (None,'checklist'):print(checklist());return 0
 result=validate(sys.stdin.read()) if a.cmd=='validate' else score_from_json(a.json,a.rubric)
 print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if 'error' in result else 0
if __name__=='__main__':raise SystemExit(main())
