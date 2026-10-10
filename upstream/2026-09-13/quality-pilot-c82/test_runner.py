import copy,json
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
import runner as r


def test_nonprefix_selected_loader_preserves_canonical_full_order():
    from bench import benchmarks
    records=[{'task_id':str(i),'prompt':str(i),'entry_point':'f'} for i in range(20)]
    expected=[{'id':p['task_id'],'prompt':p['prompt'],'meta':{'entry_point':'f'}} for p in records]
    wanted=['2','7','11','14','18']
    want=[p for p in benchmarks._subsample(expected,None,0) if p['id'] in wanted]
    assert r.select_corpus_items('humanevalplus',records,wanted)==want
    assert len(want)==5


def test_overlay_pair_only_approved_native_uniform_treatment():
    a={'models':[{'name':r.MODEL,'kv_bits':0,'kv_quant_scheme':'turboquant','generation_defaults':{'temperature':.5}}]}
    b=copy.deepcopy(a);b['models'][0].update(kv_bits=8,kv_quant_scheme='uniform')
    r.validate_overlay_pair(a,b)
    b['models'][0]['generation_defaults']['temperature']=.6
    with pytest.raises(r.PilotError):r.validate_overlay_pair(a,b)


def test_bad_module_origin_rejected():
    with patch('runner.STACK',Path('/not-the-source')):
        with pytest.raises(r.PilotError):r.validate_imports()


def test_provenance_barrier_never_acks_failed_verification():
    entry={'bench':'math500','id':'id'};frozen={'requests':[entry]}
    ack=Mock();verify=Mock(side_effect=r.PilotError('bad manifest'))
    with pytest.raises(r.PilotError):r.before_request({'index':0,'bench':'math500','id':'id'},0,frozen,verify,ack)
    ack.assert_not_called()


def test_duplicate_or_wrong_request_index_cannot_ack():
    entry={'bench':'math500','id':'id'};frozen={'requests':[entry]}
    for event in ({'index':1,'bench':'math500','id':'id'},{'index':0,'bench':'math500','id':'wrong'}):
        with pytest.raises(r.PilotError):r.before_request(event,0,frozen,Mock(),Mock())


def test_monitor_selftest_counts_and_mean_max(tmp_path):
    m=r.Monitor(tmp_path/'heartbeat.jsonl');assert m.selftest();m.start()
    m.complete({'id':'a','bench':'math500','wall_s':2,'completion_tokens':10,'converged':True,'nonconv_kind':None})
    a=m.assess();assert a['completed']==1 and a['counter_delta']==1 and a['eta_s_mean']==28 and a['max_wall_s']==2
    assert m.assess()['counter_delta']==0
    m.close('complete')
    assert json.loads((tmp_path/'heartbeat.jsonl').read_text().splitlines()[-1])['event']=='RUNNER-EXIT'


def test_output_symlink_escape_and_overwrite_refused(tmp_path):
    inside=tmp_path/'private';outside=tmp_path/'outside';inside.mkdir();outside.mkdir()
    (inside/'run').symlink_to(outside,target_is_directory=True)
    with pytest.raises(r.PilotError):r.require_new(inside/'run',inside)
    file=inside/'existing';file.mkdir();(file/'row').write_text('x')
    with pytest.raises(r.PilotError):r.require_new(file,inside)


def test_manifest_sampling_kv_source_mismatch():
    arm={'entry':{'max_kv_cache_size':262144,'kv_prealloc_tokens':262144,'kv_bits':0,'kv_quant_scheme':'turboquant','prefill_step_size':512,'quantized_kv_start':0},'overlay_sha256':'x','params':{'max_tokens':102400,'thinking_budget':81920}}
    source={'src/mlx-vlm':'a','src/mlx-serve':'b'}
    man={'model':r.MODEL,'sampling_profile':'deployed','sampling':arm['params'],'registry':{'sha256':'x'},'kv':arm['entry'],'runtime':{'draft_kind':'mtp','probe_timeout_s':21080},'git':{'serving_path':source},'tune':'tag'}
    r.validate_manifest(man,arm,source,'tag')
    for group,key,value in [('sampling','max_tokens',256),('kv','kv_bits',4),('registry','sha256','wrong'),('runtime','draft_kind','off')]:
        bad=copy.deepcopy(man);bad[group][key]=value
        with pytest.raises(r.PilotError):r.validate_manifest(bad,arm,source,'tag')


