I found no blockers or majors. I read `p426_harvest.py`, `p426_secrets.py`, `p426_reconcile.py` and part of `p426_freeze.py`. I did not review the sequencer (`p426_wave2.py`), locks, hooks or the receipt, did not trace the legacy-path changes, and ran nothing. So this is not a clean bill of health for those parts.

**F1 — minor — confirmed in source: `benchmark/bench/p426_secrets.py:56-73` (`parse_assignments`)**
- Problem: the parser strips only a quote pair that spans the whole right-hand side. It does not handle a trailing shell comment or text after a closing quote.
- Scenario: `export FOO_API_KEY="abcd1234efgh5678" # work key` is stored as `"abcd1234efgh5678" # work key`, and `export FOO_TOKEN=abcd1234efgh5678 # x` keeps the ` # x`. `exact_hits` then never finds the real value in a transcript or log. For a token that matches none of the `FORMATS` patterns, the exact-value defence is silently off, and `absent_sources` doesn't report it.
- Fix: parse the right-hand side shell-style, using `shlex.split(value, comments=True)` and taking the first token. If a credential-keyed line can't be parsed cleanly, raise `SecretsError`, so the harvest refuses rather than skips the value.

**F2 — minor — confirmed in source: `p426_secrets.py:130` (`bearer` format)**
- Problem: the pattern needs `Authorization:` followed directly by `Bearer`. Header dumps in JSON or JSONL look like `"Authorization": "Bearer abc…"`, with a closing quote before the colon and another quote before `Bearer`.
- Scenario: an opencode events or stderr file that echoes request headers is not flagged by the bearer format. The `hf_` and `sk-` formats and the exact-value match still catch known credentials, so the leak is limited to unknown bearer strings.
- Fix: use `Authorization["']?\s*[:=]\s*["']?Bearer\s+…`.

**F3 — minor, scope request — `p426_reconcile.engagement_problems` (line 146) and its callers in `p426_hooks.py:243` and `p426_freeze.py:155`**
- Problem: the check skips ON requests with fewer than 2 generated tokens, and no leg-level check requires at least one engaged request.
- Scenario: an ON item whose requests are all ≤1 token reconciles as engaged with zero MTP counters. This is unlikely for coding items, but the item is still reported as engaged.
- Fix: in the ON arm, report an item or leg with no judged request as `unengaged`, not valid.

**F4 — minor (availability) — `p426_harvest.py:393-406` (`Gate.check`)**
- Problem: a non-UTF-8 file is never scrubbed. It is only refused if a PII marker appears in it.
- Scenario: a server-log slice (`_log_slices`) that starts or ends inside a multibyte character, or an evidence file with one stray byte, containing a home path fails the whole attempt instead of being scrubbed. This fails closed, so it is not a leak. It does cost a harvest of a finished leg.
- Fix: for evidence-bound files, decode with `errors="surrogateescape"` or `replace`, scrub, and record that the decode was lossy.
