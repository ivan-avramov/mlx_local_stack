"""Root offline validation/export for one completed C82 capacity ladder."""
from pathlib import Path
import sys,json,hashlib,math,yaml
P=Path(__file__).resolve().parent;R=P.parent;STACK=Path('$STACK_REPO')
MODEL='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed';mode=sys.argv[1];assert mode in ('native16','uniform8')
tag=f'm42c82cap-{mode}-20260913';run=R/'capacity'/tag/MODEL;src=R/'stack-validation/benchmark/results'/MODEL
sys.path.insert(0,str(R/'stack-validation/benchmark'))
from bench.retrieval import build_context,make_question,score
from bench.scorecard import capacity_retrieval_scorecard
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((run/'summary.json').read_text());assert summary['status']=='complete' and summary.get('error') is None
records=[json.loads(l) for l in (src/f'capacity_ladder.{tag}.jsonl').read_text().splitlines()]
assert [r['ctx'] for r in records]==[131072,196608,262144]
assert [r['prompt_tokens'] for r in records]==[130783,196115,261449]
assert summary['records']==records
cal=json.loads((run/'calibration.json').read_text());assert cal['validated'] and cal['prompt_tokens']==3210 and cal['filler_sha256']=='739c49f19cb5c7c403de43ad0effcd5ec3f2b76af72972aca97c199a4dfa2c72'
cal_req=json.loads((run/'request-01.json').read_text());cal_res=json.loads((run/'response-01.json').read_text())
filler='The quick brown fox jumps over the lazy dog near the riverbank at sunset. '*200
assert cal_req=={'model':MODEL,'messages':[{'role':'user','content':filler}],'params':{'max_tokens':1,'temperature':0.0},'timeout':120,'tools':None}
assert cal_res['prompt_tokens']==cal['prompt_tokens'] and len(filler)==cal['calibration_chars']
assert cal['chars_per_token']==len(filler)/cal['prompt_tokens']
before=json.loads((run/'prelaunch-evidence.json').read_text());after=json.loads((run/'postrun-evidence.json').read_text());assert before==after
assert before['supervisor_sources']['capacity_runner']==sha(P/'capacity_runner.py')
assert before['supervisor_sources']['capacity_child']==sha(P/'capacity_child.py')
manifest=json.loads((src/f'capacity_ladder.{tag}.manifest.json').read_text());overlay=P/(mode+'.yaml')
assert manifest['registry']['sha256']==sha(overlay) and manifest['git']['serving_path']==before['source']['serving_path']
assert manifest['kv']['kv_bits']==(8 if mode=='uniform8' else 0)
assert manifest['kv']['kv_quant_scheme']==('uniform' if mode=='uniform8' else 'turboquant')
assert manifest['runtime']['draft_kind']=='mtp'
approved={'src/mlx-vlm':'c5a6f97bb918d4aa90b9d501b573721d34ab76e0','src/mlx-serve':'f8f1df4952b2baf15f3504159f2869e170795fb2'}
assert manifest['git']['submodules']==before['source']['submodules']==approved
entry=next(e for e in yaml.safe_load(overlay.read_text())['models'] if e['name']==MODEL)
assert manifest['model']==MODEL and manifest['sampling_profile']=='deployed'
assert manifest['sampling']=={**entry['generation_defaults'],'max_tokens':256,'thinking_budget':256}
assert manifest['sampling']['max_tokens']==256 and manifest['sampling']['thinking_budget']==256
assert manifest['kv']['max_kv_cache_size']==manifest['kv']['kv_prealloc_tokens']==262144
assert len(list(run.glob('request-*.json')))==len(list(run.glob('response-*.json')))==4
for i,row in enumerate(records,2):
 response=json.loads((run/f'response-{i:02d}.json').read_text())
 assert not row.get('error') and type(row['server_peak_gb']) in (int,float) and math.isfinite(row['server_peak_gb'])
 assert row['server_peak_gb']==response['peak_mem_gb'] and row['prefill_s']==response['prefill_s'] and row['decode_tps']==response['decode_tps']
 assert response['raw_timings']['cache_n']==0
 assert response['raw_timings']['prompt_n']==row['prompt_tokens']
 assert response['prompt_tokens']==row['prompt_tokens'] and response['prefill_tps']==row['prefill_tps']
 context,needles=build_context(row['ctx'],cal['chars_per_token'])
 assert row['retrieval_acc']==score(response.get('content',''),needles)
 assert row['draft']['draft_kind']=='mtp' and row['draft']['draft_n']>0
 for key in row['draft']:assert row['draft'][key]==response['raw_timings'][key]
 h=json.loads((run/f'request-{i:02d}.json').read_text());assert h['model']==MODEL and h['params']==manifest['sampling']
 assert h['messages']==[{'role':'user','content':context+'\n\n'+make_question(needles)}]
 assert h['timeout']==7200 and h['tools'] is None
 assert row['acceptance']==round(row['draft']['draft_n_accepted']/row['draft']['draft_n'],4)
