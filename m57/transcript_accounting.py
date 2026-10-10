import json,glob,os,sys,collections
import numpy as np
W="$STACK_WORKDIR"; M="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
R="$STACK_REPO/benchmark/results/"+M
fix=lambda p:p.replace("$STACK_WORKDIR",W).replace("$HOME/ws","$HOME/ws")
PC=[10,50,90,99,100]
def pct(a):
    a=np.array(a,float)
    return {} if len(a)==0 else {("max" if q==100 else "p%d"%q):float(np.percentile(a,q)) for q in PC}|{"mean":float(a.mean()),"n":len(a)}
BANDS=[("0",0,0),("1-5",1,5),("6-8",6,8),("9-511",9,511),("512-1023",512,1023),(">=1024",1024,1e18)]
CB=[("<16K",0,16384),("16-64K",16384,65536),("64-128K",65536,131072),(">128K",131072,1e18)]
def bands(pre):
    n=len(pre);return {b[0]:{"n":sum(b[1]<=x<=b[2] for x in pre),"share":sum(b[1]<=x<=b[2] for x in pre)/max(n,1)} for b in BANDS}
def ctxsplit(turns):
    tot=sum(t["pre"] for t in turns) or 1
    return {c[0]:{"tokens":sum(t["pre"] for t in turns if c[1]<=t["ctx"]<c[2]),"share":sum(t["pre"] for t in turns if c[1]<=t["ctx"]<c[2])/tot,"turns":sum(1 for t in turns if c[1]<=t["ctx"]<c[2])} for c in CB}
def fit(X,y):
    X=np.array(X,float);y=np.array(y,float)
    c,*_=np.linalg.lstsq(X,y,rcond=None);return c.tolist()
out={}
# ---------- opencode
oc=[];sess=0;missing=0;rows_total=0;seenp=set()
for f in sorted(glob.glob(R+"/opencode_*.m55.s*.jsonl")):
    for l in open(f):
        r=json.loads(l);rows_total+=1
        p=r.get("transcript_path")
        if not p or not os.path.exists(fix(p)): missing+=1;continue
        if p in seenp: continue
        seenp.add(p)
        d=json.load(open(fix(p)));steps=[]
        for m in d["messages"]:
            if m["info"].get("role")!="assistant":continue
            cur=[]
            for pt in m["parts"]:
                if pt["type"]=="tool": cur.append(len((pt["state"].get("output") or "")) if isinstance(pt["state"].get("output"),str) else len(json.dumps(pt["state"].get("output"))))
                if pt["type"]=="step-finish":
                    tk=pt["tokens"];steps.append({"in":tk["input"],"cr":tk["cache"]["read"],"cw":tk["cache"]["write"],"out":tk["output"],"chars":sum(cur),"reason":pt.get("reason")});cur=[]
        sess+=1
        prev=None
        for i,s in enumerate(steps):
            ctx=s["in"]+s["cr"]+s["cw"];s["ctx"]=ctx;s["pre"]=s["in"]+s["cw"]
            s["sid"]=p;s["i"]=i
            s["prevctx"]=prev["ctx"] if prev else None
            s["prevchars"]=prev["chars"] if prev else None
            s["prevout"]=prev["out"] if prev else None
            prev=s;oc.append(s)
# calibrate: new tokens vs chars of previous step's tool outputs
rows=[s for s in oc if s["i"]>0]
X=[[s["prevchars"],s["prevout"],1] for s in rows];y=[s["ctx"]-s["prevctx"] for s in rows]
cf=fit(X,y);cpt=1/cf[0] if cf[0] else None
for s in oc: s["obs"]=(s["prevchars"]*cf[0]) if s["i"]>0 else 0
cold=[s for s in oc if s["i"]>0 and s["cr"]<0.5*s["prevctx"]]
def cause(s):
    if s["ctx"]<s["prevctx"]: return "ctx_shrank(compaction?)"
    if s["cr"]==0: return "cache_read_0_full_replay"
    return "partial_prefix(%.2f of prev)"%(s["cr"]/s["prevctx"])
ocres={"sessions":sess,"rows_total":rows_total,"rows_without_transcript":missing,"unique_transcripts":len(seenp),"turns":len(oc),
 "ctx":pct([s["ctx"] for s in oc]),"prefilled":pct([s["pre"] for s in oc]),"prefilled_excl_first_turn":pct([s["pre"] for s in oc if s["i"]>0]),
 "first_turn_ctx":pct([s["ctx"] for s in oc if s["i"]==0]),"first_turn_cache_read":pct([s["cr"] for s in oc if s["i"]==0]),
 "obs_tokens_est":pct([s["obs"] for s in oc if s["i"]>0]),"calib_new_tokens_vs[chars,prev_out,1]":cf,"chars_per_token_tool_output":cpt,
 "bands_all":bands([s["pre"] for s in oc]),"bands_excl_first":bands([s["pre"] for s in oc if s["i"]>0]),"prefilled_total":sum(s["pre"] for s in oc),
 "prefilled_by_ctx":ctxsplit(oc),"cache_write_nonzero_turns":sum(1 for s in oc if s["cw"]),
 "cold":{"n":len(cold),"share_turns":len(cold)/len(oc),"ctx":[s["ctx"] for s in cold],"pre":[s["pre"] for s in cold],"tokens_reread":sum(s["pre"] for s in cold),
  "share_prefilled":sum(s["pre"] for s in cold)/sum(s["pre"] for s in oc),"causes":collections.Counter(cause(s) for s in cold),"detail":[(os.path.basename(s["sid"]),s["i"],s["prevctx"],s["cr"],s["in"]) for s in cold]},
 "first_turn_total_share_of_prefilled":sum(s["pre"] for s in oc if s["i"]==0)/sum(s["pre"] for s in oc)}
