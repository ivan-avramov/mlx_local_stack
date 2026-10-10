# M60 judge pass — exact, ordered commands (no GPU; run after `run_m60.py` exits 0)

Spec: `$STACK_REPO/docs/specs/m60-shipped-state-certification.md` ("Judge pass"). Pair: `m40on` vs `m60ship`,
same model. 70 pairs (40 items + 30 anchors) × 2 orders × 3 judges = 240 item + 180 anchor verdicts.
Never pooled with M38 or M40 verdicts. Nothing under `benchmark/results/judge_c_v1/` or `judge_m40/` is written:
every command carries an explicit `--out` (the tool's default `--out` is `judge_c_v1` and it rewrites
`pair_manifest.jsonl` there on EVERY invocation, including `--dry-run`).

Command shapes below were verified 2026-10-06 against the existing `m38`/`m40on` tunes in a scratch `--out`
(70 pairs; 280 packets = 60 anchor + 80 item per Claude judge; ingest and gate ran; the gate tool reproduced
the committed M40 gate metrics and ranking exactly). They have NOT been run on `m60ship` (no rows yet).

```sh
. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
cd "$STACK_REPO/benchmark"
M=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
OUT=results/judge_m60/$M                 # canonical verdicts / gate / ranking
PK=$STACK_WORKDIR/m60/packets            # private packets + manifest (names the arms: judges never read it)
S1=$STACK_WORKDIR/m60/judge_stage1       # scratch for the anchors-only gate
PY=../.venv-bench/bin/python
COMMON="--models $M --pair-tunes m40on m60ship --anchors results/judge_c_v1/pairs.jsonl --out $OUT"
```

## 0. Preconditions (refuse to start otherwise)

- `$STACK_WORKDIR/m60/run_m60.rc` is `0`; `summary.json` has `cjudge.shared_converged_with_m40on >= 38`.
- If `summary.json` `cjudge.length_ratio_vs_m40on.in_band` is false: the length-adjusted margin is owed
  beside the raw one (step 7).
- `git -C "$STACK_REPO" status --short benchmark/results/judge_c_v1 benchmark/results/judge_m40` is empty
  before AND after every step.

## 1. Pair manifest + first-pair prompts (no judge call)

```sh
$PY -m bench.run_judge_pairwise $COMMON --dry-run
```
Expect `70 pairs (40 candidate + 30 anchor)`. Fewer than 38 candidate pairs → stop.

## 2. Record the panel actually used (the tool's judge labels are fixed strings)

The verdict rows will say `opus` / `sonnet` / `codex:gpt-5.6-terra:medium`. The Claude subagent judges are NOT
the model versions gated in M38/M40. Write the real identities before any call:

```sh
cat > $OUT/panel.json <<'EOF'
{"codex:gpt-5.6-terra:medium": {"transport": "codex exec in-process", "model": "gpt-5.6-terra", "effort": "medium"},
 "opus": {"transport": "claude-code-subagent", "model": "<exact model id the subagent ran on>"},
 "sonnet": {"transport": "claude-code-subagent", "model": "<exact model id the subagent ran on>"},
 "note": "labels are the tool's fixed judge names; never pooled with M38/M40 verdicts"}
EOF
```

## 3. Export blind packets for the two Claude judges (no judge call)

```sh
$PY -m bench.run_judge_pairwise $COMMON --judges opus sonnet --export-packets $PK --batch-size 10
$PY - "$PK" <<'EOF'      # stage lists: anchors first, items only after the gate passes
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1] + "/manifest.jsonl")]
for judge in ("opus", "sonnet"):
    for stage, keep in (("anchors", lambda r: r.get("anchor_type")), ("items", lambda r: not r.get("anchor_type"))):
        paths = [r["path"] for r in rows if r["judge"] == judge and keep(r)]
        open(f"{sys.argv[1]}/{judge}.{stage}.txt", "w").write("\n".join(paths) + "\n")
        print(judge, stage, len(paths))
EOF
```
Expect `opus anchors 60`, `opus items 80`, `sonnet anchors 60`, `sonnet items 80`.

