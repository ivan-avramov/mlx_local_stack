# P426 T3 — acceptance 6 smoke on the fixed candidate (2026-10-28 00:46–00:49Z)

Designer, GPU. Candidate = B0 + spec v2.1 + `impl-1` + fix round 1 (scratch `70c49f90`). Worktrees built from scratch:
`$STACK_WORKDIR/t3/smoke-off` at `70c49f90`, `$STACK_WORKDIR/t3/smoke-on` = it + the restore commit in the P511 form (C241;
`p426_plan.restore_diff_problems` of the fixed candidate → `[]`); submodules `c688e722` / `e6a7a5a`; `.venv` (`uv sync --frozen`) and
`.venv-bench` (`uv pip sync` of the bench lock) fresh, mlx 0.32.4 in both; both trees clean. Before: the P499 rehearsal stopped
cooperatively right after row 15 of block 2 Go (`STOP` 00:45:49Z, item 16 cancelled at its start and archived, router stopped by the
chain; `scripts/stack_stop.sh` → `:8000 free`, zero BUSY survivors). Driver `t3_smoke.py` (here, paths scrubbed): lean router per arm
from its worktree (`MLX_SERVE_CONFIG` = that worktree's committed `main_models.yaml`, `MLX_VLM_CACHE_SESSION_MAX=1`, no
`APC_ENABLED`), ownership / env / cwd verified, 3 non-streaming requests (`max_tokens` 512, seeds 1000–1002), the worker log slice
(`logs/mlx_vlm.log` `Request completed`), teardown via `scripts/stack_stop.sh` verified. Concurrent CPU load: the T3 test-writer's
suite (load ≈ 3.8); functional smoke only, no rates cited.

| Arm | Worker draft flags | Requests | `Request completed` | Draft fields | Teardown | Verdict |
|---|---|---|---|---|---|---|
| OFF | none (`--model caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, no `--draft-*`, no `--mtp-verify-scan`) | 3 / 3 `stop` (488 / 179 / 24 tokens) | 3, `backend=cached_session` | none | `:8000 free`, no survivors | **PASS** |
| ON | `--mtp-verify-scan joint_v1 --draft-kind mtp --draft-model caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter` | 3 / 3 `stop` (488 / 179 / 24 tokens) | 3, `backend=cached_session` | every request: `draft_kind=mtp`, accepted / proposed 301 / 372, 105 / 146, 13 / 20; `verify_blocks_per_query=0` | `:8000 free`, no survivors | **PASS** |

Both arms: `--kv-quant-scheme turboquant` with no `--kv-bits` (registry `kv_bits: 0`, C81) = native16 KV, as the plan fixes. Same
seeds gave identical completion lengths in both arms (consistent with exact speculative sampling; not a test of it).

- **P504** (C238): on the S′ fork, `registry_states.overlay_on` of the committed ON registry restores nothing and returns it byte-
  identical (sha256 `11861d8a3956…` both) — the file `qualify` writes as `overlay-<entry>.yaml` (`qualify.py:984–985`) equals the ON
  worktree's `main_models.yaml`, so the leg's sha check holds.
- **#2545** (fork `73d366ec`, unset sampling from the checkpoint for Python / CLI callers): does not reach M1. M1 generates through
  the worker's server path (unchanged by #2545), and `qualify` refuses unless every resolved sampling key equals the registry's
  `generation_defaults` (`qualify.py:332–338`; the entry pins temperature 0.5, top_p 0.95, top_k 20, min_p 0.0, presence_penalty 0.0).

## Rerun on the C242 pins (2026-10-28 03:04–03:06Z)

S′'s pins moved (C242) to fork `1c7c8fa1` (lock refresh) and mlx-serve `1ddf6f84` (`ruff format`). Worktrees rebuilt from scratch at
the pin-moved candidate (scratch `5ea34d16`; ON = it + the P511 restore commit, restore check `[]`), fresh venvs (mlx 0.32.4). Same driver
and requests: **OFF PASS** (no draft flags, 3 / 3 `stop`, no draft fields), **ON PASS** (`--draft-kind mtp` + drafter + `joint_v1`, draft
counters on 3 / 3), completion lengths again 488 / 179 / 24 in both arms, teardown verified each time (`off.pins2.result.json`,
`on.pins2.result.json`). P504 rechecked on the new ON registry: `overlay_on` restores nothing, byte-identical (sha256 `11861d8a3956…`).
