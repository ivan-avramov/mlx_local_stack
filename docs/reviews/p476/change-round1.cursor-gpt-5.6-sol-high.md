- Location: `mlx-vlm/mlx_vlm/tests/test_p426_qualify_predictor.py:29-48`  
  Severity: major  
  Problem: The candidate removes the served entry from `qualify.ENTRIES`, but this dependent test still calls `arm_for(STATIC, ...)`.   <!-- allow-shorthand: verbatim reviewer output -->
  Failure scenario: The full fork suite gets three `KeyError` failures, despite the targeted fork tests passing.  
  Proposed change: Inject the synthetic served entry with the same scoped fixture used by `test_p415_qualify.py`.

- Location: `mlx_local_stack/openwebui-init/model_settings.json:14-16`, `openwebui-init/reconcile_models.py:175-187,238-260`  
  Severity: major  
  Problem: Removing the six IDs from `excluded_model_ids` eliminates the tombstones used to detect unmanaged saved OWUI registrations.  
  Failure scenario: A persisted pruned registration remains selectable and passes reconciliation verification, but requests fail because the router no longer serves it.  
  Proposed change: Retain separate migration tombstones until every persisted volume has completed backup-backed pruning; test unmanaged post-prune registrations.

- Location: `mlx_local_stack/benchmark/mem_decompose.py:29-35,76-92`  
  Severity: major  
  Problem: Its documented gemma invocation no longer finds registry settings and silently falls back to 262144 tokens instead of that model’s former 196608 cap.   <!-- allow-shorthand: verbatim reviewer output -->
  Failure scenario: The probe measures the wrong deployment configuration and may hit the memory backstop/OOM it was designed to investigate.  
  Proposed change: Refuse absent models, or require an explicit historical registry fixture.

- Location: `mlx_local_stack/benchmark/run_bfcl_h2h.sh:10-27`  
  Severity: major  
  Problem: The documented `gemma` selector still targets the now-pruned `gemma-4-26B-A4B-it-OptiQ-4bit`.   <!-- allow-shorthand: verbatim reviewer output -->
  Failure scenario: `./run_bfcl_h2h.sh gemma` reaches mlx-serve with an unknown model and fails routing/404.   <!-- allow-shorthand: verbatim reviewer output -->
  Proposed change: Retire the selector with an immediate diagnostic, or require a dedicated historical registry overlay.
