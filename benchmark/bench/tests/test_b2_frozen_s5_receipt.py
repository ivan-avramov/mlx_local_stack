"""P426 B2 frozen tests, s5 receipt (spec v3.2 §6.4-6.5, §11.3 classifier, §16.2 `bench.p426_receipt` / `bench.p426_secrets`).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
Unit level: the classifier and scans (`is_credential_key`, `credential_values`, `scan`, `exact_hits`), the pair gate
(`pair_problems`) on receipts in the §16.1 shape, and `write_dossier`. Every secret is a fake; no test prints one."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from bench.tests import b2_frozen_support as S


def SEC():
    from bench import p426_secrets
    return p426_secrets


def REC():
    from bench import p426_receipt
    return p426_receipt


# ------------------------------------------------------------------------------------------------ the classifier (§11.3)
@pytest.mark.parametrize("name", ["HF_TOKEN", "hf_token", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "OWUI_ADMIN_PASSWORD",
                                  "GH_CREDENTIALS", "PROXY_AUTH", "MY_Api_Key"])
def test_new_credential_key_names_are_classified(name):
    assert SEC().is_credential_key(name) is True


@pytest.mark.parametrize("name", ["TOKENIZERS_PARALLELISM", "PATH", "HOME", "STACK_WORKDIR", "MLX_VLM_CACHE_SESSION_MAX"])
def test_new_the_allowlist_and_ordinary_keys_are_not_credentials(name):
    assert SEC().is_credential_key(name) is False


# post-reveal 3h (§16.8 after the strict verify round 1): `KV_*` / `TQ_*` names are non-secret only by an exact allowlist
@pytest.mark.parametrize("name", ["KV_API_KEY", "TQ_TOKEN", "KV_SECRET", "TQ_AUTH_HEADER", "KV_PASSWORD"])
def test_new_a_kv_or_tq_name_off_the_exact_allowlist_is_a_credential(name):
    assert SEC().is_credential_key(name) is True


def test_new_a_stack_defined_kv_name_is_on_the_exact_allowlist():
    assert SEC().is_credential_key("KV_KEY_BITS") is False          # defined by the fork's server (`runtime_config.py`)


def test_new_config_assignments_are_parsed_shell_style(tmp_path):
    """post-reveal 3h (§16.8): shell-style parsing — quotes removed, a trailing `# comment` dropped."""
    home = tmp_path / "home"
    home.mkdir()
    cfg = home / "config.sh"
    a, b, c = "F" * 40, "G" * 40, "H" * 40
    cfg.write_text(f"export HF_TOKEN='{a}'  # the hub token\nOPENAI_API_KEY=\"{b}\"\nexport GH_TOKEN={c} # gh\n")
    values = set(SEC().credential_values(home=home, config_path=cfg, environ={}).values())   # keys are the candidate's labels
    assert {a, b, c} <= values
    assert not any("#" in v or "'" in v or '"' in v for v in values)


def test_new_an_unparseable_credential_keyed_config_line_refuses_naming_the_key_never_the_value(tmp_path):
    """post-reveal 3h (§16.8): an unparseable credential-keyed line refuses."""
    home = tmp_path / "home"
    home.mkdir()
    cfg = home / "config.sh"
    value = "J" * 40
    cfg.write_text(f"export HF_TOKEN='{value}\n")                  # an unterminated quote
    with pytest.raises(SEC().SecretsError) as e:
        SEC().credential_values(home=home, config_path=cfg, environ={})
    assert "HF_TOKEN" in str(e.value) and value not in str(e.value)


@pytest.mark.parametrize("line", ["export HF_TOKEN=K{v}$SUFFIX", "export HF_TOKEN=K{v}`id`"], ids=["dollar", "backtick"])
def test_new_a_credential_value_with_an_unquoted_dollar_or_backtick_refuses(tmp_path, line):
    """post-reveal 3i (§16.8 after the strict verify round 2): a credential-keyed config value containing an unquoted `$` or a
    backtick refuses (`SecretsError`: it cannot be matched exactly), naming the key, never the value."""
    home = tmp_path / "home"
    home.mkdir()
    cfg = home / "config.sh"
    value = "L" * 30
    cfg.write_text(line.format(v=value) + "\n")
    with pytest.raises(SEC().SecretsError) as e:
        SEC().credential_values(home=home, config_path=cfg, environ={})
    assert "HF_TOKEN" in str(e.value) and value not in str(e.value)


def test_new_a_single_quoted_dollar_in_a_credential_value_is_literal(tmp_path):
    """The contrast: inside single quotes `$` is literal shell text, so the value is exact and used."""
    home = tmp_path / "home"
    home.mkdir()
    cfg = home / "config.sh"
    value = "M" * 30 + "$x"
    cfg.write_text(f"export HF_TOKEN='{value}'\n")
    assert value in set(SEC().credential_values(home=home, config_path=cfg, environ={}).values())


@pytest.mark.parametrize("text", ['{"Authorization": "Bearer ' + "q" * 32 + '"}', "'Authorization': 'Bearer " + "q" * 32 + "'"],
                         ids=["json", "quoted"])
def test_new_the_bearer_format_matches_the_quoted_and_json_header_forms(text):
    """post-reveal 3h (§16.8): the bearer format also matches the quoted / JSON header form."""
    found = SEC().scan(text)
    assert found and "q" * 32 not in repr(found)


def test_new_credential_values_come_from_the_token_files_the_machine_config_and_the_environment(tmp_path):
    home = tmp_path / "home"
    (home / ".cache/huggingface").mkdir(parents=True)
    (home / ".hftoken").write_text("A" * 40)
    (home / ".cache/huggingface/token").write_text("B" * 40)
    cfg = home / ".config/mlx_local_stack/config.sh"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('export STACK_WORKDIR="/x"\nexport HF_TOKEN="' + "C" * 40 + '"\nexport TOKENIZERS_PARALLELISM=false\n')
    environ = {"P426_TEST_API_KEY": "D" * 40, "SOME_KEY": "1", "TOKENIZERS_PARALLELISM": "false", "PATH": "/usr/bin",
               "SHORT_TOKEN": "abc", "PLACEHOLDER_SECRET": "changeme"}
    values = set(SEC().credential_values(home=home, config_path=cfg, environ=environ).values())
    assert {"A" * 40, "B" * 40, "C" * 40, "D" * 40} <= values
    assert not values & {"1", "false", "abc", "changeme", "/usr/bin", "/x"}       # placeholders, < 12 chars, non-keys


def test_new_absent_secret_files_are_not_an_error(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert SEC().credential_values(home=home, config_path=home / ".config/none/config.sh", environ={}) == {}


def test_new_a_listed_secret_file_that_exists_but_cannot_be_read_refuses(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    tok = home / ".hftoken"
    tok.write_text("E" * 40)
    sec = SEC()                                                   # the module must exist (not an ImportError 'refusal')
    os.chmod(tok, 0)
    try:
        with pytest.raises(Exception) as e:
            sec.credential_values(home=home, config_path=home / "none.sh", environ={})
    finally:
        os.chmod(tok, 0o600)
    assert "E" * 40 not in str(e.value)


@pytest.mark.parametrize("value", [S.FAKE_HF_TOKEN_FILE, "sk-" + "s" * 40, "ghp_" + "R" * 36, "github_pat_" + "P" * 60,
                                   "AKIA" + "Z" * 16, "-----BEGIN " + "RSA PRIVATE KEY-----",
                                   "Authorization: Bearer " + "b" * 32],
                         ids=["hf", "sk", "ghp", "github_pat", "akia", "pem", "bearer"])
def test_new_scan_finds_each_credential_format_and_never_carries_the_value(value):
    text = '{"messages": [{"text": "here: ' + value + ' end"}]}'
    found = SEC().scan(text)
    assert found and any(f.start <= text.index(value) < f.end or text.index(value) <= f.start < text.index(value) + len(value)
                         for f in found)
    assert value not in repr(found) and all(value not in str(f) for f in found)


def test_new_tokenizers_parallelism_false_and_a_one_valued_key_never_match():
    text = "TOKENIZERS_PARALLELISM=false\nSOME_KEY=1\nreasoning about tokens and keys"
    assert SEC().scan(text) == []
    assert SEC().exact_hits(text, {"SOME_KEY": "1", "TOKENIZERS_PARALLELISM": "false"}) == []


def test_new_exact_hits_find_a_40_character_token_and_never_carry_it():
    text = "the model wrote " + S.FAKE_SECRET_40 + " into the transcript"
    hits = SEC().exact_hits(text, {"HF_TOKEN": S.FAKE_SECRET_40})
    assert len(hits) == 1 and text[hits[0].start:hits[0].end] == S.FAKE_SECRET_40
    assert S.FAKE_SECRET_40 not in repr(hits)


# ------------------------------------------------------------------------------------------------ the pair gate (§6.5)
def pair(off_over=None, on_over=None):
    return S.arm_receipt_doc("off", **(off_over or {})), S.arm_receipt_doc("on", **(on_over or {}))


def _mutate(receipt, path, value):
    """A copy of the self-hashed receipt with `path` set to `value`, RE-SEALED (1i): a receipt is an immutable self-hashed
    record (§16), so the gate may verify its seal; the difference under test must be the only thing wrong."""
    r = copy.deepcopy(receipt)
    node = r
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return S.self_hashed(r)


def problems_naming(off, on, name):
    """The pair problems, asserting one names `name` (a field / key); both receipts verify their seals, so the difference
    under test is the only thing wrong with the pair."""
    assert all(S.self_hashed(r)["sha256"] == r["sha256"] for r in (off, on))
    probs = REC().pair_problems(off, on)
    assert probs, f"no problem for a difference in {name}"
    assert any(name in p for p in probs), (name, probs)
    return probs


def test_new_an_on_off_pair_differing_only_in_the_allowed_items_passes():
    off, on = pair()
    assert REC().pair_problems(off, on) == []


@pytest.mark.parametrize("key", ["_", "OLDPWD", "PWD", "SHLVL", "TERM_SESSION_ID", "SECURITYSESSIONID", "__CF_USER_TEXT_ENCODING"])
def test_new_volatile_keys_never_count_as_a_difference(key):
    """§6.4's closed volatile list (a module constant, §16.7): a volatile key present in one leg only is no difference."""
    off, on = pair()
    on = _mutate(on, ("env", "worker", key), "<volatile>")
    assert REC().pair_problems(off, on) == []


