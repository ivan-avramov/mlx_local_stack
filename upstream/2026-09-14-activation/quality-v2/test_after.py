import copy,json
from pathlib import Path
import pytest,yaml
import screen

BASE=Path(__file__).resolve().parent.parent/'quality'

def registry_pair():
 before=yaml.safe_load((BASE/'registry-before.yaml').read_text());after=copy.deepcopy(before)
 next(e for e in after['models'] if e['name']==screen.MODELS['native16'])['cache_session_shrink']=True
 return before,after

def test_only_native_true_registry_amendment():screen.validate_registry_amendment(*registry_pair())

@pytest.mark.parametrize('change',['false','null','string','int','tq4','temperature','fullcap','extra'])
def test_other_registry_drift_rejected(change):
 before,after=registry_pair();n=next(e for e in after['models'] if e['name']==screen.MODELS['native16']);t=next(e for e in after['models'] if e['name']==screen.MODELS['tq4'])
 if change in ('false','null','string','int'):n['cache_session_shrink']={'false':False,'null':None,'string':'on','int':1}[change]
 elif change=='tq4':t['cache_session_shrink']=None
 elif change=='temperature':n['generation_defaults']['temperature']=.7
 elif change=='fullcap':n['kv_prealloc_tokens']=131072
 else:after['extra']='unapproved'
 with pytest.raises(screen.ScreenError):screen.validate_registry_amendment(before,after)


def test_reviewed_metadata_only_amendment():
 before=json.loads((BASE/'frozen-before.json').read_text())['module_hashes']
 expected=screen.amended_module_hashes(before)
 for p,h in before.items():
  if not p.endswith('/provenance.py'):assert expected[p]==h
 assert expected[str(screen.STACK/'benchmark/bench/provenance.py')]==screen.REVIEWED_BENCH['provenance.py']
 assert screen.historical_module_path(screen.STACK/'benchmark/bench/provenance.py')==BASE/'historical-code/provenance.py'


def worker(mode):
 f=json.loads((BASE/'frozen-before.json').read_text());arm=copy.deepcopy(f['arms'][mode]);arm['mode']=mode
 if mode=='native16':arm['entry']['cache_session_shrink']=True
 e=arm['entry'];flags={'--model':e['hf_path'],'--host':'127.0.0.1','--port':'8091','--max-kv-size':'262144','--kv-prealloc-tokens':'262144','--kv-quant-scheme':'turboquant','--prefill-step-size':'512','--generation-defaults':json.dumps(arm['params']),'--draft-kind':'mtp','--draft-model':e['draft_model'],'--quantized-kv-start':'0','--memory-limit-frac':'0.85'}
 if mode=='native16':flags['--cache-session-shrink']='on'
 else:flags['--kv-bits']='4'
 cmd=[str(screen.STACK/'.venv/bin/python3'),str(screen.STACK/'.venv/bin/mlx_vlm.server')]+[x for pair in flags.items() for x in pair]
 env={'MLX_SERVE_CONFIG':str(screen.REGISTRY),'MLX_VLM_CACHE_SESSION_MAX':'2'}
 return arm,cmd,env

@pytest.mark.parametrize('mode',['native16','tq4'])
def test_after_per_model_flag_known_positive(mode):screen.validate_process(*worker(mode))

@pytest.mark.parametrize('change',['omit','off','other_model'])
def test_wrong_retirement_policy_rejected(change):
 arm,cmd,env=worker('tq4' if change=='other_model' else 'native16')
 if change=='other_model':cmd+=['--cache-session-shrink','on']
 elif change=='omit':cmd=cmd[:-2]
 else:cmd[-1]='off'
 with pytest.raises(screen.ScreenError):screen.validate_process(arm,cmd,env)


def test_complete_archived_baseline_is_read_only():
 f=json.loads((BASE/'frozen-before.json').read_text());before=screen.sha(BASE/'frozen-before.json')
 inventory=screen.baseline_inventory(f)
 assert inventory[str(BASE/'registry-before.yaml')]==f['registry_sha256']
 assert inventory[str(BASE/'historical-code/provenance.py')]==f['module_hashes'][str(screen.STACK/'benchmark/bench/provenance.py')]
 assert before==screen.BEFORE_PIN==screen.sha(BASE/'frozen-before.json')


