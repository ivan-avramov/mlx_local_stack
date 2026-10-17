"""P364 chain side: the frozen prompt date is epoch metadata (chain.json), taken from the reference epoch or stated
explicitly at epoch start, frozen and reverified on resume, never defaulted to today."""

from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from bench import chain_ops as co
from bench.tests.test_c147_chain_runner import (  # noqa: F401
    C147, CHAIN, EPOCH_DATE, FP, PICK1, PILOT, R, arg, chain_json, env, invocations, log_has, run)

OTHER = "Tue Jan 06 2026"
TODAY = time.strftime("%a %b %d %Y")


def test_build_cmd_carries_the_frozen_date_only_when_given():
    leg = dict(model=PICK1, lang="python", seed_base=1001, out="/o/x.jsonl")
    step = dict(kind="pilot", names=["a"], limit=5)
    assert "--frozen-prompt-date" not in R.build_cmd("/py", "/p.py", leg, step, "/r", "/c", "/k")
    cmd = R.build_cmd("/py", "/p.py", leg, step, "/r", "/c", "/k", frozen=EPOCH_DATE)
    assert arg(cmd, "--frozen-prompt-date") == EPOCH_DATE and cmd[-2:] == ["--frozen-prompt-date", EPOCH_DATE]


def test_parse_args_rejects_a_malformed_date():
    with pytest.raises(SystemExit) as e:
        R.parse_args(CHAIN + ["--frozen-prompt-date", "2026-01-05"])
    assert e.value.code == 2
    assert R.parse_args(CHAIN + ["--frozen-prompt-date", EPOCH_DATE]).frozen_prompt_date == EPOCH_DATE


def test_a_new_epoch_without_a_date_refuses_and_writes_nothing(env):
    rc = run(env, PILOT, frozen=None)
    assert rc == 2 and not (env["out"] / "chain.json").exists() and invocations(env) == []
    assert log_has(env, "never defaulted to today")


def test_both_date_sources_refuse(env, tmp_path):
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps({"frozen_prompt_date": EPOCH_DATE}))
    rc = run(env, PILOT + ["--frozen-prompt-date", EPOCH_DATE, "--frozen-date-from", str(ref)])
    assert rc == 2 and not (env["out"] / "chain.json").exists()


def test_explicit_date_is_frozen_in_chain_json_and_reaches_the_probe_rows(env):
    assert run(env, PILOT) == 0
    doc = chain_json(env)
    assert doc["frozen_prompt_date"] == EPOCH_DATE and doc["frozen_prompt_date_source"] == {"kind": "explicit"}
    assert all(arg(i["argv"], "--frozen-prompt-date") == EPOCH_DATE for i in invocations(env))
    out = env["out"] / "pilot" / f"{PICK1}.pilot.opencode_python.jsonl"
    rows = [json.loads(s) for s in out.read_text().splitlines()]
    assert rows and all(r["prompt_date"] == EPOCH_DATE for r in rows)
    assert all(r["prompt_date_update_removed"] is False for r in rows)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    assert man["runtime"]["frozen_prompt_date"] == EPOCH_DATE


def test_the_date_comes_from_the_reference_epochs_chain_json(env, tmp_path):
    ref = tmp_path / "reference" / "chain.json"
    ref.parent.mkdir()
    ref.write_text(json.dumps({"frozen_prompt_date": OTHER, "policy_sha256": "b" * 64}))
    assert run(env, PILOT + ["--frozen-date-from", str(ref)]) == 0
    doc = chain_json(env)
    assert doc["frozen_prompt_date"] == OTHER
    src = doc["frozen_prompt_date_source"]
    assert src["kind"] == "reference" and src["chain_json"] == "reference/chain.json"
    assert src["chain_json_sha256"] == co.hashlib.sha256(ref.read_bytes()).hexdigest()
    assert str(tmp_path) not in json.dumps(doc["frozen_prompt_date_source"])           # no absolute paths recorded
    assert all(arg(i["argv"], "--frozen-prompt-date") == OTHER for i in invocations(env))


@pytest.mark.parametrize("content", [None, "garbage", json.dumps({}), json.dumps({"frozen_prompt_date": "2026-01-05"}),
                                     json.dumps([1])])
def test_a_reference_without_a_valid_date_refuses(env, tmp_path, content):
    ref = tmp_path / "ref.json"
    if content is not None:
        ref.write_text(content)
    assert run(env, PILOT + ["--frozen-date-from", str(ref)], frozen=None) == 2
    assert not (env["out"] / "chain.json").exists() and invocations(env) == []


def resume_chain(env, *extra):
    """A Chain over the finished epoch's out-root, as a resumed run builds it (init_lifecycle is the resume gate)."""
    from bench.tests.test_c147_chain_runner import TIMERS
    args = R.parse_args(PILOT + ["--probe", str(C147 / "fake_probe.py"), "--python", sys.executable, "--out-root",
                                 str(env["out"]), *extra])
    chain = R.Chain(args, env["ops"], R.Timers(**TIMERS), lambda *_: None, R.load_universe(), env["out"])
    chain.init_lifecycle()
    return chain


