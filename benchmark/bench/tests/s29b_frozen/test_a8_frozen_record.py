"""S29 B8-A8 rule 3.6 accepts the decider legs' frozen record (spec docs/specs/s29-a8-frozen-record.md, R1-R4).

Worlds are copies of the REAL tg2 records (`benchmark/results/m76/wave2.tg2/` + `B8.json`) in a temp tree (hard links, so a
copy is cheap; every edit replaces the file, never writes through a link). R2's negatives are edits of that copy; where the case
needs a validly sealed but wrong amendment it is re-sealed with `p426_hooks.seal` and the decider chains are re-pointed at it.

Class of each test (comment above it): fix = fails on the baseline, passes once the spec is met; invariant = holds before and
after (guards against over-loosening); new = new behaviour with no baseline counterpart.

Assertions are on outcomes (pair accepted / rejected with a rule-3.6 reason, document status, recorded inputs); no A8 result,
pass rate or verdict is read.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bench import p426_hooks as ph
from bench import p426_verify as V

BENCH = Path(__file__).resolve().parents[3]
REPO = BENCH.parent
RESULTS = BENCH / "results"
M76 = RESULTS / "m76"
REAL_TG2 = M76 / "wave2.tg2"
DECIDER = ("s1", "s2", "reload")
CONFIRM = ("s1", "s2")

needs_real = pytest.mark.skipif(
    not ((REAL_TG2 / "run" / "amendment.json").is_file() and (REAL_TG2 / "run" / "v8_base.json").is_file()
         and (M76 / "B8.json").is_file()),
    reason="the real tg2 records (run/amendment.json, run/v8_base.json, B8.json) are not present in this checkout")
pytestmark = needs_real


# ----------------------------------------------------------------------------------------------------------------- helpers
def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def rewrite(path, data):
    """Replace `path` with `data` (bytes or a JSON-able doc) without writing through a hard link."""
    path = Path(path)
    path.unlink()
    path.write_bytes(data if isinstance(data, bytes) else (json.dumps(data, sort_keys=True, indent=1) + "\n").encode())


class World:
    def __init__(self, tmp_path):
        self.rows = tmp_path / "benchmark" / "results"
        self.m76 = self.rows / "m76"
        self.tg2 = self.m76 / "wave2.tg2"
        self.m76.mkdir(parents=True)
        shutil.copytree(REAL_TG2, self.tg2, copy_function=link_or_copy, ignore=shutil.ignore_patterns("README.md"))
        link_or_copy(M76 / "B8.json", self.m76 / "B8.json")

    # -- the records
    @property
    def amendment_path(self):
        return self.tg2 / "run" / "amendment.json"

    @property
    def v8_path(self):
        return self.tg2 / "run" / "v8_base.json"

    def amendment(self):
        return json.loads(self.amendment_path.read_text())

    def chain_path(self, attempt):
        return self.tg2 / attempt / "chain.json"

    def chains(self, sessions):
        return sorted(p for p in self.tg2.glob("tg2-m76-*-*.a*/chain.json") if p.parent.name.split("-")[3].split(".")[0] in sessions)

    def set_frozen_sha(self, chain_path, sha):
        doc = json.loads(chain_path.read_text())
        doc["frozen_record"]["sha256"] = sha
        rewrite(chain_path, doc)

    def retarget_deciders(self, old, new):
        for p in self.chains(DECIDER):
            if json.loads(p.read_text())["frozen_record"]["sha256"] == old:
                self.set_frozen_sha(p, new)

    def reseal_amendment(self, **changes):
        """A validly sealed amendment with `changes`, the decider chains re-pointed at it (the only wrong thing is its content)."""
        old = self.amendment()
        new = ph.seal({k: v for k, v in dict(old, **changes).items() if k != "sha256"})
        assert ph.sealed_ok(new)
        rewrite(self.amendment_path, new)
        self.retarget_deciders(old["sha256"], new["sha256"])
        return new

    # -- the verdict-free view of B8-A8
    def b8_sha(self):
        return sha_file(self.m76 / "B8.json")

    def build(self):
        return V.verify_a8_kv(self.m76, self.b8_sha())


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def pairs(doc):
    return {p["pair"]: p for p in doc["pairs"]}


def r36(pair, *needles):
    """The pair's rule-3.6 reasons that mention every needle."""
    return [r for r in pair["reasons"] if "rule 3.6" in r and all(n in r for n in needles)]


