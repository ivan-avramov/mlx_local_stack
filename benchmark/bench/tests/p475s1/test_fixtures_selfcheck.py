"""The fake's fixed formats against the REAL parsers / sources (these run on the baseline: they prove the fixtures reproduce what the
contract says they reproduce, not the candidate)."""
import importlib.util
import re

import pytest

from bench import chain_ops, paths
from bench import p426_leg

from . import fakes
from .fakes import ARMS, kv_line, pmset_log_text, pmset_texts, strict_row, worker_argv

ROOT = paths.repo_root()


def test_pmset_text_parses_with_the_real_parse_power():
    # class: preserves an invariant
    ac, bt = pmset_texts(140, 28, 80)
    assert chain_ops.parse_power(ac, bt) == {"watts": 140, "volts": 28.0, "batt": 80}


def test_pmset_log_text_is_a_well_formed_history_for_the_real_reader():
    # class: preserves an invariant
    text = pmset_log_text([(1_800_000_100.0, "Batt"), (1_800_000_200.0, "AC")])
    assert p426_leg.power_history_problems(0, text) == []


def test_pmset_log_text_battery_intervals_match_the_forks_reader():
    # class: preserves an invariant
    path = ROOT / "src/mlx-vlm/dev/p369_phase2/qualify.py"
    spec = importlib.util.spec_from_file_location("qualify_for_selfcheck", path)
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"the fork's qualify.py does not import here: {type(exc).__name__}")
    text = pmset_log_text([(1_800_000_100.0, "Batt"), (1_800_000_200.0, "AC")])
    got = mod.battery_intervals(text, 1_800_000_000.0, 1_800_000_300.0)
    assert len(got) == 1 and got[0][1] is not None


def test_kv_line_field_order_is_the_servers():
    # class: preserves an invariant (app.py logs these fields in this order)
    src = (ROOT / "src/mlx-vlm/mlx_vlm/server/app.py").read_text()
    m = re.search(r'"KV cache resolved:(.*?)",\s*kv_bits,', src, re.S)
    assert m, "the server's log statement moved"
    names = re.findall(r"(\w+)=%r", re.sub(r'"\s*"', "", m.group(1)))
    mine = re.findall(r"(\w+)=", kv_line("TQ4").split("KV cache resolved:")[1])
    assert names == mine


@pytest.mark.parametrize("arm", ARMS)
def test_worker_argv_flags_are_flags_mlx_serve_emits(arm):
    # class: preserves an invariant (every flag the fake emits exists in `_build_command`)
    src = (ROOT / "src/mlx-serve/src/mlx_serve/process_manager.py").read_text()
    for tok in worker_argv("/wt", arm):
        if tok.startswith("--"):
            assert f'"{tok}"' in src, tok


def test_mlx_serve_emits_no_kv_group_size_flag():
    # class: preserves an invariant (a fact the contract's R3 wording leans on: `--kv-group-size` is checked by exact argv equality,
    # not because `_build_command` ever emits it)
    src = (ROOT / "src/mlx-serve/src/mlx_serve/process_manager.py").read_text()
    assert "--kv-group-size" not in src


def test_strict_row_keys_are_the_servers_timings_keys():
    # class: preserves an invariant
    schemas = (ROOT / "src/mlx-vlm/mlx_vlm/server/schemas.py").read_text()
    row = strict_row("TQ4", 8192)
    for k in ("prompt_n", "cache_n", "predicted_n", "prompt_ms", "prompt_per_second", "predicted_per_second", "draft_kind",
              "draft_rounds", "draft_n", "draft_n_accepted"):
        assert re.search(rf"^\s+{k}:", schemas, re.M), k
        assert k in row


def test_the_fake_ladder_row_passes_its_own_strict_rule_shape():
    # class: preserves an invariant (ON row: 256 tokens, length, cache_n 0, rate = n / ms)
    r = strict_row("TQ4", 131072)
    assert r["completion_tokens"] == r["predicted_n"] == 256 and r["finish_reason"] == "length" and r["cache_n"] == 0
    assert abs(r["prompt_per_second"] - r["prompt_n"] / (r["prompt_ms"] / 1000)) < 1e-6
    assert "draft_kind" not in strict_row("TQ4-OFF", 131072)


# ------------------------------------------------------------------------------------------- the fake's own machinery
@pytest.mark.parametrize("mode,valid", [("ok", True), ("ticks:7", True), ("ticks:6", True), ("power_fail", False),
                                        ("gap", False), ("no_exit", False), ("early_exit", False)])
def test_watch_journal_modes_read_as_intended_by_the_real_p426_verdict(tmp_path, mode, valid):
    # class: preserves an invariant (the journal fixture is judged by `bench_watch.speed_verdict`, the P426 reader capacity mode
    # reuses; `ticks:6` is valid for the READER and fails only the contract's own count rule (driver interval - 600) // 300 = 7)
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "benchmark" / "m1"))
    import bench_watch as W
    d = SimpleNamespace(pid=1, ct=2.0)
    p = tmp_path / "watch.jsonl"
    p.write_text(fakes.watch_journal(1_800_000_000.0, 1_800_000_000.0 + 2760.0, d, mode))
    assert W.speed_verdict(p)["valid"] is valid, W.speed_verdict(p)


def test_a_manual_pass_through_the_fake_ops_writes_what_the_contract_says(tmp_path, monkeypatch):
    # class: preserves an invariant (stack -> router -> load -> driver -> files, with the real argv / log formats)
    import json
    w = fakes.World(tmp_path, monkeypatch).make_worktrees()
    ops = fakes.FakeOps(w)
    st = ops.stack(w.wt("TQ4"), w.wt("TQ4") / "main_models.yaml", "mtp")
    st.start_router()
    ident = st.load(fakes.PICK)
    assert ident["cmdline"][0].endswith("mlx_vlm.server") and "--kv-bits" in ident["cmdline"]      # RealOps' `load`: the argv list
    assert ops.port_listener(8000) == st.router["pid"]
    argv = [str(w.wt("TQ4") / ".venv-bench/bin/python"), "-m", "bench.run_capacity", "--model", fakes.PICK, "--grid", "8192,131072",
            "--out-tag", "p475-u4-tq4-b1.a1", "--expected-rung-seconds", "60,400"]
    proc = ops.spawn(argv, {"MLX_BENCH_SESSION_PREFIX": "p475-u4-tq4-b1.a1"}, w.wt("TQ4") / "benchmark")
    assert ops.wait(proc, 10.0) is None                      # not finished yet: the fake driver takes its derived duration
    assert ops.wait(proc, 10_000.0) == 0
    out = w.wt("TQ4") / "benchmark/results" / fakes.PICK
    rows = [json.loads(x) for x in (out / "capacity_ladder.p475-u4-tq4-b1.a1.jsonl").read_text().splitlines()]
    assert [r["ctx"] for r in rows] == [8192, 131072] and rows[0]["session_id"].startswith("p475-u4-tq4-b1.a1")
    assert st.stop_stack() == 0 and ops.port_listener(8000) is None and w.procs == {}
