"""The A14 comparator: exact JSON-pointer table (plan 4 A14), the four-shape file-layout mapping (R10, R27).

`compare(old, new, table, rederive=None)` -> `CompareResult(ok, failures)`. Every difference between the two normalized
results must be listed in the table, else it is a failure naming the JSON pointer:

  * allowed ADDITIONS (new side only): row `/config_id /arm /epoch_id /snapshot_sha256 /final_tree/* /token_accounting`;
    manifest `/runtime/{config_id,arm,epoch_id,snapshot_sha256,snapshot_complete,snapshot_fields,evidence_policy}`;
    anything under `/runtime/policy/` (new policy keys); chain.json `/progress /chain_config /snapshots /epoch_id
    /artifacts` and new `/lifecycle/<member>`.
  * allowed VALUE CHANGES (code-derived hashes), each ONLY when the independent `rederive(pointer, old, new)` hook
    accepts: `probe_code_sha256`, `scaffold_policy_sha256`, `generation_identity_sha256` (row top level or manifest
    `/runtime/`), existing `/runtime/policy/*` values, chain.json `/lifecycle/* /sha256/* /policy_sha256 /pinned/{...}`.
  * FORBIDDEN in tg1 rows: `/compaction`, `/receipts` (any appearance).
  * removals and everything unlisted: failure.

File layout (chain results): `canonical(result, side)` maps both layouts onto one logical form (per leg: concatenated rows,
manifests per step, attempts, logs, cancel/ack texts) so the pre-P371 `<stem>.jsonl` / `<stem>.attempt<n>.*` files and the
new `<stem>.L<leg>.<phase>.a<n>.*` files compare 1:1 per tg1 phase shape (a pilot only / b pilot+full / c full only /
d smoke). `to_new_layout` is the inverse, used by tests to build conforming (and planted-difference) new-side results."""
from __future__ import annotations

import copy
import re

TABLE = {
    "row_additions": ["/config_id", "/arm", "/epoch_id", "/snapshot_sha256", "/token_accounting"],
    "row_addition_prefixes": ["/final_tree/", "/final_tree"],
    "manifest_additions": ["/runtime/" + k for k in ("config_id", "arm", "epoch_id", "snapshot_sha256", "snapshot_complete",
                                                     "snapshot_fields", "evidence_policy")],
    "manifest_addition_prefixes": ["/runtime/policy/"],
    "chain_additions": ["/progress", "/chain_config", "/snapshots", "/epoch_id", "/artifacts"],
    "chain_addition_prefixes": ["/lifecycle/"],
    "row_value_changes": ["/generation_identity_sha256", "/probe_code_sha256", "/scaffold_policy_sha256"],
    "manifest_value_changes": ["/runtime/probe_code_sha256", "/runtime/scaffold_policy_sha256",
                               "/runtime/generation_identity_sha256"],
    "manifest_value_change_prefixes": ["/runtime/policy/"],
    "chain_value_changes": ["/policy_sha256", "/pinned/probe_code_sha256", "/pinned/scaffold_policy_sha256",
                            "/pinned/generation_identity_sha256"],
    "chain_value_change_prefixes": ["/lifecycle/", "/sha256/"],
    "forbidden_in_rows": ["/compaction", "/receipts"],
}


class CompareResult:
    def __init__(self, failures):
        self.failures = list(failures)

    @property
    def ok(self):
        return not self.failures

    def __repr__(self):
        return "CompareResult(ok=%s, failures=%s)" % (self.ok, self.failures[:5])


# ------------------------------------------------------------------------------------------------ pointers / diff
def esc(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def diff(old, new, ptr=""):
    """Yield (pointer, kind, old, new): kind changed | added | removed (lists compared index-wise)."""
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new), key=str):
            p = ptr + "/" + esc(k)
            if k not in new:
                yield p, "removed", old[k], None
            elif k not in old:
                yield p, "added", None, new[k]
            else:
                yield from diff(old[k], new[k], p)
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            p = "%s/%d" % (ptr, i)
            if i >= len(new):
                yield p, "removed", old[i], None
            elif i >= len(old):
                yield p, "added", None, new[i]
            else:
                yield from diff(old[i], new[i], p)
    elif old != new or type(old) is not type(new):
        yield ptr, "changed", old, new


