"""Backfill the `quant` block of provenance manifests stamped `{}` (or a failure note).

P8 (2026-09-02): `gather()` resolved the O34 `$HOME/...`-form hf_path with a literal isdir test,
so every LOCAL-PATH model manifest since 2026-08-20 carries `quant: {}`. quant_info is a pure
function of the snapshot dir, so the block is recomputable in place — this rewrites ONLY `quant`,
preserving every other key and the writer's `json.dumps(indent=2)` byte form.

Usage:
    python -m bench.backfill_quant [--results-root DIR] [--registry YAML] [--dry-run]
                                   [--only-model NAME]

Manifests whose snapshot dir cannot be found are reported and left untouched.
"""
import argparse
import glob
import json
import os

from . import paths, provenance, quant_info

QUANT_KEYS = ("effective_bits", "footprint_gb", "mixed", "nominal_bits", "bit_histogram")


def needs_backfill(quant) -> bool:
    return quant == {} or quant is None or (isinstance(quant, dict) and "note" in quant)


def _summary(quant) -> str:
    if not isinstance(quant, dict) or not quant or "note" in quant:
        return "{}" if not quant or quant == {} else "note"
    eb = quant.get("effective_bits")
    eb = f"{eb:.3f}" if isinstance(eb, (int, float)) else str(eb)
    return f"(effective_bits={eb}, mixed={quant.get('mixed')})"


def resolve_dir(model: str, manifest: dict, registry: str | None):
    """Snapshot dir for `model`: the manifest's OWN kv.hf_path first (the weights the run actually
    used), then the registry's current hf_path (verifier note, 2026-09-02: a registry entry repointed
    since the run must not stamp the row with today's weights)."""
    candidates = [(manifest.get("kv") or {}).get("hf_path")]
    try:
        kv = provenance.registry_kv(model, registry) or {}
        candidates.append(kv.get("hf_path"))
    except (OSError, ValueError):
        pass
    for c in candidates:
        if not c:
            continue
        d = provenance._resolve_snapshot(c)
        if d:
            return d
    return None


def backfill_manifest(path: str, registry: str | None, dry_run: bool = False) -> tuple[str, str, str]:
    """Returns (status, old_summary, new_summary); status in {skip-ok, skip-nodir, fixed, would-fix}."""
    with open(path) as f:
        raw = f.read()
    man = json.loads(raw)
    old = man.get("quant")
    if not needs_backfill(old):
        return "skip-ok", _summary(old), _summary(old)
    d = resolve_dir(man.get("model", ""), man, registry)
    if not d:
        return "skip-nodir", _summary(old), "-"
    try:
        qi = quant_info.quant_info(d)
    except Exception as ex:  # noqa: BLE001 — one bad snapshot must not abort the sweep (verifier note)
        return "skip-nodir", _summary(old), f"quant_info failed: {ex!s:.80}"
    new = {k: qi[k] for k in QUANT_KEYS if k in qi}
    if dry_run:
        return "would-fix", _summary(old), _summary(new)
    man["quant"] = new  # in-place: key order preserved
    out = json.dumps(man, indent=2)
    with open(path, "w") as f:
        f.write(out)
    with open(path) as f:
        back = json.load(f)
    # bit_histogram carries int keys that JSON round-trips to str (same as the live writer)
    if back["quant"] != json.loads(json.dumps(new)) or list(back) != list(man):
        raise RuntimeError(f"re-read mismatch after rewriting {path}")
    return "fixed", _summary(old), _summary(new)


def run(results_root: str, registry: str | None, dry_run: bool, only_model: str | None) -> dict:
    counts = {"skip-ok": 0, "skip-nodir": 0, "fixed": 0, "would-fix": 0}
    pattern = os.path.join(results_root, "**", "*.manifest.json")
    for p in sorted(glob.glob(pattern, recursive=True)):
        if only_model:
            with open(p) as f:
                if json.load(f).get("model") != only_model:
                    continue
        status, old, new = backfill_manifest(p, registry, dry_run=dry_run)
        counts[status] += 1
        if status != "skip-ok":
            print(f"{status:10s} {p}  {old} -> {new}")
    print("summary:", " ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", default=str(paths.default_results_root()))
    ap.add_argument("--registry", default=str(paths.registry_path()))
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--only-model", default=None, help="restrict to manifests of this registry name")
    a = ap.parse_args(argv)
    run(a.results_root, a.registry, a.dry_run, a.only_model)


if __name__ == "__main__":
    main()
