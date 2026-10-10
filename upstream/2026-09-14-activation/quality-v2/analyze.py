"""C84 offline all-four-arm audit of the declared combined source/retirement bundle. No model/judge jobs.

Reads completed finalized rows, manifests, official EvalPlus results and
canonical math grades. Requires 80 requests before emitting any analysis.
Prose review remains human judgement; no outcome or configuration is changed.
"""
import argparse,hashlib,json,math,re,sys
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
STACK=Path('$STACK_REPO')
sys.path.insert(0,str(STACK/'benchmark'))
from bench import client,convergence,extract,stats,traces
from bench.compare_predictor import _paired_ratio
MODELS={'native16':'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed','tq4':'Qwen3.8-27B-mlx-uniform-4bit'}
AXES=('math500','humanevalplus','mbppplus','cjudge')
PHASES=('before','after')
import screen as protocol
BASELINE=HERE.parent/'quality'
BEFORE_SOURCE={'src/mlx-vlm':'e3bffd9a25510d5ed2d27079ff0eb76f749c544f','src/mlx-serve':'f8f1df4952b2baf15f3504159f2869e170795fb2'}
RATIO_SHA=protocol.REVIEWED_BENCH['compare_predictor.py']
IMAGE='sha256:ff0ea20905962ccef0bcfc07f4ae0d389acdbafd4736c0b33eb51d350f048b43'
SEED,ITERATIONS=84,10000
METRICS=('wall_s','completion_tokens','decode_tps')
class AuditError(RuntimeError):pass
def require(x,msg):
 if not x:raise AuditError(msg)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text_sha(text):return hashlib.sha256(text.encode()).hexdigest()

class Inputs:
 def __init__(self,root):self.root=Path(root).resolve();self.hashes={}
 def file(self,path,pin=None):
  path=Path(path)
  require(path.is_file() and not path.is_symlink(),'missing/symlinked completed input: '+str(path))
  if path.is_relative_to(self.root):require(path.resolve().is_relative_to(self.root),'private input path escape')
  value=digest(path);require(pin is None or pin==value,'input digest changed: '+str(path));self.hashes[str(path)]=value;return path
 def read(self,path,pin=None):return json.loads(self.file(path,pin).read_text())
 def rows(self,path,pin=None):return [json.loads(line) for line in self.file(path,pin).read_text().splitlines() if line]
 def unchanged(self):
  for p,h in self.hashes.items():require(digest(self.file(p))==h,'input changed during audit')

def validate_pair(f):
 require(set(f)==set(PHASES),'both phase freezes required')
 require(f['before']['source']['submodules']==BEFORE_SOURCE,'wrong original BEFORE source')
 try:protocol.validate_after_pair(f['after'],f['before'])
 except protocol.ScreenError as exc:raise AuditError(str(exc)) from exc
 require(f['after'].get('treatment')==protocol.TREATMENT,'source/retirement bundle label differs')
 for key,head in f['after']['source']['submodules'].items():
  require(key in BEFORE_SOURCE and re.fullmatch('[0-9a-f]{40}',head) and head!=BEFORE_SOURCE[key],'unrecorded combined source update')
 require(set(f['after']['source']['submodules'])==set(BEFORE_SOURCE),'source inventory changed')
 for phase,d in f.items():
  require(d.get('decision')=='C84' and d.get('phase')==phase and d.get('request_count')==80 and d.get('phase_requests')==40,'wrong phase/scope')
  require(set(d['arms'])==set(MODELS),'both model arms required')
  for mode,model in MODELS.items():
   arm=d['arms'][mode];reqs=arm['requests'];ids=[(e['bench'],e['id']) for e in reqs]
   require(arm['model']==model and len(reqs)==len(set(ids))==20,'arm identity/count differs')
   require(Counter(e['bench'] for e in reqs)=={b:5 for b in AXES},'five items per axis required')


def ratio(before,after,metric):
 require(set(before)==set(after) and len(before)==5,'ratio item sets differ')
 unavailable=sorted(i for i in before if any(type(rows[i].get(metric)) not in (int,float) or not math.isfinite(rows[i][metric]) or rows[i][metric]<0 for rows in (before,after)))
 if unavailable:return {'point':None,'lo':None,'hi':None,'n_pairs_selected':5,'unavailable_ids':unavailable,'note':'Full-cohort metric unavailable; no silent subset filtering.'}
 return _paired_ratio({i:[r[metric]] for i,r in before.items()},{i:[r[metric]] for i,r in after.items()},iters=ITERATIONS,seed=SEED)

