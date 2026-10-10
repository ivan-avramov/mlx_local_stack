import copy,json,subprocess
from unittest.mock import Mock
from pathlib import Path
import pytest
import child

P={'temperature':.5,'top_p':.95,'top_k':20,'min_p':0.,'presence_penalty':0.,'max_tokens':102400,'thinking_budget':81920,'enable_thinking':True,'reasoning_effort':'medium'}
def expected(n=20):
 from bench import rowschema
 out=[]
 for i in range(n):
  seed=rowschema.sample_seed(str(i),0,base=0)
  payload={'model':'model','messages':[{'role':'user','content':str(i)}],'stream':False,**P,'seed':seed}
  out.append({'id':str(i),'bench':('math500','humanevalplus','mbppplus','cjudge')[i%4],'seed':seed,'payload':payload,'wire':json.dumps(payload)})
 return out

def response():
 return {'choices':[{'index':0,'finish_reason':'stop','message':{'content':'answer','reasoning':'reason'}}], 'usage':{'prompt_tokens':50,'completion_tokens':10},'timings':{'predicted_per_second':40.,'peak_memory':55.,'draft_kind':'mtp','draft_rounds':5,'draft_n':10,'draft_n_accepted':5}}

def row(e):
 return {'id':e['id'],'bench':e['bench'],'model':'model','sample':0,'sampler_seed':e['seed'],'seed_base':0,'schema_version':2,'prompt_tokens':50,'completion_tokens':10,'finish_reason':'stop','thinking_budget':81920,'content':'answer','converged':True,'draft':{'draft_kind':'mtp','draft_rounds':5,'draft_n':10,'draft_n_accepted':5},'wall_s':1.}

def test_exact_twenty_no_extra_and_no_memory_cutoff(tmp_path):
 delegate=Mock(return_value=response());sink=Mock();es=expected();g=child.Guard(es,tmp_path,delegate,lambda *_:None,lambda *_:None)
 for e in es:
  g.post('/v1/chat/completions',e['payload'],timeout=21080);g.append(tmp_path/'row',row(e),sink)
 g.finish();assert delegate.call_count==20 and sink.call_count==20
 with pytest.raises(child.PilotAbort):g.post('/v1/chat/completions',es[0]['payload'],timeout=21080)
 assert delegate.call_count==20

@pytest.mark.parametrize('n',[15,19,21])
def test_wrong_count_rejected(tmp_path,n):
 with pytest.raises(child.PilotAbort):child.Guard(expected(n),tmp_path,Mock(),Mock(),Mock())

@pytest.mark.parametrize('field',['model','seed','messages','temperature','stream'])
def test_payload_drift_before_transport(tmp_path,field):
 d=Mock();g=child.Guard(expected(),tmp_path,d,Mock(),Mock());p=copy.deepcopy(expected()[0]['payload']);p[field]='wrong'
 with pytest.raises(child.PilotAbort):g.post('/v1/chat/completions',p,timeout=21080)
 d.assert_not_called()

def test_transport_escapes_canonical_exception_recovery(tmp_path):
 d=Mock(side_effect=TimeoutError('timed out'));g=child.Guard(expected(),tmp_path,d,Mock(),Mock())
 with pytest.raises(child.PilotAbort):g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)
 assert g.completed==0 and d.call_count==1 and not issubclass(child.PilotAbort,Exception)

@pytest.mark.parametrize('bad',[None,-1,True,float('nan')])
def test_bad_usage_no_row(tmp_path,bad):
 r=response();r['usage']['completion_tokens']=bad;d=Mock(return_value=r);g=child.Guard(expected(),tmp_path,d,Mock(),Mock())
 with pytest.raises(child.PilotAbort):g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)
 assert g.completed==0

import screen

def proposal():
 return {'arms':{m:{'model':name,'requests':expected(),'items':{},'params':P} for m,name in screen.MODELS.items()}}

def test_phase_paths_and_exact_pairing():
 p=proposal();a=screen.phase_plan(p,'before',{'submodules':{'src/mlx-vlm':'a','src/mlx-serve':'s'}})
 b=screen.phase_plan(p,'after',{'submodules':{'src/mlx-vlm':'b','src/mlx-serve':'s'}},a)
 assert a['phase']=='before' and b['phase']=='after' and a['request_count']==b['request_count']==80
 for m in screen.MODELS:
  assert a['arms'][m]['requests']==b['arms'][m]['requests']
  assert a['arms'][m]['results']['cjudge']!=b['arms'][m]['results']['cjudge']

@pytest.mark.parametrize('change',['payload','serve','same_vlm'])
def test_bad_after_pair_rejected(change):
 p=proposal();source={'submodules':{'src/mlx-vlm':'a','src/mlx-serve':'s'}}
 a=screen.phase_plan(p,'before',source);other={'submodules':{'src/mlx-vlm':'b','src/mlx-serve':'s'}}
 if change=='payload':p['arms']['native16']['requests'][0]['wire']='changed'
 elif change=='serve':other['submodules']['src/mlx-serve']='different'
 else:other=source
 with pytest.raises(screen.ScreenError):screen.phase_plan(p,'after',other,a)