def test_resume_keeps_the_recorded_date_and_reverifies_an_argument(env):
    assert run(env, PILOT) == 0
    assert resume_chain(env).frozen == EPOCH_DATE                    # no argument: the recorded date is used
    assert resume_chain(env, "--frozen-prompt-date", EPOCH_DATE).frozen == EPOCH_DATE
    record = (env["out"] / "chain.json").read_text()
    with pytest.raises(R.RecordInvalid, match="differs from the chain's frozen"):
        resume_chain(env, "--frozen-prompt-date", OTHER)
    assert (env["out"] / "chain.json").read_text() == record         # the record is never rewritten


def test_resume_against_a_reference_with_another_date_refuses(env, tmp_path):
    assert run(env, PILOT) == 0
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps({"frozen_prompt_date": OTHER}))
    with pytest.raises(R.RecordInvalid, match="differs from the chain's frozen"):
        resume_chain(env, "--frozen-date-from", str(ref))
    ref.write_text(json.dumps({"frozen_prompt_date": EPOCH_DATE}))
    assert resume_chain(env, "--frozen-date-from", str(ref)).frozen == EPOCH_DATE


def test_resume_of_a_record_without_a_frozen_date_refuses(env):
    assert run(env, PILOT) == 0
    doc = chain_json(env)
    doc.pop("frozen_prompt_date")
    (env["out"] / "chain.json").write_text(json.dumps(doc))
    with pytest.raises(R.RecordInvalid, match="frozen_prompt_date absent or malformed"):
        resume_chain(env)


def test_a_manifest_with_another_date_aborts_at_the_barrier(env):
    rc = run(env, PILOT, extra_env={"FAKE_MANIFEST_OVERRIDE": json.dumps({"runtime.frozen_prompt_date": OTHER})})
    assert rc == 2 and log_has(env, "frozen_prompt_date")


def test_fake_probe_parity_refuses_a_missing_or_malformed_date(tmp_path):
    base = [sys.executable, str(C147 / "fake_probe.py"), "--model", PICK1, "--items", "a", "--lang", "python",
            "--seed-base", "1", "--out", str(tmp_path / "o.jsonl"), "--scaffold", FP.SCAFFOLD, "--expect-items", "python/a",
            "--a4-v2-receipt", "r", "--sampling-profile", "deployed", "--cancel-file", str(tmp_path / "c"),
            "--manifest-ack", str(tmp_path / "k")]
    for extra in ([], ["--frozen-prompt-date", "2026-01-05"]):
        got = subprocess.run(base + extra, capture_output=True, text=True, timeout=30)
        assert got.returncode == 2 and "--frozen-prompt-date" in got.stdout


def leg_for(out, ids):
    return dict(session="s1", model=PICK1, lang="python", seed_base=1001, expected_ids=ids, out=str(out), rc=0)


def good_leg(tmp_path, frozen=EPOCH_DATE):
    out = tmp_path / "o.jsonl"
    worker = dict(pid=1, create_time=1.0, model_path="m", registry_sha256="a" * 64)
    FP.write_leg(out, PICK1, "python", 1001, ["python/a"], worker, tmp_path)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    man["runtime"]["frozen_prompt_date"] = frozen
    out.with_suffix(".manifest.json").write_text(json.dumps(man))
    rows = [json.loads(s) for s in out.read_text().splitlines()]
    for r in rows:
        r["prompt_date"] = frozen
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return out, rows


def pinned_for(out):
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    return {k: v for k, v in co.runtime_identity(man).items()}


def test_validate_leg_checks_the_manifest_and_every_row_against_the_frozen_date(tmp_path):
    out, rows = good_leg(tmp_path)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    pinned = {**pinned_for(out), "serving_path": man["git"]["serving_path"], "registry_sha256": man["registry"]["sha256"]}
    leg = leg_for(out, ["python/a"])
    kw = dict(workdir=str(tmp_path), policy_sha=man["runtime"]["scaffold_policy_sha256"])
    assert co.validate_leg(leg, pinned, frozen_prompt_date=EPOCH_DATE, **kw) == []
    assert any("runtime_frozen_prompt_date" in w for w in co.validate_leg(leg, pinned, frozen_prompt_date=OTHER, **kw))
    rows[0]["prompt_date"] = TODAY if TODAY != EPOCH_DATE else OTHER
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert any("row_prompt_date" in w for w in co.validate_leg(leg, pinned, frozen_prompt_date=EPOCH_DATE, **kw))
    rows[0]["prompt_date"] = EPOCH_DATE
    rows[0]["prompt_date_update_removed"] = "no"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert any("prompt_date_real" in w for w in co.validate_leg(leg, pinned, frozen_prompt_date=EPOCH_DATE, **kw))
