"""C82 private supervisor. No router lifecycle, grading, or numeric memory cutoff."""
import argparse
import copy
import fcntl
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
STACK=ROOT/'stack-validation'
MODEL='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
BENCHES=('math500','humanevalplus','mbppplus')
SELECTION_SHA='02b30efc7bd6d3fd94628a53a5e1f69d7255ee5fa3e4d86060790fc00f4a39e7'
TREATMENTS={'native16':(0,'turboquant'),'uniform8':(8,'uniform')}
SPLIT_KV_ENV=('KV_KEY_BITS','KV_VALUE_BITS','KV_KEY_SCHEME','KV_VALUE_SCHEME')
_CAPACITY_HELPERS=None
TIMEOUT=21080
BOUND=15*TIMEOUT+1200
MODULES=('benchmarks','generate','client','convergence','model_params','rowschema','paths','traces','depth','provenance')


class PilotError(RuntimeError):pass


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def jhash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def capacity_helpers():
    global _CAPACITY_HELPERS
    path=ROOT/'capacity_runner.py'
    if _CAPACITY_HELPERS is None:
        name='_c82_original_capacity_helpers'
        spec=importlib.util.spec_from_file_location(name,path)
        if spec is None or spec.loader is None:raise PilotError('cannot load original capacity helper')
        module=importlib.util.module_from_spec(spec)
        sys.modules[name]=module
        spec.loader.exec_module(module)
        _CAPACITY_HELPERS=module
    if Path(_CAPACITY_HELPERS.__file__).resolve()!=path.resolve():raise PilotError('capacity helper source path differs')
    return _CAPACITY_HELPERS


def require_new(path,root):
    path,root=Path(path),Path(root).resolve()
    if not path.resolve().is_relative_to(root):raise PilotError('output symlink escapes private root')
    if path.exists():raise PilotError('refusing existing output or resume: '+str(path))


def validate_imports(expected=None):
    if not STACK.resolve().is_relative_to(ROOT.resolve()):raise PilotError('isolated stack root escapes private integration')
    hashes={}
    for name in MODULES:
        module=importlib.import_module('bench.'+name)
        path=STACK/'benchmark/bench'/f'{name}.py'
        if Path(module.__file__).resolve()!=path.resolve() or not path.resolve().is_relative_to(STACK.resolve()):
            raise PilotError('benchmark module resolves outside isolated clone: '+name)
        hashes[name]=sha(path)
    hashes['run.py']=sha(STACK/'benchmark/run.py')
    from bench import generate
    if generate.results_root().resolve()!=(STACK/'benchmark/results').resolve():raise PilotError('canonical result path overridden')
    if not (STACK/'benchmark/results').resolve().is_relative_to(STACK.resolve()):raise PilotError('canonical result symlink escape')
    if expected is not None and hashes!=expected:raise PilotError('canonical module hashes changed')
    return hashes


def select_corpus_items(bench,records,wanted):
    from bench import benchmarks
    if bench=='math500':items=[{'id':p['unique_id'],'prompt':p['problem'],'answer':p['answer']} for p in records]
    else:items=[{'id':p['task_id'],'prompt':p['prompt'],'meta':{'entry_point':p.get('entry_point')}} for p in records]
    ordered=benchmarks._subsample(items,None,0)
    result=[p for p in ordered if p['id'] in set(wanted)]
    if len(result)!=5 or {p['id'] for p in result}!=set(wanted):raise PilotError('selected corpus IDs missing/duplicate')
    return result


def validate_overlay_pair(a,b):
    first,second=copy.deepcopy(a),copy.deepcopy(b)
    e1=[e for e in first['models'] if e['name']==MODEL]
    e2=[e for e in second['models'] if e['name']==MODEL]
    if len(e1)!=1 or len(e2)!=1 or (e1[0].get('kv_bits'),e1[0].get('kv_quant_scheme'))!=TREATMENTS['native16'] or (e2[0].get('kv_bits'),e2[0].get('kv_quant_scheme'))!=TREATMENTS['uniform8']:
        raise PilotError('expected native0/turboquant-disabled and uniform8/uniform')
    e2[0]['kv_bits'],e2[0]['kv_quant_scheme']=TREATMENTS['native16']
    if first!=second:raise PilotError('overlays differ beyond kv_bits/kv_quant_scheme')


