"""M76 B3: the pair verifier B8 under `lever=kv` (Wave 1 + A5) on a synthetic world: a git repo whose two commits carry the REAL
N16 and X registries, the harvested KV record, `m76/ids.json`, and the legs' receipts / rows / manifests. A pair is accepted only
when the KV deltas hold and everything else is equal; rejections name the rule."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bench import m76_ids as M
from bench import p426_ids
from bench import p426_plan as P
from bench import p426_verify as V

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
ENGAGED = dict(draft_kind="mtp", draft_rounds=5, draft_n=10, draft_n_accepted=7)
GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}


_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m76_b3_fe"
_FIXTURE_ARM = {"89205085": "n16", "origin/m76-f45-x": "x", "origin/m76-f45-v": "v", "origin/m76-f45-xo": "xo"}


def _show(ref):
    """The arm's committed registry: the sha256-pinned fixture copy (`fixtures/m76_b3_fe/`, checked against its source revision by
    `test_m76_b3_registry_fixtures_pinned.py`) — so the test runs on any clone, not only where the local `m76-f45-*` branches exist
    (S23-P93); any other ref / path from git."""
    arm = _FIXTURE_ARM.get(ref)
    if arm and "main_models.yaml" == "main_models.yaml":
        data = (_FIXTURES / f"{arm}_main_models.yaml").read_bytes()
        return data
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{"main_models.yaml"}"], capture_output=True)
    if r.returncode:
        pytest.skip(f"{ref} is not in this repository's objects")
    data = r.stdout
    return data


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV).stdout.strip()


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


class World:
    def __init__(self, tmp, monkeypatch, kinds=("cjudge", "longctx"), sizes=None):
        self.repo, self.rows = tmp / "repo", tmp / "results"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        self.text = {"n16": _show("89205085"), "x": _show("origin/m76-f45-x")}
        self.head = {}
        for arm in ("n16", "x"):
            (self.repo / "main_models.yaml").write_bytes(self.text[arm])
            git(self.repo, "add", "main_models.yaml")
            git(self.repo, "commit", "-q", "-m", arm)
            self.head[arm] = git(self.repo, "rev-parse", "HEAD")
        monkeypatch.setattr("bench.generate.results_root", lambda: str(self.rows))
        p = p426_ids.build(REPO)["axes"]["math500"]
        universe = p["block1"] + p["block2"] + [f"test/s/{i:03d}.json" for i in range(400)]
        from bench.tests.test_m76_b3_impl_lever import build_ids

        self.ids = build_ids(universe=universe, sizes=sizes)
        self.budget = self.ids["axes"]["longctx"]["budget"]
        self._write(self.rows / "m76" / "ids.json", json.dumps(self.ids))
        venvs = {v: {p_: "0.32.4" if p_ in ("mlx", "mlx-metal") else "1" for p_ in P.VENV_PACKAGES} for v in P.VENVS}
        self.frozen = dict(build="s3", lever="kv", arms=["n16", "x"], uv_lock_sha256="a" * 64, bench_lock_sha256="b" * 64,
                           venvs={a: venvs for a in ("n16", "x")},
                           **{k: P.EXPECTED_BUILDS["s3"][k] for k in ("mlx_vlm", "mlx_serve", "production_ref")},
                           **{f"stack_head_{a}": self.head[a] for a in ("n16", "x")},
                           **{f"stack_clean_{a}": True for a in ("n16", "x")},
                           **{f"registry_{a}_sha": sha(self.text[a]) for a in ("n16", "x")})
        fb = json.dumps(self.frozen).encode()
        self._write(self.rows / "m76" / "wave1" / "run" / "frozen.s3.json", fb)
        self.frozen_sha = sha(fb)
        for kind in kinds:
            for label in ("b1", "b2"):
                for arm in ("n16", "x"):
                    self.leg(kind, arm, label)

    def _write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())

    def argv(self, arm):
        from bench.tests.test_m76_b3_impl_lever import worker_argv

        return worker_argv(arm, wt=f"$STACK_WORKDIR/worktrees/m76-f45-{arm}")

    def manifest(self, arm):
        """A manifest of `provenance.gather`'s shape: the arms differ only in the KV / mode fields, the arm commit, the
        tune key and the volatile router / timestamp."""
        return dict(model=ENTRY, box="box-1", fingerprint_version=9, sampling_profile="deployed", timestamp=100 + len(arm),
                    tune=f"m76-{arm}-b1", sampling=dict(temperature=0.5, top_p=0.95, max_tokens=102400, thinking_budget=81920),
                    registry=dict(sha256=sha(self.text[arm])), router=dict(pid=1000 + len(arm), config=f"/wt/{arm}"),
                    git=dict(stack_head=self.head[arm], submodules={"src/mlx-vlm": "v" * 40},
                             serving_path={"src/mlx-vlm": "t" * 40, "src/mlx-serve": "u" * 40}),
                    quant=dict(effective_bits=4.5),
                    runtime=dict(apc_enabled=False, draft_kind="mtp", mtp_verify_scan="joint_v1",
                                 tq4_attention="off" if arm == "n16" else "m72_exact", session_retain_prompt_end=True),
                    kv=dict(kv_bits=0 if arm == "n16" else 4, kv_quant_scheme="uniform" if arm == "n16" else "turboquant",
                            max_kv_cache_size=262144, prefill_step_size=4096, hf_path="caslca/x"))

    def leg(self, kind, arm, label, *, row_hook=None, argv=None, manifest_hook=None):
        leg, tune = V.kv_leg_of(kind, arm, label), V.kv_tune_of(arm, label, kind)
        receipt = dict(verdict="VALID", problems=[], name=leg, arm=arm, kind=kind, speed_valid=True, speed_problems=[],
                       pins=dict(self.frozen, frozen_sha=self.frozen_sha),
                       state=dict(stack_head=self.head[arm], frozen_sha=self.frozen_sha),
                       worker=dict(cmdline="202 " + " ".join(argv or self.argv(arm)).replace('", "', '","')), log={})
        ldir = self.rows / "m76" / "wave1" / leg
        self._write(ldir / f"{leg}.receipt.json", json.dumps(receipt))
        self._write(ldir / "SCRUB_MANIFEST.json", json.dumps(dict(leg=leg, files={})))
        edir = self.rows / ENTRY
        if kind == "cjudge":
            rows = []
            for i in self.ids["axes"]["cjudge"][f"block{label[-1]}"]:
                content = f"answer {i}"
                row = dict(id=i, sampler_seed=7, content=content, content_sha256=sha(content), thinking_budget=81920, draft=ENGAGED,
                           decode_tps=30.0 if arm == "n16" else 25.0)
                rows.append(row_hook(row) if row_hook else row)
            self._write(edir / f"cjudge.{tune}.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
            self._write(edir / f"cjudge.{tune}.manifest.json", json.dumps(self.manifest(arm)))
        else:
            lc = self.ids["axes"]["longctx"]
            by = {i["id"]: i for i in lc["items"]}
            for iid in (lc["tier2"] if label.startswith("t2-") else lc)[f"block{label[-1]}"]:
                item = by[iid]
                row = dict(trial=0, seed=item["task_seed"], sampler_seed=lc["sampler_seeds"][iid], content=f"codes {iid}",
                           prompt_tokens=self.budget[iid]["prompt_tokens"], finish_reason="stop", draft=ENGAGED,
                           completion_tokens=100, hits=[True] * 5, score=1.0, budget_hit=False)
                row = row_hook(row) if row_hook else row
                stem = f"{'retrieval' if item['task'] == 'retrieval' else 'reasoning'}.{tune}.{iid}"
                self._write(edir / f"{stem}.json", json.dumps(dict(records=[dict(ctx=item["rung"], rows=[row])])))
                self._write(edir / f"{stem}.manifest.json", json.dumps(manifest_hook(self.manifest(arm), iid)
                                                                      if manifest_hook else self.manifest(arm)))
        return leg

    def verify(self, kinds=("cjudge", "longctx")):
        return V.verify_wave1_kv(self.rows, self.repo, ("n16", "x"), kinds=kinds)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def test_a_clean_kv_world_is_accepted(world):
    b8 = world.verify()
    assert b8["lever"] == "kv" and b8["label"] == "X − N16" and b8["pair"] == ["n16", "x"]
    got = {(p["kind"], p["block"]): p for p in b8["pairs"]}
    assert set(got) == {("cjudge", "b1"), ("cjudge", "b2"), ("longctx", "b1"), ("longctx", "b2")}
    for p in got.values():
        assert p["accepted"], p["reasons"]
        assert p["legs"] == {"n16": V.kv_leg_of(p["kind"], "n16", p["block"]), "x": V.kv_leg_of(p["kind"], "x", p["block"])}
        assert not p["keys_rejected"]
    assert got[("longctx", "b1")]["axis"] == "A5" and got[("longctx", "b1")]["keys_accepted"] == len(world.ids["axes"]["longctx"]["block1"])
    assert all(not k.startswith("p426") for k in b8["inputs"])


def test_argv_beyond_the_kv_flags_is_rejected(world):
    argv = world.argv("x")
    argv[argv.index("--prefill-step-size") + 1] = "2048"
    world.leg("cjudge", "x", "b1", argv=argv)
    got = {(p["kind"], p["block"]): p for p in world.verify()["pairs"]}
    assert not got[("cjudge", "b1")]["accepted"] and any("rule 2c" in r and "beyond" in r for r in got[("cjudge", "b1")]["reasons"])
    assert got[("cjudge", "b2")]["accepted"]


def test_an_arm_without_the_tq4_flags_is_rejected(world):
    world.leg("cjudge", "x", "b2", argv=world.argv("n16"))
    p = {(p["kind"], p["block"]): p for p in world.verify()["pairs"]}[("cjudge", "b2")]
    assert not p["accepted"] and any("--kv-bits" in r for r in p["reasons"])


def test_unengaged_rows_are_rejected_on_either_arm(world):
    world.leg("cjudge", "n16", "b1", row_hook=lambda r: dict(r, draft=None))
    p = {(p["kind"], p["block"]): p for p in world.verify()["pairs"]}[("cjudge", "b1")]
    assert not p["accepted"] and any("not engaged" in r for r in p["reasons"])


def test_a5_seed_mismatch_rejects_the_key(world):
    world.leg("longctx", "x", "b2", row_hook=lambda r: dict(r, sampler_seed=r["sampler_seed"] + 1))
    p = {(p["kind"], p["block"]): p for p in world.verify()["pairs"]}[("longctx", "b2")]
    assert p["keys_rejected"] and all("seed mismatch" in k["reason"] for k in p["keys_rejected"])


def test_a_sampling_difference_is_rejected(world, monkeypatch):
    orig = world.manifest

    def manifest(arm):
        m = orig(arm)
        if arm == "x":
            m["sampling"]["temperature"] = 0.6
        return m
    monkeypatch.setattr(world, "manifest", manifest)
    world.leg("cjudge", "x", "b1")
    p = {(p["kind"], p["block"]): p for p in world.verify()["pairs"]}[("cjudge", "b1")]
    assert not p["accepted"] and any("sampling.temperature differs" in r for r in p["reasons"])


def test_the_kv_record_must_be_the_pairs(world):
    rec = dict(world.frozen, lever="mtp")
    (world.rows / "m76" / "wave1" / "run" / "frozen.s3.json").write_text(json.dumps(rec))
    with pytest.raises(V.RefusalError, match="KV record"):
        world.verify()


def test_math500_tier2_is_not_run_when_absent(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, kinds=())
    b8 = V.verify_wave1_kv(w.rows, w.repo, ("n16", "x"), kinds=())
    assert b8["pairs"] == [] and b8["not_run"] == []
    with pytest.raises(V.RefusalError, match="missing"):
        V.verify_wave1_kv(w.rows, w.repo, ("n16", "x"), kinds=("math500",))


def test_p426_named_members_are_deny_listed(world):
    assert V._kv_member(world.rows, world.rows / "m76" / "wave1" / "run" / "frozen.s3.json", "w")      # allowed
    p426 = world.rows / "p426" / "x.json"
    p426.parent.mkdir(parents=True)
    p426.write_text("{}")
    with pytest.raises(V.RefusalError, match="deny-listed"):
        V._kv_member(world.rows, p426, "w")


def test_cli_kv_refusals(world, tmp_path, capsys):
    out = tmp_path / "B8.json"
    assert V.main(["all", "--results-root", str(world.rows / "m76"), "--rows-root", str(world.rows), "--repo", str(world.repo),
                   "--out", str(out), "--lever", "kv"]) == 2
    assert V.main(["all", "--results-root", str(world.rows / "m76"), "--rows-root", str(world.rows), "--repo", str(world.repo),
                   "--out", str(out), "--lever", "kv", "--pair", "x,n16"]) == 2
    assert V.main(["all", "--results-root", str(world.rows / "p426"), "--rows-root", str(world.rows), "--repo", str(world.repo),
                   "--out", str(out), "--pair", "n16,x"]) == 2
    assert not out.exists()


# ------------------------------------------------------------------------------------------------- fix round 1 (spec v1.2)
def _pair(world, kind, label, kinds=("cjudge", "longctx")):
    return {(p["kind"], p["block"]): p for p in world.verify(kinds)["pairs"]}[(kind, label)]


def test_any_rejected_key_rejects_the_pair(world):
    """v1.2 B8 completeness: a seed-mismatched A5 row no longer leaves its pair accepted on fewer items."""
    first = world.ids["axes"]["longctx"]["block2"][0]
    world.leg("longctx", "x", "b2", row_hook=lambda r: dict(r, sampler_seed=r["sampler_seed"] + 1)
              if r["content"] == f"codes {first}" else r)
    p = _pair(world, "longctx", "b2")
    assert len(p["keys_rejected"]) == 1 and p["accepted"] is False
    assert any(r.startswith("rule 3") and "incomplete" in r for r in p["reasons"])


def test_a5_rows_must_carry_the_frozen_prompt_count(world):
    """v1.2 A5 budgets: a row whose prompt token count differs from the planner's frozen count is a rejected key."""
    world.leg("longctx", "n16", "b1", row_hook=lambda r: dict(r, prompt_tokens=r["prompt_tokens"] + 1))
    p = _pair(world, "longctx", "b1")
    assert p["accepted"] is False
    assert p["keys_rejected"] and all("prompt_tokens" in k["reason"] for k in p["keys_rejected"])