def test_new_a_problem_names_the_differing_process_and_field():
    off, on = pair()
    on = _mutate(on, ("env", "worker", "MLX_VLM_CACHE_SESSION_MAX"), "2")
    probs = problems_naming(off, on, "MLX_VLM_CACHE_SESSION_MAX")
    assert any("worker" in p and "MLX_VLM_CACHE_SESSION_MAX" in p for p in probs)
    assert not any("'2'" in p or "=2" in p for p in probs)                 # names the key, never echoes the value


def _tamper_seal(doc):
    doc = copy.deepcopy(doc)
    doc["sha256"] = "0" * 64                                               # the content unchanged, its seal wrong
    return doc


def _tamper_volatile(doc):
    doc = copy.deepcopy(doc)
    doc["env"]["worker"]["PWD"] = "/somewhere/else"                        # a volatile key's value: no pair difference
    return doc


@pytest.mark.parametrize("tamper", [_tamper_seal, _tamper_volatile], ids=["seal-replaced", "edited-not-resealed"])
@pytest.mark.parametrize("side", ["first", "second"])
def test_new_a_receipt_whose_seal_does_not_verify_is_a_problem(tamper, side):
    """§16: the receipt is an immutable self-hashed record; a tampered copy never passes the gate. 2d: the tamper really
    breaks the seal (asserted) and adds no pair difference, so the seal is the only thing wrong."""
    off, on = pair()
    assert REC().pair_problems(off, on) == []                              # the untampered pair passes
    if side == "first":
        off = tamper(off)
        bad = off
    else:
        on = tamper(on)
        bad = on
    assert S.self_hashed(bad)["sha256"] != bad["sha256"]                    # the seal does not verify
    assert REC().pair_problems(off, on)