def validate_layout_evidence(layout):
    if layout.get('model')!=MODEL:raise PilotError('layout evidence is for another model')
    arms=layout.get('arms',{})
    expected={'native16':{'ArraysCache':48,'PreallocKVCache':16},
              'uniform8':{'ArraysCache':48,'PreallocQuantizedKVCache':16}}
    for mode,counts in expected.items():
        if arms.get(mode,{}).get('counts')!=counts or arms[mode].get('full_floor')!=262144:
            raise PilotError('bounded cache layout/floor differs: '+mode)
    if arms['uniform8'].get('group_size')!=64:raise PilotError('bounded uniform cache group differs')


def prepare(source_repo,native_overlay,uniform_overlay):
    import yaml
    from bench import benchmarks,generate,model_params,rowschema
    module_hashes=validate_imports()
    if sha(HERE/'selection.json')!=SELECTION_SHA:raise PilotError('selection SHA differs from C82 approval')
    selection=json.loads((HERE/'selection.json').read_text())
    if selection.get('decision')!='C82' or selection['model']!=MODEL or selection['approved_requests']!=30 or selection['states']!=['native16','uniform8']:
        raise PilotError('selection experiment differs')
    inventory={str(HERE/'selection.json'):SELECTION_SHA}
    layout_path=HERE/'layout-evidence.json'
    layout=json.loads(layout_path.read_text());validate_layout_evidence(layout)
    inventory[str(layout_path)]=sha(layout_path)
    substitutions={'$STACK_REPO':str(Path(source_repo).resolve()),'$STACK_WORKDIR':str(ROOT.parents[1]),'$HOME':str(Path.home())}
    def verify_input(info):
        text=info['path']
        for key,value in substitutions.items():text=text.replace(key,value)
        path=Path(text)
        if '$' in text or not path.is_file() or sha(path)!=info['sha256'] or path.stat().st_size!=info['bytes']:
            raise PilotError('frozen input missing/hash mismatch: '+text)
        inventory[str(path.resolve())]=info['sha256']
        return path
    parent=Path(source_repo)/'docs/specs/c77-proposed-selection.json'
    if sha(parent)!=selection['parent_selection_sha256']:raise PilotError('parent approval selection changed')
    inventory[str(parent.resolve())]=selection['parent_selection_sha256']
    for info in selection['source_rules']:verify_input(info)
    groups={g['axis']:g for g in selection['groups']}
    if set(groups)!=set(BENCHES) or len(selection['groups'])!=3:raise PilotError('unexpected axis groups')
    items_by_bench={}
    selected_meta={}
    for bench in BENCHES:
        group=groups[bench]
        for info in group['sources'].values():verify_input(info)
        info=selection['corpora'][bench];path=verify_input(info)
        if bench=='math500':
            import pyarrow.ipc as ipc
            with path.open('rb') as f:records=ipc.open_stream(f).read_all().to_pylist()
        else:records=[json.loads(line) for line in path.read_text().splitlines() if line]
        keys=[p[info['identity_key']] for p in records]
        if len(set(keys))!=info['unique_item_count'] or len(keys)!=len(set(keys)) or jhash(sorted(keys))!=info['sorted_ids_sha256']:
            raise PilotError('corpus identity inventory changed')
        indexed=dict(zip(keys,records));metas=group['items']
        if len(metas)!=5 or {m['id'] for m in metas}!=set(group['selected_ids']):raise PilotError('selected group size/identity changed')
        for meta in metas:
            raw=indexed[meta['id']]
            prompt=raw['problem'] if bench=='math500' else raw['prompt']
            if jhash(raw)!=meta['corpus_record_sha256'] or hashlib.sha256(prompt.encode()).hexdigest()!=meta['corpus_prompt_sha256']:
                raise PilotError('selected record/prompt hash changed')
            if meta['sample']!=0 or meta['seed_base']!=0 or meta['sampler_seed']!=rowschema.sample_seed(meta['id'],0,base=0) or meta['model']!=MODEL or meta['bench']!=bench:
                raise PilotError('selected identity/sample/seed differs')
            selected_meta[(bench,meta['id'])]=meta
        items_by_bench[bench]=select_corpus_items(bench,records,group['selected_ids'])
    docs=[yaml.safe_load(Path(p).read_text()) for p in (native_overlay,uniform_overlay)]
    validate_overlay_pair(*docs)
    arms={}
    for mode,path,doc in zip(('native16','uniform8'),(native_overlay,uniform_overlay),docs):
        path=Path(path).resolve()
        if not path.is_relative_to(ROOT):raise PilotError('overlay outside private integration')
        entry=next(e for e in doc['models'] if e['name']==MODEL)
        params=model_params.params_for(MODEL,profile='deployed',registry_path=str(path))
        expected_tune=groups['math500']['historical_configuration']['sampling']
        if params!=expected_tune or params.get('max_tokens')!=102400 or params.get('thinking_budget')!=81920 or not params.get('enable_thinking'):
            raise PilotError('deployed full-budget tune differs')
        if any(entry.get(k)!=v for k,v in {'max_kv_cache_size':262144,'kv_prealloc_tokens':262144,'prefill_step_size':512,'draft_kind':'mtp'}.items()):
            raise PilotError('cap/preallocation/prefill/predictor differs')
        tag=f'm42c82-{mode}-20260913'
        results={b:str(STACK/'benchmark/results'/MODEL/f'{b}.{tag}.jsonl') for b in BENCHES}
        arms[mode]={'overlay':str(path),'overlay_sha256':sha(path),'entry':entry,'params':params,'tune':tag,'results':results}
        inventory[str(path)]=sha(path)
    config_path=Path(arms['native16']['entry']['hf_path'])/'config.json'
    if sha(config_path)!=layout['config_sha256']:raise PilotError('bounded layout checkpoint config differs')
    inventory[str(config_path.resolve())]=sha(config_path)
    requests=[]
    for i in range(5):
        for bench in BENCHES:
            item=items_by_bench[bench][i];seed=selected_meta[(bench,item['id'])]['sampler_seed']
            messages=generate._wrap_for_generation(bench,benchmarks.build_messages(bench,item),None,item['id'])
            payloads=[{'model':MODEL,'messages':messages,'stream':False,**arms[m]['params'],'seed':seed} for m in ('native16','uniform8')]
            if json.dumps(payloads[0])!=json.dumps(payloads[1]):raise PilotError('paired payload bytes differ')
            requests.append({'bench':bench,'id':item['id'],'seed':seed,'payload':payloads[0],'wire':json.dumps(payloads[0])})
    return {'selection_sha256':SELECTION_SHA,'cache_layout_evidence_sha256':inventory[str(layout_path)],'cache_layout_scope':layout['kind'],'native_live_model_dtype_observed':layout.get('native_live_model_dtype_observed'),'module_hashes':module_hashes,'input_hashes':inventory,'requests':requests,'items_by_bench':items_by_bench,'arms':arms,
            'instrument_hashes':{str(p):sha(p) for p in (HERE/'runner.py',HERE/'child.py',ROOT/'capacity_runner.py')},
            'historical_generation_reference_s':selection['generation_time_lower_bound_s'],'timing_reference_note':'inherited historical C80 planning value; not a uniform8 prediction or guaranteed bound','memory_policy':'rough48GB guideline; no automatic numeric cutoff'}


