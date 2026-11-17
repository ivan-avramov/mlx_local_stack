"""Shared support for the M76 B4b-1 (spec `docs/specs/m76-b4b-tg2-runner.md` v5) test-writer tests; no tests here.

Everything the specification leaves open is a NAME GUESS and lives in `GUESSES` / `ATTR` below, in this one module. A test that
reaches a guessed name goes through `attr(...)` / `call(...)` / `make_corpus(...)`, which fail with a message that names the guess
(`SPELLING GUESS <key>: ...`) instead of an AttributeError: a different, equally valid spelling is then a one-line change here.

Class of each test (comment above it): (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.

Fixtures (`fixtures/m76_b4b1_fe/`, sha256-pinned by `grade-trees.manifest.json`, itself pinned below):
- `grade-trees/<lang>/<variant>/`: the RECORDED real `tg2_grade` output trees (reference, stub, compile, tampered per language;
  rust also alloc / flood / spin) of the pilot items rust/say, javascript/word-search, java/zipper, cpp/spiral-matrix. Only the 15 MB
  `rust/flood/.../execute.stdout` is dropped (the manifest lists it as `dropped`). Outcomes not recorded for real (`timeout`,
  `mem_kill`, `crash`, `storage_cap`) are SYNTHETIC `Tg2Grade` objects, labelled so in the tests that use them.
- `golden_tg1_*.json`: BASELINE outputs (tg1 surface, corpus prompt / identity, probe identity) written by running the tests on the
  baseline while the marker file `fixtures/m76_b4b1_fe/.record` existed (removed afterwards); compared otherwise.
- `grade-trees.manifest.json` pins every copied file; the copy itself is of the recorded trees named in the brief.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2]                 # .../benchmark
REPO = BENCH.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "m76_b4b1_fe"
TREES = FIX / "grade-trees"
TREES_MANIFEST = FIX / "grade-trees.manifest.json"
TREES_MANIFEST_SHA256 = "3fe79f4f2c01e9f7e2ff569627dac7a7fc9a4d3e63e0fb71dbdcef6d6ab5e75e"
RECORD = (FIX / ".record").exists()          # a marker file (present only while the baseline goldens are being written)

DRAW_PATH = BENCH / "m65" / "tg2_draw.json"
UNIVERSE_PATH = BENCH / "m65" / "tg2_universe.json"
TG2_DRAW_SHA256 = "82875e1d3da7ce71bd7750ff5729874eefc2e5a40772e1bf4f82e71d3cf444e3"      # spec §1 "Pins in code"
TG2_UNIVERSE_SHA256 = "2bf6add47237d2f1f4135013e47eae07f35e1e668b935e18ec2768b7baadc3e9"
POLYGLOT_SHA = "7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f"                                  # the universe's fingerprint
LANGS = ("rust", "javascript", "java", "cpp")
PILOT = {"rust": "rust/say", "javascript": "javascript/word-search", "java": "java/zipper", "cpp": "cpp/spiral-matrix"}
SCAFFOLD = "opencode-v2-web-tg2"
HELPER_TEXT = {                                   # spec §1 "Prompt (E1)": `H`, exactly one per language
    "rust": "Helper modules may go under src/; you may add [dependencies] from the offline crates listed in OFFLINE_CRATES.md "
            "to Cargo.toml.",
    "java": "Helper classes may go only in the solution's package.",
    "javascript": "Helper .js files may go beside the solution.",
    "cpp": "Helper .h / .cpp files may go beside the solution.",
}
KINDS = ("stall", "loop", "alloc")

# ---------------------------------------------------------------------------------------------------- the guesses
GUESSES = {
    "corpus-ctor": "`corpus_tg2.Tg2Corpus(universe_path, polyglot_root=<Path>, polyglot_sha=<callable path->sha>)` (tg1's signature)",
    "corpus-prompt": "`corpus.prompt(prepared, inject=None)` (the `Corpus` contract)",
    "corpus-snapshot": "`corpus.snapshot(work, private, boundary)` is a context manager (tg1's `sg.snapshot`)",
    "grade-outcome": "`corpus_tg2.grade_outcome(result, entry, *, seq, boundary, final)` (spec §1)",
    "grade-seam": "the docker-running inner `bench.tg2_grade.grade` is the fake seam; `grade_item` (strip, tamper check) runs for real",
    "identity-keys": "`corpus.identity()` keys: corpus_id, universe_sha256, draw_sha256, grader_version, image, grader_timeout_s",
    "chain-entry": "`benchmark/chains/c147/run_tg2_chain.py` exposes `parse_args(argv)`, `tg2_config(a)`, `CORE_SPECS`, `LANGS`, "
                   "`Chain` like `run_tg1_chain`",
    "chain-argv": "the chain entry's positional argument is dropped: `--leg pilot|s1|s2|reload` / `--rehearsal r2|r3` replace "
                  "`pilot|chain <session>`; the parsed namespace carries `mode`, `sessions`, `rehearsal` (bool), `inject`, `tg2_leg`",
    "strict-rows": "`p426_wave2.tg2_strict_rows(leg_roots, session)`: `leg_roots` = the harvested attempt roots of ONE arm (a list "
                   "of directories, each with chain.json, schedule.json and `<session>/*.jsonl`)",
    "schedule": "`schedules.tg2_p426(draw_doc, leg, model, predictor)` / `schedules.check_tg2_p426(schedule, draw_doc, leg)`",
    "freeze-flags": "`p426_freeze rehearsal|v8 ... --corpus tg2 ...` and `p426_wave2 positives --corpus tg2 --arm-worktree n16=<W> "
                    "--out <file>` parse (other required flags of those commands are not guessed)",
    "harvest-classify": "`p426_harvest.classify(kind, rel)`: grade-sequence files are `kind=\"evidence\"` (like tg1's go.stderr) at "
                        "`<item>.grades/seq-NNNN/<file>`; `.tg2-registry/*.json` is `kind=\"run\"` at "
                        "`grading-private/.tg2-registry/<file>.json`",
}


def attr(module, name, key):
    """`module.name`, or a failure naming the guess `key`."""
    if not hasattr(module, name):
        pytest.fail(f"SPELLING GUESS {key}: {module.__name__} has no `{name}` — {GUESSES.get(key, key)}", pytrace=False)
    return getattr(module, name)


def bench_mod(name, key=None):
    try:
        return importlib.import_module("bench." + name)
    except ImportError as exc:
        pytest.fail(f"bench.{name} cannot be imported ({exc}) — {GUESSES.get(key, 'the spec names this module')}", pytrace=False)


def load_path_module(rel, alias):
    path = REPO / rel
    if not path.is_file():
        pytest.fail(f"{rel} does not exist (spec §Scope: new file)", pytrace=False)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def chain_entry():
    return load_path_module("benchmark/chains/c147/run_tg2_chain.py", "run_tg2_chain_b4b1fe")


def tg1_chain_entry():
    return load_path_module("benchmark/chains/c147/run_tg1_chain.py", "run_tg1_chain_b4b1fe")


def probe_module():
    try:
        return importlib.import_module("run_tg2_probe")
    except ImportError as exc:
        pytest.fail(f"benchmark/run_tg2_probe.py cannot be imported ({exc})", pytrace=False)


# ---------------------------------------------------------------------------------------------------- data
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def draw_doc():
    return json.loads(DRAW_PATH.read_text())


def universe_doc():
    return json.loads(UNIVERSE_PATH.read_text())


def polyglot():
    base = os.environ.get("POLYGLOT_DIR") or str(Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark")
    root = Path(base)
    if not (root / "rust/exercises/practice").is_dir():
        pytest.skip("polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)")
    return root


def make_corpus(load=True):
    """The real `Tg2Corpus` on the committed universe and the real polyglot checkout (guess `corpus-ctor`)."""
    mod = bench_mod("corpus_tg2", "corpus-ctor")
    cls = attr(mod, "Tg2Corpus", "corpus-ctor")
    root = polyglot()
    try:
        corpus = cls(UNIVERSE_PATH, polyglot_root=root, polyglot_sha=lambda r: POLYGLOT_SHA)
    except TypeError as exc:
        pytest.fail(f"SPELLING GUESS corpus-ctor: {exc} — {GUESSES['corpus-ctor']}", pytrace=False)
    if load:
        corpus.load_universe()
    return corpus


def prepare_item(corpus, item, dest):
    return corpus.prepare(item, Path(dest))


def spec_text_variants(lang, slug):
    """`.docs/instructions.md` followed (blank line) by `.docs/instructions.append.md` when present (spec E1). The spec does not
    say how the first file's trailing newline joins the blank line, so every plausible reading is acceptable."""
    docs = polyglot() / lang / "exercises/practice" / slug / ".docs"
    first = (docs / "instructions.md").read_text(encoding="utf-8")
    extra = docs / "instructions.append.md"
    if not extra.is_file():
        return [first]
    second = extra.read_text(encoding="utf-8")
    return ["%s\n\n%s" % (first, second), "%s\n%s" % (first, second), "%s\n\n%s" % (first.rstrip("\n"), second)]