def _other_images():
    imgs = S.LOADED_IMAGES("<WT>")
    imgs[0] = dict(imgs[0], sha256="0" * 64)                          # libmlx.dylib with other bytes; mlx.metallib unchanged
    return imgs


@pytest.mark.parametrize("path,value,name", [
    (("env", "worker", "MLX_VLM_CACHE_SESSION_MAX"), "2", "MLX_VLM_CACHE_SESSION_MAX"),
    (("env", "probe", "EXTRA_FLAG"), "1", "EXTRA_FLAG"),
    (("argv", "router"), ["<WT>/.venv/bin/mlx-serve", "start", "--debug"], "argv.router"),
    (("argv", "worker"), ["<WT>/.venv/bin/python", "-m", "mlx_vlm.server", "--model", S.HF, "--port", "8092"], "argv.worker"),
    (("credential_keys", "worker"), ["HF_TOKEN", "OPENAI_API_KEY"], "OPENAI_API_KEY"),   # [d2] a key in one process of one leg
    (("loaded_images",), _other_images(), "loaded_images"),
    (("probe_entry",), "<WT>/benchmark/run_tg1_probe_alt.py", "probe_entry"),
    (("snapshots", "target"), lambda: dict(S.pinned_snapshots("off")["target"], revision="f" * 40), "snapshots.target"),
], ids=["env-worker", "env-probe", "argv-router", "argv-worker", "credential-key", "loaded-images", "probe-entry",
        "snapshot-target"])
