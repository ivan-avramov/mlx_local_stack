Same cold reviewer, read-only, round 3. Your rounds are at $STACK_WORKDIR/m48/codex_review.md
and codex_review2.md. The author committed a further fix (`git -C mlx-vlm show HEAD`, on top of bb59774a).
Verify P4, P5, P9 and P8 against that commit with CPU reproductions using `mlx-vlm/.venv/bin/python` (mlx imports;
the pick's tokenizer is in ~/.cache/huggingface, see tests/test_prompt_end_retention.py::test_shipped_qwen_template_boundary_and_canonical_suffix):
- P5: is the boundary design sound — the server's `_retention_boundary` (placeholder answer "x") vs the real
  answer's common prefix; can they differ? What happens if the real echo's common prefix is LONGER than the
  boundary (e.g. a client that echoes reasoning_content)? Confirm with the shipped template, thinking ON, that
  retire-at-boundary + canonical suffix gives a byte-exact match through the assistant turn, and that an
  edited user turn still rewinds to the pinned anchor.
- P4: the dispatch mismatch path now clears the session; any remaining path that publishes an inconsistent one?
- P9: pin promotion via `capture_states(..., pinned=True)` on an existing offset; check FIFO eviction keeps it.
- P8: which of your original repros are now covered by the committed tests; what is still only live-testable.
- ar.py landing: `retain_at_offset` interplay with the anchor landing (`snapshot_at_offset`) when both targets
  fall in the same chunk, with `checkpoint_lengths`, and on the pre-prefill (cache-offset) path.
Flag anything NEW. End with a per-finding table and a yes/no: fit to bump into the stack for the live gates?
