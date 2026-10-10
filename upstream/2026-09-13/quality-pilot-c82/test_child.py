import copy,json
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
import child as c

PARAMS={'temperature':.5,'top_p':.95,'top_k':20,'min_p':0.,'presence_penalty':0.,'max_tokens':102400,'thinking_budget':81920,'enable_thinking':True,'reasoning_effort':'medium'}


def expected(n=15):
    from bench import benchmarks,generate,rowschema
    rows=[]
    for i in range(n):
        item={'id':f'id{i}','prompt':f'Problem{i}'}
        params={**PARAMS,'seed':rowschema.sample_seed(item['id'],0,base=0)}
        body={'model':'model','messages':generate._wrap_for_generation('humanevalplus',benchmarks.build_messages('humanevalplus',item),None,item['id']),'stream':False,**params}
        rows.append({'bench':'humanevalplus','id':item['id'],'seed':params['seed'],'wire':json.dumps(body),'payload':body})
    return rows


def response(ct=20,pt=100,finish='stop',peak=52):
    return {'choices':[{'index':0,'finish_reason':finish,'message':{'role':'assistant','content':'answer','reasoning':'thought'}}],
            'usage':{'prompt_tokens':pt,'completion_tokens':ct},
            'timings':{'draft_kind':'mtp','draft_rounds':3,'draft_n':5,'draft_n_accepted':4,'peak_memory':peak,'predicted_per_second':40.0}}


def guard(tmp_path,n=15):
    delegate=Mock(return_value=response())
    return c.Guard(expected(n),tmp_path,delegate,lambda *_:None,lambda *_:None),delegate


@pytest.mark.parametrize('mutation',['seed','prompt','temperature','model','stream','extra'])
def test_unapproved_request_aborts_before_http(tmp_path,mutation):
    g,delegate=guard(tmp_path);body=copy.deepcopy(expected()[0]['payload'])
    if mutation=='prompt':body['messages'][0]['content']+=' changed'
    elif mutation=='extra':body['tools']=[]
    else:body[mutation]='wrong'
    with pytest.raises(c.PilotAbort):g.post('/v1/chat/completions',body,timeout=21080)
    delegate.assert_not_called()


@pytest.mark.parametrize('field,value',[('prompt_tokens',None),('completion_tokens',-1),('completion_tokens',False),('completion_tokens',float('nan'))])
def test_malformed_usage_aborts_without_row(tmp_path,field,value):
    g,delegate=guard(tmp_path);bad=response();bad['usage'][field]=value;delegate.return_value=bad
    with pytest.raises(c.PilotAbort):g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)
    assert g.completed==0


@pytest.mark.parametrize('change',['finish','counter','counter_kind','aliases'])
def test_malformed_protocol_or_missing_engagement_aborts(tmp_path,change):
    g,delegate=guard(tmp_path);bad=response()
    if change=='finish':bad['choices'][0]['finish_reason']=None
    elif change=='aliases':bad['choices'][0]['message']['reasoning_content']='conflict'
    elif change=='counter':bad['timings']['draft_n']=0
    else:bad['timings']['draft_kind']='off'
    delegate.return_value=bad
    with pytest.raises(c.PilotAbort):g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)


def canonical_row(entry,ct=20,pt=100,finish='stop'):
    return {'id':entry['id'],'bench':entry['bench'],'model':'model','sample':0,'sampler_seed':entry['seed'],'seed_base':0,'schema_version':2,
            'prompt_tokens':pt,'completion_tokens':ct,'finish_reason':finish,'content':'answer','thinking_budget':81920,'converged':ct<81920 and finish=='stop',
            'draft':{'draft_kind':'mtp','draft_rounds':3,'draft_n':5,'draft_n_accepted':4},'wall_s':1}


def test_exact_fifteen_calls_no_extra_and_high_memory_not_stopped(tmp_path):
    g,delegate=guard(tmp_path);append=Mock()
    for e in expected():
        g.post('/v1/chat/completions',e['payload'],timeout=21080)
        g.append(Path('rows'),canonical_row(e),append)
    g.finish()
    assert delegate.call_count==15 and append.call_count==15
    with pytest.raises(c.PilotAbort):g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)
    assert delegate.call_count==15


def test_duplicate_unexpected_and_missing_rows_fail(tmp_path):
    g,_=guard(tmp_path)
    with pytest.raises(c.PilotAbort):g.finish()
    g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)
    bad=canonical_row(expected()[0]);bad['id']='wrong'
    with pytest.raises(c.PilotAbort):g.append(Path('rows'),bad,Mock())


def test_budget_hit_preserved_and_resolved(tmp_path):
    g,delegate=guard(tmp_path);delegate.return_value=response(ct=81920)
    e=expected()[0];g.post('/v1/chat/completions',e['payload'],timeout=21080)
    row=canonical_row(e,ct=81920)
    g.append(Path('rows'),row,Mock())
    assert row['resolved_thinking_budget']==81920 and row['converged'] is False


def test_transport_escapes_actual_canonical_catch_no_error_row_or_next_call(tmp_path):
    from bench import generate,client,model_params
    entries=expected();g,delegate=guard(tmp_path);delegate.side_effect=OSError('HTTP failed')
    queue=[('model','humanevalplus',{'id':f'id{i}','prompt':f'Problem{i}'},0) for i in range(2)]
    with patch.object(generate,'build_queue',return_value=(queue,{'humanevalplus':2})),patch.object(generate,'provenance_precheck'),patch.object(generate,'stamp_manifests'),patch.object(client,'preload',return_value=0),patch.object(model_params,'params_for',return_value=dict(PARAMS)),patch.object(client,'_post',side_effect=g.post),patch.object(generate,'_append') as append:
        with pytest.raises(c.PilotAbort):generate.run(['model'],['humanevalplus'],{'humanevalplus':5},sampling_profile='deployed',probe_timeout=21080)
    delegate.assert_called_once();append.assert_not_called()