def read_frozen(expected_sha=None):
    path=HERE/'frozen.json'
    if expected_sha is not None and sha(path)!=expected_sha:raise PilotError('frozen plan changed')
    frozen=json.loads(path.read_text())
    if frozen.get('selection_sha256')!=SELECTION_SHA:raise PilotError('wrong selection in frozen plan')
    return frozen


def validate_frozen_items(frozen,selection):
    groups={g['axis']:g for g in selection['groups']}
    if set(frozen['items_by_bench'])!=set(groups):raise PilotError('frozen axes differ')
    for bench,items in frozen['items_by_bench'].items():
        metas={m['id']:m for m in groups[bench]['items']}
        if len(items)!=len(metas) or {i['id'] for i in items}!=set(metas):raise PilotError('frozen identities differ')
        for item in items:
            meta=metas[item['id']]
            if hashlib.sha256(item['prompt'].encode()).hexdigest()!=meta['corpus_prompt_sha256']:
                raise PilotError('frozen prompt differs from approved corpus')
            if 'answer_gold_sha256' in meta and hashlib.sha256(str(item.get('answer')).encode()).hexdigest()!=meta['answer_gold_sha256']:
                raise PilotError('frozen math answer differs')


def verify_frozen(frozen):
    for mapping in ('input_hashes','instrument_hashes'):
        for path,digest in frozen[mapping].items():
            if sha(path)!=digest:raise PilotError('frozen source/input changed: '+path)
    validate_imports(frozen['module_hashes'])
    selection=json.loads((HERE/'selection.json').read_text())
    validate_frozen_items(frozen,selection)
    from bench import benchmarks,generate,rowschema,model_params
    for arm in frozen['arms'].values():
        if model_params.params_for(MODEL,profile='deployed',registry_path=arm['overlay'])!=arm['params']:
            raise PilotError('frozen sampling differs from overlay')
    actual=[]
    for i in range(5):
        for bench in BENCHES:
            item=frozen['items_by_bench'][bench][i];seed=rowschema.sample_seed(item['id'],0,base=0)
            body={'model':MODEL,'messages':generate._wrap_for_generation(bench,benchmarks.build_messages(bench,item),None,item['id']),'stream':False,**frozen['arms']['native16']['params'],'seed':seed}
            actual.append({'bench':bench,'id':item['id'],'seed':seed,'payload':body,'wire':json.dumps(body)})
    if actual!=frozen['requests']:raise PilotError('frozen request bytes differ from canonical builders')


