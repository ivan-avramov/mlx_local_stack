#!/usr/bin/env bash
# P1a — opencode go/no-go smoke. Gates ~24h of harness-gradient work (plan task 11).
#
# The plan asks this to verify (a) the request reaches :8000, (b) the tuned sampling actually
# lands -- "read back from the worker log, not assumed" -- and (c) a scriptable non-interactive
# mode exists. One of those three cannot be done as written, and the reason matters:
#
#   THERE IS NO RESOLVED-SAMPLING LOG LINE. AGENTS.md (FU-2) says "resolved sampling is logged at
#   INFO", but the fork has no such line: grepping mlx-vlm/mlx_vlm/server/generation.py finds no
#   log of the merged params, and the live worker logs confirm it -- mlx-serve sends worker STDOUT
#   to DEVNULL and only stderr to $TMPDIR/mlx-manager-logs/<model>.log (process_manager.py:387),
#   and those files contain no sampling fields at all.
#
#   Worse, a resolved-sampling line would NOT answer the question even if it existed. Under FU-2
#   the registry supplies generation_defaults for every field a request OMITS, and opencode's
#   configured values are IDENTICAL to the registry's. So "resolved temperature = 0.4" is what you
#   see whether opencode forwarded 0.4 or sent nothing at all. The readback has to use a value that
#   DIFFERS from the registry default, and be observed in behaviour.
#
# So sampling-landing is tested BEHAVIOURALLY, with distinctive values whose effect is visible in
# the router's own metrics line (which logs `completion=<n>`):
#
#   Gate B -- options.max_tokens = 7. Forwarded => the reply truncates at ~7 tokens. Not forwarded
#             => the registry default 102400 applies and the reply runs long. This exercises the
#             STANDARD AI-SDK param path (max_tokens -> maxOutputTokens).
#   Gate C -- options.thinking_budget = 16. Forwarded => the worker force-injects </think> almost
#             immediately, so completion is tiny. Not forwarded => 81920 applies and a normal
#             thinking trace appears. This exercises the NON-STANDARD extras path.
#
# B and C are separate mechanisms and can disagree: the AI SDK maps max_tokens itself, whereas
# thinking_budget / enable_thinking / min_p must ride through as pass-through body params. C is the
# one the campaign depends on (thinking is enabled for all tests), so a B-pass/C-fail is a NO-GO
# for tuned comparisons through opencode, not a partial success. That distinction is the whole
# point of running this before spending the 24h.
#
# NOTE this smoke changes only the DEPLOYED opencode config (~/.config/opencode), never the repo's
# generated one, and restores it from a backup at the end.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH
R=$HOME/ws/mlx_local_stack
CFG=$HOME/.config/opencode/opencode.json
BAK=/tmp/opencode.json.p1a-backup
RLOG=$R/logs/main_model.log
MODEL=Ornith-1.0-35B-mlx-uniform-4bit
OUT=/tmp/p1a_opencode_smoke.log
PROMPT="Reply with exactly the single word: OK"

exec > >(tee -a "$OUT") 2>&1
say(){ echo "[$(date +%H:%M:%S)] $*"; }

# --- read the router's metrics line for requests appended AFTER a recorded line offset ----------
# `completion=` comes from mlx-serve's own metrics line, so this needs no worker log.
report_since() {   # report_since <line_offset> <label>
  local off="$1" label="$2"
  awk -v n="$off" 'NR>n' "$RLOG" \
    | grep "/v1/chat/completions" \
    | sed -n "s#.*/v1/chat/completions \([0-9]*\).*model=\([^ ]*\).*prompt=\([0-9]*\) | completion=\([0-9]*\).*#    ${label}: status=\1 model=\2 prompt=\3 completion=\4#p"
}

set_opt() {  # set_opt <key> <json-value>  (or: set_opt <key> DELETE)
  python3 - "$CFG" "$1" "$2" <<'EOF'
import json, sys
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(path))
opts = d["provider"]["mlx-local"]["models"]["Ornith-1.0-35B-mlx-uniform-4bit"].setdefault("options", {})
if val == "DELETE":
    opts.pop(key, None)
else:
    opts[key] = json.loads(val)
json.dump(d, open(path, "w"), indent=2)
print(f"    set options.{key} = {val}")
EOF
}

run_gate() {  # run_gate <label>
  local label="$1"
  local off; off=$(wc -l < "$RLOG")
  cd "$R" || return 1
  # opencode's small_model points at :8092 (task model), which the LEAN bench router does not
  # start -- any title/summary call will fail. That is expected here and must not fail the gate;
  # only the :8000 chat call is being measured.
  opencode run --model "mlx-local/$MODEL" "$PROMPT" > "/tmp/p1a_${label}_stdout.log" 2>&1
  local rc=$?
  say "  ${label}: opencode rc=$rc"
  echo "    opencode stdout (first 5 lines):"
  head -5 "/tmp/p1a_${label}_stdout.log" | sed 's/^/      /'
  local seen; seen=$(report_since "$off" "$label")
  if [ -z "$seen" ]; then
    echo "    !!! ${label}: NO /v1/chat/completions request appeared in the router log"
  else
    echo "$seen"
  fi
}

say "=== P1a opencode smoke START (opencode $(opencode --version 2>/dev/null))"

# ---- prerequisite: the DEPLOYED config predates both campaign winners --------------------------
say "backing up + deploying the repo's generated opencode config"
cp -p "$CFG" "$BAK" && say "  backup -> $BAK"
mkdir -p "$(dirname "$CFG")"
cp "$R/opencode_config/opencode.json" "$CFG"
say "  deployed models now:"
opencode models 2>/dev/null | grep "^mlx-" | sed 's/^/    /'

# ---- Gate C(iii): scriptable non-interactive mode ---------------------------------------------
say "GATE (c) non-interactive mode: 'opencode run' present in --help"
opencode --help 2>&1 | grep -q "opencode run" && say "  PASS: 'opencode run' exists" \
                                              || say "  FAIL: no 'opencode run' subcommand"

# ---- Gate A: does the request reach :8000 at all? ---------------------------------------------
say "GATE (a) endpoint reach — tuned config as shipped"
run_gate "gateA_baseline"

# ---- Gate B: do STANDARD options forward? ----------------------------------------------------
say "GATE (b) options forwarding — max_tokens 7 (registry default is 102400)"
set_opt max_tokens 7
run_gate "gateB_maxtok7"
say "  INTERPRET: completion ~7 => options FORWARDED; completion large => NOT forwarded"
set_opt max_tokens 102400

# ---- Gate C: do NON-STANDARD extras forward? -------------------------------------------------
say "GATE (c) extras forwarding — thinking_budget 16 (registry default is 81920)"
set_opt thinking_budget 16
run_gate "gateC_budget16"
say "  INTERPRET: tiny completion => extras FORWARDED; long thinking trace => NOT forwarded"
set_opt thinking_budget 81920

# ---- restore ----------------------------------------------------------------------------------
cp -p "$BAK" "$CFG"
if diff -q "$BAK" "$CFG" >/dev/null; then say "config RESTORED from backup (verified identical)";
else say "!!! config restore MISMATCH — inspect $CFG vs $BAK"; fi
say "=== P1a opencode smoke DONE — results in $OUT"
