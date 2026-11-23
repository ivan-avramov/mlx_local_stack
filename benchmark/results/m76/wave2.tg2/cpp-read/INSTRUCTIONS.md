# Failure-mode read: nine C++ coding-agent packets

Each packet `P01.md` … `P09.md` holds TWO independent runs of the same coding agent (same model) on the same C++ exercise. In every packet exactly one run is counted as a FAIL by the benchmark (it failed the hidden tests, or the harness stopped it as stalled / looping even if its code passed). The runs differ only in an internal serving setting you are not told; do not try to guess it.

Read each packet in full and write your verdict for it. For each packet produce one JSON object:

{
  "packet": "P0n",
  "failing_run": 1 or 2,
  "failure_class": one of "premature_completion" (declared done without verifying / with failing tests), "compile_error", "logic_error", "spec_misread", "tool_or_environment", "stall_or_loop_with_correct_code", "stall_or_loop_without_correct_code", "degraded_generation", "other",
  "root_cause": "2–4 sentences, citing what in the transcript shows it",
  "degraded_generation_signs": {"run1": [..], "run2": [..]} — short quotes of anything that looks like degraded text generation: incoherent or garbled text, malformed identifiers / tokens, repeated junk, or contradicting / forgetting information that is visible earlier in the same session; [] when none,
  "ordinary_variance": "yes" | "no" | "unclear" — would a competent agent plausibly make this same mistake on another attempt (yes), or does it look like a capability or coherence deficit (no)?,
  "ordinary_variance_why": "one sentence"
}

Then one final JSON object: {"summary": "3–5 sentences: do the failing runs share a pattern; is any failure different in kind from ordinary agent mistakes?"}.

Base every claim on the packet text. Do not modify the packet files.
