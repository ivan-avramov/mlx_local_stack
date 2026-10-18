"""P371 phase 4 (C179 / P377, plan 5 "Campaign freeze"): `--campaign-core <tag>` on the M64 chain entry. The campaign core of a
multi-arm chain is ONE closure per arm probe entry plus the chain entry's closure: `campaign_core` takes several probe
entries (`probes={arm: {entry, data}}`), the M64 entry builds them from the arm specs, records the result under
`chain.json.artifacts.campaign_core`, refuses at creation unless the closures at the tag equal the current ones and
re-verifies at every launch, barrier, resume and exit (same semantics as tg1). Real `git` over a throw-away repository for the
closure arithmetic; the fake arm probe and fake ChainOps for the chain."""
from __future__ import annotations

import pytest

from bench import arm_opencode as ao
from bench import arm_specs
from bench import campaign_core as cc
from bench import identity_closure as ic
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    M, PICK2, REPO, SMOKE, SMOKE3, calls, chain_json, env, invocations, log_has, run)
from bench.tests.test_p371_campaign_core import git

PROBES = dict(oc=dict(entry="benchmark/probe_oc.py", data=("benchmark/data_oc.json",)),
              pi=dict(entry="benchmark/probe_pi.py", data=()))
SPECS = dict(probes=PROBES, chain_entry="benchmark/chains/chain_entry.py", chain_data=())


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    for rel, text in {
            "benchmark/bench/__init__.py": "",
            "benchmark/bench/core.py": "VALUE = 1\n",
            "benchmark/bench/oc_only.py": "X = 1\n",
            "benchmark/bench/pi_only.py": "Y = 1\n",
            "benchmark/bench/chain.py": "from bench import core\n",
            "benchmark/probe_oc.py": "from bench import core\nfrom bench import oc_only\n",
            "benchmark/probe_pi.py": "from bench import core\nfrom bench import pi_only\n",
            "benchmark/chains/chain_entry.py": "from bench import chain\n",
            "benchmark/data_oc.json": "{}\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "core")
    git(root, "tag", "campaign-1")
    return root


# ---------------------------------------------------------------- campaign_core with several probe entries
def test_one_closure_per_arm_probe_and_the_chain_entry(repo):
    now = cc.closure_shas(repo, **SPECS)
    assert set(now) == {"probe_closures", "probe_closure_sha256", "chain_closure_sha256"}
    assert set(now["probe_closures"]) == {"oc", "pi"} and now["probe_closures"]["oc"] != now["probe_closures"]["pi"]
    assert now["probe_closures"]["oc"] == ic.closure_sha256("benchmark/probe_oc.py", repo, data=("benchmark/data_oc.json",))
    assert now["probe_closures"]["pi"] == ic.closure_sha256("benchmark/probe_pi.py", repo)
    at = cc.at_ref("campaign-1", repo, **SPECS)
    assert set(at) == {"tag", "commit", "probe_closures", "probe_closure_sha256", "chain_closure_sha256"}
    cc.require_equal(at, now)                                          # match: no exception


def test_the_single_probe_form_is_unchanged(repo):
    single = dict(probe_entry="benchmark/probe_oc.py", probe_data=("benchmark/data_oc.json",),
                  chain_entry="benchmark/chains/chain_entry.py")
    assert set(cc.closure_shas(repo, **single)) == {"probe_closure_sha256", "chain_closure_sha256"}


def test_a_member_of_one_arms_probe_closure_changed_refuses_and_names_that_arm_and_file(repo):
    (repo / "benchmark/bench/oc_only.py").write_text("X = 2\n")
    at, now = cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS)
    assert at["probe_closures"]["oc"] != now["probe_closures"]["oc"] and at["probe_closures"]["pi"] == now["probe_closures"]["pi"]
    with pytest.raises(cc.CampaignCoreMismatch, match=r"probe\[oc\]") as exc:
        cc.require_equal(at, now, repo=repo, **SPECS)
    assert "oc_only.py" in str(exc.value) and "probe[pi]" not in str(exc.value)


def test_a_shared_core_member_changed_moves_every_arms_closure_and_the_chain_closure(repo):
    (repo / "benchmark/bench/core.py").write_text("VALUE = 2\n")
    at, now = cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS)
    assert all(at["probe_closures"][a] != now["probe_closures"][a] for a in ("oc", "pi"))
    with pytest.raises(cc.CampaignCoreMismatch, match=r"probe\[oc\].*probe\[pi\]|probe\[pi\].*probe\[oc\]"):
        cc.require_equal(at, now)