def test_a5_rows_resolved_budget_must_be_the_frozen_one(world):
    """Both arms served another max_tokens (equal between them): the rows' own resolved budget != the frozen one."""
    def lower(m, iid):
        m["sampling"]["max_tokens"] = 90000
        return m
    for arm in ("n16", "x"):
        world.leg("longctx", arm, "b1", manifest_hook=lower)
    p = _pair(world, "longctx", "b1")
    lc = world.ids["axes"]["longctx"]
    capped = [i for i in lc["block1"] if world.budget[i]["resolved_max_tokens"] > 90000]
    assert capped and p["accepted"] is False
    assert {k["key"][1] for k in p["keys_rejected"]} >= set(capped)
    assert all("resolved" in k["reason"] for k in p["keys_rejected"])


def test_the_resolved_budget_of_the_196608_rung_is_the_prompts_own(world):
    lc = world.ids["axes"]["longctx"]
    for item in [i for i in lc["items"] if i["rung"] == 196608]:
        cell = world.budget[item["id"]]
        assert cell["resolved_max_tokens"] == 262144 - cell["prompt_tokens"]      # not a planner constant (65,024)
    assert _pair(world, "longctx", "b1")["accepted"] and _pair(world, "longctx", "b2")["accepted"]


@pytest.mark.parametrize("path,value", [(("runtime", "apc_enabled"), True), (("runtime", "session_retain_prompt_end"), False),
                                        (("git", "serving_path", "src/mlx-vlm"), "w" * 40), (("fingerprint_version",), 8),
                                        (("sampling_profile",), "production"), (("box",), "box-2"),
                                        (("kv", "prefill_step_size"), 2048)])
