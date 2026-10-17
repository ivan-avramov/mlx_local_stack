"""P311-lite (iv): the shared generation composite (spec 4, test 3)."""
import json
import subprocess
from pathlib import Path

import pytest

from bench import identity_closure as ic
from bench import tg1_runner as runner

REPO = Path(__file__).resolve().parents[3]
ENTRY = "benchmark/run_tg1_probe.py"


@pytest.fixture
def p(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    import importlib
    return importlib.import_module("run_tg1_probe")


def selection(p):
    return p._carrier_selection(runner.SCAFFOLD, None, source=runner.CARRIER)


def ident(p, **kw):
    return runner.identity(p, selection(p), "u" * 64, "2.0.20", Path(p.__file__), **kw)


# ---- composite (spec 4)
COMPOSITE = ("probe_code_sha256", "scaffold_policy_sha256", "opencode_version", "opencode_exe_sha256",
             "opencode_bench_config_sha256", "carrier_source_sha256", "agent_system_sha256", "polyglot_sha",
             "sampling_profile")


def full(p):
    base = ident(p)
    base.update(selection(p)["fields"], polyglot_sha="p" * 40, sampling_profile="deployed", seed_base=1, lang="python")
    return base


def test_composite_names_exactly_the_listed_fields_in_a_canonical_hash(p):
    import hashlib
    base = full(p)
    fields = runner.generation_fields(base)
    assert set(fields) == set(COMPOSITE)
    want = hashlib.sha256(json.dumps({k: base[k] for k in COMPOSITE}, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
    assert runner.generation_identity_sha256(base) == want


@pytest.mark.parametrize("field", COMPOSITE)
def test_composite_changes_for_each_listed_field(p, field):
    base = full(p)
    changed = dict(base)
    changed[field] = "changed" if base[field] is None else str(base[field]) + "x"
    assert runner.generation_identity_sha256(changed) != runner.generation_identity_sha256(base)


@pytest.mark.parametrize("field", ["seed_base", "lang", "id", "model", "prompt_date", "a4_v2_pass"])
def test_composite_ignores_fields_that_are_not_generation_identity(p, field):
    base = full(p)
    other = {**base, field: "different"}
    assert runner.generation_identity_sha256(other) == runner.generation_identity_sha256(base)


@pytest.mark.parametrize("field", COMPOSITE)
def test_composite_fails_closed_on_a_missing_field(p, field):
    base = full(p)
    del base[field]
    with pytest.raises(ValueError, match=field):
        runner.generation_identity_sha256(base)


def test_print_identity_adds_the_composite(p, capsys, monkeypatch, tmp_path):
    binary = tmp_path / "opencode"
    binary.write_bytes(b"fake")
    corpus = tmp_path / "poly"
    corpus.mkdir()
    for cmd in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", "-C", str(corpus), *cmd], check=True)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
    monkeypatch.setenv("POLYGLOT_DIR", str(corpus))

    class A:
        universe = None
        agent_system_file = None
        tg1_inject = None
        sampling_profile = "deployed"
    assert runner.print_identity(p, A()) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["generation_identity_sha256"]) == 64 and len(out["polyglot_sha"]) == 40
    assert out["toolchain"]["grader_image_id"].startswith("sha256:")
    assert out["probe_code_sha256"] == ic.closure_sha256(ENTRY, REPO, data=runner.GENERATION_DATA)