def test_an_arm_data_file_is_part_of_that_arms_closure_only(repo):
    (repo / "benchmark/data_oc.json").write_text('{"x": 1}\n')
    at, now = cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS)
    assert at["probe_closures"]["oc"] != now["probe_closures"]["oc"] and at["probe_closures"]["pi"] == now["probe_closures"]["pi"]


def test_the_chain_closure_alone_changed_refuses(repo):
    (repo / "benchmark/bench/chain.py").write_text("from bench import core\nZ = 1\n")
    at, now = cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS)
    assert at["probe_closures"] == now["probe_closures"]
    with pytest.raises(cc.CampaignCoreMismatch, match="chain"):
        cc.require_equal(at, now)


def test_an_arm_added_or_dropped_since_the_tag_is_a_mismatch(repo):
    at = cc.at_ref("campaign-1", repo, **SPECS)
    fewer = cc.closure_shas(repo, probes={"oc": PROBES["oc"]}, chain_entry=SPECS["chain_entry"])
    with pytest.raises(cc.CampaignCoreMismatch):
        cc.require_equal(at, fewer)


# ---------------------------------------------------------------- the M64 entry
def test_the_m64_entry_takes_the_flag_and_validates_it():
    assert M.parse_args(SMOKE + ["--campaign-core", "v1"]).campaign_core == "v1"
    assert M.parse_args(SMOKE).campaign_core is None
    with pytest.raises(SystemExit):
        M.parse_args(SMOKE + ["--campaign-core", " "])


def test_the_m64_core_specs_follow_the_probe_identity_recipe_per_arm_and_the_entry_closure():
    specs = M.core_specs(["oc"])
    assert set(specs["probes"]) == {"oc"} and specs["probes"]["oc"]["entry"] == arm_specs.spec_for("oc").probe
    assert tuple(specs["probes"]["oc"]["data"]) == tuple(ao.GENERATION_DATA) == tuple(arm_specs.spec_for("oc").generation_data)
    now = cc.closure_shas(REPO, **specs)
    assert now["probe_closures"]["oc"] == ic.closure_sha256("benchmark/run_oc_probe.py", REPO, data=ao.GENERATION_DATA)
    assert specs["chain_entry"] == "benchmark/chains/m64/run_m64_chain.py"
    assert {"benchmark/bench/chain_core.py", "benchmark/bench/campaign_core.py"} <= set(
        cc.members(REPO, specs["chain_entry"], specs["chain_data"]))


class FakeCampaign:
    """`at_ref` / `current` / `require_equal` with the multi-probe record, with shas the test controls."""

    def __init__(self, arms=("oc",), at_over=None):
        self.cc = cc
        self.now = dict(probe_closures={a: f"{i}" * 64 for i, a in enumerate(arms, 1)}, chain_closure_sha256="b" * 64)
        self.now["probe_closure_sha256"] = "a" * 64
        self.at = dict(tag="campaign-1", commit="c" * 40, **self.now)
        self.at.update(at_over or {})
        self.refs = []

    def at_ref(self, ref):
        self.refs.append(ref)
        if ref != self.at["tag"]:
            raise cc.CampaignError(f"--campaign-core {ref!r} does not resolve to a commit in this repository")
        return dict(self.at)

    def current(self):
        return dict(self.now)

    def require_equal(self, recorded, now):
        cc.require_equal(recorded, now)


FLAG = ["--campaign-core", "campaign-1"]


def test_a_matching_campaign_core_is_recorded_under_the_chain_artifacts_and_the_chain_runs(env):
    cam = FakeCampaign()
    assert run(env, SMOKE + FLAG, campaign=cam) == 0
    assert chain_json(env)["artifacts"]["campaign_core"] == cam.at and cam.refs == ["campaign-1"]
    assert log_has(env, "campaign core campaign-1")


def test_the_m64_entry_builds_the_real_campaign_helper_from_the_arms_specs_when_none_is_injected(env, monkeypatch):
    seen = {}

    class Spy:
        def __init__(self, repo, **specs):
            seen.update(repo=repo, specs=specs)

        def at_ref(self, ref):
            raise cc.CampaignError("spy: stop here")

    monkeypatch.setattr(M.campaign_core, "Campaign", Spy)
    assert run(env, SMOKE + FLAG) == 2
    assert set(seen["specs"]["probes"]) == {"oc"} and seen["specs"]["chain_entry"] == "benchmark/chains/m64/run_m64_chain.py"
    assert seen["specs"]["probes"]["oc"]["entry"] == "benchmark/chains/m64/fake_arm_probe.py"       # F7: the resolved entry (`run` passes --probe oc=)


