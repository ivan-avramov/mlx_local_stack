#!/usr/bin/env python3
"""M65 tg2 universe freeze (spec docs/specs/m65-tg2-corpus.md, T5): every Rust / Java / JavaScript / C++ item gets
a deprecated/inverted scan, >= 3 fresh reference runs (identical collected leaf sets, all pass), >= 2 fresh stub runs
(identical collected leaves, baseline_failing > 0) and no skipped leaves; every exclusion is listed with its reason.
Never excluded by model outcome and never by infrastructure (a TransportAbort aborts the freeze). No model calls.

Resumable: each finished item is cached under <workdir>/items; one progress line per item goes to the log file."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench import structured_grade as sg, tg2_grade as tg, tg2_materialize as mat  # noqa: E402
from bench.token_turn_gate import TransportAbort  # noqa: E402

REF_RUNS = 3
STUB_RUNS = 2
GRADE_TIMEOUT = 900


def policy(ref_runs=None, stub_runs=None):
    """The freeze policy every cached record depends on (run counts, timeouts, resource limits, optional leaves, the
    Rust allowlist file's sha256)."""
    return dict(ref_runs=REF_RUNS if ref_runs is None else ref_runs, stub_runs=STUB_RUNS if stub_runs is None else stub_runs,
                grade_timeout=GRADE_TIMEOUT, timeout_rule="max(180, int(3 * max reference seconds) + 1)",
                timeout_floor=tg.TIMEOUT_FLOOR, pids_limit=tg.PIDS_LIMIT, memory_limit=tg.MEMORY_LIMIT, nofile_limit=tg.NOFILE_LIMIT,
                fsize_limit=tg.FSIZE_LIMIT, output_cap=tg.OUTPUT_CAP, report_cap=tg.REPORT_CAP,
                max_junit_files=tg.MAX_JUNIT_FILES, tree_cap=tg.TREE_CAP, work_volume=tg.WORK_VOLUME_SIZE,
                report_volume=tg.REPORT_VOLUME_SIZE,
                optional_leaves=sorted([lang, slug, sorted(v)] for (lang, slug), v in tg.OPTIONAL_LEAVES.items()),
                allowlist_sha256=hashlib.sha256(Path(tg.ALLOWLIST_FILE).read_bytes()).hexdigest())


def freezer_sha256(root=None):
    """sha256 over the static import closure of this freezer (grader, materializer, helpers it imports)."""
    from bench import identity_closure as ic
    return ic.closure_sha256("m65/tg2_universe.py", Path(root) if root else Path(__file__).resolve().parents[1],
                             data=("m65/tg2_image/verify_corpus.py",))      # loaded by path, so hashed as a data dependency


def fingerprint(*, image_id, polyglot_sha, ref_runs=None, stub_runs=None, grader_version=None):
    """Everything a cached freeze record's validity depends on; a record is reusable only on an exact match."""
    pol = json.dumps(policy(ref_runs, stub_runs), sort_keys=True)
    return dict(polyglot_sha=polyglot_sha, image_id=image_id, grader_version=grader_version or tg.VERSION,
                materializer_version=mat.VERSION, policy=hashlib.sha256(pol.encode()).hexdigest(),
                cargo_locks_sha256=tg.verified_cargo_locks_sha256(), freezer_sha256=freezer_sha256())


def _mismatch(item, found, expected):
    if not isinstance(found, dict):
        return "%s: no fingerprint (record from before fingerprinting)" % item
    diff = sorted(k for k in expected if found.get(k) != expected[k])
    return "%s: fingerprint differs in %s" % (item, ", ".join(diff)) if diff else None


VERIFY_CORPUS_FILE = Path(__file__).resolve().parent / "tg2_image/verify_corpus.py"


def require_pinned_corpus(corpus, pinned=None):
    """The corpus checkout must be exactly the image-recorded `polyglot_sha` (IMAGE_ID) with clean target-language
    subtrees (m65/tg2_image/verify_corpus.py); anything else is refused."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("tg2_image_verify_corpus", VERIFY_CORPUS_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pinned = pinned or tg.image_record().get("polyglot_sha", "")
    try:
        return module.verify(corpus, pinned)
    except SystemExit as exc:
        raise TransportAbort("tg2 corpus is not the pinned clean checkout: %s" % exc) from exc


def inputs_sha256(corpus, lang, slug):
    """sha256 over (relative path, content) of every file of one exercise directory (tests, stubs, `.meta`, `.docs`,
    `.approaches`...): everything an item's freeze record depends on."""
    root = mat.exercise_dir(corpus, lang, slug)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def verify_unchanged(corpus, records):
    """Before assembling: the corpus is still the pinned clean checkout and every recorded item's inputs hash equals the
    current bytes (a mutation between or after items is refused, never mixed into the universe)."""
    require_pinned_corpus(corpus)
    changed = []
    for r in records:
        lang, slug = r["item"].split("/", 1)
        recorded = (r.get("fingerprint") or {}).get("inputs_sha256")
        if inputs_sha256(corpus, lang, slug) != recorded:
            changed.append(r["item"])
    if changed:
        raise TransportAbort("corpus changed during the freeze: inputs_sha256 differs for %s" % ", ".join(changed))


def default_grader(guard):
    def grader(lang, tree, slug, private, *, prepared, solutions, timeout, prepared_cargo_toml=None, extra_crates=()):
        return tg.grade_item(lang, tree, slug, private, prepared=prepared, solutions=solutions, guard=guard,
                             timeout=timeout, prepared_cargo_toml=prepared_cargo_toml, extra_crates=extra_crates)
    return grader


def _seconds(result):
    return round(sum(p["seconds"] for p in result.phases), 2)


def _leaf_sha(leaves):
    return hashlib.sha256(json.dumps(sorted(leaves)).encode()).hexdigest()


def freeze_item(corpus, lang, slug, root, grader, *, locks_fn=None, ref_runs=REF_RUNS, stub_runs=STUB_RUNS):
    """One item's freeze record. `root` is a fresh scratch directory under a non-TMPDIR root."""
    item = "%s/%s" % (lang, slug)
    rec = dict(item=item, status="excluded", reason="", scan=None, reference_runs=[], stub_runs=[])
    root = Path(root)
    scan = mat.deprecated_scan(corpus, lang, slug)
    rec["scan"] = scan
    if scan and scan.startswith("deprecated"):
        rec["reason"] = scan
        return rec
    try:
        plan = mat.read_plan(corpus, lang, slug)
    except mat.FreezeError as exc:
        rec["reason"] = "plan: %s" % exc
        return rec
    private = root / "private"
    private.mkdir(parents=True, exist_ok=True)
    try:
        prep = mat.prepare_tree(corpus, lang, slug, root / "prepared")
    except mat.FreezeError as exc:
        rec["reason"] = "prepare: %s" % exc
        return rec
    prepared = sg.manifest(prep.tree)
    cargo_toml = (prep.tree / "Cargo.toml").read_text() if lang == "rust" else None
    rec.update(solutions=plan.solutions, tests=plan.tests, mapping=[list(m) for m in plan.mapping], rewrites=prep.rewrites,
               prepared=prepared, prepared_cargo_toml=cargo_toml)

    extra = mat.reference_extra_crates(corpus, lang, slug)
    rec["reference_extra_crates"] = list(extra)

    def run(kind, n):
        tree = root / ("%s%d" % (kind, n))
        shutil.copytree(prep.tree, tree)
        if kind == "ref":
            mat.apply_reference(corpus, plan, tree)
        result = grader(lang, tree, slug, private, prepared=prepared, solutions=plan.solutions, timeout=GRADE_TIMEOUT,
                        prepared_cargo_toml=cargo_toml,
                        extra_crates=extra if kind == "ref" else ())
        shutil.rmtree(tree, ignore_errors=True)
        return result

    refs = [run("ref", n) for n in range(ref_runs)]
    rec["reference_runs"] = [dict(outcome=r.outcome, seconds=_seconds(r), leaves=len(r.leaves),
                                  leaf_sha256=_leaf_sha(r.leaves), failed=sorted(k for k, ok in r.leaves.items() if not ok))
                             for r in refs]
    outcomes = {r.outcome for r in refs}
    if outcomes != {"parsed"}:
        detail = refs[0].reason_detail or refs[0].reason
        rec["reason"] = ("reference runs did not all parse: %s%s" % (sorted(outcomes), " (%s)" % detail if detail else ""))
        return rec
    optional = tg.OPTIONAL_LEAVES.get((lang, slug), frozenset())
    if len({_leaf_sha(r.leaves) for r in refs}) != 1:
        rec["reason"] = "reference runs collected different leaf sets (nondeterministic)"
        return rec
    leaves = refs[0].leaves
    failing = sorted(k for k, ok in leaves.items() if not ok and k not in optional)
    if failing:
        rec["reason"] = "reference does not pass every collected leaf: %s" % failing[:5]
        return rec
    universe = sorted(k for k in leaves if k not in optional)
    if not universe:
        rec["reason"] = "reference collected no leaves"
        return rec
    rec["optional_excluded"] = sorted(k for k in leaves if k in optional)
    if optional and set(rec["optional_excluded"]) != set(optional):
        rec["reason"] = "expected optional leaves %s not collected" % sorted(optional - set(leaves))
        return rec
    stubs = [run("stub", n) for n in range(stub_runs)]
    rec["stub_runs"] = [dict(outcome=r.outcome, seconds=_seconds(r), leaves=len(r.leaves),
                             leaf_sha256=_leaf_sha(r.leaves)) for r in stubs]
    if len({_leaf_sha(r.leaves) for r in stubs}) != 1 or len({r.outcome for r in stubs}) != 1:
        rec["reason"] = "stub runs disagree (outcome or collected leaves)"
        return rec
    stubs[0].optional = frozenset(optional)
    baseline = stubs[0].failing(universe)
    rec["baseline_failing"] = baseline
    if baseline <= 0:
        rec["reason"] = "baseline_failing == 0 (the untouched stub already passes every leaf)"
        return rec
    ref_s = max(r["seconds"] for r in rec["reference_runs"])
    rec.update(status="valid", reason="", leaves=universe, timeout_s=max(180, int(3 * ref_s) + 1))
    return rec


def assemble(records, *, image_id, polyglot_sha, grader_version=None):
    expected = fingerprint(image_id=image_id, polyglot_sha=polyglot_sha, grader_version=grader_version)
    bad = [m for r in records for m in [_mismatch(r["item"], r.get("fingerprint"), expected)] if m]
    if bad:
        raise TransportAbort("stale freeze records refused (assemble): " + "; ".join(bad))
    for r in records:
        value = (r["fingerprint"] or {}).get("inputs_sha256")
        if not (isinstance(value, str) and len(value) == 64):
            raise TransportAbort("stale freeze records refused (assemble): %s: no inputs_sha256" % r["item"])
    records = [dict({k: v for k, v in r.items() if k != "fingerprint"}, inputs_sha256=r["fingerprint"]["inputs_sha256"])
               for r in records]
    languages = {}
    for rec in records:
        lang = rec["item"].split("/")[0]
        entry = languages.setdefault(lang, dict(valid=[], excluded={}))
        if rec["status"] == "valid":
            entry["valid"].append(rec["item"])
        else:
            entry["excluded"][rec["item"]] = rec["reason"]
    for entry in languages.values():
        entry["valid"].sort()
        entry["N_actual"] = len(entry["valid"])
    return dict(grader_version=expected["grader_version"], materializer_version=mat.VERSION, fingerprint=expected,
                policy=policy(), image_id=image_id, polyglot_sha=polyglot_sha, spec="docs/specs/m65-tg2-corpus.md", ref_runs=REF_RUNS, stub_runs=STUB_RUNS,
                languages={k: languages[k] for k in sorted(languages)},
                items={r["item"]: r for r in sorted(records, key=lambda r: r["item"])})


def freeze(out, doc):
    out = Path(out)
    side = out.with_suffix(out.suffix + ".sha256")
    if out.exists() or side.exists():
        raise TransportAbort("frozen tg2 universe already exists (refusing to overwrite)")
    raw = (json.dumps(doc, sort_keys=True, indent=1) + "\n").encode()
    from bench import proc_guard as pg
    pg.atomic_write(out, raw)
    pg.atomic_write(side, (hashlib.sha256(raw).hexdigest() + "\n").encode())
    return hashlib.sha256(raw).hexdigest()


def load(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if path.with_suffix(path.suffix + ".sha256").read_text().strip() != sha:
            raise ValueError("sha256 differs")
        doc = json.loads(raw)
        if doc["grader_version"] != tg.VERSION or not isinstance(doc["items"], dict):
            raise ValueError("grader version %r != %r: re-freeze needed" % (doc["grader_version"], tg.VERSION))
        if doc.get("materializer_version") != mat.VERSION:
            raise ValueError("materializer version %r != %r: re-freeze needed" % (doc.get("materializer_version"), mat.VERSION))
        pinned_image, pinned_corpus = tg.pinned_image_id(), tg.image_record().get("polyglot_sha")
        if doc["image_id"] != pinned_image or doc["polyglot_sha"] != pinned_corpus:
            raise ValueError("embedded image / corpus (%s, %s) are not the current pins (%s, %s): re-freeze needed"
                             % (doc["image_id"], doc["polyglot_sha"], pinned_image, pinned_corpus))
        try:
            now = fingerprint(image_id=pinned_image, polyglot_sha=pinned_corpus, grader_version=doc["grader_version"],
                              ref_runs=doc["ref_runs"], stub_runs=doc["stub_runs"])
        except TransportAbort as exc:
            raise ValueError("%s: re-freeze needed" % exc) from exc
        if doc.get("fingerprint") != now or doc.get("policy") != policy(doc["ref_runs"], doc["stub_runs"]):
            diff = sorted(k for k in now if (doc.get("fingerprint") or {}).get(k) != now[k]) or ["policy"]
            raise ValueError("the freeze fingerprint differs from the current grader/freezer/policy in %s: re-freeze needed"
                             % ", ".join(diff))
        return doc, sha
    except (OSError, ValueError, KeyError) as exc:
        raise TransportAbort("invalid frozen tg2 universe: " + str(exc)) from exc


def report(doc, sha):
    lines = ["# tg2 universe freeze report", "",
             "Grader `%s`, image `%s`, polyglot `%s`; universe sha256 `%s`." % (
                 doc["grader_version"], doc["image_id"], doc["polyglot_sha"], sha), "",
             "Per item: %d fresh reference runs (identical collected leaf sets, all pass) and %d fresh stub runs "
             "(identical collected leaves, `baseline_failing > 0`)." % (doc["ref_runs"], doc["stub_runs"]), "",
             "| Language | candidates | N_actual | excluded |", "|---|---|---|---|"]
    for lang, entry in doc["languages"].items():
        lines.append("| %s | %d | %d | %d |" % (lang, entry["N_actual"] + len(entry["excluded"]), entry["N_actual"],
                                                len(entry["excluded"])))
    lines += ["", "## Exclusions (every one with its reason)", ""]
    any_excl = False
    for lang, entry in doc["languages"].items():
        for item, why in sorted(entry["excluded"].items()):
            lines.append("- `%s`: %s" % (item, why))
            any_excl = True
    if not any_excl:
        lines.append("- none")
    lines += ["", "## Determinism", ""]
    valid = [r for r in doc["items"].values() if r["status"] == "valid"]
    ident = sum(len({x["leaf_sha256"] for x in r["reference_runs"]}) == 1 for r in valid)
    lines.append("- reference runs with identical leaf sets: %d of %d valid items" % (ident, len(valid)))
    ident = sum(len({x["leaf_sha256"] for x in r["stub_runs"]}) == 1 for r in valid)
    lines.append("- stub runs with identical leaf sets: %d of %d valid items" % (ident, len(valid)))
    for lang in doc["languages"]:
        secs = [x["seconds"] for r in valid if r["item"].startswith(lang + "/") for x in r["reference_runs"]]
        if secs:
            lines.append("- %s reference grade seconds: median %.1f, max %.1f; per-item timeout = max(180, 3 x max)" % (
                lang, statistics.median(secs), max(secs)))
    lines += ["", "## Optional leaves (JS `test.skip`, excluded from scoring by id)", ""]
    opt = [(r["item"], r["optional_excluded"]) for r in valid if r.get("optional_excluded")]
    lines += ["- `%s`: %s" % (i, ids) for i, ids in opt] or ["- none"]
    rewrites = sum(sum(r["rewrites"].values()) for r in valid if r.get("rewrites"))
    lines += ["", "## Skip-form rewrites", "", "- %d skip forms rewritten across valid items (JS xtest/xit/xdescribe, Java @Disabled)" % rewrites,
              "", "## Deprecated / inverted scan", ""]
    scans = [(r["item"], r["scan"]) for r in doc["items"].values() if r.get("scan")]
    lines += ["- `%s`: %s" % x for x in scans] or ["- no item declares itself deprecated or inverted"]
    return "\n".join(lines) + "\n"


def run_all(corpus, workdir, log, grader, *, image_id, polyglot_sha, locks_fn=None, only=None, ref_runs=REF_RUNS,
            stub_runs=STUB_RUNS):
    """Resumable. A cached record is reused only on an EXACT fingerprint match; any mismatch (or a record from before
    fingerprinting) aborts the whole run before anything executes, listing every stale item (nothing is discarded or
    overwritten: the operator removes the cache directory deliberately)."""
    fp = fingerprint(image_id=image_id, polyglot_sha=polyglot_sha, ref_runs=ref_runs, stub_runs=stub_runs)
    items = [(lang, slug) for lang, slugs in mat.list_items(corpus).items() for slug in slugs]
    if only:
        items = [i for i in items if "%s/%s" % i in only or i[0] in only]
    cache = Path(workdir) / "items"
    cache.mkdir(parents=True, exist_ok=True)
    stale = []
    for lang, slug in items:
        path = cache / ("%s__%s.json" % (lang, slug))
        if path.exists():
            want = dict(fp, inputs_sha256=inputs_sha256(corpus, lang, slug))
            m = _mismatch("%s/%s" % (lang, slug), json.loads(path.read_text()).get("fingerprint"), want)
            if m:
                stale.append(m)
    if stale:
        raise TransportAbort("stale cached freeze records in %s (remove the cache to refreeze): %s" % (cache, "; ".join(stale)))
    records, started = [], time.monotonic()
    done_new = 0
    for n, (lang, slug) in enumerate(items, 1):
        path = cache / ("%s__%s.json" % (lang, slug))
        t0 = time.monotonic()
        if path.exists():
            rec, tag = json.loads(path.read_text()), "cached"
        else:
            scratch = Path(workdir) / "scratch" / ("%s__%s" % (lang, slug))
            shutil.rmtree(scratch, ignore_errors=True)
            before = inputs_sha256(corpus, lang, slug)
            rec = freeze_item(corpus, lang, slug, scratch, grader, locks_fn=locks_fn, ref_runs=ref_runs,
                              stub_runs=stub_runs)
            after = inputs_sha256(corpus, lang, slug)
            if before != after:
                shutil.rmtree(scratch, ignore_errors=True)
                raise TransportAbort("corpus changed while freezing %s/%s (inputs_sha256 %s -> %s); freeze aborted, "
                                     "no record written" % (lang, slug, before, after))
            rec["fingerprint"] = dict(fp, inputs_sha256=before)
            shutil.rmtree(scratch, ignore_errors=True)
            path.write_text(json.dumps(rec, sort_keys=True))
            tag, done_new = "run", done_new + 1
        elapsed = time.monotonic() - started
        eta = (elapsed / done_new) * (len(items) - n) if done_new else 0
        line = "%s [%d/%d] %-26s %-8s %s %5.1fs elapsed=%.0fs eta=%.0fs" % (
            time.strftime("%H:%M:%S"), n, len(items), rec["item"], rec["status"], tag, time.monotonic() - t0, elapsed, eta)
        if rec["status"] != "valid":
            line += "  EXCLUDED: %s" % rec["reason"][:160]
        Path(log).open("a").write(line + "\n")
        records.append(rec)
    return records


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True, help="non-TMPDIR scratch / cache root")
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("tg2_universe.json"))
    ap.add_argument("--report", type=Path, default=Path(__file__).with_name("TG2_UNIVERSE_REPORT.md"))
    ap.add_argument("--log", type=Path)
    ap.add_argument("--only", action="append", help="lang or lang/slug (repeatable); partial runs are not frozen")
    args = ap.parse_args(argv)
    args.workdir.mkdir(parents=True, exist_ok=True)
    log = args.log or args.workdir / "freeze.log"
    sha_poly = require_pinned_corpus(args.corpus)
    guard = tg.LocalDocker()
    leftover = tg.list_leftovers(guard.run_grader, args.workdir)
    if leftover["containers"] or leftover["volumes"]:
        raise TransportAbort("tg2 leftovers present: %s" % leftover)
    image_id = tg.pinned_image_id()
    records = run_all(args.corpus, args.workdir, log, default_grader(guard), only=args.only, image_id=image_id,
                      polyglot_sha=sha_poly)
    if args.only:
        print("partial run (--only): not frozen")
        return 0
    verify_unchanged(args.corpus, records)
    doc = assemble(records, image_id=image_id, polyglot_sha=sha_poly)
    sha = freeze(args.out, doc)
    args.report.write_text(report(doc, sha))
    print("frozen", args.out, sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
