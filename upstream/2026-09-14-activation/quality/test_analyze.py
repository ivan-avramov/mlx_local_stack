import copy
import pytest
import analyze


@pytest.fixture(autouse=True)
def mocked_symbolic_math(monkeypatch):
 # Synthetic fixture grades only. Never import heavy symbolic math while the model runs.
 monkeypatch.setattr(analyze,'math_eq',lambda a,b:(a,b)==(r'\frac{1}{2}','0.5') or a==b)

def fakes():
 states={p:{'phase':p,'decision':'C84','request_count':80,'phase_requests':40,'selection_sha256':'selection','registry_sha256':'registry','runtime':{'versions':{'mlx':'0.32.2'}},'module_hashes':{'stats':'same'},'corpus_ids':{},'source':{'submodules':{'src/mlx-vlm':analyze.SOURCES[p],'src/mlx-serve':analyze.SERVE},'serving_path':{'src/mlx-vlm':p,'src/mlx-serve':'same'}},'arms':{}} for p in analyze.PHASES}
 for f in states.values():
  for mode,model in analyze.MODELS.items():
   f['arms'][mode]={'model':model,'params':{'thinking_budget':81920},'entry':{'kv_bits':0 if mode=='native16' else 4},'items':{},'requests':[{'bench':b,'id':f'{b}/{i}','seed':i,'wire':f'{b}/{i}'} for i in range(5) for b in analyze.AXES]}
 return states


def test_clean_source_treatment():analyze.validate_pair(fakes())
@pytest.mark.parametrize('field',['runtime','registry','source','request','model','sampling','entry'])
def test_pair_drift_rejected(field):
 f=fakes();a=f['after']
 if field=='runtime':a['runtime']['versions']['mlx']='other'
 elif field=='registry':a['registry_sha256']='different'
 elif field=='source':a['source']['submodules']['src/mlx-serve']='other'
 elif field=='request':a['arms']['native16']['requests'][0]['wire']='changed'
 elif field=='model':a['arms']['native16']['model']='other'
 elif field=='sampling':a['arms']['native16']['params']['thinking_budget']=80
 else:a['arms']['native16']['entry']['kv_bits']=4
 with pytest.raises(analyze.AuditError):analyze.validate_pair(f)


def test_ratios_use_after_over_before_and_keep_all_pairs():
 a={str(i):{'wall_s':float(i+1)} for i in range(5)};b={i:{'wall_s':r['wall_s']*2} for i,r in a.items()}
 r=analyze.ratio(a,b,'wall_s');assert r['point']==r['lo']==r['hi']==2 and r['n_items']==5
 b['0']['wall_s']=None;r=analyze.ratio(a,b,'wall_s');assert r['point'] is None and r['unavailable_ids']==['0'] and r['n_pairs_selected']==5


def test_zero_discordance_never_establishes_equivalence():
 d=analyze.delta({str(i):True for i in range(5)},{str(i):True for i in range(5)})
 assert d['delta']==d['lo']==d['hi']==0 and 'verdict' not in d and d['raw_helper_verdict']=='equivalent'
 assert d['equivalence_established'] is False


def test_partial_dataset_emits_no_result(tmp_path):
 with pytest.raises(analyze.AuditError):analyze.analyze(tmp_path,'a'*64,'b'*64)
 assert not (tmp_path/'analysis').exists()

import hashlib,json
from pathlib import Path

def put(p,obj,jsonl=False):
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(''.join(json.dumps(x)+'\n' for x in obj) if jsonl else json.dumps(obj))
 return analyze.digest(p)


