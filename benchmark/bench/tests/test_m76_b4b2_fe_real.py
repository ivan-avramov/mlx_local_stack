"""M76 B4b-2 (spec v1.5) — acceptance §7.1 / §7.2 / §7.3 on the COMMITTED records: the byte-identity goldens (B8.json, SIGNALS.md /
SIGNALS.json, SIGNALS-partial.md / .json regenerate from `main`'s inputs), the A8-present projection of the sheet, and the shape of
B8-A8 on the real harvested tg2 pilot pair and decider (`benchmark/results/m76/wave2.tg2/`; S29: the decider legs run on the
sealed post-pilot amendment).

Class of each test (comment above it): (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.

Note (spec §9.7): §7.3 is to run on the NEW-identity pilot pair once it is harvested; the pair committed now is the old-identity one
(no S27 sidecars, no reruns), so these tests describe what must hold on it today and must still hold on its successor.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench import p426_verify as V
from bench import schedules
from bench.tests import test_m76_b4b2_fe_support as W

BENCH = W.BENCH
RESULTS = BENCH / "results"
M76 = RESULTS / "m76"
TG2 = M76 / "wave2.tg2"
PAIR = ("n16", "x")


def cli(module, args, tmp_path):
    env = {"PYTHONPATH": str(BENCH), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(tmp_path),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "MLX_BENCH_RESULTS": str(RESULTS)}
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=BENCH, capture_output=True, text=True, timeout=3000, env=env)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------------------------ B8 (§7.1, §7.5)
@pytest.fixture(scope="module")
def regenerated_b8(tmp_path_factory):
    out = tmp_path_factory.mktemp("b8")
    proc = cli("bench.p426_verify", ["all", "--lever", "kv", "--pair", "n16,x", "--results-root", M76, "--rows-root", RESULTS,
                                     "--repo", W.REPO, "--out", out / "B8.json"], out)
    return out, proc


# (b) B8.json regenerates byte-identically from main's inputs (A8 never enters it)
def test_b8_regenerates_byte_identically(regenerated_b8):
    out, proc = regenerated_b8
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert (out / "B8.json").read_bytes() == (M76 / "B8.json").read_bytes()


# (c) and, because A8's run record exists on main and v8 is the tg2 kv pair, the CLI writes B8-A8.json beside it
def test_the_cli_writes_b8_a8_beside_b8(regenerated_b8):
    out, proc = regenerated_b8
    assert proc.returncode == 0, proc.stderr[-1500:]
    path = out / "B8-A8.json"
    assert path.is_file()
    doc = json.loads(path.read_text())
    assert doc["corpus"] == "tg2" and doc["base_b8_sha256"] == sha(out / "B8.json") == sha(M76 / "B8.json")


# (b) B8.json never includes A8
def test_committed_b8_has_no_a8():
    doc = json.loads((M76 / "B8.json").read_text())
    assert "A8" not in doc["axes"] and not [k for k in doc["inputs"] if "wave2.tg2" in k]


# ------------------------------------------------------------------------------------------------------------------ signals goldens (§7.1)
def _signals(tmp_path, *extra):
    args = ["all", "--lever", "kv", "--results-root", M76, "--rows-root", RESULTS, "--b8", M76 / "B8.json",
            "--out-md", tmp_path / "S.md", "--out-json", tmp_path / "S.json", *extra]
    return cli("bench.p426_signals", args, tmp_path)


# (b) with no B8-A8.json SIGNALS.md / SIGNALS.json regenerate byte-identically (the sheet over the frozen panel, not ingested: no --partial)
def test_signals_regenerate_byte_identically(tmp_path):
    proc = _signals(tmp_path, "--panel", M76 / "panel")
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert (tmp_path / "S.md").read_bytes() == (M76 / "SIGNALS.md").read_bytes()
    assert (tmp_path / "S.json").read_bytes() == (M76 / "SIGNALS.json").read_bytes()


# (b) ... and so do SIGNALS-partial.md / .json (the frozen stage-3 panel, ingested under --partial)
def test_partial_signals_regenerate_byte_identically(tmp_path):
    proc = _signals(tmp_path, "--panel", M76 / "panel", "--partial")
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert (tmp_path / "S.md").read_bytes() == (M76 / "SIGNALS-partial.md").read_bytes()
    assert (tmp_path / "S.json").read_bytes() == (M76 / "SIGNALS-partial.json").read_bytes()


# (b) the committed frozen stage-3 panel is unchanged by the A8 work (its members are A1–A5 and A7-s1..s3, none A8)
def test_the_frozen_panel_has_no_a8_member():
    assert sorted(p.name for p in (M76 / "panel").iterdir() if p.is_dir()) == ["A1", "A2", "A3", "A4", "A5", "A7-s1", "A7-s2", "A7-s3"]


# ------------------------------------------------------------------------------------------------------------------ §7.2 projection
def projection(sig):
    sig = copy.deepcopy(sig)
    sig["axes"].pop("A8", None)
    (sig.get("decode") or {}).pop("A8", None)
    sig["header"] = {k: v for k, v in sig["header"].items() if "sha" not in k and "n_inputs" not in k and "a8" not in k.lower()}
    for k in ("inputs", "inputs_a8", "flags"):          # the candidate adds `inputs_a8` beside B8's `inputs`
        sig.pop(k, None)
    for m in ((sig.get("panel") or {}).get("members") or {}).values():
        m.pop("holm_p", None)
    comp = (sig.get("panel") or {}).get("completeness")
    if isinstance(comp, dict):                          # B8-A8 adds its `A8-<session>` members to the expected / missing lists
        for k in ("expected", "missing_members"):
            comp[k] = _non_a8(comp.get(k))
    return json.loads(json.dumps(sig, sort_keys=True, default=str))


def _non_a8(members):
    return [m for m in members or [] if not str(m).startswith("A8-")]


def flags_without_a8(flags):
    """The sheet's flags minus what B8-A8 causes: flags of member A8 dropped, the A8 panel members taken out of
    `panel_incomplete` (its items and its text)."""
    out = []
    for f in flags:
        if f.get("member") == "A8":
            continue
        f = copy.deepcopy(f)
        if f.get("flag") == "panel_incomplete":
            items = list(f.get("items") or [])
            f["text"] = f["text"].replace(f"missing members {items}", f"missing members {_non_a8(items)}")
            f["items"] = _non_a8(items)
        out.append(json.dumps(f, sort_keys=True, default=str))
    return sorted(out)


def a8_panel_members(doc):
    from bench import p426_panel as P

    return [f"A8-{s}" for s in P.kv_a8_member_sessions(doc)]


# (c) with the real B8-A8.json: the sheet's A1–A7 sections, decode, coverage and raw statistics equal the committed ones; only A8
# content may differ — the A8 section and decode, header shas / counts, the Holm column, A8 flags, and the panel completeness now
# also expecting exactly B8-A8's `A8-<session>` members
@pytest.mark.parametrize("committed,partial", [("SIGNALS.json", False), ("SIGNALS-partial.json", True)])
def test_a8_record_changes_only_the_a8_parts_of_the_real_sheet(committed, partial):
    from bench import p426_signals as S

    b8 = json.loads((M76 / "B8.json").read_text())
    doc = V.verify_a8_kv(M76, sha(M76 / "B8.json"))
    got = S.compute_kv(RESULTS, b8, b8_sha256=sha(M76 / "B8.json"), panel=M76 / "panel", partial=partial, b8_a8=doc,
                       b8_a8_sha256=hashlib.sha256(V.dumps(doc).encode()).hexdigest())
    want = json.loads((M76 / committed).read_text())
    assert projection(got) == projection(want)
    assert "A8" in got["axes"]
    members = a8_panel_members(doc)
    assert members == ["A8-s1", "A8-s2"]                # the decider's confirmatory sessions are B8-A8-accepted
    gc, wc = got["panel"]["completeness"], want["panel"]["completeness"]
    assert gc["expected"] == wc["expected"] + members
    assert gc["missing_members"] == wc["missing_members"] + [m for m in members if not (M76 / "panel" / m).is_dir()]
    assert flags_without_a8(got["flags"]) == flags_without_a8(want["flags"])


# ------------------------------------------------------------------------------------------------------------------ §7.3
@pytest.fixture(scope="module")
def real_doc():
    return V.verify_a8_kv(M76, sha(M76 / "B8.json"))


def sessions(doc):
    return {p["pair"]: p for p in doc["pairs"]}


# (c) B8-A8 builds on the harvested pilot and decider: the pilot accepted (diagnostic), s1 / s2 accepted (pair), reload accepted
# (diagnostic), the record complete
def test_the_real_pilot_and_decider_pairs_build_accepted(real_doc):
    got = sessions(real_doc)
    assert got["pilot"]["accepted"] is True, got["pilot"]["reasons"]
    assert got["pilot"]["reasons"] == [] and got["pilot"]["role"] == "diagnostic"
    for s, role in (("s1", "pair"), ("s2", "pair"), ("reload", "diagnostic")):
        assert got[s]["status"] == "accepted" and got[s]["accepted"] is True and got[s]["reasons"] == [], (s, got[s]["reasons"])
        assert got[s]["role"] == role and got[s]["keys"], s
    assert real_doc["status"] == "complete" and real_doc["corpus"] == "tg2" and real_doc["sessions"] == ["s1", "s2"]


# (c) final-tree identities matched for every pilot row of both arms (no null sha), provenance passing
def test_the_real_pilot_identities_are_matched_and_provenance_passes(real_doc):
    pilot = sessions(real_doc)["pilot"]
    assert len(pilot["keys"]) == 4
    for k in pilot["keys"]:
        assert all(isinstance(k["manifest_sha256"][a], str) and len(k["manifest_sha256"][a]) == 64 for a in PAIR), k
    assert not [r for r in pilot["reasons"] if "provenance" in r.lower()]


# (c) the record is bound to what it read: the B8.json it accompanies and every input file's sha
def test_the_real_record_binds_b8_and_its_inputs(real_doc):
    assert real_doc["base_b8_sha256"] == sha(M76 / "B8.json")
    assert real_doc["inputs"]
    for rel, digest in real_doc["inputs"].items():      # relative to results_root, or to rows_root (`m76/` prefixed)
        assert sha(M76 / rel if (M76 / rel).is_file() else RESULTS / rel) == digest, rel
    names = set(real_doc["inputs"])
    assert names & {"wave2.tg2/run/v8_base.json", "m76/wave2.tg2/run/v8_base.json"}
    assert names & {"wave2.tg2/run/sequence.json", "m76/wave2.tg2/run/sequence.json"}


# (c) the decider ran on the amendment (S29 rule 3.6): every selected decider attempt's chain names the sealed post-pilot
# amendment, which binds this v8 base and the accepted pilot's dossier; X s1 a1 / a2 (INVALID before any item) are not selected;
# the s1 / s2 / reload pairs are accepted on it, the pilot on the v8 base
def test_the_real_decider_pairs_are_accepted_on_the_amendment(real_doc):
    got = sessions(real_doc)
    amendment = json.loads((TG2 / "run" / "amendment.json").read_text())
    v8 = json.loads((TG2 / "run" / "v8_base.json").read_text())
    assert amendment["v8_base_sha256"] == v8["sha256"]
    assert amendment["pilot_dossier_sha256"] == sha(M76 / got["pilot"]["dossier"])
    assert {"m76/wave2.tg2/run/amendment.json", "m76/wave2.tg2/run/v8_base.json"} <= set(real_doc["inputs"])
    for s in ("s1", "s2", "reload"):
        assert got[s]["accepted"] is True and got[s]["reasons"] == [], (s, got[s]["reasons"])
        for arm in PAIR:
            chain = json.loads((TG2 / got[s]["attempts"][arm] / "chain.json").read_text())
            assert chain["tg2_leg"] == s and chain["frozen_record"]["sha256"] == amendment["sha256"], (s, arm)
    for arm in PAIR:
        chain = json.loads((TG2 / got["pilot"]["attempts"][arm] / "chain.json").read_text())
        assert chain["frozen_record"]["sha256"] == v8["sha256"]
    seq = json.loads((TG2 / "run" / "sequence.json").read_text())
    assert {(l["leg"], l["attempt"]): l["state"] for l in seq["legs"]}[("tg2-m76-x-s1", 2)] == "INVALID"      # the premise
    assert got["s1"]["attempts"]["x"] not in ("tg2-m76-x-s1.a1", "tg2-m76-x-s1.a2")


# (c) the new-identity pilot pair is accepted as a whole record: both arms' four rows, the dossier, the harvest, provenance
def test_the_real_pilot_pair_is_accepted_without_any_reason(real_doc):
    pilot = sessions(real_doc)["pilot"]
    assert pilot["accepted"] is True and pilot["status"] == "accepted" and pilot["reasons"] == []


# (c) §7.3 / B11: the rebuilt tg2 prompt equals the first user message of every pilot export on the evidence ref (needs the polyglot
# checkout and the evidence objects of the new-identity pilot)
def test_the_real_pilot_exports_pass_the_prompt_check():
    from bench import p426_panel as P

    root = Path(os.environ.get("POLYGLOT_DIR") or str(Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark"))
    if not (root / "rust").is_dir():
        pytest.skip("polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)")
    git = lambda *a: subprocess.run(["git", "-C", str(W.REPO), *a], capture_output=True, text=True)      # noqa: E731
    ref = git("rev-parse", "--verify", "--quiet", "origin/evidence")
    probe = git("ls-tree", "-r", "--name-only", "origin/evidence", "--", "benchmark/results/m76/wave2.tg2/tg2-m76-n16-pilot.a1/evidence")
    if ref.returncode or probe.returncode or not probe.stdout.strip():          # (the evidence ref holds evidence files, not HARVEST.json)
        pytest.skip("the new-identity pilot's evidence objects are not on origin/evidence in this clone")
    top = V.repo_top(W.REPO)
    top_ref = (top, V.resolve_commit(top, ref.stdout.strip(), "--evidence-ref"))
    pinned = json.loads((W.BENCH / "m65" / "tg2_universe.json").read_text())["polyglot_sha"]
    corpus = P.a8_corpus(root, polyglot_sha=lambda r: pinned)
    reader = V.Reader(M76)
    ctx = dict(root=M76, prefix=V.KV_REPO_PREFIX, namespace=V.A8_NS)
    n = 0
    for arm in PAIR:
        att = V._a8_load_attempt(reader, f"tg2-m76-{arm}-pilot.a1", "pilot", arm)
        for rid, row in sorted(att["rows"].items()):
            prompt, _entry = P.a8_prompt_check(ctx, att, row, rid, corpus, top_ref)
            assert prompt.startswith("Implement the solution")
            n += 1
    assert n == 8


# (b) regression: the OLD-identity pilot pair, at its archive path, still verifies when put where the consumers read it
# (a copy of `wave2.tg2-old-identity/` as `wave2.tg2/` in a scratch rows tree: its records name `…/wave2.tg2/…` paths)
def test_the_old_identity_pilot_pair_still_verifies_from_its_archive(tmp_path):
    import shutil

    arch = M76 / "wave2.tg2-old-identity"
    root = tmp_path / "benchmark" / "results" / "m76"
    shutil.copytree(arch, root / "wave2.tg2", ignore=shutil.ignore_patterns("README.md"))
    shutil.copy(M76 / "B8.json", root / "B8.json")
    doc = V.verify_a8_kv(root, sha(root / "B8.json"))
    pilot = sessions(doc)["pilot"]
    assert pilot["accepted"] is True and pilot["reasons"] == [], pilot["reasons"]
    assert all(sessions(doc)[s]["status"] == "incomplete" for s in ("s1", "s2", "reload"))


# (c) the javascript lock-file regrade is gone (spec §9.1): nothing says "regrade pending", an outcome is an outcome
def test_no_regrade_machinery_in_the_real_record(real_doc):
    assert "regrade" not in json.dumps(real_doc).lower()


# (c) the decider's launch-latency record is published: B8-A8 reads it as `present` (sealed, rows well-formed), bound to its sha
# and an input of the record
def test_the_real_latency_is_present_and_verifies(real_doc):
    path = TG2 / "run" / "exec_latency.json"
    published = json.loads(path.read_text())
    lat = real_doc["latency"]
    assert lat["status"] == "present" and lat["path"] == f"{V.A8_NS}/run/exec_latency.json"
    assert lat["sha256"] == published["sha256"] and len(lat["rows"]) == len(published["rows"]) > 0
    assert real_doc["inputs"]["m76/wave2.tg2/run/exec_latency.json"] == sha(path)


# (b) the premises the above rest on, checked on the committed pilot itself (these pass on the baseline too)
@pytest.mark.parametrize("arm", PAIR)
def test_the_committed_pilot_schedule_is_the_pinned_draws_prefix(arm):
    sched = json.loads((TG2 / f"tg2-m76-{arm}-pilot.a1" / "schedule.json").read_text())
    schedules.check_tg2_p426(sched, W.draw_doc(), "pilot")


@pytest.mark.parametrize("arm", PAIR)
def test_the_committed_pilot_rows_bind_their_published_manifests(arm):
    att = TG2 / f"tg2-m76-{arm}-pilot.a1"
    harvest = json.loads((att / "HARVEST.json").read_text())
    published = {f["published"]: f["published_sha256"] for f in harvest["files"] if f.get("destination") == "main"}
    n = 0
    for rows in sorted((att / "pilot").glob("*.jsonl")):
        for line in rows.read_text().splitlines():
            row = json.loads(line)
            lang, item = row["id"].split("/", 1)
            run = row["final_tree"]["manifest"].rsplit("/", 2)[0].rsplit("/", 1)[1].rsplit(".", 1)[1]
            rel = f"benchmark/results/m76/wave2.tg2/{att.name}/evidence/{run}/{lang}__{item}.final_tree/manifest.json"
            assert published[rel] == row["final_tree"]["manifest_sha256"] == sha(W.REPO / rel)
            n += 1
    assert n == 4


# (b) the v8 record names the pinned draw and the pair B8-A8 is built for
def test_the_committed_v8_is_the_tg2_kv_pair():
    v8 = json.loads((TG2 / "run" / "v8_base.json").read_text())
    assert v8["lever"] == "kv" and v8["corpus"] == "tg2" and v8["arms"] == ["n16", "x"]
    assert v8["tg2_draw_sha256"] == schedules.TG2_DRAW_SHA256
    for arm in PAIR:
        chain = json.loads((TG2 / f"tg2-m76-{arm}-pilot.a1" / "chain.json").read_text())
        assert chain["tg2_leg"] == "pilot" and chain["frozen_record"]["sha256"] == v8["sha256"]
