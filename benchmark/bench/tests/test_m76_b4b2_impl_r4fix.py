"""M76 B4b-2 fix round 4 (ledger `change-ledger-r3.md`, "After round 3"): one synthetic red test per real-record finding (T1, T2)
plus the controls that pin nothing else is loosened."""
from __future__ import annotations

import json

import pytest

from bench import p426_panel as P
from bench import p426_verify as V
from bench.tests.test_m76_b4b2_impl_panel import _Corpus, _export_world
from bench.tests.test_m76_b4b2_impl_r1fix import a8, by_session, world


# ------------------------------------------------------------------------------------------------ T1 probe_session
def _probe_session_hook(leader_x=True):
    def hook(arm, session, lang, man):
        man = json.loads(json.dumps(man))
        man["probe_session"] = dict(sid=1000 if arm == "n16" else 2000, leader=True if arm == "n16" else leader_x,
                                    started=1.5 if arm == "n16" else 9.5, run_dir=f"$STACK_WORKDIR/opencode-probe-v2/run-{arm}-{lang}")
        return man
    return hook


def test_t1_kv_normalise_drops_only_the_per_invocation_probe_session_keys():
    man = dict(probe_session=dict(sid=1, leader=True, started=2.0, run_dir="r", other="kept"), sampling=dict(temperature=0.6))
    got = V.kv_normalise(man)
    assert got["probe_session"] == dict(leader=True, other="kept") and got["sampling"] == dict(temperature=0.6)
    assert man["probe_session"]["run_dir"] == "r"                                       # the input is not mutated
    assert "probe_session" not in V.kv_normalise(dict(probe_session=dict(sid=1, started=2.0, run_dir="r")))


def test_t1_differing_probe_session_invocation_keys_are_not_provenance(tmp_path):
    rec = by_session(a8(world(tmp_path, manifest_hook=_probe_session_hook())))["pilot"]
    assert rec["accepted"], rec["reasons"]


def test_t1_a_differing_probe_session_leader_still_rejects(tmp_path):
    rec = by_session(a8(world(tmp_path, manifest_hook=_probe_session_hook(leader_x=False))))["pilot"]
    assert not rec["accepted"] and any("probe_session.leader" in r for r in rec["reasons"]), rec["reasons"]
    assert not any("probe_session.run_dir" in r or "probe_session.sid" in r or "probe_session.started" in r
                   for r in rec["reasons"]), rec["reasons"]


# ------------------------------------------------------------------------------------------------ T2 the escaped run argument
PROMPT = 'Implement the solution in src/lib.rs. It\'s fine to stop at "trillion". Helper modules may go under src/.'


def _check(tmp_path, monkeypatch, text, prompt=PROMPT):
    ctx, att, row = _export_world(tmp_path, monkeypatch, text)
    return P.a8_prompt_check(ctx, att, row, "rust/say", _Corpus(prompt), ("top", "ref"))


def test_t2_the_quoted_run_argument_with_escaped_embedded_quotes_is_the_runners_prompt(tmp_path, monkeypatch):
    got, _entry = _check(tmp_path, monkeypatch, '"' + PROMPT.replace('"', '\\"') + '"')
    assert got == PROMPT


@pytest.mark.parametrize("text", [
    '"' + PROMPT + '"',                                                        # quoted, embedded quotes NOT escaped
    '"' + PROMPT.replace('"', '\\"') + '" ',                                   # trailing whitespace
    '"' + PROMPT.replace('"', '\\"').replace("Implement", "implement") + '"',  # case differs
    '"' + PROMPT.replace('"', '\\"').replace(". ", ".  ", 1) + '"',            # whitespace differs inside
    PROMPT.replace('"', '\\"'),                                                # escaped but not enclosed
    '"' + PROMPT.replace('"', '\\"'),                                          # opening quote only
], ids=["unescaped", "trailing-ws", "case", "inner-ws", "unenclosed", "open-only"])
def test_t2_any_other_form_of_a_prompt_with_embedded_quotes_refuses(tmp_path, monkeypatch, text):
    with pytest.raises(V.RefusalError, match="first user message"):
        _check(tmp_path, monkeypatch, text)


def test_t2_a_prompt_without_quotes_keeps_the_exact_and_the_quoted_forms(tmp_path, monkeypatch):
    plain = "Implement the solution in src/lib.rs so that the tests pass."
    for text in (plain, f'"{plain}"'):
        assert _check(tmp_path, monkeypatch, text, prompt=plain)[0] == plain