ROW = re.compile(r"^/(?:runs/\d+/rows/\d+|legs/[^/]+/rows/\d+)(?P<rel>/.*)?$")
MANIFEST = re.compile(r"^/(?:runs/\d+/manifest|legs/[^/]+/manifests/[^/]+)(?P<rel>/.*)?$")
CHAIN = re.compile(r"^/chain_json(?P<rel>/.*)?$")


def classify(ptr):
    for kind, rx in (("row", ROW), ("manifest", MANIFEST), ("chain", CHAIN)):
        m = rx.match(ptr)
        if m:
            return kind, m.group("rel") or ""
    return None, ptr


def _listed(rel, exact, prefixes):
    return rel in exact or any(rel.startswith(p) for p in prefixes)


def compare(old, new, table=TABLE, rederive=None):
    old, new = _strip(old), _strip(new)
    if old.get("kind") == "chain" and new.get("kind") == "chain":
        old, new = canonical(old, "old"), canonical(new, "new")
    failures = []
    for ptr, kind, a, b in diff(old, new):
        doc, rel = classify(ptr)
        if doc == "row" and kind in ("added", "changed") and any(rel == f or rel.startswith(f + "/")
                                                                  for f in table["forbidden_in_rows"]):
            failures.append("%s: FORBIDDEN in tg1 rows" % ptr)
            continue
        if kind == "added":
            ok = ((doc == "row" and _listed(rel, table["row_additions"], table["row_addition_prefixes"]))
                  or (doc == "manifest" and _listed(rel, table["manifest_additions"], table["manifest_addition_prefixes"]))
                  or (doc == "chain" and _listed(rel, table["chain_additions"], table["chain_addition_prefixes"])))
            if not ok:
                failures.append("%s: addition not in the table" % ptr)
        elif kind == "removed":
            failures.append("%s: removed (old %r)" % (ptr, _short(a)))
        else:
            allowed = ((doc == "row" and rel in table["row_value_changes"])
                       or (doc == "manifest" and _listed(rel, table["manifest_value_changes"],
                                                         table["manifest_value_change_prefixes"]))
                       or (doc == "chain" and _listed(rel, table["chain_value_changes"], table["chain_value_change_prefixes"])))
            if not allowed:
                failures.append("%s: %r -> %r (unlisted difference)" % (ptr, _short(a), _short(b)))
            elif rederive is None or not rederive(ptr, a, b):
                failures.append("%s: value change %r -> %r not accepted by an independent re-derivation"
                                % (ptr, _short(a), _short(b)))
    return CompareResult(failures)


def _short(v):
    s = repr(v)
    return s if len(s) < 70 else s[:67] + "..."


def _strip(result):
    return {k: v for k, v in result.items() if not str(k).startswith("_")}


# ------------------------------------------------------------------------------------------------ file layout
STEM = r"(?P<stem>.+opencode_[a-z]+)"
OLD_ROWS = re.compile(rf"^{STEM}\.jsonl$")
OLD_MAN = re.compile(rf"^{STEM}\.manifest\.json$")
OLD_ATT = re.compile(rf"^{STEM}\.attempt(?P<n>\d+)\.(?P<ext>json|log|CANCEL|ACK)$")
NEW_FILE = re.compile(rf"^{STEM}\.L(?P<leg>\d+)\.(?P<phase>pilot|full|block|rerun|retry)\.a(?P<n>\d+)\."
                      r"(?P<ext>jsonl|manifest\.json|json|log|CANCEL|ACK)$")
