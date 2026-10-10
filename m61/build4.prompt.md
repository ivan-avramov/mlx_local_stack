Continue the M61 implementer job, round 4 (fixes from a cold verification). Branch `m61-web-audit`, your rounds are committed
(3b488a2, ac7f99b). Same rules as $STACK_WORKDIR/m61/build.prompt.md (tests first, local mocks only, no :8000, no
internet, no commit, no home paths in committed files, full model names, never edit docs/handoff.md). Verifier scratch (repro
scripts) is in $STACK_WORKDIR/m61/verify/.

Fix, each with a failing test first:
1. Subagent channel: count `subagent` tool calls per row (`subagent_calls`). For `opencode-v2-web` rows with `subagent_calls > 0`
   set `web_audit_incomplete: true` (child sessions are not exported/audited); `report_rows` excludes incomplete rows as
   unresolved web contact. Do not deny the subagent tool (scaffold change, not ruled).
2. A4 receipt for every scaffold: `scripts/session_pinning_gate.py` gains `--scaffold` and `--agent-system-file` that reuse the
   probe's carrier selection/composition (`_carrier_selection` or a shared helper) so `receipt.carrier_sha256` equals the carrier
   the probe writes. Default stays the M59 behaviour only if that is what the gate currently does for `--opencode v2`; otherwise
   match the probe default. Test: receipt sha == probe-written sha for opencode-v2, opencode-v2-web, and opencode-v2 + system file.
3. Reports: `benchmark/bench/compare.py` and `benchmark/m1/scoreboard.py` must route `opencode-v2-web` rows (and any row carrying
   web-audit fields) through `report_rows` (exclusions + separate count), or refuse them with a clear message where routing is
   not possible. Tests for both.
4. Auditor hermeticity: invoke `codex exec --ephemeral --ignore-user-config -m gpt-6-astra -s read-only --skip-git-repo-check …`
   (both flags exist in codex-cli 0.161.0); record `codex --version` (`auditor_version`) in every sidecar record; idempotence key =
   (prompt sha, auditor id, auditor version).
5. `web_denied`: count only webfetch rejections and rejections of NET_SHELL-matching commands; record each rejection's
   `error.message`.
6. `_web_audit` must never abort a leg: any exception → `web_audit_error` on the row (string), row excluded by `report_rows`
   (fail closed); encode with `errors="surrogatepass"`; handle `state.content` null/missing.
7. Pre-flag: Python includes class method names (not dunder); threshold `min(3, n_identifiers)` with n ≥ 1; Go keeps methods.
8. Denylist case: add `*XERCISM*` and `*PROBLEM-SPECIFICATIONS*` variants for webfetch and shell (Wildcard is case-sensitive).
   Keep the M59 carrier unchanged.
9. NET_SHELL: also match `pip3? install|download`, `uv (pip|add)`, `go (get|install)`, `cargo (add|install)`, `npx `, `gh `,
   `brew `, `git (clone|fetch|pull)`. A NET_SHELL command that writes to a file (`-o`, `-O`, `--output`, `>`, `tee`) sets
   `web_audit_incomplete: true` (its content can reach the model by a later read we do not audit).
10. `web_audit.py --retry-errors` re-audits records whose latest result is `audit_error`.

Then run both suites and `configgen check` (restore uv.lock if rewritten). `test_runserver_term.py` was load-flaky in the
verifier's full run (passes alone) — note it, do not change it.
Report (terse, Q-numbered): fix → test name, one line each; suite summary lines; open questions.
