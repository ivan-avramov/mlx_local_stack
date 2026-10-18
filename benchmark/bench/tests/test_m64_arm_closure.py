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


# P371 (C178): the shared core, corpus and adapter are IN every probe closure now (the tg1 epoch rotated once, accepted);
# what stays out is checked per entry. Exclusions only ever grow.
CORE = {"benchmark/bench/arm_runner.py", "benchmark/bench/arm_adapter.py", "benchmark/bench/arm_opencode.py",
        "benchmark/bench/arm_watchdog.py", "benchmark/bench/corpus.py", "benchmark/bench/corpus_tg1.py",
        "benchmark/bench/run_config.py", "benchmark/bench/host.py", "benchmark/bench/worker_receipts.py"}
NEVER = {"benchmark/bench/chain_hooks.py", "benchmark/bench/web_evidence.py", "benchmark/bench/chain_ops.py",
         "benchmark/bench/chain_rows.py", "benchmark/bench/schedules.py"}


def pi_dsh_or_tg2(files):
    return sorted(f for f in files if "/tg2_" in f or "/arm_pi" in f or "/arm_dsh" in f or "/pi_" in f or "/dsh_" in f)


def test_the_tg1_probe_closure_holds_the_core_and_excludes_the_forbidden_modules():
    got = closure("benchmark/run_tg1_probe.py")
    assert CORE <= got
    assert not (got & SCORING), sorted(got & SCORING)
    assert not (got & NEVER), sorted(got & NEVER)
    assert "benchmark/bench/m64_search.py" not in got and "benchmark/run_oc_probe.py" not in got
    assert not pi_dsh_or_tg2(got), pi_dsh_or_tg2(got)


def test_the_tg1_carrier_and_plugins_the_arm_wraps_are_unedited_by_this_build():
    import subprocess
    base = subprocess.run(["git", "merge-base", "HEAD", "main"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    assert base, "no merge base with main"
    changed = subprocess.run(["git", "diff", "--name-only", base, "HEAD"], cwd=REPO, capture_output=True,
                             text=True).stdout.split()
    assert "benchmark/opencode_bench_v2_web_tg1.json" not in changed
    kept = {"benchmark/opencode_plugins/" + n for n in ("noretry.js", "toolbounds.js", "datefreeze.js")}
    assert not (set(changed) & kept), sorted(set(changed) & kept)


def test_the_m64_oc_probe_closure_is_generation_only():
    got = closure("benchmark/run_oc_probe.py")
    assert NEW <= got and CORE <= got and not (got & SCORING)
    assert not (got & NEVER), sorted(got & NEVER)
    assert not pi_dsh_or_tg2(got), pi_dsh_or_tg2(got)
    assert closure("benchmark/run_tg1_probe.py") - {"benchmark/run_tg1_probe.py", "benchmark/bench/tg1_runner.py"} <= got


def test_the_search_service_is_imported_by_the_oc_entry_only():
    assert "benchmark/bench/m64_search.py" in closure("benchmark/run_oc_probe.py")
    assert "benchmark/bench/m64_search.py" not in closure("benchmark/bench/arm_opencode.py")


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
