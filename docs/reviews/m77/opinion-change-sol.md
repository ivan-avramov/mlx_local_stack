P1  
Location: `mlx-serve/src/mlx_serve/process_manager.py:438-444`; `mlx-vlm/mlx_vlm/server/cli.py:777-799`; `runtime_config.py:393-397`; `generation.py:1581-1713`  
Severity: major  
Evidence: confirmed — source trace  
Problem: An MTP-OFF registry entry does not reliably produce an OFF worker. `Popen` inherits mlx-serve’s environment, while the worker CLI clears scan/mode variables but only writes draft variables when flags are present. Thus inherited `MLX_VLM_DRAFT_KIND` or `MLX_VLM_DRAFT_MODEL` survives the argv omission. Frozen tests inspect argv only and never cross the process/environment boundary.  
Concrete failure scenario: Start mlx-serve with `MLX_VLM_DRAFT_KIND=mtp` and `MLX_VLM_DRAFT_MODEL=/d`, then use the accepted OFF entry. The worker inherits those values, sees MTP ON with `per_query`, rejects the missing `joint_v1`, and never reaches READY. With only an inherited draft model, it loads the drafter and then rejects via the post-load guard. Requests receive a load failure/503.  
Proposed change: For a TQ4 MTP-OFF entry, pass an explicit child environment to `Popen` with `MLX_VLM_DRAFT_KIND` and `MLX_VLM_DRAFT_MODEL` removed. Add a process-boundary test covering inherited draft variables through CLI → runtime config → initialization. The safety guards themselves are sound: no traced path reaches READY with MTP ON lacking `joint_v1`, or OFF with a drafter or module verify stamp; the mismatch is mlx-serve acceptance followed by worker refusal.

P2  
Location: `mlx-vlm/mlx_vlm/server/cli.py:687-692`  
Severity: minor  
Evidence: confirmed — source trace  
Problem: `--tq4-attention` help still says `--mtp-verify-scan joint_v1` is always required, contradicting the new supported OFF configuration.  
Concrete failure scenario: A direct-worker operator follows `--help`, adds `joint_v1` without a drafter, and startup is refused because OFF forbids that scan.  
Proposed change: Describe `joint_v1` as required only with `--draft-kind mtp`; document `per_query` as the OFF configuration.

P3  
Location: `mlx-vlm/mlx_vlm/server/generation.py:203-209,235-245,1600-1608`  
Severity: minor  
Evidence: confirmed — source trace  
Problem: Beyond the specification, both generation helpers accept an omitted `draft_kind` sentinel, and `_initialize_model` deliberately omits the configured value for MTP ON or mode-absent calls. This creates a second implicit representation of MTP ON instead of the specified required argument and same-value propagation. Frozen tests do not enforce that interface; implementer tests instead certify the deviation.  
Concrete failure scenario: A future OFF-path caller using the old helper shape omits `draft_kind`; it silently receives MTP-ON checks and rejects the normal OFF scan as missing `joint_v1`, rather than failing immediately at the call site.  
Proposed change: Make `draft_kind` required on the generation helpers and always pass `configured_draft_kind`; update legacy test fakes to accept the keyword.
