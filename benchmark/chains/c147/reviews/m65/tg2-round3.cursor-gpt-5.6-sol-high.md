T14–T26 verification: T14–T16 and T18–T26 are addressed at design level. T23–T25 remain correctly marked as build-time verification. T17 and T22 retain gaps below.

T27 — high — `docs/specs/m65-tg2-corpus.md:59-64`  
Failure: C++ reference files cannot map “by stem.” Corpus examples are named `.meta/example.cpp` and `.meta/example.h`, while destinations are exercise-named files such as `gigasecond.cpp` and `gigasecond.h`. Three exercises—including `binary-search-tree`—have only `example.h` but two solution paths. A literal implementation cannot construct references and may exclude all C++ items or overwrite the wrong path.  
Fix: map by file type to the unique solution destination (`example.cpp` → solution `.cpp`, `example.h` → solution `.h`), retain unmatched prepared stubs for header-only references, and reject ambiguous or missing destinations.

T28 — high — `docs/specs/m65-tg2-corpus.md:28-30,116-123`  
Failure: the panel is deferred until the M64 panel exists, but tg2 completion/reporting is not gated on it. The chain can therefore produce a final model comparison using execution metrics alone, contrary to the mandatory subjective-quality rule. A hash without retained exact bytes would also be insufficient for later reconstruction.  
Fix: retain content-addressed snapshots of the exact final graded implementation tree and state that no final tg2 comparison or recommendation is complete until the two-provider panel has run; otherwise report the benchmark as pending subjective review.

Build notes, non-verdict-holding: implement and test the new tg2 identity closure and universe loader; validate phase evidence for all four graders; generate the nested `rust/macros/tests/invalid/Cargo.lock`; cover both Java `@Disabled` forms; and exercise all three Gradle dependency closures offline.

VERDICT: AGREE WITH CHANGES T27,T28
