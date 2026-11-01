- Location: `material/proc_guard_after.py.txt:61-70, 480-550, 825-831, 1066-1129`
  Severity: major
  Evidence: confirmed (source-traced)
  Problem: `_scan()` silently drops an unconstructable tracked parent without preserving its PID as an ownership obligation. Its visible children therefore cannot join the ancestry closure.
  Concrete failure scenario: tracked parent P forks C; constructing P raises `SystemError`, while C is listed with `ppid=P`. Because P is absent from `alive`, C is not tracked. P exits before the next tick and C changes cwd/argv away from item roots. Cleanup can skip C as same-session via `_sweep_excluded`, leaving it alive and reporting clean.
  Proposed change: retain failed-construction PIDs. When one matches a tracked identity, conservatively record all listing descendants whose ancestry reaches that PID as unreadable descendant obligations, including during cleanup confirmation scans.

- Location: `material/proc_guard_after.py.txt:347-351, 591-595, 731-737`
  Severity: minor
  Evidence: confirmed (source-traced)
  Problem: A3 is false. Adding raw `SystemError` to `_transient` catches exceptions from non-psutil code inside broad handlers. In particular, `self.scrub()` and `after_signal()` are caller callbacks.
  Concrete failure scenario: `p.terminate()` succeeds, then `after_signal(token)` raises `SystemError`. The exception is swallowed, the process is omitted from `signalled`, and `verify_gone([])` succeeds despite the cutoff commit failing.
  Proposed change: translate `SystemError` to `AccessDenied` only immediately around psutil operations; keep callbacks and guard bookkeeping outside those handlers.