def test_fix_any_other_difference_between_the_arms_refuses(path, value, name):
    """§6.5 / §16.7: every difference outside the closed list is a problem naming its field (the dotted receipt path, or the
    key for `env` / `credential_keys`); both receipts stay sealed, so the difference is the only thing wrong."""
    value = value() if callable(value) else value              # 2e: a value built from the pins is read at run time
    off, on = pair()
    if path == ("argv", "worker"):
        off = _mutate(off, path, value)
    else:
        on = _mutate(on, path, value)
    problems_naming(off, on, name)


def test_fix_an_interpreter_inventory_difference_refuses():
    off, on = pair()
    on = _mutate(on, ("interpreters", 0, "inventory_sha256"), "5" * 64)
    problems_naming(off, on, "interpreters")


def test_fix_an_env_difference_outside_the_closed_list_refuses():
    """[d2] §6.5: the allowed list is closed in the specification; an environment difference outside it is never allowed."""
    off, on = pair()
    on = _mutate(on, ("env", "worker", "PYTHONHASHSEED"), "0")
    problems_naming(off, on, "PYTHONHASHSEED")


def test_new_a_credential_key_missing_from_one_process_of_one_leg_refuses_naming_the_key():
    """[d2] C238: credential keys are compared per process; a key present in one process of one leg only is systemic."""
    off, on = pair()
    on = _mutate(on, ("credential_keys", "probe"), [])
    problems_naming(off, on, "HF_TOKEN")


# ------------------------------------------------------------------------------------------------ the dossier (§6.5)
def _two_receipts(tmp_path):
    off, on = pair()
    a = S.write_record(tmp_path / "off.a1" / "receipt.json", off)
    b = S.write_record(tmp_path / "on.a1" / "receipt.json", on)
    ha = S.write_record(tmp_path / "off.a1" / "HARVEST.json", S.self_hashed({"leg": "tg1-p426-off-pilot", "attempt": 1}))
    hb = S.write_record(tmp_path / "on.a1" / "HARVEST.json", S.self_hashed({"leg": "tg1-p426-on-pilot", "attempt": 1}))
    return [a, b], [ha, hb]