## 4. Stage 1 — anchors only

- Claude judges: one blind subagent per ≤ 20 packets, model `opus` for `opus.anchors.txt`, `sonnet` for
  `sonnet.anchors.txt`. Give the subagent ONLY: the text of `$PK/README_JUDGE.md` and its explicit packet paths.
  It must not read `manifest.jsonl`, the `*.txt` stage lists, this file, the repo, or another packet's verdict.
  It writes `<pkt>.verdict.json` beside each packet. No retries beyond re-issuing a packet whose verdict file
  is missing or unparseable.
- Codex judge (not stageable; runs all 70 pairs × 2 orders = 140 calls, resumable, escalates on transport failure):

```sh
$PY -m bench.run_judge_pairwise $COMMON --judges "codex:gpt-5.6-terra:medium" --allow-single-family \
    > "$STACK_WORKDIR/m60/judge_codex.log" 2>&1
```
  Exit 0 required. Do not run `scripts/stack_stop.sh` while it runs (its process sweep matches text in argv).

- Ingest the anchor verdicts and compute the gate on ANCHOR ROWS ONLY, in scratch (the gate tool writes a
  `ranking.json` whenever the gate passes — with anchors only it is meaningless; it must never land in `$OUT`):

```sh
$PY -m bench.run_judge_pairwise --ingest-packets $PK --out $OUT
mkdir -p $S1 && $PY - "$OUT" "$S1" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1] + "/verdicts.jsonl")]
anchors = [r for r in rows if r.get("anchor_type")]
open(sys.argv[2] + "/verdicts.anchors.jsonl", "w").write("".join(json.dumps(r) + "\n" for r in anchors))
by = {}
for r in anchors:
    by[r["judge"]] = by.get(r["judge"], 0) + 1
print(by)
EOF
$PY -m bench.judge_gate --pairs $OUT/pair_manifest.jsonl --verdicts $S1/verdicts.anchors.jsonl --out $S1
```
Expect 60 anchor rows per judge (180). `gate=PASS` → stage 2. `gate=FAIL` (exit 1) → STOP: no item packet
is issued, no item verdict is read, report the six metrics; revising the panel is an operator decision.
Delete `$S1/ranking.json` unread.

## 5. Stage 2 — item packets (only after stage 1 PASS)

Same subagent protocol over `opus.items.txt` and `sonnet.items.txt` (80 packets each). Then:

```sh
$PY -m bench.run_judge_pairwise --ingest-packets $PK --out $OUT      # expect 0 missing
```

## 6. Gate + verdict of record

```sh
$PY -m bench.judge_gate --pairs $OUT/pair_manifest.jsonl --verdicts $OUT/verdicts.jsonl --out $OUT
```
Writes `$OUT/gate.json` (must be PASS with all 420 rows; exit 1 = no ranking) and `$OUT/ranking.json`.
Read from `ranking.json` → the single pair `…@m40on__…@m60ship`: `preference_rate_model_1` (for `m40on`),
`ci`, `p_value`, `family_splits`, `n_items`, `mde`. Pre-registered: FAIL if `m40on` is preferred with p < .05
(CI of the `m40on` preference rate entirely above 0.5); otherwise "no detectable drift at n=40 (MDE ±20 pp)",
an underpowered PASS. Null-verdict share above the tool's warning threshold for any judge → investigate first.

## 7. Length-adjusted margin (only if the token-length ratio is outside [0.8, 1.25])

`bench/judge_length_diag.py` — read its header for the invocation; report the adjusted margin beside the raw one.

## 8. Record

Token/call counts into `$OUT/costlog.json` (subagent totals are approximate — say so). Verdicts, gate, ranking,
pair manifest and `panel.json` are committed with the certification commit; `$PK` and `$S1` stay private.