def attempts_of(pair):
    return list(pair["attempts"].values())


# ------------------------------------------------------------------------------------------------ premises on the real records
# invariant: the real records have the shape the spec describes (pilot on the v8 base, deciders on the amendment, the amendment
# binding both) — the tests below stand on it
def test_the_real_records_have_the_described_shape(world):
    v8, am = json.loads(world.v8_path.read_text()), world.amendment()
    assert ph.sealed_ok(am) and ph.sealed_ok(v8)
    assert am["v8_base_sha256"] == v8["sha256"] != am["sha256"]
    dossiers = sorted((world.tg2 / "pairs").glob("pilot__*.json"))
    assert len(dossiers) == 1 and am["pilot_dossier_sha256"] == sha_file(dossiers[0])
    for p in world.chains(("pilot",)):
        assert json.loads(p.read_text())["frozen_record"]["sha256"] == v8["sha256"], p
    for p in world.chains(DECIDER):
        assert json.loads(p.read_text())["frozen_record"]["sha256"] == am["sha256"], p


# ------------------------------------------------------------------------------------------------------------------------ R1
# fix: every decider session's pair is accepted on the real records, with no rule-3.6 reason
@pytest.mark.parametrize("session", DECIDER)
def test_r1_decider_pair_on_the_amendment_is_accepted(world, session):
    got = pairs(world.build())[session]
    assert got["accepted"] is True and got["status"] == "accepted", got["reasons"]
    assert not r36(got, "frozen_record")


# fix: B8-A8 itself reads the decider (confirmatory sessions accepted -> complete)
def test_r1_document_is_complete_when_the_deciders_are_on_the_amendment(world):
    doc = world.build()
    assert doc["status"] == "complete", {s: p["reasons"] for s, p in pairs(doc).items() if p["reasons"]}


# invariant: the pilot (on the v8 base) is still accepted — the fix must not move the pilot onto the amendment
def test_r1_pilot_on_the_v8_base_is_accepted(world):
    pilot = pairs(world.build())["pilot"]
    assert pilot["accepted"] is True and pilot["reasons"] == [], pilot["reasons"]


# ------------------------------------------------------------------------------------------------------------------------ R2
# Each negative has a control above (the untampered copy is accepted), so a rejection here is caused by the tamper alone.

# new: no amendment published while decider attempts name one -> a rule-3.6 reason on every decider pair, never a crash
def test_r2_no_amendment_published(world):
    world.amendment_path.unlink()
    got = pairs(world.build())                                   # must not raise
    for s in DECIDER:
        assert got[s]["accepted"] is False and r36(got[s]), (s, got[s]["reasons"])
    assert got["pilot"]["accepted"] is True                      # the pilot never needed it
    assert world.build()["status"] == "incomplete"


# new: a tampered amendment (content edited, stale seal; the chains still name the stale seal) -> decider pairs rejected
def test_r2_unsealed_amendment(world):
    doc = world.amendment()
    doc["leg_deadline_s"] = dict(doc["leg_deadline_s"], s1=doc["leg_deadline_s"]["s1"] + 1.0)
    assert not ph.sealed_ok(doc)
    rewrite(world.amendment_path, doc)
    got = pairs(world.build())
    for s in DECIDER:
        assert got[s]["accepted"] is False and r36(got[s]), (s, got[s]["reasons"])
    assert world.build()["status"] == "incomplete"


# new: an amendment with no seal at all
def test_r2_amendment_without_a_seal(world):
    doc = {k: v for k, v in world.amendment().items() if k != "sha256"}
    rewrite(world.amendment_path, doc)
    got = pairs(world.build())
    for s in DECIDER:
        assert got[s]["accepted"] is False and r36(got[s]), (s, got[s]["reasons"])