def complete_fixture(root):
 # Reuse frozen input shapes only. Every response and grade here is synthetic.
 original=json.loads((analyze.HERE/'frozen-before.json').read_text());pins={}
 for phase in analyze.PHASES:
  f=copy.deepcopy(original);f['phase']=phase;f['source']['submodules']['src/mlx-vlm']=analyze.SOURCES[phase];f['source']['serving_path']['src/mlx-vlm']=phase
  f['input_hashes']={};f['instrument_hashes']={}
  for mode,a in f['arms'].items():
   a['tag']=f'fake-{phase}-{mode}';a['results']={b:str(root/'results'/phase/a['model']/f"{b}.{a['tag']}.jsonl") for b in analyze.AXES}
  pins[phase]=put(root/f'frozen-{phase}.json',f)
  for mode,a in f['arms'].items():
   out=root/'runs'/phase/mode;gd=root/'grades'/phase/mode;rows={b:[] for b in analyze.AXES};files={}
   for index,entry in enumerate(a['requests'],1):
    b=entry['bench'];item=next(i for i in a['items'][b] if i['id']==entry['id']);content='Synthetic prose answer.' if b=='cjudge' else ('\\boxed{'+str(item['answer'])+'}' if b=='math500' else '```python\ndef f():\n    return 1\n```')
    raw={'choices':[{'index':0,'finish_reason':'stop','message':{'content':content,'reasoning':'Synthetic reasoning.'}}],'usage':{'prompt_tokens':100,'completion_tokens':10},'timings':{'predicted_per_second':40.,'draft_kind':'mtp','draft_rounds':3,'draft_n':6,'draft_n_accepted':5}}
    r={'model':a['model'],'bench':b,'id':entry['id'],'sample':0,'sampler_seed':entry['seed'],'seed_base':0,'content':analyze.client.strip_thinking(content),'content_sha256':analyze.text_sha(content),'reasoning_sha256':analyze.text_sha('Synthetic reasoning.'),'prompt_tokens':100,'completion_tokens':10,'finish_reason':'stop','wall_s':2.,'decode_tps':40.,'thinking_budget':81920,'resolved_thinking_budget':81920,'converged':True,'draft':{k:v for k,v in raw['timings'].items() if k!='predicted_per_second'},'answer_gold':item.get('answer')}
    r['nonconv_kind']=analyze.traces.classify(r,trace_text='Synthetic reasoning.');rows[b].append(r)
    directory=out/f'request-{index:02d}';directory.mkdir(parents=True)
    p=directory/'request.json';p.write_text(entry['wire']);files[str(p)]=analyze.digest(p)
    for name,obj in [('response.json',raw),('row.json',r)]:p=directory/name;files[str(p)]=put(p,obj)
   for b,rs in rows.items():
    p=Path(a['results'][b]);files[str(p)]=put(p,rs,True)
    m={'model':a['model'],'tune':a['tag'],'sampling_profile':'deployed','sampling':a['params'],'registry':{'sha256':f['registry_sha256']},'git':f['source'],'runtime':{'draft_kind':'mtp','probe_timeout_s':21080},'kv':{k:a['entry'][k] for k in ('kv_bits','kv_quant_scheme','quantized_kv_start','max_kv_cache_size','kv_prealloc_tokens','prefill_step_size')}}
    mp=p.with_suffix('.manifest.json');files[str(mp)]=put(mp,m)
    for src in (p,mp):dest=gd/a['model']/src.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(src.read_bytes())
   put(out/'summary.json',{'status':'complete','completed':20,'frozen_sha256':pins[phase]})
   final={'decision':'C84','status':'complete','phase':phase,'mode':mode,'model':a['model'],'tag':a['tag'],'completed':20,'frozen_sha256':pins[phase],'source':f['source'],'registry_sha256':f['registry_sha256'],'files':files}
   finalpin=put(root/f'finalized-{phase}-{mode}.json',final);scores=[];jobs=[]
   for b in analyze.AXES[:3]:
    items=[]
    for r in rows[b]:
     i={'id':r['id'],'sample':0,'ok':True,'score':1.}
     if b=='math500':i.update(gold=r['answer_gold'],pred=analyze.extract.extract_boxed(r['content']))
     items.append(i)
    scores.append({'model':a['model'],'benchmark':b,'n':5,'items':items,'strict_items':items,'acc':1.,'acc_strict':1.,'conv_rate':1.})
    if b!='math500':
     selected={r['id']:analyze.extract.extract_code(r['content']) for r in rows[b]}
     samples=[{'task_id':i,'solution':selected.get(i,'def __pad__():\n    pass\n')} for i in f['corpus_ids'][b]]
     sp=gd/a['model']/f"{b}.{a['tag']}_samples.jsonl";ep=sp.with_name(f"{b}.{a['tag']}_samples_eval_results.json")
     ev={r['task_id']:[{'base_status':'pass' if r['task_id'] in selected else 'fail','plus_status':'pass' if r['task_id'] in selected else 'fail','solution':r['solution']}] for r in samples}
     jobs.append({'cid':'a'*64,'samples_sha256':put(sp,samples,True),'result_sha256':put(ep,{'eval':ev})})
   put(gd/'complete-scores.json',scores)
   put(gd/'grading-provenance.json',{'decision':'C84','phase':phase,'mode':mode,'status':'mechanical_grading_complete_prose_review_pending','image':analyze.IMAGE,'platform':'linux/arm64','network':'none','frozen_sha256':pins[phase],'run_evidence_sha256':finalpin,'canonical_grader_sha256':f['module_hashes'][str(analyze.STACK/'benchmark/bench/grade.py')],'math_grading':{'versions':{'math-verify':'0.9.0','latex2sympy2_extended':'1.11.0','sympy':'1.14.0'},'symbolic_equivalence':True},'containers':jobs})
 return pins


