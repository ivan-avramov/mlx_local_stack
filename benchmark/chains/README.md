# Chain drivers (frozen)

Verbatim copies of the out-of-repo drivers that produced the M54–M62 agentic rows, committed
2026-10-10 (P229) so the procedure survives loss of the operator's workdir. Only absolute home
paths were rewritten to `$STACK_WORKDIR` / `$STACK_REPO`; logic is unchanged and untested in
this location. Outputs still go to `$STACK_WORKDIR/<milestone>/`.

| Dir | Rows | Entry point |
|---|---|---|
| `m54/` | `agentbench_os.v1.chain*` | `launch_redo.sh` → `run_arms_redo.py`; `land_chain4.sh` lands rows (needs a `$STACK_WORKDIR/m54/wt-aac939b` worktree of commit `aac939b`) |
| `m55/` | `opencode_*.m55.*` (frozen 1.18 probe) | `run_m55.py`, `land_m55.sh` |
| `m59/` | `opencode_v2_*.m59.*` | `run_m59.py` (router start/ownership, power gate, watcher); `make_overlay.py`, `mem_watchdog.py`, `prompt_identity.py`, `chain_resume.sh` |
| `m61/` | `opencode_v2_*.m61*`, `*.rr.*` | `drive_ab.sh` / `drive_rr.sh` → `run_m61.py` / `run_m61_rr.py` (import `../m59/run_m59.py`) |
| `m62/` | `opencode_v2_tg1_*.m62v3/.m62v4` | `drive_live.sh` → `run_m62_live.py` (imports `../m59/run_m59.py`) |

`m59/run_codex.sh` and `m62/run_codex.sh` run Codex cold reviews/implementers (`codex exec -m gpt-6-astra`).
Known limits (C147): the M59 runner's fixed 6 h leg timeout kills without cleanup and treats row
count as completion; a tg1 chain needs a replacement runner. Raw outputs of these runs are on the
`evidence` branch.