def canonical_args(frozen,mode):
    return ['generate','--models',MODEL,'--benches',','.join(BENCHES),
            '--limit',','.join(b+'=5' for b in BENCHES),'--ids',','.join(b+'='+':'.join(i['id'] for i in frozen['items_by_bench'][b]) for b in BENCHES),
            '--sampling-profile','deployed','--samples','1','--seed-base','0','--seed','0','--order','roundrobin',
            '--chunks','all','--tune',frozen['arms'][mode]['tune'],'--probe-timeout',str(TIMEOUT)]


def validate_manifest(man,arm,source,tag):
    if man.get('model')!=MODEL or man.get('sampling_profile')!='deployed' or man.get('sampling')!=arm['params'] or man.get('tune')!=tag:
        raise PilotError('manifest identity/profile/tune/sampling mismatch')
    if man.get('registry',{}).get('sha256')!=arm['overlay_sha256'] or man.get('git',{}).get('serving_path')!=source:
        raise PilotError('manifest registry/source mismatch')
    if man.get('runtime',{}).get('draft_kind')!='mtp' or man.get('runtime',{}).get('probe_timeout_s')!=TIMEOUT:
        raise PilotError('manifest predictor/timeout mismatch')
    for key in ('kv_bits','kv_quant_scheme','max_kv_cache_size','kv_prealloc_tokens','prefill_step_size','quantized_kv_start'):
        if man.get('kv',{}).get(key)!=arm['entry'].get(key):raise PilotError('manifest KV mismatch: '+key)


def before_request(event,completed,frozen,verify,ack):
    if type(event.get('index')) is not int or event['index']!=completed or completed>=15:raise PilotError('unexpected request sequence')
    expected=frozen['requests'][completed]
    if (event.get('bench'),event.get('id'))!=(expected['bench'],expected['id']):raise PilotError('unexpected request identity')
    verify()
    ack({'ack':completed})