TOK = [
    (re.compile(r"\.attempt(\d+)\.(json|log|CANCEL|ACK)\b"), r".A\1.\2"),
    (re.compile(r"\.L\d+\.(?:pilot|full|block|rerun|retry)\.a(\d+)\.(json|log|CANCEL|ACK)\b"), r".A\1.\2"),
    (re.compile(r"\.L\d+\.(?:pilot|full|block|rerun|retry)\.a\d+\.jsonl\b"), ".ROWS"),
    (re.compile(r"\.L\d+\.(?:pilot|full|block|rerun|retry)\.a\d+\.manifest\.json\b"), ".MANIFEST"),
    (re.compile(r"(opencode_[a-z]+)\.jsonl\b"), r"\1.ROWS"),
    (re.compile(r"(opencode_[a-z]+)\.manifest\.json\b"), r"\1.MANIFEST"),
]


def tok(node):
    """Rewrite layout-specific file names inside every string onto layout-neutral tokens (`.A<n>.<ext>`, `.ROWS`)."""
    if isinstance(node, str):
        for rx, rep in TOK:
            node = rx.sub(rep, node)
        return node
    if isinstance(node, dict):
        return {tok(k): tok(v) for k, v in node.items()}
    if isinstance(node, list):
        return [tok(v) for v in node]
    return node


def _split(rel):
    d, _, name = rel.rpartition("/")
    return d, name


def canonical(result, side=None):
    """Layout-neutral form of a chain result (see the module docstring). `side` is informational: names decide."""
    if result.get("kind") != "chain":
        return copy.deepcopy(result)
    out = {k: copy.deepcopy(v) for k, v in result.items() if k not in ("files", "step_manifests", "pilot_rows")}
    legs = out.pop("legs", None) if not result.get("files") else None
    if legs is None:
        legs = _legs(result)
    out["legs"] = {k: tok(v) for k, v in legs.items()}
    for key in ("chain_json", "invocations", "ops_calls", "milestones"):
        if key in out:
            out[key] = tok(out[key])
    out["extras"] = tok({k: v for k, v in _extras(result).items()})
    return out


def _parsed(result):
    parsed, extras = {}, {}
    for rel, entry in (result.get("files") or {}).items():
        d, name = _split(rel)
        m = OLD_ATT.match(name)
        if m:
            parsed.setdefault((d, m["stem"]), {}).setdefault("att", {}).setdefault(int(m["n"]), {})[m["ext"]] = entry
            continue
        m = OLD_MAN.match(name)
        if m:
            parsed.setdefault((d, m["stem"]), {})["old_manifest"] = entry
            continue
        m = OLD_ROWS.match(name)
        if m and entry.get("kind") == "rows":
            parsed.setdefault((d, m["stem"]), {})["old_rows"] = entry
            continue
        m = NEW_FILE.match(name)
        if m:
            slot = parsed.setdefault((d, m["stem"]), {}).setdefault("new", {}).setdefault(int(m["n"]), {"phase": m["phase"]})
            slot[m["ext"]] = entry
            continue
        extras[rel] = entry
    return parsed, extras


def _extras(result):
    return _parsed(result)[1]