def test_without_the_flag_nothing_is_recorded_and_nothing_is_computed(env):
    assert run(env, SMOKE, campaign=FakeCampaign()) == 0
    assert chain_json(env)["artifacts"]["campaign_core"] is None


def test_a_changed_arm_probe_closure_member_refuses_before_anything_is_written(env):
    cam = FakeCampaign(arms=("oc", "pi"), at_over=dict(probe_closures={"oc": "0" * 64, "pi": "2" * 64}))
    assert run(env, SMOKE3 + FLAG, campaign=cam) == 2
    assert log_has(env, "campaign core drift") and log_has(env, "probe[oc]") and not log_has(env, "probe[pi]")
    assert invocations(env) == [] and not (env["out"] / "chain.json").exists() and not calls(env, "start_router")


def test_a_changed_chain_closure_refuses(env):
    cam = FakeCampaign(at_over=dict(chain_closure_sha256="0" * 64))
    assert run(env, SMOKE + FLAG, campaign=cam) == 2 and log_has(env, "campaign core drift") and invocations(env) == []


def test_an_unresolvable_ref_refuses(env):
    assert run(env, SMOKE + ["--campaign-core", "missing"], campaign=FakeCampaign()) == 2
    assert log_has(env, "does not resolve") and invocations(env) == []


def test_drift_mid_chain_aborts_rc_2_before_the_next_launch(env):
    cam = FakeCampaign()
    ops = env["ops"]
    original = ops.a4_gate

    def gate(model, tag, scaffold=None):
        if model == PICK2:
            cam.now = dict(cam.now, probe_closures={"oc": "9" * 64})
        return original(model, tag, scaffold)
    ops.a4_gate = gate
    assert run(env, SMOKE + FLAG, campaign=cam) == 2
    assert log_has(env, "campaign core drift") and log_has(env, "probe[oc]")
    assert len(invocations(env)) < 8


def test_drift_at_exit_aborts(env):
    cam = FakeCampaign()
    ops = env["ops"]
    ops.on_unload = lambda: cam.__dict__.update(now=dict(cam.now, chain_closure_sha256="8" * 64)) \
        if len(ops.names("unload")) >= 2 else None
    assert run(env, SMOKE + FLAG, campaign=cam) == 2 and log_has(env, "campaign core drift") and log_has(env, "exit")


def test_a_resume_keeps_enforcing_the_recorded_core_without_the_flag_and_refuses_another_ref(env):
    cam = FakeCampaign()
    assert run(env, SMOKE + FLAG, campaign=cam) == 0
    launched = len(invocations(env))
    cam.now = dict(cam.now, probe_closures={"oc": "7" * 64})
    assert run(env, SMOKE, campaign=cam) == 2 and log_has(env, "campaign core drift") and len(invocations(env)) == launched
    other = FakeCampaign(at_over=dict(tag="campaign-2"))
    assert run(env, SMOKE + ["--campaign-core", "campaign-2"], campaign=other) == 2 and log_has(env, "campaign")


def test_a_real_git_closure_drift_in_one_arms_probe_refuses_the_m64_chain(env, tmp_path):
    """End to end with the real helper over a throw-away repository: a tagged core, then one arm's probe closure member
    edited in the working tree."""
    root = tmp_path / "r"
    for rel, text in {"benchmark/bench/__init__.py": "", "benchmark/bench/core.py": "V = 1\n", "benchmark/bench/oc_only.py": "X = 1\n",
                      "benchmark/probe_oc.py": "from bench import core\nfrom bench import oc_only\n",
                      "benchmark/chains/chain_entry.py": "from bench import core\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "core")
    git(root, "tag", "campaign-1")
    specs = dict(probes={"oc": dict(entry="benchmark/probe_oc.py", data=())}, chain_entry="benchmark/chains/chain_entry.py",
                 chain_data=())
    assert run(env, SMOKE + FLAG, campaign=cc.Campaign(root, **specs)) == 0         # equal: runs to the end
    assert chain_json(env)["artifacts"]["campaign_core"]["tag"] == "campaign-1"
    env2 = dict(env, out=tmp_path / "second", lines=[])
    (root / "benchmark/bench/oc_only.py").write_text("X = 2\n")
    assert run(env2, SMOKE + FLAG, campaign=cc.Campaign(root, **specs)) == 2
    assert any("probe[oc]" in ln and "oc_only.py" in ln for ln in env2["lines"])
