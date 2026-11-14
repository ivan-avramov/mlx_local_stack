"""M76 B3 fix round 1 (spec v1.2 erratum): A7 under `lever=kv` — tg1 session s3 (seed 3003) end to end (schedule, chain config,
sequencer legs, freeze deadline, dossier pair), the sessions taken from B7's committed plan (`m76_rule.axis_plan("A7")`), B8
refusing incomplete evidence (a missing planned session; any rejected key rejects the session pair), the KV harvest prefix for
the final-tree identities, and the A7 signals verdict from `m76_rule.axis_verdict` (the real B7 module, no shim)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bench import m76_rule
from bench import p426_freeze as fz
from bench import p426_plan as P
from bench import p426_signals as S
from bench import p426_verify as V
from bench import p426_wave2 as W2
from bench import schedules
from bench.tests.p613.a7world import dumps, sealed, sha_bytes

BENCH = Path(__file__).resolve().parents[2]
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PREFIX = "benchmark/results/m76"
SESSIONS = ("s1", "s2", "s3")
DIAG = ("pilot", "reload")
SEED = {"s1": 1001, "s2": 2002, "s3": 3003, "pilot": 1001, "reload": 1001}
ITEMS = [f"python/a{i}" for i in range(5)] + [f"go/g{i}" for i in range(3)]     # every paired session runs the same items
IDS = {s: list(ITEMS) for s in SESSIONS}
IDS.update(pilot=ITEMS[:5], reload=ITEMS[:5])
COMMIT = {"n16": "a1" * 20, "x": "b2" * 20}


# ------------------------------------------------------------------------------------------------- the plan's sessions
def test_a7_sessions_come_from_b7s_plan():
    assert P.kv_a7_sessions() == ("s1", "s2", "s3")                  # the committed report: one look over s1 + s2 + s3
    assert m76_rule.axis_plan("A7")["looks"][-1]["size"] == 3


def test_a7_sessions_refuse_a_plan_they_cannot_run(monkeypatch):
    monkeypatch.setattr(m76_rule, "axis_plan", lambda axis, report=None: dict(looks=[dict(look=1, size=4, unit="sessions")]))
    with pytest.raises(ValueError):
        P.kv_a7_sessions()
    with pytest.raises(fz.Refusal):
        W2.kv_a7_sessions()


# ------------------------------------------------------------------------------------------------- s3 in the schedule
NAMES = {"python": [f"p{i}" for i in range(12)], "go": [f"g{i}" for i in range(9)]}


def test_s3_schedule_is_seed_3003_and_s1_shaped():
    s3 = schedules.tg1("chain", ["s3"], NAMES, picks=(MODEL,), p426=True, s3=True)
    s1 = schedules.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True, s3=True)
    assert [b["seed_base"] for b in s3["blocks"]] == [3003] and s3["m76_s3"] is True
    assert [leg["lang"] for leg in s3["blocks"][0]["legs"]] == [leg["lang"] for leg in s1["blocks"][0]["legs"]] == ["python", "go"]
    import random
    assert s3["blocks"][0]["legs"][0]["full_names"] == random.Random(3003).sample(sorted(NAMES["python"]), 12)
    assert schedules.tg1_legs_table((MODEL,), ("python", "go"), True, s3=True)["s3"] == [(MODEL, "python"), (MODEL, "go")]


def test_s3_never_exists_without_the_m76_flag():
    legacy = schedules.tg1("chain", ["s1"], NAMES, picks=(MODEL,), p426=True)
    assert "m76_s3" not in legacy                                      # P426's schedule dict unchanged
    assert "s3" not in schedules.tg1_legs_table((MODEL,), ("python", "go"), True)
    with pytest.raises((KeyError, ValueError)):
        schedules.tg1("chain", ["s3"], NAMES, picks=(MODEL,), p426=True)
    with pytest.raises(ValueError):
        schedules.tg1_legs_table((MODEL,), ("python", "go"), False, s3=True)
    occ = [dict(session="s3", language="go", item="g1", seed=3003, arm_of_dnf="x", occurrence=0),
           dict(session="s1", language="python", item="p1", seed=1001, arm_of_dnf="n16", occurrence=2)]
    with pytest.raises(ValueError):
        schedules.makeup_canonical(occ)
    assert [m["session"] for m in schedules.makeup_canonical(occ, s3=True)] == ["s1", "s3"]
    assert schedules.tg1_makeup(occ, {"go": ["g1"], "python": ["p1"]}, picks=(MODEL,), s3=True)["m76_s3"] is True


def test_the_chain_config_carries_s3_only_under_kv():
    sys.path.insert(0, str(BENCH / "chains" / "c147"))
    import run_tg1_chain as C

    base = ["chain", "s3", "--p426", "--models", MODEL, "--predictor", "mtp", "--out-root", "/wd/m76/p426/wave2/x.a1",
            "--campaign-core", "c", "--frozen-prompt-date", "Fri Nov 13 2026", "--probe-code-sha", "a" * 64,
            "--policy-sha", "b" * 64, "--frozen-record", "/wd/r.json"]
    a = C.parse_args(base + ["--lever", "kv", "--kv-arm", "x"])
    params = C.tg1_config(a).schedule["params"]
    assert params["seeds"]["s3"] == 3003 and params["m76_s3"] is True and "s3" in params["legs"]
    with pytest.raises(SystemExit):
        C.parse_args(base)                                             # lever mtp: s3 is an unknown session
    mtp = C.parse_args(["chain", "s1"] + base[2:])
    p = C.tg1_config(mtp).schedule["params"]
    assert "s3" not in p["seeds"] and "m76_s3" not in p and "s3" not in p["legs"]


def test_the_sequencer_runs_the_plans_sessions():
    t = W2.kv_legs("n16", "x")
    names = [leg["name"] for leg in t["run"]]
    assert names == ["tg1-m76-n16-pilot", "tg1-m76-x-pilot", "tg1-m76-n16-s1", "tg1-m76-x-s1", "tg1-m76-x-s2",
                     "tg1-m76-n16-s2", "tg1-m76-n16-s3", "tg1-m76-x-s3", "tg1-m76-x-reload", "tg1-m76-n16-reload"]
    assert [leg["n"] for leg in t["run"]] == list(range(1, 11)) and [leg["n"] for leg in t["makeup"]] == [11, 12]
    assert [leg["role"] for leg in t["run"]] == ["first", "second"] * 5
    two = W2.kv_legs("n16", "x", sessions=("s1", "s2"))
    assert [leg["name"] for leg in two["run"]][-2:] == ["tg1-m76-x-reload", "tg1-m76-n16-reload"] and len(two["run"]) == 8
    with pytest.raises(ValueError):
        W2.kv_legs("n16", "x", sessions=("s1", "s3"))
    assert W2.deadline_s("s3", {"python": 1}, dict(w_python_s=10, w_go_s=10)) > 0


def test_the_amendment_gives_s3_its_deadline_and_the_dossier_its_pair():
    from bench import p426_receipt as pr
    assert "s3" in pr.KV_DOSSIER_PAIRS and "s3" not in pr.PAIRS


def test_a_v_pair_refuses_at_wave2_preflight(tmp_path):
    a = W2.parse_args(["run", "--lever", "kv", "--pair", "x,v", "--arm-worktree", f"x={tmp_path}/a",
                       "--arm-worktree", f"v={tmp_path}/b", "--out-base", str(tmp_path / "m76" / "p426" / "w"),
                       "--record-dir", str(tmp_path / "rec")])
    with pytest.raises(fz.Refusal, match="stage 4"):
        W2.check_args(a, tmp_path)


# ------------------------------------------------------------------------------------------------- a KV A7 world
def attempt(arm, session):
    return f"tg1-m76-{arm}-{session}.a1"


def invocation_manifest(arm, session, lang, leg):
    """A tg1 invocation manifest of `provenance.gather` + `arm_runner`'s shape: the arms differ only in the KV / mode fields,
    the arm commit, the observed worker fingerprint's KV flags / entry keys, and the per-invocation identity."""
    tq4 = arm != "n16"
    flags = {"--model": "caslca/x", "--draft-kind": "mtp", "--max-kv-size": "262144"}
    entry = dict(hf_path="caslca/x", draft_kind="mtp", max_kv_cache_size=262144)
    if tq4:
        flags.update({"--kv-bits": "4", "--tq4-attention": "m72_exact"})
        entry.update(kv_bits=4, tq4_attention="m72_exact")
    ident = dict(flags=flags, entry=entry, target=dict(kind="hf", repo="caslca/x", revision="r1"), draft=None,
                 apc=dict(router="0", worker="0"), retain_prompt_end="on")
    return dict(
        model=MODEL, box="box-1", fingerprint_version=9, sampling_profile="deployed", timestamp=f"t-{arm}-{session}-{lang}",
        sampling=dict(temperature=0.6, top_p=0.95, max_tokens=102400, thinking_budget=81920),
        registry=dict(sha256=("r" if tq4 else "q") * 64), router=dict(pid=1000 + leg, config=f"/wt/{arm}"),
        git=dict(stack_head=COMMIT[arm], serving_path={"src/mlx-vlm": "t" * 40, "src/mlx-serve": "u" * 40}),
        quant=dict(effective_bits=4.5),
        kv=dict(kv_bits=4 if tq4 else 0, kv_quant_scheme="turboquant" if tq4 else "uniform", max_kv_cache_size=262144,
                prefill_step_size=4096, hf_path="caslca/x"),
        runtime=dict(apc_enabled=False, draft_kind="mtp", mtp_verify_scan="joint_v1",
                     tq4_attention="m72_exact" if tq4 else "off", lang=lang, seed_base=SEED[session],
                     sampling_profile="deployed", probe_code_sha256="9" * 64, scaffold_policy_sha256="c" * 64,
                     generation_identity_sha256="g" * 64, invocation_nonce=f"n-{arm}-{session}-{lang}",
                     arm_identity=ident, arm_identity_sha256=sha_bytes(json.dumps(ident, sort_keys=True).encode())),
        worker=dict(pid=2000 + leg + len(arm), create_time=1.5), run_id=f"20261114T00000{leg}-{arm}{session}")