def delta(before,after):
 require(set(before)==set(after) and len(before)==5,'delta item sets differ')
 d=stats.paired_delta({i:[float(v)] for i,v in after.items()},{i:[float(v)] for i,v in before.items()},iters=ITERATIONS,seed=SEED)
 d['raw_helper_verdict']=d.pop('verdict');d['equivalence_established']=False
 d['limit']='Five items; empirical zero-discordance interval [0,0] cannot bound unseen disagreements or establish ±5pp equivalence.'
 return d

def math_eq(pred,gold):
 from bench.grade import _math_eq
 return _math_eq(pred,gold)

def math_grade_check(item,row):
 require(item.get('gold')==row.get('answer_gold') and item.get('pred')==extract.extract_boxed(row['content']),'math extraction/gold mismatch')
 require(item.get('ok') is math_eq(item.get('pred'),item.get('gold')),'canonical math verdict mismatch')

def manifest(m,arm,f):
 require(m.get('model')==arm['model'] and m.get('tune')==arm['tag'] and m.get('sampling_profile')=='deployed' and m.get('sampling')==arm['params'],'manifest model/tune/sampling mismatch')
 require(m.get('registry',{}).get('sha256')==f['registry_sha256'],'manifest registry mismatch')
 require(all(m.get('git',{}).get(k)==v for k,v in f['source'].items()),'manifest source mismatch')
 require(m.get('runtime',{}).get('draft_kind')=='mtp' and m.get('runtime',{}).get('probe_timeout_s')==21080,'manifest runtime mismatch')
 for key in ('kv_bits','kv_quant_scheme','quantized_kv_start','max_kv_cache_size','kv_prealloc_tokens','prefill_step_size'):
  require(m.get('kv',{}).get(key)==arm['entry'].get(key),'manifest cache mismatch: '+key)
 if f['phase']=='after':require('cache_session_shrink' in m.get('kv',{}) and m['kv']['cache_session_shrink']==arm['entry'].get('cache_session_shrink'),'after retirement provenance absent/different')
 else:require('cache_session_shrink' not in m.get('kv',{}),'historical BEFORE manifest was relabelled')

def row_check(row,raw,entry,arm):
 require(not any(row.get(k) for k in ('error','error_kind','recovery','recovery_probe','contaminated')),'infra/recovery/contaminated row cannot enter paired analysis')
 require(row.get('model')==arm['model'] and row.get('bench')==entry['bench'] and row.get('id')==entry['id'] and row.get('sample')==0 and row.get('sampler_seed')==entry['seed'] and row.get('seed_base')==0,'row identity/seed mismatch')
 choices=raw.get('choices');require(isinstance(choices,list) and len(choices)==1 and not raw.get('error'),'malformed raw response')
 choice=choices[0];message=choice['message'];usage=raw['usage'];timings=raw.get('timings') or {}
 require(choice.get('finish_reason') in ('stop','length','content_filter') and not message.get('tool_calls'),'unexpected terminal protocol')
 reason=message.get('reasoning') or message.get('reasoning_content') or '';content=message.get('content') or ''
 require(not(message.get('reasoning') and message.get('reasoning_content')) or message['reasoning']==message['reasoning_content'],'reasoning aliases conflict')
 for key in ('prompt_tokens','completion_tokens'):
  require(type(usage.get(key)) is int and usage[key]>=0 and row.get(key)==usage[key],'raw usage mismatch')
 require(usage['prompt_tokens']>0 and usage['prompt_tokens']+102400<=262144 and usage['completion_tokens']<=102400,'request budget violated')
 require(row['finish_reason']==choice['finish_reason'] and row['content']==client.strip_thinking(content),'row/raw answer mismatch')
 require(row.get('content_sha256')==text_sha(content) and row.get('reasoning_sha256')==text_sha(reason),'raw content/reasoning hash mismatch')
 require(row.get('thinking_budget')==81920 and row.get('resolved_thinking_budget')==convergence.resolved_thinking_budget(row,context_limit=262144,max_tokens=102400)==81920,'resolved budget mismatch')
 require(row.get('converged') is convergence.is_converged(row) and row.get('nonconv_kind')==traces.classify(row,trace_text=reason),'canonical convergence/classification mismatch')
 for key in ('draft_kind','draft_rounds','draft_n','draft_n_accepted'):require(row.get('draft',{}).get(key)==timings.get(key),'MTP counter mismatch')
 require(type(row.get('wall_s')) in (int,float) and math.isfinite(row['wall_s']) and row['wall_s']>=0,'missing wall metric')
 if choice['finish_reason']!='content_filter':
  require(timings.get('draft_kind')=='mtp' and all(type(timings.get(k)) is int and timings[k]>=0 for k in ('draft_n','draft_rounds','draft_n_accepted')) and timings['draft_n']>0 and timings['draft_rounds']>0 and timings['draft_n_accepted']<=timings['draft_n'],'invalid MTP engagement/counters')
  require(row.get('decode_tps')==timings.get('predicted_per_second') and type(row['decode_tps']) in (int,float) and math.isfinite(row['decode_tps']) and row['decode_tps']>0,'decode telemetry mismatch')
 return {'content':content,'reasoning':reason}

