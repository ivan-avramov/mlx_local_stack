"""C84 offline canonical grading; root SHA-pins finalized 20-request arm.

Reuses the immutable C82 NativeRunner sandbox (read-only samples, private
scratch, owned CID cleanup, ARM64 offline image). Prose receives integrity
records and a human-review document only; no correctness or quality score.
"""
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys
from pathlib import Path
import screen as s

def sandbox():
 path=s.OLD/'grade_pilot.py';s.require(s.sha(path)==s.OLD_GRADE_SHA,'reviewed sandbox helper changed')
 spec=importlib.util.spec_from_file_location('_c84_reviewed_c82_sandbox',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def completed(f,phase,mode,path,pin):
 s.require(Path(path).resolve()==s.HERE/f'finalized-{phase}-{mode}.json','wrong finalized artifact path')
 s.require(s.sha(s.regular(path))==pin,'root-reviewed finalization SHA differs');e=s.read(path);a=f['arms'][mode]
 s.require(e.get('status')=='complete' and e.get('phase')==phase and e.get('mode')==mode and e.get('model')==a['model'] and e.get('completed')==20,'finalization identity/count differs')
 s.require(e.get('frozen_sha256')==s.sha(s.HERE/f'frozen-{phase}.json') and e.get('source')==f['source'] and e.get('registry_sha256')==f['registry_sha256'],'finalization source/registry differs')
 expected=set()
 for p in a['results'].values():expected.update((str(Path(p)),str(Path(p).with_suffix('.manifest.json'))))
 for i in range(1,21):
  for name in ('request.json','response.json','row.json'):expected.add(str(s.HERE/'runs'/phase/mode/f'request-{i:02d}'/name))
 s.require(set(e.get('files',{}))==expected,'finalization file inventory differs')
 for p,h in e['files'].items():s.require(s.sha(s.regular(p))==h,'finalized data changed')
 s.manifest_check(a,f);return e

def offline_eval(original,axis,model,*,image,runner,corpus_ids,**kwargs):
 s.require(axis in ('humanevalplus','mbppplus') and axis in corpus_ids,'missing frozen executable corpus')
 return original(axis,model,image=image,runner=runner,all_ids=corpus_ids[axis],**kwargs)

def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['before','after'],required=True);p.add_argument('--mode',choices=s.MODELS,required=True);p.add_argument('--frozen-sha',required=True);p.add_argument('--run-evidence',required=True);p.add_argument('--run-evidence-sha256',required=True);a=p.parse_args()
 frozenpath=s.HERE/f'frozen-{a.phase}.json';s.require(s.sha(frozenpath)==a.frozen_sha,'frozen SHA differs');f=s.read(frozenpath)
 s.verify(f,check_source=False);arm=f['arms'][a.mode];e=completed(f,a.phase,a.mode,a.run_evidence,a.run_evidence_sha256)
 g=sandbox();dest=s.HERE/'grades'/a.phase/a.mode;s.require(not dest.exists() and dest.resolve().is_relative_to(s.HERE/'grades'),'existing/escaped grade directory')
 inputs=[Path(p) for p in e['files']];protected=g.immutable_hashes([*inputs,frozenpath,Path(a.run_evidence),s.REGISTRY])
 expected={b:{i['id']:i['seed'] for i in arm['requests'] if i['bench']==b} for b in s.BENCHES}
 for axis,p in arm['results'].items():g.validate_rows([json.loads(x) for x in Path(p).read_text().splitlines() if x],expected[axis])
 proc=subprocess.run(['docker','image','inspect',g.IMAGE],capture_output=True,text=True,timeout=30,check=True);meta=json.loads(proc.stdout)[0]
 s.require(meta['Id']==g.IMAGE and meta['Architecture']=='arm64','approved offline image identity differs')
 modeldir=dest/arm['model'];modeldir.mkdir(parents=True)
 for p in arm['results'].values():
  for src in (Path(p),Path(p).with_suffix('.manifest.json')):
   shutil.copy2(src,modeldir/src.name);protected[modeldir/src.name]=s.sha(src)
 os.environ.update(MLX_BENCH_RESULTS=str(dest),MLX_SERVE_CONFIG=str(s.REGISTRY),HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TMPDIR=str(s.HERE/'tmp'),NLTK_DATA=str(s.HERE/'tmp/nltk'))
 from bench import grade,generate
 s.require(generate.results_root().resolve()==dest,'canonical grader output escaped')
 math=g.validate_math_dependencies(grade._math_eq);native=g.NativeRunner(modeldir,immutable_files=protected);original=grade.grade_evalplus
 def checked(b,model,**kw):
  s.require(model==arm['model'] and b in ('humanevalplus','mbppplus'),'unapproved executable grading scope')
  g.verify_immutable(protected);score=offline_eval(original,b,model,image=g.IMAGE,runner=native,corpus_ids=f['corpus_ids'],**kw);g.verify_immutable(protected)
  g.validate_evaluator(modeldir/f"{b}.{arm['tag']}_samples_eval_results.json",expected[b]);g.validate_score(score,expected[b]);return score
 grade.grade_evalplus=checked
 try:
  scores=grade.grade_all([arm['model']],list(s.BENCHES[:3]),tune=arm['tag'])
  for score in scores:g.validate_score(score,expected[score['benchmark']])
  prose=[json.loads(x) for x in Path(arm['results']['cjudge']).read_text().splitlines() if x]
  review=[];markdown=['# C84 prose review — human/source judgement pending','',f"Model: {arm['model']}; phase: {a.phase}",'','Integrity, output length and convergence are not prose quality scores.']
  for r in prose:
   item=next(i for i in arm['items']['cjudge'] if i['id']==r['id']);body=r.get('content') or ''
   review.append({'id':r['id'],'converged':r['converged'],'nonconv_kind':r.get('nonconv_kind'),'completion_tokens':r['completion_tokens'],'content_nonempty':bool(body.strip()),'content_sha256':hashlib.sha256(body.encode()).hexdigest(),'quality_score':None,'human_review':'pending'})
   markdown+=['',f"## {r['id']}",'','Prompt:',item['prompt'],'','Response:',body,'','Review factual support, instruction compliance, completeness, coherence and limitations. Compare paired before/after bodies after both phases; record a reasoned judgement.']
  g.verify_immutable(protected)
  s.save(dest/'complete-scores.json',scores);s.save(dest/'prose-integrity.json',review)
  with (dest/'prose-review.md').open('x') as out:out.write('\n'.join(markdown)+'\n')
  s.save(dest/'grading-provenance.json',{'decision':'C84','phase':a.phase,'mode':a.mode,'status':'mechanical_grading_complete_prose_review_pending','run_evidence_sha256':a.run_evidence_sha256,'image':g.IMAGE,'platform':'linux/arm64','network':'none','containers':native.calls,'math_grading':math,'sandbox_helper_sha256':s.OLD_GRADE_SHA,'frozen_sha256':a.frozen_sha,'canonical_grader_sha256':s.sha(grade.__file__),'limits':f['limits']})
  print(json.dumps([{'benchmark':x['benchmark'],'n':x['n'],'acc':x['acc'],'acc_strict':x['acc_strict'],'conv_rate':x['conv_rate']} for x in scores]))
 finally:grade.grade_evalplus=original
if __name__=='__main__':main()