class KVWorld:
    """`benchmark/results/m76/wave2/` of a (n16, x) pair: v8 base, sequence, dossiers, attempts (rows, items, HARVEST under the
    m76 prefix, schedules), every session of `sessions`."""

    def __init__(self, base, sessions=SESSIONS + DIAG, rows=None, ids=None, manifest_hook=None):
        self.root = Path(base) / "repo" / PREFIX
        self.rows = rows or {}                                         # {(arm, session): {id: patch}}
        self.manifest_hook = manifest_hook                             # (arm, session, lang, manifest) -> manifest | None
        self.ids = dict(IDS, **(ids or {}))
        (self.root / "wave2" / "run").mkdir(parents=True)
        (self.root / "wave2" / "pairs").mkdir(parents=True)
        v8 = sealed(dict(kind="p426_v8_base", lever="kv", arms=["n16", "x"], build="s3", n16_commit=COMMIT["n16"],
                         x_commit=COMMIT["x"], gitlinks={}, created="2026-11-14T00:00:00Z"))
        (self.root / "wave2" / "run" / "v8_base.json").write_text(dumps(v8))
        for s in sessions:
            for arm in ("n16", "x"):
                self.build_attempt(arm, s)
            self.dossier(s)
        seq = dict(legs=[dict(leg=attempt(a, s)[:-3], attempt=1, state="VALID") for s in sessions for a in ("n16", "x")],
                   pairs=[dict(pair=s, n16=attempt("n16", s), x=attempt("x", s), dossier=f"pairs/{s}__n16-a1__x-a1.json",
                               verdict="PASS") for s in sessions])
        (self.root / "wave2" / "run" / "sequence.json").write_text(dumps(seq))

    def build_attempt(self, arm, s):
        att = self.root / "wave2" / attempt(arm, s)
        (att / s).mkdir(parents=True)
        (att / "items").mkdir()
        ids = self.ids[s]
        legs = []
        for lang in ("python", "go"):
            members = [i for i in ids if i.startswith(lang + "/")]
            if members:
                legs.append(dict(session=s, model=MODEL, lang=lang, seed_base=SEED[s], invocations=[dict(
                    phase="full", names=[m.split("/")[1] for m in members], limit=None, expect=members)]))
        sched = dict(schema=1, builder="tg1", mode="chain", smoke=False, p426=True, picks=[MODEL],
                     blocks=[dict(session=s, model=MODEL, seed_base=SEED[s], legs=legs, pilot_only=s in DIAG)])
        (att / "schedule.json").write_text(dumps(sched))
        files, lines = [], []
        run = "20261114T000000-abc"
        for k, rid in enumerate(ids):
            lang, item = rid.split("/")
            mrel = f"wave2/{attempt(arm, s)}/evidence/{run}/{lang}__{item}.final_tree/manifest.json"
            mp = self.root / mrel
            mp.parent.mkdir(parents=True, exist_ok=True)
            mp.write_text(dumps(dict(files={"sol.txt": f"{arm}|{s}|{rid}"}, item=rid)))
            row = dict(bench="opencode", schema_version=3, id=rid, model=MODEL, sample=0, passed=True, acc=1, converged=True,
                       nonconv_kind=None, nonconv_flags=[], sampler_seed=SEED[s] * 1000 + k, seed_base=SEED[s],
                       final_tree=dict(manifest_sha256=sha_bytes(mp.read_bytes()), files={}, missing=[]))
            row.update((self.rows.get((arm, s)) or {}).get(rid, {}))
            lines.append(json.dumps(row, sort_keys=True))
            files.append(dict(destination="main", published=f"{PREFIX}/{mrel}", published_sha256=sha_bytes(mp.read_bytes()),
                              sha256=sha_bytes(mp.read_bytes()), source="x", compression=None, exclusion_reason=None))
            rec = dict(case="completed", verdict="reconciled", slot=f"tg1-p426|oc|{MODEL}|{s}|{lang}|{item}",
                       totals=dict(requests=2, generated_tokens=302, decode_s=10.0, accepted=80, proposed=100, prompt_tokens=1000,
                                   decode_rate_source="completed requests (spec 8)"),
                       requests=[dict(generated_tokens=151, decode_tok_s=30.0, error=None)] * 2)
            (att / "items" / f"tg1-p426__oc__{MODEL}__{s}__{lang}__{item}.json").write_text(dumps(rec))
        for li, lang in enumerate(("python", "go")):               # one probe invocation per language leg
            mine = [x for x in lines if json.loads(x)["id"].startswith(lang + "/")]
            if not mine:
                continue
            stem = f"{MODEL}.{s}.opencode.L{li}.full.a1"
            (att / s / f"{stem}.jsonl").write_text("".join(x + "\n" for x in mine))
            man = invocation_manifest(arm, s, lang, li)
            if self.manifest_hook:
                man = self.manifest_hook(arm, s, lang, man)
            if man is not None:
                (att / s / f"{stem}.manifest.json").write_text(dumps(man))
        (att / "HARVEST.json").write_text(dumps(sealed(dict(attempt=1, leg=attempt(arm, s)[:-3], state="VALID", files=files))))
        (att / "receipt.json").write_text(dumps(sealed(dict(argv=[], env={}))))
        (att / "leg.json").write_text(dumps(sealed(dict(attempt=1, leg=attempt(arm, s)[:-3], state="VALID", speed_valid=True,
                                                         speed_reason="ok"))))
        (att / "chain.json").write_text(dumps(dict(status="finished", artifacts=dict(campaign_core=dict(commit=COMMIT[arm])),
                                                   p426_dnf=[], p426_ledger=[])))

    def dossier(self, s):
        arms = {arm: dict(attempt=attempt(arm, s),
                          harvest_sha256=sha_bytes((self.root / "wave2" / attempt(arm, s) / "HARVEST.json").read_bytes()),
                          receipt_sha256=sha_bytes((self.root / "wave2" / attempt(arm, s) / "receipt.json").read_bytes()))
                for arm in ("n16", "x")}
        doc = sealed(dict(pair=s, lever="kv", ref="n16", test="x", verdict="PASS", arms=arms,
                          differences=[dict(process="worker", field="argv.worker", ref=None, test="--kv-bits 4")]))
        (self.root / "wave2" / "pairs" / f"{s}__n16-a1__x-a1.json").write_text(dumps(doc))


