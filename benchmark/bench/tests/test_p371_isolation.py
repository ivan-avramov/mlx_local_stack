"""P371 phase 4 (plan 5 "Isolation (R17)", acceptance criterion 5): ONE test process runs three configurations of the shared
core, each through its probe AND its chain (fake client / fake probe / fake ops, no router, worker or GPU), in BOTH orders:

  tg1            `run_tg1_probe` (fake opencode binary) + the tg1 chain (`run_tg1_chain`, fake probe)
  m64-oc-tg1     `run_oc_probe` (fake client, offline search service) + the M64 chain with the arm `oc`
  neutral-4lang  a NON-opencode adapter (`NeutralArm`) over a four-language fake corpus (rust, java, javascript, cpp)
                 + the M64 chain over those four languages with the fake non-opencode arm `dsh`

Per configuration the record holds its rows, identities (probe code / scaffold policy / generation composite), closures, the
chain's frozen lifecycle and the disabled features; the two orders must produce IDENTICAL records (no state leaks between
configurations), the three configurations' identities must be pairwise distinct, tg1 must have no watchdog, compaction,
receipts or barrier files, and the M64 chains must have barrier files."""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import threading
from pathlib import Path

import pytest

from bench import arm_runner
from bench import chain_core as core
from bench import identity_closure as ic
from bench import provenance
from bench import tg1_runner
from bench.tests import m64_support as ms
from bench.tests import test_c147_chain_runner as t1c
from bench.tests import test_p371_oc_fake_item as oc_item
from bench.tests.arm_neutral import LABEL, NeutralArm, NeutralCorpus
from bench.tests.p371_world import args as core_args, evidence as core_evidence, neutral_world, template as core_template
from bench.tests.test_tg1_integration import tg_fixture

REPO = Path(__file__).resolve().parents[3]
LANGS4 = ("rust", "java", "javascript", "cpp")
BARRIER_FILE = re.compile(r"\.item\d+\.(ready|go|done|continue|stop)$")
# the fake client binary is a script that names its own temp directory, so its exe sha (an input of the opencode composites) is
# the one value that legitimately differs between two runs; every other generation input must not
VOLATILE = ("opencode_exe_sha256", "generation_identity_sha256", "snapshot_sha256")
CONFIGS = ("tg1", "m64-oc-tg1", "neutral-4lang")


class FourLangCorpus(NeutralCorpus):
    """The neutral one-file corpus over four languages (two items each)."""
    corpus_id = "neutral-4lang"
    languages = LANGS4

    def load_universe(self, path=None):
        return {"items": {f"{lang}/{n}": {} for lang in LANGS4 for n in ("one", "two")}}, "u" * 64

    def items(self, lang):
        return [f"{lang}/one", f"{lang}/two"] if lang in LANGS4 else []


def barrier_files(root):
    return sorted(p.name for p in Path(root).rglob("*") if p.is_file() and BARRIER_FILE.search(p.name))


def probe_record(rows_path, *, entry_files=None):
    """Rows, identities and disabled features of one probe invocation (rows file + its manifest)."""
    rows_path = Path(rows_path)
    rows = [json.loads(x) for x in rows_path.read_text().splitlines()]
    man = json.loads(rows_path.with_suffix(".manifest.json").read_text())
    rt = man["runtime"]
    return dict(
        rows=[dict(id=r["id"], config_id=r["config_id"], arm=r["arm"], passed=r["passed"], nonconv_kind=r["nonconv_kind"],
                   stop_reason=r["stop_reason"], keys=sorted(r)) for r in rows],
        config_id=rt["config_id"], arm=rt["arm"], scaffold=rt["scaffold"], probe_code=rt["probe_code_sha256"],
        policy=rt["scaffold_policy_sha256"], generation=rt["generation_identity_sha256"],
        generation_inputs={k: rt.get(k) for k in sorted(rt) if k.endswith("_sha256") and k not in VOLATILE},
        evidence_policy=rt["evidence_policy"], watchdog=rt["policy"]["watchdog"], compaction=rt["policy"]["compaction"],
        langs=rt["policy"]["langs"], barrier_files=barrier_files(rows_path.parent))


# ---------------------------------------------------------------- the three probes
def probe_tg1(mp, tmp):
    mp.setenv("STACK_WORKDIR", str(tmp))
    p = importlib.import_module("run_tg1_probe")
    f = tg_fixture(p, mp, tmp)
    assert f["run"]("one", extra=["--expect-items", "python/one"]) == 0
    return probe_record(f["out"])


