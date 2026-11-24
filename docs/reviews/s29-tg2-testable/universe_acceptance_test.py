"""Designer's acceptance 1 + 3 over the WHOLE tg2 universe (docker): per item, the prompt's stated command runs exactly the
grader's graded leaves locally and all pass with the reference; the real grader grades the same tree clean; no tamper after the
command. Scratch (not part of the candidate)."""
import pytest
from bench.tests.s29c_frozen import s29c_support as S
from bench.tests.s29c_frozen import test_s29c_t1_docker as D

ALL = [i for lang in S.LANGS for i in S.items_of(lang)]


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    S.docker_env()
    return dict(corpus=S.make_corpus(), factory=tmp_path_factory, done={})


@pytest.mark.parametrize("item", ALL)
def test_universe_item(item, ctx, monkeypatch):
    lang = item.split("/", 1)[0]
    monkeypatch.setitem(D.ITEMS, lang, item)
    monkeypatch.setitem(D.VARIANTS, lang, [])          # variants are covered per language by the frozen test
    ctx["done"].pop(lang, None)
    r = D.reference(ctx, lang)
    assert r["local"] is not None and r["rc"] == 0, (item, r["rc"], r["out"][-600:])
    assert r["local"]["failed"] == 0 and r["local"]["skipped"] == 0, (item, r["local"])
    assert r["local"]["passed"] == len(r["graded"]), (item, r["local"]["passed"], len(r["graded"]))
    if "names" in r["local"]:
        assert r["local"]["names"] == r["graded"]
    assert r["tamper"] == [], (item, r["tamper"])
    o = r["outcome"]
    assert o is not None and not o.tampered and o.failing == 0 and set(o.leaves) == r["graded"], (item, o and o.failing)
