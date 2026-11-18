Round 1 of 3.

P1 — major — `host_env.py:17-18,41-56`: the fingerprint does not cover all mutable environment the agent can reach; it records directory names or existence, not contents.

Concrete escapes:
- `HOME="$REAL_HOME" python3 -m pip install --user black` changes `~/Library/Python/...`, which is untracked.
- Reinstalling an existing global npm package changes its contents without changing `/opt/homebrew/lib/node_modules` names: `npm install -g typescript@latest`.
- Creating an unlisted executable in `/opt/homebrew/bin` is invisible because that PATH directory is not listed and only 14 named tools are resolved.
- Changes inside an already-present `~/.rustup`, `~/.cargo`, or `~/.gradle` remain invisible.

Thus the original `brew install openjdk@17` is caught, but the claimed Homebrew/global npm/pip-user/real-HOME/PATH coverage is incomplete.

P2 — major — `p426_wave2.py:800-809`, `p426_wave2.py:200-219`: post-run checking is not guaranteed.

A detached command such as:

```sh
nohup sh -c 'sleep 60; brew install jq' >/tmp/install.log 2>&1 &
```

can mutate the host after the immediate post-leg snapshot. A later pre-launch check will refuse, but the offending leg may already be recorded and harvested as VALID; on the final leg there may be no later check. Additionally, exceptions before the check—such as `classify_leg()` failing, or `positive_inject()` timing out—skip it entirely because it is not in a `finally`.

P3 — major — `host_env.py:22-31`: command output is not a deterministic installation fingerprint.

A transient 30-second timeout records `error: TimeoutExpired`; the next successful call reports a version and falsely signals drift without an installation change. `gradle --version` can also emit a one-time welcome line, while only the first non-empty line is retained. This can invalidate the first clean leg.

Cellar changes caused by another process are real host drift, so invalidating the leg is conservative and correct even though the leg was not necessarily causal. Likewise, an operator-approved change after the baseline should refuse resume: the paired run no longer has a matched environment and needs a fresh baseline/run.

P4 — major — `p426_wave2.py:1200-1206,1283-1290`: `host_env.json` is never included in published run files.

The baseline remains scratch state rather than committed run evidence. The positives record embeds its baseline, but sequenced runs do not publish theirs.

P5 — minor — `p426_wave2.py:803-808`: changing `state` to `INVALID` preserves the previous `class`.

A clean leg that modifies the host produces `state: "INVALID"` with `class: "valid"`; an originally overrun/systemic leg can similarly retain the wrong class. It should be classified consistently as systemic/environmental.

P6 — no finding — `p426_wave2.py:803-832,1076-1082`: apart from P5, INVALID wiring is correct.

Host drift overrides OVERRUN state, `leg.json` and sequence state are written, the INVALID attempt is harvested, and execution stops. For a simultaneous overrun, the immediate stop is rc 3/OVERRUN rather than the environment reason, but the recorded state remains INVALID and resume cannot continue it.

P7 — no finding — `p426_wave2.py:1659-1699`: the normal real-box path cannot skip the seam.

Both sequencer and positives CLI paths construct `BoxSeqOps`, whose `host_env()` exists. Optionality only permits injected test/fake ops to omit it.

P8 — major — `test_s26_host_env.py:31-104`: important test coverage is missing:
- No positives mutation test, despite the module docstring claiming positives coverage.
- No pip-user, in-place npm/toolchain update, or arbitrary PATH-entry escape test.
- No transient/variable version-output test.
- No detached post-exit mutation test.
- No host-change-plus-OVERRUN test checking state, class, harvest, and stop.
- No assertion that the baseline is published.
- No test that unexpected exceptions still trigger a post-run comparison.
