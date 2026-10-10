import importlib.util
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('c82capacity',HERE/'capacity_child.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_above_guideline_continues_all_three_rungs():
 calls=[]
 def original(*args,**kw):
  calls.append(kw['grid'][0]);return [{'ctx':kw['grid'][0],'server_peak_gb':49.0,'fits':False}]
 assert len(m.run_all_rungs(original,grid=m.GRID,gate_gb=48))==3
 assert calls==list(m.GRID)
def test_invalid_grid_rejected_before_call():
 def original(*args,**kw):raise AssertionError('must not call')
 with pytest.raises(m.C82Error):m.run_all_rungs(original,grid=(131072,),gate_gb=48)
def test_error_aborts_before_next_request():
 calls=[]
 def original(*args,**kw):calls.append(kw['grid'][0]);return [{'ctx':kw['grid'][0],'error':'HTTP failure'}]
 with pytest.raises(m.C82Error):m.run_all_rungs(original,grid=m.GRID,gate_gb=48)
 assert calls==[131072]
def test_wrong_output_rung_rejected():
 with pytest.raises(m.C82Error):m.run_all_rungs(lambda *a,**kw:[{'ctx':1}],grid=m.GRID,gate_gb=48)

def test_fifth_request_rejected_before_delegate(tmp_path):
 class Delegate:
  def complete(self,*a,**kw):raise AssertionError('extra request')
 guard=m.CalibrationGuardDriver(Delegate(),tmp_path/'calibration.json',10);guard.requests=4
 with pytest.raises(m.C82Error):guard.complete('model',[],{})
def test_transport_escapes_ordinary_exception_handler(tmp_path):
 class Delegate:
  def complete(self,*a,**kw):raise TimeoutError('fake')
 guard=m.CalibrationGuardDriver(Delegate(),tmp_path/'calibration.json',10);guard.requests=1
 with pytest.raises(m.C82Error):guard.complete('model',[],{},timeout=7200)
 assert not issubclass(m.C82Error,Exception)
def test_wrong_prompt_occupancy_aborts(tmp_path):
 class Delegate:
  def complete(self,*a,**kw):return {'prompt_tokens':1}
 guard=m.CalibrationGuardDriver(Delegate(),tmp_path/'calibration.json',10);guard.requests=1
 with pytest.raises(m.C82Error):guard.complete('model',[],{},timeout=7200)
def test_three_high_peak_rows_complete_without_gate_rejection():
 spec=importlib.util.spec_from_file_location('c82supervisor',HERE/'capacity_runner.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
 rows=[{'ctx':ctx,'server_peak_gb':49,'fits':False,'prompt_tokens':tok} for ctx,tok in zip(m.GRID,(130783,196115,261449))]
 result=r.classify_records(rows)
 assert result['status']=='complete' and result['nominal_gate_262144'] is None
 assert result['within_rough_48gb'] is False

@pytest.mark.parametrize('peak',[None,float('nan'),float('inf'),-1,True])
def test_invalid_peak_stops_before_next_rung(peak):
 calls=[]
 def original(*a,**kw):calls.append(kw['grid'][0]);return [{'ctx':kw['grid'][0],'server_peak_gb':peak}]
 with pytest.raises(m.C82Error):m.run_all_rungs(original,grid=m.GRID,gate_gb=48)
 assert calls==[131072]
def test_changed_calibration_occupancy_rejected(tmp_path):
 class Delegate:
  def complete(self,*a,**kw):return {'prompt_tokens':3209}
 filler='The quick brown fox jumps over the lazy dog near the riverbank at sunset. '*200
 g=m.CalibrationGuardDriver(Delegate(),tmp_path/'calibration.json',len(filler))
 with pytest.raises((m.CalibrationError,m.C82Error)):g.complete('model',[{'role':'user','content':filler}],{'max_tokens':1,'temperature':0.0},timeout=120)
def test_changed_calibration_filler_rejected_before_request(tmp_path):
 class Delegate:
  def complete(self,*a,**kw):raise AssertionError('changed prompt must not send')
 g=m.CalibrationGuardDriver(Delegate(),tmp_path/'calibration.json',14800)
 with pytest.raises((m.CalibrationError,m.C82Error)):g.complete('model',[{'role':'user','content':'x'*14800}],{'max_tokens':1,'temperature':0.0},timeout=120)

@pytest.mark.parametrize('key',['KV_KEY_BITS','KV_VALUE_BITS','KV_KEY_SCHEME','KV_VALUE_SCHEME'])
def test_split_override_rejected_by_live_worker_guard(key):
 spec=importlib.util.spec_from_file_location('c82supervisor',HERE/'capacity_runner.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
 with pytest.raises(r.InstrumentError,match='split KV'):
  r.validate_worker({'environment':{key:'4'},'command':[]},{},Path('/unused'),Path('/unused'))

@pytest.mark.parametrize('extra',[['--kv-key-bit=4'],['--kv-value-bit','4'],['--kv-key-schem=uniform'],['--kv-value-scheme','turboquant'],['--kv-group-size','32'],['--kv-group-size=32'],['--kv-quant-sch=turboquant'],['--kv-quant-scheme=turboquant']])
def test_full_valid_worker_rejects_override_spellings(extra):
 import json,yaml,copy
 spec=importlib.util.spec_from_file_location('c82supervisor',HERE/'capacity_runner.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
 e=yaml.safe_load((HERE/'uniform8.yaml').read_text())['models'][0];overlay=HERE/'uniform8.yaml';runtime=HERE.parent/'runtime-venv'
 cmd=[str(runtime/'bin/python'),str(runtime/'bin/mlx_vlm.server')]
 for k,v in [('model',e['hf_path']),('max-kv-size',262144),('kv-prealloc-tokens',262144),('prefill-step-size',512),('draft-kind','mtp'),('draft-model',e['draft_model']),('kv-bits',8),('kv-quant-scheme','uniform'),('quantized-kv-start',0),('generation-defaults',json.dumps(e['generation_defaults']))]:cmd.extend(['--'+k,str(v)])
 worker={'command':cmd,'environment':{'MLX_SERVE_CONFIG':str(overlay),'MLX_VLM_CACHE_SESSION_MAX':'2','KV_BITS':'8','HF_HUB_OFFLINE':'1'}}
 r.validate_worker(worker,e,overlay,runtime)
 worker['command'][2:2]=extra
 with pytest.raises(r.InstrumentError):r.validate_worker(worker,e,overlay,runtime)
