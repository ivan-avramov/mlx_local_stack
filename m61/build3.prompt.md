Continue the M61 implementer job, round 3. Your round-2 work is committed on branch `m61-web-audit` (3b488a2); your report is
$STACK_WORKDIR/m61/tmp/build-report.md. Implement spec section P201 of `docs/specs/m61-web-audit-and-prompt-ab.md`
(re-read the whole spec; P201 is new, operator-requested). Same rules as $STACK_WORKDIR/m61/build.prompt.md
(tests first, local mocks only, no :8000, no internet, no commit, no home paths in committed files, full model names).

Specifics:
- Code-search deny patterns appended to the web carrier via the configgen emitter (regenerate; `configgen check`); the
  `opencode-v2` carrier must stay byte-identical (existing pin).
- Evidence sidecars: write each fetch/network-shell output under the item's transcript area as specified, record path (portable
  `$STACK_WORKDIR` form), sha256, bytes in `web_fetches` / `net_shell` entries.
- `benchmark/web_audit.py`: the auditor is invoked as a subprocess
  `codex exec -m gpt-6-astra -s read-only --skip-git-repo-check -o <tmpfile> -` with the prompt on STDIN (never in argv), behind
  an injectable `auditor` callable so tests use a fake. Prompt template file `benchmark/web_audit_prompt.md` (its sha recorded in
  each sidecar line with the auditor id). Output parsing must refuse anything but exactly one allowed label (+ a one-line reason);
  a malformed answer is recorded as `unclear`. Timeouts via subprocess timeout; a failed call is recorded as `audit_error`
  (counts as unresolved, i.e. excluded until the operator resolves it). Idempotent: re-running skips fetches already audited
  with the same prompt sha.
- Pre-flag: public identifiers of the stub (Python: top-level `def`/`class` names; Go: exported `func`/`type` names) — ≥ 3 present
  in fetched text of the item's language → `preflag: true` on the sidecar line.
- Extend `bench.answer_key.report_rows` (or its successor) to apply the P201 reporting rule from the sidecar.
- Known positives/negatives as fixtures: the go/matrix fetch (exists), a synthetic community-style solution of `python/bowling`
  you write in a deliberately different style from the polyglot reference (verify the overlap detector does NOT flag it — that
  is the point), and a short Go stdlib documentation excerpt (write a plausible paraphrase, not a copy).
- Do NOT call the real auditor from tests. At the end, if your sandbox can run `codex exec`, run the real auditor once on the
  three fixtures and report the labels; if it cannot, say so and give the exact command for the operator.

Report (terse, Q-numbered): files changed; test summary lines (both suites + configgen check); fixture overlap numbers; real
auditor labels or the command; open questions.
