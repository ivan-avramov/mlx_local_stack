Continue the M61 implementer job (task: $STACK_WORKDIR/m61/build.prompt.md — re-read it and the spec).
Ruling on your question (APPROVED, your interpretation):
- `--scaffold opencode-v2` without a system file: the exact M59 carrier bytes and the exact M59 `scaffold_policy_sha256` recipe
  (same inputs, same value). Pin both with tests.
- Record the new fields (`scaffold`, `carrier_source`, `carrier_source_sha256`, `agent_system_file`, `agent_system_sha256`) in the
  manifest and rows for EVERY scaffold and resume-check them for every scaffold; they enter `scaffold_policy_sha256` only for the
  web scaffold and for any run with a system file.
- `probe_code_sha256` changes normally with the code; do not pin it.
I am amending the spec text accordingly. Do not label your points with P-ids (use Q1, Q2, …). Proceed with the full build now.
