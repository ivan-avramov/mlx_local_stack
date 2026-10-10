import json
from pathlib import Path
import subprocess
import pytest

import grade_pilot as g


def command(tmp_path):
    return ['docker','run','--rm','--name','evalplus-c82-test','--platform','linux/amd64',
            '-v',f'{tmp_path}:/work',g.IMAGE,'evalplus.evaluate','--dataset','humaneval',
            '--samples','/work/humanevalplus.test_samples.jsonl']


def test_native_command_is_pinned_offline_and_narrow(tmp_path):
    sample=samples(tmp_path)
    out=g.native_command(command(tmp_path),tmp_path,tmp_path/'output',tmp_path/'control/cid','unique-name')
    assert out[out.index('--platform')+1]=='linux/arm64'
    assert out[out.index('--network')+1]=='none'
    assert out[out.index('--pull')+1]=='never'
    assert out[out.index('-v')+1]==f'{tmp_path}/output:/work:rw'
    assert f'{sample}:/work/{sample.name}:ro' in out
    assert out.count(g.IMAGE)==1
    assert out[-2:]==['--parallel','2']
    assert out[out.index(g.IMAGE)+1:out.index(g.IMAGE)+4]==['python','-m','evalplus.evaluate']


@pytest.mark.parametrize('kind',['mount','image','samples','dataset'])
def test_rejects_unapproved_execution_surface(tmp_path,kind):
    samples(tmp_path)
    cmd=command(tmp_path)
    if kind=='mount':cmd[cmd.index('-v')+1]='/tmp:/work'
    if kind=='image':cmd[cmd.index(g.IMAGE)]='unapproved:latest'
    if kind=='samples':cmd[-1]='/work/../escape.jsonl'
    if kind=='dataset':cmd[cmd.index('--dataset')+1]='unexpected'
    with pytest.raises(g.GradingError):g.native_command(cmd,tmp_path,tmp_path/'out',tmp_path/'cid','unique')


def test_missing_eval_item_is_infrastructure_failure(tmp_path):
    p=tmp_path/'eval.json';p.write_text(json.dumps({'eval':{'HumanEval/1':[{'base_status':'pass','plus_status':'pass'}]}}))
    with pytest.raises(g.GradingError):g.validate_evaluator(p,{'HumanEval/1','HumanEval/2'})


@pytest.mark.parametrize('status',['pending',None,'crash'])
def test_unrecognised_evaluator_status_is_not_wrong_answer(tmp_path,status):
    p=tmp_path/'eval.json';p.write_text(json.dumps({'eval':{'HumanEval/1':[{'base_status':'pass','plus_status':status}]}}))
    with pytest.raises(g.GradingError):g.validate_evaluator(p,{'HumanEval/1'})


def test_normal_semantic_failure_is_valid_grade(tmp_path):
    p=tmp_path/'eval.json';p.write_text(json.dumps({'eval':{'HumanEval/1':[{'base_status':'fail','plus_status':'fail'}]}}))
    g.validate_evaluator(p,{'HumanEval/1'})


def test_generated_code_timeout_is_a_valid_correctness_failure(tmp_path):
    p=tmp_path/'eval.json';p.write_text(json.dumps({'eval':{'HumanEval/1':[{'base_status':'timeout','plus_status':'timeout'}]}}))
    g.validate_evaluator(p,{'HumanEval/1'})


def test_base_failure_plus_pass_escalates_canonical_scorer_disagreement(tmp_path):
    p=tmp_path/'eval.json';p.write_text(json.dumps({'eval':{'HumanEval/1':[{'base_status':'fail','plus_status':'pass'}]}}))
    with pytest.raises(g.GradingError):g.validate_evaluator(p,{'HumanEval/1'})


def test_failed_container_with_results_still_fails(tmp_path):
    samples(tmp_path)
    def run(cmd,**kwargs):return subprocess.CompletedProcess(cmd,1,'','failure')
    runner=g.NativeRunner(tmp_path,run=run)
    with pytest.raises(g.GradingError):runner(command(tmp_path),capture_output=True,text=True,timeout=10)