out["opencode"]=ocres
# row-level aggregates (both s1+s2)
agg=[];
for f in sorted(glob.glob(R+"/opencode_*.m55.s*.jsonl")):
    for l in open(f):
        r=json.loads(l);t=r.get("traffic")
        if t: agg.append(t)
out["opencode_row_traffic_all_rows"]={"rows":len(agg),"turns":sum(t["turns"] for t in agg),"max_context":pct([t["max_context"] for t in agg]),"input_tokens_cumulative_sum":sum(t["input_tokens_cumulative"] for t in agg),"input_tokens_incremental_sum":sum(t["input_tokens_incremental"] for t in agg)}
# ---------- agentbench
ab={}
for c in (1,3,4):
    f=R+"/agentbench_os.v1.chain%d.jsonl"%c
    ts=[];ns=0;miss=0
    for l in open(f):
        r=json.loads(l);p=r.get("transcript_path")
        if not p or not os.path.exists(fix(p)): miss+=1;continue
        d=json.load(open(fix(p)));ns+=1;prev=None
        for i,t in enumerate(d["turns"]):
            if t.get("prompt_tokens") is None: continue
            s={"ctx":t["prompt_tokens"],"comp":t["completion_tokens"],"i":i,"sid":r["id"],"chars":len(prev["tr"]) if prev else 0,"prevctx":prev["ctx"] if prev else None,"prevcomp":prev["comp"] if prev else None}
            tr=t.get("tool_result");s["tr"]=tr if isinstance(tr,str) else json.dumps(tr or "")
            # tool_result in turn i is observed by turn i+1
            prev=s;ts.append(s)
    ab[c]={"sessions":ns,"missing":miss,"turns":ts}
allt=[s for c in ab for s in ab[c]["turns"]]
rows=[s for s in allt if s["i"]>0]
cf2=fit([[s["chars"],s["prevcomp"],1] for s in rows],[s["ctx"]-s["prevctx"] for s in rows])
for s in allt:
    s["obs"]=s["chars"]*cf2[0] if s["i"]>0 else 0
    s["pre"]=s["ctx"] if s["i"]==0 else max(s["ctx"]-s["prevctx"],0)  # IDEAL-reuse estimate, not measured
shrink=[s for s in allt if s["i"]>0 and s["ctx"]<s["prevctx"]]
abres={"chains":{c:{"sessions":ab[c]["sessions"],"missing_transcripts":ab[c]["missing"],"turns":len(ab[c]["turns"])} for c in ab},"turns":len(allt),"sessions":sum(ab[c]["sessions"] for c in ab),
 "ctx":pct([s["ctx"] for s in allt]),"first_turn_ctx":pct([s["ctx"] for s in allt if s["i"]==0]),
 "prefilled_IDEAL_REUSE_ESTIMATE":pct([s["pre"] for s in allt]),"prefilled_ideal_excl_first":pct([s["pre"] for s in rows]),
 "delta_ctx_per_turn":pct([s["ctx"]-s["prevctx"] for s in rows]),"obs_tokens_est":pct([s["obs"] for s in rows]),
 "calib_delta_vs[chars,prev_comp,1]":cf2,"chars_per_token_tool_output":1/cf2[0],
 "bands_ideal":bands([s["pre"] for s in allt]),"bands_ideal_excl_first":bands([s["pre"] for s in rows]),"prefilled_ideal_total":sum(s["pre"] for s in allt),
 "prefilled_by_ctx_ideal":ctxsplit(allt),"first_turn_share_of_ideal_prefill":sum(s["pre"] for s in allt if s["i"]==0)/sum(s["pre"] for s in allt),
 "ctx_shrinks":{"n":len(shrink),"detail":[(s["sid"],s["i"],s["prevctx"],s["ctx"]) for s in shrink][:20]},"cached_tokens":"unavailable (not recorded in transcripts/rows; no server log covers these runs)"}
out["agentbench_os"]=abres
json.dump(out,open(W+"/m57/transcript_accounting.json","w"),indent=1,default=str)
print(json.dumps(out,indent=1,default=str)[:9000])