def test_item_event_is_logged_without_duplicate_event_argument(tmp_path):
    frozen={'requests':[{'bench':'math500','id':'id','seed':9}]}
    row={'bench':'math500','id':'id','sampler_seed':9,'wall_s':1,'completion_tokens':2,'converged':True}
    m=r.Monitor(tmp_path/'heartbeat.jsonl')
    assert r.admit_item({'event':'ITEM','completed':1,'row':row},0,frozen,m,tmp_path)==1
    assert json.loads((tmp_path/'heartbeat.jsonl').read_text())['event']=='ITEM'


def test_canonical_messages_from_frozen_items_must_still_match_selection():
    from bench import benchmarks,generate,rowschema
    import hashlib
    item={'id':'a','prompt':'original','answer':'1'}
    meta={'id':'a','sample':0,'seed_base':0,'sampler_seed':rowschema.sample_seed('a',0,base=0),'corpus_prompt_sha256':hashlib.sha256(b'original').hexdigest()}
    selection={'groups':[{'axis':'math500','items':[meta]}]}
    frozen={'items_by_bench':{'math500':[item]}}
    r.validate_frozen_items(frozen,selection)
    item['prompt']='changed'
    with pytest.raises(r.PilotError):r.validate_frozen_items(frozen,selection)


def test_owned_cleanup_survives_exited_leader_and_bound_is_request_derived():
    child=Mock();child.pid=123;child.poll.return_value=0
    with patch('runner.os.killpg') as kill:r.stop_owned(child)
    kill.assert_called_once_with(123,r.signal.SIGKILL)
    child.wait.assert_called_once_with(timeout=15)
    assert r.BOUND==15*21080+1200


def test_child_environment_mismatch_is_rejected():
    env={'PYTHONPATH':'/isolated','MLX_SERVE_CONFIG':'/overlay','MLX_BENCH_RESULTS':'/out','MLX_SERVE_BASE':'http://localhost:8000','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':'/private/tmp'}
    r.validate_child_environment(dict(env),env)
    for key in env:
        bad=dict(env);bad[key]='wrong'
        with pytest.raises(r.PilotError):r.validate_child_environment(bad,env)
    with pytest.raises(r.PilotError):r.validate_child_environment({**env,'APC_ENABLED':'0'},env)



def test_selection_pin_is_c82():
    assert r.SELECTION_SHA=='02b30efc7bd6d3fd94628a53a5e1f69d7255ee5fa3e4d86060790fc00f4a39e7'


def runtime_frame(mode):
    bits='0' if mode=='native16' else '8'
    scheme='turboquant' if mode=='native16' else 'uniform'
    command=['/runtime/python','/runtime/mlx_vlm.server','--kv-quant-scheme',scheme]
    if mode=='uniform8':command+=['--kv-bits','8']
    return {'worker':{'pid':7,'command':command,'environment':{'KV_BITS':bits}}}


@pytest.mark.parametrize('mode',['native16','uniform8'])
def test_c82_runtime_treatment_and_group_guard(mode):
    frame=runtime_frame(mode)
    r.validate_treatment_runtime(mode,frame,{'KV_BITS':frame['worker']['environment']['KV_BITS']})
    for env in ({'KV_BITS':'4'},{'KV_BITS':None},{'KV_BITS':frame['worker']['environment']['KV_BITS'],'KV_GROUP_SIZE':'128'}):
        with pytest.raises(r.PilotError):r.validate_treatment_runtime(mode,frame,env)
    frame['worker']['command']+=['--kv-group-size','64']
    r.validate_treatment_runtime(mode,frame,{'KV_BITS':frame['worker']['environment']['KV_BITS'],'KV_GROUP_SIZE':'64'})


@pytest.mark.parametrize('tokens',[['--kv-group-size','128'],['--kv-group-size=128'],['--kv-group','128'],['--kv-quant-scheme=turboquant'],['--kv-quant-sch','turboquant']])
def test_noncanonical_or_wrong_cache_overrides_rejected(tokens):
    frame=runtime_frame('uniform8');frame['worker']['command']+=tokens
    with pytest.raises(r.PilotError):r.validate_treatment_runtime('uniform8',frame,{'KV_BITS':'8'})