def admit_item(event,completed,frozen,monitor,out):
    if event['completed']!=completed+1 or completed>=15:raise PilotError('unexpected/duplicate item event')
    row=event['row'];expected=frozen['requests'][completed]
    if (row['bench'],row['id'],row['sampler_seed'])!=(expected['bench'],expected['id'],expected['seed']):raise PilotError('item event differs from selection')
    completed+=1;monitor.complete(row);monitor.log('ITEM',completed=completed,row=row)
    save(Path(out)/'progress.json',{'completed':completed,'rows':monitor.rows})
    return completed


class Monitor:
    def __init__(self,path):
        self.path=Path(path);self.rows=[];self.previous=0;self.current=None;self.started=time.monotonic();self.stop=threading.Event();self.lock=threading.RLock();self.thread=None
    def log(self,event,**fields):
        with self.lock,self.path.open('a') as f:f.write(json.dumps({'event':event,'unix_time':time.time(),**fields},allow_nan=False)+'\n')
    def complete(self,row):
        with self.lock:self.rows.append(row);self.current=None
    def assess(self):
        with self.lock:
            n=len(self.rows);delta=n-self.previous;self.previous=n
            times=[r['wall_s'] for r in self.rows]
            return {'completed':n,'counter_delta':delta,'progressing':delta>0,'current':self.current,'mean_wall_s':sum(times)/n if n else None,'max_wall_s':max(times) if n else None,
                    'eta_s_mean':sum(times)/n*(15-n) if n else None,'eta_note':'completed-item mean estimate, not a guaranteed bound; allow right tails',
                    'tokens':[r['completion_tokens'] for r in self.rows],'convergence':[r['converged'] for r in self.rows],
                    'nonconv_kinds':[r.get('nonconv_kind') for r in self.rows if not r['converged']],
                    'elapsed_s':time.monotonic()-self.started,'fragment_progress':'unavailable: canonical nonstreaming client',
                    'recommendation':'continue approved bounded arm when provenance is valid; retain nonconvergence, no memory threshold stop'}
    def selftest(self):
        fake=Monitor(self.path);fake.complete({'wall_s':2,'completion_tokens':1,'converged':True});a=fake.assess();ok=a['counter_delta']==1 and a['eta_s_mean']==28 and fake.assess()['counter_delta']==0
        self.log('SELFTEST',passed=ok);return ok
    def start(self):
        def loop():
            while not self.stop.wait(300):self.log('ASSESSMENT',**self.assess())
        self.thread=threading.Thread(target=loop,daemon=True);self.thread.start()
    def close(self,status,error=None):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        self.log('RUNNER-EXIT',status=status,error=error,**self.assess())


def validate_child_environment(observed,expected):
    for key in ('PYTHONPATH','MLX_SERVE_CONFIG','MLX_BENCH_RESULTS','MLX_SERVE_BASE','PYTHONDONTWRITEBYTECODE','TMPDIR'):
        if observed.get(key)!=expected[key]:raise PilotError('actual child environment differs: '+key)
    if 'APC_ENABLED' in observed:raise PilotError('child inherited APC')


def stop_owned(child):
    if child is None:return
    try:os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    child.wait(timeout=15)
    if child.stdin:child.stdin.close()
    if child.stdout:child.stdout.close()


def validate_treatment_runtime(mode,evidence,environment):
    bits,scheme=TREATMENTS[mode]
    if environment.get('KV_BITS')!=str(bits):raise PilotError('worker must explicitly inherit matching KV_BITS')
    for key in SPLIT_KV_ENV:
        if environment.get(key) is not None:raise PilotError('unapproved split KV environment override: '+key)
    command=evidence['worker']['command']
    for token in command:
        if not token.startswith('--'):continue
        option=token.partition('=')[0]
        for key in SPLIT_KV_ENV:
            if ('--'+key.lower().replace('_','-')).startswith(option):
                raise PilotError('unapproved split KV command override: '+token)
        for canonical in ('--kv-group-size','--kv-quant-scheme'):
            if canonical.startswith(option) and token!=canonical:
                raise PilotError('noncanonical cache option: '+token)
    try:found=capacity_helpers().flags(command)
    except Exception as exc:raise PilotError('invalid cache command shape') from exc
    if found.get('--kv-quant-scheme')!=scheme:raise PilotError('worker cache scheme differs')
    if found.get('--kv-group-size') not in (None,'64') or environment.get('KV_GROUP_SIZE') not in (None,'64'):
        raise PilotError('worker cache group size differs from64')
    if environment.get('KV_QUANT_SCHEME') not in (None,scheme):raise PilotError('worker scheme environment differs')


