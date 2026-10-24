# First sol attempt (truncated in transit: only findings 26–33 arrived; the full re-dispatch is design-round1.cursor-gpt-5.6-sol-high.md)

26. Location: §3 `client_inactivity`; §6 zero failures
   Severity: blocker  
   Problem: A scored `client_inactivity` can terminate an active stream and produce `Request failed: stream_closed_before_completion`. The failed line has no session ID and the interrupted request has no client `request_usage`.  
   Concrete failure scenario: A legitimate scored non-convergence becomes systemic under §6, or the unfinished request disappears from reconciliation.  
   Proposed change: Define a narrow window-bound terminal-disconnect record that reconciles the interrupted client event to the server failure; reject every other failure.

27. Location: §2 exit checks; §5 schedule
   Severity: major  
   Problem: tg1 schedules are currently neither frozen nor checked by `check_realized`; `freezes_schedule` covers only `blocks` and `tg2_tier`. Current tg1 also sorts sampled pilots/full lists.  
   Concrete failure scenario: The correct item set runs in the wrong order or with a duplicate, while argv-oriented tests pass.  
   Proposed change: Freeze a P426 schedule hash before launch and maintain an ordered realized-slot ledger, including DNF placeholders.

28. Location: §7 watcher; §10 tests
   Severity: major  
   Problem: The current watcher cannot read `chain.json` and writes only the first power failure, with no complete tick history, PID/create-time binding, finalized battery interval, or successful-exit receipt.  
   Concrete failure scenario: The watcher crashes after one valid tick and absence of a failure file is interpreted as speed-valid.  
   Proposed change: Define a fail-closed authoritative receipt containing driver identity, every tick, progress snapshots, start/end, finalized `pmset` intervals, and watcher exit state.

29. Location: §7 speed validity
   Severity: major  
   Problem: The specification does not propagate invalid speed evidence across an ON/OFF session pair.  
   Concrete failure scenario: B6 computes a ratio using valid ON measurements against power-invalid OFF measurements.  
   Proposed change: Exclude both arms of an s1 or s2 speed pair when either watcher receipt is invalid; label a lone valid session descriptive and not order-balanced.

30. Location: §4 runtime environment; §9 public evidence
   Severity: blocker — sensitive area: credentials and file permissions  
   Problem: The model-facing opencode process inherits ambient and `.env` variables. A shell tool can expose credentials before downstream scrubbing.  
   Concrete failure scenario: The model runs `env` or prints an authorization header; the secret reaches transcripts and public staging.  
   Proposed change: Launch probes with a minimal allowlisted environment and a dedicated non-production local credential; redact exact injected values, reject unknown binaries/symlinks, and keep raw staging under restrictive permissions.

31. Location: §1 pilot gate; §9 timeout derivation
   Severity: major  
   Problem: “Both VALID” does not say whether pilots may contain DNFs or speed-invalid observations, despite using their walls to set full-run deadlines. The pilot samples only Python.  
   Concrete failure scenario: Three usable Python observations produce an optimistic timeout that immediately overruns on Go.  
   Proposed change: Require five reconciled, zero-DNF, speed-valid pilot items for timeout calibration, or define a conservative recorded fallback for missing/invalid observations and Go.

32. Location: §2 “nothing busy … before every invocation”
   Severity: major  
   Problem: After router startup, a literal busy-process census sees the chain’s own router and worker; broad exemption would admit foreign workloads.  
   Concrete failure scenario: Every post-load invocation refuses, or another model worker runs concurrently undetected.  
   Proposed change: Define “no foreign busy process” using exact recorded PID/create-time identities and descendants; test owned and foreign processes separately.

33. Location: §3 makeup schedule
   Severity: major  
   Problem: “DNF items for both arms” does not specify union versus intersection.  
   Concrete failure scenario: ON DNFs item A and OFF DNFs item B; an intersection-based implementation schedules nothing.  
   Proposed change: Use the union of DNF occurrences, rerunning each occurrence under both arms with its original session/language/item/seed identity, in a separate namespace excluded from primary inference.
