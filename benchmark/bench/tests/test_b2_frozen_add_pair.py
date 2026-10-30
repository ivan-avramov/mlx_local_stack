"""P426 B2 frozen tests, delivery 1d (amended 1f for C238 / [d2]): the pair gate inside the chain (spec §6.4-6.5, §16.5
`--pair-receipt`).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour (all NEW here).
Two hermetic legs (`b2_frozen_add_support.world`: the frozen P426 world + the §16.5 seams, one box's environment): the OFF leg
writes `receipt.json`; the ON leg gets `--pair-receipt <it>` and compares at its after-load checkpoint, before item one.
C238: no pair key — credential KEYS are compared per process, never values or hashes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S


def run_leg(tmp_path, monkeypatch, arm, *, extra=(), adjust=None, mode=("pilot",), rehearsal=False):
    env = A.world(tmp_path, monkeypatch, arm=arm, rehearsal=rehearsal)
    if adjust:
        adjust(env)
    argv, r = A.pair_argv(env, mode, extra=extra)
    try:
        rc = S.run_p426(env, argv, rfd=r)
    finally:
        env["ops"].cancel()
    return rc, env


def first_receipt(tmp_path, monkeypatch):
    rc, env = run_leg(tmp_path / "off", monkeypatch, "off")
    assert rc == 0, "\n".join(env["lines"][-20:])
    return Path(env["out"]) / "receipt.json"


def no_item_started(env):
    return not list(Path(env["out"]).rglob("*.item0.go"))


def test_new_the_second_leg_of_a_pair_passes_the_gate_and_runs(tmp_path, monkeypatch):
    rec = first_receipt(tmp_path, monkeypatch)
    rc, env = run_leg(tmp_path / "on", monkeypatch, "on", extra=["--pair-receipt", str(rec)])
    assert rc == 0, "\n".join(env["lines"][-20:])
    assert len(list(Path(env["out"]).rglob("items/*.ready.json"))) == 5


def test_new_a_credential_key_in_one_process_of_one_leg_only_refuses_before_item_one(tmp_path, monkeypatch):
    """[d2] §6.5: a credential key present in one process of one leg only is a difference -> systemic."""
    rec = first_receipt(tmp_path, monkeypatch)

    def extra_key(env):
        base = env["ops"].proc_environ
        env["ops"].proc_environ = lambda pid: dict(base(pid), OPENAI_API_KEY="Y" * 30) if pid == 1 else base(pid)
    rc, env = run_leg(tmp_path / "on", monkeypatch, "on", extra=["--pair-receipt", str(rec)], adjust=extra_key)
    assert rc == 2 and env["ops"].names("load") and no_item_started(env)
    assert "Y" * 30 not in S.all_output_text(env["out"])


def test_new_the_same_credential_keys_with_other_values_pass_the_gate(tmp_path, monkeypatch):
    """C238: values are never compared (nor recorded): a rotated token with the same key set is not a difference."""
    rec = first_receipt(tmp_path, monkeypatch)

    def rotated(env):
        base = env["ops"].proc_environ
        env["ops"].proc_environ = lambda pid: dict(base(pid), HF_TOKEN="R" * 40)
    rc, env = run_leg(tmp_path / "on", monkeypatch, "on", extra=["--pair-receipt", str(rec)], adjust=rotated)
    assert rc == 0, "\n".join(env["lines"][-20:])


def test_new_an_environment_difference_refuses_before_item_one(tmp_path, monkeypatch):
    rec = first_receipt(tmp_path, monkeypatch)

    def extra_var(env):
        base = env["ops"].proc_environ
        env["ops"].proc_environ = lambda pid: dict(base(pid), MLX_VLM_CACHE_SESSION_MAX="2")
    rc, env = run_leg(tmp_path / "on", monkeypatch, "on", extra=["--pair-receipt", str(rec)], adjust=extra_var)
    assert rc == 2 and env["ops"].names("load") and no_item_started(env)


def test_new_a_loaded_library_difference_refuses_before_item_one(tmp_path, monkeypatch):
    rec = first_receipt(tmp_path, monkeypatch)

    def other_lib(env):                             # 1i: both §6.4 libraries loaded; only libmlx.dylib's bytes differ
        imgs = S.LOADED_IMAGES(env["wt"])
        imgs[0] = dict(imgs[0], sha256="0" * 64)
        env["ops"].loaded_images = lambda pid: imgs
    rc, env = run_leg(tmp_path / "on", monkeypatch, "on", extra=["--pair-receipt", str(rec)], adjust=other_lib)
    assert rc == 2 and env["ops"].names("load") and no_item_started(env)


SEAMS = ["proc_argv", "proc_environ", "interpreter_inventory", "loaded_images", "snapshot_hashes", "expected_worker_argv",
         "busy_procs", "descendants", "create_time"]


@pytest.mark.parametrize("seam", SEAMS)
def test_new_a_missing_check_seam_is_systemic_never_a_skip(tmp_path, monkeypatch, seam):
    """§16.7 (1i): in P426 mode a ChainOps seam the checks need that is missing is systemic, never a skip — the leg exits 2,
    no item starts, and a line names the seam. The seams are §16.2's ChainOps list plus §16.5 / §16.6's (identities by
    `create_time(pid)`)."""
    def remove(env):
        ops = env["ops"]
        if seam in vars(ops):
            monkeypatch.delattr(ops, seam)
        for klass in type(ops).__mro__:
            if seam in vars(klass):
                monkeypatch.delattr(klass, seam)
        assert not hasattr(ops, seam)
    rc, env = run_leg(tmp_path, monkeypatch, "off", adjust=remove)
    assert rc == 2 and no_item_started(env), "\n".join(env["lines"][-20:])
    assert any(seam in ln for ln in env["lines"]), env["lines"][-20:]


def test_new_a_missing_pair_receipt_refuses(tmp_path, monkeypatch):
    rc, env = run_leg(tmp_path / "on", monkeypatch, "on", extra=["--pair-receipt", str(tmp_path / "nope/receipt.json")])
    assert rc == 2 and no_item_started(env)
    assert any("REFUSED: " in ln for ln in env["lines"])


def test_new_a_rehearsal_leg_records_credential_keys_per_process_and_no_value(tmp_path, monkeypatch):
    """C238 (replaces the 1e `--hmac-fd` rehearsal test): R1 is a pair like any other; its receipt carries keys only."""
    rc, env = run_leg(tmp_path, monkeypatch, "off", mode=("chain", "s1", "--rehearsal"), rehearsal=True)
    assert rc == 0, "\n".join(env["lines"][-20:])
    rec = json.loads((Path(env["out"]) / "receipt.json").read_text())
    assert "credentials" not in rec and all("HF_TOKEN" in rec["credential_keys"][w] for w in ("router", "worker", "probe"))
    assert all("HF_TOKEN" not in rec["env"][w] for w in ("router", "worker", "probe"))          # §16.7: absent from env
    assert S.FAKE_SECRET_40 not in json.dumps(rec) and "/p426/rehearsal/" in str(env["out"])
