"""P371 phase 3a (plan 4 R7): `bench.chain_rows` is the ONLY reader of chain out-root rows. Every consumer listed in the
chain_rows docstring is migrated; a repository scan rejects a direct chain-row read outside `chain_rows` (explicit
allow-list, each entry with its reason); the stored-chain report outputs are byte-identical to the committed ones; the two
reports that need a live chain directory (M61 rerun, M59) are covered by golden snapshots over fixtures."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bench import chain_rows as cr

REPO = Path(__file__).resolve().parents[3]
BENCH = REPO / "benchmark"


# ---------------------------------------------------------------- the chain_rows API the consumers use
def test_rows_if_present_is_empty_for_a_missing_file_and_strict_for_a_torn_one(tmp_path):
    assert cr.rows_if_present(tmp_path / "none.jsonl") == []
    good = tmp_path / "ok.jsonl"
    good.write_text(json.dumps({"id": "python/a", "passed": True}) + "\n")
    assert cr.rows_if_present(good) == [{"id": "python/a", "passed": True}]
    torn = tmp_path / "torn.jsonl"
    torn.write_text('{"id": "python/a"}\n{"id": ')
    with pytest.raises(cr.ChainRowsError, match="torn"):
        cr.rows_if_present(torn)
    anon = tmp_path / "anon.jsonl"
    anon.write_text('{"passed": true}\n')
    with pytest.raises(cr.ChainRowsError):
        cr.rows_if_present(anon)


def test_the_stored_result_layout_names(tmp_path):
    assert cr.stored_name("python", "p223", "s1") == "opencode_v2_python.p223.s1.jsonl"
    assert cr.stored_path(tmp_path / "M", "go", "m63", "reload") == tmp_path / "M" / "opencode_v2_go.m63.reload.jsonl"
    (tmp_path / "M").mkdir()
    (tmp_path / "M" / "opencode_v2_go.m63.s2.jsonl").write_text('{"id": "go/x"}\n')
    assert cr.stored_rows(tmp_path / "M", "go", "m63", "s2") == [{"id": "go/x"}]
    assert cr.stored_rows(tmp_path / "M", "go", "m63", "s1") == []                 # absent leg: empty, like the old readers


def test_the_legacy_out_root_leg_paths(tmp_path):
    p = lambda layout, **kw: cr.legacy_path(tmp_path, layout, model="M", **kw)      # noqa: E731
    assert p("c147", session="s1", lang="python") == tmp_path / "s1" / "M.s1.opencode_python.jsonl"
    assert p("m63", session="reload", lang="python") == tmp_path / "reload" / "M.reload.opencode_python.jsonl"
    assert p("m61rr", session="s2", lang="go") == tmp_path / "M.rr.s2.opencode_go.jsonl"
    assert p("m59", session="s1", lang="go") == tmp_path / "s1" / "M.opencode_go.jsonl"
    assert p("m59", session="s2", lang="go") == tmp_path / "s2" / "M.s2.opencode_go.jsonl"
    assert p("m59flat", session="s1", lang="go") == tmp_path / "M.opencode_go.jsonl"
    with pytest.raises(ValueError):
        p("nope", session="s1", lang="go")
    assert cr.legacy_rows(tmp_path, "m59", model="M", session="s1", lang="go") == []


# ---------------------------------------------------------------- chain_ops reads rows through chain_rows
def test_chain_ops_reads_the_probes_rows_through_chain_rows(tmp_path):
    from bench import chain_ops as co
    f = tmp_path / "r.jsonl"
    f.write_text('{"id": "python/a"}\n')
    ops = co.ChainOps(REPO, tmp_path, tmp_path / "ov.yaml", lambda m: None)
    assert ops.rows(f) == [{"id": "python/a"}] and ops.rows(tmp_path / "missing.jsonl") == []
    f.write_text('{"id": "python/a"}\n{"id"')
    with pytest.raises(cr.ChainRowsError):
        ops.rows(f)
    leg = dict(session="s", model="m", lang="python", seed_base=1, expected_ids=["python/a"], out=str(f), rc=0)
    assert any(w.startswith("rows_torn") for w in co.validate_leg(leg, {}, tmp_path))


# ---------------------------------------------------------------- the scan
PATTERNS = {
    "proc_guard.load_rows": re.compile(r"\bload_rows\("),
    "chain row file name": re.compile(r"""opencode_(?:v2_)?\{|\.opencode_\{|\.attempt\{[^"'\n]*\.jsonl|\.dnf\.jsonl"""),
}
# every entry: path -> why it is not a chain-row READER that must go through chain_rows
ALLOW = {
    "benchmark/bench/chain_rows.py": "the loader itself",
    "benchmark/bench/proc_guard.py": "defines load_rows (generic probe-side loader; the probe no longer reads rows)",
    "benchmark/bench/schedules.py": "names the stems / files the chain writes (layout author, no reads)",
    "benchmark/chains/m55/m55_report.py": "frozen M55 chain report (legacy, own dir; AGENTS: frozen runners stay)",
    "benchmark/chains/m55/run_m55.py": "frozen M55 runner / writer (own dir)",
    "benchmark/chains/m59/run_m59.py": "frozen M59 runner / writer (own dir)",
    "benchmark/chains/m61/run_m61.py": "frozen M61 runner / writer (own dir)",
    "benchmark/chains/m61/run_m61_rr.py": "frozen M61 rerun runner / writer (own dir)",
}


def scan(root=BENCH):
    hits = {}
    for path in sorted(Path(root).rglob("*.py")):
        rel = path.relative_to(root.parent if root.name == "benchmark" else root).as_posix()
        parts = path.relative_to(root).parts
        if "tests" in parts or any(p.startswith(".venv") or p == "__pycache__" for p in parts):
            continue
        text = path.read_text(errors="replace")
        found = [name for name, rx in PATTERNS.items() if rx.search(text)]
        if found:
            hits[rel] = found
    return hits


def test_no_module_reads_chain_rows_outside_chain_rows_except_the_documented_allow_list():
    hits = scan()
    offenders = {rel: v for rel, v in hits.items() if rel not in ALLOW}
    assert offenders == {}, "direct chain-row access outside chain_rows (migrate it or allow-list it with a reason)"


def test_every_allow_list_entry_still_exists_and_still_matches():
    hits = scan()
    for rel, reason in ALLOW.items():
        assert (REPO / rel).is_file(), rel
        assert reason and rel in hits, f"{rel} no longer matches a pattern: remove it from the allow-list"


def test_a_planted_direct_reader_fails_the_scan(tmp_path):
    root = tmp_path / "benchmark"
    (root / "results").mkdir(parents=True)
    (root / "results" / "evil.py").write_text(
        'import json\nrows = [json.loads(l) for l in open(f"{d}/{m}.s1.opencode_{lang}.jsonl")]\n')
    (root / "results" / "evil2.py").write_text("from bench import proc_guard as pg\nrows = pg.load_rows(p)\n")
    (root / "results" / "fine.py").write_text("from bench import chain_rows\nrows = chain_rows.stored_rows(d, 'go', 't', 's1')\n")
    got = scan(root)
    assert set(got) == {"benchmark/results/evil.py", "benchmark/results/evil2.py"}


def test_the_m64_chain_names_no_rows_file_itself_it_runs_on_the_core_and_the_loader():
    entry = (REPO / "benchmark/chains/m64/run_m64_chain.py").read_text()
    assert ".dnf." not in entry and ".jsonl" not in entry and "opencode_{" not in entry
    core = (REPO / "benchmark/bench/chain_core.py").read_text()
    assert ".dnf.jsonl" not in core and "cr.dnf_" in core


def test_the_migrated_consumers_import_chain_rows():
    for rel in ("benchmark/results/p223_tg1/tg1_report.py", "benchmark/results/m63_mtp/m63_report.py",
                "benchmark/results/c144_base/c144base_report.py", "benchmark/results/m61_rr/rr_report.py",
                "benchmark/chains/m59/m59_report.py", "benchmark/m64/power_sim.py", "benchmark/bench/chain_ops.py"):
        assert "chain_rows" in (REPO / rel).read_text(), rel


# ---------------------------------------------------------------- byte-identical report outputs
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "r7_reports"


def fixture_rows(model, lang, n):
    from bench import rowschema
    rows = []
    for i in range(n):
        item = f"{lang}/item{i:02d}"
        rows.append({"id": item, "model": model, "sample": 0, "passed": i % 3 != 0, "converged": True, "nonconv_kind": None,
                     "nonconv_flags": [], "wall_s": 100.0 + 7 * i, "stop_reason": None, "acc": int(i % 3 != 0),
                     "sampler_seed": rowschema.sample_seed(item, 0, 1001), "web_fetches": [],
                     "traffic": {"turns": 4, "output_tokens": 900 + i}, "loop_metrics": {"tool_calls": 3, "error_calls": 0}})
    return rows


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"


def run_report(script, env, cwd):
    return subprocess.run([sys.executable, str(script)], env=env, cwd=cwd, capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize("folder,script,report", [("p223_tg1", "tg1_report.py", "P223_REPORT.md"),
                                                  ("m63_mtp", "m63_report.py", "M63_REPORT.md"),
                                                  ("c144_base", "c144base_report.py", "C144BASE_REPORT.md")])
def test_stored_chain_reports_are_byte_identical_to_the_committed_ones(folder, script, report):
    """P223 / M63 / c144-base: the report on the committed stored rows equals the committed report, byte for byte."""
    target = BENCH / "results" / folder / report
    committed = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:benchmark/results/{folder}/{report}"],
                               capture_output=True).stdout
    before = target.read_bytes()
    try:
        run = run_report(BENCH / "results" / folder / script, dict(os.environ), REPO)
        assert run.returncode == 0, run.stderr[-1500:]
        assert target.read_bytes() == before and (before == committed or not committed)
    finally:
        target.write_bytes(before)


def build_fixture(wd, repo):
    """A fixture chain: `$STACK_WORKDIR/m61/rr/...` (M61 rerun), `$STACK_WORKDIR/m59/<s>/...` (M59), and the stored
    comparison rows under `<repo>/benchmark/results` (M59 rows per model, the 1.18 medium baselines)."""
    from bench import rowschema                                    # noqa: F401  (fixture rows use sample_seed)
    for m in (P1, P2):
        for lang in ("python", "go"):
            write_rows(repo / "benchmark/results" / (f"{m}-MED/opencode.jsonl" if lang == "python" else f"{m}/opencode_go.medium.jsonl"),
                       fixture_rows(m, lang, 8))
            for s in ("s1", "s2"):
                f = wd / "m61/rr" / f"{m}.rr.{s}.opencode_{lang}.jsonl"
                write_rows(f, fixture_rows(m, lang, 9))
                f.with_suffix(".manifest.json").write_text(json.dumps({"runtime": {"first_write_window_s": 658}}))
                write_rows(repo / "benchmark/results" / m / f"opencode_v2_{lang}.m59.{s}.jsonl", fixture_rows(m, lang, 9)[2:])
                v2 = wd / "m59" / s / (f"{m}.opencode_{lang}.jsonl" if s == "s1" else f"{m}.{s}.opencode_{lang}.jsonl")
                write_rows(v2, fixture_rows(m, lang, 9))
                v2.with_suffix(".manifest.json").write_text(json.dumps({"runtime": {"first_write_window_s": 630}}))
    (wd / "m59/stallprobe").mkdir(parents=True, exist_ok=True)


def fixture_reports(tmp_path):
    """Run the M61 rerun and M59 reports over the fixture; returns {name: text}. The scripts are run in place (they only
    write beside themselves: RR_REPORT.md is restored, M59_REPORT.md lands in the fixture workdir)."""
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    (repo / "benchmark").mkdir(parents=True)
    for entry in BENCH.iterdir():                                 # the real code, a private `results/` for the fixture rows
        if entry.name not in ("results", "__pycache__") and not entry.name.startswith("."):
            (repo / "benchmark" / entry.name).symlink_to(entry)
    build_fixture(wd, repo)
    env = {**os.environ, "STACK_REPO": str(repo), "STACK_WORKDIR": str(wd)}
    out = {}
    rr = BENCH / "results/m61_rr/rr_report.py"
    md = rr.with_name("RR_REPORT.md")
    before = md.read_bytes()
    try:
        run = run_report(rr, env, REPO)
        assert run.returncode == 0, run.stderr[-1500:]
        out["rr_report.stdout"] = run.stdout
        out["rr_report.md"] = md.read_text()
    finally:
        md.write_bytes(before)
    run = run_report(BENCH / "chains/m59/m59_report.py", env, REPO)
    assert run.returncode == 0, run.stderr[-1500:]
    out["m59_report.stdout"] = run.stdout
    out["m59_report.md"] = (wd / "m59/M59_REPORT.md").read_text()
    return {k: v.replace(str(tmp_path), "$TMP") for k, v in out.items()}


@pytest.mark.parametrize("name", ["rr_report.stdout", "rr_report.md", "m59_report.stdout", "m59_report.md"])
def test_the_reports_that_need_a_live_chain_directory_match_their_golden_over_a_fixture(tmp_path, name):
    got = fixture_reports(tmp_path)
    if os.environ.get("P371_REGEN_R7") == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for key, text in got.items():
            (GOLDEN / key).write_text(text)
    assert got[name] == (GOLDEN / name).read_text(), "report output differs from the golden generated before the R7 migration"
