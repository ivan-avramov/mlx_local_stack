# P405 code review — round 3 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p405-kv-scheme` `4e2f864c..79914344`

Post-review (lead): K10 and K11 fixed as specified, test-first (fork `64afc7dd`); K11's cap context changed by C194 (no hard stop: the C193 ruling carries no cap; `--wall-limit-s` validated finite > 0); escalated to the operator with the rec to accept without a fourth round.

P1 — I’ll treat C193’s 20,400 s cap as authoritative for this review, verify the exact target commit and production pin first, then inspect the request/cache interception and authorization paths beyond the inline diff.P2 — The production pin is exact: `git diff --exit-code 7207179b 79914344 -- mlx_vlm ':!mlx_vlm/tests'` returned clean. K9’s default-path defect is fixed; the remaining scrutiny is on whether K7’s evidence is durably recorded and whether C193’s wall cap is impossible to bypass.Production pin verified clean.

K7 — Runtime validation fixed, but durable evidence remains incomplete; see K10.  
K8 — Intended C193 path fixed, but cap enforcement has a bypass; see K11.  
K9 — Cleared.

K10 — Medium — `dev/p400_perf_probe.py:442-449`  
Problem: The full validated per-request cache manifest is discarded; only distinct cache kinds are recorded. Paths, widths, group size, and TurboQuant mode are absent, contrary to K7’s required durable manifest.  
Failure scenario: The expensive ABBA completes, but its report cannot independently establish the exact per-layer codec configuration; materially different TurboQuant manifests produce identical recorded evidence.  
Fix: Store `live` verbatim in each request result, optionally storing the template once per leg, and test serialized evidence.

K11 — Medium — `dev/p369_phase2/orchestrate.py:1650-1669`  
Problem: `--wall-limit-s nan` bypasses `wall_limit_s > cap`; `campaign_deadline()` then returns NaN. Since `now >= NaN` is always false, C193’s campaign watchdog never fires.  
Failure scenario: A malformed C193 invocation runs with no effective 20,400-second campaign cap while recording NaN as its wall limit.  
Fix: Reject non-finite wall limits before comparison and test NaN explicitly; preferably require a finite positive value.

VERDICT: NOT CLEARED K10 K11
