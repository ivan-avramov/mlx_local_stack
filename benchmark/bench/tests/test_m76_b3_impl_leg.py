"""M76 B3: `bench.p426_leg` under `lever=kv` — the arm serves its committed registry, the KV delta against the recorded N16 base
(real arm texts), the worker argv carries exactly the arm's KV flags and MTP ON, every row of BOTH arms is engaged, the A5 leg
runs its per-item invocations; mocked ops (no router, no model)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from bench import p426_leg as L
from bench import p426_plan as P
from bench.tests.test_p426_leg import ENGAGED, FakeOps, _log_for

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
REFS = {"n16": "89205085", "x": "origin/m76-f45-x", "v": "origin/m76-f45-v"}


_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m76_b3_fe"
_FIXTURE_ARM = {"89205085": "n16", "origin/m76-f45-x": "x", "origin/m76-f45-v": "v", "origin/m76-f45-xo": "xo"}


def _show(ref):
    """The arm's committed registry: the sha256-pinned fixture copy (`fixtures/m76_b3_fe/`, checked against its source revision by
    `test_m76_b3_registry_fixtures_pinned.py`) — so the test runs on any clone, not only where the local `m76-f45-*` branches exist
    (S23-P93); any other ref / path from git."""
    arm = _FIXTURE_ARM.get(ref)
    if arm and "main_models.yaml" == "main_models.yaml":
        data = (_FIXTURES / f"{arm}_main_models.yaml").read_bytes()
        return data.decode()
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{"main_models.yaml"}"], capture_output=True)
    if r.returncode:
        pytest.skip(f"{ref} is not in this repository's objects")
    data = r.stdout
    return data.decode()


@pytest.fixture(scope="module")
def reg():
    return {arm: _show(ref) for arm, ref in REFS.items()}


def cmdline(arm):
    from bench.tests.test_m76_b3_impl_lever import worker_argv

    return "202 " + " ".join(t if " " not in t else t.replace(" ", "") for t in worker_argv(arm))


def _venvs():
    one = {p: "0.32.4" if p in ("mlx", "mlx-metal") else "1.0" for p in P.VENV_PACKAGES}
    return {v: dict(one) for v in P.VENVS}


def kv_pins(reg, arms=("n16", "x", "v")):
    rec = dict(build="s3", lever="kv", arms=list(arms), uv_lock_sha256="a" * 64, bench_lock_sha256="b" * 64, venvs={},
               **{k: P.EXPECTED_BUILDS["s3"][k] for k in ("mlx_vlm", "mlx_serve", "production_ref")})
    for i, arm in enumerate(arms):
        rec.update({f"stack_head_{arm}": f"{i + 1:x}" * 40, f"stack_clean_{arm}": True,
                    f"registry_{arm}_sha": L.sha256_text(reg[arm])})
        rec["venvs"][arm] = _venvs()
    return dict(rec, frozen_sha="f" * 64)


def _row(i, pt=None):
    return {"id": i, "draft": ENGAGED, "completion_tokens": 5, "session_id": f"m76-t-{i}",
            "prompt_tokens": pt if pt is not None else 100 + ord(i[0]), "sampler_seed": 7, "sample": 0, "seed_base": 0}


def kv_spec(tmp_path, reg, arm="x", rows=None, planned=("a", "b"), **over):
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows_path = tmp_path / "rows.jsonl"
    spec = L.LegSpec(name=f"math500-m76-{arm}-b1", arm=arm, kind="rows", model=ENTRY, registry_text=reg[arm],
                     off_registry_text=reg["n16"], driver_argv=["true"], destinations=[rows_path], rows_path=rows_path,
                     planned=list(planned), receipt_dir=tmp_path / "receipts", server_log=tmp_path / "mlx_vlm.log",
                     expected_requests=len(planned), seeds={i: {"sampler_seed": 7, "sample": 0, "seed_base": 0} for i in planned},
                     pins=kv_pins(reg), build="s3", lever="kv", **over)
    spec._test_rows = rows if rows is not None else [_row(i) for i in planned]
    return spec


def _state(spec):
    return dict(P.build_pins(spec.pins, spec.arm), frozen_sha=spec.pins["frozen_sha"])


def run_kv(spec, ops, *, envs=None, log_lines=None, driver=None):
    spec.server_log.write_text("")

    def default_driver(argv, env, timeout, cwd=None):
        if envs is not None:
            envs.append(env)
        spec.rows_path.write_text("".join(json.dumps(r) + "\n" for r in spec._test_rows))
        with spec.server_log.open("a") as f:
            f.write("\n".join(log_lines if log_lines is not None else _log_for(spec._test_rows, spec.expected_extra)) + "\n")
        return 0

    ops.router_config_sha = L.sha256_text(spec.registry_text)
    if not getattr(ops, "cmdline", None):
        ops.cmdline = cmdline(spec.arm)
    return L.run_leg(spec, ops, run_driver=driver or default_driver, pins_check=lambda model, role: [] if role == "on" else ["role"],
                     watcher=lambda spec: (lambda: dict(power_failure=None, exited_early=False, ticks=20)),
                     battery_intervals=lambda start, end: ([], []),
                     clock=iter(["2026-11-13T01:00:00Z", "2026-11-13T02:00:00Z"]).__next__, repo_state=lambda: _state(spec))


@pytest.mark.parametrize("arm", ["n16", "x", "v"])
def test_a_clean_kv_leg_is_valid(tmp_path, reg, arm):
    envs = []
    receipt = run_kv(kv_spec(tmp_path, reg, arm), FakeOps(), envs=envs)
    assert receipt["verdict"] == "VALID", receipt["problems"]
    assert envs[0]["MLX_BENCH_SESSION_PREFIX"] == f"math500-m76-{arm}-b1"
    assert "p426" not in envs[0]["MLX_BENCH_SESSION_PREFIX"]


def test_the_worker_must_carry_the_arms_kv_flags(tmp_path, reg):
    ops = FakeOps()
    ops.cmdline = cmdline("n16")                      # the X leg's worker without --kv-bits / --tq4-attention
    receipt = run_kv(kv_spec(tmp_path, reg, "x"), ops)
    assert receipt["verdict"] == "INVALID" and any("--kv-bits" in p for p in receipt["problems"])
    ops = FakeOps()
    ops.cmdline = cmdline("v")
    receipt = run_kv(kv_spec(tmp_path / "b", reg, "x"), ops)
    assert receipt["verdict"] == "INVALID" and any("--tq4-attention" in p for p in receipt["problems"])


def test_both_kv_arms_need_engaged_rows(tmp_path, reg):
    rows = [_row("a"), dict(_row("b"), draft=None)]
    receipt = run_kv(kv_spec(tmp_path, reg, "n16", rows=rows), FakeOps())
    assert receipt["verdict"] == "INVALID" and any("missing draft telemetry" in p for p in receipt["problems"])


def test_kv_requests_must_be_cached_session(tmp_path, reg):
    spec = kv_spec(tmp_path, reg, "n16")
    lines = [line.replace("backend=cached_session", "backend=continuous_batching") for line in _log_for(spec._test_rows)]
    receipt = run_kv(spec, FakeOps(), log_lines=lines)
    assert receipt["verdict"] == "INVALID" and any("cached_session" in p for p in receipt["problems"])


def test_a_kv_registry_beyond_the_delta_never_starts(tmp_path, reg):
    bad = reg["x"].replace("    kv_bits: 4\n", "    kv_bits: 4\n    kv_group_size: 32\n", 1)
    spec = kv_spec(tmp_path, reg, "x")
    spec.registry_text = bad
    spec.pins[f"registry_x_sha"] = L.sha256_text(bad)
    ops = FakeOps()
    receipt = run_kv(spec, ops)
    assert receipt["verdict"] == "NOT_STARTED" and "start_router" not in ops.calls
    assert any("kv_group_size" in p for p in receipt["problems"])


def test_a_kv_leg_serves_its_recorded_registry(tmp_path, reg):
    spec = kv_spec(tmp_path, reg, "x")
    spec.pins["registry_x_sha"] = "0" * 64
    receipt = run_kv(spec, FakeOps())
    assert receipt["verdict"] == "NOT_STARTED" and any("registry_x_sha" in p for p in receipt["problems"])
    spec = kv_spec(tmp_path / "b", reg, "x")
    spec.off_registry_text = reg["v"]                 # the base is N16's committed registry, nothing else
    receipt = run_kv(spec, FakeOps())
    assert receipt["verdict"] == "NOT_STARTED"


def test_the_n16_leg_is_the_base_itself(tmp_path, reg):
    spec = kv_spec(tmp_path, reg, "n16")
    spec.registry_text = reg["x"]
    spec.pins["registry_n16_sha"] = L.sha256_text(reg["x"])
    receipt = run_kv(spec, FakeOps())
    assert receipt["verdict"] == "NOT_STARTED"


# ------------------------------------------------------------------------------------------------ A5 (longctx)
def _a5_spec(tmp_path, reg, arm="x"):
    res = tmp_path / "results"
    res.mkdir(parents=True)
    paths = {"retrieval-131072-00": res / f"retrieval.m76-{arm}-b1.retrieval-131072-00.json",
             "reasoning-131072-00": res / f"reasoning.m76-{arm}-b1.reasoning-131072-00.partial.jsonl"}
    spec = kv_spec(tmp_path, reg, arm, planned=tuple(paths), rows=[])
    spec.kind = "longctx"
    spec.rows_path = None
    spec.rows_paths = paths
    spec.destinations = list(paths.values())
    spec.driver_argvs = [["retrieval", "retrieval-131072-00"], ["reasoning", "reasoning-131072-00"]]
    spec.driver_argv = spec.driver_argvs[0]
    spec.expected_requests, spec.expected_extra = 4, 2
    spec.seeds = {i: {"sampler_seed": 11} for i in paths}
    return spec


def _a5_driver(spec, calls, fail_second=False):
    def driver(argv, env, timeout, cwd=None):
        calls.append(list(argv))
        kind, iid = argv
        row = dict(trial=0, seed=5, sampler_seed=11, session_id=f"m76-t-{iid}", prompt_tokens=131100, draft=ENGAGED,
                   content="x", finish_reason="stop")
        cal = f"m76-t-cal-{iid}"
        if kind == "retrieval":
            spec.rows_paths[iid].write_text(json.dumps(dict(records=[dict(ctx=131072, rows=[row])],
                                                            calibration_session_id=cal)))
        else:
            spec.rows_paths[iid].write_text(json.dumps(dict(key="k", record=dict(ctx=131072, rows=[row]))) + "\n")
            Path(f"{spec.rows_paths[iid]}.provenance.json").write_text(json.dumps(dict(calibration_session_id=cal)))
        lines = _log_for([row])
        ts = "2026-10-22 01:00:00,000 - mlx_vlm.server - INFO - "
        lines += [f"{ts}Request started: endpoint=/chat/completions model=m stream=False in_flight=1",
                  f"{ts}Request completed: endpoint=/chat/completions model=m stream=False backend=cached_session session={cal} "
                  f"cached_tokens=0 prompt_tokens=200 generated_tokens=1 elapsed=1.000s finish_reason=length in_flight=0"]
        with spec.server_log.open("a") as f:
            f.write("\n".join(lines) + "\n")
        return 1 if fail_second and kind == "reasoning" else 0
    return driver


def test_an_a5_leg_runs_every_item_invocation_and_reconciles(tmp_path, reg):
    spec, calls = _a5_spec(tmp_path, reg), []
    receipt = run_kv(spec, FakeOps(), driver=_a5_driver(spec, calls))
    assert receipt["verdict"] == "VALID", receipt["problems"]
    assert calls == spec.driver_argvs


def test_a_failing_a5_invocation_is_invalid(tmp_path, reg):
    spec, calls = _a5_spec(tmp_path, reg), []
    receipt = run_kv(spec, FakeOps(), driver=_a5_driver(spec, calls, fail_second=True))
    assert receipt["verdict"] == "INVALID" and any("driver exit 1" in p for p in receipt["problems"])


def test_an_a5_item_without_its_rows_is_invalid(tmp_path, reg):
    spec, calls = _a5_spec(tmp_path, reg), []
    drv = _a5_driver(spec, calls)

    def driver(argv, env, timeout, cwd=None):
        rc = drv(argv, env, timeout, cwd)
        if argv[0] == "reasoning":
            spec.rows_paths["reasoning-131072-00"].unlink()
        return rc
    receipt = run_kv(spec, FakeOps(), driver=driver)
    assert receipt["verdict"] == "INVALID" and any("reasoning-131072-00" in p for p in receipt["problems"])


# ------------------------------------------------------------------------------------------------ the CLI
def test_cli_refusals_under_kv(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    base = ["--axis", "cjudge", "--block", "1", "--stack-root", str(tmp_path), "--workdir", str(tmp_path),
            "--receipt-dir", str(tmp_path / "r")]
    assert L.main(base + ["--arm", "x", "--lever", "kv", "--build", "s2"]) == 2
    assert L.main(base + ["--arm", "on", "--lever", "kv", "--build", "s3"]) == 2
    assert L.main(base + ["--arm", "x", "--lever", "kv", "--build", "s3", "--registry-on", "o.yaml"]) == 2
    assert L.main(base + ["--arm", "x", "--build", "s2"]) == 2                  # a KV arm under the default lever (mtp)
    names = sorted(p.name for p in (tmp_path / "r").iterdir())
    assert names and all(n.endswith(".receipt.json") for n in names)
    assert any(n.startswith("cjudge-m76-x-b1") for n in names)
    assert not any("p426" in n for n in names if "m76" in n)
    frozen = tmp_path / "m76" / "p426" / "frozen.s3.json"
    assert not frozen.exists()
    assert L.main(base + ["--arm", "x", "--lever", "kv", "--build", "s3"]) == 2   # the record is missing: NOT_STARTED


# ------------------------------------------------------------------------------------------------- fix round 1 (spec v1.2)
@pytest.mark.parametrize("pair", P.KV_PAIRS)
def test_registry_delta_problems_takes_the_kv_lever(reg, pair):
    """v1.2: the existing `registry_delta_problems` takes `lever=` (arms given or read from each text's KV state)."""
    a, b = pair
    assert L.registry_delta_problems(reg[a], reg[b], ENTRY, lever="kv") == []
    assert L.registry_delta_problems(reg[a], reg[b], ENTRY, lever="kv", arms=(a, b)) == []
    assert L.registry_delta_problems(reg[a], reg[a], ENTRY, lever="kv")                      # one KV state: refused
    bad = reg[b].replace("draft_kind: mtp", "draft_kind: none", 1)
    assert L.registry_delta_problems(reg[a], bad, ENTRY, lever="kv")                         # an MTP key differs
    with pytest.raises(ValueError):
        L.registry_delta_problems(reg[a], reg[b], ENTRY, lever="bogus")
    # lever mtp (the default) is today's rule: two KV arms are no MTP restore delta
    assert L.registry_delta_problems(reg[a], reg[b], ENTRY) == L.registry_delta_problems(reg[a], reg[b], ENTRY, lever="mtp")
    assert L.registry_delta_problems(reg[a], reg[b], ENTRY)


@pytest.mark.parametrize("arm", ["n16", "x", "v"])
def test_model_argv_problems_takes_the_kv_lever(reg, arm):
    hf = L._models(reg[arm])[0][ENTRY]["hf_path"]
    line = cmdline(arm).replace(f"caslca/{ENTRY} ", f"{hf} ", 1)
    assert L.model_argv_problems(line, reg[arm], ENTRY, lever="kv") == []
    assert L.model_argv_problems(line, reg[arm], ENTRY, lever="kv", arm=arm) == []
    other = {"n16": "x", "x": "v", "v": "n16"}[arm]
    assert L.model_argv_problems(line, reg[arm], ENTRY, lever="kv", arm=other)               # the other arm's flags
    stripped = " ".join(t for t in line.split() if t not in ("--draft-kind", "mtp"))
    assert L.model_argv_problems(stripped, reg[arm], ENTRY, lever="kv")                      # MTP ON is required