heart=[json.loads(l) for l in (run/'heartbeat.jsonl').read_text().splitlines()]
assert heart[-1]['rungs_completed']==3 and heart[-1].get('error') is None
scorecard=json.loads((src/f'capacity_retrieval.{tag}.json').read_text())
expected_scorecard=capacity_retrieval_scorecard(MODEL,records,gate_gb=48)
expected_scorecard['idle_baseline_gb']=manifest['runtime']['idle_baseline_gb']
assert scorecard==expected_scorecard
assert heart[0]['event']=='SELFTEST' and heart[0]['passed'] and heart[-1]['event']=='RUNNER-EXIT' and heart[-1]['status']=='complete'
files=[src/f'capacity_ladder.{tag}.jsonl',src/f'capacity_ladder.{tag}.manifest.json',src/f'capacity_retrieval.{tag}.json']
evidence={'decision':'C82','status':'complete','mode':mode,'model':MODEL,'tag':tag,'records':records,'summary':summary,'calibration':cal,'prelaunch':before,
 'files_sha256_before_redaction':{f.name:sha(f) for f in files},'raw_requests':{f.name:sha(f) for f in run.glob('request-*.json')},'raw_responses':{f.name:sha(f) for f in run.glob('response-*.json')},
 'instrument_hashes':{n:sha(P/n) for n in ['capacity_runner.py','capacity_child.py']},
 'memory_policy':'C79 rough target around48GB. Raw fits/scorecard/within_rough_48gb booleans are numeric comparisons with48, not eligibility or stopping rules. A small overrun does not disqualify.',
 'postrun_attestation':'producer rechecked live stability then serialized the original prelaunch evidence, not an independent second snapshot',
 'scorecard_interpretation':'Raw scorecard max_fitting_ctx and retrieval_effective_ctx are conditioned on the numeric memory threshold. They do not establish a retrieval failure or an authoritative effective-context curve; consult per-rung retrieval_acc and dedicated quality ladders.',
 'measurement_scope':'one bounded256-token generation per long-prompt rung; retrieval co-signal is not quality certification; seed inherited implicit server default0',
 'system_observations':[json.loads(l) for l in (P/f'memory-observations-{mode}.jsonl').read_text().splitlines()]}
def redact(s):
 for a,b in [(str(STACK.parent/'mlx_local_stack_workdir'),'$STACK_WORKDIR'),(str(STACK),'$STACK_REPO'),(str(Path.home()),'$HOME')]:s=s.replace(a,b)
 return s
out=STACK/'benchmark/results'/MODEL
for f in files:
 dest=out/f.name;assert not dest.exists();dest.write_text(redact(f.read_text()))
dest=out/f'capacity_retrieval.{tag}.provenance.json';assert not dest.exists();dest.write_text(redact(json.dumps(evidence,indent=2)+'\n'))
(P/f'finalized-capacity-{mode}.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({'mode':mode,'status':'complete','peaks':[r['server_peak_gb'] for r in records],'prefill_s':[r['prefill_s'] for r in records],'decode_tps':[r['decode_tps'] for r in records]}))