def test_provenance_outside_the_kv_whitelist_rejects(world, monkeypatch, path, value):
    """v1.2: the complete normalized provenance is compared; only the KV / mode keys and the arm commit may differ."""
    orig = world.manifest

    def manifest(arm):
        m = orig(arm)
        if arm == "x":
            d = m
            for k in path[:-1]:
                d = d[k]
            d[path[-1]] = value
        return m
    monkeypatch.setattr(world, "manifest", manifest)
    world.leg("cjudge", "x", "b1")
    p = _pair(world, "cjudge", "b1")
    assert p["accepted"] is False and any("provenance" in r and ".".join(path) in r for r in p["reasons"])


def test_the_whitelisted_differences_are_accepted(world):
    m = {a: world.manifest(a) for a in ("n16", "x")}
    assert m["n16"]["kv"]["kv_bits"] != m["x"]["kv"]["kv_bits"] and m["n16"]["git"]["stack_head"] != m["x"]["git"]["stack_head"]
    assert V.kv_provenance_problems(m["n16"], m["x"], "n16", "x") == []
    assert _pair(world, "cjudge", "b1")["accepted"]


def test_verify_takes_a_top_level_lever(world, tmp_path, capsys):
    out = tmp_path / "B8.json"
    with pytest.raises(SystemExit):
        V.main(["--lever", "bogus", "all"])
    err = capsys.readouterr().err
    assert "argument --lever: invalid choice" in err and "mtp" in err and "kv" in err
    assert V.main(["--lever", "kv", "a7", "--results-root", str(world.rows / "m76"), "--out", str(out)]) == 2
    assert "all --pair" in capsys.readouterr().err
    # the top-level flag reaches the KV verifier (this world has no Math500 legs: B8 refuses on them, not on the flag)
    assert V.main(["--lever", "kv", "all", "--results-root", str(world.rows / "m76"), "--rows-root", str(world.rows),
                   "--repo", str(world.repo), "--out", str(out), "--pair", "n16,x"]) == 2
    err = capsys.readouterr().err
    assert "math500" in err and "lever kv flag" not in err


