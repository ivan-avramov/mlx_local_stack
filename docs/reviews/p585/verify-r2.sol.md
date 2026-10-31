1. Location: `benchmark/bench/proc_guard.py:46-69,372-373`  
Severity: major  
Evidence: confirmed by source trace and reproduction  
Resolution: not resolved  
Problem: `Process.__init__` reads `_proc.create_time(monotonic=True)` before the subclass wrappers run. Likewise, `process_iter()` constructs base objects before `_read_safe()` changes their class. Both paths can emit raw `SystemError`.  
Failure scenario: a process exits during `g.get(pid)` or scan object construction; the guard receives `SystemError` and the monitor dies.  
Proposed change: guard construction itself and make scan acquisition consume constructor failures per process. Add tests patching `create_time` before lookup/iteration.

2. Location: `benchmark/bench/proc_guard.py:42,360`  
Severity: major  
Evidence: confirmed by source trace and reproduction  
Resolution: not resolved  
Problem: initialization calls `psutil.Process().parents()`, which is absent from `_READS`. `parents()` recursively creates plain `Process` objects and reads their `ppid`/creation time; even subclassing the initial object leaves ancestor reads unwrapped.  
Failure scenario: an ancestor changes state during traversal and its `ppid()` raises `SystemError`, aborting guard construction.  
Proposed change: invoke `parents()` through a wrapper covering the whole operation, or traverse ancestors explicitly with guarded reads. Test both the initial process and a later ancestor failing.

3. Location: `benchmark/bench/proc_guard.py:372-373`; `benchmark/bench/tests/hermetic_scan.py:38-42`  
Severity: major  
Evidence: confirmed by source trace and reproduction  
Resolution: not resolved  
Problem: caller-supplied `scan` and `get` results bypass `_read_safe`. The documented `FamilyScan` returns ordinary cached `psutil.Process` objects, so guard reads other than `_cmdline()` can still emit `SystemError`; it also performs an unguarded `ppid()` internally.  
Failure scenario: `_processes()` receives a base process from a custom scan and `status()` raises `SystemError`.  
Proposed change: wrap results from both default and supplied lookup/scan functions. Separately handle `SystemError` inside `FamilyScan` before it returns.

4. Location: `benchmark/bench/proc_guard.py:52-60,66-69`  
Severity: major  
Evidence: confirmed by psutil source and reproduction  
Resolution: not resolved  
Problem: the generated wrappers discard `cache_activate` and `cache_deactivate` attributes from psutil’s decorated `memory_info`, `ppid`, and `uids` methods. Consequently `oneshot()` and `repr()` raise `AttributeError`. Because the scan mutates psutil’s global cached objects, later consumers such as `psutil.process_iter(attrs=...)` also fail.  
Failure scenario: after a guard scan, a provenance lookup using `process_iter(["pid", "cmdline"])` invokes `as_dict()`/`oneshot()` and crashes.  
Proposed change: preserve wrapper metadata with `functools.wraps(base)` or explicitly copy the cache-control attributes. Test `oneshot()`, `repr()`, and cached `process_iter(attrs=...)`.Review completed and findings were delivered. One panel member succeeded; two were unavailable due CLI config-write restrictions. No follow-up action is needed.