def pairs_by(b8):
    return {p["pair"]: p for p in b8["pairs"]}


def test_b8_verifies_every_planned_session(tmp_path):
    w = KVWorld(tmp_path)
    b8 = V.verify_a7_kv(w.root, ("n16", "x"))
    got = pairs_by(b8)
    assert b8["sessions"] == ["s1", "s2", "s3"] and set(got) == {"s1", "s2", "s3", "pilot", "reload"}
    for s in SESSIONS:
        assert got[s]["accepted"], got[s]["reasons"]
        assert got[s]["role"] == "pair" and got[s]["keys_accepted"] == len(IDS[s])


def test_b8_refuses_when_a_planned_session_is_missing(tmp_path):
    w = KVWorld(tmp_path, sessions=("s1", "s2") + DIAG)
    with pytest.raises(V.RefusalError, match="s3"):
        V.verify_a7_kv(w.root, ("n16", "x"))


def test_a_rejected_key_rejects_the_session_pair(tmp_path):
    rid = IDS["s3"][2]
    w = KVWorld(tmp_path, rows={("x", "s3"): {rid: dict(sampler_seed=1)}})
    got = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))
    assert got["s3"]["keys_rejected"] and got["s3"]["accepted"] is False
    assert any("rule 3" in r and "incomplete" in r for r in got["s3"]["reasons"])
    assert got["s1"]["accepted"] and got["s2"]["accepted"]


