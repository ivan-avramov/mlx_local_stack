import re,json,os
import numpy as np
L=[l for l in open(os.path.expanduser('~/ws/mlx_local_stack/logs/main_model.log')) if 'metrics — /v1/chat' in l and l[11:19]>='13:36:00']
reqs=[]
for l in L:
    ms=int(re.search(r'\| (\d+)ms',l).group(1)); p=int(re.search(r'prompt=(\d+)',l).group(1)); c=int(re.search(r'completion=(\d+)',l).group(1))
    t=re.search(r'TTFT=(\d+)ms',l); reqs.append((l[11:19],ms,p,c,int(t.group(1)) if t else None))
items=[];cur=[]
for r in reqs:
    if cur and r[2]<cur[-1][2]: items.append(cur); cur=[]
    cur.append(r)
items.append(cur)
names=['scale-generator','zipper','poker','two-bucket','forth']
print(f"{'item':16}{'turns':>6}{'in_tok':>9}{'new_in':>8}{'out_tok':>8}{'max_ctx':>8}{'wall_s':>8}")
X=[];Y=[]
for n,it in zip(names,items):
    turns=len(it); intot=sum(r[2] for r in it); out=sum(r[3] for r in it); mx=max(r[2] for r in it); wall=sum(r[1] for r in it)/1000
    new=it[0][2]+sum(it[i][2]-it[i-1][2] for i in range(1,len(it)))
    print(f"{n:16}{turns:>6}{intot:>9}{new:>8}{out:>8}{mx:>8}{wall:>8.1f}")
    prev=0
    for r in it:
        X.append([1,r[2]-prev if prev else r[2],r[3]]); Y.append(r[1]); prev=r[2]
X=np.array(X,float);Y=np.array(Y,float)
b,res,_,_=np.linalg.lstsq(X,Y,rcond=None)
print(f"fit ms = {b[0]:.0f} + {b[1]:.2f}*new_prompt + {b[2]:.2f}*completion  -> prefill ~{1000/b[1]:.0f} tok/s (incremental), decode ~{1000/b[2]:.1f} tok/s; R2={1-res[0]/((Y-Y.mean())**2).sum():.3f}")
tot_new=sum(x[1] for x in X); tot_out=sum(x[2] for x in X)
print(f"totals: requests={len(reqs)} input(cum)={sum(r[2] for r in reqs)} new_input={tot_new:.0f} output={tot_out:.0f} router_wall={sum(r[1] for r in reqs)/1000:.0f}s")
print(f"cost split: prefill share {tot_new*b[1]/(tot_new*b[1]+tot_out*b[2]):.0%}, decode share {tot_out*b[2]/(tot_new*b[1]+tot_out*b[2]):.0%}")
for n in names:
    d=json.load(open(os.path.expanduser(f'~/ws/mlx_local_stack_workdir/opencode_transcripts/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/opencode_live_check/python__{n}.json')))
    a=[m['info'] for m in d['messages'] if m['info'].get('role')=='assistant']
    print(f"  transcript {n}: assistant_msgs={len(a)} input={sum(m['tokens']['input'] for m in a)} output={sum(m['tokens']['output'] for m in a)} reasoning={sum(m['tokens']['reasoning'] for m in a)}")