# ------------------------------------------------------------------------------------------- A5 tier 2 (spec v1.4)
@pytest.fixture
def world2(tmp_path, monkeypatch):
    """A world whose ids hold A5 tiers 42 / 54 (a two-look plan's sizes)."""
    return World(tmp_path, monkeypatch, sizes=(42, 54))


def test_a5_tier2_legs_are_verified_as_their_own_pairs(world2):
    lc = world2.ids["axes"]["longctx"]
    rec = world2.verify()
    assert {"longctx/t2-b1", "longctx/t2-b2"} <= set(rec["not_run"])        # not run yet: not_run, never refused
    for label in V.KV_TIER2:
        for arm in ("n16", "x"):
            world2.leg("longctx", arm, label)
    got = {(p["kind"], p["block"]): p for p in world2.verify()["pairs"]}
    for label in V.KV_TIER2:
        p = got[("longctx", label)]
        assert p["accepted"], p["reasons"]
        assert p["tier"] == 2 and p["axis"] == "A5"
        assert p["tunes"] == {"n16": f"m76-n16-lc-{label}", "x": f"m76-x-lc-{label}"}
        assert sorted(k["key"][1] for k in p["keys"]) == sorted(lc["tier2"][f"block{label[-1]}"])
    first = lc["tier2"]["block1"][0]
    world2.leg("longctx", "x", "t2-b1", row_hook=lambda r: dict(r, sampler_seed=r["sampler_seed"] + 1)
               if r["content"].endswith(first) else r)
    p = {(p["kind"], p["block"]): p for p in world2.verify()["pairs"]}[("longctx", "t2-b1")]
    assert not p["accepted"] and [k["key"][1] for k in p["keys_rejected"]] == [first]


