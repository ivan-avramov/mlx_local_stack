Verify, round 2 of 3. Read-only. Your round-1 findings on the earlier exclusion fix (P1 major: excluding an item because of a token
in ONE arm's answer selects on the treatment; P2 minor: filtering inputs before validating --prompts) — the designer re-checked the
real data: in 6 of the 9 items only the N16 answer carries the token; no prompt does. The exclusion was REVERTED. New fix (fix2.diff):
the KV-lever leak check `_kv_leaks` no longer treats `family-token` as a leak, because both KV arms are one registry entry (same
model, KV mode differs), so a family token in an answer carries no arm identity; KV / arm identifiers (KV_LEAK_PATTERNS: m76, n16,
tq4, kv_bits, m72_…), registry names (`_leak_names`) and template tags still refuse. Tests: test_v2.py.
For each round-1 finding state resolved or not, and why. Then: can a judge now learn which ARM wrote an answer, or be steered by
anything the arms differ in other than answer quality? Does the MTP lever path (`_a7_write_packets` / line ~775 check) change? Is the
change limited to KV packets? Numbered findings with severity, file:line, scenario; "no findings" if none. Do not modify any file.
