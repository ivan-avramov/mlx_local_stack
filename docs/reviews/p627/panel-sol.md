P1
- Location: `benchmark/bench/local_gate.py:310-313`
- Severity: blocker
- Evidence: confirmed
- Problem: The longest existing prefix can mistake a class component for a module.
- Concrete failure scenario: For `pkg.tests.test_k.TestKlass::test_m`, live-only `pkg/tests/test_k/TestKlass.py` is selected and marked absent-allowed. This directly fails the frozen test at `.p627-material/test_local_gate_absent_skips.py:172-180`.
- Proposed change: Derive the module boundary from authoritative collection rules or metadata; fail closed when class/module interpretation is ambiguous.

P2
- Location: `benchmark/bench/local_gate.py:368-395`
- Severity: blocker
- Evidence: confirmed
- Problem: Failed or errored testcase IDs can be reclassified as absent, violating C277.
- Concrete failure scenario: JUnit contains a failed `pkg.tests.test_a::test_one`, pytest reports rc 0, and `pkg/tests/test_a.py` exists only live. The candidate removes it from `unexplained` and emits PASS.
- Proposed change: Parse all JUnit testcase IDs and apply absent-allowed only when the ID does not appear anywhere in JUnit. Add live-only failed/error tests.

P3
- Location: `benchmark/bench/local_gate.py:310-313`
- Severity: major
- Evidence: confirmed
- Problem: `Path.is_file()` follows file and directory symlinks, so “under live” can resolve outside the repository.
- Concrete failure scenario: Live `pkg/tests/test_a.py` symlinks to an external regular file while scratch lacks the path; the gate permits PASS.
- Proposed change: Reject symlink components or verify the resolved file remains beneath the resolved repository root. Test terminal and ancestor symlinks.

P4
- Location: `benchmark/bench/local_gate.py:330-372`
- Severity: minor
- Evidence: confirmed
- Problem: `baseline_skips_absent` is not always present as required.
- Concrete failure scenario: An earlier gate step fails, bypassing initialization. This contradicts the frozen test at `.p627-material/test_local_gate_absent_skips.py:114-117`.
- Proposed change: Initialize `baseline_skips_absent=[]` in the initial receipt.

P5
- Location: `benchmark/bench/local_gate.py:390-393`; `docs/specs/p627-gate-absent-skips.md:13-19`
- Scope request
- Evidence: confirmed
- Problem: Neither candidate nor v1 distinguishes “added later” from rename, deletion/recreation, unrelated branch history, or an untracked live file. The formal v1 state rule permits all of these.
- Concrete failure scenario: A matching untracked file is created in live, an old SHA receives a PASS receipt, then the file is removed; the unchanged policy digest still permits that receipt at push time.
- Proposed change: If historical “added later” provenance is intended, revise v1 to require a tracked live blob, ancestry from the gated SHA, and durable provenance reflected in receipt validation or policy identity.