def test_real_inputs_prepare_with_private_proposed_registry(tmp_path,monkeypatch):
 before,after=registry_pair();registry=tmp_path/'proposed.yaml';registry.write_text(yaml.safe_dump(after));monkeypatch.setattr(screen,'REGISTRY',registry)
 f=screen.prepare();old=json.loads((BASE/'frozen-before.json').read_text())
 screen.validate_after_pair(f,old)
 assert f['treatment']==screen.TREATMENT and 'source' not in f and f['phase_requests']==40
 assert all(f['arms'][m]['requests']==old['arms'][m]['requests'] for m in screen.MODELS)
 assert all(str(screen.HERE) in p for a in f['arms'].values() for p in a['results'].values())


@pytest.mark.parametrize('change',['sample','registry_entry','runtime','module','phase'])
def test_after_pair_rejects_non_treatment_drift(tmp_path,monkeypatch,change):
 _,doc=registry_pair();p=tmp_path/'config.yaml';p.write_text(yaml.safe_dump(doc));monkeypatch.setattr(screen,'REGISTRY',p)
 f=screen.prepare();old=json.loads((BASE/'frozen-before.json').read_text())
 if change=='sample':f['arms']['native16']['requests'][0]['seed']+=1
 elif change=='registry_entry':f['arms']['tq4']['entry']['cache_session_shrink']=None
 elif change=='runtime':f['runtime']['versions']['mlx']='0.32.3'
 elif change=='module':f['module_hashes'][str(screen.STACK/'benchmark/bench/grade.py')]='changed'
 else:f['phase']='before'
 with pytest.raises(screen.ScreenError):screen.validate_after_pair(f,old)


@pytest.mark.parametrize('mode',['native16','tq4'])
def test_canonical_after_cli_twenty_calls(tmp_path,monkeypatch,mode):
 import io
 from unittest.mock import patch
 import child
 from bench import benchmarks,client,generate,model_params
 items={b:[{'id':f'{b}/{i}','prompt':f'Problem{i}','answer':'1'} for i in range(5)] for b in screen.BENCHES}
 a=copy.deepcopy(json.loads((BASE/'frozen-before.json').read_text())['arms'][mode]);a.update(items=items,tag=f'fake-after-{mode}')
 a['requests']=screen.requests_for(a);results=tmp_path/'results/after';a['results']={b:str(results/a['model']/f"{b}.{a['tag']}.jsonl") for b in screen.BENCHES}
 out=tmp_path/'runs/after'/mode;out.mkdir(parents=True);calls=[]
 def fake_post(path,payload,timeout=3600):
  calls.append((path,copy.deepcopy(payload)))
  if path=='/v1/models/load':return {'status':'ready'}
  return {'choices':[{'index':0,'finish_reason':'stop','message':{'content':'answer','reasoning':'reason'}}],'usage':{'prompt_tokens':100,'completion_tokens':10},'timings':{'predicted_per_second':40.,'peak_memory':55.,'draft_kind':'mtp','draft_rounds':3,'draft_n':6,'draft_n_accepted':5}}
 monkeypatch.setenv('MLX_SERVE_CONFIG',str(screen.REGISTRY));monkeypatch.setenv('MLX_BENCH_RESULTS',str(results))
 with patch.object(screen,'HERE',tmp_path),patch.object(screen,'frozen',return_value={'arms':{mode:a}}),patch.object(generate,'RESULTS',results),patch.object(generate,'provenance_precheck'),patch.object(generate,'stamp_manifests'),patch.object(model_params,'params_for',side_effect=lambda *args,**kw:dict(a['params'])),patch.object(client,'_post',side_effect=fake_post),patch('sys.stdin',io.StringIO(''.join(json.dumps({'ack':i})+'\n' for i in range(20)))):
  child.run('after',mode,'fake-pin',out)
 assert len([x for x in calls if x[0]=='/v1/models/load'])==1
 assert [json.dumps(x[1]) for x in calls if x[0]=='/v1/chat/completions']==[e['wire'] for e in a['requests']]
 for p in a['results'].values():
  rows=[json.loads(x) for x in Path(p).read_text().splitlines()];assert len(rows)==5 and all(r['resolved_thinking_budget']==81920 for r in rows)


def test_registry_numeric_type_drift_is_not_the_approved_field():
 before,after=registry_pair();t=next(e for e in after['models'] if e['name']==screen.MODELS['tq4']);t['kv_bits']=float(t['kv_bits'])
 with pytest.raises(screen.ScreenError):screen.validate_registry_amendment(before,after)
