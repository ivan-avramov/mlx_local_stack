import os,sys,json,time,subprocess,fcntl
from pathlib import Path
import yaml
import helpers as h
R=Path(os.environ['STACK_REPO']);Q=Path(os.environ['STACK_WORKDIR'])/'queue';D=Q/'m39_vision_gate'
MODELS=['Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed','Qwen3.8-27B-mlx-uniform-4bit','Ornith-1.0-35B-mlx-uniform-4bit','Qwen3.6-27B-Opus-Distill-OptiQ-4bit']
EXPECT_TEMP={'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed':0.5,'Qwen3.8-27B-mlx-uniform-4bit':0.6,'Ornith-1.0-35B-mlx-uniform-4bit':0.4,'Qwen3.6-27B-Opus-Distill-OptiQ-4bit':0.3}
EXPECT_EFFORT={'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed':'medium','Qwen3.8-27B-mlx-uniform-4bit':'medium'}
NATIVE_ROUTING={'Ornith-1.0-35B-mlx-uniform-4bit'}  # operator ruling 2026-09-11 (C67): Ornith enters the C contest at native routing, draft-OFF
ROUTER_LOG=R/'logs/main_model.log'
VISION_GATE_BOUND_H=6  # 20 items x 2 short turns; generous vs the multi-hour full-benchmark legs this chain replaces
def fresh_overlay(model):
 """Fresh draft-OFF overlay from the CURRENT worktree registry (re-read every model, not once at
 the top of the chain -- mirrors M38/M39-visionqa's fresh_overlay: the registry is the record and
 may be edited by the operator across the days this chain runs). The native-routing check must
 run on the ORIGINAL entry BEFORE the draft_*/moe_expand strip below, else it is vacuous (everything
 has had those keys popped by the time it runs)."""
 data=yaml.safe_load((R/'main_models.yaml').read_text())
 orig_entry=next(x for x in data['models'] if x['name']==model)
 if model in NATIVE_ROUTING:assert 'moe_expand' not in orig_entry,'native-routing model '+model+' unexpectedly carries moe_expand in the registry'
 for entry in data['models']:
  for key in list(entry):
   if key.startswith('draft_') or key=='moe_expand':entry.pop(key)
 entry=next(x for x in data['models'] if x['name']==model)
 gd=entry['generation_defaults']
 assert gd['enable_thinking'] is True
 assert gd['thinking_budget']==81920
 assert entry['kv_prealloc_tokens']==entry['max_kv_cache_size']==262144
 assert gd['temperature']==EXPECT_TEMP[model]
 if model in EXPECT_EFFORT:assert gd['reasoning_effort']==EXPECT_EFFORT[model]
 overlay=D/'native.yaml';overlay.write_text(yaml.safe_dump(data,sort_keys=False))
 return overlay
def probe_gate(model):
 """Known-positive gate: a one-image SEES/BLIND probe right after the router is up for this
 model, before any vision_gate.py spend. `probe_vision.py` prints a JSON object with a `verdict`
 field (SEES/BLIND/UNREACHABLE) and exits 0 only on SEES."""
 pr=subprocess.run([h.PY,str(R/'benchmark/probe_vision.py'),'--model',model],cwd=R,capture_output=True,text=True)
 h.log('PROBE '+model+': rc='+str(pr.returncode)+' stdout='+pr.stdout.strip().replace('\n',' ')+(' stderr='+pr.stderr.strip().replace('\n',' ') if pr.stderr.strip() else ''))
 try:verdict=json.loads(pr.stdout).get('verdict')
 except Exception:verdict=None
 if verdict!='SEES':raise RuntimeError('probe_vision verdict='+str(verdict)+' (expected SEES) for '+model+' -- BLIND, aborting this leg')
def run_vision_gate(model,overlay):
 """`benchmark/vision_gate.py --model <m> --resume`, driver env carries MLX_SERVE_CONFIG so the
 model's `deployed` sampling profile and `registry_context_limit` read the SAME overlay the
 router is actually serving (C35). --resume makes a re-run of this leg (e.g. after a transport
 error) pick up only the ids that never finished, rather than refusing a non-empty --out."""
 env=dict(os.environ);env.pop('APC_ENABLED',None);env['MLX_SERVE_CONFIG']=str(overlay)
 cmd=[h.PY,str(R/'benchmark/vision_gate.py'),'--model',model,'--resume']
 h.log('RUN vision_gate '+model+': '+' '.join(cmd))
 with (D/(model+'_vision_gate.log')).open('a') as out:
  p=subprocess.run(cmd,cwd=R,env=env,stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,timeout=VISION_GATE_BOUND_H*3600)
 h.log('END vision_gate '+model+' rc='+str(p.returncode))
 return p.returncode
def main():
 lock=(D/'queue.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 (D/'queue.pid').write_text(str(os.getpid()))
 h.log('SELFTEST M39 vision-gate chain armed; no predecessor -- box asserted idle at start, not waited-for')
 p=subprocess.run(['pgrep','-f','[r]un.py generate|[v]ision_gate.py|[m]lx_vlm.server'],capture_output=True,text=True)
 if p.stderr.strip() or p.stdout.strip() or h.listeners():raise RuntimeError('Expected idle driver/worker/router at M39-vision-gate start (no predecessor to wait for) -- pgrep_stdout='+repr(p.stdout.strip())+' listeners='+repr(h.listeners()))
 for model in MODELS:
  try:
   overlay=fresh_overlay(model)
   h.ensure_router(str(overlay))
   probe_gate(model)
   rc=run_vision_gate(model,overlay)
   if rc:raise RuntimeError('vision_gate.py exited rc='+str(rc)+' for '+model+' -- a transport/other failure ESCALATED (never graded), per AGENTS.md')
   summary_path=R/'benchmark/results'/model/'vision_gate.v1.summary.json'
   summary=json.loads(summary_path.read_text())
   if summary.get('n')!=20:raise RuntimeError('vision_gate summary n='+str(summary.get('n'))+' (expected 20) for '+model)
   h.log('RESULT '+model+': '+str(summary['pass'])+'/'+str(summary['n'])+' pass, fail='+str(summary['fail'])+' null='+str(summary['null'])+' pass_rate='+str(summary['pass_rate']))
   if summary.get('fail_or_null_ids'):h.log('RESULT '+model+' fail_or_null_ids='+json.dumps(summary['fail_or_null_ids']))
  except Exception as e:
   import traceback
   h.log('ERROR leg for '+model+': '+repr(e)+'\n'+traceback.format_exc())
   h.stop_router()
   if h.listeners():raise RuntimeError('router still listening on :8000 after error cleanup for '+model)
   continue
  h.unload();h.stop_router()
  if h.listeners():raise RuntimeError('router still listening on :8000 after stop for '+model)
 h.log('=== M39 VISION GATE QUEUE DONE ===')
if __name__=='__main__':
 try:main()
 except Exception as e:h.log('FATAL '+repr(e));raise
