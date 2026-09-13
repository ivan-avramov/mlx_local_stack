import json,glob,collections,itertools,math,sys
import numpy as np
from scipy.optimize import minimize
rng=np.random.default_rng(38)
MODELS=['Qwen3.8-27B-mlx-uniform-4bit','Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed','Ornith-1.0-35B-mlx-uniform-4bit','Qwen3.6-27B-Opus-Distill-OptiQ-4bit','NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit']
SH={m:s for m,s in zip(MODELS,['UNI','MIX','ORN','Q36','NEM'])}
L={}
for f in glob.glob('results/*/cjudge.m38.jsonl'):
    m=f.split('/')[1]
    for l in open(f):
        r=json.loads(l); L[f"{m}::{r['id']}"]=len((r.get('content') or ''))
v=[json.loads(l) for l in open('results/judge_c_v1/verdicts.jsonl')]
J=['sonnet','opus','codex:gpt-5.6-terra:medium']  # allow-shorthand
by=collections.defaultdict(dict); meta={}
for r in v:
    if r['anchor_type'] is None:
        by[(r['pair_id'],r['judge'])][r['order']]=r['choice']; meta[r['pair_id']]=(r['a_key'],r['b_key'],r['item_id'])
def collapse(o):
    a=o.get('AB'); b=o.get('BA')
    if a is None or b is None: return 'tie'
    bn={'A':'B','B':'A','tie':'tie'}[b]
    return a if a==bn else 'tie'
pv={}
for (pid,j),o in by.items(): pv.setdefault(pid,{})[j]=collapse(o)
def panel(d):
    c=collections.Counter(d.values()).most_common(1)[0]
    return c[0] if c[1]>=2 else 'tie'
# ---- 1. per model-pair: preference of m1 split by whether m1 was shorter
print("== 1. Panel preference for ROW model, split by whether ROW was the SHORTER answer (n items)")
rows=[]
for pid,d in pv.items():
    a,b,item=meta[pid]; ma,mb=a.split('::')[0],b.split('::')[0]
    pvd=panel(d); sa=1.0 if pvd=='A' else (0.0 if pvd=='B' else 0.5)
    rows.append((ma,mb,item,sa,L[a],L[b]))
pairs=collections.defaultdict(list)
for ma,mb,item,sa,la,lb in rows:
    m1,m2=sorted((ma,mb),key=MODELS.index)
    s1=sa if ma==m1 else 1-sa; l1,l2=(la,lb) if ma==m1 else (lb,la)
    pairs[(m1,m2)].append((item,s1,l1,l2))
for (m1,m2),xs in sorted(pairs.items(), key=lambda kv:(MODELS.index(kv[0][0]),MODELS.index(kv[0][1]))):
    sh=[s for _,s,l1,l2 in xs if l1<l2]; lo=[s for _,s,l1,l2 in xs if l1>=l2]
    f=lambda z: f"{np.mean(z):.2f} (n={len(z)})" if z else "—"
    print(f"  {SH[m1]} vs {SH[m2]}: overall {np.mean([s for _,s,_,_ in xs]):.3f} | {SH[m1]} shorter: {f(sh)} | {SH[m1]} longer: {f(lo)}")
# ---- 2. Bradley-Terry with length covariate, per judge and panel; item-cluster bootstrap for UNI-MIX
def fit(obs, use_len=True):
    # obs: list of (ia, ib, y in {1,0,0.5}, loglenratio)
    k=len(MODELS)
    def nll(th):
        beta=th[:k]; g=th[k] if use_len else 0.0
        s=0.0
        for ia,ib,y,x in obs:
            z=beta[ia]-beta[ib]+g*x
            p=1/(1+math.exp(-z))
            s-= y*math.log(p+1e-12)+(1-y)*math.log(1-p+1e-12)
        s+=0.01*np.sum(beta**2)  # tiny ridge; identifiability via NEM anchor below
        return s
    th0=np.zeros(k+1)
    res=minimize(nll,th0,method='L-BFGS-B')
    beta=res.x[:k]-res.x[MODELS.index('NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit')]
    return beta, (res.x[k] if use_len else None)
def build(rows_src):
    obs=[]
    for ma,mb,item,sa,la,lb in rows_src:
        obs.append((MODELS.index(ma),MODELS.index(mb),sa,math.log(la/lb)))
    return obs
print("\n== 2. Bradley-Terry strengths (NEM=0), panel verdicts, with vs without log-length covariate")
b0,_=fit(build(rows),False); b1,g=fit(build(rows),True)
for m in MODELS: print(f"  {SH[m]}: raw {b0[MODELS.index(m)]:+.2f}  length-adjusted {b1[MODELS.index(m)]:+.2f}")
print(f"  length coefficient (per log-ratio): {g:+.2f}  -> a 2x longer answer multiplies odds by {math.exp(g*math.log(2)):.2f}")
# per-judge
print("\n== 2b. per-judge length-adjusted strengths")
for j in J:
    rj=[]
    for pid,d in pv.items():
        a,b,item=meta[pid]; c=d[j]; sa=1.0 if c=='A' else (0.0 if c=='B' else 0.5)
        rj.append((a.split('::')[0],b.split('::')[0],item,sa,L[a],L[b]))
    bj,gj=fit(build(rj),True)
    print(f"  {j[:6]}: "+"  ".join(f"{SH[m]} {bj[MODELS.index(m)]:+.2f}" for m in MODELS)+f"  | len coef {gj:+.2f}")
# bootstrap UNI-MIX adjusted difference over items
items=sorted({r[2] for r in rows}); byitem=collections.defaultdict(list)
for r in rows: byitem[r[2]].append(r)
diffs=[]; order_same=0
iu,im=MODELS.index('Qwen3.8-27B-mlx-uniform-4bit'),MODELS.index('Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed')
B=300
for _ in range(B):
    samp=[r for it in rng.choice(items,len(items),replace=True) for r in byitem[it]]
    bb,_=fit(build(samp),True); diffs.append(bb[iu]-bb[im]); order_same+= (np.argsort(-bb).tolist()==np.argsort(-b1).tolist())
diffs=np.array(diffs)
print(f"\n== 3. Length-adjusted UNI - MIX strength: point {b1[iu]-b1[im]:+.2f}, 95% item-bootstrap CI [{np.percentile(diffs,2.5):+.2f}, {np.percentile(diffs,97.5):+.2f}] (B={B}); P(UNI>MIX adj) = {np.mean(diffs>0):.2f}; full adjusted order reproduced in {order_same/B:.2f} of resamples")
print(f"   adjusted P(UNI beats MIX at equal length) = {1/(1+math.exp(-(b1[iu]-b1[im]))):.3f}")
json.dump({'bt_raw':dict(zip(MODELS,map(float,b0))),'bt_len_adjusted':dict(zip(MODELS,map(float,b1))),'length_coef':float(g),'uni_minus_mix_adj':float(b1[iu]-b1[im]),'uni_minus_mix_adj_ci95':[float(np.percentile(diffs,2.5)),float(np.percentile(diffs,97.5))],'p_uni_gt_mix_adj':float(np.mean(diffs>0)),'B':B},open(sys.argv[1],'w'),indent=1)
