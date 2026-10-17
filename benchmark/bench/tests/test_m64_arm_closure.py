"""M64 step 4a: the new modules are NOT in the tg1 generation closure (tg1's identity is untouched) and the M64 oc probe's
own closure is generation-only (no scoring), with the identity round trip through the arm entry."""
from __future__ import annotations

import json
from pathlib import Path

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import arm_runner
from bench import identity_closure as ic
from bench.tests.test_opencode_v2_probe import tg1_probe as probe          # noqa: F401  (fixture)

REPO = Path(__file__).resolve().parents[3]
NEW = {"benchmark/bench/arm_adapter.py", "benchmark/bench/arm_opencode.py", "benchmark/bench/arm_runner.py",
       "benchmark/bench/arm_watchdog.py", "benchmark/run_oc_probe.py"}
SCORING = {"benchmark/bench/answer_key.py", "benchmark/bench/web_audit.py", "benchmark/bench/web_scan.py",
           "benchmark/bench/tg1_score.py", "benchmark/bench/generate.py", "benchmark/bench/row_scores.py"}


def closure(entry):
    return {p.resolve().relative_to(REPO.resolve()).as_posix() for p in ic.python_closure(REPO / entry, REPO)}


def test_the_tg1_probe_closure_contains_none_of_the_arm_modules():
    assert not (closure("benchmark/run_tg1_probe.py") & NEW)


def test_the_tg1_modules_the_arm_wraps_are_unedited_by_this_build():
    import subprocess
    base = subprocess.run(["git", "merge-base", "HEAD", "main"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    assert base, "no merge base with main"
    changed = subprocess.run(["git", "diff", "--name-only", base, "HEAD"], cwd=REPO, capture_output=True,
                             text=True).stdout.split()
    tg1 = closure("benchmark/run_tg1_probe.py")
    assert not (set(changed) & tg1), sorted(set(changed) & tg1)
    assert "benchmark/opencode_bench_v2_web_tg1.json" not in changed
    assert not any(c.startswith("benchmark/opencode_plugins/") for c in changed)


def test_the_m64_oc_probe_closure_is_generation_only():
    got = closure("benchmark/run_oc_probe.py")
    assert NEW <= got and not (got & SCORING)
    assert closure("benchmark/run_tg1_probe.py") <= got | {"benchmark/run_tg1_probe.py"}


def test_print_identity_round_trip_through_the_arm_runner(probe, monkeypatch, tmp_path, capsys):
    from bench import toolchain
    monkeypatch.setattr(toolchain, "current", lambda: {"lock_sha256": "l", "interpreter": "i", "grader_image_id": "g"})
    binary = tmp_path / "opencode"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
    monkeypatch.setattr(probe, "_polyglot_sha", lambda root: "7" * 40)
    monkeypatch.setattr(probe, "_polyglot_root", lambda: tmp_path)
    adapter = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())

    class A:
        agent_system_file = None
        universe = REPO / "benchmark/m62/universe.json"
        tg1_inject = None
        sampling_profile = "deployed"

    assert arm_runner.print_identity(probe, adapter, A) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["arm"] == "oc" and out["scaffold"] == "opencode-v2-web-tg1c" and out["opencode_version"] == "2.0.20"
    assert out["generation_identity_sha256"] and len(out["generation_identity_sha256"]) == 64
    assert out["scaffold_policy_sha256"] and out["probe_code_sha256"] and out["polyglot_sha"] == "7" * 40
    _ = aa
