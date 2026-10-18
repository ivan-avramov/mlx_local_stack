"""P371 phase 4 (plan 5, P311 closures per entry): ONE fake end-to-end item through the M64 oc ENTRY (`run_oc_probe` as the
host, bound exactly as `run_oc_probe._main` binds it: the m64 template, an evidence policy without the chain's barrier, the offline test search service, a fake client binary). On its own this is an
ordinary item test; `test_p371_closures.py` runs it in a fresh interpreter with the module-dump plugin and compares the
modules it loaded with the static closure of `run_oc_probe.py`."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from bench import arm_opencode as ao
from bench import arm_runner
from bench import corpus_tg1
from bench.tests.test_opencode_v2_probe import MODEL
from bench.tests.test_tg1_integration import FROZEN, tg_fixture

REPO = Path(__file__).resolve().parents[3]


def run_fake_oc_item(monkeypatch, tmp_path):
    """One fake item through the oc entry; returns the rows file (the manifest is its sibling)."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    entry = importlib.import_module("run_oc_probe")
    f = tg_fixture(entry, monkeypatch, tmp_path)
    monkeypatch.setattr(ao, "CARRIER", REPO / "benchmark/opencode_bench_v2_web_tg1.json")
    monkeypatch.setattr(arm_runner, "worker_json", lambda e: (
        {"configured_context_limit": 262144} if e == "health" else {"summary": {"in_flight": 0}}))
    adapter = ao.OpencodeArm(entry, mode="m64", search=ao.OfflineTestSearchService())
    monkeypatch.setattr(adapter, "_prove_plugins", lambda *a, **k: None)      # the fake client has no plugin API
    out = tmp_path / "rows.jsonl"
    argv = ["probe", "--model", MODEL, "--items", "one", "--seed-base", "77", "--scaffold", "opencode-v2-web-tg1c",
            "--limit", "5", "--out", str(out), "--universe", str(tmp_path / "universe.json"), "--frozen-prompt-date", FROZEN]
    monkeypatch.setattr(sys, "argv", argv)
    a = entry._parser().parse_args(argv[1:])
    corpus = corpus_tg1.Tg1Corpus(a.universe or arm_runner.DEFAULT_UNIVERSE, polyglot_root=entry._polyglot_root,
                                  polyglot_sha=entry._polyglot_sha)              # what `run_oc_probe._main` binds
    assert arm_runner.main(entry, adapter, a, template=ao.m64_template(),
                           evidence=ao.m64_evidence(receipts="absent", item_barrier="off"), corpus=corpus) == 0
    return out


def test_a_fake_item_runs_through_the_oc_entry(monkeypatch, tmp_path):
    out = run_fake_oc_item(monkeypatch, tmp_path)
    (row,) = [json.loads(line) for line in out.read_text().splitlines()]
    assert row["config_id"] == "m64-oc-tg1" and row["arm"] == "oc" and row["passed"] is True