def test_timeout_cleans_only_owned_container(tmp_path):
    samples(tmp_path)
    calls=[]
    def run(cmd,**kwargs):
        calls.append(cmd)
        if cmd[1]=='run':
            Path(cmd[cmd.index('--cidfile')+1]).write_text('b'*64)
            raise subprocess.TimeoutExpired(cmd,10)
        return subprocess.CompletedProcess(cmd,0,'','')
    runner=g.NativeRunner(tmp_path,run=run)
    with pytest.raises(g.GradingError):runner(command(tmp_path),capture_output=True,text=True,timeout=10)
    assert calls[-1]==['docker','kill','b'*64]


def test_duplicate_or_error_rows_rejected():
    good={'id':'HumanEval/1','sample':0,'content':'x','sampler_seed':7}
    with pytest.raises(g.GradingError):g.validate_rows([good,good],{'HumanEval/1':7})
    with pytest.raises(g.GradingError):g.validate_rows([{**good,'error':'HTTP500'}],{'HumanEval/1':7})
    with pytest.raises(g.GradingError):g.validate_rows([{**good,'sampler_seed':8}],{'HumanEval/1':7})


def test_partial_and_recovered_scores_rejected():
    for bad in [{'n':4,'acc':1.0},{'n':5,'acc':None},{'n':5,'acc':1.0,'timed_out':True}]:
        with pytest.raises(g.GradingError):g.validate_score(bad,{'a','b','c','d','e'})


def samples(directory):
    path=directory/'humanevalplus.test_samples.jsonl'
    path.write_text(json.dumps({'task_id':'HumanEval/1','solution':'pass'})+'\n')
    return path


def fake_evaluation(cmd,**kwargs):
    cid=Path(cmd[cmd.index('--cidfile')+1]);cid.write_text('a'*64)
    mounts=[cmd[i+1] for i,x in enumerate(cmd) if x=='-v']
    output=Path(next(m for m in mounts if m.endswith(':/work:rw')).split(':')[0])
    result=output/'humanevalplus.test_samples_eval_results.json'
    result.write_text(json.dumps({'eval':{'HumanEval/1':[{'base_status':'pass','plus_status':'pass'}]}}))
    return subprocess.CompletedProcess(cmd,0,'done','')


def test_evaluator_mounts_only_scratch_and_readonly_sample(tmp_path):
    sample=samples(tmp_path);rows=tmp_path/'rows.jsonl';rows.write_text('original')
    observed=[]
    def run(cmd,**kwargs):observed.append(cmd);return fake_evaluation(cmd,**kwargs)
    runner=g.NativeRunner(tmp_path,run=run,immutable_files=[rows])
    runner(command(tmp_path),capture_output=True,text=True,timeout=10)
    c=observed[0];mounts=[c[i+1] for i,x in enumerate(c) if x=='-v']
    assert len(mounts)==2
    assert f'{sample}:/work/{sample.name}:ro' in mounts
    assert not any(m.startswith(str(tmp_path)+':') for m in mounts)
    assert not any(str(Path(c[c.index('--cidfile')+1]).parent) in m for m in mounts)
    assert (tmp_path/'humanevalplus.test_samples_eval_results.json').is_file()
    assert rows.read_text()=='original'


def test_name_collision_never_kills_unowned_container(tmp_path):
    samples(tmp_path);calls=[]
    def run(cmd,**kwargs):calls.append(cmd);return subprocess.CompletedProcess(cmd,125,'','name already in use')
    runner=g.NativeRunner(tmp_path,run=run)
    with pytest.raises(g.GradingError):runner(command(tmp_path),capture_output=True,text=True,timeout=10)
    runner(['docker','kill','evalplus-c82-test'],capture_output=True,text=True,timeout=10)
    assert len(calls)==1 and calls[0][1]=='run'
    assert calls[0][calls[0].index('--name')+1]!='evalplus-c82-test'


