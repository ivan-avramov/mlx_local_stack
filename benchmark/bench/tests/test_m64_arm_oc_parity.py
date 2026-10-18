"""M64 step 4a PARITY (P371: one core): the tg1 entry (`tg1_runner.main`) and the opencode arm in tg1 configuration driven
directly through `arm_runner.main` with the tg1 bindings write the SAME rows, manifest runtime, evidence contents and,
against the real pinned client, the exact request sequence on the wire; only values that name a run (paths, ids, clocks)
differ."""
from __future__ import annotations

import json
import sys

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import arm_runner
from bench.tests.arm_entry import tg1_main
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_tg1_integration import FROZEN, pinned_binary, tg_fixture      # noqa: F401  (fixtures)

# values that name a run, not what the run did: evidence locations (the stem and run id), wall clocks, and the
# generation composite (the arm joins it: spec 4). Evidence CONTENTS are compared through their sha256.
RUN_NAMING = {"datefreeze_path", "events_path", "stderr_path", "transcript_path", "tmp_window", "wall_s",
              "generation_identity_sha256", "grade_reports", "final_tree"}


def run_arm(f, p, tmp_path, monkeypatch, out, adapter, items="one", extra=()):
    argv = ["probe", "--model", MODEL, "--items", items, "--seed-base", "77", "--scaffold", "opencode-v2-web-tg1",
            "--limit", "5", "--out", str(out), "--universe", str(tmp_path / "universe.json"),
            "--frozen-prompt-date", FROZEN, *extra]
    monkeypatch.setattr(sys, "argv", argv)
    return tg1_main(p, adapter, p._parser().parse_args(argv[1:]))