def test_complete_synthetic_four_arm_pipeline(tmp_path):
 pins=complete_fixture(tmp_path);report,review=analyze.analyze(tmp_path,pins['before'],pins['after'])
 assert report['requests']==80 and report['pairs']==40 and set(report['models'])==set(analyze.MODELS.values())
 assert len([x for x in review.splitlines() if x.startswith('## ')])==10
 for model in report['models'].values():
  assert set(model['axes'])==set(analyze.AXES)
  for axis,a in model['axes'].items():
   assert a['n_pairs']==5 and a['content_identical_count']==a['reasoning_identical_count']==5 and a['ratios']['wall_s']['point']==1
   if axis=='cjudge':assert a['quality_score'] is None and a['human_review']=='pending'
   else:assert a['strict_quality_delta']['equivalence_established'] is False

@pytest.mark.parametrize('damage',['missing_grade','raw_response','missing_final','partial_summary','official_status'])
def test_bad_completed_fixture_cannot_produce_report(tmp_path,damage):
 pins=complete_fixture(tmp_path);model=analyze.MODELS['tq4'];gd=tmp_path/'grades/after/tq4'
 if damage=='missing_grade':(gd/'complete-scores.json').unlink()
 elif damage=='missing_final':(tmp_path/'finalized-after-tq4.json').unlink()
 elif damage=='partial_summary':put(tmp_path/'runs/after/tq4/summary.json',{'status':'running','completed':19,'frozen_sha256':pins['after']})
 elif damage=='raw_response':put(tmp_path/'runs/after/tq4/request-20/response.json',{})
 else:
  path=gd/model/'humanevalplus.fake-after-tq4_samples_eval_results.json';ev=json.loads(path.read_text());ev['eval'][next(iter(ev['eval']))][0]['plus_status']=None;put(path,ev)
 with pytest.raises(analyze.AuditError):analyze.analyze(tmp_path,pins['before'],pins['after'])
 assert not (tmp_path/'analysis').exists()


def test_math_grade_must_match_canonical_scorer(monkeypatch):
 monkeypatch.setattr(analyze,'math_eq',lambda a,b:False,raising=False)
 item={'pred':'2','gold':'1','ok':True}
 with pytest.raises(analyze.AuditError):analyze.math_grade_check(item,{'content':'\\boxed{2}','answer_gold':'1'})


def test_changed_math_outcome_is_exact_exclusive_solve(tmp_path):
 pins=complete_fixture(tmp_path);phase='after';mode='native16';f=json.loads((tmp_path/'frozen-after.json').read_text());a=f['arms'][mode]
 entry=next(e for e in a['requests'] if e['bench']=='math500');index=a['requests'].index(entry)+1;directory=tmp_path/'runs'/phase/mode/f'request-{index:02d}'
 raw=json.loads((directory/'response.json').read_text());raw['choices'][0]['message']['content']='No valid answer.';put(directory/'response.json',raw)
 row=json.loads((directory/'row.json').read_text());row['content']='No valid answer.';row['content_sha256']=analyze.text_sha('No valid answer.');put(directory/'row.json',row)
 rp=Path(a['results']['math500']);rs=[json.loads(x) for x in rp.read_text().splitlines()];rs=[row if r['id']==entry['id'] else r for r in rs];put(rp,rs,True)
 gd=tmp_path/'grades'/phase/mode;(gd/a['model']/rp.name).write_bytes(rp.read_bytes())
 scores=json.loads((gd/'complete-scores.json').read_text());score=next(s for s in scores if s['benchmark']=='math500')
 for field in ('items','strict_items'):
  item=next(i for i in score[field] if i['id']==entry['id']);item.update(pred=None,ok=False,score=0.)
 score.update(acc=.8,acc_strict=.8);put(gd/'complete-scores.json',scores)
 finalpath=tmp_path/f'finalized-{phase}-{mode}.json';final=json.loads(finalpath.read_text())
 for p in (rp,directory/'response.json',directory/'row.json'):final['files'][str(p)]=analyze.digest(p)
 finalpin=put(finalpath,final);gp=json.loads((gd/'grading-provenance.json').read_text());gp['run_evidence_sha256']=finalpin;put(gd/'grading-provenance.json',gp)
 report,_=analyze.analyze(tmp_path,pins['before'],pins['after']);axis=report['models'][a['model']]['axes']['math500']
 assert axis['before_only_solved']==[entry['id']] and axis['after_only_solved']==[] and axis['after']['acc_strict']==.8
 assert axis['strict_quality_delta']['delta']==pytest.approx(-.2)
 assert report['models'][analyze.MODELS['tq4']]['axes']['math500']['after']['acc_strict']==1.
