"""Authorized Go successor. PLAN is the queue of record; this is its executable snapshot."""
import os,sys,json,time,hashlib,subprocess,signal,statistics,copy,fcntl
from pathlib import Path
import yaml
import helpers as h
R=Path(os.environ['STACK_REPO']);Q=Path(os.environ['STACK_WORKDIR'])/'queue';D=Q/'resolution'
BASE='Qwen3.8-27B-mlx-uniform-4bit';MIXED='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
ORN='Ornith-1.0-35B-mlx-uniform-4bit';NEM='NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit'
log=h.log

def active(pid):
 p=subprocess.run(['ps','-o','command=','-p',str(pid)],capture_output=True,text=True)
 return p.stdout.strip()

def execute(cmd,tag,env=None):
 with (D/(tag+'.log')).open('a') as out:
  p=subprocess.Popen(cmd,cwd=R,env=env or os.environ,stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
  (D/(tag+'.pid')).write_text(str(p.pid));log(f'START {tag} pid={p.pid}')
  while p.poll() is None:
   try:p.wait(timeout=300)
   except subprocess.TimeoutExpired:log(f'WATCH {tag} alive; details in resolution/{tag}.log; per-item probe/bench assessment is authoritative')
  if p.returncode:raise RuntimeError(f'{tag} rc={p.returncode}; inspect its log')
 log('COMPLETE '+tag)

def overlay(tag,model,expand=None,draft=False):
 x=copy.deepcopy(registry)
 for m in x['models']:
  for key in list(m):
   if key.startswith('draft_') or key=='moe_expand':m.pop(key)
  if m['name']==model:
   if expand:m['moe_expand']=expand
   if draft:
    if model==MIXED:
     m.update(draft_kind='mtp',draft_model=str(Q/'mtp_recovery'/f'{MIXED}-mtp-normfix'))
    else:
     original=next(a for a in registry['models'] if a['name']==model)
     m.update({k:v for k,v in original.items() if k.startswith('draft_')})
     assert m.get('draft_kind')=='mtp'
 p=D/(tag+'.yaml');p.write_text(yaml.safe_dump(x,sort_keys=False));return str(p)

def arm(model,bench,tune,ids,pilot,ov,draft=False,k=1):
 h.ensure_router(ov)
 for phase,selected in [('pilot',pilot),('full',ids)]:
  tag=tune+'_'+bench+'_'+phase
  extra=['--limit',bench+'=0','--ids',bench+'='+':'.join(selected)]
  # Pilot mean/max are lower bounds; allow full-budget right tails, never shorten item timeouts.
  if h.run_generate(model,bench,tune,len(selected),tag,ov,expect_draft='mtp' if draft else 'off',extra=extra,samples=k,bound_h=72):raise RuntimeError(tag+' generation failed')
  s=h.summarize(model,bench,tune,len(selected)*k,tag)
  if s['n']!=len(selected)*k or s['errors']:raise RuntimeError(tag+' invalid rows')
  if phase=='pilot':log(f'PILOT SIZING {tag} mean_s={s["wall_mean_s"]} max_s={s["wall_max_s"]}; projected_lower_bound_s={s["wall_mean_s"]*len(ids)*k}; tails may exceed estimate')
 command=([h.PY,str(D/'native_grade.py'),model,bench,tune] if bench in ['humanevalplus','mbppplus'] else [h.PY,str(R/'benchmark/run.py'),'grade','--models',model,'--benches',bench,'--tune',tune])
 execute(command,tune+'_'+bench+'_grade',dict(os.environ,MLX_SERVE_CONFIG=ov))
 score=json.loads((R/'benchmark/results'/model/f'{bench}.{tune}.score.json').read_text())
 if score.get('acc') is None or score.get('errors'):raise RuntimeError(tune+' invalid grade')
 log('RESULT '+tune+' '+bench+' '+json.dumps({k:score.get(k) for k in ['n','acc','acc_strict','conv_rate','nonconv_kinds']}))
 log('REVIEW OWED: update README ranking/evidence tables; interpret quality, tokens, tails and B/C movement; no automatic promotion')

def main():
 global registry
 lock=(D/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 pid=int((Q/'go_medium.pid').read_text())
 log(f'SELFTEST successor armed; waiting for Go runner {pid}; no serving changes while active')
 while 'queue_go_medium.py' in active(pid):
  log('WATCH Go predecessor alive; '+(Q/'go_medium.log').read_text().splitlines()[-1]);time.sleep(300)
 if '=== MEDIUM GO DONE ===' not in (Q/'go_medium.log').read_text():raise RuntimeError('Go exited without completion; preserve router and inspect')
 for model in [BASE,MIXED]:
  rows=[json.loads(l) for l in (R/'benchmark/results'/model/'opencode_go.medium.jsonl').read_text().splitlines()]
  if len(rows)!=22:raise RuntimeError('Go row count does not match completion')
 if subprocess.run(['pgrep','-f','[r]un.py generate|[r]un_opencode'],capture_output=True,text=True).stdout.strip():raise RuntimeError('another generation driver is active')
 h.stop_router()
 if h.worker_cmdline():raise RuntimeError('worker survived shutdown; no second model allowed')
 freeze=json.loads((D/'carrier_before.json').read_text())
 for p,sha in freeze.items():
  if hashlib.sha256((R/p).read_bytes()).hexdigest()!=sha:raise RuntimeError('bench carrier changed unexpectedly: '+p)
  (R/p).write_bytes((Q/'c57_release'/p).read_bytes())
 registry=yaml.safe_load((R/'main_models.yaml').read_text())
 execute([h.PY,'-m','configgen','check'],'configgen')
 for name in ['positive','original','corrected']:
  job=D/name;model=BASE if name=='positive' else MIXED
  (job/'overlay.yaml').write_bytes(Path(overlay('probe_'+name,model)).read_bytes())
  execute([h.PY,str(job/'run.py')],'mtp_'+name,dict(os.environ,PYTHONPATH=str(R/'benchmark')))
  report=json.loads((job/'result.json').read_text());on=report['arms']['on']['rows']
  accepted=sum(r.get('draft_n_accepted',0) or 0 for r in on)
  log(f'MTP {name} accepted={accepted} gate={report["gate"]}')
  if name=='positive' and not accepted:raise RuntimeError('known-positive MTP control failed; do not interpret zero')
 audit_pid=int((D/'regrade.pid').read_text())
 while 'native_regrade_chain.py' in active(audit_pid):
  log('WATCH waiting for independent saved-output Rosetta audit');time.sleep(300)
 for tune in ['m34afnat','m34afexp']:
  if not (D/(tune+'_mbppplus_native_diff.json')).exists():raise RuntimeError('Rosetta audit incomplete; inspect before trusting quality scores')
 report=json.loads((D/'corrected/result.json').read_text())
 if (report.get('gate') or {}).get('ratio',0)>=1.3 and all(r.get('converged') for arm in report['arms'].values() for r in arm['rows']):
  for bench in ['humanevalplus','mbppplus']:
   ids=sets[bench]['ids'][:50];pilot=[i for i in sets[bench]['pilot'] if i in ids]
   import random
   pilot=random.Random(5911).sample(ids,5)
   for on in [False,True]:arm(MIXED,bench,'m36on' if on else 'm36off',ids,pilot,overlay('m36on' if on else 'm36off',MIXED,draft=on),on,k=3)
 else:log('M36 quality extension not started: speed/convergence screen failed; investigate, keep production OFF')
 h.stop_router()
 # Use serving dependencies plus pytest only from the bench environment; no model checkpoint loaded.
 site=next((R/'.venv-bench/lib').glob('python*/site-packages'))
 code=f"import sys;sys.path.append({str(site)!r});import mlx.core as mx;mx.set_cache_limit(0);mx.set_memory_limit(2000000000);import pytest;raise SystemExit(pytest.main([{str(R.parent/'mlx-vlm/mlx_vlm/tests/test_moe_expand.py')!r},'-q','-p','no:cacheprovider']))"
 execute([str(R/'.venv/bin/python'),'-c',code],'expansion_integration',dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(R.parent/'mlx-vlm')))
 for label,exp,on in [('naton',None,True),('natoff',None,False),('expoff','27-39:20:0.8:0.5',False),('expon','27-39:20:0.8:0.5',True)]:
  arm(ORN,'mbppplus','m34br'+label,sets['mbppplus']['ids'],sets['mbppplus']['pilot'],overlay('m34br'+label,ORN,exp,on),on)
 for bench in ['mbppplus','math500']:
  for label,exp in [('nat',None),('exp','36-51:15:0.8:0.5')]:
   arm(NEM,bench,'m34cr'+label,sets[bench]['ids'],sets[bench]['pilot'],overlay('m34cr'+label,NEM,exp))
 h.stop_router();log('=== RESOLUTION QUEUE DONE === results require human assessment and README update; no automatic promotion')

sets=json.loads((D/'ids.json').read_text())
if __name__=='__main__':
 try:main()
 except Exception as e:log('FATAL '+repr(e));raise