def test_the_final_tree_identity_reads_the_kv_harvest_prefix(tmp_path):
    w = KVWorld(tmp_path)
    keys = pairs_by(V.verify_a7_kv(w.root, ("n16", "x")))["s1"]["keys"]
    assert all(k["manifest_sha256"]["n16"] and k["manifest_sha256"]["x"] for k in keys)   # bound through HARVEST (m76/)
    assert not any(k["identical"] for k in keys)                       # the two arms' trees differ in this world


# ------------------------------------------------------------------------------------------------- A7 provenance (v1.3)
def _set(m, path, value):
    d = m
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value
    return m


def test_a7_clean_world_compares_every_invocation_manifest(tmp_path):
    """v1.3: the KV delta (kv / runtime mode keys, the arm commit, the worker fingerprint's KV flags) and the per-invocation
    identity (run id, worker pid, nonce, timestamp, router) never reject."""
    w = KVWorld(tmp_path)
    b8 = V.verify_a7_kv(w.root, ("n16", "x"))
    assert all(p["accepted"] for p in b8["pairs"]), [p["reasons"] for p in b8["pairs"]]
    assert any(k.endswith(".manifest.json") for k in b8["inputs"])           # the manifests are B8 inputs (staleness)


@pytest.mark.parametrize("path,value", [
    (("sampling_profile",), "production"), (("runtime", "sampling_profile"), "production"),
    (("runtime", "apc_enabled"), True), (("git", "serving_path", "src/mlx-vlm"), "w" * 40), (("fingerprint_version",), 8),
    (("kv", "prefill_step_size"), 2048), (("sampling", "temperature"), 0.7), (("box",), "box-2"),
    (("runtime", "generation_identity_sha256"), "h" * 64),
    (("runtime", "arm_identity", "flags", "--max-kv-size"), "131072"),   # a non-KV worker flag in the fingerprint
])
def test_a7_provenance_outside_the_kv_whitelist_rejects_the_session_pair(tmp_path, path, value):
    def hook(arm, s, lang, m):
        return _set(m, path, value) if (arm, s, lang) == ("x", "s2", "go") else m

    got = pairs_by(V.verify_a7_kv(KVWorld(tmp_path, manifest_hook=hook).root, ("n16", "x")))
    assert got["s2"]["accepted"] is False
    assert any("provenance" in r and ".".join(path) in r for r in got["s2"]["reasons"]), got["s2"]["reasons"]
    assert got["s1"]["accepted"] and got["s3"]["accepted"]