def test_a5_tier2_leg_without_an_ids_tier2_refuses(world):
    """A one-look ids.json has no A5 tier 2: a tier-2 leg directory is refused, never paired against nothing."""
    assert "tier2" not in world.ids["axes"]["longctx"]
    assert {"longctx/t2-b1", "longctx/t2-b2"} <= set(world.verify()["not_run"])
    (world.rows / "m76" / "wave1" / "longctx-m76-x-lc-t2-b1").mkdir(parents=True)
    with pytest.raises(V.RefusalError, match="no longctx tier 2"):
        world.verify()


def test_a5_ids_must_be_nested(world2):
    ids = json.loads((world2.rows / "m76" / "ids.json").read_text())
    lc = ids["axes"]["longctx"]
    lc["items"] = lc["items"][42:] + lc["items"][:42]                       # tier 2 before tier 1
    (world2.rows / "m76" / "ids.json").write_text(json.dumps(ids))
    with pytest.raises(V.RefusalError, match="nested"):
        world2.verify()


def test_compute_kv_a5_two_looks_end_to_end(world2, monkeypatch):
    """Look 1 on tier 1 (UNDECIDED) → look 2 on tier 1 + tier 2, through B8 and B7's real `axis_verdict` (two-look stand-in
    plan in the TEST only)."""
    from bench import m76_rule
    from bench import p426_signals as S

    real = m76_rule.axis_plan
    looks = ((42, 0.003808), (54, 0.021192))
    monkeypatch.setattr(m76_rule, "axis_plan", lambda axis, **kw: real(axis, **kw) if axis != "A5" else dict(
        axis="A5", sessions=1, items=54, report_sha256="e" * 64,
        looks=[dict(look=k + 1, size=n, unit="items", alpha=a, exact_alpha=a) for k, (n, a) in enumerate(looks)]))
    lc = world2.ids["axes"]["longctx"]
    fail = [i for i in lc["block1"] if i.startswith("retrieval-")][0]
    world2.leg("longctx", "x", "b1", row_hook=lambda r: dict(r, hits=[True] * 4 + [False]) if r["content"].endswith(fail) else r)
    b8 = V.verify_all_kv(world2.rows, world2.repo, ("n16", "x"), kinds=("cjudge", "longctx"))
    sig = S.compute_kv(world2.rows, b8)
    a5 = sig["axes"]["A5"]
    assert a5["looks"][0]["verdict"] == "UNDECIDED" and a5["looks"][1]["status"].startswith("pending")   # tier 2 not run
    for label in V.KV_TIER2:
        for arm in ("n16", "x"):
            world2.leg("longctx", arm, label)
    b8 = V.verify_all_kv(world2.rows, world2.repo, ("n16", "x"), kinds=("cjudge", "longctx"))
    a5 = S.compute_kv(world2.rows, b8)["axes"]["A5"]
    l1, l2 = a5["looks"]
    assert (l1["n_items"], l1["alpha"], l2["n_items"], l2["alpha"]) == (42, 0.003808, 54, 0.021192)
    assert l2["verdict"] == m76_rule.verdict_a5(1, 0, 54, alpha=0.021192).verdict and a5["final_look"] == 2
    assert l1["size_warnings"] == l2["size_warnings"] == [] and "tier_mismatch" not in a5
    assert a5["gates"]["retrieval"]["n"] == 27 and a5["n"] == 54
