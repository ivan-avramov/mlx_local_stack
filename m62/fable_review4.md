# Cold review of M62 spec revision 4 (f73cd6a) — claude-fable-5-1, 2026-10-09

Verdict: approve with changes (F1–F5 before implementation; F6–F12 text edits). Folded into revision 5 (42ff111).

Part A: P28 PARTIAL (no sampling protocol; idle+none causal) · P29 RESOLVED · P30 RESOLVED · P31 RESOLVED · P32 PARTIAL
(completed-but-unpublished final message, unknown/partial lines, pending grade at exit) · P33 RESOLVED · P34 PARTIAL
(over-broad forbidden additions; two graders at terminal) · P35 RESOLVED · P36 RESOLVED · P37 RESOLVED · P38 PARTIAL
(manifest lacked export shas; fixtures under-specified) · P39 RESOLVED.

Data: 454 rows/400 matched/374 valid passes; event types only tool_use/step_start/step_finish/text; reasoning = 0 in
all 3,603 step_finish; export tokens == live by messageID 3,328/3,328; 374/374 passes omit final step_finish; 18 stopped
rows end error.type=aborted; passing max 26 requests, event-order identical run 2, single request 35,771, item 38,657
(+ final export message ≈ 39,142).

F1 MAJOR silence: single sample can false-abort (step capture/publish gap) → 60 s cadence, 3 idle samples, client_exit_hang.
F2 MAJOR per-step_finish order (charge, enqueue capture boundary=j, then checks).
F3 MAJOR gate-stop may leave a completed-but-unpublished final message (usage+finish, no error) → allow and charge; await
   pending grade at exit; torn tail after kill.
F4 MAJOR unknown event types (reasoning, error) must not abort; duplicate = (type, part.id).
F5 MAJOR forbidden additions over-reach for Go (scratch *_test.go, nested go.mod in a passing go/markdown row) → only
   TestMain in package, root go.mod/go.work/vendor.
F6 MINOR passed from the structured final grade under tg1; drop legacy grader.
F7 MINOR output = tokens.output + tokens.reasoning (opencode output is visible − reasoning).
F8 MINOR K identity = (tool, canonical JSON input); errored calls count; mid-request.
F9 MINOR cancel bound max(300 s, prefill floor × prompt).
F10 MINOR exact fixtures: kindergarten (looping, request 15); alphametics (stalled, completed request 40); book-store no stop.
F11 MINOR pending definition; slow grading must not defer stalled; grading-worker death → abort.
F12 MINOR strict new-minimum progress departs from recorded Phase H direction → operator sign-off.
F13 NIT 483 step_starts/482 completed; grader timeouts; sweep must exclude operator shells; 39,142 includes export message.
F14 NIT go test -json trusts binary output (accepted residual).
