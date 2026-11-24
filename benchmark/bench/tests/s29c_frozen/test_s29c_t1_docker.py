"""S29c T1 / acceptance 1 and 3 with the real tools and the real grader, one item per language (docker; skipped with a reason when
docker, the pinned `tg2-grader` image or the polyglot corpus is absent).

Per language, over the production preparation (`Tg2Corpus.prepare`) with the item's reference solution overlaid:
  * the command the prompt states (else the language's canonical command, see s29c_support) is run in the grader image, exactly as
    the agent would type it plus only what the network-less container needs (offline flags, Cargo.lock, node_modules);
  * what that run executed (the tool's own report: libtest summary, Gradle JUnit XML, jest summary, Catch summary) equals what
    the real grader grades on the same tree (production `Tg2Corpus.snapshot` + `Tg2Corpus.grade`), none skipped;
  * the production tamper check (`Tg2Corpus.tamper_reasons`) returns no reason after that run and after its ordinary variants;
  * a known negative (a solution that compiles but is wrong) fails locally AND in the grader.
Classes: rust / cpp parity tests are [FIX] (fail on the baseline: ignored / macro-guarded tests); javascript / java parity and every
tamper test are [INV] (hold on the baseline); the negatives are [INV]."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

from bench import tg2_grade as tg
from bench.token_turn_gate import TransportAbort
from bench.tests.s29c_frozen import s29c_support as S

DOCKER_SKIP = S.docker_skip_reason()
pytestmark = [pytest.mark.docker, pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")]

ITEMS = {"rust": "rust/accumulate", "javascript": "javascript/zebra-puzzle", "java": "java/zebra-puzzle", "cpp": "cpp/all-your-base"}
VARIANTS = {
    "rust": ["cargo build", "cargo test accumulate_empty", "cargo clean && cargo test"],
    "java": ["./gradlew compileJava", "./gradlew test --tests ZebraPuzzleTest", "./gradlew clean test"],
    "javascript": ["npx jest zebra", "npm test -- -t zebra", "npm test"],
    "cpp": ["cmake --build build", "rm -rf build && cmake -S . -B build && cmake --build build"],
}


def _scratch(factory, name):
    """A work root the grader may mount (never under TMPDIR, P361): the pytest tree when it qualifies, else `$STACK_WORKDIR`."""
    candidate = factory.mktemp(name)
    try:
        tg.refuse_tmp_source(candidate)
        return candidate
    except TransportAbort:
        pass
    root = os.environ.get("STACK_WORKDIR")
    if not root:
        pytest.skip("no work root outside TMPDIR (set STACK_WORKDIR)")
    path = Path(root) / "s29c-test" / (name + "-" + uuid.uuid4().hex[:8])
    path.mkdir(parents=True)
    return path


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    S.docker_env()
    return dict(corpus=S.make_corpus(), factory=tmp_path_factory, done={})


def _snapshot_and_grade(corpus, prepared, run, *, grade=True):
    private = run / "grading-private"
    private.mkdir(parents=True, exist_ok=True)
    with corpus.snapshot(prepared.work, private, 0) as snap:
        reasons = corpus.tamper_reasons(snap, prepared)
        outcome = None
        if grade and not reasons:
            outcome = corpus.grade(snap, prepared, private, tg.LocalDocker(), None, 0, 0, False)
    return reasons, outcome


def reference(ctx, lang):
    """prepared + reference, the stated command run, the tree snapshotted, tamper-checked and graded (cached per language)."""
    if lang in ctx["done"]:
        return ctx["done"][lang]
    corpus, item = ctx["corpus"], ITEMS[lang]
    slug = item.split("/", 1)[1]
    root = _scratch(ctx["factory"], f"ref-{lang}")
    prepared = S.prepare(corpus, item, root / "work")
    prompt = S.prompt_of(corpus, prepared)
    command = S.stated_or_canonical(lang, slug, prompt)
    S.apply_reference(prepared.work, lang, slug)
    rc, out = S.run_in_container(prepared.work, slug, lang, command)
    local = S.parse_local(lang, prepared.work, out)
    reasons, outcome = _snapshot_and_grade(corpus, prepared, root / "run")
    after_variants = []
    for variant in VARIANTS[lang]:
        vcmd = variant.replace("<slug>", slug)
        S.run_in_container(prepared.work, slug, lang, vcmd)
        after_variants.append((vcmd, _snapshot_and_grade(corpus, prepared, root / "run", grade=False)[0]))
    result = dict(item=item, slug=slug, command=command, rc=rc, out=out, local=local, tamper=reasons, outcome=outcome,
                  variants=after_variants, graded=S.graded_leaves(item), prepared=prepared)
    ctx["done"][lang] = result
    return result


@pytest.mark.parametrize("lang", S.LANGS)
def test_t1_the_stated_command_runs_the_full_graded_suite_locally(lang, ctx):
    """[FIX rust, cpp / INV javascript, java] the command the agent is told to run executes every graded test (none skipped /
    ignored / disabled) and, with the reference solution, all of them pass."""
    r = reference(ctx, lang)
    tail = r["out"][-1500:]
    if lang == "javascript" and r["local"] is None and r["rc"] != 0 and S.NETWORK_FAILURE.search(r["out"]):
        pytest.skip(f"the npm registry is unreachable from the container (not a statement about the workspace): {tail[-200:]!r}")
    assert r["local"] is not None, f"{r['item']}: no test summary in the output of `{r['command']}` (rc {r['rc']}):\n{tail}"
    local, graded = r["local"], r["graded"]
    assert r["rc"] == 0, f"`{r['command']}` exited {r['rc']}:\n{tail}"
    assert local["failed"] == 0 and local["skipped"] == 0, f"{r['item']}: `{r['command']}` skipped/failed tests: {local}\n{tail}"
    assert local["passed"] == len(graded), f"{r['item']}: `{r['command']}` ran {local['passed']} tests, the grader grades {len(graded)}"
    if "names" in local:
        assert local["names"] == graded, (sorted(local["names"] ^ graded)[:6])


@pytest.mark.parametrize("lang", S.LANGS)
def test_t1_the_real_grader_grades_the_same_tree_clean(lang, ctx):
    """[INV] the grader, on the snapshot of the tree the local run left behind, passes exactly the graded leaves (count and names)."""
    r = reference(ctx, lang)
    assert r["tamper"] == [], r["tamper"]
    outcome = r["outcome"]
    assert outcome is not None and outcome.tampered is False
    assert outcome.failing == 0, (r["item"], outcome.failing, outcome.leaves)
    assert set(outcome.leaves) == r["graded"] and len(outcome.leaves) == len(r["graded"])


@pytest.mark.parametrize("lang", S.LANGS)
def test_acc3_no_tamper_after_the_stated_command(lang, ctx):
    """[INV] acceptance 3: after the stated build-and-test command, `tamper_reasons` of the production corpus returns no reasons."""
    assert reference(ctx, lang)["tamper"] == []


@pytest.mark.parametrize("lang", S.LANGS)
def test_acc3_no_tamper_after_the_ordinary_variants(lang, ctx):
    """[INV] ... and after each ordinary variant (build only, run one test, clean rebuild)."""
    for command, reasons in reference(ctx, lang)["variants"]:
        assert reasons == [], (command, reasons)


# ------------------------------------------------------------------------------------------------- known negatives
def _mutate(lang, text, k):
    """The reference source with one function made wrong but still compiling (None when it has no k-th candidate)."""
    if lang == "cpp":
        hits = list(re.finditer(r"\breturn\s+[^;{}]+;", text))
        if k >= len(hits):
            return None
        return text[:hits[k].start()] + "return {};" + text[hits[k].end():]
    heads = list(re.finditer(r"\bpub\s+fn\s+\w+[^{;]*\{", text))
    if k >= len(heads):
        return None
    depth, i = 1, heads[k].end()
    while i < len(text) and depth:
        depth += text[i] == "{"
        depth -= text[i] == "}"
        i += 1
    return text[:heads[k].end()] + " todo!() " + text[i - 1:]


def _negative(ctx, lang):
    key = ("neg", lang)
    if key in ctx["done"]:
        return ctx["done"][key]
    corpus, item = ctx["corpus"], ITEMS[lang]
    slug = item.split("/", 1)[1]
    entry = corpus._loaded()["items"][item]
    if lang in ("cpp", "rust"):
        attempts = list(range(8))                       # the reference with its k-th `return <expr>;` -> `return {};` (cpp) / k-th `pub fn` body -> `todo!()` (rust)
    else:
        attempts = [None]                               # the untouched stub: compiles, every test fails
    last = None
    for k in attempts:
        root = _scratch(ctx["factory"], f"neg-{lang}-{k}")
        prepared = S.prepare(corpus, item, root / "work")
        prompt = S.prompt_of(corpus, prepared)
        command = S.stated_or_canonical(lang, slug, prompt)
        if k is not None:
            S.apply_reference(prepared.work, lang, slug)
            target = next(prepared.work / rel for rel in prepared.editable if rel.endswith(".cpp" if lang == "cpp" else ".rs"))
            mutated = _mutate(lang, target.read_text(), k)
            if mutated is None:
                break
            target.write_text(mutated)
        rc, out = S.run_in_container(prepared.work, slug, lang, command)
        local = S.parse_local(lang, prepared.work, out)
        private = root / "run" / "grading-private"
        private.mkdir(parents=True, exist_ok=True)
        with corpus.snapshot(prepared.work, private, 0) as snap:
            result = tg.grade_item(lang, snap.path, slug, private, prepared=prepared.prepared, solutions=list(prepared.editable),
                                   prepared_cargo_toml=entry.get("prepared_cargo_toml"), extra_crates=(), guard=tg.LocalDocker(),
                                   timeout=entry["timeout_s"])
        last = dict(item=item, command=command, rc=rc, out=out, local=local, grade=result, entry=entry, k=k)
        if result.outcome == "parsed":                  # compiled and graded: a wrong solution
            break
    ctx["done"][key] = last
    return last


@pytest.mark.parametrize("lang", S.LANGS)
def test_acc1_a_compiling_wrong_solution_fails_locally(lang, ctx):
    """[INV] acceptance 1: a solution that compiles but is wrong shows failures when the stated command is run."""
    n = _negative(ctx, lang)
    if n is None or n["grade"].outcome != "parsed":
        pytest.skip(f"{lang}: no compiling wrong solution could be built for {ITEMS[lang]} (grader outcome "
                    f"{getattr(n and n['grade'], 'outcome', None)!r})")
    local = n["local"]
    assert n["rc"] != 0 or (local is not None and local["failed"] > 0), (n["command"], n["rc"], local, n["out"][-800:])


@pytest.mark.parametrize("lang", S.LANGS)
def test_acc1_a_compiling_wrong_solution_fails_in_the_grader(lang, ctx):
    """[INV] acceptance 1: ... and in the grader."""
    n = _negative(ctx, lang)
    if n is None or n["grade"].outcome != "parsed":
        pytest.skip(f"{lang}: no compiling wrong solution could be built for {ITEMS[lang]}")
    assert n["grade"].failing(set(n["entry"]["leaves"])) >= 1
