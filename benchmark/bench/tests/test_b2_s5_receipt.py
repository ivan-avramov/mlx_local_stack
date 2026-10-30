"""B2 slice s5 (spec docs/specs/p426-b2-tg1-wave2.md v3.2, 3 / 6.3-6.5 / 11.3 / 16.1-16.6, C238): the credential classifier
(`bench.p426_secrets`), the arm-equality receipt, the pair gate and the pair dossier (`bench.p426_receipt`), the ChainOps
seams behind them, and their wiring into the chain (after load, before every invocation, the busy census).

Every secret here is a FAKE built at run time; no test reads the operator's real files or environment."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from bench import chain_ops as co
from bench import p426_receipt as pr
from bench import p426_secrets as ps

FAKE_TOKEN = "fake-" + "tok3n-" * 4                    # >= 12 chars, never a real credential
FAKE_API = "fake-" + "ap1k3y-" * 4
FAKE_FILE = "fake-" + "f1l3t0k-" * 3
DRAFTER = "caslca/Some-Model-mtp-drafter"
PAIRS = {"--draft-kind": "mtp", "--draft-model": DRAFTER, "--mtp-verify-scan": "joint_v1"}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


# ===================================================================================================== classifier
@pytest.mark.parametrize("name", ["HF_TOKEN", "hf_token", "OPENAI_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD",
                                  "GOOGLE_CREDENTIALS", "MY_AUTH", "MLX_API_KEY", "MLX_VLM_SERVER_API_KEY", "KV_AUTH_TOKEN",
                                  "SSH_AUTH_SOCK"])
def test_credential_keys_are_those_matching_the_six_patterns_case_insensitively(name):
    assert ps.is_credential_key(name)


@pytest.mark.parametrize("name", ["PATH", "HOME", "TOKENIZERS_PARALLELISM", "KV_KEY_BITS", "KV_KEY_SCHEME", "KV_PREALLOC_TOKENS",
                                  "TQ_KV_QUANT_MODE", "MLX_VLM_THINKING_START_TOKEN", "MLX_VLM_MAX_TOKENS", "MLX_VLM_TOKEN_QUEUE_TIMEOUT",
                                  "MLX_VLM_CACHE_SESSION_MAX", "MLX_SERVE_CONFIG"])
def test_the_committed_non_secret_allowlist_and_unrelated_names_are_not_credential_keys(name):
    assert not ps.is_credential_key(name)


def test_an_mlx_prefix_does_not_hide_a_credential_key():
    assert ps.is_credential_key("MLX_API_KEY") and ps.is_credential_key("MLX_VLM_SERVER_API_KEY")


def test_the_classifier_over_matches_by_design_names_containing_auth_are_credential_keys():
    assert ps.is_credential_key("GIT_AUTHOR_NAME")          # recorded as a key only; a known false positive of the pattern rule


# ===================================================================================================== format scan
def finding_kinds(text):
    return sorted({f.kind for f in ps.scan(text)})


@pytest.mark.parametrize("text, kind", [
    ("x hf_" + "a1B2c3D4e5" * 3 + " y", "hf_token"),
    ("key=sk-" + "Ab12" * 6, "sk_key"),
    ("ghp_" + "A1b2C3d4E5" * 4, "github_token"),
    ("github_pat_" + "A1b2C3d4E5_" * 3, "github_pat"),
    ("id AKIA" + "ABCDEFGH12345678", "aws_key_id"),
    ("-----BEGIN " + "RSA PRIVATE KEY-----", "private_key"),
    ("-----BEGIN " + "PRIVATE KEY-----", "private_key"),
    ("Authorization: Bearer " + "abc123def456", "bearer"),
])
def test_scan_finds_each_credential_format_with_offsets_and_no_value(text, kind):
    hits = ps.scan(text)
    assert [h.kind for h in hits] == [kind]
    h = hits[0]
    assert 0 <= h.start < h.end <= len(text)
    assert not hasattr(h, "value") and text[h.start:h.end] not in repr(h)


@pytest.mark.parametrize("text", [
    "def hf_hub_download(repo): pass",                       # a short word after `hf_`
    "the risk-assessment-framework-document", "a task-based-execution-plan-here",   # `sk-` inside a word
    "Authorization: Bearer <token>", "Authorization: Bearer $KEY", "headers['Authorization'] = 'Bearer ' + key",
    "-----BEGIN CERTIFICATE-----", "AKIA is a prefix", "ghp_short",
])
def test_scan_does_not_flag_prose_placeholders_or_code(text):
    assert ps.scan(text) == []


def test_scan_reports_every_occurrence_in_order():
    text = "a hf_" + "x1" * 15 + " b hf_" + "y2" * 15
    assert [h.start for h in ps.scan(text)] == sorted(h.start for h in ps.scan(text)) and len(ps.scan(text)) == 2


# ===================================================================================================== exact values
def test_exact_hits_find_every_occurrence_and_never_carry_the_value():
    text = f"before {FAKE_TOKEN} middle {FAKE_TOKEN} end"
    hits = ps.exact_hits(text, {"HF_TOKEN": FAKE_TOKEN})
    assert [(h.start, h.end) for h in hits] == [(7, 7 + len(FAKE_TOKEN)), (7 + len(FAKE_TOKEN) + 8, 7 + 2 * len(FAKE_TOKEN) + 8)]
    assert all(h.kind == "exact:HF_TOKEN" for h in hits) and FAKE_TOKEN not in repr(hits)


@pytest.mark.parametrize("value", ["", "short", "changeme", "true", "false", "none", "null", "0", "1", "x" * 11])
def test_exact_matching_ignores_short_and_placeholder_values(value):
    assert ps.exact_hits(f"text {value} text", {"K": value}) == []


def test_exact_matching_uses_a_12_character_value():
    v = "abcdefghijkl"
    assert len(ps.exact_hits(f"..{v}..", {"K": v})) == 1


# ===================================================================================================== sources
def write(path, text, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mode is not None:
        path.chmod(mode)
    return path


def test_credential_values_collect_the_four_sources_in_memory_and_filter(tmp_path):
    home = tmp_path / "home"
    cfg = write(tmp_path / "cfg/config.sh", f'export HF_TOKEN="{FAKE_TOKEN}"\nSTACK_DIR=/x\nexport SHORT_TOKEN=abc\n# OLD_KEY=zzz\n')
    envf = write(tmp_path / "wt/.env", f"MLX_API_KEY='{FAKE_API}'\nPLAIN=value\nPLACEHOLDER_SECRET=changeme\n")
    write(home / ".hftoken", FAKE_FILE + "\n")
    write(home / ".cache/huggingface/token", "tiny\n")
    got = ps.credential_values(home=home, config_path=cfg, environ={"OPENAI_API_KEY": FAKE_API + "-env", "PATH": "/bin",
                                                                  "TOKENIZERS_PARALLELISM": "false-and-long-enough"},
                               env_files=[envf])
    assert sorted(got.values()) == sorted([FAKE_TOKEN, FAKE_API, FAKE_FILE, FAKE_API + "-env"])
    assert not any(k in got for k in ("PATH", "PLAIN", "STACK_DIR"))          # non-credential keys never enter
    assert "tiny" not in got.values() and "abc" not in got.values() and "changeme" not in got.values()


def test_a_listed_file_that_exists_but_cannot_be_read_refuses_and_absent_files_are_recorded(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    home = tmp_path / "home"
    write(home / ".hftoken", FAKE_FILE, mode=0)
    with pytest.raises(ps.SecretsError) as e:
        ps.credential_values(home=home, config_path=tmp_path / "absent.sh", environ={})
    assert FAKE_FILE not in str(e.value) and ".hftoken" in str(e.value)
    (home / ".hftoken").chmod(0o600)
    assert ps.credential_values(home=home, config_path=tmp_path / "absent.sh", environ={}) == {"file:.hftoken": FAKE_FILE}
    assert ps.absent_sources(home=home, config_path=tmp_path / "absent.sh") == ["config", "file:.cache/huggingface/token"]


# ===================================================================================================== receipt fixtures
class ProcOps:
    """The per-process seams of `ChainOps`, answered from tables; `arm` decides the ON-only flag pairs and the drafter."""

    def __init__(self, arm, root, *, home="/home/tester", workdir="/scratch/wd", wt=None, out=None, drafter=DRAFTER, snaps=None):
        self.arm = arm
        self.wt = wt or f"{root}/stack-p426-{arm}"
        self.out = out or f"{root}/out/tg1-p426-{arm}-s1.a1"
        self.home, self.wd = home, workdir
        self.interp = {"path": f"{self.wt}/.venv/bin/python", "inventory_sha256": "1" * 64, "editables": {
            "mlx-vlm": dict(tree=f"{self.wt}/src/mlx-vlm", gitlink="a" * 40, clean=True),
            "mlx-serve": dict(tree=f"{self.wt}/src/mlx-serve", gitlink="b" * 40, clean=True)}}
        self.images = [dict(path=f"{self.wt}/.venv/lib/python3.12/site-packages/mlx/lib/libmlx.dylib", sha256="c" * 64),
                       dict(path=f"{self.wt}/.venv/lib/python3.12/site-packages/mlx/lib/mlx.metallib", sha256="d" * 64)]
        self.snaps = snaps or {"target": dict(hf_path="caslca/Some-Model", revision="r" * 40, files={"config.json": "e" * 64}),
                               "drafter": dict(hf_path=drafter, revision="q" * 40, files={"model.safetensors": "f" * 64})}
        if arm == "off":
            self.snaps = dict(self.snaps, drafter=None)
        self.calls = []
        base = [f"{self.wt}/.venv/bin/python", f"{self.wt}/.venv/bin/mlx_vlm.server", "--model", "caslca/Some-Model", "--host", "127.0.0.1",
                "--port", "8091", "--max-kv-size", "262144"]
        tail = ["--quantized-kv-start", "0"]
        on = [t for k, v in dict(PAIRS, **{"--draft-model": drafter}).items() for t in (k, v)] if arm == "on" else []
        self.argvs = {10: [f"{self.wt}/.venv/bin/python", f"{self.wt}/.venv/bin/mlx-serve", "start"], 20: base + on + tail}
        env = {"HOME": home, "USER": "tester", "LOGNAME": "tester", "PATH": f"{self.wt}/.venv/bin:/usr/bin", "PWD": self.wt, "OLDPWD": "/x",
               "SHLVL": "2", "_": "/usr/bin/env", "TERM_SESSION_ID": "w0t0p0:ABC", "SECURITYSESSIONID": "186a5",
               "__CF_USER_TEXT_ENCODING": "0x1F5:0:0", "MLX_SERVE_CONFIG": f"{self.wt}/main_models.yaml",
               "MLX_VLM_CACHE_SESSION_MAX": "1", "TMPDIR": f"{self.out}/tmp", "STACK_WORKDIR": workdir,
               "TOKENIZERS_PARALLELISM": "false", "KV_KEY_BITS": "8"}
        self.envs = {10: dict(env, HF_TOKEN=FAKE_TOKEN), 20: dict(env, HF_TOKEN=FAKE_TOKEN, MLX_VLM_SERVER_API_KEY=FAKE_API),
                     30: dict(env, HF_TOKEN=FAKE_TOKEN)}
        self.launch = dict(argv=[f"{self.wt}/.venv/bin/python", f"{self.wt}/benchmark/run_tg1_probe.py"], env=self.envs[30])

    def proc_argv(self, pid):
        self.calls.append(("proc_argv", pid))
        return list(self.argvs[pid])

    def proc_environ(self, pid):
        self.calls.append(("proc_environ", pid))
        return dict(self.envs[pid])

    def interpreter_inventory(self, pid, **kw):
        self.calls.append(("interpreter_inventory", pid))
        return copy.deepcopy(self.interp)

    def interpreter_inventory_at(self, exe):
        self.calls.append(("interpreter_inventory_at", exe))
        return copy.deepcopy(self.interp)

    def loaded_images(self, pid):
        return copy.deepcopy(self.images)

    def snapshot_hashes(self, model):
        return copy.deepcopy(self.snaps)


def receipt_of(arm, tmp_path, mutate=None, **kw):
    ops = ProcOps(arm, str(tmp_path), **kw)
    if mutate:
        mutate(ops)
    return pr.arm_receipt(ops, worktree=ops.wt, out_root=ops.out, pids=dict(router=10, worker=20, probe=None), model="Some-Model",
                          probe_launch=ops.launch), ops


@pytest.fixture
def pair(tmp_path):
    return receipt_of("off", tmp_path)[0], receipt_of("on", tmp_path)[0]


# ===================================================================================================== receipt fields
def test_the_receipt_has_exactly_the_16_1_fields_and_a_valid_self_hash(tmp_path):
    r, _ = receipt_of("on", tmp_path)
    assert set(r) == {"argv", "env", "credential_keys", "interpreters", "loaded_images", "probe_entry", "snapshots", "sha256"}
    assert set(r["argv"]) == {"router", "worker"} and set(r["env"]) == set(r["credential_keys"]) == {"router", "worker", "probe"}
    body = {k: v for k, v in r.items() if k != "sha256"}
    assert r["sha256"] == hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def test_roots_home_and_workdir_are_canonicalized_in_every_path_value(tmp_path):
    r, ops = receipt_of("on", tmp_path)
    text = json.dumps(r)
    for raw in (ops.wt, ops.out, ops.home, ops.wd, "tester\""):
        assert raw not in text, raw
    assert r["argv"]["worker"][:2] == ["<WT>/.venv/bin/python", "<WT>/.venv/bin/mlx_vlm.server"]
    assert r["env"]["router"]["MLX_SERVE_CONFIG"] == "<WT>/main_models.yaml" and r["env"]["router"]["TMPDIR"] == "<OUT>/tmp"
    assert r["env"]["router"]["STACK_WORKDIR"] == "$STACK_WORKDIR" and r["env"]["router"]["HOME"] == "$HOME"
    assert r["probe_entry"] == "<WT>/benchmark/run_tg1_probe.py"
    assert r["interpreters"][0]["path"] == "<WT>/.venv/bin/python"
    assert r["interpreters"][0]["editables"]["mlx-vlm"] == dict(tree="<WT>/src/mlx-vlm", gitlink="a" * 40, clean=True)
    assert all(i["path"].startswith("<WT>/") for i in r["loaded_images"])


def test_a_root_is_replaced_only_at_a_path_boundary(tmp_path):
    def mutate(ops):
        ops.envs[10]["NEAR"] = ops.wt + "2/x"
        ops.envs[10]["EXACT"] = ops.wt
    r, ops = receipt_of("off", tmp_path, mutate)
    assert r["env"]["router"]["NEAR"] == ops.wt + "2/x" and r["env"]["router"]["EXACT"] == "<WT>"


def test_volatile_keys_are_recorded_as_keys_only(tmp_path):
    r, _ = receipt_of("on", tmp_path)
    for key in ("_", "OLDPWD", "PWD", "SHLVL", "TERM_SESSION_ID", "SECURITYSESSIONID", "__CF_USER_TEXT_ENCODING"):
        assert all(r["env"][p][key] == "<volatile>" for p in r["env"]), key
    text = json.dumps(r)
    assert "w0t0p0:ABC" not in text and "186a5" not in text and "0x1F5" not in text
    assert r["env"]["router"]["TOKENIZERS_PARALLELISM"] == "false" and r["env"]["router"]["KV_KEY_BITS"] == "8"


def test_credential_keys_are_recorded_per_process_as_keys_only_with_no_value_and_no_hash(tmp_path):
    r, _ = receipt_of("on", tmp_path)
    assert r["credential_keys"] == {"router": ["HF_TOKEN"], "worker": ["HF_TOKEN", "MLX_VLM_SERVER_API_KEY"], "probe": ["HF_TOKEN"]}
    assert all("HF_TOKEN" not in r["env"][p] and "MLX_VLM_SERVER_API_KEY" not in r["env"][p] for p in r["env"])
    text = json.dumps(r)
    for secret in (FAKE_TOKEN, FAKE_API):
        assert secret not in text and sha(secret) not in text and hashlib.sha256(secret.encode()).digest().hex() not in text
        assert base64.b64encode(hashlib.sha256(secret.encode()).digest()).decode() not in text


def test_the_probe_environment_comes_from_the_launch_spec_when_no_probe_process_exists_else_from_its_pid(tmp_path):
    r, ops = receipt_of("off", tmp_path)
    assert ("proc_environ", 30) not in ops.calls and r["env"]["probe"]["MLX_VLM_CACHE_SESSION_MAX"] == "1"
    ops = ProcOps("off", str(tmp_path))
    ops.argvs[30] = ops.launch["argv"] + ["--model", "m"]
    r2 = pr.arm_receipt(ops, worktree=ops.wt, out_root=ops.out, pids=dict(router=10, worker=20, probe=30), model="Some-Model")
    assert ("proc_environ", 30) in ops.calls and r2["probe_entry"] == "<WT>/benchmark/run_tg1_probe.py"


def test_one_interpreter_used_by_all_three_processes_is_listed_once(tmp_path):
    r, ops = receipt_of("on", tmp_path)
    assert len(r["interpreters"]) == 1 and r["interpreters"][0]["inventory_sha256"] == "1" * 64
    assert [c for c in ops.calls if c[0] == "interpreter_inventory"]          # asked per process, deduplicated by path


def test_two_inventories_for_one_interpreter_path_are_a_receipt_error(tmp_path):
    ops = ProcOps("on", str(tmp_path))
    answers = iter(["1" * 64, "2" * 64, "1" * 64])
    base = ops.interpreter_inventory
    ops.interpreter_inventory = lambda pid, **kw: dict(base(pid), inventory_sha256=next(answers))
    with pytest.raises(pr.ReceiptError, match="inventory"):
        pr.arm_receipt(ops, worktree=ops.wt, out_root=ops.out, pids=dict(router=10, worker=20, probe=None), model="m", probe_launch=ops.launch)


def test_loaded_images_snapshots_and_the_drafter_per_arm(tmp_path):
    on, _ = receipt_of("on", tmp_path)
    off, _ = receipt_of("off", tmp_path)
    assert [i["path"].rsplit("/", 1)[1] for i in on["loaded_images"]] == ["libmlx.dylib", "mlx.metallib"]
    assert on["snapshots"]["drafter"]["hf_path"] == DRAFTER and off["snapshots"]["drafter"] is None
    assert on["snapshots"]["target"] == off["snapshots"]["target"]


@pytest.mark.parametrize("drop", ["libmlx.dylib", "mlx.metallib"])
def test_a_native_library_the_worker_did_not_load_is_a_receipt_error(tmp_path, drop):
    with pytest.raises(pr.ReceiptError, match=drop.replace(".", r"\.")):
        receipt_of("on", tmp_path, lambda ops: setattr(ops, "images", [i for i in ops.images if not i["path"].endswith(drop)]))


def test_a_dirty_or_misplaced_editable_tree_is_a_receipt_error(tmp_path):
    with pytest.raises(pr.ReceiptError, match="mlx-vlm"):
        receipt_of("on", tmp_path, lambda ops: ops.interp["editables"]["mlx-vlm"].update(clean=False))
    with pytest.raises(pr.ReceiptError, match="mlx-serve"):
        receipt_of("on", tmp_path, lambda ops: ops.interp["editables"]["mlx-serve"].update(tree="/elsewhere/mlx-serve"))


# ===================================================================================================== pair gate
def test_an_off_on_pair_differs_only_by_the_allowed_list(pair):
    off, on = pair
    assert pr.pair_problems(off, on) == []
    assert pr.pair_problems(on, off) == []        # order of legs is free
    assert [d["field"] for d in pr.observed_differences(off, on)] == ["snapshots.drafter", "argv.worker"]


def reseal(r):
    body = {k: v for k, v in r.items() if k != "sha256"}
    return dict(body, sha256=hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest())


def problems(off, on, **kw):
    return pr.pair_problems(reseal(off), reseal(on))


def test_a_receipt_whose_self_hash_does_not_verify_is_a_problem(pair):
    off, on = pair
    on = dict(on, probe_entry="<WT>/other.py")
    assert any("sha256" in p for p in pr.pair_problems(off, on))


def test_two_legs_of_the_same_arm_are_not_a_pair(tmp_path):
    a, b = receipt_of("off", tmp_path)[0], receipt_of("off", tmp_path)[0]
    assert any("one OFF and one ON" in p for p in problems(a, b))
    a, b = receipt_of("on", tmp_path)[0], receipt_of("on", tmp_path)[0]
    assert any("one OFF and one ON" in p for p in problems(a, b))


@pytest.mark.parametrize("edit", [
    lambda on: on["argv"]["worker"].extend(["--extra-flag", "1"]),                                      # an extra worker flag
    lambda on: on["argv"]["worker"].__setitem__(on["argv"]["worker"].index("joint_v1"), "per_query"),   # a wrong pair value
    lambda on: on["argv"]["worker"].__setitem__(on["argv"]["worker"].index("--max-kv-size") + 1, "1"),  # another flag's value
    lambda on: on["argv"]["worker"].__delitem__(slice(-4, -2)) if False else on["argv"]["worker"].extend(["--draft-kind", "mtp"]),   # a duplicate pair
    lambda on: on["argv"]["router"].append("--x"),
])
def test_any_argv_difference_outside_the_three_pairs_is_a_problem(pair, edit):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    edit(on)
    assert problems(off, on)


def test_an_on_worker_missing_a_pair_is_a_problem(pair):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    i = on["argv"]["worker"].index("--mtp-verify-scan")
    del on["argv"]["worker"][i:i + 2]
    assert any("mtp" in p.lower() for p in problems(off, on))


def test_the_pairs_are_position_free_but_the_rest_must_keep_its_order(pair):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    w = on["argv"]["worker"]
    i = w.index("--draft-kind")
    moved = w[i:i + 6]
    del w[i:i + 6]
    w[2:2] = moved                                                  # the pairs elsewhere: allowed
    assert problems(off, on) == []
    w2 = copy.deepcopy(on)
    a, b = w2["argv"]["worker"].index("--host"), w2["argv"]["worker"].index("--port")
    w2["argv"]["worker"][a:a + 2], w2["argv"]["worker"][b:b + 2] = w2["argv"]["worker"][b:b + 2], w2["argv"]["worker"][a:a + 2]
    assert problems(off, w2)


def test_the_draft_model_must_be_the_drafter_snapshot_that_was_hashed(pair):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    on["snapshots"]["drafter"]["hf_path"] = "caslca/Other-mtp-drafter"
    assert any("drafter" in p for p in problems(off, on))


def test_the_allowed_list_is_closed():
    assert set(pr.ALLOWED_DIFFERENCES) == {"worker_argv.mtp_pairs", "snapshots.drafter"}


def test_a_drafter_snapshot_on_the_off_side_or_a_target_difference_is_a_problem(pair):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    off["snapshots"]["drafter"] = copy.deepcopy(on["snapshots"]["drafter"])
    assert problems(off, on)
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    on["snapshots"]["target"]["revision"] = "z" * 40
    assert any("target" in p for p in problems(off, on))


@pytest.mark.parametrize("proc", ["router", "worker", "probe"])
def test_an_environment_value_or_non_volatile_key_difference_is_a_problem(pair, proc):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    on["env"][proc]["KV_KEY_BITS"] = "4"
    assert any(f"env.{proc}" in p and "KV_KEY_BITS" in p for p in problems(off, on))
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    on["env"][proc]["NEW_VARIABLE"] = "1"
    assert any(f"env.{proc}" in p and "NEW_VARIABLE" in p for p in problems(off, on))


def test_a_volatile_key_present_in_one_leg_only_is_allowed_a_stable_key_present_in_one_leg_only_is_not(pair):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    del on["env"]["router"]["SHLVL"]
    assert problems(off, on) == []
    assert "env.SHLVL" in [d["field"] for d in pr.observed_differences(reseal(off), reseal(on))]
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    del on["env"]["router"]["TMPDIR"]
    assert problems(off, on)


def test_a_key_that_is_not_on_the_closed_volatile_list_cannot_hide_behind_the_volatile_marker(pair):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    on["env"]["router"]["KV_KEY_BITS"] = "<volatile>"
    assert any("KV_KEY_BITS" in p for p in problems(off, on))


@pytest.mark.parametrize("proc", ["router", "worker", "probe"])
def test_a_credential_key_present_in_one_process_of_one_leg_only_is_a_problem(pair, proc):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    on["credential_keys"][proc] = sorted(on["credential_keys"][proc] + ["EXTRA_API_KEY"])
    ps_ = problems(off, on)
    assert any(f"credential_keys.{proc}" in p and "EXTRA_API_KEY" in p for p in ps_)
    off2, on2 = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    off2["credential_keys"][proc] = sorted(off2["credential_keys"][proc] + ["EXTRA_API_KEY"])
    assert problems(off2, on2)
    assert all(FAKE_TOKEN not in p and FAKE_API not in p for p in ps_)


def test_the_same_credential_keys_in_both_legs_are_equal_whatever_their_values(tmp_path):
    off = receipt_of("off", tmp_path)[0]

    def other_values(ops):
        for env in ops.envs.values():
            env["HF_TOKEN"] = FAKE_FILE
    on = receipt_of("on", tmp_path, other_values)[0]
    assert problems(off, on) == []                                  # values are neither recorded nor compared (C238)


@pytest.mark.parametrize("field, edit", [
    ("interpreters", lambda r: r["interpreters"][0].update(inventory_sha256="9" * 64)),
    ("interpreters", lambda r: r["interpreters"][0]["editables"]["mlx-vlm"].update(gitlink="9" * 40)),
    ("loaded_images", lambda r: r["loaded_images"][0].update(sha256="9" * 64)),
    ("probe_entry", lambda r: r.update(probe_entry="<WT>/other.py")),
])
def test_interpreter_image_and_probe_entry_differences_are_problems(pair, field, edit):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    edit(on)
    assert any(field in p for p in problems(off, on))


def test_every_problem_names_its_field_and_none_carries_a_credential_value(pair):
    off, on = copy.deepcopy(pair[0]), copy.deepcopy(pair[1])
    on["env"]["worker"]["KV_KEY_BITS"] = "4"
    on["credential_keys"]["worker"].append("Z_TOKEN")
    for p in problems(off, on):
        assert p.split(":")[0].split(".")[0] in {"argv", "env", "credential_keys", "interpreters", "loaded_images", "probe_entry", "snapshots", "receipt"}


# ===================================================================================================== argv + snapshot checks
EXPECTED = ["/venv/bin/mlx_vlm.server", "--model", "m", "--port", "8091"]


def test_the_worker_argv_must_equal_the_one_mlx_serve_builds(tmp_path):
    assert pr.worker_argv_problems(EXPECTED, EXPECTED, "off") == []
    assert pr.worker_argv_problems(["/venv/bin/python"] + EXPECTED, EXPECTED, "off")               # exact: no tolerated leading token
    assert pr.worker_argv_problems(EXPECTED + ["--x"], EXPECTED, "off")
    assert pr.worker_argv_problems(EXPECTED[:-1], EXPECTED, "off")


def test_off_carries_none_of_the_pairs_and_on_exactly_the_three():
    on = EXPECTED + [t for k, v in PAIRS.items() for t in (k, v)]
    assert pr.worker_argv_problems(on, on, "on") == [] and pr.worker_argv_problems(EXPECTED, EXPECTED, "off") == []
    assert pr.worker_argv_problems(on, on, "off") and pr.worker_argv_problems(EXPECTED, EXPECTED, "on")
    wrong = EXPECTED + ["--draft-kind", "mtp", "--draft-model", DRAFTER]
    assert pr.worker_argv_problems(wrong, wrong, "on")


PINS = {"Some-Model": {"target": dict(hf_path="caslca/Some-Model", revision="r" * 40, files={"config.json": "e" * 64}),
                       "drafter": dict(hf_path=DRAFTER, revision="q" * 40, files={"model.safetensors": "f" * 64})}}


def test_the_snapshots_must_equal_the_reviewed_pins_target_always_drafter_on_only(tmp_path):
    off, on = (receipt_of(a, tmp_path)[0]["snapshots"] for a in ("off", "on"))
    assert pr.snapshot_problems(off, PINS, "Some-Model", "off") == [] and pr.snapshot_problems(on, PINS, "Some-Model", "on") == []
    bad = copy.deepcopy(on)
    bad["target"]["files"]["config.json"] = "0" * 64
    assert any("target" in p for p in pr.snapshot_problems(bad, PINS, "Some-Model", "on"))
    bad = copy.deepcopy(on)
    bad["drafter"]["revision"] = "0" * 40
    assert any("drafter" in p for p in pr.snapshot_problems(bad, PINS, "Some-Model", "on"))
    assert any("drafter" in p for p in pr.snapshot_problems(on, PINS, "Some-Model", "off"))            # OFF loads no drafter
    assert any("drafter" in p for p in pr.snapshot_problems(off, PINS, "Some-Model", "on"))
    assert any("no reviewed pins" in p for p in pr.snapshot_problems(on, PINS, "Other-Model", "on"))


def test_the_pins_come_from_the_forks_pins_json_in_the_worktree(tmp_path):
    f = tmp_path / "src/mlx-vlm/dev/p369_phase2/pins.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(PINS))
    assert pr.load_pins(tmp_path) == PINS
    with pytest.raises(pr.ReceiptError, match="pins"):
        pr.load_pins(tmp_path / "missing")


# ===================================================================================================== ChainOps seams (RECORD, vmmap, snapshots, argv)
def b64(path):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b"=").decode()


def dist(site, name, version, files, editable_tree=None):
    d = site / f"{name.replace('-', '_')}-{version}.dist-info"
    d.mkdir(parents=True)
    (d / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    rows = []
    for rel, body in files.items():
        f = site / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
        rows.append(f"{rel},{b64(f)},{len(body)}")
    rows += [f"{d.name}/METADATA,,", f"{d.name}/RECORD,,", "pkg/__pycache__/x.cpython-312.pyc,,"]
    (d / "RECORD").write_text("\n".join(rows) + "\n")
    if editable_tree:
        (d / "direct_url.json").write_text(json.dumps({"url": "file://" + str(editable_tree), "dir_info": {"editable": True}}))
    return d


@pytest.fixture
def site(tmp_path):
    s = tmp_path / "venv/lib/python3.12/site-packages"
    s.mkdir(parents=True)
    dist(s, "alpha", "1.0", {"alpha/__init__.py": "A = 1\n", "alpha/core.py": "B = 2\n"})
    dist(s, "beta", "2.1", {"beta.py": "C = 3\n"})
    tree = tmp_path / "wt/src/mlx-vlm"
    tree.mkdir(parents=True)
    dist(s, "mlx-vlm", "0.4", {"__editable__.mlx_vlm.pth": str(tree) + "\n"}, editable_tree=tree)
    return s


def git_sh(clean=True, head="a" * 40):
    def sh(cmd, **kw):
        assert cmd[:1] == ["git"], cmd
        out = head + "\n" if "rev-parse" in cmd else ("" if clean else " M x.py\n")
        return co.Result(out, "", 0)
    return sh


def chain_ops(tmp_path, sh=None, env=None):
    return co.ChainOps(tmp_path / "repo", tmp_path / "wd", tmp_path / "wd/served.yaml", lambda m: None, sh=sh or git_sh(),
                       env_source=env if env is not None else {})


def test_the_inventory_hashes_sorted_name_version_and_record_digests_and_excludes_the_editable(tmp_path, site):
    inv = chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)
    assert set(inv) == {"path", "inventory_sha256", "editables"} and len(inv["inventory_sha256"]) == 64
    assert list(inv["editables"]) == ["mlx-vlm"] and inv["editables"]["mlx-vlm"] == dict(
        tree=str(tmp_path / "wt/src/mlx-vlm"), gitlink="a" * 40, clean=True)
    again = chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)
    assert again["inventory_sha256"] == inv["inventory_sha256"]
    (site / "mlx_vlm-0.4.dist-info/METADATA").write_text("Name: mlx-vlm\nVersion: 9\n")           # editable metadata is excluded
    assert chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)["inventory_sha256"] == inv["inventory_sha256"]
    (site / "alpha/core.py").write_text("B = 2\n")                                               # same bytes: still equal
    assert chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)["inventory_sha256"] == inv["inventory_sha256"]


def test_a_mutated_record_file_is_systemic_on_a_fixture_site_packages_tree(tmp_path, site):
    (site / "alpha/core.py").write_text("B = 3\n")
    with pytest.raises(co.ChainAbort, match=r"alpha.*core\.py|core\.py.*alpha"):
        chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)


def test_a_record_file_that_is_gone_is_systemic(tmp_path, site):
    (site / "beta.py").unlink()
    with pytest.raises(co.ChainAbort, match="beta"):
        chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)


def test_a_new_version_changes_the_inventory_and_a_dirty_editable_tree_is_reported(tmp_path, site):
    base = chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)
    dist(site, "gamma", "1.0", {"gamma.py": "G = 1\n"})
    assert chain_ops(tmp_path).interpreter_inventory(0, site_packages=site)["inventory_sha256"] != base["inventory_sha256"]
    dirty = chain_ops(tmp_path, sh=git_sh(clean=False)).interpreter_inventory(0, site_packages=site)
    assert dirty["editables"]["mlx-vlm"]["clean"] is False


VMMAP = """Process:         python [4242]
==== Non-writable regions for process 4242
REGION TYPE                    START - END         [ VSIZE  RSDNT  DIRTY   SWAP] PRT/MAX SHRMOD PURGE    REGION DETAIL
__TEXT                      100000000-100004000    [   16K    16K     0K     0K] r-x/r-x SM=COW          /venv/bin/python
__TEXT                      102000000-103000000    [   16M    12M     0K     0K] r-x/r-x SM=COW          {lib}/libmlx.dylib
__TEXT                      104000000-105000000    [   16M    12M     0K     0K] r-x/r-x SM=COW          {lib}/libmlx.dylib
mapped file                 106000000-107000000    [   16M    12M     0K     0K] r--/r-- SM=COW          {lib}/mlx.metallib
mapped file                 108000000-109000000    [   16M    12M     0K     0K] r--/r-- SM=COW          /usr/lib/libSystem.dylib
"""


def test_loaded_images_come_from_vmmap_not_lsof_and_carry_the_sha256_of_each_loaded_file(tmp_path):
    lib = tmp_path / "mlx/lib"
    lib.mkdir(parents=True)
    (lib / "libmlx.dylib").write_bytes(b"dylib")
    (lib / "mlx.metallib").write_bytes(b"metallib")
    seen = []

    def sh(cmd, **kw):
        seen.append(cmd)
        return co.Result(VMMAP.format(lib=lib), "", 0)
    got = chain_ops(tmp_path, sh=sh).loaded_images(4242)
    assert seen == [["vmmap", "-w", "4242"]] or seen[0][0] == "vmmap"
    assert got == [dict(path=str(lib / "libmlx.dylib"), sha256=hashlib.sha256(b"dylib").hexdigest()),
                   dict(path=str(lib / "mlx.metallib"), sha256=hashlib.sha256(b"metallib").hexdigest())]


def test_loaded_images_refuse_when_vmmap_fails_or_the_file_cannot_be_hashed(tmp_path):
    with pytest.raises(co.ChainAbort, match="vmmap"):
        chain_ops(tmp_path, sh=lambda cmd, **kw: co.Result("", "denied", 1)).loaded_images(1)
    with pytest.raises(co.ChainAbort, match="libmlx"):
        chain_ops(tmp_path, sh=lambda cmd, **kw: co.Result(VMMAP.format(lib=tmp_path / "gone"), "", 0)).loaded_images(1)


def test_snapshot_hashes_have_the_pins_shape_for_the_target_and_the_drafter(tmp_path):
    import yaml
    cache = tmp_path / "hub"
    for hf, rev, files in (("caslca/Some-Model", "r1", {"config.json": b"{}", "sub/extra.bin": b"zz", "README.md": b"doc"}),
                           (DRAFTER, "q1", {"model.safetensors": b"w"})):
        repo = cache / ("models--" + hf.replace("/", "--"))
        (repo / "refs").mkdir(parents=True)
        (repo / "refs/main").write_text(rev + "\n")
        for rel, body in files.items():
            f = repo / "snapshots" / rev / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(body)
    served = tmp_path / "wd/served.yaml"
    served.parent.mkdir()
    served.write_text(yaml.safe_dump({"models": [dict(name="Some-Model", hf_path="caslca/Some-Model", draft_kind="mtp", draft_model=DRAFTER),
                                                 dict(name="Plain", hf_path="caslca/Some-Model")]}))
    ops = chain_ops(tmp_path, env={"HF_HUB_CACHE": str(cache)})
    got = ops.snapshot_hashes("Some-Model")
    assert got["target"] == dict(hf_path="caslca/Some-Model", revision="r1", files={
        "config.json": hashlib.sha256(b"{}").hexdigest(), "sub/extra.bin": hashlib.sha256(b"zz").hexdigest()})
    assert got["drafter"] == dict(hf_path=DRAFTER, revision="q1", files={"model.safetensors": hashlib.sha256(b"w").hexdigest()})
    assert ops.snapshot_hashes("Plain")["drafter"] is None


def test_expected_worker_argv_runs_the_forks_own_builder_in_the_worktree_environment(tmp_path):
    seen = {}

    def sh(cmd, **kw):
        seen.update(cmd=cmd, **kw)
        return co.Result(json.dumps(["/venv/bin/mlx_vlm.server", "--model", "m"]), "", 0)
    ops = chain_ops(tmp_path, sh=sh)
    assert ops.expected_worker_argv(tmp_path / "reg.yaml", "Some-Model") == ["/venv/bin/mlx_vlm.server", "--model", "m"]
    assert seen["cmd"][0] == str(ops.repo / ".venv/bin/python") and "-I" in seen["cmd"] and "_build_command" in " ".join(seen["cmd"])
    assert seen["env"]["MLX_SERVE_CONFIG"] == str(tmp_path / "reg.yaml") and "Some-Model" in seen["cmd"]
    with pytest.raises(co.ChainAbort, match="builder"):
        chain_ops(tmp_path, sh=lambda cmd, **kw: co.Result("not json", "boom", 1)).expected_worker_argv(tmp_path / "r.yaml", "m")


def test_process_seams_read_a_real_process_and_its_descendants():
    ops = co.ChainOps.__new__(co.ChainOps)
    assert ops.proc_argv(os.getpid())[0] and isinstance(ops.proc_environ(os.getpid()), dict)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert child.pid in ops.descendants(os.getpid()) and os.getpid() not in ops.descendants(os.getpid())
        assert ops.proc_argv(child.pid)[-1] == "import time; time.sleep(30)"
    finally:
        child.kill()
        child.wait()


@pytest.mark.parametrize("name", ["proc_argv", "proc_environ", "descendants", "interpreter_inventory", "loaded_images", "snapshot_hashes",
                                  "expected_worker_argv", "busy_procs", "worktree_state"])
def test_chain_ops_defines_every_receipt_seam(name):
    assert callable(getattr(co.ChainOps, name))


def test_chain_ops_answers_create_time_per_instance_and_defines_no_seam_the_spec_does_not_name(tmp_path):
    ops = co.ChainOps(tmp_path / "repo", tmp_path / "wd", tmp_path / "wd/served.yaml", lambda m: None, create_time=lambda pid: 5.0)
    assert ops.create_time(7) == 5.0
    assert not hasattr(co.ChainOps, "identity_alive") and not hasattr(co.ChainOps, "router_identity")