def differences():
    """2e: built at call time (the pins are read when a test runs, never at import)."""
    return [{"process": "worker", "field": "argv.worker", "off": None, "on": "--draft-kind mtp"},     # §16.7: dotted path
            {"process": "-", "field": "snapshots.drafter", "off": None, "on": S.pinned_snapshots("on")["drafter"]["revision"]}]


def arms(receipts, harvests, off_attempt="tg1-p426-off-pilot.a1", on_attempt="tg1-p426-on-pilot.a2"):
    """§16.7: `off` / `on` = `{attempt, receipt, harvest}` (`attempt` the attempt name `<leg>.a<n>`)."""
    return dict(off={"attempt": off_attempt, "receipt": receipts[0], "harvest": harvests[0]},
                on={"attempt": on_attempt, "receipt": receipts[1], "harvest": harvests[1]})


def test_new_the_pair_dossier_is_self_hashed_and_keyed_by_arm(tmp_path):
    """[d2] §16.1 / §16.7: `write_dossier(path, *, pair, off, on, differences, verdict)` writes `{pair, arms: {off: {attempt,
    receipt_sha256, harvest_sha256}, on: {…}}, differences, verdict, at, sha256}`, one per pair attempt."""
    receipts, harvests = _two_receipts(tmp_path)
    path = tmp_path / "pairs" / "pilot__off-a1__on-a2.json"
    doc = REC().write_dossier(path, pair="pilot", **arms(receipts, harvests), differences=differences(), verdict="PASS")
    on_disk = json.loads(path.read_text())
    assert on_disk == doc and S.self_hashed(on_disk)["sha256"] == on_disk["sha256"]
    assert on_disk["pair"] == "pilot" and on_disk["verdict"] == "PASS" and on_disk["differences"] == differences()
    assert on_disk["at"]
    assert on_disk["arms"] == {
        "off": {"attempt": "tg1-p426-off-pilot.a1", "receipt_sha256": S.sha256_file(receipts[0]),
                "harvest_sha256": S.sha256_file(harvests[0])},
        "on": {"attempt": "tg1-p426-on-pilot.a2", "receipt_sha256": S.sha256_file(receipts[1]),
               "harvest_sha256": S.sha256_file(harvests[1])}}


def test_new_the_pair_dossier_is_immutable(tmp_path):
    receipts, harvests = _two_receipts(tmp_path)
    path = tmp_path / "pairs" / "pilot__off-a1__on-a1.json"
    kw = dict(pair="pilot", **arms(receipts, harvests, on_attempt="tg1-p426-on-pilot.a1"), differences=[], verdict="PASS")
    REC().write_dossier(path, **kw)
    before = path.read_bytes()
    with pytest.raises(Exception):
        REC().write_dossier(path, **dict(kw, verdict="FAIL"))
    assert path.read_bytes() == before


# ------------------------------------------------------------------------------------------------ the receipt (§6.4, §16.4)
def receipt(tmp_path, monkeypatch, arm="off", environ=None):
    """`arm_receipt(ops, *, worktree, out_root, pids)` (C238: no key) over the FakeOps seams `proc_argv` / `proc_environ` /
    `interpreter_inventory` / `loaded_images` / `snapshot_hashes` (b2_frozen_support.p426_world)."""
    env = S.p426_world(tmp_path, monkeypatch, arm=arm)
    ops = env["ops"]
    ident = ops.load(S.MODEL)
    if environ is not None:
        ops.proc_environ = lambda pid: dict(environ)
    pids = {"router": 1, "worker": ident["pid"], "probe": 4242}
    try:
        doc = REC().arm_receipt(ops, worktree=env["wt"], out_root=env["out"], pids=pids)
    finally:
        ops.cancel()
    return doc, env, None


