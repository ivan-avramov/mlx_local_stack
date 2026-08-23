#!/bin/zsh
# Registry commit dance, mechanized (was performed by hand 4+ times on 2026-08-23 alone).
#
# This box intentionally overrides a few models' `hf_path` with local absolute paths
# (avoiding multi-GB re-downloads). Those lines are PII and must NEVER be committed; the
# committed form is the `caslca/<name>` (or other hub) path. To commit an INTENTIONAL
# registry change (certification, new model, cap change) without leaking the local dirt:
#
#   scripts/registry_commit.sh "commit message"            # swap -> commit -> restore
#   scripts/registry_commit.sh --dry-run                   # show what would be committed
#
# Mechanics: every hf_path whose value is an absolute path is replaced by that model's
# hf_path line from HEAD. A local-path model with NO committed counterpart is a REFUSAL:
# add its `caslca/<name>` placeholder line (with a NOT-YET-UPLOADED note) in the same
# edit, commit that, and only then rely on this script.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
REG=main_models.yaml
BACKUP="$(mktemp "${TMPDIR:-/tmp}/registry_backup.XXXXXX")"
cp -p "$REG" "$BACKUP"

restore() { cp -p "$BACKUP" "$REG"; }
trap restore EXIT

python3 - "$REG" <<'PY'
import re, subprocess, sys
reg = sys.argv[1]
head = subprocess.check_output(["git", "show", f"HEAD:{reg}"], text=True).splitlines(True)
# model name -> its hf_path line in HEAD
head_hf, cur = {}, None
for line in head:
    m = re.match(r"  - name: (\S+)", line)
    if m: cur = m.group(1)
    if re.match(r"\s+hf_path:", line) and cur: head_hf[cur] = line
out, cur, missing = [], None, []
for line in open(reg):
    m = re.match(r"  - name: (\S+)", line)
    if m: cur = m.group(1)
    hm = re.match(r"(\s+)hf_path:\s*(\S+)", line)
    if hm and hm.group(2).startswith("/"):
        if cur in head_hf: line = head_hf[cur]
        else: missing.append(cur)
    out.append(line)
if missing:
    sys.exit(f"REFUSED: local-path model(s) with no committed hf_path counterpart: {missing}. "
             "Commit a caslca/<name> placeholder (NOT-YET-UPLOADED note) for them first.")
open(reg, "w").writelines(out)
PY

if ! git diff --quiet HEAD -- "$REG" && grep -n "/Users/" "$REG"; then
  echo "REFUSED: absolute home paths remain in $REG after the swap" >&2
  exit 1
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "--- would commit this $REG diff (working tree restored on exit) ---"
  git --no-pager diff -- "$REG" || true
  exit 0
fi
[[ -n "${1:-}" ]] || { echo "usage: $0 \"commit message\" | --dry-run" >&2; exit 2; }

git add "$REG"
git commit -m "$1"
# trap restores the local hf_path dirt; verify the restoration took
restore
trap - EXIT
if ! cmp -s "$REG" "$BACKUP"; then
  echo "WARNING: restored registry differs from backup at $BACKUP — inspect by hand" >&2
  exit 1
fi
echo "committed; local registry dirt restored (verified byte-identical)"