# new: a validly sealed amendment that names another v8 base (the chains name this amendment)
def test_r2_amendment_naming_another_v8_base(world):
    world.reseal_amendment(v8_base_sha256="1" * 64)
    got = pairs(world.build())
    for s in DECIDER:
        assert got[s]["accepted"] is False and r36(got[s]), (s, got[s]["reasons"])
    assert world.build()["status"] == "incomplete"


# new: a validly sealed amendment that names another pilot dossier
def test_r2_amendment_naming_another_pilot_dossier(world):
    world.reseal_amendment(pilot_dossier_sha256="2" * 64)
    got = pairs(world.build())
    for s in DECIDER:
        assert got[s]["accepted"] is False and r36(got[s]), (s, got[s]["reasons"])
    assert world.build()["status"] == "incomplete"


# new: a validly sealed amendment missing the binding fields altogether
@pytest.mark.parametrize("field", ("v8_base_sha256", "pilot_dossier_sha256"))
def test_r2_amendment_without_a_binding_field(world, field):
    am = world.amendment()
    old = am["sha256"]
    new = ph.seal({k: v for k, v in am.items() if k not in ("sha256", field)})
    rewrite(world.amendment_path, new)
    world.retarget_deciders(old, new["sha256"])
    got = pairs(world.build())
    for s in DECIDER:
        assert got[s]["accepted"] is False and r36(got[s]), (s, got[s]["reasons"])


# invariant: a decider attempt naming a sha that is neither the v8 base's nor the amendment's -> that session rejected, naming it;
# the other sessions are unaffected
@pytest.mark.parametrize("bad", ("0" * 64, "not-a-sha"))
def test_r2_decider_attempt_naming_a_foreign_sha(world, bad):
    victim = pairs(world.build())["s1"]["attempts"]["x"]
    world.set_frozen_sha(world.chain_path(victim), bad)
    got = pairs(world.build())
    assert got["s1"]["accepted"] is False and r36(got["s1"], victim), got["s1"]["reasons"]
    assert got["s2"]["accepted"] is True and got["reload"]["accepted"] is True


# invariant: a decider attempt with no frozen_record block at all is a reason, not a crash
def test_r2_decider_attempt_without_a_frozen_record(world):
    victim = pairs(world.build())["s2"]["attempts"]["n16"]
    path = world.chain_path(victim)
    doc = json.loads(path.read_text())
    doc.pop("frozen_record")
    rewrite(path, doc)
    got = pairs(world.build())
    assert got["s2"]["accepted"] is False and r36(got["s2"], victim), got["s2"]["reasons"]


# new: a pilot attempt naming the amendment (everything else in order) -> the pilot pair is rejected, naming the attempt;
# a fix that simply accepts either sha for every session fails here
@pytest.mark.parametrize("arm", ("n16", "x"))
def test_r2_pilot_attempt_naming_the_amendment(world, arm):
    victim = pairs(world.build())["pilot"]["attempts"][arm]
    world.set_frozen_sha(world.chain_path(victim), world.amendment()["sha256"])
    got = pairs(world.build())
    assert got["pilot"]["accepted"] is False and r36(got["pilot"], victim), got["pilot"]["reasons"]
    assert all(got[s]["accepted"] is True for s in DECIDER)       # the deciders are untouched


# invariant: a pilot attempt naming a foreign sha is rejected
def test_r2_pilot_attempt_naming_a_foreign_sha(world):
    victim = pairs(world.build())["pilot"]["attempts"]["n16"]
    world.set_frozen_sha(world.chain_path(victim), "3" * 64)
    got = pairs(world.build())
    assert got["pilot"]["accepted"] is False and r36(got["pilot"], victim)


# new: the amendment may bind THIS campaign only — a decider on an amendment whose pilot dossier is not the accepted pilot's is
# rejected even though that amendment is sealed and names the right v8 base (the rule, not the file, ties it to the pilot)
def test_r2_amendment_dossier_must_be_the_accepted_pilots(world):
    dossier = next((world.tg2 / "pairs").glob("pilot__*.json"))
    assert world.amendment()["pilot_dossier_sha256"] == sha_file(dossier)       # control: it is this campaign's today
    world.reseal_amendment(pilot_dossier_sha256=hashlib.sha256(b"another campaign's pilot").hexdigest())
    got = pairs(world.build())
    assert not any(got[s]["accepted"] for s in DECIDER)