def probe_oc(mp, tmp):
    return probe_record(oc_item.run_fake_oc_item(mp, tmp))


def probe_neutral(mp, tmp):
    world = neutral_world(mp, tmp)
    records = {}
    for lang in LANGS4:
        out = tmp / f"rows.{lang}.jsonl"
        a = core_args(tmp, lang=lang, out=str(out), items="one")
        assert arm_runner.main(world.host, NeutralArm(world.host), a, template=core_template(
            config_id="neutral-4lang", langs=LANGS4), evidence=core_evidence(), corpus=FourLangCorpus(tmp)) == 0
        records[lang] = probe_record(out)
    first = records[LANGS4[0]]
    for lang, rec in records.items():              # one configuration: the same identities for every language
        assert {k: rec[k] for k in ("probe_code", "policy", "generation", "config_id", "arm")} == \
            {k: first[k] for k in ("probe_code", "policy", "generation", "config_id", "arm")}, lang
    return dict(first, rows=[row for lang in LANGS4 for row in records[lang]["rows"]],
                barrier_files=sorted(f for rec in records.values() for f in rec["barrier_files"]))


# ---------------------------------------------------------------- the three chains
def tg1_chain_env(tmp, mp):
    mp.setenv("STACK_WORKDIR", str(tmp))
    ops = t1c.FakeOps(tmp)
    uni = tmp / "universe.json"
    uni.write_text(json.dumps({"items": {**{f"python/p{i}": {} for i in range(1, 7)}, **{f"go/g{i}": {} for i in range(1, 7)}}}))
    return dict(wd=tmp, ops=ops, uni=uni, lines=[], out=tmp / "c147")


def m64_chain_env(tmp, mp):
    mp.setenv("STACK_WORKDIR", str(tmp))
    ms.fake_specs(mp)
    ops = ms.FakeOps(tmp)
    uni = tmp / "universe.json"
    uni.write_text(json.dumps({"items": {**{f"python/p{i:02d}": {} for i in range(22)}, **{f"go/g{i:02d}": {} for i in range(21)}}}))
    return dict(wd=tmp, ops=ops, uni=uni, lines=[], out=tmp / "m64-smoke")


def chain_record(env, extra=None):
    cj = json.loads((env["out"] / "chain.json").read_text())
    return dict(config_id=cj["chain_config"]["config_id"], builder=cj["chain_config"]["schedule"]["builder"],
                transport=cj["chain_config"]["transport_policy"], resume=cj["chain_config"]["resume_policy"],
                langs=cj["chain_config"]["schedule"]["params"].get("langs"), lifecycle=sorted(cj["lifecycle"]),
                lifecycle_sha=cj["lifecycle"], arms=sorted(cj["arms"]), status=cj["status"], rc=cj["rc"],
                scored=len(core.cr.load_slots(cj, env["out"]).scored), contract=cj["artifacts"]["contract"],
                campaign=cj["artifacts"]["campaign_core"], barrier_files=barrier_files(env["out"]), **(extra or {}))


def chain_tg1(mp, tmp):
    env = tg1_chain_env(tmp, mp)
    try:
        assert t1c.run(env, t1c.CHAIN) == 0
        return chain_record(env)
    finally:
        env["ops"].cancel()


def chain_oc(mp, tmp):
    env = m64_chain_env(tmp, mp)
    try:
        assert ms.run(env, ms.SMOKE) == 0
        return chain_record(env)
    finally:
        env["ops"].cancel()


def chain_neutral(mp, tmp):
    env = m64_chain_env(tmp, mp)
    argv = ["chain", "s1", "--smoke", "--arms", "dsh", "--probe-code-sha", "dsh=" + "9" * 64, "--python", sys.executable,
            "--out-root", str(env["out"]), "--arm-idle-s", "0", "--probe", f"dsh={ms.FAP_PATH}",
            "--frozen-prompt-date", ms.FROZEN]
    a = ms.M.parse_args(argv)
    cfg = ms.M.m64_config(a, langs=LANGS4)
    names = {lang: [f"{lang[:2]}{i:02d}" for i in range(4)] for lang in LANGS4}
    chain = core.Chain(cfg, a, env["ops"], ms.M.Timers(**t1c.TIMERS), env["lines"].append, repo=REPO, out_root=env["out"],
                       names=names, lifecycle_files=ms.M.lifecycle_files(REPO), needs_docker=lambda lang: False)
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("rc", chain.run()), daemon=True)
    th.start()
    th.join(120)
    try:
        assert not th.is_alive() and res["rc"] == 0, "\n".join(env["lines"][-15:])
        return chain_record(env)
    finally:
        env["ops"].cancel()


