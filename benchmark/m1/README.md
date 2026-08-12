# M1 agentic head-to-head — runner scripts

Committed because they previously existed only in `/tmp` on both boxes (cleared on reboot) and
carried absolute home paths. All machine-local paths are now env vars, so nothing here is PII.

```bash
export REPO=$(pwd)                       # the stack repo ON THE WORKER BOX
export AIDER_REPO=~/path/to/aider        # clone of Aider-AI/aider (has benchmark/benchmark.py)
export POLYGLOT_DIR=~/path/to/polyglot-benchmark
bash benchmark/m1/m1_driver.sh           # detach it: nohup ... </dev/null & disown
bash benchmark/m1/m1_heartbeat.sh        # 15-min progress + stall/OOM self-check
bash benchmark/m1/ornith_ladder.sh       # queued temp-ladder re-check (run AFTER M1)
```

## Non-obvious things these encode (each one cost a run to learn)

- **`--num-tests N` is an UNSEEDED RANDOM SAMPLE.** `benchmark.py` does
  `sorted(...) → random.shuffle(...) → [:N]` with no seed, so two invocations pick DIFFERENT
  exercises. The item set is therefore pinned by NAME via `AIDER_KEYWORDS` (keywords filter runs
  BEFORE the shuffle) plus `AIDER_LANGUAGES` (keywords match the whole path, so they do not by
  themselves restrict language). Without this, a paired comparison is impossible — and the
  campaign's historical `n=34` vs `n=16` agentic rows were two unrelated random subsets.
- **APC must be ABSENT from the router env.** `APC_NUM_BLOCKS=16384` (what `runserver.sh` ships)
  costs ~33GB: with Ornith resident the footprint was 54.2GB/4.1GB-free and every generation died
  on `[METAL] Insufficient Memory`. APC absent → 20.8GB/39.9GB-free. Verify with `ps -E` on the
  router pid; a stale exported value persists silently.
- **aider sets `RETRY_TIMEOUT` to 24 HOURS**, so one failing request silently eats a day (this is
  how the OOM stayed invisible). The driver therefore carries its own watchdog — M5 has neither
  `timeout` nor `gtimeout`.
- **cpp is excluded from the headline set.** A g++ template-error cascade fed back into the prompt
  produced a 165k-token request on the first cpp exercise, past the model's input budget: that
  measures the C++ toolchain, not the model. Run it as a separate sub-study if wanted.
- **The shipped `weak_model_name` 404s.** `aider_config/aider.model.settings.yml` points every
  model's weak model at `openai/mlx-community/Qwen2.5-1.5B-Instruct-4bit`, which lives on :8092 and
  is deliberately NOT a router entry — aider has one endpoint. The driver generates
  `/tmp/aider.bench.settings.yml` pointing the weak model at the served model itself; the shipped
  carrier is untouched (a real fix is a 4-carrier change per the AGENTS.md note-to-self).
- **Use a FRESH run tag after any config change.** `collect_case_results` globs by run name, so
  reusing a tag pools void cases with clean ones. Tags used so far: `m1` (void, APC-OOM),
  `m1b` (void), `m1c` (void, config reverted mid-flight) → next is `m1e`.
- **`pgrep -f "mlx-serve start" | wc -l` is NOT a duplicate-router check** — it counts the `uv run`
  wrapper and its child. Use the listener count on :8000
  (`lsof -nP -iTCP:8000 -sTCP:LISTEN`). A genuine duplicate showed SIX processes and two workers.