def expected_prompts(entry, lang, slug, inject=None):
    """Every acceptable exact prompt for the entry (spec E1): one per reading of the blank line (`spec_text_variants`)."""
    from bench import corpus_tg1
    S, T = ", ".join(entry["solutions"]), ", ".join(entry["tests"])
    out = []
    for spec in spec_text_variants(lang, slug):
        p = ("Implement the solution in %s so that the tests in %s pass. The specification follows.\n\n%s\n\n"
             "Do NOT modify the tests or the build files except as stated below. Do not create new files unless the "
             "specification requires them; %s" % (S, T, spec, HELPER_TEXT[lang]))
        if inject:
            p += " " + corpus_tg1.INJECT_ADDENDA[inject]
        out.append(p)
    return out


# ---------------------------------------------------------------------------------------------------- recorded trees
def trees_manifest():
    return json.loads(TREES_MANIFEST.read_text())


def tree_dir(lang, variant):
    return TREES / lang / variant


def recorded_summary(lang, variant):
    return json.loads((tree_dir(lang, variant) / "result.json").read_text())


def grades_dir(lang, variant):
    return next(tree_dir(lang, variant).glob("*.grades"))


def seq_dir(lang, variant, seq=1):
    return grades_dir(lang, variant) / ("seq-%04d" % seq)


