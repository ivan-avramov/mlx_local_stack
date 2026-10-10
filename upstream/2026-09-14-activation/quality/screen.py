"""C84 private 80-request fresh before/after repair regression; root owns model lifecycle.

prepare freezes corpus bytes/current canonical builders; seal requires final
serving SHAs. run accepts a root-pinned launch artifact and frozen SHA, then
checks actual process/source/registry/manifests before every HTTP request.
Historical results are references, not a fresh old/new experiment.
"""
import argparse,copy,fcntl,hashlib,importlib,importlib.util,json,os,queue,re,signal,subprocess,sys,threading,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ACTIVATION=HERE.parent
STACK=Path('$STACK_REPO')
REGISTRY=STACK/'main_models.yaml'
OLD=ACTIVATION.parent/'2026-09-13/quality-pilot-c82'
MODELS={'native16':'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed','tq4':'Qwen3.8-27B-mlx-uniform-4bit'}
BENCHES=('math500','humanevalplus','mbppplus','cjudge')
SELECTION_SHA='5edcaf060e504c4eca1617a68a106a14e3f467d9510df75372dc25c64d7b94a6'
OLD_FROZEN_SHA='240ebeb38bea29867cb0a7a43427f387df434b0ce349959d7a2d405d7e84eaa8'
OLD_GRADE_SHA='7c4414e136003991fd4a5de8fc21775af09a2f5e17d40de0563db2eb8f177130'
MODULES=('benchmarks','generate','client','convergence','model_params','rowschema','paths','traces','depth','provenance','grade','stats','extract')
TIMEOUT=21080  # 102400 / floor 5 tok/s + 600s headroom; retries zero
COUNT=20
class ScreenError(RuntimeError):pass
def require(x,s):
 if not x:raise ScreenError(s)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jhash(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 p=Path(p);require(p.resolve().is_relative_to(HERE) and not p.is_symlink(),'private path escape')
 with p.open('x') as f:f.write(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def regular(p):
 p=Path(p);require(p.is_file() and not p.is_symlink(),'missing/symlinked input: '+str(p));return p

def canonical_modules(expected=None):
 hashes={}
 for name in MODULES:
  m=importlib.import_module('bench.'+name);p=STACK/'benchmark/bench'/f'{name}.py'
  require(Path(m.__file__).resolve()==p,'unexpected benchmark import: '+name);hashes[str(p)]=sha(p)
 hashes[str(STACK/'benchmark/run.py')]=sha(STACK/'benchmark/run.py')
 if expected is not None:require(hashes==expected,'canonical code changed')
 return hashes

def resolve_info(info):
 substitutions={'$STACK_REPO':str(STACK),'$STACK_WORKDIR':str(ACTIVATION.parents[1]),'$HOME':str(Path.home())}
 s=info['path']
 for k,v in substitutions.items():s=s.replace(k,v)
 p=regular(s);require('$' not in s and sha(p)==info['sha256'] and p.stat().st_size==info['bytes'],'selection input changed: '+s)
 return p

def corpus_items(axis,records):
 if axis=='math500':return [{'id':r['unique_id'],'prompt':r['problem'],'answer':r['answer']} for r in records]
 if axis=='cjudge':return [{'id':r['id'],'prompt':r['prompt'],'meta':{'source':r.get('source'),'source_id':r.get('source_id'),'category':r.get('category')},'source':r.get('source'),'category':r.get('category')} for r in records]
 return [{'id':r['task_id'],'prompt':r['prompt'],'meta':{'entry_point':r.get('entry_point')}} for r in records]

def requests_for(arm):
 from bench import benchmarks,generate,rowschema
 result=[]
 for i in range(5):
  for axis in BENCHES:
   item=arm['items'][axis][i];seed=rowschema.sample_seed(item['id'],0,base=0)
   payload={'model':arm['model'],'messages':generate._wrap_for_generation(axis,benchmarks.build_messages(axis,item),None,item['id']),'stream':False,**arm['params'],'seed':seed}
   result.append({'bench':axis,'id':item['id'],'seed':seed,'payload':payload,'wire':json.dumps(payload)})
 return result

def prepare():
 import yaml
 from bench import benchmarks,model_params,rowschema
 parent=regular(STACK/'docs/specs/c77-proposed-selection.json');require(sha(parent)==SELECTION_SHA,'C77 selection changed')
 s=read(parent);inventory={str(parent):sha(parent)}
 for info in s['source_rules']:
  p=resolve_info(info);inventory[str(p)]=sha(p)
 records={}
 for axis,info in s['corpora'].items():
  p=resolve_info(info);inventory[str(p)]=sha(p)
  if axis=='math500':
   import pyarrow.ipc as ipc
   with p.open('rb') as f:records[axis]=ipc.open_stream(f).read_all().to_pylist()
  else:records[axis]=[json.loads(x) for x in p.read_text().splitlines() if x]
  ids=[r[info['identity_key']] for r in records[axis]]
  require(len(ids)==len(set(ids))==info['unique_item_count'] and jhash(sorted(ids))==info['sorted_ids_sha256'],'corpus inventory differs')
  if 'provenance_file' in info:
   p=resolve_info(info['provenance_file']);inventory[str(p)]=sha(p)
 registry=yaml.safe_load(REGISTRY.read_text());arms={}
 for mode,model in MODELS.items():
  entries=[e for e in registry['models'] if e['name']==model];require(len(entries)==1,'ambiguous deployed model')
  entry=entries[0];params=model_params.params_for(model,profile='deployed',registry_path=str(REGISTRY))
  require(entry['kv_bits']==(0 if mode=='native16' else 4) and entry['kv_quant_scheme']=='turboquant','wrong deployed KV mode')
  require(all(entry.get(k)==v for k,v in {'draft_kind':'mtp','max_kv_cache_size':262144,'kv_prealloc_tokens':262144,'prefill_step_size':512,'quantized_kv_start':0}.items()),'deployed structural configuration differs')
  items={};timings={}
  for axis in BENCHES:
   g=next(g for g in s['groups'] if g['model']==model and g['axis']==axis)
   require(g['historical_configuration']['sampling']==params,'deployed sampling changed from selected historical profile')
   for info in g['sources'].values():
    p=resolve_info(info);inventory[str(p)]=sha(p)
   allitems=benchmarks._subsample(corpus_items(axis,records[axis]),None,0)
   items[axis]=[i for i in allitems if i['id'] in g['selected_ids']]
   require(len(items[axis])==5 and {i['id'] for i in items[axis]}==set(g['selected_ids']),'selected identities differ')
   raw={r[s['corpora'][axis]['identity_key']]:r for r in records[axis]}
   for meta in g['items']:
    r=raw[meta['id']];prompt=r['problem'] if axis=='math500' else r['prompt']
    require(jhash(r)==meta['corpus_record_sha256'] and hashlib.sha256(prompt.encode()).hexdigest()==meta['corpus_prompt_sha256'],'selected corpus record changed')
    require(meta['sample']==0 and meta['seed_base']==0 and meta['sampler_seed']==rowschema.sample_seed(meta['id'],0,base=0),'selected seed mismatch')
   timings[axis]={'historical_mean_s':g['timing']['mean_wall_s'],'historical_max_s':g['timing']['max_wall_s'],'five_request_reference_s':5*g['timing']['mean_wall_s']}
  tag='c84quality-'+mode+'-20260914'
  arm={'model':model,'mode':mode,'entry':entry,'params':params,'items':items,'tag':tag,'historical_timing':timings}
  arm['requests']=requests_for(arm);arm['results']={b:str(HERE/'results'/model/f'{b}.{tag}.jsonl') for b in BENCHES};arms[mode]=arm
 old=regular(OLD/'frozen.json');require(sha(old)==OLD_FROZEN_SHA,'C82 frozen reference changed');inventory[str(old)]=sha(old)
 ref={(r['bench'],r['id']):r for r in read(old)['requests']}
 overlap=[r for r in arms['native16']['requests'] if r['bench']!='cjudge']
 require(len(overlap)==15 and all(r==ref[(r['bench'],r['id'])] for r in overlap),'native16 C82 exact request comparison failed')
 return {'decision':'C84','kind':'fresh actual-stack before/after C85 repair regression','status':'PREPARED_UNARMED','request_count':80,'selection_sha256':SELECTION_SHA,'arms':arms,'corpus_ids':{b:sorted(r[s['corpora'][b]['identity_key']] for r in records[b]) for b in BENCHES},'input_hashes':inventory,'module_hashes':canonical_modules(),'registry_sha256':sha(REGISTRY),'runtime':runtime_state(),'native16_c82_payloads_identical':15,'historical_generation_reference_s':s['timing']['generation_only_lower_bound_s'],'limits':['Not the C77 fresh old/new80 experiment.','Historical comparisons are noncausal references; five items per axis do not certify ±5pp.','Prose requires human/source review; hashes are integrity only.','No numeric memory cutoff, no retries, no API judges.']}

def runtime_state():
 import importlib.metadata
 sites=list((STACK/'.venv/lib').glob('python*/site-packages'));require(len(sites)==1,'ambiguous serving package path')
 distributions=list(importlib.metadata.distributions(path=[str(sites[0])]))
 versions={d.metadata['Name'].lower().replace('_','-'):d.version for d in distributions}
 require(versions.get('mlx')=='0.32.2' and versions.get('mlx-metal')=='0.32.2','installed serving MLX changed')
 editables={}
 for d in distributions:
  name=d.metadata['Name'].lower().replace('_','-')
  if name in ('mlx-vlm','mlx-serve'):
   info=json.loads(d.read_text('direct_url.json') or '{}')
   from urllib.parse import unquote,urlparse
   require(info.get('dir_info',{}).get('editable') is True and Path(unquote(urlparse(info['url']).path)).resolve()==(STACK/'src'/name).resolve(),'serving editable import path differs: '+name)
   editables[name]=info
 require(set(editables)=={'mlx-vlm','mlx-serve'},'serving editable metadata missing')
 return {'versions':versions,'editables':editables}

def source_state():
 from bench import provenance
 d=provenance._git_shas()
 for name in ('mlx-vlm','mlx-serve'):
  dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=STACK/'src'/name,text=True)
  require(not dirty.strip(),'serving source worktree dirty: '+name)
 return {k:d[k] for k in ('submodules','serving_path')}

def verify(f,check_source=True):
 require(f['decision']=='C84' and f['request_count']==80,'scope changed')
 for mapping in ('input_hashes','module_hashes','instrument_hashes'):
  for p,h in f[mapping].items():require(sha(regular(p))==h,'frozen file changed: '+p)
 require(sha(REGISTRY)==f['registry_sha256'],'actual registry changed')
 require(runtime_state()==f['runtime'],'serving runtime packages/import roots changed')
 canonical_modules(f['module_hashes'])
 if check_source:require(source_state()==f['source'],'source differs from final frozen pin')
 for arm in f['arms'].values():require(requests_for(arm)==arm['requests'],'canonical requests changed')

def frozen(pin,phase):
 require(re.fullmatch('[0-9a-f]{64}',pin) and sha(HERE/f'frozen-{phase}.json')==pin,'frozen SHA differs')
 f=read(HERE/f'frozen-{phase}.json');require(f['phase']==phase,'phase pin differs');verify(f);return f

def phase_plan(prepared,phase,source,before=None):
 require(phase in ('before','after'),'invalid phase')
 f=copy.deepcopy(prepared);f['source']=source;f['phase']=phase;f['request_count']=80;f['phase_requests']=40
 if phase=='after':
  require(before is not None and before.get('phase')=='before','fresh baseline freeze required')
  require(source['submodules']['src/mlx-serve']==before['source']['submodules']['src/mlx-serve'] and source['submodules']['src/mlx-vlm']!=before['source']['submodules']['src/mlx-vlm'],'only repaired VLM source must change')
  for mode in MODELS:
   for key in ('model','requests','items','params','entry'):
    require(f['arms'][mode].get(key)==before['arms'][mode].get(key),'before/after treatment drift: '+key)
  require(f.get('registry_sha256')==before.get('registry_sha256') and f.get('module_hashes')==before.get('module_hashes') and f.get('runtime')==before.get('runtime'),'registry/canonical builders changed across phases')
 for mode,arm in f['arms'].items():
  arm['tag']=f'c84repair-{phase}-{mode}-20260914'
  arm['results']={b:str(HERE/'results'/phase/arm['model']/f"{b}.{arm['tag']}.jsonl") for b in BENCHES}
 return f

def seal(phase,vlm,serve):
 prepared=read(HERE/'prepared.json');require(all(re.fullmatch('[0-9a-f]{40}',x) for x in (vlm,serve)),'full final SHAs required')
 source=source_state();require(source['submodules']=={'src/mlx-vlm':vlm,'src/mlx-serve':serve},'requested source SHAs not installed')
 before=read(HERE/'frozen-before.json') if phase=='after' else None
 if phase=='after':
  for mode in MODELS:
   summary=read(HERE/'runs'/'before'/mode/'summary.json')
   require(summary.get('status')=='complete' and summary.get('completed')==COUNT and summary.get('frozen_sha256')==sha(HERE/'frozen-before.json'),'fresh before baseline incomplete')
 f=phase_plan(prepared,phase,source,before)
 if before is not None:f['input_hashes'][str(HERE/'frozen-before.json')]=sha(HERE/'frozen-before.json')
 f['instrument_hashes']={str(HERE/n):sha(HERE/n) for n in ('screen.py','child.py','grade_screen.py')}
 f['instrument_hashes'][str(OLD/'grade_pilot.py')]=OLD_GRADE_SHA
 f['status']='FROZEN_READY_FOR_ROOT_LAUNCH';verify(f);save(HERE/f'frozen-{phase}.json',f);return sha(HERE/f'frozen-{phase}.json')

def cli_flags(command):
 allowed={'--model','--host','--port','--max-kv-size','--kv-prealloc-tokens','--kv-quant-scheme','--prefill-step-size','--generation-defaults','--draft-kind','--draft-model','--quantized-kv-start','--memory-limit-frac','--kv-bits','--kv-group-size'}
 args=command[2:];require(len(args)%2==0,'worker flag arity changed');out={}
 for k,v in zip(args[::2],args[1::2]):
  require(k in allowed and k not in out and not v.startswith('--'),'unexpected/duplicate/abbreviated worker option: '+k);out[k]=v
 return out

def validate_process(arm,cmd,env):
 require(cmd[:2]==[str(STACK/'.venv/bin/python3'),str(STACK/'.venv/bin/mlx_vlm.server')],'unexpected worker executable')
 flags=cli_flags(cmd);e=arm['entry']
 want={'--model':e['hf_path'],'--host':'127.0.0.1','--port':'8091','--max-kv-size':'262144','--kv-prealloc-tokens':'262144','--kv-quant-scheme':'turboquant','--prefill-step-size':'512','--draft-kind':'mtp','--draft-model':e['draft_model'],'--quantized-kv-start':'0','--memory-limit-frac':'0.85'}
 require(all(flags.get(k)==v for k,v in want.items()),'worker structural flags differ')
 require(json.loads(flags['--generation-defaults'])==arm['params'],'worker defaults differ')
 require(flags.get('--kv-bits')==(None if arm['mode']=='native16' else '4'),'worker KV precision differs')
 require(flags.get('--kv-group-size') in (None,'64'),'worker group differs')
 require(env.get('MLX_SERVE_CONFIG')==str(REGISTRY) and env.get('MLX_VLM_CACHE_SESSION_MAX')=='2' and 'APC_ENABLED' not in env,'worker env contract differs')
 require(not env.get('PYTHONPATH') and not env.get('PYTHONHOME'),'worker Python import override')
 require(not any(k.startswith('KV_') for k in env),'inherited KV override')
 for k in ('MLX_VLM_SESSION_SHRINK_ON_RETIRE','MLX_VLM_SESSION_EVICT_HEADROOM_FRAC','MLX_VLM_CACHE_ANON_SESSIONS','MLX_VLM_DELTANET_RING_SIZE','MLX_VLM_DELTANET_REWIND','MLX_EPICACHE_BUDGET','MLX_METAL_GPU_ARCH'):
  require(k not in env,'unapproved cache/runtime override: '+k)

def validate_listener(port,pid,run=subprocess.run):
 result=run(['lsof','-nP','-t',f'-iTCP:{port}','-sTCP:LISTEN'],capture_output=True,text=True,timeout=15)
 require(result.returncode==0 and set(result.stdout.split())=={str(pid)},f'HTTP listener {port} does not belong exclusively to recorded PID')

def require_run_output(out):
 out=Path(out)
 require(out.resolve().is_relative_to(HERE/'runs') and not out.exists() and not out.is_symlink(),'existing/escaped output directory')

def live(f,arm,launch,pin,initial=None):
 import psutil
 require(sha(regular(launch))==pin,'launch evidence changed');e=read(launch)
 require(e['source_shas']=={k.split('/')[-1]:v for k,v in f['source']['submodules'].items()} and e['serving_path']==f['source']['serving_path'],'launch source differs')
 require(e['overlay_sha256']==f['registry_sha256'] and e['state']['overlay']==str(REGISTRY) and e['state']['model']==arm['model'],'launch model/registry differs')
 require(all(f['runtime']['versions'].get(k.lower().replace('_','-'))==v for k,v in e['versions'].items()),'launch runtime versions differ')
 w=psutil.Process(e['worker']['pid']);router=psutil.Process(e['state']['pid']);validate_process(arm,w.cmdline(),w.environ())
 validate_listener(8000,router.pid);validate_listener(8091,w.pid)
 require(str(STACK/'.venv/bin/mlx-serve') in router.cmdline(),'router executable differs')
 require(w.cmdline()==e['worker']['command'],'worker command differs from launch')
 re_=router.environ();require(re_.get('MLX_SERVE_CONFIG')==str(REGISTRY) and re_.get('MLX_VLM_CACHE_SESSION_MAX')=='2' and 'APC_ENABLED' not in re_,'router provenance differs')
 workers=[p.pid for p in psutil.process_iter(['cmdline']) if any(x.endswith('/mlx_vlm.server') or x=='mlx_vlm.server' for x in p.info['cmdline'] or [])]
 require(workers==[w.pid],'must have exactly the root-owned worker')
 state={'worker_pid':w.pid,'worker_created':w.create_time(),'router_pid':router.pid,'router_created':router.create_time(),'worker_command':w.cmdline(),'cache_env':{k:v for k,v in w.environ().items() if k.startswith(('KV_','MLX_VLM_'))}}
 if initial is not None:require(state==initial,'worker/router identity or config changed')
 verify(f);return state

def validate_manifest(m,arm,f):
 require(m.get('model')==arm['model'] and m.get('tune')==arm['tag'] and m.get('sampling_profile')=='deployed' and m.get('sampling')==arm['params'],'manifest identity/tune/profile differs')
 require(m.get('registry',{}).get('sha256')==f['registry_sha256'],'manifest registry differs')
 require(all(m.get('git',{}).get(k)==v for k,v in f['source'].items()),'manifest serving provenance differs')
 require(m.get('runtime',{}).get('draft_kind')=='mtp' and m.get('runtime',{}).get('probe_timeout_s')==TIMEOUT,'manifest predictor/timeout differs')
 for k in ('kv_bits','kv_quant_scheme','quantized_kv_start','max_kv_cache_size','kv_prealloc_tokens','prefill_step_size'):
  require(m.get('kv',{}).get(k)==arm['entry'].get(k),'manifest KV differs: '+k)

def canonical_args(a):
 return ['generate','--models',a['model'],'--benches',','.join(BENCHES),'--limit',','.join(b+'=5' for b in BENCHES),'--ids',','.join(b+'='+':'.join(i['id'] for i in a['items'][b]) for b in BENCHES),'--sampling-profile','deployed','--samples','1','--seed-base','0','--seed','0','--order','roundrobin','--chunks','all','--tune',a['tag'],'--probe-timeout',str(TIMEOUT)]


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
                    'eta_s_mean':sum(times)/n*(20-n) if n else None,'eta_note':'completed-item mean estimate, not a guaranteed bound; allow right tails',
                    'tokens':[r['completion_tokens'] for r in self.rows],'convergence':[r['converged'] for r in self.rows],
                    'nonconv_kinds':[r.get('nonconv_kind') for r in self.rows if not r['converged']],
                    'elapsed_s':time.monotonic()-self.started,'fragment_progress':'unavailable: canonical nonstreaming client',
                    'recommendation':'continue approved bounded arm when provenance is valid; retain nonconvergence, no memory threshold stop'}
    def selftest(self):
        fake=Monitor(self.path);fake.complete({'wall_s':2,'completion_tokens':1,'converged':True});a=fake.assess();ok=a['counter_delta']==1 and a['eta_s_mean']==38 and fake.assess()['counter_delta']==0
        self.log('SELFTEST',passed=ok);return ok
    def start(self):
        def loop():
            while not self.stop.wait(300):self.log('ASSESSMENT',**self.assess())
        self.thread=threading.Thread(target=loop,daemon=True);self.thread.start()
    def close(self,status,error=None):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        self.log('RUNNER-EXIT',status=status,error=error,**self.assess())