@pytest.mark.parametrize('phase',['before','after'])
@pytest.mark.parametrize('mode',['native16','tq4'])
def test_actual_canonical_cli_twenty_calls(tmp_path,monkeypatch,phase,mode):
 import io
 from unittest.mock import patch
 from bench import benchmarks,client,generate,model_params
 items={b:[{'id':f'{b}/{i}','prompt':f'Problem{i}','answer':'1'} for i in range(5)] for b in screen.BENCHES}
 a={'model':screen.MODELS[mode],'items':items,'params':P,'tag':f'test-{phase}-{mode}'};a['requests']=screen.requests_for(a)
 results=tmp_path/'results'/phase;a['results']={b:str(results/a['model']/f"{b}.{a['tag']}.jsonl") for b in screen.BENCHES};out=tmp_path/'runs'/phase/mode;out.mkdir(parents=True)
 calls=[]
 def post(path,payload,timeout=3600):calls.append((path,copy.deepcopy(payload)));return {'status':'ready'} if path=='/v1/models/load' else response()
 monkeypatch.setenv('MLX_SERVE_CONFIG',str(screen.REGISTRY));monkeypatch.setenv('MLX_BENCH_RESULTS',str(results))
 with patch.object(screen,'HERE',tmp_path),patch.object(screen,'frozen',return_value={'arms':{mode:a}}),patch.object(generate,'RESULTS',results),patch.object(generate,'provenance_precheck'),patch.object(generate,'stamp_manifests'),patch.object(model_params,'params_for',side_effect=lambda *a,**kw:dict(P)),patch.object(client,'_post',side_effect=post),patch('sys.stdin',io.StringIO(''.join(json.dumps({'ack':i})+'\n' for i in range(20)))):
  child.run(phase,mode,'fakepin',out)
 assert len([x for x in calls if x[0]=='/v1/models/load'])==1
 assert [json.dumps(x[1]) for x in calls if x[0]=='/v1/chat/completions']==[e['wire'] for e in a['requests']]
 for b,p in a['results'].items():
  rs=[json.loads(x) for x in Path(p).read_text().splitlines()];assert len(rs)==5 and all(r['resolved_thinking_budget']==81920 for r in rs)


def actual_fixture(mode='native16'):
 arm=json.loads((screen.HERE/'prepared.json').read_text())['arms'][mode];e=arm['entry']
 flags={'--model':e['hf_path'],'--host':'127.0.0.1','--port':'8091','--max-kv-size':'262144','--kv-prealloc-tokens':'262144','--kv-quant-scheme':'turboquant','--prefill-step-size':'512','--generation-defaults':json.dumps(arm['params']),'--draft-kind':'mtp','--draft-model':e['draft_model'],'--quantized-kv-start':'0','--memory-limit-frac':'0.85'}
 if mode=='tq4':flags['--kv-bits']='4'
 cmd=[str(screen.STACK/'.venv/bin/python3'),str(screen.STACK/'.venv/bin/mlx_vlm.server')]+[x for pair in flags.items() for x in pair]
 env={'MLX_SERVE_CONFIG':str(screen.REGISTRY),'MLX_VLM_CACHE_SESSION_MAX':'2'}
 return arm,cmd,env

@pytest.mark.parametrize('mode',['native16','tq4'])
def test_deployed_command_known_positive(mode):screen.validate_process(*actual_fixture(mode))

@pytest.mark.parametrize('override',['--kv-bits=8','--kv-b','--kv-key-bits','--kv-quant-s','--kv-prealloc-tokens'])
def test_worker_override_rejected(override):
 a,c,e=actual_fixture();c.extend([override,'8'])
 with pytest.raises(screen.ScreenError):screen.validate_process(a,c,e)

@pytest.mark.parametrize('key',['APC_ENABLED','KV_BITS','KV_KEY_BITS','KV_VALUE_SCHEME','MLX_VLM_SESSION_SHRINK_ON_RETIRE','MLX_METAL_GPU_ARCH'])
def test_worker_environment_override_rejected(key):
 a,c,e=actual_fixture();e[key]='1'
 with pytest.raises(screen.ScreenError):screen.validate_process(a,c,e)

@pytest.mark.parametrize('change',['registry','sampling','source','precision','timeout','tag'])
def test_manifest_drift_rejected(change):
 a,_,_=actual_fixture();f={'registry_sha256':'reg','source':{'submodules':{'src/mlx-vlm':'a'},'serving_path':{'src/mlx-vlm':'h'}}}
 m={'model':a['model'],'tune':a['tag'],'sampling_profile':'deployed','sampling':copy.deepcopy(a['params']),'registry':{'sha256':'reg'},'git':copy.deepcopy(f['source']),'runtime':{'draft_kind':'mtp','probe_timeout_s':screen.TIMEOUT},'kv':{k:a['entry'][k] for k in ('kv_bits','kv_quant_scheme','quantized_kv_start','max_kv_cache_size','kv_prealloc_tokens','prefill_step_size')}}
 screen.validate_manifest(m,a,f)
 if change=='registry':m['registry']['sha256']='bad'
 if change=='sampling':m['sampling']['temperature']=.7
 if change=='source':m['git']['submodules']['src/mlx-vlm']='bad'
 if change=='precision':m['kv']['kv_bits']=4
 if change=='timeout':m['runtime']['probe_timeout_s']=600
 if change=='tag':m['tune']='bad'
 with pytest.raises(screen.ScreenError):screen.validate_manifest(m,a,f)