def rows_of(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_rows_and_manifest_equal_the_tg1_path_except_the_arm_fields(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    a, b = tmp_path / "tg1.jsonl", tmp_path / "arm.jsonl"
    assert f["run"]("one", extra=["--out", str(a)]) == 0
    assert run_arm(f, probe, tmp_path, monkeypatch, b, ao.OpencodeArm(probe, mode="tg1")) == 0
    (ra,), (rb,) = rows_of(a), rows_of(b)
    assert set(rb) == set(ra)
    for key in sorted(set(ra) - RUN_NAMING):
        assert ra[key] == rb[key], key
    assert {k: v for k, v in ra["final_tree"].items() if k != "manifest"} == {
        k: v for k, v in rb["final_tree"].items() if k != "manifest"}                   # the manifest PATH names the run
    assert ra["evidence_sha256"] == rb["evidence_sha256"]                       # events, stderr, export, receipts: same bytes
    assert [r["outcome"] for r in ra["grade_reports"]] == [r["outcome"] for r in rb["grade_reports"]]
    assert rb["arm"] == "oc" and rb["snapshot_sha256"] and rb["epoch_id"] is None
    ma = json.loads(a.with_suffix(".manifest.json").read_text())
    mb = json.loads(b.with_suffix(".manifest.json").read_text())
    assert set(mb) == set(ma)
    assert set(mb["runtime"]) == set(ma["runtime"])
    for key in set(ma["runtime"]) - {"generation_identity_sha256"}:
        assert ma["runtime"][key] == mb["runtime"][key], key
    assert mb["runtime"]["snapshot_fields"]["compaction"] == "off" and mb["runtime"]["config_id"] == "tg1"
    assert mb["runtime"]["evidence_policy"]["namespace"] == "opencode_transcripts"


def test_tg1_mode_rows_carry_no_m64_only_blocks(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert run_arm(f, probe, tmp_path, monkeypatch, tmp_path / "b.jsonl", ao.OpencodeArm(probe, mode="tg1")) == 0
    (row,) = rows_of(tmp_path / "b.jsonl")
    assert "compaction" not in row and "shell_watchdog" not in row
    assert "carrier_transform" not in row and row["scaffold"] == "opencode-v2-web-tg1"


def test_the_tg1_composite_is_the_p311_recipe_and_the_m64_arm_joins_the_arm(probe, monkeypatch, tmp_path):
    from bench import tg1_runner
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert run_arm(f, probe, tmp_path, monkeypatch, tmp_path / "b.jsonl", ao.OpencodeArm(probe, mode="tg1")) == 0
    rt = json.loads((tmp_path / "b.jsonl").with_suffix(".manifest.json").read_text())["runtime"]
    assert rt["generation_identity_sha256"] == tg1_runner.generation_identity_sha256(rt)      # P311: no arm in it
    assert rt["generation_identity_sha256"] != aa.arm_generation_sha256("oc", rt, ao.OpencodeArm.GENERATION_FIELDS)
    m64 = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
    assert m64.generation_identity_sha256(rt) == aa.arm_generation_sha256("oc", rt, ao.OpencodeArm.GENERATION_FIELDS)


def test_a_resumed_arm_probe_skips_done_items_and_refuses_a_changed_arm_field(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    out = tmp_path / "b.jsonl"
    assert run_arm(f, probe, tmp_path, monkeypatch, out, ao.OpencodeArm(probe, mode="tg1")) == 0
    assert run_arm(f, probe, tmp_path, monkeypatch, out, ao.OpencodeArm(probe, mode="tg1")) == 0       # resume: no-op
    assert len(rows_of(out)) == 1
    with pytest.raises(SystemExit, match="resume provenance differs"):
        _changed_epoch(f, probe, tmp_path, monkeypatch, out)


def _changed_epoch(f, probe, tmp_path, monkeypatch, out):
    argv = ["probe", "--model", MODEL, "--items", "two", "--seed-base", "77", "--scaffold", "opencode-v2-web-tg1",
            "--limit", "5", "--out", str(out), "--universe", str(tmp_path / "universe.json"),
            "--frozen-prompt-date", FROZEN]
    monkeypatch.setattr(sys, "argv", argv)
    a = probe._parser().parse_args(argv[1:])
    a.epoch_id = "e" * 64
    return tg1_main(probe, ao.OpencodeArm(probe, mode="tg1"), a)


def test_a_failing_transcript_still_leaves_its_raw_evidence(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    binary = tmp_path / "opencode"
    binary.write_text(binary.read_text().replace("session) cat", "session) echo partial; exit 3; cat"))
    with pytest.raises(SystemExit, match="session export failed"):
        run_arm(f, probe, tmp_path, monkeypatch, tmp_path / "b.jsonl", ao.OpencodeArm(probe, mode="tg1"))
    exports = list(tmp_path.rglob("python__one.json"))
    assert exports and exports[0].read_text().strip() == "partial"                  # tg1 writes the raw output first


# ---------------------------------------------------------------- the request sequence against the real client
def bodies(mock):
    return [(c["path"], c["body"]) for c in mock.chats]


def test_the_request_sequence_on_the_wire_is_identical_to_the_tg1_path(probe, pinned_binary, monkeypatch, tmp_path):
    seqs = []
    for arm_path in (False, True):
        with MockServer({}) as mock:
            sub = tmp_path / ("arm" if arm_path else "tg1")
            sub.mkdir()
            f = tg_fixture(probe, monkeypatch, sub, binary=pinned_binary, mock=mock)
            monkeypatch.setattr(arm_runner.provenance, "opencode_v2_destination",
                                lambda *a, **k: mock.base)                    # isolate the config-endpoint race
            if arm_path:
                assert run_arm(f, probe, sub, monkeypatch, sub / "b.jsonl", ao.OpencodeArm(probe, mode="tg1")) == 0
            else:
                assert f["run"]("one") == 0
            assert len(mock.chats) == 2 and mock.tripwire_hits == 0
            seqs.append(bodies(mock))
    assert seqs[0] == seqs[1]


def test_the_request_bodies_carry_the_paired_seed_and_the_deployed_budgets(probe, pinned_binary, monkeypatch, tmp_path):
    with MockServer({}) as mock:
        f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
        monkeypatch.setattr(arm_runner.provenance, "opencode_v2_destination",
                            lambda *a, **k: mock.base)
        assert run_arm(f, probe, tmp_path, monkeypatch, tmp_path / "b.jsonl", ao.OpencodeArm(probe, mode="tg1")) == 0
        (row,) = rows_of(tmp_path / "b.jsonl")
        for _, body in bodies(mock):
            assert body["seed"] == row["sampler_seed"] and body["thinking_budget"] == 81920
            assert body["max_tokens"] == 102400 and body["enable_thinking"] is True