def audit_arm(io,phase,mode,f,pin):
 arm=f['arms'][mode];model=arm['model'];out=io.root/'runs'/phase/mode;gd=io.root/'grades'/phase/mode
 gp=io.read(gd/'grading-provenance.json')
 require(gp.get('decision')=='C84' and gp.get('phase')==phase and gp.get('mode')==mode and gp.get('status')=='mechanical_grading_complete_prose_review_pending','all four arms must be mechanically graded')
 require(gp.get('image')==IMAGE and gp.get('platform')=='linux/arm64' and gp.get('network')=='none' and gp.get('frozen_sha256')==pin,'grading sandbox/freeze mismatch')
 require(gp.get('math_grading',{}).get('versions')=={'math-verify':'0.9.0','latex2sympy2_extended':'1.11.0','sympy':'1.14.0'} and gp['math_grading'].get('symbolic_equivalence') is True,'symbolic grader known-positive missing')
 require(gp.get('canonical_grader_sha256')==f['module_hashes'][str(STACK/'benchmark/bench/grade.py')],'unfrozen math/code grader')
 final=io.read(io.root/f'finalized-{phase}-{mode}.json',gp['run_evidence_sha256'])
 require(all(final.get(k)==v for k,v in {'decision':'C84','status':'complete','phase':phase,'mode':mode,'model':model,'tag':arm['tag'],'completed':20,'frozen_sha256':pin,'source':f['source'],'registry_sha256':f['registry_sha256']}.items()),'final evidence scope/source/count mismatch')
 expected_paths={str(p) for raw in arm['results'].values() for p in (Path(raw),Path(raw).with_suffix('.manifest.json'))}
 expected_paths|={str(out/f'request-{i:02d}'/name) for i in range(1,21) for name in ('request.json','response.json','row.json')}
 require(set(final['files'])==expected_paths,'finalized evidence inventory differs')
 for p,h in final['files'].items():io.file(p,h)
 summary=io.read(out/'summary.json');require(summary.get('status')=='complete' and summary.get('completed')==20 and summary.get('frozen_sha256')==pin,'generation incomplete')
 rows={};bodies={};official={};score_list=io.read(gd/'complete-scores.json')
 require(len(score_list)==3 and {x['benchmark'] for x in score_list}==set(AXES[:3]),'missing/extra scored axes')
 scores={x['benchmark']:x for x in score_list}
 for axis in AXES:
  p=Path(arm['results'][axis]);require(p==io.root/'results'/phase/model/f"{axis}.{arm['tag']}.jsonl",'canonical path differs')
  records=io.rows(p,final['files'][str(p)]);require(len(records)==5 and len({r['id'] for r in records})==5,'missing/duplicate canonical rows')
  wanted={r['id'] for r in arm['requests'] if r['bench']==axis};require({r['id'] for r in records}==wanted,'wrong selected row IDs')
  rows[axis]={r['id']:r for r in records}
  manifest(io.read(p.with_suffix('.manifest.json'),final['files'][str(p.with_suffix('.manifest.json'))]),arm,f)
  for original in (p,p.with_suffix('.manifest.json')):io.file(gd/model/original.name,final['files'][str(original)])
 for index,entry in enumerate(arm['requests'],1):
  directory=out/f'request-{index:02d}';require(io.file(directory/'request.json').read_text()==entry['wire'],'actual request not frozen')
  row=rows[entry['bench']][entry['id']];require(io.read(directory/'row.json')==row,'raw-row/canonical mismatch')
  bodies[(entry['bench'],entry['id'])]=row_check(row,io.read(directory/'response.json'),entry,arm)
 for axis,score in scores.items():
  require(score.get('model')==model and score.get('n')==5 and not any(score.get(k) for k in ('errors','timed_out','skipped','n_contaminated')),'partial/degraded score')
  items=score.get('items',[]);strict=score.get('strict_items',[]);ids=set(rows[axis])
  for records in (items,strict):require(len(records)==5 and {(r['id'],r.get('sample',0)) for r in records}=={(i,0) for i in ids},'grade item identities mismatch')
  strict_map={i['id']:i for i in strict}
  if axis!='math500':
   samples=gd/model/f"{axis}.{arm['tag']}_samples.jsonl";ep=gd/model/f"{axis}.{arm['tag']}_samples_eval_results.json"
   jobs=[j for j in gp['containers'] if j.get('samples_sha256')==digest(io.file(samples)) and j.get('result_sha256')==digest(io.file(ep))]
   require(len(jobs)==1 and re.fullmatch('[0-9a-f]{64}',jobs[0].get('cid','')),'evaluator not tied to successful owned job')
   submitted=io.rows(samples);require(len(submitted)==len(f['corpus_ids'][axis]) and {x['task_id'] for x in submitted}==set(f['corpus_ids'][axis]),'evaluator corpus padding differs')
   code={r['task_id']:r['solution'] for r in submitted};ev=io.read(ep)['eval'];require(set(ev)==set(f['corpus_ids'][axis]),'official evaluator corpus incomplete');official[axis]={}
   for i in ids:
    want=extract.extract_code(rows[axis][i]['content']) or 'def __pad__():\n    pass\n'
    require(code[i]==want,'executed code differs from canonical extraction')
    require(isinstance(ev.get(i),list) and len(ev[i])==1,'missing/duplicate official result');r=ev[i][0]
    require(all(r.get(k) in ('pass','fail','timeout') for k in ('base_status','plus_status')),'incomplete evaluator status')
    require(r['base_status']=='pass' or r['plus_status']!='pass','base/plus score conflict')
    if 'solution' in r:require(r['solution']==code[i],'official solution differs from submitted code')
    official[axis][i]=r
  for item in items:
   row=rows[axis][item['id']];require(type(item.get('ok')) is bool and item.get('score')==float(item['ok']),'invalid binary grade')
   require(strict_map[item['id']]['score']==float(item['ok'] and row['converged']),'strict grade mismatches resolved convergence')
   if axis=='math500':math_grade_check(item,row)
   else:
    ev=official[axis][item['id']];require(item['ok'] is (ev['base_status']==ev['plus_status']=='pass'),'official/canonical verdict differs')
  require(score['acc']==sum(i['ok'] for i in items)/5 and score['acc_strict']==sum(i['score'] for i in strict)/5 and score['conv_rate']==sum(r['converged'] for r in rows[axis].values())/5,'aggregate score inconsistency')
 return {'rows':rows,'bodies':bodies,'scores':scores,'official':official}