def collect_treatment_live(mode,arm,launch,launch_sha,owned_pid=None):
    cap=capacity_helpers()
    evidence=cap.collect_live(arm['entry'],Path(arm['overlay']),STACK,ROOT/'runtime-venv',launch,launch_sha,owned_pid=owned_pid)
    import psutil
    environment=psutil.Process(evidence['worker']['pid']).environ()
    observed={k:environment.get(k) for k in ('KV_BITS','KV_GROUP_SIZE','KV_QUANT_SCHEME',*SPLIT_KV_ENV)}
    validate_treatment_runtime(mode,evidence,observed)
    evidence['c82_cache_environment']=observed
    evidence['cache_layout_basis']='root-owned bounded layout evidence; not inferred from benchmark manifests'
    return evidence


def execute(mode,launch,frozen_sha):
    frozen=read_frozen(frozen_sha);verify_frozen(frozen)
    arm=frozen['arms'][mode];out=HERE/'runs'/mode
    require_new(out,HERE)
    for path in arm['results'].values():
        for candidate in (Path(path),Path(path).with_suffix('.manifest.json')):
            require_new(candidate,STACK)
    if mode=='uniform8':
        previous=json.loads((HERE/'runs/native16/summary.json').read_text())
        if previous.get('status')!='complete' or previous.get('completed')!=15 or previous.get('frozen_sha256')!=frozen_sha:raise PilotError('uniform8 arm requires completed paired native16 arm')
        for i,entry in enumerate(frozen['requests']):
            if (HERE/'runs/native16'/f'request-{i+1:02d}/request.json').read_text()!=entry['wire']:raise PilotError('native16 actual payload differs from frozen pair')
    env=dict(os.environ,PYTHONPATH=str(STACK/'benchmark'),MLX_SERVE_CONFIG=arm['overlay'],MLX_SERVE_BASE='http://localhost:8000',
             MLX_BENCH_RESULTS=str(STACK/'benchmark/results'),PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TMPDIR=str(ROOT/'tmp'))
    if os.environ.get('APC_ENABLED') is not None:raise PilotError('APC_ENABLED must be absent')
    if os.environ.get('MLX_SERVE_CONFIG')!=arm['overlay'] or os.environ.get('PYTHONPATH')!=str(STACK/'benchmark'):raise PilotError('parent overlay/module environment differs')
    launch=Path(launch).resolve();launch_sha=sha(launch)
    cap=capacity_helpers()
    before=collect_treatment_live(mode,arm,launch,launch_sha)
    out.mkdir(parents=True)
    save(out/'prelaunch.json',{'evidence':before,'frozen_sha256':frozen_sha,'launch_sha256':launch_sha,'command_args':canonical_args(frozen,mode)})
    monitor=Monitor(out/'heartbeat.jsonl');child=None;status='instrument-error';error=None;completed=0;complete_event=False
    started=time.monotonic()
    try:
        if not monitor.selftest():raise PilotError('monitor selftest failed')
        monitor.start()
        command=[sys.executable,str(HERE/'child.py'),'--mode',mode,'--frozen-sha',frozen_sha,'--out',str(out)]
        child=subprocess.Popen(command,cwd=str(STACK/'benchmark'),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
        import psutil
        observed=psutil.Process(child.pid).environ()
        validate_child_environment(observed,env)
        save(out/'driver.json',{'pid':child.pid,'command':command,'environment':{k:observed.get(k) for k in env if k in ('PYTHONPATH','MLX_SERVE_CONFIG','MLX_BENCH_RESULTS','MLX_SERVE_BASE','PYTHONDONTWRITEBYTECODE','TMPDIR')},'bound_s':BOUND})
        lines=queue.Queue()
        def read():
            try:
                for line in child.stdout:lines.put(line)
            finally:lines.put(None)
        threading.Thread(target=read,daemon=True).start()
        def verify():
            if sha(HERE/'frozen.json')!=frozen_sha:raise PilotError('frozen plan changed during run')
            verify_frozen(frozen)
            after=collect_treatment_live(mode,arm,launch,launch_sha,owned_pid=child.pid)
            cap.assert_stable(before,after)
            for path in arm['results'].values():
                man=json.loads(Path(path).with_suffix('.manifest.json').read_text())
                validate_manifest(man,arm,before['source']['serving_path'],arm['tune'])
        def ack(value):child.stdin.write(json.dumps(value)+'\n');child.stdin.flush()
        eof=False
        with (out/'child.log').open('w') as log:
            while not eof or child.poll() is None:
                if time.monotonic()-started>BOUND:raise PilotError('derived child lifetime bound exceeded')
                try:line=lines.get(timeout=.5)
                except queue.Empty:continue
                if line is None:eof=True;continue
                log.write(line);log.flush()
                if not line.startswith('C82_EVENT '):continue
                event=json.loads(line[len('C82_EVENT '):])
                if event['event']=='BEFORE_REQUEST':
                    monitor.current={'index':event['index'],'bench':event['bench'],'id':event['id']}
                    before_request(event,completed,frozen,verify,ack)
                elif event['event']=='ITEM':
                    completed=admit_item(event,completed,frozen,monitor,out)
                elif event['event']=='COMPLETE':
                    if event['attempted']!=15 or event['completed']!=15 or completed!=15:raise PilotError('incomplete terminal count')
                    complete_event=True
                else:raise PilotError('child infrastructure failure: '+str(event))
            if child.wait(timeout=15)!=0 or not complete_event:raise PilotError('child failed/incomplete')
        verify()
        final=[]
        for bench,path in arm['results'].items():
            rows=[json.loads(line) for line in Path(path).read_text().splitlines() if line]
            if len(rows)!=5 or {r['id'] for r in rows}!={e['id'] for e in frozen['requests'] if e['bench']==bench}:raise PilotError('final canonical identities/counts differ')
            final+=rows
        if len(final)!=15 or any(r.get('error') for r in final):raise PilotError('final canonical rows invalid')
        status='complete'
    except BaseException as exc:error=str(exc);raise
    finally:
        try:
            stop_owned(child)
        except Exception as exc:
            status='instrument-error';error='owned-child cleanup failed: '+str(exc)
            raise PilotError(error) from exc
        finally:
            try:
                save(out/'summary.json',{'status':status,'error':error,'mode':mode,'completed':completed,'frozen_sha256':frozen_sha,'rows':monitor.rows,'graded':False,'request_maximum':15,'memory_policy':'no numeric cutoff; root owns worker cleanup'})
            finally:monitor.close(status,error)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--source-repo',type=Path,required=True);prep.add_argument('--native16-overlay',type=Path,required=True);prep.add_argument('--uniform8-overlay',type=Path,required=True);prep.add_argument('--dry-run',action='store_true')
    run=sub.add_parser('run');run.add_argument('--mode',choices=['native16','uniform8'],required=True);run.add_argument('--launch-evidence',required=True);run.add_argument('--frozen-sha',required=True)
    args=p.parse_args()
    try:
        if args.command=='prepare':
            frozen=prepare(args.source_repo,args.native16_overlay,args.uniform8_overlay)
            if not args.dry_run:require_new(HERE/'frozen.json',HERE);save(HERE/'frozen.json',frozen)
            print(json.dumps({'requests_per_arm':len(frozen['requests']),'payload_pair_sha256':jhash(frozen['requests']),'dry_run':args.dry_run}));return 0
        with (HERE/'pilot.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            def interrupt(signum,frame):raise PilotError('supervisor signal '+str(signum))
            signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
            execute(args.mode,args.launch_evidence,args.frozen_sha);return 0
    except BaseException as exc:
        print('C82 INSTRUMENT ERROR: '+str(exc),flush=True);return 2


if __name__=='__main__':raise SystemExit(main())
