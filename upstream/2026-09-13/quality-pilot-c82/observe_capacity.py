"""Read-only capacity event and system-pressure observer; never signals a model."""
from pathlib import Path
import json,time,subprocess,sys,psutil
P=Path(__file__).resolve().parent;mode=sys.argv[1];assert mode in ('uniform8','native16')
run=P.parent/'capacity'/f'm42c82cap-{mode}-20260913'/'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
seen=0;last=0
while True:
 lines=(run/'heartbeat.jsonl').read_text().splitlines() if (run/'heartbeat.jsonl').exists() else []
 for line in lines[seen:]:
  try:d=json.loads(line)
  except json.JSONDecodeError:continue
  if d['event'] in ('RUNG-COMPLETE','RUNNER-EXIT','ASSESSMENT'):
   print(json.dumps({k:d.get(k) for k in ('event','status','rungs_completed','current_rung','current_rung_elapsed_s','peaks','errors','error','elapsed_s','completed_prefill_ratios')}),flush=True)
 seen=len(lines)
 if time.monotonic()-last>=60:
  state=json.loads((P/'active.json').read_text());sample={'unix_time':time.time(),'mode':mode,'phase':'during capacity; first sample is not a prelaunch baseline'}
  for name,cmd in [('swap',['sysctl','vm.swapusage']),('memory_pressure',['memory_pressure','-Q'])]:
   try:sample[name]=subprocess.check_output(cmd,text=True,timeout=10).strip()
   except (OSError,subprocess.SubprocessError) as e:sample[name]={'error':type(e).__name__}
  try:
   worker=psutil.Process(state['worker_pid']);sample['worker']={'pid':worker.pid,'elapsed_s':round(time.time()-worker.create_time(),1),'rss_gb':worker.memory_info().rss/1e9}
  except psutil.Error:sample['worker']=None
  with (P/f'memory-observations-{mode}.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  print(json.dumps({'event':'SYSTEM-OBSERVATION',**sample}),flush=True);last=time.monotonic()
 if (run/'summary.json').exists():
  d=json.loads((run/'summary.json').read_text());print(json.dumps({'event':'FINAL',**{k:d.get(k) for k in ('status','error','actual_prompt_tokens','within_rough_48gb')}}),flush=True);break
 time.sleep(1)