def test_monitor_known_positive_and_exit(tmp_path):
 m=screen.Monitor(tmp_path/'monitor.jsonl');assert m.selftest();m.close('complete')
 e=[json.loads(x) for x in m.path.read_text().splitlines()];assert e[0]['event']=='SELFTEST' and e[-1]['event']=='RUNNER-EXIT'

def test_exclusive_private_write_and_symlink_escape(tmp_path,monkeypatch):
 monkeypatch.setattr(screen,'HERE',tmp_path);p=tmp_path/'x.json';screen.save(p,{'ok':True})
 with pytest.raises(FileExistsError):screen.save(p,{'ok':False})
 symlink=tmp_path/'escape';symlink.symlink_to(tmp_path.parent,target_is_directory=True)
 with pytest.raises(screen.ScreenError):screen.save(symlink/'should-not-write.json',{})

def test_unreviewed_or_incomplete_grading_rejected(tmp_path,monkeypatch):
 import grade_screen
 monkeypatch.setattr(screen,'HERE',tmp_path);p=tmp_path/'finalized-before-native16.json';p.write_text('{}')
 with pytest.raises(screen.ScreenError):grade_screen.completed({'arms':{'native16':{'model':'model'}}},'before','native16',p,'wrong-pin')
 with pytest.raises(screen.ScreenError):grade_screen.completed({'arms':{'native16':{'model':'model'}}},'before','native16',p,screen.sha(p))

def test_reused_sandbox_pinned_and_symbolic_positive_is_not_string_fallback():
 import grade_screen
 g=grade_screen.sandbox();assert screen.sha(g.__file__)==screen.OLD_GRADE_SHA
 with pytest.raises(g.GradingError):g.validate_math_dependencies(lambda a,b:a==b,version=lambda name:g.MATH_VERSIONS[name])

def test_extract_module_is_frozen():assert 'extract' in screen.MODULES

def test_evalplus_uses_frozen_all_ids_without_host_loader(tmp_path,monkeypatch):
 import grade_screen
 from bench import grade,generate
 monkeypatch.setenv('MLX_BENCH_RESULTS',str(tmp_path));monkeypatch.setattr(generate,'RESULTS',tmp_path)
 monkeypatch.setattr(grade,'_rows',lambda *a,**k:[{'id':'HumanEval/1','sample':0,'content':'```python\ndef f():\n return 1\n```','converged':True}])
 loader=Mock(side_effect=AssertionError('host dataset loader must never run'));monkeypatch.setattr(grade,'_evalplus_all_ids',loader)
 def fake_runner(command,**kwargs):
  result=tmp_path/'model'/'humanevalplus.test_samples_eval_results.json'
  result.write_text(json.dumps({'eval':{i:[{'base_status':'pass','plus_status':'pass'}] for i in ('HumanEval/1','HumanEval/2')}}))
  return subprocess.CompletedProcess(command,0,'','')
 score=grade_screen.offline_eval(grade.grade_evalplus,'humanevalplus','model',image='fake',runner=fake_runner,corpus_ids={'humanevalplus':['HumanEval/1','HumanEval/2']},tune='test')
 loader.assert_not_called();assert score['n']==1 and score['acc']==1.0

@pytest.mark.parametrize('key',['PYTHONPATH','PYTHONHOME'])
def test_worker_shadow_imports_rejected(key):
 a,c,e=actual_fixture();e[key]='/unapproved'
 with pytest.raises(screen.ScreenError):screen.validate_process(a,c,e)

@pytest.mark.parametrize('observed',['','23\n','22\n23\n'])
def test_wrong_endpoint_owner_rejected(observed):
 call=Mock(return_value=subprocess.CompletedProcess([],0,observed,''))
 with pytest.raises(screen.ScreenError):screen.validate_listener(8000,22,run=call)

def test_endpoint_owner_known_positive():
 call=Mock(return_value=subprocess.CompletedProcess([],0,'22\n',''));screen.validate_listener(8000,22,run=call)
 assert call.call_args.args[0]==['lsof','-nP','-t','-iTCP:8000','-sTCP:LISTEN']

def test_output_ancestor_symlink_rejected_before_mkdir(tmp_path,monkeypatch):
 monkeypatch.setattr(screen,'HERE',tmp_path);outside=tmp_path/'outside';outside.mkdir();(tmp_path/'runs').symlink_to(outside,target_is_directory=True)
 with pytest.raises(screen.ScreenError):screen.require_run_output(tmp_path/'runs'/'before'/'native16')
 assert not list(outside.iterdir())