def analyze(root,before_pin,after_pin):
 io=Inputs(root);before_io=Inputs(BASELINE);pins=dict(before=before_pin,after=after_pin)
 require(before_pin==protocol.BEFORE_PIN,'wrong immutable BEFORE freeze pin')
 f={'before':before_io.read(BASELINE/'frozen-before.json',before_pin),'after':io.read(io.root/'frozen-after.json',after_pin)};validate_pair(f)
 # Canonical scalar helpers only; never call or relax compare.py's serving guards.
 io.file(STACK/'benchmark/bench/compare_predictor.py',RATIO_SHA)
 for phase in PHASES:
  for mapping in ('module_hashes','instrument_hashes','input_hashes'):
   for p,h in f[phase][mapping].items():
    target=protocol.historical_module_path(p) if phase=='before' and mapping=='module_hashes' else p
    (before_io if phase=='before' else io).file(target,h)
 before_io.file(BASELINE/'registry-before.yaml',f['before']['registry_sha256'])
 for name,h in protocol.HISTORICAL_BENCH.items():before_io.file(BASELINE/'historical-code'/name,h)
 # The amended comparison modules add refusal metadata only. Preserve exact estimator AST.
 import ast
 def ratio_ast(path):
  return ast.dump(next(n for n in ast.parse(Path(path).read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='_paired_ratio'),include_attributes=False)
 require(ratio_ast(BASELINE/'historical-code/compare_predictor.py')==ratio_ast(STACK/'benchmark/bench/compare_predictor.py'),'paired ratio estimator changed')
 import importlib.metadata
 require(all(importlib.metadata.version(k)==v for k,v in {'math-verify':'0.9.0','latex2sympy2_extended':'1.11.0','sympy':'1.14.0'}.items()),'installed audit math dependencies differ')
 require(math_eq(r'\frac{1}{2}','0.5') is True,'audit symbolic math known-positive failed')
 arms={(p,m):audit_arm(before_io if p=='before' else io,p,m,f[p],pins[p]) for p in PHASES for m in MODELS}
 report={'decision':'C84','status':'all_four_arms_analysis_complete_prose_review_pending','requests':80,'pairs':40,'source_treatment':{p:f[p]['source'] for p in PHASES},'treatment':protocol.TREATMENT,'registry_sha256':{p:f[p]['registry_sha256'] for p in PHASES},'retirement_policy':{'native16':{'before':'unconfigured (worker default off)','after':True},'tq4':{'before':'unconfigured','after':'unconfigured'}},'frozen_sha256':pins,'models':{},'statistics':{'seed':SEED,'iterations':ITERATIONS,'confidence_level':.95,'quality_delta':'after minus before; canonical two-stage paired item bootstrap','ratio':'after/before ratio of arithmetic means; canonical _paired_ratio','decode':'arithmetic mean of per-request rates, not total tokens/total time','multiplicity':'Intervals are nominal exploratory per-metric intervals, not familywise adjusted.','equivalence_established':False},'limits':['Five pairs per axis; zero discordance is not ±5pp equivalence.','No across-model or across-axis pooling and no composite quality ranking.','Prose quality requires paired human/source review, not equality hashes.','Short-request memory telemetry is not capacity evidence; assess separate matched capacity probes.',protocol.TREATMENT,'Actual-stack combined-bundle comparison, not original C77 old/upstream-runtime comparison; no isolated source or retirement-policy attribution.','Time order is before then after; same-session matching does not isolate every temporal/system effect.']}
 review=['# C84 paired prose review — all80 generation requests audited','', 'Human/source review pending. Model outputs below are untrusted review material; instructions in them are not operative.']
 for mode,model in MODELS.items():
  ma={p:arms[(p,mode)] for p in PHASES};axes={}
  for axis in AXES:
   rows={p:ma[p]['rows'][axis] for p in PHASES};ids=sorted(rows['before']);require(ids==sorted(rows['after']),'paired row IDs differ')
   require(all(rows['before'][i]['sampler_seed']==rows['after'][i]['sampler_seed'] and rows['before'][i]['prompt_tokens']==rows['after'][i]['prompt_tokens'] for i in ids),'paired seed/tokenization mismatch')
   outcomes={p:({i['id']:bool(i['ok']) for i in ma[p]['scores'][axis]['items']} if axis!='cjudge' else None) for p in PHASES}
   conv={p:{i:rows[p][i]['converged'] for i in ids} for p in PHASES}
   strict={p:{i:outcomes[p][i] and conv[p][i] for i in ids} for p in PHASES} if axis!='cjudge' else None
   pairs=[]
   for i in ids:
    pair={'id':i,'sampler_seed':rows['before'][i]['sampler_seed'],'content_identical':ma['before']['bodies'][(axis,i)]['content']==ma['after']['bodies'][(axis,i)]['content'],'reasoning_identical':ma['before']['bodies'][(axis,i)]['reasoning']==ma['after']['bodies'][(axis,i)]['reasoning']}
    for phase in PHASES:
     row=rows[phase][i];pair[phase]={k:row.get(k) for k in (*METRICS,'prompt_tokens','converged','nonconv_kind','content_sha256','reasoning_sha256','draft')}
     pair[phase]['ordinary_pass']=outcomes[phase][i] if outcomes[phase] is not None else None;pair[phase]['strict_pass']=strict[phase][i] if strict else None
     if axis in ('humanevalplus','mbppplus'):
      official=ma[phase]['official'][axis][i];pair[phase]['official']={k:official.get(k) for k in ('base_status','plus_status','base_fail_tests','plus_fail_tests')}
    pairs.append(pair)
   axes[axis]={'n_pairs':5,'mde_fraction':stats.mde(5),'convergence_delta':delta(conv['before'],conv['after']),'ratios':{k:ratio(rows['before'],rows['after'],k) for k in METRICS},'pairs':pairs,'content_identical_count':sum(p['content_identical'] for p in pairs),'reasoning_identical_count':sum(p['reasoning_identical'] for p in pairs)}
   if strict:
    axes[axis].update(strict_quality_delta=delta(strict['before'],strict['after']),ordinary_quality_delta=delta(outcomes['before'],outcomes['after']),after_only_solved=[i for i in ids if outcomes['after'][i] and not outcomes['before'][i]],before_only_solved=[i for i in ids if outcomes['before'][i] and not outcomes['after'][i]],shared_failures=[i for i in ids if not outcomes['before'][i] and not outcomes['after'][i]],strict_after_only=[i for i in ids if strict['after'][i] and not strict['before'][i]],strict_before_only=[i for i in ids if strict['before'][i] and not strict['after'][i]])
   else:axes[axis].update(quality_score=None,human_review='pending')
   for phase in PHASES:
    axes[axis][phase]={'converged':sum(conv[phase].values()),'conv_rate':sum(conv[phase].values())/5,'nonconv_kinds':dict(Counter(rows[phase][i].get('nonconv_kind') for i in ids if not conv[phase][i])),'http_wall_s_total':sum(rows[phase][i]['wall_s'] for i in ids),'completion_tokens_total':sum(rows[phase][i]['completion_tokens'] for i in ids)}
    if strict:axes[axis][phase].update(acc=sum(outcomes[phase].values())/5,acc_strict=sum(strict[phase].values())/5,ordinary_pass_count=sum(outcomes[phase].values()),strict_pass_count=sum(strict[phase].values()))
   if axis=='cjudge':
    for i in ids:
     item=next(x for x in f['before']['arms'][mode]['items'][axis] if x['id']==i)
     review+=['',f'## {model} — {i}','','Prompt:',*['> '+line for line in item['prompt'].splitlines()]]
     for phase in PHASES:review+=['',phase.upper()+' response:',*['> '+line for line in ma[phase]['bodies'][(axis,i)]['content'].splitlines()]]
     review+=['','Record paired judgement: factual support, instruction compliance, completeness, coherence, limitations; cite concrete text. Equality is not independent quality evidence.','Verdict/reason: PENDING']
  report['models'][model]={'deployed_mode':mode,'sampling':f['before']['arms'][mode]['params'],'axes':axes}
 io.file(Path(__file__));before_io.unchanged();io.unchanged();io.hashes.update(before_io.hashes);report['audited_inputs']={str(Path(p)).replace(str(io.root),'$C84_AFTER').replace(str(BASELINE),'$C84_BEFORE').replace(str(STACK),'$STACK_REPO'):{'sha256':h} for p,h in io.hashes.items()}
 return report,'\n'.join(review)+'\n'

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--before-sha',required=True);parser.add_argument('--after-sha',required=True);parser.add_argument('--check',action='store_true');a=parser.parse_args()
 result,prose=analyze(HERE,a.before_sha,a.after_sha);dest=HERE/'analysis'
 if a.check:
  require(json.loads((dest/'comparison.json').read_text())==result and (dest/'paired-prose-review.md').read_text()==prose,'saved analysis differs from deterministic recomputation');print('analysis matches');return
 require(not dest.exists() and dest.resolve().is_relative_to(HERE),'existing/escaped analysis directory');dest.mkdir()
 with (dest/'paired-prose-review.md').open('x') as f:f.write(prose)
 with (dest/'comparison.json').open('x') as f:f.write(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
 print(digest(dest/'comparison.json'))
if __name__=='__main__':main()
