"""Private C82 adapter: canonical scorers with pinned offline ARM64 execution.

Real grading requires root-reviewed --run-evidence and --run-evidence-sha256.
Evidence JSON schema v1: decision="C82", status="complete", model=MODEL,
mode="native16"|"uniform8", tune, source_root (absolute fixed real results root),
selection_sha256, overlay_sha256, source_shas (SOURCE_HEADS mapping),
serving_path (same source keys -> 64-hex fingerprints), versions
({"mlx":"0.32.2","mlx-metal":"0.32.2"}), sampling (full deployed dict),
kv (kv_bits, kv_quant_scheme, kv_group_size, quantized_kv_start, prefill_step_size,
max_kv_cache_size, kv_prealloc_tokens), runtime={"draft_kind":"mtp"},
files (exact six row/manifest basenames -> SHA256). The root finalizer asserts
completion and runtime provenance; this adapter checks that pinned contract
against every input. Evidence is never mounted into an evaluator container.
Only --control with the fixed selftest input root may omit this evidence.
Both states require root-observed kv_group_size=64 in completion evidence.
Canonical manifests currently omit that field; check it if present, otherwise
retain its independent provenance. Native16 uses bits=0/scheme=turboquant
(disabled); uniform8 uses bits=8/scheme=uniform. No scoring rules change.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
IMAGE='sha256:ff0ea20905962ccef0bcfc07f4ae0d389acdbafd4736c0b33eb51d350f048b43'
MODEL='Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
AXES=('math500','humanevalplus','mbppplus')
SELECTION_SHA='02b30efc7bd6d3fd94628a53a5e1f69d7255ee5fa3e4d86060790fc00f4a39e7'
TUNES={'m42c82-native16-20260913':'native16','m42c82-uniform8-20260913':'uniform8'}
SOURCE_HEADS={'src/mlx-vlm':'c5a6f97bb918d4aa90b9d501b573721d34ab76e0',
              'src/mlx-serve':'f8f1df4952b2baf15f3504159f2869e170795fb2'}
MATH_VERSIONS={'math-verify':'0.9.0','latex2sympy2_extended':'1.11.0','sympy':'1.14.0'}


class GradingError(RuntimeError):
    pass


def require(condition,message):
    if not condition:raise GradingError(message)


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular_file(path,parent=None):
    path=Path(path)
    require(not path.is_symlink() and path.is_file(),'missing or symlinked input/output: '+path.name)
    if parent is not None:
        require(path.parent.resolve()==Path(parent).resolve(),'file escapes expected directory')
    return path


def input_files(source,tune):
    modeldir=Path(source)/MODEL
    require(not modeldir.is_symlink() and modeldir.resolve().parent==Path(source).resolve(),'model directory escapes source root')
    paths=[]
    for bench in AXES:
        rows=modeldir/f'{bench}.{tune}.jsonl'
        paths.extend([regular_file(rows,modeldir),regular_file(rows.with_suffix('.manifest.json'),modeldir)])
    return paths


def immutable_hashes(paths):
    return {Path(p):sha(regular_file(p)) for p in paths}


def verify_immutable(expected):
    for path,digest in expected.items():
        require(sha(regular_file(path))==digest,'immutable grading input changed: '+path.name)


def validate_math_dependencies(math_eq,version=importlib.metadata.version):
    try:installed={name:version(name) for name in MATH_VERSIONS}
    except importlib.metadata.PackageNotFoundError as exc:raise GradingError('missing math grading dependency') from exc
    require(installed==MATH_VERSIONS,'math grading dependency versions changed')
    # The canonical normalized-string fallback cannot make these equal.
    require(math_eq(r'\frac{1}{2}','0.5') is True,'canonical symbolic math known-positive failed')
    return {'versions':installed,'symbolic_equivalence':True,'probe':[r'\frac{1}{2}','0.5']}


def validate_run_evidence(path,pin,source,tune,overlay,inputs,sampling):
    require(path is not None and isinstance(pin,str) and re.fullmatch('[0-9a-f]{64}',pin),'root completion evidence and SHA256 required')
    path=regular_file(path)
    require(sha(path)==pin,'root completion evidence SHA256 differs')
    require(tune in TUNES,'unapproved tune')
    e=json.loads(path.read_text());mode=TUNES[tune]
    require(e.get('schema_version')==1 and e.get('decision')=='C82' and e.get('status')=='complete','run is not independently finalized complete')
    require(e.get('model')==MODEL and e.get('mode')==mode and e.get('tune')==tune,'finalized run identity differs')
    require(e.get('source_root')==str(Path(source).resolve()),'finalized input root differs')
    require(e.get('selection_sha256')==SELECTION_SHA and e.get('overlay_sha256')==sha(overlay),'finalized selection/overlay differs')
    require(e.get('source_shas')==SOURCE_HEADS,'finalized serving commits differ')
    require(e.get('versions')=={'mlx':'0.32.2','mlx-metal':'0.32.2'},'finalized runtime versions differ')
    serving=e.get('serving_path',{})
    require(set(serving)==set(SOURCE_HEADS) and all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in serving.values()),'invalid finalized serving fingerprints')
    kv={'kv_bits':8 if mode=='uniform8' else 0,'kv_quant_scheme':'uniform' if mode=='uniform8' else 'turboquant',
        'kv_group_size':64,'quantized_kv_start':0,'prefill_step_size':512,'max_kv_cache_size':262144,'kv_prealloc_tokens':262144}
    require(e.get('sampling')==sampling and e.get('kv')==kv and e.get('runtime')=={'draft_kind':'mtp'},'finalized sampling/cache/predictor contract differs')
    require(e.get('files')=={p.name:sha(regular_file(p)) for p in inputs},'finalized row/manifest hashes differ')
    for path in inputs:
        if not path.name.endswith('.manifest.json'):continue
        m=json.loads(path.read_text())
        require(m.get('model')==MODEL and m.get('tune')==tune and m.get('sampling_profile')=='deployed','manifest identity/profile differs')
        require(m.get('sampling')==sampling and all(m.get('kv',{}).get(k)==v for k,v in kv.items() if k!='kv_group_size'),'manifest sampling/cache contract differs')
        require('kv_group_size' not in m.get('kv',{}) or m['kv']['kv_group_size']==64,'manifest KV group size differs')
        require(m.get('runtime',{}).get('draft_kind')=='mtp','manifest predictor differs')
        require(m.get('git',{}).get('submodules')==SOURCE_HEADS and m.get('git',{}).get('serving_path')==serving,'manifest source provenance differs')
        require(m.get('registry',{}).get('sha256')==e['overlay_sha256'],'manifest registry differs')
    return e


def native_command(command,directory,output,cidfile,name):
    c=list(command);directory=Path(directory).resolve()
    require(c[:4]==['docker','run','--rm','--name'],'unexpected Docker command')
    require(len(c)==15 and c[5:8]==['--platform','linux/amd64','-v'],'unexpected Docker arguments')
    require(c[8]==f'{directory}:/work' and c[9]==IMAGE,'mount/image differs from approved grading job')
    require(c[10:12]==['evalplus.evaluate','--dataset'] and c[12] in ('humaneval','mbpp'),'unexpected evaluator/dataset')
    require(c[13]=='--samples','unexpected evaluator command')
    require(re.fullmatch(r'evalplus-[a-zA-Z0-9_.-]+',c[4]) is not None,'invalid container name')
    require(c[14].startswith('/work/') and Path(c[14]).name==c[14][6:] and c[14].endswith('_samples.jsonl'),'invalid sample path')
    sample=regular_file(directory/Path(c[14]).name,directory)
    return ['docker','run','--rm','--pull','never','--name',name,'--cidfile',str(cidfile),
            '--platform','linux/arm64','--network','none','--cap-drop','ALL',
            '--security-opt','no-new-privileges','-v',f'{output}:/work:rw',
            '-v',f'{sample}:/work/{sample.name}:ro',IMAGE,'python','-m',
            'evalplus.evaluate',*c[11:],'--parallel','2']


def validate_evaluator(path,expected):
    ev=json.loads(Path(path).read_text()).get('eval',{})
    require(isinstance(ev,dict),'invalid evaluator record')
    for item in expected:
        entries=ev.get(item)
        require(isinstance(entries,list) and len(entries)==1,'missing/duplicate evaluator draw: '+item)
        for field in ('base_status','plus_status'):
            require(entries[0].get(field) in ('pass','fail','timeout'),'incomplete evaluator status: '+item+'/'+field)
        require(entries[0]['base_status']=='pass' or entries[0]['plus_status']!='pass',
                'base-fail/plus-pass exposes canonical scorer disagreement; needs separate review')


def validate_rows(rows,expected):
    require(len(rows)==len(expected),'wrong row count')
    keys=[(r.get('id'),r.get('sample')) for r in rows]
    require(set(keys)=={(i,0) for i in expected} and len(set(keys))==len(keys),'missing/duplicate row identity')
    for r in rows:
        require(not r.get('error') and not r.get('contaminated') and not r.get('recovery'),'infrastructure/recovery row cannot be graded')
        require(r.get('sampler_seed')==expected[r['id']],'sampler seed differs')


def validate_score(score,expected):
    require(score.get('n')==len(expected) and score.get('acc') is not None,'missing/partial grade')
    require(not score.get('timed_out') and not score.get('errors') and not score.get('skipped'),'degraded grade')
    keys=[(r.get('id'),r.get('sample',0)) for r in score.get('items',[])]
    require(set(keys)=={(i,0) for i in expected} and len(keys)==len(expected),'incomplete scored identities')


class NativeRunner:
    def __init__(self,directory,run=subprocess.run,immutable_files=()):
        self.directory=Path(directory).resolve();self.run=run;self.calls=[];self.jobs={}
        self.immutable=immutable_hashes(immutable_files)

    def cleanup(self,job):
        if job.get('cleaned'):return
        cidpath=job['cidfile']
        if not cidpath.exists():return
        cid=regular_file(cidpath,cidpath.parent).read_text().strip()
        require(re.fullmatch('[0-9a-f]{64}',cid) is not None,'invalid owned container ID')
        require(job.get('cid') in (None,cid),'owned container ID changed')
        job['cid']=cid;job['cleaned']=True
        self.run(['docker','kill',cid],capture_output=True,text=True,timeout=30)

    def __call__(self,command,**kwargs):
        # Canonical fallback cleanup is scoped to a previously owned container.
        if list(command[:2])==['docker','kill']:
            require(len(command)==3,'unexpected cleanup arguments')
            if command[2] in self.jobs:self.cleanup(self.jobs[command[2]])
            return subprocess.CompletedProcess(command,0,'no further owned container cleanup','')
        canonical_name=command[4] if len(command)>4 else ''
        require(canonical_name not in self.jobs,'duplicate grading job')
        name='c82-'+uuid.uuid4().hex
        jobroot=self.directory.parent/'evaluator-jobs'/name
        require(jobroot.resolve()==jobroot,'evaluator scratch path contains symlink')
        output=jobroot/'output';control=jobroot/'control';output.mkdir(parents=True);control.mkdir()
        cidfile=control/'container.cid'
        c=native_command(command,self.directory,output,cidfile,name)
        sample=regular_file(self.directory/Path(command[-1]).name,self.directory)
        frozen={**self.immutable,**immutable_hashes([sample])};verify_immutable(frozen)
        records=[json.loads(line) for line in sample.read_text().splitlines() if line]
        ids=[r['task_id'] for r in records];require(len(ids)==len(set(ids)),'duplicate evaluator sample ID')
        resultname=sample.name.replace('.jsonl','_eval_results.json');target=self.directory/resultname
        require(not target.exists() and not target.is_symlink(),'refuse pre-existing evaluator result')
        job={'name':name,'cidfile':cidfile,'output':output,'cid':None,'cleaned':False}
        self.jobs[canonical_name]=job
        audit={'name':name,'cid':None,'samples_sha256':frozen[sample]};self.calls.append(audit)
        try:
            proc=self.run(c,**kwargs)
            (control/'stdout.log').write_text(proc.stdout or '')
            (control/'stderr.log').write_text(proc.stderr or '')
            require(proc.returncode==0,'nonzero evaluator exit; no valid grade')
            require(cidfile.exists(),'successful Docker call did not capture an owned CID')
            cid=regular_file(cidfile,control).read_text().strip()
            require(re.fullmatch('[0-9a-f]{64}',cid) is not None,'invalid owned container ID')
            job['cid']=audit['cid']=cid
            verify_immutable(frozen)
            result=regular_file(output/resultname,output)
            ev=json.loads(result.read_text()).get('eval',{})
            require(set(ev)==set(ids),'incomplete or extra evaluator task identities')
            validate_evaluator(result,ids)
            result_hash=sha(result)
            require(not target.exists() and not target.is_symlink(),'evaluator target appeared during execution')
            with target.open('xb') as f:f.write(result.read_bytes())
            require(sha(target)==result_hash,'copied evaluator result differs')
            audit['result_sha256']=result_hash
            return proc
        except BaseException as exc:
            self.cleanup(job)
            audit['cid']=job.get('cid')
            if isinstance(exc,subprocess.TimeoutExpired):
                raise GradingError('container execution timeout; no valid grade') from exc
            raise


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--source-root',required=True);ap.add_argument('--destination',required=True)
    ap.add_argument('--tune',required=True);ap.add_argument('--overlay',required=True);ap.add_argument('--control',action='store_true')
    ap.add_argument('--run-evidence');ap.add_argument('--run-evidence-sha256')
    a=ap.parse_args(argv)
    require(a.tune in (*TUNES,'c82-grader-selftest'),'unapproved tune')
    require(a.control==(a.tune=='c82-grader-selftest'),'control label mismatch')
    source=Path(a.source_root).resolve();dest=Path(a.destination).resolve();overlay=Path(a.overlay).resolve()
    allowed_source=HERE/'selftest-inputs' if a.control else ROOT/'stack-validation/benchmark/results'
    require(source==allowed_source and not Path(a.source_root).is_symlink(),'input root is not the fixed approved root')
    require(dest.is_relative_to(HERE/'grades'),'grading destination outside private experiment')
    require(source!=dest and not dest.exists(),'refuse existing grading destination')
    allowed_overlays=[HERE/f'{mode}.yaml' for mode in TUNES.values()] if a.control else [HERE/f'{TUNES[a.tune]}.yaml']
    require(overlay in allowed_overlays and overlay.is_file(),'invalid C82 overlay')
    selection=HERE/'selection.json';require(hashlib.sha256(selection.read_bytes()).hexdigest()==SELECTION_SHA,'selection changed')
    data=json.loads(selection.read_text());groups={g['axis']:g for g in data['groups']}
    expected={b:{i['id']:i['sampler_seed'] for i in groups[b]['items']} for b in AXES}
    for corpus in data['corpora'].values():
        path=Path(os.path.expandvars(corpus['path']))
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==corpus['sha256'],'corpus changed: '+path.name)
    inputs=input_files(source,a.tune)
    sampling=groups['math500']['historical_configuration']['sampling']
    require(all(groups[b]['historical_configuration']['sampling']==sampling for b in AXES),'selection sampling differs across axes')
    root_evidence=None
    if not a.control:
        require(a.run_evidence and Path(a.run_evidence).resolve().is_relative_to(HERE),'completion evidence must be in private control area')
        root_evidence=validate_run_evidence(a.run_evidence,a.run_evidence_sha256,source,a.tune,overlay,inputs,sampling)
    protected=immutable_hashes([*inputs,overlay,selection]+([Path(a.run_evidence)] if root_evidence else []))
    for b in AXES:
        rows_file=source/MODEL/f'{b}.{a.tune}.jsonl';manifest=rows_file.with_suffix('.manifest.json')
        require(rows_file.is_file() and manifest.is_file(),'missing row/manifest')
        rows=[json.loads(line) for line in rows_file.read_text().splitlines() if line]
        validate_rows(rows,expected[b]);man=json.loads(manifest.read_text())
        require(man.get('sampling',{}).get('max_tokens')==102400 and man.get('kv',{}).get('max_kv_cache_size')==262144,'budget provenance mismatch')
        require(man.get('sampling',{}).get('thinking_budget')==81920,'thinking budget changed')
        require(man.get('sampling',{}).get('enable_thinking') is True,'thinking disabled')
        if not a.control:
            require(man.get('runtime',{}).get('draft_kind')=='mtp','predictor state changed')
            require(man.get('kv',{}).get('kv_bits')==(8 if TUNES[a.tune]=='uniform8' else 0),'cache mode changed')
    proc=subprocess.run(['docker','image','inspect',IMAGE],capture_output=True,text=True,timeout=30,check=True)
    meta=json.loads(proc.stdout)[0];require(meta['Id']==IMAGE and meta['Architecture']=='arm64','native image identity mismatch')
    modeldir=dest/MODEL;modeldir.mkdir(parents=True)
    for path in inputs:shutil.copy2(path,modeldir/path.name)
    protected.update(immutable_hashes([modeldir/p.name for p in inputs]))
    os.environ['MLX_BENCH_RESULTS']=str(dest);os.environ['MLX_SERVE_CONFIG']=str(overlay)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1';os.environ['TMPDIR']=str(HERE/'tmp')
    sys.path.insert(0,str(ROOT/'stack-validation/benchmark'))
    from bench import grade,generate
    require(Path(grade.__file__).resolve()==ROOT/'stack-validation/benchmark/bench/grade.py','unexpected grader source')
    require(generate.results_root().resolve()==dest,'grader output root mismatch')
    math_evidence=validate_math_dependencies(grade._math_eq)
    native=NativeRunner(modeldir,immutable_files=protected);original=grade.grade_evalplus
    def checked_eval(b,model,**kwargs):
        verify_immutable(protected)
        score=original(b,model,image=IMAGE,runner=native,**kwargs)
        require(not score.get('timed_out'),'timeout-recovered evaluator result is not accepted')
        verify_immutable(protected)
        validate_evaluator(modeldir/f'{b}.{a.tune}_samples_eval_results.json',expected[b])
        validate_score(score,expected[b]);return score
    grade.grade_evalplus=checked_eval
    try:
        scores=grade.grade_all([MODEL],list(AXES),tune=a.tune)
        for score in scores:validate_score(score,expected[score['benchmark']])
        verify_immutable(protected)
        dump(dest/'complete-scores.json',scores)
        dump(dest/'grading-provenance.json',{'status':'complete','kind':'synthetic grader selftest' if a.control else 'C82 quality pilot',
             'image':IMAGE,'platform':'linux/arm64','network':'none','source_inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
             'selection_sha256':SELECTION_SHA,'grader_sha256':hashlib.sha256(Path(grade.__file__).read_bytes()).hexdigest(),'containers':native.calls,
             'math_grading':math_evidence,'run_evidence_sha256':a.run_evidence_sha256,'run_evidence':root_evidence})
        print(json.dumps([{'benchmark':s['benchmark'],'n':s['n'],'acc':s['acc'],'acc_strict':s['acc_strict'],'conv_rate':s['conv_rate']} for s in scores]))
    finally:grade.grade_evalplus=original


if __name__=='__main__':main()
