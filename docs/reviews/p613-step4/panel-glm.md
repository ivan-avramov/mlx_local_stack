## Findings

### F1 — BLOCKER (confirmed): the candidate records the resolved full commit sha, failing the frozen golden test `test_golden_cli_final`

**Location:** `benchmark/bench/p426_signals_divergence.py` (`a7_divergence`, lines `ref = V.resolve_commit(...)` → `inputs[f"evidence:{ref}:{path}"]` and `evidence_ref=ref`); `benchmark/bench/p426_signals.py` `compute_all` line `evidence_ref=div["evidence_ref"]`. Counterpart: `.p613-material/frozen-tests/test_p613s4_golden.py` (`EVIDENCE_REF = "b6ec7819"`; `assert any(v == EVIDENCE_REF for _, v in _scalars(sig["header"]))` and `ev = [k for k in sig["inputs"] if k.startswith(f"evidence:{EVIDENCE_REF}:")]; assert len(ev) == 172`).

**Evidence:** `V.resolve_commit` (`benchmark/bench/p426_verify.py:1244-1249`) returns `git rev-parse --verify --quiet <sha>^{commit}`, which expands a short sha to the full 40-char commit. The implementer's own report confirms this: "`header.evidence_ref` = `b6ec781939f970987b449d329aed1d46596c3da5`" and P6 states they "record the resolved full commit sha … not the short `b613s4-panel` that was passed in." The golden test passes `--evidence-ref b6ec7819` and asserts the header carries the scalar `"b6ec7819"` and that input keys begin with `evidence:b6ec7819:`. With the candidate, `header.evidence_ref` is the full sha (no header scalar equals `"b6ec7819"` — `header.panel` holds only `frozen_sha256`/`files_sha256`/counts, not a ref), and every input key is `evidence:b6ec781939…:<path>`, which does **not** start with `evidence:b6ec7819:` (the char after `b6ec7819` is `3`, not `:`). Both assertions fail.

**Problem:** The candidate does not pass its own independent (frozen) golden test. The four-eyes gate requires the frozen tests to pass before merge; the implementer's report concedes the golden tests were never run (`bench/tests/p613s4/` doesn't exist yet), so this deviation went undetected. The contract (`docs/specs/p613-step4-contract.md`) says "the `evidence` branch at a RECORDED ref (`--evidence-ref` …)" and "The header records the evidence ref," and its golden block names `evidence b6ec7819` — i.e. the as-passed ref. The test-writer read "RECORDED ref" as the value supplied on the CLI; the implementer read it as the resolved commit. The frozen test encodes the former.

**Failure scenario:** Run `pytest .p613-material/frozen-tests/test_p613s4_golden.py::test_golden_cli_final` against the candidate on the committed data (with `b6ec7819` and `e8383713` in the object database). It fails at the `any(v == EVIDENCE_REF …)` assertion (and again at `len(ev) == 172`).

**Proposed change:** Record the as-passed `evidence_ref` string in `header.evidence_ref` and in the `evidence:<ref>:` input-key prefix (do not resolve it for storage). Continue to resolve it only for the `git show` reads and for the `git show`-only provenance. If the operator prefers the full sha for precision, that is a contract/test change to raise with the operator — not a unilateral implementer choice that breaks the frozen test.

---

### F2 — MAJOR (hypothesis): no frozen test exercises a B8-rejected A7 session inside the divergence section, so "rejected → `complete=False` → not FINAL" is unverified

**Location:** `benchmark/bench/p426_signals_divergence.py` (`complete = all(sessions[s]["status"] == "accepted" for s in SESSIONS)`); `benchmark/bench/p426_signals.py` `_final_ready` (`if not (rec.get("divergence") or {}).get("complete"): missing.append("divergence")`). Counterpart: `.p613-material/frozen-tests/` — every hermetic world (`s4world.ACCEPTED`) and the golden data have both sessions B8-accepted; `with_rejected` only removes a *key* (`go/psi`), never rejects a *session*.

**Evidence:** `s4world.build_case(…, with_rejected=True)` edits B8 to reject the single key `go/psi` (s4world docstring: "edits B8 to reject `go/psi`"), and the CLI worlds are built `with_rejected=False` because `p426_signals all` refuses a B8 whose pair keys differ. No fixture rejects an entire `s1` or `s2` pair. So the branch in `a7_divergence` that emits `sessions[s] = dict(status="rejected by B8", …)` and forces `complete=False` is never executed by any test.

**Problem:** If that branch were mis-implemented (e.g. `complete` computed from `SESSIONS` presence rather than per-session `status == "accepted"`, or a rejected session silently treated as accepted), `_final_ready` could mark the sheet FINAL with a missing session, exactly the "mark the sheet FINAL when a section is missing" failure the request names. The contract data does not exercise it, but the code path is shipped and a future regrade could produce a rejected session.

**Failure scenario:** A future B8 rejects `s2` (e.g. a receipt goes INVALID). `a7_divergence` builds `sessions["s2"]["status"] = "rejected by B8"`. If a bug there set `complete=True`, the sheet would print FINAL with `s2`'s divergence items empty and the operator would not be told a section is missing.