@pytest.mark.parametrize('what',['rows','sample','output_symlink'])
def test_modified_inputs_and_escaped_results_never_copy_back(tmp_path,what):
    sample=samples(tmp_path);rows=tmp_path/'rows.jsonl';rows.write_text('original')
    def run(cmd,**kwargs):
        if cmd[:2]==['docker','kill']:return subprocess.CompletedProcess(cmd,0,'','')
        proc=fake_evaluation(cmd,**kwargs)
        if what=='rows':rows.write_text('changed')
        elif what=='sample':sample.write_text('changed')
        else:
            output=Path(next(cmd[i+1] for i,x in enumerate(cmd) if x=='-v' and cmd[i+1].endswith(':/work:rw')).split(':')[0])
            result=output/'humanevalplus.test_samples_eval_results.json';outside=tmp_path/'outside.json';result.rename(outside);result.symlink_to(outside)
        return proc
    runner=g.NativeRunner(tmp_path,run=run,immutable_files=[rows])
    with pytest.raises(g.GradingError):runner(command(tmp_path),capture_output=True,text=True,timeout=10)
    assert not (tmp_path/'humanevalplus.test_samples_eval_results.json').exists()


def test_symlinked_inputs_or_model_directory_rejected(tmp_path):
    source=tmp_path/'source';outside=tmp_path/'outside';source.mkdir();outside.mkdir()
    (source/g.MODEL).symlink_to(outside,target_is_directory=True)
    with pytest.raises(g.GradingError):g.input_files(source,'tune')
    (source/g.MODEL).unlink();(source/g.MODEL).mkdir()
    target=outside/'rows';target.write_text('[]')
    (source/g.MODEL/'math500.tune.jsonl').symlink_to(target)
    with pytest.raises(g.GradingError):g.input_files(source,'tune')


def evidence_fixture(tmp_path):
    source=tmp_path/'source';(source/g.MODEL).mkdir(parents=True)
    tune='m42c82-uniform8-20260913';overlay=tmp_path/'overlay.yaml';overlay.write_text('overlay')
    sampling={'temperature':0.5,'top_p':0.95,'top_k':20,'min_p':0.0,'presence_penalty':0.0,'max_tokens':102400,'thinking_budget':81920,'enable_thinking':True,'reasoning_effort':'medium'}
    kv={'kv_bits':8,'kv_quant_scheme':'uniform','kv_group_size':64,'quantized_kv_start':0,'prefill_step_size':512,'max_kv_cache_size':262144,'kv_prealloc_tokens':262144}
    paths={k:'a'*64 for k in g.SOURCE_HEADS}
    files=[]
    for bench in g.AXES:
        p=source/g.MODEL/f'{bench}.{tune}.jsonl';p.write_text('{}\n');files.append(p)
        m=p.with_suffix('.manifest.json');m.write_text(json.dumps({'model':g.MODEL,'tune':tune,'sampling_profile':'deployed','sampling':sampling,'kv':kv,'runtime':{'draft_kind':'mtp'},'git':{'submodules':g.SOURCE_HEADS,'serving_path':paths},'registry':{'sha256':g.sha(overlay)}}));files.append(m)
    e={'schema_version':1,'decision':'C82','status':'complete','model':g.MODEL,'mode':'uniform8','tune':tune,'source_root':str(source),'selection_sha256':g.SELECTION_SHA,'overlay_sha256':g.sha(overlay),'source_shas':g.SOURCE_HEADS,'serving_path':paths,'versions':{'mlx':'0.32.2','mlx-metal':'0.32.2'},'sampling':sampling,'kv':kv,'runtime':{'draft_kind':'mtp'},'files':{p.name:g.sha(p) for p in files}}
    evidence=tmp_path/'reviewed.json';evidence.write_text(json.dumps(e))
    return source,tune,overlay,sampling,files,evidence,e