def _legs(result):
    parsed, _ = _parsed(result)
    snaps = result.get("step_manifests") or {}
    legs = {}
    for (d, stem), p in sorted(parsed.items()):
        key = (d + "/" if d else "") + stem
        leg = {"rows": [], "manifests": {}, "attempts": [], "logs": {}, "signals": {}}
        if "new" in p:
            for n in sorted(p["new"]):
                slot = p["new"][n]
                leg["rows"] += (slot.get("jsonl") or {}).get("rows", [])
                phase = slot["phase"]
                name = phase if phase not in leg["manifests"] else "%s#%d" % (phase, n)
                if "manifest.json" in slot:
                    leg["manifests"][name] = slot["manifest.json"].get("doc")
                if "json" in slot:
                    leg["attempts"].append(slot["json"].get("doc"))
                _side_files(leg, n, slot)
        else:
            atts = p.get("att", {})
            rows = (p.get("old_rows") or {}).get("rows", [])
            leg["rows"] = rows
            order = sorted(atts)
            docs = [(atts[n].get("json") or {}).get("doc") or {} for n in order]
            steps = [d_.get("step") or "step%d" % (i + 1) for i, d_ in enumerate(docs)]
            snap = snaps.get(key) or {}
            snap_docs = [snap[k] for k in sorted(snap, key=int)]
            for i, (n, d_, step) in enumerate(zip(order, docs, steps)):
                name = step if step not in leg["manifests"] else "%s#%d" % (step, n)
                if i == len(order) - 1:
                    if p.get("old_manifest"):
                        leg["manifests"][name] = p["old_manifest"].get("doc")
                else:
                    match = [s for s in snap_docs if d_.get("run_id") and s.get("run_id") == d_.get("run_id")]
                    pick = match[-1] if match else (snap_docs[i] if i < len(snap_docs) else None)
                    if pick is not None:
                        leg["manifests"][name] = pick
                leg["attempts"].append(d_)
                _side_files(leg, n, atts[n])
        legs[key] = leg
    return legs


def _side_files(leg, n, files):
    if "log" in files:
        leg["logs"][str(n)] = {k: v for k, v in files["log"].items() if k != "kind"}
    sig = {}
    for ext in ("CANCEL", "ACK"):
        if ext in files:
            sig[ext.lower()] = files[ext].get("text")
    if sig:
        leg["signals"][str(n)] = sig


def to_new_layout(old):
    """Test support: rebuild an OLD-layout chain result in the NEW layout (`<stem>.L<leg>.<phase>.a<n>.*`), splitting
    each leg's rows file per attempt, so `compare(old, to_new_layout(old))` exercises the mapping both ways."""
    parsed, extras = _parsed(old)
    new = {k: copy.deepcopy(v) for k, v in old.items() if k not in ("files", "step_manifests", "pilot_rows")}
    legs = _legs(old)
    files = {}
    for (d, stem), p in sorted(parsed.items()):
        key = (d + "/" if d else "") + stem
        leg = legs[key]
        atts = p.get("att", {})
        order = sorted(atts)
        remaining = list(leg["rows"])
        pilot_rows = old.get("pilot_rows")
        for i, n in enumerate(order):
            doc = (atts[n].get("json") or {}).get("doc") or {}
            phase = doc.get("step") or "pilot"
            ids = _expect_ids(doc)
            if ids is not None:
                mine = [r for r in remaining if r.get("id") in ids]
            elif len(order) > 1 and i == 0 and pilot_rows:
                mine = remaining[:pilot_rows]
            elif i == len(order) - 1 or len(order) == 1:
                mine = list(remaining)
            else:
                mine = []
            remaining = [r for r in remaining if r not in mine]
            base = (d + "/" if d else "") + "%s.L1.%s.a%d" % (stem, phase, n)
            files[base + ".jsonl"] = {"kind": "rows", "rows": copy.deepcopy(mine)}
            name = phase if i == 0 or phase not in [(atts[m].get("json") or {}).get("doc", {}).get("step") for m in order[:i]] else "%s#%d" % (phase, n)
            if name in leg["manifests"]:
                files[base + ".manifest.json"] = {"kind": "manifest", "doc": copy.deepcopy(leg["manifests"][name])}
            for ext in ("json", "log", "CANCEL", "ACK"):
                if ext in atts[n]:
                    files[base + "." + ext] = copy.deepcopy(atts[n][ext])
    for rel, entry in extras.items():
        files[rel] = copy.deepcopy(entry)
    new["files"] = files
    return new


def _expect_ids(doc):
    argv = doc.get("argv") or []
    if "--expect-items" in argv:
        return set(argv[argv.index("--expect-items") + 1].split(","))
    return None
