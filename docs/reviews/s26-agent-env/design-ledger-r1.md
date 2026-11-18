# S26 agent-env spec — design review round 1 of 3 (strict `opinion`), dispositions

Panel: Sol (`gpt-5.6-sol-high`, cursor-agent `--mode ask`, checkout) 5 findings; GLM (`glm-5.2-high`, same) 15. Applied once as v1.1, not re-reviewed.

| Finding | Sev | Disposition | Why |
|---|---|---|---|
| Sol P1 DECLINED waives harness FAILs | blocker | adapted | DECLINED only for `not_observed*` or `FAIL:no_shell_part` (= no shell call carrying `bytearray(`, `inject_verify.py:251`: the decline itself), evidence hash-verified, marker absent; Sol's literal rule (`not_observed*` only) would fail the observed Java alloc decline |
| Sol P2 identity policy rebuilt by `GenerationPolicy` | major | adopted | confirmed `arm_runner._identity_inputs`; optional field omitted when None keeps tg1's hash |
| Sol P3 / GLM F4 end-of-run placement | major | adopted | one finalization for DONE and `--through`, before publishing |
| Sol P4 `check` trusts the receipt | major | adopted (light) | cache manifest of `wrapper/dists` + `caches/modules-2/files-2.1` sizes; `--force` clears |
| Sol P5 / GLM F3 positives exception path | minor / major | adopted | caught, sealed FAIL record with exception + host diff |
| GLM F1 post-leg check not on exception path | major | adopted | `try/finally` launch → `leg.json`; logs and re-raises |
| GLM F2 class of a host-changed leg | major | adopted | `class: systemic` (`classify_leg.invalid`) |
| GLM F5 `build_env` misses the positives path | major | declined | traced: positives and chain both spawn via `run_tg2_probe.py` → `arm_runner` → `adapter.build_env` (`:1123`, `:1207`); the agent's shell inherits it (transcript `PATH=/opt/homebrew/bin:/usr/bin:/bin`) |
| GLM F6 JVM `user.home` assumption | major (hyp.) | declined | measured: `HOME=/tmp/fakehome java -XshowSettings:properties` → real home; recorded in the spec |
| GLM F7–F9 draft vs spec mismatches | minor | noted | the spec governs; the draft is starting code |
| GLM F10 message separator | minor | adopted | `"; ".join(diff)` pinned |
| GLM F11 end check / publication beyond the ask | scope | kept | catches a change after the last leg's own check (detached installers, r1 P2) |
| GLM F12 prefill env differs from the agent's | minor | adopted | prefill = agent spawn fields + `GRADLE_USER_HOME` |
| GLM F13 prior reason lost | minor | adopted | prepend, keep `(prior: …)` |
| GLM F14 baseline written late | minor | adopted | baseline at `run()` entry; resume compares first |
| GLM F15 positives record lacks the after state | minor | adopted | `host_env_after` recorded |