@pytest.mark.parametrize('mutation',['none','missing','hash','incomplete','mode','source','runtime','prealloc','sampling','rows'])
def test_pinned_finalization_evidence_binds_inputs_and_contract(tmp_path,mutation):
    source,tune,overlay,sampling,files,path,e=evidence_fixture(tmp_path)
    if mutation=='incomplete':e['status']='running'
    elif mutation=='mode':e['mode']='native16'
    elif mutation=='source':e['source_shas']={**e['source_shas'],'src/mlx-vlm':'b'*40}
    elif mutation=='runtime':e['versions']['mlx']='0.32.0'
    elif mutation=='prealloc':e['kv']['kv_prealloc_tokens']=65536
    elif mutation=='sampling':e['sampling']={**sampling,'temperature':0.7}
    path.write_text(json.dumps(e));pin=g.sha(path)
    if mutation=='rows':files[0].write_text('changed')
    args=(None if mutation=='missing' else path,'0'*64 if mutation=='hash' else pin,source,tune,overlay,files,sampling)
    if mutation=='none':assert g.validate_run_evidence(*args)['status']=='complete'
    else:
        with pytest.raises(g.GradingError):g.validate_run_evidence(*args)


@pytest.mark.parametrize('problem',['missing','wrong','fallback'])
def test_math_dependency_or_symbolic_probe_failure_rejected(problem):
    def version(name):
        if problem=='missing':raise g.importlib.metadata.PackageNotFoundError(name)
        return '0.0' if problem=='wrong' else g.MATH_VERSIONS[name]
    with pytest.raises(g.GradingError):g.validate_math_dependencies(lambda a,b:False if problem=='fallback' else True,version)


def test_math_probe_requires_non_string_equivalence():
    calls=[]
    def equal(a,b):calls.append((a,b));return True
    evidence=g.validate_math_dependencies(equal,g.MATH_VERSIONS.__getitem__)
    assert calls==[(r'\frac{1}{2}','0.5')] and evidence['symbolic_equivalence'] is True


def test_timeout_before_container_creation_never_kills_by_name(tmp_path):
    samples(tmp_path);calls=[]
    def run(cmd,**kwargs):calls.append(cmd);raise subprocess.TimeoutExpired(cmd,10)
    runner=g.NativeRunner(tmp_path,run=run)
    with pytest.raises(g.GradingError):runner(command(tmp_path),timeout=10)
    runner(['docker','kill','evalplus-c82-test'])
    assert len(calls)==1


def test_nonzero_exit_with_complete_result_is_not_copied(tmp_path):
    samples(tmp_path);calls=[]
    def run(cmd,**kwargs):
        calls.append(cmd)
        if cmd[1]=='kill':return subprocess.CompletedProcess(cmd,0,'','')
        fake_evaluation(cmd,**kwargs)
        return subprocess.CompletedProcess(cmd,1,'','failed after writing')
    runner=g.NativeRunner(tmp_path,run=run)
    with pytest.raises(g.GradingError):runner(command(tmp_path),timeout=10)
    assert calls[-1]==['docker','kill','a'*64]
    assert not (tmp_path/'humanevalplus.test_samples_eval_results.json').exists()


@pytest.mark.parametrize('mutation',['prealloc','sampling','draft','fingerprint','registry','model'])
def test_manifest_cannot_differ_from_root_finalized_contract(tmp_path,mutation):
    source,tune,overlay,sampling,files,path,e=evidence_fixture(tmp_path)
    mpath=files[1];m=json.loads(mpath.read_text())
    if mutation=='prealloc':m['kv']['kv_prealloc_tokens']=0
    elif mutation=='sampling':m['sampling']['temperature']=0.7
    elif mutation=='draft':m['runtime']['draft_kind']='off'
    elif mutation=='fingerprint':m['git']['serving_path']['src/mlx-vlm']='b'*64
    elif mutation=='registry':m['registry']['sha256']='b'*64
    else:m['model']='another-model'
    mpath.write_text(json.dumps(m));e['files'][mpath.name]=g.sha(mpath);path.write_text(json.dumps(e))
    with pytest.raises(g.GradingError):g.validate_run_evidence(path,g.sha(path),source,tune,overlay,files,sampling)


