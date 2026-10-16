import json,os,sys
sys.path.insert(0,'.')
from bench import judge_gate as J
T=os.environ['TMPDIR']+'/p348/jg'
cfg=[('judge_c_v1','results/judge_c_v1/pairs.jsonl','results/judge_c_v1/verdicts.jsonl'),
 ('judge_m40/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed',)*1,
 ]
import glob
jobs=[('judge_c_v1','pairs_full.jsonl')]
for d in ['judge_m40/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed','judge_m40/Qwen3.8-27B-mlx-uniform-4bit','judge_m60/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed']:
    jobs.append((d,'pair_manifest.jsonl'))
def walk(a,b,p,diffs):
    if isinstance(a,dict) and isinstance(b,dict):
        for k in set(a)|set(b): walk(a.get(k,'<absent>'),b.get(k,'<absent>'),p+'/'+k,diffs)
    elif isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        for i,(x,y) in enumerate(zip(a,b)): walk(x,y,p+f'[{i}]',diffs)
    elif a!=b: diffs.append((p,a,b))
for d,pf in jobs:
    base='results/'+d
    pairs=J.read_jsonl(f'{base}/{pf}'); vr=J.read_jsonl(f'{base}/verdicts.jsonl')
    judges=sorted({r.get('judge') for r in vr if r.get('judge')})
    os.makedirs(f'{T}/{d}',exist_ok=True)
    g=J.compute_gate(pairs,vr,judges)
    og=json.load(open(f'{base}/gate.json'))
    diffs=[];walk(og,json.loads(json.dumps(g)),'',diffs)
    print(d,'gate',g['overall'],'diffs',diffs[:5])
    json.dump(g,open(f'{T}/{d}/gate.json','w'),indent=2)
    r=J.compute_ranking(pairs,vr,judges,seed=0)
    orr=json.load(open(f'{base}/ranking.json'))
    r=json.loads(json.dumps(r))
    diffs=[];walk({k:v for k,v in orr.items() if k!='usage'},r,'',diffs)
    print(d,'ranking',{k:v['verdict'] for k,v in r['pairs'].items()} if len(r['pairs'])<3 else {k[-30:]:v['verdict'] for k,v in r['pairs'].items()})
    for x in diffs[:10]: print('   DIFF',x)
    json.dump(r,open(f'{T}/{d}/ranking.json','w'),indent=2)
