import os,json,pathlib,random,hashlib
import yaml
from bench import benchmarks
R=pathlib.Path(os.environ['STACK_REPO']); Q=pathlib.Path(os.environ['STACK_WORKDIR'])/'queue'; D=Q/'resolution';D.mkdir(exist_ok=True)
base='Qwen3.8-27B-mlx-uniform-4bit'; mixed='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
source=(Q/'c51_medium/run.py').read_text()
for name,model,drafter in [('positive',base,Q.parent/'scratch/m6a'/f'{base}-mtp-drafter'),('original',mixed,Q.parent/'scratch/m6a'/f'{mixed}-mtp-drafter'),('corrected',mixed,Q/'mtp_recovery'/f'{mixed}-mtp-normfix')]:
 job=D/name;job.mkdir(exist_ok=True)
 s=source.replace("JOB=Path(os.environ['STACK_WORKDIR'])/'queue/c51_medium'",f"JOB=Path(os.environ['STACK_WORKDIR'])/'queue/resolution/{name}'")
 s=s.replace("MODEL='Qwen3.8-27B-mlx-uniform-4bit'",'MODEL='+repr(model))
 s=s.replace("draft_model=str(Path(os.environ['STACK_WORKDIR'])/'scratch/m6a'/f'{MODEL}-mtp-drafter')",'draft_model='+repr(str(drafter)))
 (job/'run.py').write_text(s)
sets={}
for bench in ['humanevalplus','mbppplus','math500']:
 ids=[r['id'] for r in benchmarks.load(bench,limit=None)]
 chosen=random.Random(5909).sample(sorted(ids),min(100,len(ids)))
 pilot=random.Random(5910).sample(chosen,5)
 sets[bench]={'ids':chosen,'pilot':pilot}
(D/'ids.json').write_text(json.dumps(sets,indent=2))
freeze={p:hashlib.sha256((R/p).read_bytes()).hexdigest() for p in ['benchmark/aider_bench.model.settings.yml','benchmark/opencode_bench.json']}
(D/'carrier_before.json').write_text(json.dumps(freeze,indent=2))
helper=(Q/'queue_m34a_full.py').read_text().split('\ndef main():')[0]
helper=helper.replace("LOG=open(f\"{OUT}/m34a_full.log\",'a',buffering=1)","LOG=open(f\"{OUT}/resolution.log\",'a',buffering=1)")
(D/'helpers.py').write_text(helper)
print('prepared probe scripts, seeded corpus samples, carrier snapshots and helper snapshot')