def test_a7_a_missing_invocation_manifest_rejects_the_session_pair(tmp_path):
    def hook(arm, s, lang, m):
        return None if (arm, s, lang) == ("n16", "s1", "python") else m

    got = pairs_by(V.verify_a7_kv(KVWorld(tmp_path, manifest_hook=hook).root, ("n16", "x")))
    assert got["s1"]["accepted"] is False and any("provenance manifest" in r for r in got["s1"]["reasons"])


def test_a7_normalise_keeps_everything_but_the_invocation_identity():
    a, b = invocation_manifest("n16", "s1", "go", 1), invocation_manifest("x", "s1", "go", 1)
    assert V.kv_provenance_problems(V.kv_a7_normalise(a), V.kv_a7_normalise(b), "n16", "x") == []
    raw = V.kv_provenance_problems(a, b, "n16", "x")                    # without the A7 normalisation: per-invocation keys
    assert any(p.startswith("run_id") for p in raw) and any(p.startswith("worker") for p in raw)


# ------------------------------------------------------------------------------------------------- A7 signals (real B7)
def _a7_signals(w):
    b8 = V.verify_a7_kv(w.root, ("n16", "x"))
    rows_root = w.root.parent
    return S._kv_a7_section(rows_root, b8, "n16", "x")


def test_a7_signals_are_axis_verdict_over_the_three_sessions(tmp_path):
    fails = {rid: dict(passed=False, acc=0) for rid in IDS["s2"][:2]}
    w = KVWorld(tmp_path, rows={("x", "s2"): fails})
    rec, decode = _a7_signals(w)
    assert rec["sessions"] == ["s1", "s2", "s3"] and rec["n_sessions"] == 3
    assert rec["alpha"] == m76_rule.axis_plan("A7")["looks"][-1]["alpha"] == 0.001
    assert set(rec) >= {"verdict", "loss_bound", "per_session", "interaction", "interaction_flag", "size_warnings", "descriptive"}
    assert rec["descriptive"]["statistic"].startswith("paired_session_delta")
    assert set(decode) == set(SESSIONS) and decode["s1"]["primary"]["n"] == len(IDS["s1"])


