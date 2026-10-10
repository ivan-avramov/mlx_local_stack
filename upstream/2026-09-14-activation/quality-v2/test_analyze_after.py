"""Filesystem fixtures only: copied baseline bytes stand in for synthetic AFTER.
No actual AFTER result is produced, graded, or claimed by these tests.
"""
import copy,json,shutil
from pathlib import Path
import pytest
import screen,analyze


def put(p,data,raw=False):
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(data if raw else json.dumps(data))
 return analyze.digest(p)


def fake_after(root):
 f=copy.deepcopy(json.loads((screen.HERE/'prepared.json').read_text()))
 f['source']={'submodules':{'src/mlx-vlm':'6822db17970d00d9938c48d82c66a565af3907be','src/mlx-serve':'b632280709f771972bffbaf3231e996e8a89f4e8'},'serving_path':{'src/mlx-vlm':'a'*64,'src/mlx-serve':'b'*64}}
 f['instrument_hashes']={}
 for mode,arm in f['arms'].items():arm['results']={b:str(root/'results/after'/arm['model']/f"{b}.{arm['tag']}.jsonl") for b in screen.BENCHES}
 pin=put(root/'frozen-after.json',f)
 before=json.loads((screen.BASELINE/'frozen-before.json').read_text())
 for mode,arm in f['arms'].items():
  old=before['arms'][mode];oldrun=screen.BASELINE/'runs/before'/mode;newrun=root/'runs/after'/mode;gd=root/'grades/after'/mode;oldgrade=screen.BASELINE/'grades/before'/mode;files={}
  for i in range(1,21):
   for name in ('request.json','response.json','row.json'):
    p=newrun/f'request-{i:02d}'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((oldrun/f'request-{i:02d}'/name).read_bytes());files[str(p)]=analyze.digest(p)
  for b,raw in arm['results'].items():
   p=Path(raw);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(Path(old['results'][b]).read_bytes());files[str(p)]=analyze.digest(p)
   m=json.loads(Path(old['results'][b]).with_suffix('.manifest.json').read_text());m['tune']=arm['tag'];m['git'].update(f['source']);m['registry']['sha256']=f['registry_sha256'];m['kv']['cache_session_shrink']=arm['entry'].get('cache_session_shrink')
   mp=p.with_suffix('.manifest.json');files[str(mp)]=put(mp,m)
   for source in (p,mp):target=gd/arm['model']/source.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
  for b in ('humanevalplus','mbppplus'):
   for suffix in ('_samples.jsonl','_samples_eval_results.json'):
    target=gd/arm['model']/f"{b}.{arm['tag']}{suffix}";target.write_bytes((oldgrade/arm['model']/f"{b}.{old['tag']}{suffix}").read_bytes())
  scores=json.loads((oldgrade/'complete-scores.json').read_text())
  for score in scores:score['tune']=arm['tag']
  put(gd/'complete-scores.json',scores)
  final={'decision':'C84','status':'complete','phase':'after','mode':mode,'model':arm['model'],'tag':arm['tag'],'completed':20,'frozen_sha256':pin,'source':f['source'],'registry_sha256':f['registry_sha256'],'files':files}
  finalpin=put(root/f'finalized-after-{mode}.json',final)
  gp=json.loads((oldgrade/'grading-provenance.json').read_text());gp.update(phase='after',frozen_sha256=pin,run_evidence_sha256=finalpin,limits=f['limits']);put(gd/'grading-provenance.json',gp)
  put(newrun/'summary.json',{'status':'complete','completed':20,'frozen_sha256':pin})
 return pin


@pytest.fixture(autouse=True)
def fake_symbolic_grader(monkeypatch):
 values={}
 for mode in screen.MODELS:
  for score in json.loads((screen.BASELINE/'grades/before'/mode/'complete-scores.json').read_text()):
   if score['benchmark']=='math500':
    for i in score['items']:values[(i['pred'],i['gold'])]=i['ok']
 values[(r'\frac{1}{2}','0.5')]=True
 monkeypatch.setattr(analyze,'math_eq',lambda a,b:values[(a,b)])


def test_retrospective_bundle_analysis_uses_original_archives(tmp_path):
 before_hash=analyze.digest(screen.BASELINE/'frozen-before.json');pin=fake_after(tmp_path)
 report,review=analyze.analyze(tmp_path,screen.BEFORE_PIN,pin)
 assert report['requests']==80 and report['treatment']==screen.TREATMENT
 assert report['registry_sha256']['before']!=report['registry_sha256']['after']
 assert report['retirement_policy']['native16']['after'] is True and report['retirement_policy']['tq4']['after']=='unconfigured'
 assert before_hash==analyze.digest(screen.BASELINE/'frozen-before.json')
 for model in report['models'].values():
  for axis in model['axes'].values():assert axis['n_pairs']==5 and axis['ratios']['wall_s']['point']==1
 assert review.count('Verdict/reason: PENDING')==10
 assert any('historical-code/provenance.py' in p for p in report['audited_inputs'])

@pytest.mark.parametrize('change',['runtime','retirement','sampling','module','request'])
def test_amended_analyzer_rejects_extra_treatment(tmp_path,change):
 pin=fake_after(tmp_path);p=tmp_path/'frozen-after.json';f=json.loads(p.read_text())
 if change=='runtime':f['runtime']['versions']['mlx']='0.99'
 elif change=='retirement':f['arms']['tq4']['entry']['cache_session_shrink']=True
 elif change=='sampling':f['arms']['native16']['params']['temperature']=.9
 elif change=='module':f['module_hashes'][str(screen.STACK/'benchmark/bench/extract.py')]='other'
 else:f['arms']['native16']['requests'][0]['wire']='different'
 pin=put(p,f)
 with pytest.raises(analyze.AuditError):analyze.analyze(tmp_path,screen.BEFORE_PIN,pin)