def manifest_check(arm,f):
 for p in arm['results'].values():validate_manifest(read(regular(Path(p).with_suffix('.manifest.json'))),arm,f)

def execute(phase,mode,pin,launch,launch_pin):
 f=frozen(pin,phase);arm=f['arms'][mode];out=HERE/'runs'/phase/mode
 require_run_output(out)
 for p in arm['results'].values():
  p=Path(p);require(p.resolve().is_relative_to(HERE/'results'),'result path escapes private root')
  require(not p.exists() and not p.with_suffix('.manifest.json').exists(),'prior canonical rows/manifests exist')
 require(os.environ.get('MLX_SERVE_CONFIG')==str(REGISTRY) and os.environ.get('PYTHONPATH')==str(STACK/'benchmark'),'supervisor registry/import environment differs')
 require('APC_ENABLED' not in os.environ,'supervisor inherited APC')
 initial=live(f,arm,launch,launch_pin);out.mkdir(parents=True)
 save(out/'prelaunch.json',{'live':initial,'launch':str(Path(launch).resolve()),'launch_sha256':launch_pin,'frozen_sha256':pin})
 monitor=Monitor(out/'heartbeat.jsonl');proc=None;completed=0;terminal=False;status='instrument-error';error=None
 env=dict(os.environ,MLX_BENCH_RESULTS=str(HERE/'results'/phase),MLX_SERVE_CONFIG=str(REGISTRY),PYTHONPATH=str(STACK/'benchmark'),MLX_SERVE_BASE='http://localhost:8000',TMPDIR=str(HERE/'tmp'),PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1')
 started=time.monotonic()
 try:
  require(monitor.selftest(),'monitor known-positive failed');monitor.start()
  proc=subprocess.Popen([sys.executable,'-B',str(HERE/'child.py'),'--mode',mode,'--phase',phase,'--frozen-sha',pin,'--out',str(out)],cwd=STACK,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,start_new_session=True)
  import psutil
  observed=psutil.Process(proc.pid).environ()
  for k in ('MLX_BENCH_RESULTS','MLX_SERVE_CONFIG','PYTHONPATH','MLX_SERVE_BASE','TMPDIR','PYTHONDONTWRITEBYTECODE'):require(observed.get(k)==env[k],'actual child env differs: '+k)
  save(out/'driver.json',{'pid':proc.pid,'created':psutil.Process(proc.pid).create_time(),'command':proc.args,'environment':{k:observed[k] for k in ('MLX_BENCH_RESULTS','MLX_SERVE_CONFIG','PYTHONPATH','TMPDIR')},'bound_s':COUNT*TIMEOUT+1200})
  lines=queue.Queue()
  def pump():
   try:
    for line in proc.stdout:lines.put(line)
   finally:lines.put(None)
  threading.Thread(target=pump,daemon=True).start();eof=False
  with (out/'child.log').open('x') as log:
   while not eof or proc.poll() is None:
    require(time.monotonic()-started<COUNT*TIMEOUT+1200,'derived lifetime bound exceeded')
    try:line=lines.get(timeout=.5)
    except queue.Empty:continue
    if line is None:eof=True;continue
    log.write(line);log.flush()
    if not line.startswith('C84_EVENT '):continue
    e=json.loads(line[len('C84_EVENT '):]);kind=e['event']
    if kind=='BEFORE_REQUEST':
     require(type(e.get('index')) is int and e['index']==completed and completed<COUNT,'unexpected request sequence')
     want=arm['requests'][completed];require((e['bench'],e['id'])==(want['bench'],want['id']),'unexpected request identity')
     require(sha(HERE/f'frozen-{phase}.json')==pin,'frozen plan changed');live(f,arm,launch,launch_pin,initial);manifest_check(arm,f)
     monitor.current={'index':completed,'bench':e['bench'],'id':e['id']};proc.stdin.write(json.dumps({'ack':completed})+'\n');proc.stdin.flush()
    elif kind=='ITEM':
     require(completed<COUNT and e['completed']==completed+1,'unexpected row sequence');r=e['row'];want=arm['requests'][completed]
     require((r['bench'],r['id'],r['sampler_seed'])==(want['bench'],want['id'],want['seed']),'row identity drift')
     completed+=1;monitor.complete(r);monitor.log('ITEM',completed=completed,row=r)
    elif kind=='COMPLETE':
     require(not terminal and e['attempted']==e['completed']==completed==COUNT,'bad terminal count');terminal=True
    else:raise ScreenError('child infrastructure failure: '+str(e))
  require(proc.wait(timeout=15)==0 and terminal,'child failed/incomplete');live(f,arm,launch,launch_pin,initial);manifest_check(arm,f);status='complete'
 except BaseException as exc:error=str(exc);raise
 finally:
  if proc is not None:
   try:os.killpg(proc.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   proc.wait(timeout=15)
  save(out/'summary.json',{'status':status,'error':error,'phase':phase,'mode':mode,'model':arm['model'],'completed':completed,'maximum':COUNT,'frozen_sha256':pin,'rows':monitor.rows,'graded':False})
  monitor.close(status,error)

def finalize(phase,mode,pin):
 f=frozen(pin,phase);arm=f['arms'][mode];out=HERE/'runs'/phase/mode;s=read(regular(out/'summary.json'))
 require(s.get('status')=='complete' and s.get('completed')==COUNT and s.get('frozen_sha256')==pin,'run not completed')
 manifest_check(arm,f);files={};rows={}
 for axis,p in arm['results'].items():
  p=regular(p);rs=[json.loads(x) for x in p.read_text().splitlines() if x];want={r['id']:r['seed'] for r in arm['requests'] if r['bench']==axis}
  require(len(rs)==5 and {r['id'] for r in rs}==set(want),'canonical identities incomplete')
  for r in rs:
   require(r.get('model')==arm['model'] and r.get('bench')==axis and r.get('sample')==0 and r.get('sampler_seed')==want[r['id']] and not r.get('error'),'invalid canonical row')
   rows[(axis,r['id'])]=r
  for path in (p,p.with_suffix('.manifest.json')):files[str(path)]=sha(regular(path))
 import child
 for i,e in enumerate(arm['requests'],1):
  d=out/f'request-{i:02d}';p=regular(d/'request.json');require(p.read_text()==e['wire'],'actual request differs')
  raw=read(regular(d/'response.json'));child.response_check(raw);r=rows[(e['bench'],e['id'])]
  require(read(regular(d/'row.json'))==r,'saved/canonical row differs')
  require(r['completion_tokens']==raw['usage']['completion_tokens'] and r['prompt_tokens']==raw['usage']['prompt_tokens'],'raw token usage differs')
  require(r['content_sha256']==hashlib.sha256((raw['choices'][0]['message'].get('content') or '').encode()).hexdigest(),'raw answer differs')
  for path in (p,d/'response.json',d/'row.json'):files[str(path)]=sha(regular(path))
 evidence={'schema_version':1,'decision':'C84','status':'complete','phase':phase,'mode':mode,'model':arm['model'],'tag':arm['tag'],'frozen_sha256':pin,'source':f['source'],'registry_sha256':f['registry_sha256'],'completed':COUNT,'files':files,'review_note':'Root must review and SHA-pin this artifact before grading; no quality verdict or certification implied.'}
 target=HERE/f'finalized-{phase}-{mode}.json';save(target,evidence);return sha(target)

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True);sub.add_parser('prepare')
 s=sub.add_parser('seal');s.add_argument('--phase',choices=['before','after'],required=True);s.add_argument('--vlm-sha',required=True);s.add_argument('--serve-sha',required=True)
 for name in ('run','finalize'):
  a=sub.add_parser(name);a.add_argument('--phase',choices=['before','after'],required=True);a.add_argument('--mode',choices=MODELS,required=True);a.add_argument('--frozen-sha',required=True)
  if name=='run':a.add_argument('--launch-evidence',required=True);a.add_argument('--launch-evidence-sha256',required=True)
 a=p.parse_args()
 if a.action=='prepare':save(HERE/'prepared.json',prepare());print(sha(HERE/'prepared.json'));return
 if a.action=='seal':print(seal(a.phase,a.vlm_sha,a.serve_sha));return
 if a.action=='finalize':print(finalize(a.phase,a.mode,a.frozen_sha));return
 with (HERE/'screen.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  def interrupted(signum,frame):raise ScreenError('supervisor interrupted')
  signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
  execute(a.phase,a.mode,a.frozen_sha,a.launch_evidence,a.launch_evidence_sha256)

if __name__=='__main__':main()
