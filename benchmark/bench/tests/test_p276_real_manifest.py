"""P276 (2026-10-11): the chain runner's identity pin must read the manifest the REAL probe writes.

The first live pilot aborted at the first-manifest barrier with `runtime_universe_sha256_invalid`: the real
`opencode-v2-web-tg1` probe records the universe sha only at `runtime.policy.universe_sha256`, while the runner read
`runtime.universe_sha256` — where `fake_probe.py` (the test contract) had put it, masking the mismatch. The fixture is
the scrubbed manifest of that pilot (m5max-128, 2026-10-11)."""
import json
from pathlib import Path

from bench import chain_ops as co
from chains.c147 import fake_probe as FP

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "c147_real_tg1_pilot_manifest.json"


def real():
    return json.loads(FIXTURE.read_text())


def test_the_real_probe_manifest_has_no_malformed_identity():
    assert co.malformed_identity(real()) == []


def test_runtime_identity_reads_every_pinned_field_from_the_real_layout():
    man = real()
    ident = co.runtime_identity(man)
    assert set(ident) == set(co.RUNTIME_PINNED)
    assert ident["universe_sha256"] == man["runtime"]["policy"]["universe_sha256"]
    assert "universe_sha256" not in man["runtime"]          # the probe does not write it at top level


def test_fake_probe_mirrors_the_real_identity_layout():
    fake = FP.build_manifest("m", "python", 1001, {"pid": 1}, "r")
    for k in co.RUNTIME_PINNED:
        in_real_top = k in real()["runtime"]
        in_fake_top = k in fake["runtime"]
        assert in_real_top == in_fake_top, k
    assert "universe_sha256" in fake["runtime"]["policy"]


ROW = FIXTURE.parent / "c147_real_tg1_pilot_row.json"


def test_runner_checks_the_seed_field_the_real_probe_writes():
    # pilot attempt 2 aborted INCOMPLETE on `row_sample_seed: None != <seed>`: the real field is `sampler_seed`
    from bench import rowschema
    row = json.loads(ROW.read_text())
    assert co.ROW_SEED_FIELD == "sampler_seed" and "sample_seed" not in row
    assert row[co.ROW_SEED_FIELD] == rowschema.sample_seed(row["id"], 0, row["seed_base"])


def test_fake_probe_rows_use_the_real_seed_field(tmp_path):
    out = tmp_path / "x.jsonl"
    FP.write_leg(out, "m", "python", 1001, ["python/a"], {"pid": 1, "create_time": 1.0, "model_path": "m",
                                                        "registry_sha256": "a" * 64}, tmp_path)
    row = json.loads(out.read_text().splitlines()[0])
    assert co.ROW_SEED_FIELD in row and "sample_seed" not in row
