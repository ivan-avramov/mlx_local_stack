#!/usr/bin/env python3
"""Private M43 capacity supervisor. Requires an already loaded, verified NEW router."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time

INSTRUMENT_DIR = Path(__file__).resolve().parent
HERE = INSTRUMENT_DIR.parent
GRID = (131072,196608,262144)
CAP = 262144
GATE_GB = 48
REQUEST_TIMEOUT = 7200
CALIBRATION_TIMEOUT = 120
PREFILL_REFERENCE_S = {131072:393.95,196608:1001.27,262144:1987.85}
PREFILL_REFERENCE_SOURCE = "benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/capacity_ladder.m41on.jsonl"
CHILD_BOUND = CALIBRATION_TIMEOUT + len(GRID)*REQUEST_TIMEOUT + 600
ENV_KEYS = ('MLX_SERVE_CONFIG','MLX_VLM_CACHE_SESSION_MAX','APC_ENABLED','HF_HUB_OFFLINE','TMPDIR','PYTHONPATH','PYTHONHOME','KV_BITS','KV_GROUP_SIZE','KV_KEY_BITS','KV_VALUE_BITS','KV_KEY_SCHEME','KV_VALUE_SCHEME')
SOURCE_HEADS = {'src/mlx-vlm':'c5a6f97bb918d4aa90b9d501b573721d34ab76e0',
                'src/mlx-serve':'f8f1df4952b2baf15f3504159f2869e170795fb2'}


class InstrumentError(RuntimeError):
    pass


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(cmd, **kwargs):
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=60,**kwargs)
    if p.returncode:
        raise InstrumentError('read-only precheck failed: '+str(cmd[:3])+' '+p.stderr[-500:])
    return p.stdout.strip()


def capacity_command(python, model, tag, calibration_evidence=None):
    evidence=calibration_evidence or HERE/'capacity'/tag/model/'calibration.json'
    return [str(python),str(INSTRUMENT_DIR/'capacity_child.py'),'--calibration-evidence',str(evidence),'--model',model,
            '--grid',','.join(map(str,GRID)),'--gate-gb',str(GATE_GB),
            '--sampling-profile','deployed','--out-tag',tag,
            '--request-timeout',str(REQUEST_TIMEOUT),'--no-preload']


def flags(command):
    result={}
    allowed={'--model','--host','--port','--max-tokens','--max-kv-size','--kv-prealloc-tokens','--kv-bits','--kv-group-size','--kv-quant-scheme','--prefill-step-size','--generation-defaults','--draft-kind','--draft-model','--draft-block-size','--quantized-kv-start','--cache-limit-gb','--memory-limit-frac'}
    for i,key in enumerate(command):
        if key.startswith('--'):
            if key not in allowed:raise InstrumentError('noncanonical or unapproved worker option: '+key)
            option=key.partition('=')[0]
            if '--kv-bits'.startswith(option) and key!='--kv-bits':
                raise InstrumentError('noncanonical KV-bit option spelling: '+key)
            if key in result or i+1==len(command):
                raise InstrumentError('duplicate/incomplete worker flag '+key)
            result[key]=command[i+1]
    return result


def validate_environment(environment, overlay):
    if environment.get('MLX_SERVE_CONFIG')!=str(overlay):
        raise InstrumentError('live process overlay differs')
    if environment.get('MLX_VLM_CACHE_SESSION_MAX')!='2':
        raise InstrumentError('live session maximum is not 2')
    if environment.get('APC_ENABLED') is not None:
        raise InstrumentError('APC_ENABLED must be absent, including value 0')
    if environment.get('HF_HUB_OFFLINE')!='1':
        raise InstrumentError('offline model access is required')


def is_worker_command(command):
    return any(Path(arg).name=='mlx_vlm.server' for arg in command)


def validate_origins(origins,root):
    expected={'mlx_vlm':root/'mlx-vlm/mlx_vlm/__init__.py',
              'mlx_serve':root/'mlx-serve/src/mlx_serve/__init__.py'}
    if any(not origins.get(k) or Path(origins[k]).resolve()!=path.resolve() for k,path in expected.items()):
        raise InstrumentError('runtime package origins are not the verified integration sources')


def validate_omitted_unquantized_bits(found, environment):
    if '--kv-bits' in found:
        raise InstrumentError('unquantized KV launcher must omit --kv-bits')
    raw=environment.get('KV_BITS')
    if raw is None:
        return
    if not isinstance(raw,str):
        raise InstrumentError('worker KV_BITS environment value is malformed')
    try:
        value=float(raw)
    except ValueError as exc:
        raise InstrumentError('worker inherited malformed KV_BITS') from exc
    if not math.isfinite(value) or value!=0.0:
        raise InstrumentError('unquantized worker inherited nonzero or nonfinite KV_BITS')


def validate_worker(worker, entry, overlay, runtime):
    forbidden_env=('KV_KEY_BITS','KV_VALUE_BITS','KV_KEY_SCHEME','KV_VALUE_SCHEME')
    forbidden_flags=('--kv-key-bits','--kv-value-bits','--kv-key-scheme','--kv-value-scheme')
    if any(worker.get('environment',{}).get(k) is not None for k in forbidden_env):
        raise InstrumentError('unapproved split KV environment override')
    if any(arg.startswith('--') and any(opt.startswith(arg.split('=')[0]) for opt in forbidden_flags) for arg in worker['command']):
        raise InstrumentError('unapproved split KV flag')
    if worker.get('environment',{}).get('KV_GROUP_SIZE') not in (None,'64'):
        raise InstrumentError('unapproved KV group environment')
    command=worker['command']
    for i,arg in enumerate(command):
        if arg.startswith('--') and '--kv-group-size'.startswith(arg.split('=')[0]):
            if arg!='--kv-group-size' or i+1>=len(command) or command[i+1]!='64':
                raise InstrumentError('unapproved KV group flag')
    if not command or str(Path(command[0]).parent)!=str(runtime/'bin'):
        raise InstrumentError('worker is not executing through NEW runtime venv')
    if not is_worker_command(command):
        raise InstrumentError('worker command is not mlx_vlm.server')
    validate_environment(worker['environment'],overlay)
    found=flags(command)
    expected={'--model':entry['hf_path'],'--max-kv-size':CAP,'--kv-prealloc-tokens':CAP,
              '--prefill-step-size':entry['prefill_step_size'],
              '--draft-kind':'mtp','--draft-model':entry['draft_model']}
    if entry.get('kv_bits',0)==0:
        validate_omitted_unquantized_bits(found,worker['environment'])
    else:
        expected['--kv-bits']=entry['kv_bits']
    if entry.get('kv_quant_scheme'):
        expected['--kv-quant-scheme']=entry['kv_quant_scheme']
    if entry.get('quantized_kv_start') is not None:
        expected['--quantized-kv-start']=entry['quantized_kv_start']
    for key,value in expected.items():
        if found.get(key)!=str(value):
            raise InstrumentError('worker '+key+' differs from explicit overlay')
    try:
        gd=json.loads(found.get('--generation-defaults','null'))
    except ValueError as exc:
        raise InstrumentError('worker sampling is malformed') from exc
    if gd!=entry['generation_defaults']:
        raise InstrumentError('worker deployed sampling differs')


def validate_manifest(man, expected):
    if man.get('registry',{}).get('sha256')!=expected['registry_sha256']:
        raise InstrumentError('result manifest overlay SHA differs')
    if man.get('runtime',{}).get('draft_kind')!='mtp':
        raise InstrumentError('result manifest predictor is not MTP')
    if man.get('sampling_profile')!='deployed':
        raise InstrumentError('result manifest is not deployed profile')
    for key in ('max_kv_cache_size','kv_prealloc_tokens'):
        if man.get('kv',{}).get(key)!=CAP:
            raise InstrumentError('result manifest '+key+' is not full cap')
    if man.get('git',{}).get('serving_path')!=expected['serving_path']:
        raise InstrumentError('result serving source hashes differ')
    if expected.get('sampling') is not None and man.get('sampling')!=expected['sampling']:
        raise InstrumentError('result sampling differs from bounded capacity probe')
    if man.get('sampling',{}).get('max_tokens')!=256 or man.get('sampling',{}).get('thinking_budget')!=256:
        raise InstrumentError('capacity probe bounds differ from M41 procedure')


def validate_peak(record):
    if record.get('error') or record.get('error_kind'):
        raise InstrumentError('transport/runtime error is not memory evidence: '+str(record.get('error')))
    peak=record.get('server_peak_gb')
    if type(peak) not in (int,float) or not math.isfinite(peak) or peak<0:
        raise InstrumentError('missing or invalid MLX peak telemetry; no gate verdict')
    if record.get('fits') is not (peak<=GATE_GB):
        raise InstrumentError('fits does not match measured MLX peak gate')


def classify_records(records):
    if not records:
        raise InstrumentError('no completed capacity records')
    contexts=[]
    actual=[]
    for record in records:
        validate_peak(record)
        if record.get('ctx') not in GRID or record['ctx'] in contexts:
            raise InstrumentError('unexpected or duplicate capacity rung')
        contexts.append(record['ctx'])
        tokens=record.get('prompt_tokens')
        if type(tokens) is not int or tokens<=0:
            raise InstrumentError('reported prompt_tokens must be a positive integer')
        if tokens<math.ceil(0.99*record['ctx']):
            raise InstrumentError('reported prompt is below registered 99% nominal-rung floor')
        if actual and tokens<=actual[-1]:
            raise InstrumentError('reported prompt counts do not increase monotonically')
        actual.append(tokens)
    facts={'actual_prompt_tokens':actual,'nominal_rungs':contexts,
           'minimum_prompt_fraction':0.99,'exact_full_occupancy_proven':False}
    target=next((r for r in records if r['ctx']==CAP),None)
    if target:
        return {**facts,'status':'complete','nominal_gate_262144':None,'within_rough_48gb':target['server_peak_gb']<=GATE_GB,'memory_policy':'descriptive guideline; no automatic rejection'}
    return {**facts,'status':'partial','nominal_gate_262144':None}


def parse_progress(line):
    match=re.fullmatch(r'\[capacity\] rung ctx=(\d+) server_peak_gb=(\S+) fits=(True|False) prefill_s=(\S+) error=(.*)',line.strip())
    if not match:
        return None
    ctx,peak,fits,prefill,error=match.groups()
    return {'ctx':int(ctx),'server_peak_gb':None if peak=='None' else float(peak),
            'fits':fits=='True','prefill_s':None if prefill=='None' else float(prefill),
            'error':None if error=='None' else error}


class Monitor:
    def __init__(self,path):
        self.path=Path(path)
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.rows=[]
        self.previous=0
        self.current_rung=None
        self.started=time.monotonic()
        self.rung_started=self.started
        self.last_line=None
        self.log_bytes=0
        self.error=None
        self.thread=None

    def log(self,event,**values):
        with self.lock,self.path.open('a') as f:
            f.write(json.dumps({'event':event,'unix_time':time.time(),**values},allow_nan=False)+'\n')

    def set_rung(self,ctx):
        with self.lock:
            self.current_rung=ctx
            self.rung_started=time.monotonic()

    def complete(self,row,wall):
        with self.lock:
            self.rows.append({**row,'wall_s':wall})

    def assess(self):
        with self.lock:
            n=len(self.rows)
            delta=n-self.previous
            self.previous=n
            ratios=[]
            for row in self.rows:
                actual=row.get('prefill_s')
                prior=PREFILL_REFERENCE_S.get(row.get('ctx'))
                valid=type(actual) in (int,float) and math.isfinite(actual) and actual>=0
                ratios.append({'ctx':row.get('ctx'),'actual_prefill_s':actual if valid else None,
                               'prior_prefill_s':prior,
                               'actual_vs_prior_ratio':actual/prior if valid and prior else None})
            elapsed=time.monotonic()-self.rung_started if self.current_rung else None
            reference=PREFILL_REFERENCE_S.get(self.current_rung)
            return {'rungs_completed':n,'rung_counter_delta':delta,'progressing':delta>0,
                    'current_rung':self.current_rung,'total_rungs':3,
                    'eta_s_mean':sum(r['wall_s'] for r in self.rows)/n*(3-n) if n else None,
                    'eta_note':'mean completed-rung wall time; lower bound at increasing context',
                    'elapsed_s':time.monotonic()-self.started,'driver_log_bytes':self.log_bytes,
                    'seconds_since_line':None if self.last_line is None else time.monotonic()-self.last_line,
                    'peaks':[r.get('server_peak_gb') for r in self.rows],
                    'errors':[r.get('error') for r in self.rows if r.get('error')],
                    'error':self.error,'convergence':'not a quality arm; bounded 256-token memory probe',
                    'request_fragment_progress':'unavailable in existing nonstreaming capacity CLI',
                    'prompt_attainment':'pending final records; live rung log omits prompt token counts',
                    'rate_vs_prediction':'observed elapsed and completed prefill relative to historical reference, not a guaranteed bound',
                    'prefill_reference_s':PREFILL_REFERENCE_S,'prefill_reference_source':PREFILL_REFERENCE_SOURCE,
                    'completed_prefill_ratios':ratios,'current_rung_elapsed_s':elapsed,
                    'current_rung_elapsed_vs_prior_prefill_ratio':elapsed/reference if elapsed is not None and reference else None,
                    'comparison_scope':'elapsed includes overhead/decode; first-pick historical prefill lower bound is a proxy for second model/unquantized KV, not a causal performance comparison',
                    'recommendation':'abort owned driver; request owner inspect still-resident worker' if self.error else
                      'continue bounded capacity instrument; inspect any missing peak or transport failure',
                    'correction_cost':'unavailable; no retry or serving change is authorized'}

    def selftest(self):
        probe=Monitor(self.path)
        probe.complete({'server_peak_gb':35},100)
        state=probe.assess()
        good=state['rung_counter_delta']==1 and state['eta_s_mean']==200 and probe.assess()['rung_counter_delta']==0
        self.log('SELFTEST',passed=good,known_positive_delta=1,known_idle_delta=0)
        return good

    def start(self):
        def background():
            while not self.stop.wait(300):
                self.log('ASSESSMENT',**self.assess())
        self.thread=threading.Thread(target=background,daemon=True,name='capacity-heartbeat')
        self.thread.start()

    def close(self,status,error=None):
        self.error=error
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        self.log('RUNNER-EXIT',status=status,**self.assess())


def source_evidence(stack):
    from bench import provenance
    evidence=provenance._git_shas()
    for relative,wanted in SOURCE_HEADS.items():
        for root in (stack/relative,HERE/Path(relative).name):
            actual=checked(['git','-C',str(root),'rev-parse','HEAD'])
            if actual!=wanted:
                raise InstrumentError('unapproved source HEAD: '+str(root))
            source='mlx_vlm' if relative.endswith('mlx-vlm') else 'src'
            dirty=checked(['git','-C',str(root),'status','--porcelain','--',source])
            if dirty:
                raise InstrumentError('serving source worktree is dirty: '+str(root))
            if provenance.serving_path_hash(str(root),actual)!=evidence['serving_path'].get(relative):
                raise InstrumentError('executed source and validation clone fingerprints differ')
    if not evidence.get('serving_path') or not all(evidence['serving_path'].values()):
        raise InstrumentError('serving source hashes unavailable')
    return evidence


def process_evidence(pid):
    import psutil
    try:
        proc=psutil.Process(pid)
        env=proc.environ()
        return {'pid':pid,'create_time':proc.create_time(),'command':proc.cmdline(),
                'environment':{key:env.get(key) for key in ENV_KEYS}}
    except (psutil.Error,OSError) as exc:
        raise InstrumentError('cannot inspect live process '+str(pid)) from exc


def read_launch_evidence(path,expected_sha):
    if sha(path)!=expected_sha:
        raise InstrumentError('selected immutable launch evidence changed')
    return json.loads(Path(path).read_text())


def validate_launch_record(record,model,overlay,overlay_sha):
    state=record.get('state') or {}
    if state.get('runtime')!='new' or state.get('model')!=model or state.get('overlay')!=str(overlay):
        raise InstrumentError('fresh launch evidence identifies a different runtime/model/overlay')
    if not isinstance(state.get('label'),str) or not state['label']:
        raise InstrumentError('fresh launch evidence requires its launch label')
    for process in (state,record.get('worker') or {}):
        if type(process.get('pid')) is not int or process['pid']<=0:
            raise InstrumentError('fresh launch evidence has invalid process PID')
    if record.get('overlay_sha256')!=overlay_sha:
        raise InstrumentError('fresh launch overlay hash differs')
    if record.get('source_shas')!={Path(k).name:v for k,v in SOURCE_HEADS.items()}:
        raise InstrumentError('fresh launch source SHAs differ from independent approved heads')
    for key in SOURCE_HEADS:
        value=record.get('serving_path',{}).get(key)
        if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
            raise InstrumentError('fresh launch serving hash missing or malformed')
    for package in ('mlx','mlx-metal'):
        if record.get('versions',{}).get(package)!='0.32.2':
            raise InstrumentError('fresh launch is not the approved NEW MLX runtime')


def collect_live(entry,overlay,stack,runtime,launch_path,launch_sha,owned_pid=None):
    import psutil
    launch=read_launch_evidence(launch_path,launch_sha)
    validate_launch_record(launch,entry['name'],overlay,sha(overlay))
    active=json.loads((HERE/'active-router.json').read_text())
    if active.get('pid')!=launch['state']['pid']:
        raise InstrumentError('active router PID differs from selected launch evidence')
    if active.get('runtime')!='new' or active.get('model')!=entry['name'] or active.get('overlay')!=str(overlay):
        raise InstrumentError('active router record does not match NEW arm')
    router=process_evidence(active['pid'])
    if not router['command'] or str(Path(router['command'][0]).parent)!=str(runtime/'bin'):
        raise InstrumentError('router is not using NEW runtime venv')
    validate_environment(router['environment'],overlay)
    listening=checked(['lsof','-nP','-a','-p',str(router['pid']),'-iTCP:8000','-sTCP:LISTEN','-Fp'])
    if 'p'+str(router['pid']) not in listening.splitlines():
        raise InstrumentError('recorded router PID does not own listening port 8000')
    workers=[]
    for proc in psutil.process_iter(['pid','cmdline']):
        command=proc.info.get('cmdline') or []
        if is_worker_command(command):workers.append(proc.pid)
        if proc.pid not in (os.getpid(),owned_pid) and any(c.startswith('bench.run_') for c in command):
            raise InstrumentError('another benchmark driver is active')
        if proc.pid!=os.getpid() and any(Path(c).name=='smoke.py' for c in command):
            raise InstrumentError('a smoke driver is still active')
    if len(workers)!=1:
        raise InstrumentError('exactly one resident model worker required')
    worker=process_evidence(workers[0])
    recorded_worker=launch['worker']
    if worker['pid']!=recorded_worker['pid'] or worker['command']!=recorded_worker.get('command'):
        raise InstrumentError('actual worker differs from selected launch evidence')
    for key,value in recorded_worker.get('environment',{}).items():
        if worker['environment'].get(key)!=value:
            raise InstrumentError('actual worker environment differs from selected launch evidence: '+key)
    validate_worker(worker,entry,overlay,runtime)
    for process in (worker,router):
        tmp=process['environment'].get('TMPDIR')
        if not tmp or not Path(tmp).resolve().is_relative_to(HERE):
            raise InstrumentError('live process temporary writes are not redirected locally')
    versions_code=("import importlib.metadata as m,importlib.util as u,json; print(json.dumps({"
                   "'versions':{k:m.version(k) for k in ['mlx','mlx-metal','mlx-vlm','mlx-serve','transformers','numpy']},"
                   "'origins':{k:u.find_spec(k).origin for k in ['mlx_vlm','mlx_serve']}}))")
    runtime_env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(HERE/'tmp'))
    for key in ('PYTHONPATH','PYTHONHOME'):
        value=worker['environment'].get(key)
        if value is None:runtime_env.pop(key,None)
        else:runtime_env[key]=value
    metadata=json.loads(checked([str(runtime/'bin/python'),'-c',versions_code],env=runtime_env))
    validate_origins(metadata['origins'],HERE)
    versions=metadata['versions']
    if versions.get('mlx')!='0.32.2' or versions.get('mlx-metal')!='0.32.2':
        raise InstrumentError('NEW MLX/Metal versions differ')
    source=source_evidence(stack)
    if source['serving_path']!=launch.get('serving_path'):
        raise InstrumentError('source hashes differ from verified NEW runtime launch')
    if any(launch.get('versions',{}).get(k)!=v for k,v in versions.items()):
        raise InstrumentError('runtime versions changed since verified NEW launch')
    return {'worker':worker,'router':router,'versions':versions,'package_origins':metadata['origins'],
            'source':source,'registry_sha256':sha(overlay),'launch_evidence_sha256':launch_sha,
            'supervisor_sources':{'capacity_runner':sha(Path(__file__)),'capacity_child':sha(INSTRUMENT_DIR/'capacity_child.py')}}


def assert_stable(before,after):
    if before!=after:
        raise InstrumentError('live runtime/source/overlay changed during capacity run')


def stop_child(child):
    if child is not None:
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        child.wait(timeout=15)


def supervise(command,env,stack,out,monitor,verify,popen=subprocess.Popen):
    events=queue.Queue()
    child=None
    start=time.monotonic()
    previous=start
    try:
        child=popen(command,cwd=str(stack/'benchmark'),env=env,stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,text=True,bufsize=1,start_new_session=True)
        write_json(out/'driver.json',{'pid':child.pid,'command':command,'env':{k:env.get(k) for k in
            ('PYTHONPATH','MLX_SERVE_CONFIG','HF_HUB_OFFLINE','TMPDIR','PYTHONDONTWRITEBYTECODE','APC_ENABLED')},
            'bound_s':CHILD_BOUND})
        actual=process_evidence(child.pid)
        # Environment is checked directly on the driver PID, not inferred from Popen input.
        import psutil
        actual_env=psutil.Process(child.pid).environ()
        for key in ('PYTHONPATH','MLX_SERVE_CONFIG','TMPDIR','PYTHONDONTWRITEBYTECODE'):
            if actual_env.get(key)!=env[key]:raise InstrumentError('driver environment mismatch: '+key)
        if 'APC_ENABLED' in actual_env:raise InstrumentError('driver inherited APC_ENABLED')
        write_json(out/'driver-live.json',actual)
        def reader():
            try:
                for line in child.stdout:events.put(line)
            finally:events.put(None)
        reader_thread=threading.Thread(target=reader,daemon=True,name='capacity-output')
        reader_thread.start()
        eof=False
        monitor.set_rung(GRID[0])
        with (out/'driver.log').open('w') as log:
            while not eof or child.poll() is None:
                if time.monotonic()-start>CHILD_BOUND:
                    raise InstrumentError('derived subprocess bound exceeded; worker may still be processing')
                try:line=events.get(timeout=.5)
                except queue.Empty:continue
                if line is None:
                    eof=True
                    continue
                log.write(line);log.flush()
                monitor.log_bytes+=len(line.encode())
                monitor.last_line=time.monotonic()
                record=parse_progress(line)
                if record:
                    index=len(monitor.rows)
                    if index>=len(GRID) or record['ctx']!=GRID[index]:
                        raise InstrumentError('capacity rung sequence differs')
                    validate_peak(record)
                    now=time.monotonic()
                    monitor.complete(record,now-previous);previous=now
                    verify(child.pid)
                    monitor.log('RUNG-COMPLETE',record=record,**monitor.assess())
                    monitor.set_rung(GRID[index+1] if index+1<len(GRID) else None)
            code=child.wait(timeout=15)
            if code:raise InstrumentError('capacity subprocess failed with exit '+str(code))
    finally:
        stop_child(child)
        if child and child.stdout:child.stdout.close()


def validate_output_paths(stack,out):
    here=HERE.resolve()
    resolved_stack=stack.resolve()
    if not resolved_stack.is_relative_to(here):
        raise InstrumentError('isolated stack root escapes private integration')
    if not (stack/'benchmark').resolve().is_relative_to(resolved_stack):
        raise InstrumentError('benchmark root escapes isolated stack')
    if not (stack/'benchmark/results').resolve().is_relative_to(resolved_stack):
        raise InstrumentError('results symlink escapes isolated stack')
    output_root=(HERE/'capacity').resolve()
    if not output_root.is_relative_to(here) or not out.resolve().is_relative_to(output_root):
        raise InstrumentError('supervisor output symlink escapes private integration')



def validate_c82_treatment(model,tag,overlay,entry):
    expected_model='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
    modes={'m42c82cap-native16-20260913':('native16',0,'turboquant','0ab8356af9c2db34fc865753cfe6be7f900e2de2612c13f3a3dcbb15e7237eee'),
           'm42c82cap-uniform8-20260913':('uniform8',8,'uniform','2b9ba892659ef6401a42d42c02e413bbcd33d4dc838533d8b5bbdfdd151f1fb0')}
    if model!=expected_model or tag not in modes:raise InstrumentError('unapproved C82 model/tag')
    mode,bits,scheme,digest=modes[tag]
    if Path(overlay)!=(INSTRUMENT_DIR/(mode+'.yaml')).resolve() or sha(overlay)!=digest:
        raise InstrumentError('C82 overlay path/hash differs')
    if entry.get('kv_bits')!=bits or entry.get('kv_quant_scheme')!=scheme or entry.get('kv_group_size',64)!=64:
        raise InstrumentError('C82 cache treatment differs')
    if any(os.environ.get(k) is not None for k in ('KV_KEY_BITS','KV_VALUE_BITS','KV_KEY_SCHEME','KV_VALUE_SCHEME')):
        raise InstrumentError('unapproved driver split KV overrides')
    if os.environ.get('KV_BITS')!=str(bits) or os.environ.get('KV_GROUP_SIZE') not in (None,'64'):
        raise InstrumentError('C82 explicit driver cache environment differs')

def load_plan(args):
    import yaml
    stack=HERE/'stack-validation'
    runtime=HERE/'runtime-venv'
    overlay=Path(args.overlay).resolve()
    launch_path=Path(args.launch_evidence).resolve()
    if not launch_path.is_relative_to(HERE) or not launch_path.is_file():
        raise InstrumentError('launch-evidence must be an existing private launch record')
    launch_sha=sha(launch_path)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',args.model):
        raise InstrumentError('model must be a registry name without path separators')
    if args.out_tag not in ('m42c82cap-native16-20260913','m42c82cap-uniform8-20260913'):
        raise InstrumentError('out-tag must be a fresh safe tag, not m41on')
    if not overlay.is_relative_to(HERE):raise InstrumentError('overlay must be private to this integration')
    doc=yaml.safe_load(overlay.read_text())
    entries=[e for e in doc.get('models',[]) if e.get('name')==args.model]
    if len(entries)!=1:raise InstrumentError('overlay must identify exactly one selected model')
    entry=entries[0]
    validate_c82_treatment(args.model,args.out_tag,overlay,entry)
    validate_launch_record(read_launch_evidence(launch_path,launch_sha),args.model,overlay,sha(overlay))
    if entry.get('max_kv_cache_size')!=CAP or entry.get('kv_prealloc_tokens')!=CAP or entry.get('draft_kind')!='mtp':
        raise InstrumentError('overlay must preserve full cap/full preallocation and shipped MTP')
    if not entry.get('generation_defaults',{}).get('enable_thinking'):
        raise InstrumentError('thinking must stay enabled')
    from bench import paths,run_capacity
    if paths.repo_root().resolve()!=stack.resolve() or Path(run_capacity.__file__).resolve()!=stack/'benchmark/bench/run_capacity.py':
        raise InstrumentError('PYTHONPATH must resolve capacity module from isolated stack-validation')
    if Path(os.environ.get('MLX_SERVE_CONFIG','')).resolve()!=overlay:
        raise InstrumentError('runner MLX_SERVE_CONFIG differs from overlay')
    if os.environ.get('APC_ENABLED') is not None:raise InstrumentError('runner APC_ENABLED must be absent')
    if Path(sys.prefix).name!='.venv-bench':raise InstrumentError('run with existing .venv-bench Python driver')
    results=stack/'benchmark/results'/args.model
    if not results.resolve().is_relative_to((stack/'benchmark/results').resolve()):
        raise InstrumentError('result path escapes isolated validation clone')
    files={name:results/(stem+'.'+args.out_tag+ext) for name,stem,ext in
           [('records','capacity_ladder','.jsonl'),('scorecard','capacity_retrieval','.json'),('manifest','capacity_ladder','.manifest.json')]}
    if any(p.exists() for p in files.values()):raise InstrumentError('refusing existing capacity outputs')
    out=HERE/'capacity'/args.out_tag/args.model
    validate_output_paths(stack,out)
    if out.exists() and any(out.iterdir()):raise InstrumentError('refusing existing supervisor output')
    env=dict(os.environ,PYTHONPATH=str(stack/'benchmark'),MLX_SERVE_CONFIG=str(overlay),
             PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TMPDIR=str(HERE/'tmp'),MLX_SERVE_BASE='http://localhost:8000')
    return {'entry':entry,'stack':stack,'runtime':runtime,'overlay':overlay,'files':files,'out':out,
            'env':env,'command':capacity_command(sys.executable,args.model,args.out_tag),
            'launch_path':launch_path,'launch_sha':launch_sha}


def execute(args):
    plan=load_plan(args)
    out=plan['out'];out.mkdir(parents=True,exist_ok=True)
    monitor=Monitor(out/'heartbeat.jsonl')
    status,error='instrument-error',None
    summary={'nominal_gate_262144':None}
    try:
        if not monitor.selftest():raise InstrumentError('monitor known-positive selftest failed')
        monitor.start()
        write_json(out/'plan.json',{'command':plan['command'],'results':{k:str(v) for k,v in plan['files'].items()},
            'request_timeout_s':REQUEST_TIMEOUT,'timeout_basis':'262K prefill precedent ~2200s plus >2x headroom',
            'subprocess_bound_s':CHILD_BOUND,'retries':0,'grid':list(GRID),
            'capacity_probe':{'max_tokens':256,'thinking_budget':256,'quality_arm':False},
            'calibration':{'count':1,'max_tokens':1,'temperature':0.0,'timeout_s':120},
            'seed':'inherited implicit server default 0; CLI has no seed option',
            'memory_policy':'48GB descriptive guideline, singleton measurement wrapper never stops for peak alone',
            'manifest_timing':'emitted at ladder end; live provenance rechecked after each rung, not a barrier before next rung',
            'router_lifecycle':'caller-owned; runner neither loads nor unloads or kills it',
            'calibration_guard':{'seam':'private capacity_child.MlxServeDriver delegate',
                                 'prompt_tokens':'positive integer, nonbool','chars_per_token_bounds':[0.5,16.0]},
            'nominal_prompt_floor':0.99,'exact_full_occupancy_proven':False,
            'prefill_reference_s':PREFILL_REFERENCE_S,'prefill_reference_source':PREFILL_REFERENCE_SOURCE,
            'launch_evidence':str(plan['launch_path']),'launch_evidence_sha256':plan['launch_sha'],
            'dry_run':args.dry_run})
        if args.dry_run:
            # Safe CPU-only module import/help verifies the real CLI without contacting a server.
            help_text=checked([sys.executable,'-m','bench.run_capacity','--help'],cwd=str(plan['stack']/'benchmark'),env=plan['env'])
            for flag in ('--grid','--sampling-profile','--out-tag','--request-timeout','--no-preload'):
                if flag not in help_text:raise InstrumentError('capacity CLI is missing '+flag)
            status='dry-run';return 0
        before=collect_live(plan['entry'],plan['overlay'],plan['stack'],plan['runtime'],plan['launch_path'],plan['launch_sha'])
        expected={'registry_sha256':before['registry_sha256'],'serving_path':before['source']['serving_path'],
                  'sampling':{**plan['entry']['generation_defaults'],'max_tokens':256,'thinking_budget':256}}
        write_json(out/'prelaunch-evidence.json',before)
        started=time.time()
        def verify(pid=None):
            after=collect_live(plan['entry'],plan['overlay'],plan['stack'],plan['runtime'],plan['launch_path'],plan['launch_sha'],owned_pid=pid)
            assert_stable(before,after)
        supervise(plan['command'],plan['env'],plan['stack'],out,monitor,verify)
        verify()
        for path in plan['files'].values():
            if not path.is_file() or path.stat().st_mtime<started-1:
                raise InstrumentError('missing/stale emitted capacity artifact: '+path.name)
        man=json.loads(plan['files']['manifest'].read_text())
        validate_manifest(man,expected)
        records=[json.loads(line) for line in plan['files']['records'].read_text().splitlines() if line]
        if [r['ctx'] for r in records]!=list(GRID[:len(records)]):
            raise InstrumentError('final capacity records do not form ordered grid prefix')
        if len(records)!=len(monitor.rows):raise InstrumentError('final records and live rung counter differ')
        for actual,observed in zip(records,monitor.rows):
            if actual.get('server_peak_gb')!=observed.get('server_peak_gb'):
                raise InstrumentError('final peak differs from live rung evidence')
        summary=classify_records(records)
        if summary['status']=='partial':raise InstrumentError('ladder stopped before completing the approved grid')
        summary['records']=records
        summary['raw_scorecard_threshold_flag_not_eligibility']=json.loads(plan['files']['scorecard'].read_text()).get('capacity_gate_pass')
        status=summary['status']
        write_json(out/'postrun-evidence.json',before)
        return 0
    except BaseException as exc:
        error=str(exc)
        status='instrument-error'
        summary['nominal_gate_262144']=None
        raise
    finally:
        write_json(out/'summary.json',{**summary,'status':status,'error':error,
                  'quality_recertification':False,'original_repository_outputs_written':False,
                  'cleanup':'owned driver only; caller-owned worker may still have an abandoned request on failure'})
        monitor.close(status,error)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('model','overlay','out-tag','launch-evidence'):parser.add_argument('--'+flag,required=True)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    validate_output_paths(HERE/'stack-validation',HERE/'capacity')
    HERE.joinpath('capacity').mkdir(exist_ok=True)
    with (HERE/'capacity/runner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def interrupted(signum,frame):raise InstrumentError('runner received signal '+str(signum))
        signal.signal(signal.SIGTERM,interrupted)
        signal.signal(signal.SIGINT,interrupted)
        try:return execute(args)
        except (InstrumentError,OSError,ValueError,LookupError,subprocess.SubprocessError) as exc:
            print('CAPACITY INSTRUMENT ERROR (no memory verdict): '+str(exc),flush=True)
            return 2


if __name__=='__main__':raise SystemExit(main())
