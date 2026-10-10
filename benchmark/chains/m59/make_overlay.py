# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m59/make_overlay.py, the driver behind the opencode_v2_*.m59.* (M59) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
"""M59 bench overlay: the current registry with every draft_*/moe_expand/mtp_verify_scan field removed (mtp_verify_scan requires draft_kind mtp) (draft-OFF, as M54/M55). NEVER commit."""
import hashlib, sys, yaml
src, dst = sys.argv[1], sys.argv[2]
raw = open(src).read(); d = yaml.safe_load(raw)
for m in d["models"]:
    for k in [k for k in m if k.startswith("draft") or k in ("moe_expand", "mtp_verify_scan")]:
        m.pop(k)
head = f"# M59 BENCH OVERLAY (draft-OFF) — generated from main_models.yaml sha256 {hashlib.sha256(raw.encode()).hexdigest()[:16]}; every draft_*/moe_expand/mtp_verify_scan field removed (mtp_verify_scan requires draft_kind mtp). NEVER commit; never point the daily-driver router at it.\n"
open(dst, "w").write(head + yaml.safe_dump(d, sort_keys=False))
print(dst)