def test_new_the_receipt_canonicalizes_the_roots_and_records_the_mlx_serve_worker_argv(tmp_path, monkeypatch):
    doc, env, _ = receipt(tmp_path, monkeypatch, arm="on")
    text = json.dumps(doc)
    assert str(env["wt"]) not in text and "<WT>" in text
    assert doc["env"]["worker"]["MLX_SERVE_CONFIG"] == "<WT>/main_models.yaml"
    worker = doc["argv"]["worker"]
    assert "--draft-kind" in worker and worker[worker.index("--draft-model") + 1] == S.DRAFTER
    assert doc["snapshots"]["drafter"] and doc["snapshots"]["target"]
    assert {"argv", "env", "credential_keys", "interpreters", "loaded_images", "probe_entry", "snapshots", "sha256"} <= set(doc)
    assert "credentials" not in doc                                        # C238: no values, no hashes


def test_new_volatile_keys_are_recorded_as_keys_only(tmp_path, monkeypatch):
    environ = {"PWD": "/some/where", "SHLVL": "3", "OLDPWD": "/x", "TERM_SESSION_ID": "w0t0p0:abc", "__CF_USER_TEXT_ENCODING": "0x1",
               "HOME": str(tmp_path / "home")}
    doc, env, _ = receipt(tmp_path, monkeypatch, environ=environ)
    for who in ("router", "worker", "probe"):
        e = doc["env"][who]
        assert all(e[k] == "<volatile>" for k in ("PWD", "SHLVL", "OLDPWD", "TERM_SESSION_ID", "__CF_USER_TEXT_ENCODING"))
        assert "/some/where" not in json.dumps(e)


def test_new_credential_keys_are_recorded_per_process_never_their_values_or_hashes(tmp_path, monkeypatch):
    """C238 [d2] §6.4 / §16.1: `credential_keys: {router: [key], worker: [key], probe: [key]}`; no value, no hash of one."""
    import hashlib
    environ = {"HF_TOKEN": S.FAKE_SECRET_40, "OPENAI_API_KEY": "Y" * 30, "TOKENIZERS_PARALLELISM": "false", "HOME": "/h"}
    doc, env, _ = receipt(tmp_path, monkeypatch, environ=environ)
    text = json.dumps(doc)
    assert {who: sorted(keys) for who, keys in doc["credential_keys"].items()} == {
        who: ["HF_TOKEN", "OPENAI_API_KEY"] for who in ("router", "worker", "probe")}
    for value in (S.FAKE_SECRET_40, "Y" * 30):
        assert value not in text
        assert hashlib.sha256(value.encode()).hexdigest() not in text
    for who in ("router", "worker", "probe"):
        assert "HF_TOKEN" not in doc["env"][who] and "OPENAI_API_KEY" not in doc["env"][who]   # §16.7: absent from env
        assert doc["env"][who].get("TOKENIZERS_PARALLELISM") == "false"          # not a credential: recorded as is


def test_new_an_off_and_an_on_receipt_of_one_build_pass_the_pair_gate(tmp_path, monkeypatch):
    shared = {"HOME": "/Users/op", "STACK_WORKDIR": "/wd", "HF_TOKEN": S.FAKE_SECRET_40, "PWD": "/x"}  # one box, both legs
    off, _, _ = receipt(tmp_path / "off", monkeypatch, arm="off", environ=shared)
    on, _, _ = receipt(tmp_path / "on", monkeypatch, arm="on", environ=shared)
    assert REC().pair_problems(off, on) == []                 # §16.7: the closed / volatile lists are module constants


def test_new_dot_env_files_are_a_credential_source(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    dot = tmp_path / "wt" / ".env"
    dot.parent.mkdir()
    dot.write_text('OWUI_ADMIN_PASSWORD="' + "P" * 20 + '"\nTOKENIZERS_PARALLELISM=false\n')
    values = set(SEC().credential_values(home=home, config_path=home / "none.sh", environ={}, env_files=(dot,)).values())
    assert "P" * 20 in values and "false" not in values