def test_real_and_control_cli_refuse_arbitrary_source_root_before_execution(tmp_path,monkeypatch):
    monkeypatch.setattr(g.subprocess,'run',lambda *a,**kw:pytest.fail('no subprocess permitted'))
    for control,tune in [(False,'m42c82-uniform8-20260913'),(True,'c82-grader-selftest')]:
        args=['--source-root',str(tmp_path),'--destination',str(tmp_path/'grade'),
              '--overlay',str(tmp_path/'overlay'),'--tune',tune]
        if control:args.append('--control')
        with pytest.raises(g.GradingError,match='fixed approved root'):g.main(args)


@pytest.mark.parametrize('mode',['uniform8','native16'])
def test_c82_modes_require_group64_even_when_canonical_manifest_omits_it(tmp_path,mode):
    source,tune,overlay,sampling,files,path,e=evidence_fixture(tmp_path)
    if mode=='native16':
        new_tune='m42c82-native16-20260913';moved=[]
        for p in files:
            new=p.with_name(p.name.replace(tune,new_tune));p.rename(new);moved.append(new)
        files=moved;tune=new_tune;e['mode']=mode;e['tune']=tune
        e['kv']['kv_bits']=0;e['kv']['kv_quant_scheme']='turboquant'
    for p in files:
        if not p.name.endswith('.manifest.json'):continue
        m=json.loads(p.read_text());m['tune']=tune;m['kv']=dict(e['kv']);m['kv'].pop('kv_group_size')
        p.write_text(json.dumps(m))
    e['files']={p.name:g.sha(p) for p in files};path.write_text(json.dumps(e))
    assert g.validate_run_evidence(path,g.sha(path),source,tune,overlay,files,sampling)['mode']==mode


@pytest.mark.parametrize('mutation',['wrong_group','missing_group','wrong_scheme','old_bits','manifest_group'])
def test_c82_evidence_rejects_wrong_group_scheme_or_legacy_tq4(tmp_path,mutation):
    source,tune,overlay,sampling,files,path,e=evidence_fixture(tmp_path)
    if mutation=='wrong_group':e['kv']['kv_group_size']=32
    elif mutation=='missing_group':e['kv'].pop('kv_group_size')
    elif mutation=='wrong_scheme':e['kv']['kv_quant_scheme']='turboquant'
    elif mutation=='old_bits':e['kv']['kv_bits']=4
    else:
        m=json.loads(files[1].read_text());m['kv']['kv_group_size']=32
        files[1].write_text(json.dumps(m));e['files'][files[1].name]=g.sha(files[1])
    path.write_text(json.dumps(e))
    with pytest.raises(g.GradingError):g.validate_run_evidence(path,g.sha(path),source,tune,overlay,files,sampling)


@pytest.mark.parametrize('tune',['m42pilot-tq4-20260913','m42pilot-native16-20260913','c80-grader-selftest'])
def test_c82_never_accepts_old_c80_input_tags(tmp_path,tune):
    with pytest.raises(g.GradingError,match='unapproved tune'):
        g.main(['--source-root',str(tmp_path),'--destination',str(tmp_path/'out'),
                '--overlay',str(tmp_path/'overlay'),'--tune',tune])


def test_c82_selection_and_unique_container_namespace_are_pinned(tmp_path):
    assert g.SELECTION_SHA=='02b30efc7bd6d3fd94628a53a5e1f69d7255ee5fa3e4d86060790fc00f4a39e7'
    samples(tmp_path);calls=[]
    def run(cmd,**kwargs):calls.append(cmd);return fake_evaluation(cmd,**kwargs)
    g.NativeRunner(tmp_path,run=run)(command(tmp_path),timeout=10)
    assert calls[0][calls[0].index('--name')+1].startswith('c82-')
