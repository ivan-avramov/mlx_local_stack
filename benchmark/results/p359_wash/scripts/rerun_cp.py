import json,glob,sys,os
sys.path.insert(0,'.')
from bench import compare_predictor as C
out={}
for f in sorted(glob.glob('results/*/*.vs.*.json')):
    d=json.load(open(f))
    mn=d['model']
    try:
        r=C.compare_predictor(mn,d['bench'],d['tune_a'],d['tune_b'],key=d['key'],margin=d['margin'],must_differ=d.get('must_differ','draft_kind'))
    except Exception as e:
        print(f,'ERR',repr(e)[:300]);continue
    if not r['comparable']:
        print(f,'REFUSED',r['reason'][:300]);continue
    od=os.environ['P359_OUT']+'/compare_predictor/'+f.split('/')[1]; os.makedirs(od,exist_ok=True); json.dump(r,open(od+'/'+os.path.basename(f),'w'),indent=2,sort_keys=True)
    # compare
    diffs=[]
    def walk(a,b,p=''):
        if isinstance(a,dict) and isinstance(b,dict):
            for k in set(a)|set(b):
                walk(a.get(k,'<absent>'),b.get(k,'<absent>'),p+'/'+k)
        elif a!=b: diffs.append((p,a,b))
    walk(d,r)
    dd=r['delta'][d['key']]
    print(os.path.basename(f),d['verdict'],'->',r['verdict'],'upper95',dd.get('discordance_upper95'),'degen',dd.get('degenerate'),'n',r['n_items'])
    for x in diffs:
        if not x[0].startswith('/warnings'): print('   DIFF',x[0],str(x[1])[:60],str(x[2])[:60])