def recorded_grade(lang, variant):
    """The `Tg2Grade` a real grade of the recorded tree returned, rebuilt from the recorded outputs with the grader's own parsers
    (`tg2_grade.parse_*`) and its recorded index / phases; `TransportAbort` for a recorded transport_abort (`spin`)."""
    from bench import tg2_grade as G
    from bench.token_turn_gate import TransportAbort
    summary = recorded_summary(lang, variant)
    slug = summary["item"].split("/", 1)[1]
    sd = seq_dir(lang, variant)
    if summary["outcome"] == "transport_abort":
        raise TransportAbort(summary["reason"])
    index = json.loads((sd / "index.json").read_text())
    phases = json.loads((sd / "phases.json").read_text()) if (sd / "phases.json").is_file() else {}      # a tamper receipt has none
    res = G.Tg2Grade(lang=lang, outcome=summary["outcome"], phases=phases.get("phases", []),
                     artifacts=index.get("artifacts", {}), image_id=phases.get("image_id", ""), reason=summary.get("reason", ""),
                     optional=G.OPTIONAL_LEAVES.get((lang, slug), frozenset()))
    if summary["outcome"] == "parsed":
        if lang == "java":
            parts = [G.parse_junit(p.read_text()) for p in sorted(sd.glob("junit-*.xml"))]
            res.leaves = G.merge_leaves(*parts)
        elif lang == "javascript":
            res.leaves = G.parse_jest((sd / "report.json").read_text(), "/work/" + slug)
        elif lang == "cpp":
            res.leaves = G.parse_junit((sd / "report.xml").read_text())
        else:
            res.leaves = G.parse_rust((sd / "execute.stdout").read_text() + (sd / "execute.stderr").read_text())
    else:
        res.all_failed = True
        if summary["outcome"] == "tampered":
            res.tamper_reasons = ["recorded tamper"]
    return res


def synthetic_grade(lang, outcome, slug):
    """A SYNTHETIC `Tg2Grade` for an outcome with no recorded real tree (timeout / mem_kill / crash / storage_cap)."""
    from bench import tg2_grade as G
    return G.Tg2Grade(lang=lang, outcome=outcome, all_failed=True, reason=outcome,
                      phases=[dict(step="execute", rc=124 if outcome == "timeout" else 1)])


def entry_of(item):
    return universe_doc()["items"][item]


# ---------------------------------------------------------------------------------------------------- golden files
def golden(name, value):
    """Record (M76_B4B1_RECORD=1) or compare a JSON-able baseline value against `fixtures/m76_b4b1_fe/<name>.json`."""
    path = FIX / (name + ".json")
    got = json.loads(json.dumps(value, sort_keys=True, default=str))
    if RECORD:
        path.write_text(json.dumps(got, sort_keys=True, indent=1) + "\n")
        return got, got
    if not path.is_file():
        pytest.fail(f"golden {path.name} is missing (record it on the baseline with M76_B4B1_RECORD=1)", pytrace=False)
    return got, json.loads(path.read_text())


def asdict(obj):
    return dataclasses.asdict(obj) if dataclasses.is_dataclass(obj) else dict(obj)