**Proposed change:** Add a hermetic world where B8 rejects one A8 session (a `rejected pair` reason), and assert `a7_divergence` returns `complete=False` for that session, `divergence.complete=False`, and `compute_all` yields `header.final.ready=False` with `"divergence"` (or `"A7-s2"`) in `missing` and a non-FINAL status.

---

### F3 — MINOR (hypothesis): the `--evidence-ref`-without-`--panel` path leaves a step-2 status string on a step-4 generator-version header

**Location:** `benchmark/bench/p426_signals.py:858-879`. When `panel is None` and `evidence_ref is not None`, the panel block is skipped, then divergence runs: `rec["header"]` is overwritten with `generator_version=STEP4_VERSION`, `evidence_ref`, `final`, but `status` stays `rec["header"]["status"]` = the step-2 `ALL_STATUS` ("PROVISIONAL — subjective panel pending (step 3)") because `final["ready"]` is False (no `subjective`).

**Evidence:** The frozen test `test_ref_without_panel_is_not_final` only asserts `status != D.FINAL` (it allows either a refusal or a non-final status), so it does not pin what the status actually is. The sheet would render through `render_all` (dispatch now includes `STEP4_VERSION`) with a step-2 status line, a step-4 generator version, a divergence section, no §4.5, and `header.final.missing == ["panel", "divergence"?]`.

**Problem:** A consumer reading the sheet sees "PROVISIONAL — subjective panel pending (step 3)" alongside a step-4 generator and a divergence section — an internally inconsistent intermediate state. Not a FINAL mislabel (good), but a confusing artifact. The contract does not define this combination (it only defines `--evidence-ref` absent → step-3 unchanged, and present with panel → FINAL-or-step3-status).

**Failure scenario:** Operator runs `all --evidence-ref <sha>` without `--panel` (typo, or panel dir not yet exported). Gets a sheet that says "subjective panel pending (step 3)" but already carries the divergence section and a step-4 header — misleading about which step is done.

**Proposed change:** Either refuse `--evidence-ref` without `--panel` (the divergence section is meaningless for FINAL without the panel, and the contract's FINAL definition requires the panel), or set the status to a step-4-specific non-final string (e.g. "PROVISIONAL — panel pending (step 3) for FINAL"). Add a frozen test pinning the chosen behaviour beyond `!= FINAL`.

---

### F4 — Scope request (no severity): assert that the divergence section's position (after §4.5, before Flags) holds on the committed/golden sheet, not only on the hermetic world

The hermetic `test_section_heading_and_position` checks `## Subjective panel (§4.5; …) < HEADING < ## Flags` in world A. The golden `test_golden_cli_final` only checks `D.HEADING in text`. A rendering-order regression on the real sheet (e.g. divergence placed before §4.5, or after Flags) would not be caught by the golden test. Cheap to add: `assert md.index("## Subjective panel (§4.5; `subjective`)") < md.index(D.HEADING) < md.index("## Flags (`flags`)")` in the golden test.

---

### What I did NOT find

- No misclassification of an A7 item's first divergence that the contract's multiset rule would catch: `gen` (sorted multiset of `text` and `(tool, JSON.input)`) drives `generation`; `env` (sorted multiset of `(tool, input, str(output))`) drives `environment` only when `gen` is equal; strict-prefix → `cutoff`; equal → `identical`. Parallel calls in a different completion order collapse to `identical` (sorted multisets); tool-input key order is normalized (`sort_keys=True`); interleaved message events are grouped by `part.messageID` in first-appearance order; reasoning/step/timestamp/metadata noise is dropped (only `text`/`tool_use` kept). The frozen world A/B tables exercise every kind, including a generation-later-but-environment-first item (`python/delta`) and a duplicated tool call (`go/rho`).
- No binding of an events file to bytes it should not: the candidate drops step 3's direct-hash shortcut and requires exactly one HARVEST record with `sha256 == row.evidence_sha256.events` and `published_sha256 == sha256(bytes read)`; the frozen binding tests cover altered bytes, missing file, bad ref, and all four HARVEST corruptions plus `raw_as_published`.
- No change to step-1–3 output: the no-`--evidence-ref` path returns the step-3 record unchanged (golden `test_golden_no_ref_path_reproduces_step3_sheet` asserts byte-identity to the committed step-3 sheet at `e8383713`); the `render_all` Pending `- none` fallback only triggers when `pending` is empty, which never occurs in step 3; the `render_md` dispatch addition of `STEP4_VERSION` does not affect the step-1 (`p613-step1`) path.
- No premature FINAL: `_final_ready` requires every Wave 1 block `accepted`, both A7 sessions `accepted`, `subjective` present, and `divergence.complete` true; the no-panel path is correctly non-FINAL.

The one substantive blocker is F1: the candidate fails its frozen golden test by recording the resolved full sha instead of the as-passed `--evidence-ref`. Resolve F1 (change the candidate to store the as-passed ref, or escalate the contract ambiguity to the operator) before merging.
