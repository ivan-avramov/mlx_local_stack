from pathlib import Path
import json,yaml,os,types,collections,hashlib
import mlx.core as mx
mx.set_default_device(mx.cpu)
from mlx_vlm.models.qwen3_5.language import LanguageModel
from mlx_vlm.models.cache import ArraysCache,PreallocKVCache,PreallocQuantizedKVCache
from mlx_vlm.generate.common import maybe_quantize_kv_cache,maybe_preallocate_kv_cache
HERE=Path(__file__).resolve().parent
entry=yaml.safe_load((HERE/'native16.yaml').read_text())['models'][0]
config_path=Path(entry['hf_path'])/'config.json'
conf=json.loads(config_path.read_text())['text_config']
assert not os.environ.get('MLX_EPICACHE_BUDGET')
assert conf['torch_dtype']=='bfloat16'
class ShapeOnly:
    layers=[types.SimpleNamespace(is_linear=x=='linear_attention') for x in conf['layer_types']]
    make_cache=LanguageModel.make_cache
report={'kind':'CPU constructor and tiny tensor verification; no model loaded or generated','model':entry['name'],'config_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest(),'checkpoint_declared_dtype':conf['torch_dtype'],'native_live_model_dtype_observed':False,'arms':{}}
for mode,bits,scheme in [('native16',None,'turboquant'),('uniform8',8,'uniform')]:
 caches=ShapeOnly().make_cache();recurrent=[x for x in caches if isinstance(x,ArraysCache)]
 maybe_quantize_kv_cache(caches,quantized_kv_start=0,kv_group_size=64,kv_bits=bits,kv_quant_scheme=scheme)
 maybe_preallocate_kv_cache(caches,262144)
 cls=PreallocKVCache if bits is None else PreallocQuantizedKVCache
 assert sum(isinstance(x,cls) for x in caches)==16
 assert [x for x in caches if isinstance(x,ArraysCache)]==recurrent and len(recurrent)==48
 assert all(x.prealloc_tokens==262144 for x in caches if isinstance(x,cls))
 # Exercise exact cache class with tiny floor, not a full-cap allocation.
 tiny=cls(prealloc_tokens=8) if bits is None else cls(prealloc_tokens=8,bits=8,group_size=64)
 x=mx.ones((1,conf['num_key_value_heads'],1,conf['head_dim']),dtype=mx.bfloat16)
 k,v=tiny.update_and_fetch(x,x);mx.eval(k,v)
 if bits is None:assert k.dtype==mx.bfloat16; observed=str(k.dtype)
 else:
  assert k[0].dtype==mx.uint32 and k[1].dtype==mx.bfloat16
  assert tiny.bits==8 and tiny.group_size==64
  observed={'packed':str(k[0].dtype),'scales':str(k[1].dtype),'bias':str(k[2].dtype)}
 report['arms'][mode]={'counts':dict(collections.Counter(type(c).__name__ for c in caches)),'full_floor':262144,'group_size':64 if bits else None,'tiny_tensor_dtypes':observed}
(HERE/'layout-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
