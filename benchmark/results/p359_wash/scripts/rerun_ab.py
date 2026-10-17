import json,os,sys
sys.path.insert(0,'.')
from bench import agentbench_compare as A
M=["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed","Qwen3.8-27B-mlx-uniform-4bit","Ornith-1.0-35B-mlx-uniform-4bit","Qwen3.6-27B-Opus-Distill-OptiQ-4bit","NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]
T=os.environ['P359_OUT']+'/agentbench_compare'; os.makedirs(T,exist_ok=True)
def walk(a,b,p,diffs):
    if isinstance(a,dict) and isinstance(b,dict):
        for k in set(a)|set(b): walk(a.get(k,'<absent>'),b.get(k,'<absent>'),p+'/'+k,diffs)
    elif isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        for i,(x,y) in enumerate(zip(a,b)): walk(x,y,p+f'[{i}]',diffs)
    elif a!=b: diffs.append((p,a,b))
for n,usem in ((1,False),(3,False),(4,True)):
    arms=[A.load_arm(m,f'results/{m}/agentbench_os.v1.chain{n}.jsonl',f'results/{m}/agentbench_os.v1.chain{n}.manifest.json' if usem else None) for m in M]
    r=A.build_report(arms)
    r=json.loads(json.dumps(r,default=str))
    json.dump(r,open(f'{T}/agentbench_os_compare_chain{n}.json','w'),indent=2)
    md=A.render_markdown(r if False else A.build_report(arms),cli_line='(regenerated P348)')
    open(f'{T}/agentbench_os_compare_chain{n}.md','w').write(md)
    old=json.load(open(f'results/agentbench_os_compare_chain{n}.json'))
    d=[];walk(old,r,'',d)
    print('chain',n,'comparable',r['comparable'],'ndiffs',len(d))
    for x in d[:15]: print('  ',x[0],str(x[1])[:50],'->',str(x[2])[:50])
    for p in r['pairs']:
        print('   ',p['model_a'][:22],p['model_b'][:22],p['delta']['verdict'],p['delta'].get('degenerate'),p['delta'].get('discordance_upper95'),p['mcnemar_b'],p['mcnemar_c'])