# ------------------------------------------------------------------------------------------------------------------------ R3
def amendment_inputs(doc):
    return {k: v for k, v in doc["inputs"].items() if k.endswith("wave2.tg2/run/amendment.json")}


# new: B8-A8 records the amendment it used (path + sha) among its inputs, beside the v8 base
def test_r3_the_amendment_is_a_recorded_input(world):
    doc = world.build()
    got = amendment_inputs(doc)
    assert list(got.values()) == [sha_file(world.amendment_path)], sorted(doc["inputs"])
    assert any(k.endswith("wave2.tg2/run/v8_base.json") for k in doc["inputs"])


# new: a later change to the amendment is detected the way the v8 base's is (the consumer's check refuses)
def test_r3_a_later_change_to_the_amendment_is_detected(world):
    doc = world.build()
    assert V.check_b8_a8(world.rows, doc, world.b8_sha(), REPO) == doc               # control: unchanged inputs verify
    rewrite(world.amendment_path, world.amendment_path.read_bytes() + b"\n")
    with pytest.raises(V.RefusalError):
        V.check_b8_a8(world.rows, doc, world.b8_sha(), REPO)


# invariant: the same check on the v8 base (what R3 says it must match)
def test_r3_a_later_change_to_the_v8_base_is_detected(world):
    doc = world.build()
    rewrite(world.v8_path, world.v8_path.read_bytes() + b"\n")
    with pytest.raises(V.RefusalError):
        V.check_b8_a8(world.rows, doc, world.b8_sha(), REPO)


# ------------------------------------------------------------------------------------------------------------------------ R4
def cli(module, args, home):
    env = {"PYTHONPATH": str(BENCH), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(home),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "MLX_BENCH_RESULTS": str(RESULTS)}
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=BENCH, capture_output=True, text=True,
                          timeout=3000, env=env)


@pytest.fixture(scope="module")
def real_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("r4")
    before = sha_file(M76 / "B8.json")
    proc = cli("bench.tests.m76_b4b2_frozen_cli",
               ["all", "--lever", "kv", "--pair", "n16,x", "--results-root", M76, "--rows-root", RESULTS,
                "--repo", REPO, "--out", out / "B8.json"], out)
    return out, proc, before


# fix: on the committed records B8-A8 is complete and all four pairs are accepted
def test_r4_real_records_b8_a8_complete_all_pairs_accepted():
    doc = V.verify_a8_kv(M76, sha_file(M76 / "B8.json"))
    assert doc["status"] == "complete", {s: p["reasons"] for s, p in pairs(doc).items() if p["reasons"]}
    assert sorted(pairs(doc)) == sorted(DECIDER + ("pilot",)) and len(doc["pairs"]) == 4
    assert all(p["accepted"] is True for p in doc["pairs"])


# fix: the CLI writes the same complete B8-A8 beside the regenerated B8
def test_r4_cli_writes_a_complete_b8_a8(real_run):
    out, proc, _ = real_run
    assert proc.returncode == 0, proc.stderr[-1500:]
    doc = json.loads((out / "B8-A8.json").read_text())
    assert doc["status"] == "complete" and all(p["accepted"] is True for p in doc["pairs"])
    assert doc["base_b8_sha256"] == sha_file(out / "B8.json")


# invariant: B8.json regenerates byte-identical to the committed one and the committed one was not touched
def test_r4_b8_json_is_byte_identical(real_run):
    out, proc, before = real_run
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert (out / "B8.json").read_bytes() == (M76 / "B8.json").read_bytes()
    assert sha_file(M76 / "B8.json") == before


# invariant: B8.json never includes A8 or the amendment
def test_r4_b8_json_does_not_include_a8():
    doc = json.loads((M76 / "B8.json").read_text())
    assert "A8" not in doc["axes"] and not [k for k in doc["inputs"] if "wave2.tg2" in k]
