"""B2 fix round 4 (the strict change review, round 2; spec 16.8 "after the strict verify round 2"): one failing-first test per item.
Hermetic: every tree is under `tmp_path`, every credential is a fake; no router, worker, model, network or GPU."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from bench import p426_freeze as fz
from bench import p426_harvest as H
from bench import p426_hooks as ph
from bench import p426_secrets as ps
from bench import p426_wave2 as w2
from bench.tests import test_b2_s8_wave2 as T8
from bench.tests import test_b2_s9_harvest as T9

FAKE = "Zk3" + "x7Pq" * 9 + "W"                                    # a fake 40-char opaque credential value
OPERATOR = "op.erator@corp-mail.example"
world = T8.world                                                    # the sequencer fixture (fake ops, fake clock)


def put_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return path


def nothing_published(main):
    assert not (main / H.WAVE2).exists() or not any(p.is_file() for p in (main / H.WAVE2).rglob("*"))


# ------------------------------------------------------------------------------------------------ 5. `$` and backtick in a credential value
@pytest.mark.parametrize("value", ["abc$HOME1234567890", 'abc"$HOME"1234567890', "abc`id`1234567890", "${HOME}abcdef1234567890",
                                   '"abc`id`1234567890"'])
def test_5_a_credential_keyed_value_with_an_unquoted_dollar_or_backtick_refuses(value):
    with pytest.raises(ps.SecretsError) as exc:
        ps.parse_assignments(f"MY_API_KEY={value}\n")
    assert "MY_API_KEY" in str(exc.value) and value not in str(exc.value) and "abc" not in str(exc.value)


@pytest.mark.parametrize("value, expected", [("'abc$HOME1234567890'", "abc$HOME1234567890"), ("'abc`id`1234567890'", "abc`id`1234567890"),
                                             (r"abc\$HOME1234567890", "abc$HOME1234567890"), ("abcdef1234567890", "abcdef1234567890")])
def test_5_single_quoted_or_escaped_or_plain_values_are_taken_literally(value, expected):
    assert ps.parse_assignments(f"MY_API_KEY={value}\n")["MY_API_KEY"] == expected


def test_5_a_non_credential_key_with_a_dollar_is_not_refused():
    assert ps.parse_assignments("PLAIN=$HOME\nOTHER=`id`\n") == {"PLAIN": "$HOME", "OTHER": "`id`"}


# ------------------------------------------------------------------------------------------------ 1. publication uses the credential values
def secret_record(tmp_path, name="sequence.json"):
    return put_json(tmp_path / "run" / name, {"rerun_reason": f"because {FAKE} was pasted", "legs": []})


def scrub_for(tmp_path, secrets=None):
    return dataclasses.replace(T9.scrub_for(tmp_path, emails=(OPERATOR,)), secrets=dict(secrets or {}))


def test_1_run_file_publication_refuses_a_configured_secret_value_and_publishes_nothing(tmp_path):
    seq = secret_record(tmp_path)
    main = tmp_path / "main"
    with pytest.raises(H.HarvestError) as exc:
        H.publish_run_files([seq], main_root=main, scrub=scrub_for(tmp_path, {"config:MY_API_KEY": FAKE}))
    assert FAKE not in str(exc.value) and "exact" in str(exc.value)
    nothing_published(main)


def test_1_dossier_publication_refuses_a_configured_secret_value_and_publishes_nothing(tmp_path):
    doc = ph.seal({"pair": "pilot", "note": f"x {FAKE} y"})
    path = put_json(tmp_path / "pairs" / "pilot__off-a1__on-a1.json", doc)
    main = tmp_path / "main"
    with pytest.raises(H.HarvestError) as exc:
        H.publish_dossier(path, main_root=main, evidence_stage=tmp_path / "stage",
                          scrub=scrub_for(tmp_path, {"config:MY_API_KEY": FAKE}))
    assert FAKE not in str(exc.value)
    nothing_published(main)


def test_1_publication_without_values_keeps_its_behaviour(tmp_path):
    seq = secret_record(tmp_path)
    assert H.publish_run_files([seq], main_root=tmp_path / "main", scrub=scrub_for(tmp_path))["published"]


def test_1_the_box_ops_pass_the_same_credential_values_to_both_publications(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config" / "mlx_local_stack").mkdir(parents=True)
    (home / ".config" / "mlx_local_stack" / "config.sh").write_text(f"export MY_API_KEY={FAKE}\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    seq = secret_record(tmp_path)
    with pytest.raises(H.HarvestError):
        ops.publish_run_files([seq], emails=(OPERATOR,))
    doc = ph.seal({"pair": "pilot", "note": FAKE})
    dossier = put_json(tmp_path / "pairs" / "pilot__off-a1__on-a1.json", doc)
    with pytest.raises(H.HarvestError):
        ops.publish_dossier(dossier, emails=(OPERATOR,))
    nothing_published(tmp_path / "main")


def test_1_an_unreadable_credential_source_is_a_refusal_not_an_unscanned_publication(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config" / "mlx_local_stack").mkdir(parents=True)
    (home / ".config" / "mlx_local_stack" / "config.sh").write_text('export MY_API_KEY="unterminated\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    with pytest.raises(H.HarvestError):
        ops.publish_run_files([put_json(tmp_path / "run" / "sequence.json", {"legs": []})], emails=(OPERATOR,))


# ------------------------------------------------------------------------------------------------ 2. immutable run files need a self-hash
@pytest.mark.parametrize("name", ["v8_base.json", "amendment.json", "manifest.json", "pilot__off-a1__on-a1.json"])
def test_2_an_immutable_run_file_without_a_valid_self_hash_is_refused(tmp_path, name):
    main = tmp_path / "main"
    bare = put_json(tmp_path / "run" / name, {"kind": "x", "n": 1})                       # no sha256 at all
    with pytest.raises(H.HarvestError, match="self-hash|sha256"):
        H.publish_run_files([bare], main_root=main, scrub=scrub_for(tmp_path))
    wrong = put_json(tmp_path / "run2" / name, dict(ph.seal({"kind": "x", "n": 1}), n=2))   # a stale hash
    with pytest.raises(H.HarvestError, match="self-hash|sha256"):
        H.publish_run_files([wrong], main_root=main, scrub=scrub_for(tmp_path))
    nothing_published(main)


def reseal_amendment(world, **changes):
    path = world.rec / "amendment.json"
    doc = json.loads(path.read_text())
    doc = {k: v for k, v in doc.items() if k != "sha256" and k not in changes}
    doc.update({k: v for k, v in changes.items() if v is not None})
    path.write_text(json.dumps(ph.seal(doc)))


def after_the_pilots(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    world.ops.events.clear()
    world.ops.launches.clear()
    world.clock.t += 3600


# ------------------------------------------------------------------------------------------------ 3. every consumer re-verifies the amendment
@pytest.mark.parametrize("changes", [dict(pilot_dossier_sha256="0" * 64), dict(pilot_dossier_sha256=None), dict(kind="p426_v8_base")],
                         ids=["other-dossier", "no-dossier", "wrong-kind"])
def test_3_makeup_re_verifies_an_existing_amendment_before_any_leg(world, changes):
    after_the_pilots(world)
    reseal_amendment(world, **changes)
    f = T8.write_occurrences(world.wd / "occ.jsonl", T8.MK)
    rc = T8.go(world, "--occurrences", str(f), cmd="makeup")
    assert rc in (1, 2) and not world.ops.names()
    assert rc == 2 or "amendment" in (world.out / "sequence.log").read_text().splitlines()[-1]


def test_3_run_re_verifies_an_existing_amendment_before_the_session_legs(world):
    after_the_pilots(world)
    reseal_amendment(world, pilot_dossier_sha256="0" * 64)
    assert T8.go(world) == 1
    assert not world.ops.names() and "pilot_dossier_sha256" in (world.out / "sequence.log").read_text().splitlines()[-1]


def test_3_an_amendment_naming_the_selected_pass_dossier_is_used(world):
    after_the_pilots(world)
    assert T8.go(world) == 0 and world.ops.names()


# ------------------------------------------------------------------------------------------------ 4. dossier publication order and resume
def seq_doc(world):
    return json.loads(world.seq.read_text())


def test_4_a_dossier_is_published_before_the_pair_record_is_saved_and_a_failure_is_exit_4(world):
    def boom(path, *, emails):
        raise OSError("disk full")
    world.ops.publish_dossier = boom
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 4
    assert seq_doc(world)["pairs"] == []                                  # no pair record without a published dossier
    assert "dossier" in (world.out / "sequence.log").read_text().splitlines()[-1]
    assert not (world.rec / "amendment.json").exists()                    # nothing consumed the unpublished pair


def test_4_after_a_failed_publication_the_resume_publishes_and_then_records_the_pair(world):
    real = world.ops.publish_dossier
    state = {"fail": True}

    def flaky(path, *, emails):
        if state["fail"]:
            raise OSError("disk full")
        return real(path, emails=emails)
    world.ops.publish_dossier = flaky
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 4
    state["fail"] = False
    world.ops.published_dossiers.clear()
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    (pair,) = seq_doc(world)["pairs"]
    assert pair["pair"] == "pilot" and pair["published"] is True
    assert [p.name for p in world.ops.published_dossiers] == [Path(pair["dossier"]).name]


def test_4_a_recorded_dossier_not_yet_published_is_republished_on_resume_idempotently(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    doc = seq_doc(world)
    for rec in doc["pairs"]:
        rec.pop("published")                                              # a record from before the order was fixed
    world.seq.write_text(json.dumps(doc))
    world.ops.published_dossiers.clear()
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    assert len(world.ops.published_dossiers) == 1 and all(p["published"] is True for p in seq_doc(world)["pairs"])
    world.ops.published_dossiers.clear()
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    assert world.ops.published_dossiers == []                             # published records are not published again


def test_4_a_failing_republication_on_resume_is_exit_4(world):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    doc = seq_doc(world)
    for rec in doc["pairs"]:
        rec.pop("published")
    world.seq.write_text(json.dumps(doc))

    def boom(path, *, emails):
        raise OSError("disk full")
    world.ops.publish_dossier = boom
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 4


def test_2_a_sealed_run_file_and_the_state_file_publish(tmp_path):
    main = tmp_path / "main"
    ok = put_json(tmp_path / "run" / "v8_base.json", ph.seal({"kind": "p426_v8_base"}))
    seq = put_json(tmp_path / "run" / "sequence.json", {"legs": [], "previous_sha256": None})    # the state file is exempt
    got = H.publish_run_files([ok, seq], main_root=main, scrub=scrub_for(tmp_path))
    assert sorted(Path(p["destination"]).name for p in got["published"]) == ["sequence.json", "v8_base.json"]
