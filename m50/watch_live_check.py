import json,os,subprocess,time,sys
W=os.path.expanduser('~/ws/mlx_local_stack_workdir/m50'); OUT=W+'/opencode_live_check.jsonl'; LOG=W+'/opencode_live_check.log'
RLOG=os.path.expanduser('~/ws/mlx_local_stack/logs/main_model.log'); PID=37899; t0=time.time(); last=0
def alive(p): return subprocess.run(['kill','-0',str(p)],capture_output=True).returncode==0
def rows():
    try: return [json.loads(l) for l in open(OUT) if l.strip()]
    except FileNotFoundError: return []
while True:
    r=rows(); n=len(r); el=time.time()-t0
    oc=subprocess.run(['pgrep','-fl','opencode run'],capture_output=True,text=True).stdout.strip().splitlines()
    rl=subprocess.run(['tail','-c','400000',RLOG],capture_output=True,text=True).stdout
    reqs=rl.count('POST /v1/chat/completions'); 
    print(f"[watch +{el/60:.1f}m] rows={n} (+{n-last}) probe_alive={alive(PID)} opencode_children={len(oc)} router_chat_posts_in_tail={reqs}",flush=True)
    for x in r[last:]:
        lm=x.get('loop_metrics') or {}
        print(f"  row {x.get('item')}: acc={x.get('acc')} stop={x.get('stop_reason')} wall={x.get('wall_s') or x.get('elapsed_s')} rc={x.get('opencode_rc')} transcript={x.get('transcript_path')} tool_calls={lm.get('tool_calls')} err={lm.get('error_calls')} rep={lm.get('repeat_identical_calls')} maxrun={lm.get('max_identical_run')}",flush=True)
    last=n
    if not alive(PID):
        print(f"[watch] probe exited; final rows={n}; ETA-vs-actual: {el/60:.1f} min total",flush=True); break
    if n and el/n*5 > 3600*2: print("  ASSESS: mean per-item pace implies >2h; watch for stall/loop stops",flush=True)
    time.sleep(300)