def test_a7_signals_refuse_incomplete_evidence(tmp_path):
    rid = IDS["s3"][0]
    w = KVWorld(tmp_path, rows={("x", "s3"): {rid: dict(sampler_seed=1)}})
    rec, _ = _a7_signals(w)
    assert "verdict" not in rec and rec["status"].startswith("incomplete")


def test_a7_signals_match_b7_on_shared_items(tmp_path):
    """The same 8 items in every session (P426's shape: the corpus is fixed, only the order differs): the sheet's verdict is
    exactly `m76_rule.axis_verdict("A7", 1, X, N16)` on the strict maps."""
    shared = {s: list(IDS["s1"]) for s in SESSIONS}
    fails = {IDS["s1"][0]: dict(passed=False, acc=0)}
    w = KVWorld(tmp_path, ids=shared, rows={("x", "s1"): fails, ("x", "s3"): fails})
    rec, _ = _a7_signals(w)
    test = {i: {s: int(not (s in ("s1", "s3") and i == IDS["s1"][0])) for s in SESSIONS} for i in IDS["s1"]}
    ref = {i: {s: 1 for s in SESSIONS} for i in IDS["s1"]}
    want = m76_rule.axis_verdict("A7", 1, test, ref)
    for k in ("verdict", "loss_bound", "delta", "lo", "hi", "alpha", "interaction_flag", "size_warnings"):
        assert rec[k] == want[k], k
    assert rec["size_warnings"] == ["8 items, plan look 1 expects 43"]            # a size warning is kept …
    sig = dict(header=dict(label="X − N16"), axes=dict(A7=rec, A1={}, A5={}))
    assert any(f["flag"] == "size_warning" and f["blocking"] for f in S.kv_flags(sig))    # … and blocks


def test_the_sheet_renders_a7_and_its_t2_decode(tmp_path):
    shared = {s: list(IDS["s1"]) for s in SESSIONS}
    w = KVWorld(tmp_path, ids=shared)
    rec, decode = _a7_signals(w)
    sig = S.kv_sheet_skeleton(("n16", "x"))
    sig["axes"].update(A7=rec, A1=dict(looks=[], final_look=None), A5=dict(status="pending"))
    sig["decode"] = {"A7": decode}
    sig["panel"] = dict(status="pending (panel not run)")
    sig["flags"] = S.kv_flags(sig)
    md = S.render_kv(sig)
    # 8 items, no discordance: B7's exact bound at α* 0.001 is 1 − 0.001^(1/8) ≈ 58 pp → UNDECIDED (and off-plan in size)
    assert rec["verdict"] == "UNDECIDED" and rec["delta"] == 0.0 and rec["loss_bound"] == pytest.approx(1 - 0.001 ** (1 / 8))
    assert "sessions ['s1', 's2', 's3']" in md and "**UNDECIDED**" in md and "A7 s3: treatment / reference" in md
    assert decode["s3"]["primary"]["geomean_ratio"] == pytest.approx(1.0)
    assert [f["flag"] for f in sig["flags"]] == ["size_warning", "undecided"]
