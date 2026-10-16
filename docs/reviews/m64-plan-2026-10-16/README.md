# M64 plan review — 2026-10-16 (harness versioning, M64 design, guard residual, aborted chain)

Lead (m5max-128 session) ↔ two cold reviewers until all three agree; then the operator rules. Files:

| file | what |
|---|---|
| `plan_v1.md` | first plan: P315 float harnesses, P316 M64 shape, P317 guard residual, P318 aborted chain |
| `round1.prompt.md` | the round-1 prompt (wrapper + plan v1) |
| `round1.codex-gpt-6.1-sol.md` | codex `gpt-6.1-sol` (m5max): AGREE WITH CHANGES |
| `round1.cursor-gpt-5.6-sol-high.md` | Cursor `gpt-5.6-sol-high` (m5max-128): DISAGREE |
| `plan_v2.md` | revised plan: E1 decision epochs, E2 M64 design, G1 guard (P317 withdrawn), R1 resume |
| `round2.prompt.md` | round-2 prompt = wrapper + both round-1 reviews + plan v2 (self-contained) |
| `round2.codex-gpt-6.1-sol.md` | codex round 2: AGREE WITH CHANGES |
| `round2.cursor-gpt-5.6-sol-high.md` | Cursor round 2: DISAGREE (G1 residual; E2 token accounting + inference gate) |
| `plan_v3.md` | revised plan after round 2 (E1 epochs w/o ranking transport; E2 spec requirements; G1 + G2 split; R1 checklist) |
| `round3.prompt.md` | round-3 prompt (reads v2, both round-2 reviews from the repo; v3 inline) |
| `round3.codex-gpt-6.1-sol.md` | (to add, from m5max) |
| `round3.cursor-gpt-5.6-sol-high.md` | (to add, from m5max-128) |

## To run on m5max (codex; no ssh from the other box) — replace <N> with the current round (now 3)

```
cd ~/ws/mlx_local_stack && git fetch origin && git switch m64-plan-review && git pull --ff-only
. ~/.config/mlx_local_stack/config.sh; mkdir -p "$STACK_WORKDIR/review-tmp"
D=docs/reviews/m64-plan-2026-10-16
TMPDIR="$STACK_WORKDIR/review-tmp" codex exec --ephemeral --ignore-user-config -m gpt-6.1-sol -s read-only \
  --skip-git-repo-check -o "$D/round<N>.codex-gpt-6.1-sol.md" - < "$D/round<N>.prompt.md" > /dev/null 2>&1; echo rc=$?
git add "$D/round<N>.codex-gpt-6.1-sol.md" && git commit -m "docs: M64 plan review round <N> — codex gpt-6.1-sol" && git push
```

Run it from the repo root on the `m64-plan-review` branch (the reviewer reads the code there). The output file is
the reviewer's final message only. Before committing, check it holds no absolute home paths (public repo); the
pre-commit naming/PII hooks also check. The throwaway worktree created earlier on m5max
(`$STACK_WORKDIR/worktrees/review-1016`) can be removed: `git worktree remove "$STACK_WORKDIR/worktrees/review-1016"`.

## Status

- Round 1: both reviewers rejected P317 (an unreadable-order process can be ours yet untracked/path-negative) and
  asked for decision epochs, an explicit M64 estimand, C154 censoring handling, balanced arm order, an `ArmAdapter`
  contract and pre-registered power. Plan v2 adopts them.
- Round 2: pending on both boxes. Live state on m5max-128: `$STACK_WORKDIR/c144-base` aborted 2026-10-16 05:15Z (rc 2,
  guard residual pid 89820); not resumed pending the operator's ruling on R1.
