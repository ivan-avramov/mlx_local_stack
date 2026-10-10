import os,sys,json,time,subprocess,fcntl,re,statistics
from pathlib import Path
import yaml
import helpers as h
R=Path(os.environ['STACK_REPO']);Q=Path(os.environ['STACK_WORKDIR'])/'queue';D=Q/'m39_visionqa'
BENCH='visionqa';TUNE='m39';TXT_TUNE='m39txt';FULL_N=40;PILOT_N=5
MODELS=['Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed','Qwen3.8-27B-mlx-uniform-4bit','Ornith-1.0-35B-mlx-uniform-4bit','Qwen3.6-27B-Opus-Distill-OptiQ-4bit']
EXPECT_TEMP={'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed':0.5,'Qwen3.8-27B-mlx-uniform-4bit':0.6,'Ornith-1.0-35B-mlx-uniform-4bit':0.4,'Qwen3.6-27B-Opus-Distill-OptiQ-4bit':0.3}
EXPECT_EFFORT={'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed':'medium','Qwen3.8-27B-mlx-uniform-4bit':'medium'}
NATIVE_ROUTING={'Ornith-1.0-35B-mlx-uniform-4bit'}  # operator ruling 2026-09-11 (C67): Ornith enters the C contest at native routing, draft-OFF
ROUTER_LOG=R/'logs/main_model.log'
def fresh_overlay(model):
 """Fresh draft-OFF overlay from the CURRENT worktree registry (re-read every model, not once at
 the top of the chain -- mirrors M38's fresh_overlay: the registry is the record and may be
 edited by the operator across the days this chain runs). The native-routing check must run on
 the ORIGINAL entry BEFORE the draft_*/moe_expand strip below, else it is vacuous (everything
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
def log_size():
 return os.path.getsize(ROUTER_LOG) if ROUTER_LOG.is_file() else 0
def probe_gate(model):
 """Known-positive gate: a one-image SEES/BLIND probe right after the router is up for this
 model, before any generation spend. `probe_vision.py` prints a JSON object with a `verdict`
 field (SEES/BLIND/UNREACHABLE) and exits 0 only on SEES."""
 pr=subprocess.run([h.PY,str(R/'benchmark/probe_vision.py'),'--model',model],cwd=R,capture_output=True,text=True)
 h.log('PROBE '+model+': rc='+str(pr.returncode)+' stdout='+pr.stdout.strip().replace('\n',' ')+(' stderr='+pr.stderr.strip().replace('\n',' ') if pr.stderr.strip() else ''))
 try:verdict=json.loads(pr.stdout).get('verdict')
 except Exception:verdict=None
 if verdict!='SEES':raise RuntimeError('probe_vision verdict='+str(verdict)+' (expected SEES) for '+model+' -- BLIND, aborting this leg')
def vision_cost(model,offset):
 """Vision prefill-cost measurement from the FULL-leg result rows (not the router log: TTFT in
 the router's metrics line equals total request latency for non-streaming requests, not prefill
 time, so it is not usable here). Per item: prefill_s = wall_s - completion_tokens/decode_tps
 (skipped if decode_tps is missing/<=0); image_prompt_tokens = prompt_tokens. Logs mean/max
 prefill_s, mean/max prompt_tokens, mean decode_tps. The router log is used ONLY as a request-
 count cross-check against `offset` (the log size captured right before this leg's launch)."""
 rows=h.rows(model,BENCH,TUNE)
 if not rows:
  h.log('COST '+model+': no result rows for '+BENCH+'.'+TUNE);return
 prefill=[];dtps=[];prm=[]
 for r in rows:
  p_=r.get('prompt_tokens')
  if isinstance(p_,(int,float)):prm.append(p_)
  d_=r.get('decode_tps');w_=r.get('wall_s');c_=r.get('completion_tokens') or 0
  if isinstance(d_,(int,float)) and d_>0 and isinstance(w_,(int,float)):
   prefill.append(w_-c_/d_);dtps.append(d_)
 if prefill:
  h.log('COST '+model+' n='+str(len(prefill))+' prefill_s_mean='+str(round(statistics.mean(prefill),2))+' prefill_s_max='+str(round(max(prefill),2))+' decode_tps_mean='+str(round(statistics.mean(dtps),2)))
 else:
  h.log('COST '+model+': no rows with usable wall_s/completion_tokens/decode_tps to derive prefill_s (keys sample='+str(sorted(rows[0].keys()))+')')
 if prm:
  h.log('COST '+model+' image_prompt_tokens_mean='+str(round(statistics.mean(prm),1))+' image_prompt_tokens_max='+str(max(prm)))
 else:
  h.log('COST '+model+': no prompt_tokens field on rows')
 if ROUTER_LOG.is_file():
  with ROUTER_LOG.open('r',errors='replace') as f:
   f.seek(offset);tail=f.read()
  n_log=len(re.findall(r'model='+re.escape(model)+r'\b',tail))
  h.log('COST '+model+': log cross-check request_count='+str(n_log)+' vs rows n='+str(len(rows))+(' MATCH' if n_log==len(rows) else ' MISMATCH (router log may include retries/other traffic)'))
def main():
 lock=(D/'queue.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 (D/'queue.pid').write_text(str(os.getpid()))
 h.log('SELFTEST M39 visionqa generation chain armed; no predecessor -- box asserted idle at start, not waited-for')
 p=subprocess.run(['pgrep','-f','[r]un.py generate|[m]lx_vlm.server'],capture_output=True,text=True)
 if p.stderr.strip() or p.stdout.strip() or h.listeners():raise RuntimeError('Expected idle driver/worker/router at M39 start (no predecessor to wait for) -- pgrep_stdout='+repr(p.stdout.strip())+' listeners='+repr(h.listeners()))
 for model in MODELS:
  try:
   overlay=fresh_overlay(model)
   h.ensure_router(str(overlay))
   probe_gate(model)
   existing=h.rows(model,BENCH,TUNE)
   if not existing:
    tag=model+'_pilot'
    if h.run_generate(model,BENCH,TUNE,PILOT_N,tag,str(overlay),bound_h=48):raise RuntimeError(tag+' generation failed')
    summary=h.summarize(model,BENCH,TUNE,PILOT_N,tag)
    if summary['n']!=PILOT_N or summary['errors']:raise RuntimeError(tag+' invalid rows')
    h.log('PILOT projected lower-bound seconds='+str(summary['wall_mean_s']*FULL_N)+' max='+str(summary['wall_max_s']))
   else:
    h.log(BENCH+'.'+TUNE+' for '+model+' resuming from partial: '+str(len(existing))+' existing rows -- skipping pilot')
   offset=log_size()
   tag=model+'_full'
   if h.run_generate(model,BENCH,TUNE,FULL_N,tag,str(overlay),bound_h=48):raise RuntimeError(tag+' generation failed')
   summary=h.summarize(model,BENCH,TUNE,FULL_N,tag)
   if summary['n']!=FULL_N or summary['errors']:raise RuntimeError(tag+' invalid rows')
   vision_cost(model,offset)
   with (D/(model+'_grade.log')).open('a') as out:
    gp=subprocess.run([h.PY,str(R/'benchmark/run.py'),'grade','--models',model,'--benches',BENCH,'--tune',TUNE],cwd=R,env=dict(os.environ,MLX_SERVE_CONFIG=str(overlay)),stdout=out,stderr=subprocess.STDOUT)
   if gp.returncode:raise RuntimeError('Grading failed')
   score=json.loads((R/'benchmark/results'/model/f'{BENCH}.{TUNE}.score.json').read_text())
   if score.get('n')!=FULL_N or score.get('errors'):raise RuntimeError('Invalid score (want n=='+str(FULL_N)+', errors==0)')
   h.log('RESULT '+model+' '+json.dumps({k:score.get(k) for k in ['n','acc','acc_strict','conv_rate','nonconv_kinds']}))
   src=next((score[k] for k in ('by_source','per_source','source_breakdown','sources') if k in score),None)
   if src is not None:h.log('PER-SOURCE '+model+' '+json.dumps(src))
   else:h.log('NOTE per-source breakdown not found in score.json (keys='+str(sorted(score.keys()))+')')
   # text-only control arm: same 40 items, image part dropped via VISIONQA_TEXT_ONLY (additive
   # flag read by benchmark/bench/benchmarks.py:_visionqa_messages; no CLI flag exists for this).
   # No pilot -- same pre-vetted items, same overlay/router, no probe re-gate (deliberately
   # image-less).
   os.environ['VISIONQA_TEXT_ONLY']='1'
   try:
    tag=model+'_txt_full'
    if h.run_generate(model,BENCH,TXT_TUNE,FULL_N,tag,str(overlay),bound_h=48):raise RuntimeError(tag+' generation failed')
    txt_summary=h.summarize(model,BENCH,TXT_TUNE,FULL_N,tag)
    if txt_summary['n']!=FULL_N or txt_summary['errors']:raise RuntimeError(tag+' invalid rows')
   finally:
    os.environ.pop('VISIONQA_TEXT_ONLY',None)
   with (D/(model+'_txt_grade.log')).open('a') as out:
    gpt=subprocess.run([h.PY,str(R/'benchmark/run.py'),'grade','--models',model,'--benches',BENCH,'--tune',TXT_TUNE],cwd=R,env=dict(os.environ,MLX_SERVE_CONFIG=str(overlay)),stdout=out,stderr=subprocess.STDOUT)
   if gpt.returncode:raise RuntimeError('Text-only control grading failed')
   score_txt=json.loads((R/'benchmark/results'/model/f'{BENCH}.{TXT_TUNE}.score.json').read_text())
   if score_txt.get('n')!=FULL_N or score_txt.get('errors'):raise RuntimeError('Invalid text-only control score (want n=='+str(FULL_N)+', errors==0)')
   h.log('RESULT '+model+' tune='+TXT_TUNE+' (text-only control, images dropped) '+json.dumps({k:score_txt.get(k) for k in ['n','acc','acc_strict','conv_rate','nonconv_kinds']}))
  except Exception as e:
   import traceback
   h.log('ERROR leg for '+model+': '+repr(e)+'\n'+traceback.format_exc())
   h.stop_router()
   if h.listeners():raise RuntimeError('router still listening on :8000 after error cleanup for '+model)
   continue
  h.unload();h.stop_router()
  if h.listeners():raise RuntimeError('router still listening on :8000 after stop for '+model)
 h.log('=== M39 VISIONQA QUEUE DONE ===')
if __name__=='__main__':
 try:main()
 except Exception as e:h.log('FATAL '+repr(e));raise
