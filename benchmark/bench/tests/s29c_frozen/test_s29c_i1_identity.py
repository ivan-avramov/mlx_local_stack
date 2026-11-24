"""S29c I1 (acceptance 5, identity part): the change produces a NEW tg2 scaffold / identity value; rows of the old and the new
identity never pool.

The pieces a tg2 row's identity is made of at the baseline: the scaffold label (`corpus_tg2.SCAFFOLD` == `arm_opencode.TG2_LABEL`),
the corpus identity dict (`Tg2Corpus.identity()`), the carrier file's sha, and from them the generation policy
(`run_config.GenerationPolicy.sha256()`, stamped into a manifest as `runtime.scaffold_policy_sha256`) which `provenance.is_compatible`
compares. The OLD identity is reconstructed from the baseline: label "opencode-v2-web-tg2", the seven baseline identity keys, the
carrier blob at the baseline commit (git). Classes: [FIX] fails on the baseline; [INV] holds on the baseline; [NEW] no baseline
counterpart. The 'binds the prompt' test is the most mechanism-sensitive of the suite (it needs the identity to be derived from
the live helper sentences at call time); it is labelled so."""
from __future__ import annotations

import hashlib
import subprocess

import pytest

from bench import arm_opencode as ao
from bench import corpus_tg2 as ct
from bench import provenance as P
from bench import run_config as rc
from bench.tests.s29c_frozen import s29c_support as S

OLD_LABEL = "opencode-v2-web-tg2"
OLD_KEYS = ("corpus_id", "universe_sha256", "draw_sha256", "grader_version", "grader_timeout_s", "image", "excluded")


def _old_carrier_sha():
    raw = subprocess.run(["git", "-C", str(S.REPO), "show", f"{S.BASELINE}:benchmark/opencode_bench_v2_web_tg2.json"],
                         capture_output=True)
    if raw.returncode:
        pytest.skip("the baseline commit is not in this repository")
    return hashlib.sha256(raw.stdout).hexdigest()


def _policy(label, identity, carrier_sha):
    return rc.PolicyTemplate(config_id="tg2", langs=S.LANGS).build(
        scaffold=label, corpus_id="tg2", corpus_identity=identity, toolbounds_sha256="1" * 64, noretry_sha256="2" * 64,
        datefreeze_sha256="3" * 64, carrier_sha256=carrier_sha, universe_sha256=identity["universe_sha256"],
        env={"PATH": "/usr/bin"}, toolchain={"t": 1}, grader_version=identity["grader_version"],
        grader_timeout_s=identity["grader_timeout_s"], grade_join_timeout_s=62)


@pytest.fixture(scope="module")
def corpus():
    return ct.Tg2Corpus()


def _live(corpus):
    return ct.SCAFFOLD, corpus.identity(), hashlib.sha256(S.CARRIER.read_bytes()).hexdigest()


def test_i1_the_scaffold_and_corpus_identity_are_not_the_baselines(corpus):
    """[FIX] the (scaffold label, corpus identity) pair differs from the baseline's - the identity is new, not only the carrier file."""
    label, identity, _sha = _live(corpus)
    old_identity = {k: identity[k] for k in OLD_KEYS if k in identity}
    assert (label, identity) != (OLD_LABEL, old_identity), "scaffold label and corpus identity are exactly the baseline's"


def test_i1_the_scaffold_label_is_one_value_everywhere(corpus):
    """[INV] the corpus, the arm and the chain agree on the tg2 label (a new label must be changed everywhere at once)."""
    from bench import chain_ops
    assert ct.SCAFFOLD == ao.TG2_LABEL == chain_ops.TG2_SCAFFOLD


def test_i1_the_generation_policy_hash_differs_from_the_baselines(corpus):
    """[FIX] the policy a new tg2 row stamps differs from the policy an old row stamped."""
    label, identity, sha = _live(corpus)
    new = _policy(label, identity, sha)
    old = _policy(OLD_LABEL, {k: identity[k] for k in OLD_KEYS if k in identity}, _old_carrier_sha())
    assert new.sha256() != old.sha256()


def test_i1_the_identity_is_deterministic(corpus):
    """[INV] two calls give the same identity (a new identity is a value, not a nonce)."""
    assert corpus.identity() == ct.Tg2Corpus().identity()


@pytest.mark.parametrize("lang", S.LANGS)
def test_i1_the_identity_binds_the_helper_sentences(lang, monkeypatch):
    """[NEW, mechanism-sensitive] changing the language's helper sentence changes the (label, corpus identity) pair: the identity binds the prompt."""
    before = _live(ct.Tg2Corpus())[:2]
    monkeypatch.setitem(ct.HINTS, lang, ct.HINTS[lang] + " (changed)")
    after = _live(ct.Tg2Corpus())[:2]
    assert before != after, "the identity does not change when the helper sentence does"


def _manifest(policy_sha):
    return {"fingerprint_version": 1, "sampling_profile": "deployed", "sampling": {}, "kv": {},
            "runtime": {"client": "opencode", "scaffold_policy_sha256": policy_sha}}


def test_i1_rows_of_the_old_and_new_identity_do_not_pool(corpus):
    """[FIX] `provenance.is_compatible` (the pooling / resume refusal) sees a row of the old identity and a row of the new one as
    different, and two rows of the same identity as compatible."""
    label, identity, sha = _live(corpus)
    new = _policy(label, identity, sha).sha256()
    old = _policy(OLD_LABEL, {k: identity[k] for k in OLD_KEYS if k in identity}, _old_carrier_sha()).sha256()
    assert P.is_compatible(_manifest(new), _manifest(new)) is True
    assert P.is_compatible(_manifest(old), _manifest(old)) is True
    assert P.is_compatible(_manifest(old), _manifest(new)) is False
    assert P.is_compatible(_manifest(new), _manifest(old)) is False
