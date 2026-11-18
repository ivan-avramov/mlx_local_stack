Cold read, round 1 of 3. Read-only; do not edit files. A small fail-closed guard in a benchmark harness (ruling C360).

Context: an agentic benchmark leg (opencode agent, open network) ran `brew install openjdk@17` onto the shared host during a run,
changing the environment every later leg (and the other arm of a paired comparison) would see. The operator asked for a LIGHT
guard: spec the environment as a recorded fingerprint and check it did not change under the leg; no sandbox, no denylist, no
auto-revert. Missing toolchains are installed once (bootstrap step 5b).

Files: host_env.py (new: fingerprint + diff), fix.diff (sequencer integration in benchmark/bench/p426_wave2.py: run baseline
<out-base>/host_env.json, check before each launch -> refuse, after each leg -> INVALID; tg2 positives check; BoxSeqOps.host_env
seam; bootstrap step 5b), test_s26_host_env.py. Repo for context: benchmark/bench/p426_wave2.py (Sequencer.run_leg, cmd_positives,
BoxSeqOps), benchmark/bench/opencode_v2_core.py:61 (the agent PATH).

Questions: (1) Can a host change made by a leg escape detection (what the agent can reach: Homebrew, global npm, /usr/local,
pip --user, the real HOME, PATH dirs)? Name the gap and a concrete command that slips through. (2) Can the guard false-alarm on
an unchanged host (nondeterminism in the version calls, Cellar entries changing for reasons outside the leg, resume of a run whose
baseline predates an operator-approved change)? (3) Is the INVALID-after-leg wiring correct (classification order vs OVERRUN,
the harvest of the INVALID leg, the stop afterwards)? (4) The optional seam (`getattr(ops, "host_env", None)`; fakes lack it):
can the real box path ever skip the check? (5) Test gaps. Numbered findings with severity (blocker / major / minor / nit),
file:line, a concrete failure scenario; "no findings" where none.