@pytest.mark.parametrize('bad_bits,bad_scheme',[(4,'turboquant'),(8,'turboquant'),(0,'uniform'),(8,'uniform')])
def test_overlay_pair_rejects_unapproved_treatment_or_other_drift(bad_bits,bad_scheme):
    a={'models':[{'name':r.MODEL,'kv_bits':0,'kv_quant_scheme':'turboquant','generation_defaults':{'temperature':.5}}]}
    b=copy.deepcopy(a);b['models'][0].update(kv_bits=bad_bits,kv_quant_scheme=bad_scheme)
    if (bad_bits,bad_scheme)==(8,'uniform'):b['models'][0]['generation_defaults']['temperature']=.6
    with pytest.raises(r.PilotError):r.validate_overlay_pair(a,b)


def test_prepare_cli_accepts_c82_overlay_option_names(tmp_path,monkeypatch):
    argv=['runner.py','prepare','--source-repo',str(tmp_path/'source'),'--native16-overlay',str(tmp_path/'native16.yaml'),'--uniform8-overlay',str(tmp_path/'uniform8.yaml'),'--dry-run']
    with patch('sys.argv',argv),patch.object(r,'prepare',return_value={'requests':[]}) as prepare:
        assert r.main()==0
    prepare.assert_called_once_with(tmp_path/'source',tmp_path/'native16.yaml',tmp_path/'uniform8.yaml')


def layout_fixture():
    return {'model':r.MODEL,'native_live_model_dtype_observed':False,
            'arms':{'native16':{'counts':{'ArraysCache':48,'PreallocKVCache':16},'full_floor':262144,'group_size':None},
                    'uniform8':{'counts':{'ArraysCache':48,'PreallocQuantizedKVCache':16},'full_floor':262144,'group_size':64}}}


def test_root_layout_evidence_requires_all_sixteen_uniform_caches_group64():
    good=layout_fixture();r.validate_layout_evidence(good)
    for change in ('group','floor','count','model'):
        bad=copy.deepcopy(good)
        if change=='group':bad['arms']['uniform8']['group_size']=128
        elif change=='floor':bad['arms']['native16']['full_floor']=0
        elif change=='count':bad['arms']['uniform8']['counts']={'ArraysCache':48,'PreallocQuantizedKVCache':15,'PreallocKVCache':1}
        else:bad['model']='other-model'
        with pytest.raises(r.PilotError):r.validate_layout_evidence(bad)


@pytest.mark.parametrize('variable',['KV_KEY_BITS','KV_VALUE_BITS','KV_KEY_SCHEME','KV_VALUE_SCHEME'])
@pytest.mark.parametrize('mode',['native16','uniform8'])
@pytest.mark.parametrize('value',['4','0','', 'turboquant'])
def test_split_kv_environment_override_is_unapproved(variable,mode,value):
    frame=runtime_frame(mode)
    env={'KV_BITS':str(r.TREATMENTS[mode][0]),variable:value}
    with pytest.raises(r.PilotError,match='split'):
        r.validate_treatment_runtime(mode,frame,env)


@pytest.mark.parametrize('option',['--kv-key-bits','--kv-value-bits','--kv-key-scheme','--kv-value-scheme'])
@pytest.mark.parametrize('spelling',['spaced','equals','abbreviated'])
def test_split_kv_cli_override_is_unapproved(option,spelling):
    frame=runtime_frame('uniform8')
    tokens=[option,'4'] if spelling=='spaced' else [option+'=4'] if spelling=='equals' else [option[:-1],'4']
    frame['worker']['command']+=tokens
    with pytest.raises(r.PilotError,match='split'):
        r.validate_treatment_runtime('uniform8',frame,{'KV_BITS':'8'})


def test_live_wrapper_captures_split_environment_for_guard(monkeypatch):
    frame=runtime_frame('uniform8')
    cap=Mock();cap.collect_live.return_value=frame
    with patch.object(r,'capacity_helpers',return_value=cap),patch('psutil.Process') as process:
        process.return_value.environ.return_value={'KV_BITS':'8','KV_KEY_BITS':'4'}
        with pytest.raises(r.PilotError,match='split'):
            r.collect_treatment_live('uniform8',{'entry':{},'overlay':'/fake'},Path('/launch'),'sha')


def test_original_absolute_capacity_helper_ignores_local_module_shadow(monkeypatch):
    import sys,types
    fake=types.ModuleType('capacity_runner');fake.__file__='/wrong/quality-pilot-c82/capacity_runner.py'
    monkeypatch.setitem(sys.modules,'capacity_runner',fake)
    monkeypatch.setattr(r,'_CAPACITY_HELPERS',None)
    helper=r.capacity_helpers()
    assert Path(helper.__file__).resolve()==(r.ROOT/'capacity_runner.py').resolve()
    assert helper is not fake
