# Handoff — 2026-09-29 (end of session): M50 served-config tripwire + M51 `runserver.sh` TERM teardown DONE (not pushed)

THE one handoff (AGENTS.md: rewritten in place each session; there is no per-feature handoff). Read this,
then `docs/PLAN.md` (the only queue) and `docs/open-questions.md` (decisions). Specs for queued work live in
`docs/specs/`; history in `docs/lab-notebook.md`.

## State of the world

- **Git: stack main has two NEW local commits on top of `90942de` — NOT PUSHED** (M51 `fix(stack)`, then M50
  `feat(bench)`); fork `../mlx-vlm` main `1bd249d3` and mlx-serve `6602ae5` unchanged and pushed. Clean trees after
  the M50 commit.
- **Stack is UP** on the M48 fork (daily driver, router `main_models.yaml`, sessions 2, APC absent, `runserver.sh`
  pid 96728 — the OLD script; the M51 fix applies to the NEXT bring-up). Resident model after the last smoke:
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. No serving config was changed this session; no model requests
  were sent (M50 was verified read-only against the live router's process facts).
- **Picks unchanged**: B/C 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` t0.5 medium, native16 KV (C81
  provisional), repaired MTP.
- Bench suite in `.venv-bench`: **1878 passed / 3 skipped** (M50 + M51 tests included).

## DONE this session (notebook 2026-09-28 M51 and 2026-09-29 M50 entries; PLAN M50/M51)

- **M51** `runserver.sh` TERM: two causes reproduced with a fake stack (bash parks a trapped signal behind the
  foreground `docker compose logs -f`; trap installed after the health waits). Fixed: trap before the first launch,
  signal traps `exit` into one EXIT handler, log tail + `compose wait` in the background under `wait`, tree-kill
  (TERM→10 s→KILL) of both server trees, `compose down`, :8000 verified free (exit 1 if bound).
  Test `benchmark/bench/tests/test_runserver_term.py` (3 cases). `scripts/stack_stop.sh` stays the belt-and-braces stop.
- **M50** served-config tripwire: `bench/provenance.assert_served_config()` first in every driver/probe (list in PLAN
  M50); refuses on no/ambiguous/remote/non-router owner, unreadable environ, missing `MLX_SERVE_CONFIG`, missing file,
  or resolved path ≠ `paths.registry_path()`; no bypass. `router{pid,config,…}` scrubbed into every manifest/result,
  `router_history` on resume/rerun, re-verify + manifest refresh after auto-restart (fatal on failure), opencode
  probes bound to `opencode debug config` in the child's cwd/env, proxy decisions differential against urllib's own
  `ProxyHandler`. Codex cold review: eight rounds (`$STACK_WORKDIR/m50/codex_review_{1..8}.md`), round 8 PASS, no new
  findings; every finding fixed or explicitly declined (notebook 2026-09-29). Live: OK on the default registry,
  REFUSED with an overlay in the driver env.

## Rules learned this session (already in AGENTS.md)

- `kill -TERM runserver.sh` now tears the stack down; `scripts/stack_stop.sh` remains the verified stop for stale
  shells and hand-started routers.
- Every driver/probe now refuses at entry unless the :8000 owner serves the driver's registry; opencode-driven probes
  verify opencode's OWN provider baseURL (global `~/.config/opencode/opencode.json`, else the shipped file).
- A cold review of a tripwire pays for many rounds: eight here, each finding real (guard ordering, router HOME,
  listener selection, opencode's effective config, swallowed refusals, resume attribution, proxy precedence spelled
  exactly as the transport spells it). Budget it; do not stop at "the exact incident is caught".
- When a guard must agree with a library's behaviour (urllib proxies), test DIFFERENTIALLY against the library's own
  code path (a real `ProxyHandler` with a stub transport), not against a re-derivation.

## Pending (reconciled)

1. **Push** the two stack commits when the operator says so (no fork changes this session).
2. **Possible follow-ups (not queued, operator call):** (a) `vision_gate` writes no manifest at all (pre-existing;
   router is in its summary only); (b) a config identity/hash exposed BY the router (`/health` or `/v1/models`) would
   close M50's residual: an in-place edit or symlink retarget after router start is invisible to a path comparison
   (fork/mlx-serve change).
3. **M46 live check**: the next opencode probe run must show one transcript per row and populated `loop_metrics`
   (and the manifest `skill_policy` fields). Lands together with **D12** on that run.
4. **Deferred**: frontier-driver composition (switchyard doc §8); S1 NVSY (parked); C77/C78/C87; C96; C104 open
   (fork test-suite sync policy, operator may veto items).
5. **D7** and **D5** remain driver-side backlog.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed sampling; explicit
served-overlay environment on every driver (now ENFORCED by M50 — a mismatch refuses). Never alter source/config
during a live run. Commit coherent units; push only on explicit current-turn instruction (forks before stack).
Next decision id C106; discussion ids continue from P71.
