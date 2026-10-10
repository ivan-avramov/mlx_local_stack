"""Root read-only validation of a completed C82 arm, then pinned grading evidence."""
from pathlib import Path
import hashlib,json,sys
P=Path(__file__).resolve().parent
R=P.parent
MODEL='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0,str(R/'stack-validation/benchmark'))
from bench import client,convergence,traces
sys.path.insert(0,str(P))
import runner
mode=sys.argv[1];assert mode in ('native16','uniform8')
frozen=json.loads((P/'frozen.json').read_text());arm=frozen['arms'][mode];out=P/'runs'/mode
runner.verify_frozen(frozen)
summary=json.loads((out/'summary.json').read_text())
assert summary.get('error') is None
assert summary['status']=='complete' and summary['completed']==15 and summary['frozen_sha256']==sha(P/'frozen.json')
for f,h in frozen['input_hashes'].items():assert sha(Path(f))==h,f
prelaunch=json.loads((out/'prelaunch.json').read_text());assert prelaunch['frozen_sha256']==sha(P/'frozen.json')
before=prelaunch['evidence']
rows={};files={}
for bench,path in arm['results'].items():
 p=Path(path);manifest=p.with_suffix('.manifest.json');files[p.name]=sha(p);files[manifest.name]=sha(manifest)
 records=[json.loads(l) for l in p.read_text().splitlines()];assert len(records)==5
 for row in records:
  key=(bench,row['id']);assert key not in rows;rows[key]=row
 m=json.loads(manifest.read_text());assert m['registry']['sha256']==arm['overlay_sha256'] and m['runtime']['draft_kind']=='mtp'
 assert m['sampling']==arm['params'] and m['git']['serving_path']==before['source']['serving_path']
requests={};responses={}
for i,e in enumerate(frozen['requests'],1):
 d=out/f'request-{i:02d}'
 assert (d/'request.json').read_text()==e['wire']
 raw=json.loads((d/'response.json').read_text());row=rows[(e['bench'],e['id'])]
 assert json.loads((d/'row.json').read_text())==row
 assert row['sampler_seed']==e['seed'] and row['model']==MODEL and not row.get('error')
 assert row['completion_tokens']==raw['usage']['completion_tokens'] and row['prompt_tokens']==raw['usage']['prompt_tokens']
 assert row['resolved_thinking_budget']==81920
 choice=raw['choices'][0];message=choice['message'];content=message.get('content') or '';reasoning=message.get('reasoning') or message.get('reasoning_content') or ''
 assert row['content']==client.strip_thinking(content) and row['finish_reason']==choice['finish_reason']
 assert row['content_sha256']==hashlib.sha256(content.encode()).hexdigest()
 assert row['reasoning_sha256']==hashlib.sha256(reasoning.encode()).hexdigest()
 for key in ('draft_kind','draft_rounds','draft_n','draft_n_accepted'):assert row.get('draft',{}).get(key)==(raw.get('timings') or {}).get(key)
 assert row['converged'] is convergence.is_converged(row)
 assert row['nonconv_kind']==traces.classify(row,trace_text=reasoning)
 assert row['resolved_thinking_budget']==convergence.resolved_thinking_budget(row,context_limit=262144,max_tokens=102400)
 requests[d.name]=sha(d/'request.json');responses[d.name]=sha(d/'response.json')
heartbeats=[json.loads(l) for l in (out/'heartbeat.jsonl').read_text().splitlines()]
assert heartbeats[0]['event']=='SELFTEST' and heartbeats[0]['passed'] is True
assert heartbeats[-1]['event']=='RUNNER-EXIT' and heartbeats[-1]['status']=='complete' and heartbeats[-1]['error'] is None and heartbeats[-1]['completed']==15
assert summary['rows']==[rows[(e['bench'],e['id'])] for e in frozen['requests']]
assert len(rows)==15
entry=arm['entry']
result={'schema_version':1,'decision':'C82','status':'complete','model':MODEL,'mode':mode,'tune':arm['tune'],
 'source_root':str(R/'stack-validation/benchmark/results'),'selection_sha256':frozen['selection_sha256'],
 'overlay_sha256':arm['overlay_sha256'],'source_shas':before['source']['submodules'],'serving_path':before['source']['serving_path'],
 'versions':{'mlx':before['versions']['mlx'],'mlx-metal':before['versions']['mlx-metal']},'sampling':arm['params'],
 'kv':{k:entry[k] for k in ('kv_bits','kv_quant_scheme','quantized_kv_start','prefill_step_size','max_kv_cache_size','kv_prealloc_tokens')},
 'runtime':{'draft_kind':'mtp'},'files':files,'summary_sha256':sha(out/'summary.json'),'raw_requests':requests,'raw_responses':responses,
 'layout_evidence_sha256':sha(P/'layout-evidence.json'),'layout_scope':'constructor/tiny-tensor CPU check; worker flags/environment verified, not in-process cache dump'}
result['kv']['kv_group_size']=64
path=P/f'finalized-{mode}.json';assert not path.exists();path.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'mode':mode,'rows':len(rows),'converged':sum(r['converged'] for r in rows.values()),'sha256':sha(path)}))
