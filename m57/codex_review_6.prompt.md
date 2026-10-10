Cold adversarial CODE review, ROUND 2, of a three-repo change. Read-only: modify nothing, load no real models, run no Metal/GPU
workload and no servers. If your sandbox cannot run pytest, say so once and review by reading.

SPEC (authoritative): docs/specs/m57-attention-policy.md in this repo — INCLUDING the binding section "Amendment 1" (policy rules 5
and 6, the non-GPU refusal, Fork F1-F6, Router, Stack S1-S5), written after round 1.

UNDER REVIEW (branch tips)
1. Fork ../mlx-vlm, branch `m57-attention-policy` @ 727e8d6a: commits 7619beb3 (policy), c1504381 (lazy embeddings), 727e8d6a
   (round-1 fixes) on top of 21d62fe6 (out of scope). `git -C ../mlx-vlm diff 21d62fe6 m57-attention-policy`; the fix alone:
   `git -C ../mlx-vlm show 727e8d6a`.
2. Router ../mlx-serve, branch `m57-attention-policy` @ 7be6bfd (30be27c + 7be6bfd). `git -C ../mlx-serve diff main m57-attention-policy`.
3. Stack (this repo), worktree branch `worktree-agent-a6011ca833d3e6e68` @ ced1cae (ddd278f, merge of main, ced1cae).
   `git diff main ced1cae -- benchmark/`.

FACTS FROM THE LIVE GATE on the real server (branch tips, registry `attention_policy: fused_v1`, MLX 0.32.2, GPU): startup log
"self-test: 12 forced calls in 0.34s"; a cold 20819-token prompt reports `timings.sdpa_forced=656, sdpa_auto=16` (41 chunks x 16
attention layers forced; the final single-token step auto); a 528-token prompt reports 16 / 32; short cached continuations report
0 / 48; 22 requests with varied tails all returned 200; with `lazy_prompt_embeddings: true` the peak fell by 0.21 GB at 21K tokens
(the size of the prompt's embeddings) and counters were unchanged. A no-model GPU parity run (fused vs unfused vs an fp32 CPU
reference, bf16, query lengths 9/127/128/512 x keys 4096/131072/262144) passed all 24 cells.

REVIEW ONLY
(i)  whether each Amendment 1 item is REALLY satisfied at the tips (not just claimed) — in particular: rule 5 (single-sequence only;
     the implementer excludes any cache with a `left_padding` attribute and runs the row recursion under `policy.suspended()` — is
     `suspended()` safe against exceptions, re-entrancy and other threads/requests using the same model instance?), rule 6, the
     non-GPU refusal, counters omitted from the response bytes under `auto` (check the serializer for every response shape that
     embeds timings, streaming and non-streaming, OpenAI and Anthropic endpoints), the self-test (it now forces query lengths 22,
     127, 128, 512 because 9 is below the 2**28 rule at 262144 keys — is the probed dtype really the attention dtype?), the lazy
     flag default-off and byte-identical, S1-S5;
(ii) defects INTRODUCED by the fix commits;
(iii) anything that would make a production request fail, change `auto` behaviour, or record false provenance.
Known and accepted, do not re-report: the MTP capture flow with lazy embeddings is not driven by a test (lazy is opt-in and gets its
own qualification arm); the pre-existing `draft_kind` tripwire still uses the old first-match worker lookup; the batched
(non-session) path reports no counters.

DELIVER (markdown, ids W1, W2, ... most severe first, repo + file:line each): what is wrong, concrete scenario, consequence, fix.
Then one line per Amendment 1 item (rules 5, 6, non-GPU, F1-F6, Router, S1-S5): satisfied / not, with evidence. Verdict per repo:
SHIP / FIX-THEN-SHIP / REWORK. Under 1100 words. No praise.
