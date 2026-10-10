"""M18 surgical re-run (C20 sequencing, 2026-08-24): regenerate EXACTLY the poisoned ids
in place (run_ids=True + allow_overwrite=True -> bfcl_eval updates listed rows, touches
nothing else), under the O41-fixed harness (derived timeout, retries=0, fail-loud).
Scoring is NOT done here — rescore_m18.py (poison-guarded) runs after all models finish.

Usage: surgical_rerun.py <model> <out_root> '<json: {category: [ids]}>'
"""
import json, os, sys
from types import SimpleNamespace

model, out_root, ids_json = sys.argv[1], os.path.abspath(sys.argv[2]), sys.argv[3]
ids = json.loads(ids_json)

os.environ["BFCL_PROJECT_ROOT"] = out_root  # MUST precede any bfcl_eval import
sys.path.insert(0, "$STACK_REPO/benchmark")

from bench import bfcl_handler as H  # noqa: E402

with open(os.path.join(out_root, "test_case_ids_to_generate.json"), "w") as f:
    json.dump(ids, f)

H.register_model(model)
from bfcl_eval._llm_response_generation import main as generation_main  # noqa: E402

gen_args = SimpleNamespace(
    model=[model], test_category=sorted(ids), temperature=0.001,
    include_input_log=False, exclude_state_log=False, num_gpus=1, num_threads=1,
    gpu_memory_utilization=0.9, backend="vllm", skip_server_setup=True,
    local_model_path=None, result_dir=os.path.join(out_root, "result"),
    allow_overwrite=True, run_ids=True, enable_lora=False, max_lora_rank=None,
    lora_modules=None,
)
generation_main(gen_args)
print(f"[surgical] {model} regenerated ids: {ids}", flush=True)
