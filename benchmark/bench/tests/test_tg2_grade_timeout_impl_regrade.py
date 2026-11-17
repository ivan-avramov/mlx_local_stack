"""M65 tg2 timeout-evidence spec v1, acceptance 3: re-grade the recorded variants with the recorder's method
(`record_tg2_trees.py`, sha256 079bd39a…d440: the draw's pilot item per language as reference / stub / compile-failure /
tampered, Rust also spin / alloc / flood, graded at the universe timeout) and compare to its `SUMMARY.json`
(fixture `recorded_SUMMARY.json`, sha256 8ba69de7…e8ce). Every row must classify as recorded except the Rust spin, which
moves from `transport_abort` (runner-start marker absent) to `timeout` with every leaf failed.

Docker-marked; the spin variant runs at 5 s (G5), every other variant at the universe timeout."""

import json
import shutil
from pathlib import Path

import pytest

from bench import tg2_grade as tg
from bench.tests.test_tg2_grade import DOCKER_SKIP, POLYGLOT, _docker_env, tmp_path  # noqa: F401
from bench.token_turn_gate import TransportAbort

BENCH = Path(__file__).resolve().parents[2]
# G5: the spin variant is re-graded at 5 s (erratum v1a's Rust floor; the reference's slowest step is 0.53 s) instead of the
# universe's 180 s; the classification (`timeout`, every leaf failed) does not depend on the length of the wait.
SPIN_TIMEOUT = 5
SUMMARY = Path(__file__).parent / "fixtures/tg2_grade_timeout_impl/recorded_SUMMARY.json"
RUST_EXTRA = {
    "spin": "\n#[cfg(test)]\nmod zz_inject {\n    #[test]\n    fn zz_spin() { loop { std::hint::spin_loop(); } }\n}\n",
    "alloc": "\n#[cfg(test)]\nmod zz_inject {\n    #[test]\n    fn zz_alloc() { let mut v = Vec::new(); loop { v.push(vec![1u8; 1 << 26]); } }\n}\n",
    "flood": ("\n#[cfg(test)]\nmod zz_inject {\n    use std::io::Write;\n    #[test]\n    fn zz_flood() { let mut o = std::io::stdout();"
              " let line = [b'x'; 4096]; loop { let _ = o.write_all(&line); } }\n}\n"),
}


@pytest.mark.docker
@pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")
def test_recorded_variants_classify_as_recorded_and_the_rust_spin_becomes_a_timeout(tmp_path):
    from bench import tg2_materialize as mat
    _docker_env()
    draw = json.loads((BENCH / "m65/tg2_draw.json").read_text())
    universe = json.loads((BENCH / "m65/tg2_universe.json").read_text())["items"]
    guard, image_id, rows = tg.LocalDocker(), tg.pinned_image_id(), []
    for lang in ("rust", "javascript", "java", "cpp"):
        item = draw["languages"][lang]["permutation"][0]
        slug = item.split("/", 1)[1]
        entry = universe[item]
        plan = mat.read_plan(POLYGLOT, lang, slug)
        root = tmp_path / lang
        prep = mat.prepare_tree(POLYGLOT, lang, slug, root / "prepared")
        for var in ["reference", "stub", "compile", "tampered"] + (list(RUST_EXTRA) if lang == "rust" else []):
            tree, private, keep = root / var / "tree", root / var / "grading-private", root / var / f"{lang}__{slug}.grades"
            shutil.copytree(prep.tree, tree)
            private.mkdir(parents=True)
            sol = tree / entry["solutions"][0]
            if var == "reference":
                mat.apply_reference(POLYGLOT, plan, tree)
            elif var == "compile":
                sol.write_text(sol.read_text() + "\n@@@ not valid source @@@\n")
            elif var == "tampered":
                t = tree / entry["tests"][0]
                t.write_text(t.read_text() + "\n")
            elif var in RUST_EXTRA:
                mat.apply_reference(POLYGLOT, plan, tree)
                sol.write_text(sol.read_text() + RUST_EXTRA[var])
            try:
                r = tg.grade_item(lang, tree, slug, private, prepared=entry["prepared"], solutions=entry["solutions"],
                                  prepared_cargo_toml=entry.get("prepared_cargo_toml"), extra_crates=(), guard=guard,
                                  image_id=image_id, timeout=SPIN_TIMEOUT if var == "spin" else entry["timeout_s"],
                                  keep=keep, seq=1, boundary="final",
                                  final=True)
                res = dict(outcome=r.outcome, reason=r.reason, leaves=len(r.leaves), failing=r.failing(set(entry["leaves"])))
            except TransportAbort as exc:
                res = dict(outcome="transport_abort", reason=str(exc)[:300])
            rows.append(dict(item=item, variant=var, **res))
            print("TG2_REGRADE", json.dumps(rows[-1]), flush=True)
    recorded = json.loads(SUMMARY.read_text())
    expected = [dict(r) for r in recorded]
    for r in expected:
        if (r["item"], r["variant"]) == ("rust/say", "spin"):
            assert r["outcome"] == "transport_abort" and "marker absent" in r["reason"]
            r.clear()
            r.update(item="rust/say", variant="spin", outcome="timeout", reason="timeout", leaves=0,
                     failing=len(universe["rust/say"]["leaves"]))
    assert rows == expected
