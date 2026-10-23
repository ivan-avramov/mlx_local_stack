"""P426 stack code round 1 K3 / K4: the leg planner — everything a Wave-1 leg depends on, derived from (axis, arm, block) and the
committed `benchmark/results/p426/ids.json` (`docs/specs/p426-fable-mtp-recert.md` §4–§5): the driver argv and cwd, every output
of the leg's stem (none may exist), the planned membership, the expected seeds per row and the expected request count.
"""

import json
from pathlib import Path

from bench import p426_ids
from bench.rowschema import sample_seed

ARMS = ("off", "on")
REQUEST_SEED_BASE = p426_ids.SEED  # A4's explicit per-draw request seeds (ids.json request_seeds)


def load_ids(repo, text=None):
    """The committed ids.json, refused unless it equals a rebuild from the M40 sources (K3: membership comes from it)."""
    repo = Path(repo)
    doc = json.loads(text if text is not None else (repo / p426_ids.OUT).read_text())
    want = dict(p426_ids.build(repo), sources_sha256=p426_ids.source_shas(repo))
    if doc != want:
        raise ValueError(f"{p426_ids.OUT}: not the committed rebuild of its sources")
    return doc


def _tune(arm, block, smoke):
    if arm not in ARMS:
        raise ValueError(f"arm {arm!r} not in {ARMS}")
    if smoke:
        return f"p426-{arm}-smoke"
    if block not in (1, 2):
        raise ValueError(f"block {block!r} not in (1, 2)")
    return f"p426-{arm}-b{block}"


def plan_leg(repo, axis, arm, block, smoke=False, results_root=None, workdir=None, reviewed_head=None, production_ref=None):
    repo = Path(repo)
    ids = load_ids(repo)
    entry = ids["entry"]
    tune = _tune(arm, block, smoke)
    if axis == "m1":  # K3: the in-process qualify leg (no router, directory evidence)
        if not workdir or not reviewed_head:
            raise ValueError("an m1 leg needs the workdir and the frozen build's reviewed head")
        if not production_ref:  # P452 F1: S's production tree, attested by qualify (B1's log-only counters)
            raise ValueError("an m1 leg needs the production ref (frozen.json production_ref)")
        out_dir = Path(workdir) / "p426" / "m1" / tune
        fork = repo / "src" / "mlx-vlm"
        return dict(
            axis=axis, arm=arm, block=block, smoke=smoke, tune=tune, entry=entry, kind="qualify", cwd=str(repo),
            out_dir=out_dir, rows_path=None, planned=[], row_key=None, expected_requests=0, expected_extra=0, seeds={},
            stem=None,
            driver_argv=[str(repo / ".venv" / "bin" / "python"), str(fork / "dev" / "p369_phase2" / "qualify.py"),
                         "--stack-root", str(repo), "--fork-root", str(fork), "--out", str(out_dir),
                         "--reviewed-head", reviewed_head, "--entry", entry, "--predictor", arm,
                         "--production-ref", production_ref],
        )
    if axis not in ids["axes"]:
        raise ValueError(f"unknown axis {axis!r}")
    sel = ids["axes"][axis]["smoke" if smoke else f"block{block}"]
    results = Path(results_root) if results_root else repo / "benchmark" / "results"
    out_dir = results / entry
    py = str(repo / ".venv-bench" / "bin" / "python")
    leg = dict(axis=axis, arm=arm, block=block, smoke=smoke, tune=tune, entry=entry, cwd=str(repo), results_dir=out_dir)
    if axis in ("math500", "cjudge"):
        stem = f"{axis}.{tune}"
        leg.update(
            driver_argv=[py, str(repo / "benchmark" / "run.py"), "generate", "--models", entry, "--benches", axis,
                         "--limit", f"{axis}=0", "--ids", f"{axis}=" + ":".join(sel), "--sampling-profile", "deployed",
                         "--tune", tune, "--order", "roundrobin", "--seed", "0", "--seed-base", "0", "--samples", "1"],
            rows_path=out_dir / f"{stem}.jsonl", planned=list(sel), row_key="id", expected_requests=len(sel),
            expected_extra=0, seeds={i: {"sampler_seed": sample_seed(i, 0, base=0), "sample": 0, "seed_base": 0} for i in sel},
        )
    elif axis == "vision":
        stem = f"vision_gate.{tune}"
        leg.update(
            driver_argv=[py, str(repo / "benchmark" / "vision_gate.py"), "--model", entry, "--ids", ":".join(sel),
                         "--out", str(out_dir / f"{stem}.jsonl")],
            rows_path=out_dir / f"{stem}.jsonl", planned=list(sel), row_key="id", expected_requests=2 * len(sel),
            expected_extra=0, seeds={i: {"seed": sample_seed(i, 0), "turn2_seed": sample_seed(i, 1)} for i in sel},
        )
    elif axis == "reasoning":
        stem = f"reasoning.{tune}"
        tasks = list(sel)
        if tasks != list(range(tasks[0], tasks[0] + len(tasks))):
            raise ValueError(f"reasoning tasks {tasks} are not contiguous (--task-seed-base + trial)")
        leg.update(
            driver_argv=[py, "-m", "bench.run_reasoning", "--model", entry, "--grid", "128000", "--samples", str(len(tasks)),
                         "--chain-len", "4", "--sampling-profile", "deployed", "--out-tag", tune,
                         "--task-seed-base", str(tasks[0]), "--request-seed-base", str(REQUEST_SEED_BASE)],
            cwd=str(repo / "benchmark"), rows_path=out_dir / f"{stem}.partial.jsonl", planned=tasks, row_key="seed",
            expected_requests=len(tasks) + 1, expected_extra=1,  # + the chars-per-token calibration request
            seeds={t: {"sampler_seed": ids["axes"]["reasoning"]["request_seeds"][str(t)]} for t in tasks},
        )
    else:
        raise ValueError(f"axis {axis!r} has no Wave-1 leg")
    leg["stem"] = stem
    leg["kind"] = {"math500": "rows", "cjudge": "rows"}.get(axis, axis)
    return leg


