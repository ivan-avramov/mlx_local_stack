# Delivery 1d (same session, still blind): §16.5 names the last seams — add the tests your remaining gaps owed

The designer froze your delivery 1c at 2026-10-27T16:49:09Z (those 11 files are now the frozen set; do not edit them). §16.5 (the change is `.b2-spec-v3.2-16c.diff`; the copy's spec is updated) names the sequencer CLI, the pair-receipt flag, the after-load census, the ledger key, the pins / expected-argv seam, the ON argv comparison, the operator email, the `RECORD` fixture seam and R1's shared key, and gives `a4_window_problems` its `a4_gate` argument. Rulings on your §4: (2) the ON argv comparison is as §16.5 says; (3) R1's ON commit differs by exactly the restore; (4) R1 shares one key across its two legs.

Write the tests your gaps G1–G8 owed, in NEW files only: `test_b2_frozen_add_<area>.py` (e.g. `_sequencer`, `_pair`, `_census`, `_ledger`, `_a4`, `_scrub`, `_record`), with any new fixtures in a new `b2_frozen_add_support.py` (import the frozen `b2_frozen_support.py`, do not change it), plus `test_b2_frozen_add_support_check.py` validating every new fixture on the baseline (must pass there). If a frozen test now contradicts §16.5, do not edit it: list it in your report with the reason.

Same rules as before. Run your new files and the frozen set on the baseline; report as before.