def test_canonical_nonconvergence_mechanism_is_preserved(tmp_path):
    from bench import traces
    g,delegate=guard(tmp_path);bad=response(ct=81920,finish='length')
    text=('We repeatedly reason about this same unchanged step.\n'*80)
    bad['choices'][0]['message']['reasoning']=text;delegate.return_value=bad
    e=expected()[0];g.post('/v1/chat/completions',e['payload'],timeout=21080)
    row=canonical_row(e,ct=81920,finish='length');row['reasoning_stats']=traces.trace_stats(text)
    row['nonconv_kind']=traces.classify(row)
    assert row['nonconv_kind']=='degenerate_repetition'
    g.append(Path('rows'),row,Mock())
    assert row['nonconv_kind']=='degenerate_repetition'


def test_unexpected_context_budget_clamping_aborts(tmp_path):
    g,delegate=guard(tmp_path);delegate.return_value=response(pt=200000)
    with pytest.raises(c.PilotAbort,match='headroom'):g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)


def test_empty_reasoning_valid_alias_normalized_without_rewriting_raw(tmp_path):
    g,delegate=guard(tmp_path);raw=response();raw['choices'][0]['message'].update(reasoning='',reasoning_content='real trace');delegate.return_value=raw
    returned=g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)
    assert returned['choices'][0]['message']['reasoning']=='real trace'
    assert json.loads((tmp_path/'request-01/response.json').read_text())['choices'][0]['message']['reasoning']==''


@pytest.mark.parametrize('field,value',[('predicted_per_second',None),('predicted_per_second',float('inf')),('peak_memory',None),('peak_memory',False),('peak_memory',-1)])
def test_missing_invalid_required_telemetry_aborts(tmp_path,field,value):
    g,delegate=guard(tmp_path);raw=response();raw['timings'][field]=value;delegate.return_value=raw
    with pytest.raises(c.PilotAbort):g.post('/v1/chat/completions',expected()[0]['payload'],timeout=21080)


def test_content_filter_is_preserved_without_fabricated_mtp(tmp_path):
    g,delegate=guard(tmp_path);raw=response(ct=0,finish='content_filter');raw.pop('timings');delegate.return_value=raw
    e=expected()[0];g.post('/v1/chat/completions',e['payload'],timeout=21080)
    row=canonical_row(e,ct=0,finish='content_filter');row['draft']={k:None for k in row['draft']}
    g.append(Path('rows'),row,Mock())
    assert row['content_filter'] is True and row['converged'] is False


@pytest.mark.parametrize('mode',['native16','uniform8'])
def test_full_actual_canonical_cli_fifteen_requests_and_no_extra_generation(tmp_path,monkeypatch,mode):
    import io
    import runner as r
    from bench import benchmarks,client,generate,model_params,rowschema
    items={b:[{'id':f'{b}/{i}','prompt':f'Problem {i}','answer':'1'} for i in range(5)] for b in r.BENCHES}
    entries=[]
    for i in range(5):
        for b in r.BENCHES:
            item=items[b][i];seed=rowschema.sample_seed(item['id'],0,base=0)
            body={'model':r.MODEL,'messages':generate._wrap_for_generation(b,benchmarks.build_messages(b,item),None,item['id']),'stream':False,**PARAMS,'seed':seed}
            entries.append({'bench':b,'id':item['id'],'seed':seed,'payload':body,'wire':json.dumps(body)})
    results=tmp_path/'canonical';tag=f'm42c82-{mode}-20260913';out=tmp_path/'runs'/mode;out.mkdir(parents=True)
    frozen={'requests':entries,'items_by_bench':items,'module_hashes':{},'arms':{mode:{'overlay':'/fake/overlay','tune':tag,'results':{b:str(results/r.MODEL/f'{b}.{tag}.jsonl') for b in r.BENCHES}}}}
    requests=[]
    def fake_post(path,payload,timeout=3600):
        requests.append((path,copy.deepcopy(payload)))
        return {'status':'ready'} if path=='/v1/models/load' else response()
    monkeypatch.setenv('MLX_SERVE_CONFIG','/fake/overlay')
    with patch.object(r,'HERE',tmp_path),patch.object(r,'read_frozen',return_value=frozen),patch.object(r,'verify_frozen'),patch.object(r,'validate_imports'),patch.object(generate,'RESULTS',results),patch.object(generate,'provenance_precheck'),patch.object(generate,'stamp_manifests'),patch.object(model_params,'params_for',side_effect=lambda *a,**k:dict(PARAMS)),patch.object(client,'_post',side_effect=fake_post),patch('sys.stdin',io.StringIO(''.join(json.dumps({'ack':i})+'\n' for i in range(15)))):
        c.run(mode,'fake-sha',out)
    completions=[body for path,body in requests if path=='/v1/chat/completions']
    assert len(completions)==15
    assert [json.dumps(p) for p in completions]==[e['wire'] for e in entries]
    assert len([p for p,_ in requests if p=='/v1/models/load'])==1
    for b,path in frozen['arms'][mode]['results'].items():
        rows=[json.loads(line) for line in Path(path).read_text().splitlines()]
        assert len(rows)==5 and all(row['resolved_thinking_budget']==81920 for row in rows)



def test_events_are_c82_scoped(capsys):
    c.emit('COMPLETE',attempted=15,completed=15)
    assert capsys.readouterr().out.startswith('C82_EVENT ')