def existing_outputs(leg):
    """Every file of the leg's stem already on disk (rows, manifest, score, summary, journal, provenance …); for an M1 leg its
    output directory."""
    if leg.get("kind") == "qualify":
        return [leg["out_dir"]] if Path(leg["out_dir"]).exists() else []
    d = Path(leg["results_dir"])
    return sorted(p for p in d.glob(f"{leg['stem']}.*")) if d.exists() else []


def seed_problems(expected, rows, key):
    """K4: every row's recorded seeds equal the planned ones (vision: both turns)."""
    problems = []
    for row in rows:
        want = expected.get(row.get(key))
        if want is None:
            continue  # membership reports it
        got = {k: row.get(k) for k in want if k != "turn2_seed"}
        if "turn2_seed" in want:
            got["turn2_seed"] = (row.get("turn2") or {}).get("seed")
        if got != want:
            problems.append(f"{row.get(key)}: seeds {got} != planned {want}")
    return problems


def qualify_problems(report, entry, arm, production_ref=None):
    """K3: the M1 leg's evidence — the planned predictor, the entry COMPLETED in the planned arm; P452: the report records
    exactly the planned production ref."""
    want_arm = "mtp_on" if arm == "on" else "mtp_off"
    problems = []
    if production_ref and report.get("production") != production_ref:
        problems.append(f"qualify production {report.get('production')!r} != planned {production_ref!r}")
    if report.get("predictor") != arm:
        problems.append(f"qualify predictor {report.get('predictor')!r} != {arm!r}")
    state = (report.get("entries") or {}).get(entry)
    if not state:
        return problems + [f"qualify report has no {entry}"]
    if state.get("status") != "COMPLETED":
        problems.append(f"qualify status {state.get('status')!r}")
    if state.get("arm") != want_arm:
        problems.append(f"qualify arm {state.get('arm')!r} != {want_arm!r}")
    return problems