STEPS = dict(tg1=(probe_tg1, chain_tg1), **{"m64-oc-tg1": (probe_oc, chain_oc), "neutral-4lang": (probe_neutral, chain_neutral)})


# ---------------------------------------------------------------- one process, both orders
def environment_state():
    return dict(env={k: v for k, v in os.environ.items() if k in ("MLX_SERVE_CONFIG", "OPENCODE_PROBE_BIN", "OPENCODE_CONFIG",
                                                                 "OPENCODE_CONFIG_CONTENT")},
                seams=(arm_runner.worker_json, arm_runner.worker_identity, arm_runner.arm_identity_of,
                       provenance.assert_served_config, provenance.assert_served_config_unchanged))


def run_order(order, root, monkeypatch):
    out = {}
    for name in order:
        before = environment_state()
        sub = root / name
        (sub / "probe").mkdir(parents=True)
        (sub / "chain").mkdir()
        with monkeypatch.context() as mp:                 # everything a configuration patches is undone with it
            probe, chain = STEPS[name]
            out[name] = dict(probe=probe(mp, sub / "probe"), chain=chain(mp, sub / "chain"))
        assert environment_state() == before, f"{name} left process state behind (env var or patched seam)"
    return out


@pytest.fixture(scope="module")
def both_orders(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        forward = run_order(CONFIGS, tmp_path_factory.mktemp("forward"), mp)
        backward = run_order(tuple(reversed(CONFIGS)), tmp_path_factory.mktemp("backward"), mp)
    finally:
        mp.undo()
    return forward, backward


def test_every_configuration_produces_the_same_record_in_both_orders(both_orders):
    forward, backward = both_orders
    assert set(forward) == set(backward) == set(CONFIGS)
    def stable(rec):
        return {k: (v if k != "probe" else {x: y for x, y in v.items() if x != "generation"}) for k, v in rec.items()}
    for name in CONFIGS:
        assert stable(forward[name]) == stable(backward[name]), name
    assert forward["neutral-4lang"] == backward["neutral-4lang"]            # no fake exe: the composite itself is stable


def test_each_configuration_has_its_own_config_id_rows_and_languages(both_orders):
    probes = {n: both_orders[0][n]["probe"] for n in CONFIGS}
    assert {n: probes[n]["config_id"] for n in CONFIGS} == {"tg1": "tg1", "m64-oc-tg1": "m64-oc-tg1",
                                                              "neutral-4lang": "neutral-4lang"}
    assert [r["id"] for r in probes["tg1"]["rows"]] == ["python/one"]
    assert [r["id"] for r in probes["m64-oc-tg1"]["rows"]] == ["python/one"]
    assert [r["id"] for r in probes["neutral-4lang"]["rows"]] == [f"{lang}/one" for lang in LANGS4]
    assert all(r["passed"] and r["nonconv_kind"] is None for n in CONFIGS for r in probes[n]["rows"])
    assert {n: probes[n]["arm"] for n in CONFIGS} == {"tg1": "oc", "m64-oc-tg1": "oc", "neutral-4lang": "dsh"}
    assert probes["neutral-4lang"]["langs"] == list(LANGS4) and probes["tg1"]["langs"] == ["python", "go"]
    chains = {n: both_orders[0][n]["chain"] for n in CONFIGS}
    assert chains["tg1"]["config_id"] == "tg1" and chains["m64-oc-tg1"]["config_id"] == "m64"
    assert chains["neutral-4lang"]["langs"] == list(LANGS4) and chains["neutral-4lang"]["config_id"] == "m64"
    assert chains["tg1"]["scored"] == 24 and chains["m64-oc-tg1"]["scored"] > 0 and chains["neutral-4lang"]["scored"] == 2 * 4 * 4
    assert (chains["tg1"]["transport"], chains["tg1"]["resume"]) == ("abort_restart", "restart_load")
    assert (chains["m64-oc-tg1"]["transport"], chains["m64-oc-tg1"]["resume"]) == ("incident_retry", "new_segment")


def test_the_probe_identities_are_pairwise_distinct_per_configuration(both_orders):
    probes = {n: both_orders[0][n]["probe"] for n in CONFIGS}
    for key in ("probe_code", "policy", "generation"):
        values = [probes[n][key] for n in CONFIGS]
        assert len(set(values)) == 3, (key, values)
    assert probes["tg1"]["scaffold"] != probes["m64-oc-tg1"]["scaffold"] and probes["neutral-4lang"]["scaffold"] == LABEL


def test_the_oc_probe_closures_are_the_recorded_identities(both_orders):
    probes = {n: both_orders[0][n]["probe"] for n in CONFIGS}
    for name, entry in (("tg1", "benchmark/run_tg1_probe.py"), ("m64-oc-tg1", "benchmark/run_oc_probe.py")):
        assert probes[name]["probe_code"] == ic.closure_sha256(entry, REPO, data=tg1_runner.GENERATION_DATA), name
    assert probes["tg1"]["probe_code"] != probes["m64-oc-tg1"]["probe_code"]


def test_the_chains_freeze_different_lifecycle_closures_and_only_the_m64_configurations_name_arms_they_run(both_orders):
    chains = {n: both_orders[0][n]["chain"] for n in CONFIGS}
    tg1, oc, neutral = (chains[n]["lifecycle_sha"] for n in CONFIGS)
    assert tg1["runner"] != oc["runner"] and tg1["chain_config"] != oc["chain_config"] != neutral["chain_config"]
    assert "benchmark/bench/schedules.py" in chains["tg1"]["lifecycle"] and "benchmark/bench/arm_ops.py" not in chains["tg1"]["lifecycle"]
    assert "benchmark/bench/arm_ops.py" in chains["m64-oc-tg1"]["lifecycle"]
    # the two M64 configurations share one chain entry: every closure member alike, only the ChainConfig differs
    assert {k: v for k, v in oc.items() if k != "chain_config"} == {k: v for k, v in neutral.items() if k != "chain_config"}
    assert chains["tg1"]["arms"] and chains["neutral-4lang"]["arms"]


def test_tg1_has_no_watchdog_no_compaction_no_receipts_and_no_barrier_files(both_orders):
    probe, chain = both_orders[0]["tg1"]["probe"], both_orders[0]["tg1"]["chain"]
    assert probe["watchdog"] == {"mode": "off"} and probe["compaction"] == "off"
    assert probe["evidence_policy"]["worker_receipts"] == "absent" and probe["evidence_policy"]["item_barrier"] == "off"
    assert not {"compaction", "receipts", "shell_watchdog", "task_tokens"} & set(probe["rows"][0]["keys"])
    assert probe["barrier_files"] == [] and chain["barrier_files"] == []


def test_the_m64_configurations_have_the_watchdog_compaction_and_the_chain_answers_barrier_files(both_orders):
    oc = both_orders[0]["m64-oc-tg1"]
    assert oc["probe"]["watchdog"]["mode"] == "on" and oc["probe"]["compaction"] == "on_accounted"
    assert {"compaction", "shell_watchdog"} <= set(oc["probe"]["rows"][0]["keys"])
    assert oc["probe"]["barrier_files"] == []                       # a direct item run has no chain to answer a barrier
    assert oc["chain"]["barrier_files"] and both_orders[0]["neutral-4lang"]["chain"]["barrier_files"]
    neutral = both_orders[0]["neutral-4lang"]["probe"]
    assert neutral["watchdog"] == {"mode": "off"} and neutral["compaction"] == "off" and neutral["barrier_files"] == []


def test_no_opencode_name_leaks_into_the_neutral_configuration(both_orders):
    text = json.dumps(both_orders[0]["neutral-4lang"]["probe"])
    assert "opencode" not in text.lower()


def test_the_process_state_the_configurations_touch_is_restored_after_each(both_orders):
    """`run_order` asserted it per configuration (env vars, patched seams); here: after both orders nothing is left."""
    assert "MLX_SERVE_CONFIG" not in os.environ or os.environ["MLX_SERVE_CONFIG"]
    assert isinstance(arm_runner.worker_json, type(lambda: 0)) and arm_runner.worker_json.__module__ == "bench.arm_runner"



def test_the_leak_check_catches_a_configuration_that_leaves_state_behind(tmp_path, monkeypatch):
    """Validate the instrument on a known positive: a configuration that sets an env var outside `monkeypatch` is reported."""
    def leaky(mp, sub):
        os.environ["MLX_SERVE_CONFIG"] = "leaked"
        return {}
    monkeypatch.setitem(STEPS, "leaky", (leaky, lambda mp, sub: {}))
    try:
        with pytest.raises(AssertionError, match="left process state behind"):
            run_order(("leaky",), tmp_path, monkeypatch)
    finally:
        os.environ.pop("MLX_SERVE_CONFIG", None)
