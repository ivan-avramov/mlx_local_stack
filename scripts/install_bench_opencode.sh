#!/bin/bash
# Install the benchmark-pinned opencode 2.0.20 under $STACK_WORKDIR (P230). Never touches Homebrew or the
# laptop-wide opencode. 2.0.20 is not on npm: the binary comes from the sha-pinned Homebrew bottle on ghcr.io,
# byte-identical to the executable recorded by the M59-M62 v2 rows (opencode_exe_sha256).
set -euo pipefail
: "${STACK_WORKDIR:?STACK_WORKDIR unset (source ~/.config/mlx_local_stack/config.sh)}"
BOTTLE_SHA=09e117ea473890d1879285a6e976ea6e62f09600eb3a2e72909522799d670b10   # opencode--2.0.20.arm64_golden_gate.bottle.tar.gz
EXE_SHA=da6c61cd188189a0bd44450ae3e19cb654a958f0b1615c83ebe47a48d0b519ae
DEST="$STACK_WORKDIR/opencode-2.0.20"
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
if [ -x "$DEST/bin/opencode" ] && [ "$(sha "$DEST/bin/opencode")" = "$EXE_SHA" ]; then
  echo "opencode 2.0.20 already installed: $DEST/bin/opencode"; exit 0
fi
TMP=$(mktemp -d "$STACK_WORKDIR/opencode-install.XXXXXX")
trap '/bin/rm -rf "$TMP"' EXIT
TOKEN=$(curl -fsS "https://ghcr.io/token?scope=repository:homebrew/core/opencode:pull" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
curl -fsSL -H "Authorization: Bearer $TOKEN" -o "$TMP/bottle.tar.gz" \
  "https://ghcr.io/v2/homebrew/core/opencode/blobs/sha256:$BOTTLE_SHA"
[ "$(sha "$TMP/bottle.tar.gz")" = "$BOTTLE_SHA" ] || { echo "REFUSED: bottle sha256 mismatch" >&2; exit 1; }
tar -xzf "$TMP/bottle.tar.gz" -C "$TMP" opencode/2.0.20/bin/opencode opencode/2.0.20/LICENSE
[ "$(sha "$TMP/opencode/2.0.20/bin/opencode")" = "$EXE_SHA" ] || { echo "REFUSED: executable sha256 mismatch" >&2; exit 1; }
mkdir -p "$DEST/bin"
/bin/cp -f "$TMP/opencode/2.0.20/LICENSE" "$DEST/LICENSE"
/bin/cp -f "$TMP/opencode/2.0.20/bin/opencode" "$DEST/bin/opencode"
chmod 755 "$DEST/bin/opencode"
[ "$(sha "$DEST/bin/opencode")" = "$EXE_SHA" ] || { echo "REFUSED: installed copy mismatch" >&2; exit 1; }
echo "installed $DEST/bin/opencode (sha256 $EXE_SHA)"
