"""Row pairing for tg1 comparisons (P311-lite, spec 5; REPORT side, not part of the generation identity).

`pair_identity = (generation_identity_sha256, arm identity of each side, prompt_date)`. Two rows pair only when their
generation composite AND the date shown to the model are equal; date-mismatched and generation-mismatched pairs are
returned separately (descriptive only), and a row without the current identity fields (a legacy row) never pairs with
anything: C165 E1, cross-epoch comparisons are descriptive."""
from __future__ import annotations

IDENTITY_FIELDS = ("generation_identity_sha256", "arm_identity_sha256")


def is_current(row):
    return all(isinstance(row.get(k), str) and row[k] for k in IDENTITY_FIELDS) and bool(row.get("prompt_date"))


def pair_identity(a, b):
    return (a.get("generation_identity_sha256"), a.get("arm_identity_sha256"), b.get("arm_identity_sha256"),
            a.get("prompt_date"))


def _index(rows):
    out = {}
    for row in rows:
        key = (row.get("id"), row.get("sample", 0))
        if key in out:
            raise ValueError(f"duplicate row {key} on one side: pair one attempt per item")
        out[key] = row
    return out


def pair_rows(rows_a, rows_b):
    """{'paired', 'date_mismatch', 'generation_mismatch': [(a, b)], 'legacy', 'unpaired_a', 'unpaired_b': [row]}."""
    ia, ib = _index(rows_a), _index(rows_b)
    out = {k: [] for k in ("paired", "date_mismatch", "generation_mismatch", "legacy", "unpaired_a", "unpaired_b")}
    for key in sorted(set(ia) | set(ib), key=lambda k: (str(k[0]), k[1])):
        a, b = ia.get(key), ib.get(key)
        if a is None or b is None:
            out["unpaired_a" if b is None else "unpaired_b"].append(a if b is None else b)
        elif not (is_current(a) and is_current(b)):
            out["legacy"].extend(r for r in (a, b) if not is_current(r))
            out["unpaired_a"].extend([a] if is_current(a) else [])
            out["unpaired_b"].extend([b] if is_current(b) else [])
        elif a["generation_identity_sha256"] != b["generation_identity_sha256"]:
            out["generation_mismatch"].append((a, b))
        elif a["prompt_date"] != b["prompt_date"]:
            out["date_mismatch"].append((a, b))
        else:
            out["paired"].append((a, b))
    return out


def gate_items(items_a, rows_a, items_b, rows_b):
    """Report gate (review L5). `items_*` is {item id: [scores]} and `rows_*` the scored rows behind it. When neither
    side holds a current-epoch row (the legacy P223 / M63 / c144-base data) the inputs come back unchanged with report
    None, so legacy reports are byte-identical. Otherwise only items whose two rows share the generation composite and
    the prompt date stay in the paired inputs; the rest are listed separately, never paired."""
    rows_a, rows_b = list(rows_a), list(rows_b)
    if not any(is_current(r) for r in rows_a + rows_b):
        return items_a, items_b, None
    got = pair_rows(rows_a, rows_b)
    groups = {}
    for a, b in got["paired"]:
        groups.setdefault(pair_identity(a, b), []).append(a["id"])
    if len(groups) > 1:               # never pool across (generation, arm A, arm B, date) tuples
        ok = set()
    else:
        ok = {a["id"] for a, _ in got["paired"]}
    report = {"paired": sorted(ok),
              "date_mismatch": sorted(a["id"] for a, _ in got["date_mismatch"]),
              "generation_mismatch": sorted(a["id"] for a, _ in got["generation_mismatch"]),
              "legacy": sorted({r["id"] for r in got["legacy"]}),
              "unpaired": sorted({r["id"] for r in got["unpaired_a"] + got["unpaired_b"]})}
    if len(groups) > 1:
        report["multiple_pair_identities"] = {str(k): sorted(v) for k, v in groups.items()}
    return ({k: v for k, v in items_a.items() if k in ok}, {k: v for k, v in items_b.items() if k in ok}, report)


def gate_note(label, report):
    """One line per non-empty mismatch class (descriptive; these items are NOT in the paired deltas)."""
    parts = [f"{key.replace('_', ' ')}: {report[key]}" for key in
             ("date_mismatch", "generation_mismatch", "legacy", "unpaired") if report[key]]
    if report.get("multiple_pair_identities"):
        parts.append(f"multiple pair identities (arm tuples; nothing pooled, compute one delta per group): "
                     f"{report['multiple_pair_identities']}")
    return f"- pairing gate {label}: {len(report['paired'])} paired" + ("; excluded " + "; ".join(parts) if parts else "")
