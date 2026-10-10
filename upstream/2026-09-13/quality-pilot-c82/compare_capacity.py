"""Compare completed C82 capacity arms without pooling contexts or quality axes."""
from pathlib import Path
import json,hashlib
P=Path(__file__).resolve().parent;R=P.parent;MODEL='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
data={mode:json.loads((P/f'finalized-capacity-{mode}.json').read_text()) for mode in ('native16','uniform8')}
for mode,d in data.items():assert d['status']=='complete' and len(d['records'])==3
for key in ('submodules','serving_path'):
 assert data['native16']['prelaunch']['source'][key]==data['uniform8']['prelaunch']['source'][key]
for mode in data:
 q=json.loads((P/'runs'/mode/'summary.json').read_text());assert q['status']=='complete' and q['completed']==15 and q['error'] is None
 g=json.loads((P/'grades'/mode/'grading-provenance.json').read_text());assert g['status']=='complete' and g['run_evidence_sha256']==sha(P/f'finalized-{mode}.json')
for i in range(1,5):
 req=[json.loads((R/'capacity'/f'm42c82cap-{mode}-20260913'/MODEL/f'request-{i:02d}.json').read_text()) for mode in ('native16','uniform8')]
 assert req[0]==req[1],f'capacity request mismatch {i}'
rows=[]
for a,b in zip(data['native16']['records'],data['uniform8']['records']):
 assert a['ctx']==b['ctx'] and a['prompt_tokens']==b['prompt_tokens']
 keys=('server_peak_gb','prefill_s','prefill_tps','decode_tps','retrieval_acc','acceptance')
 rows.append({'nominal_context':a['ctx'],'actual_prompt_tokens':a['prompt_tokens'],'native16':{k:a[k] for k in keys},'uniform8':{k:b[k] for k in keys},'uniform8_minus_native16_peak_gb':b['server_peak_gb']-a['server_peak_gb'],'native16_decode_over_uniform8':a['decode_tps']/b['decode_tps'],'native16_prefill_time_reduction_fraction':1-a['prefill_s']/b['prefill_s']})
result={'decision':'C82','status':'complete','model':MODEL,'completed_quality_requests':30,'completed_capacity_and_calibration_requests':8,'rows':rows,'capacity_evidence_sha256':{mode:sha(P/f'finalized-capacity-{mode}.json') for mode in data},'source_shas':data['native16']['prelaunch']['source']['submodules'],'quality_analysis':'m42_c82_quality_2026-09-13.json','limits':['One observation per context/state; ratios have no repeatability interval or isolated causal attribution.','Quality pilot has five paired tasks per axis, not equivalence certification.','Capacity retrieval co-scores are not authoritative effective-context quality curves.','Numeric 48GB scorecard flags do not determine eligibility.','System pressure snapshots began during each arm; they are not matched prelaunch baselines.'],'default':'native16, operator-approved C81; no configuration switch during C82'}
(P/'capacity-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(rows,indent=2))
