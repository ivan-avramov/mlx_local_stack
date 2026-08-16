"""The changed-lines model-name checker (`bench.modelnames`) — O24.

WHY A CHANGED-LINES CHECK AND NOT A REPO-WIDE ONE. AGENTS.md requires the full registry name in
reports, results, docs AND commits. Enforcement did not match: `test_docs_full_model_names.py` covers
only `docs/*.md` and only one two-word shorthand, so bare shorthand reached 4 of 5 commit messages in
a single session after the rule had been flagged. But a repo-wide assertion is not available either —
measured 2026-08-16 there are ~300 pre-existing sites (AGENTS.md 23, lab-notebook 156,
campaign-queue 86, open-questions 30, campaign-results 11). A test that fails on all of them gets
disabled, which is strictly worse than a narrow one that passes.

So the unit of enforcement is the ADDED LINE and the COMMIT MESSAGE: new violations are blocked, the
historical narrative is left alone, and the check converges as files are touched.

THE FALSE-POSITIVE CASES ARE THE WHOLE DESIGN PROBLEM. Every banned shorthand is also a SUBSTRING of
a legal registry name (`gemma` in `gemma-4-31B-it-qat-6bit`, `8bit` in `Qwen3.6-27B-MLX-8bit`,
`qat-6bit` in `gemma-4-31B-it-qat-6bit`, `Distill` in `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`). A
checker that flags those is one that gets switched off within a day, so each pattern is anchored to
reject the legal form.
"""
import pytest

from bench import modelnames as MN


# ------------------------------------------------------------------ it catches the real thing
@pytest.mark.parametrize("text", [
    "Nemotron ifeval n=200 completed",
    "Ornith wins every latency statistic",
    "the distill forfeits nothing to truncation",
    "gemma cannot be compared at a matched budget",
    "the MoE is faster",
    "the OptiQ recalls where QAT does not",
    "qat-6bit scored 90%",
    "the 8bit variant was the ceiling",
    # generalisation cases: these defeated the original blocklist entirely
    "the Lightning model beat the others",
    "Qwen3.6-27B was faster",          # AMBIGUOUS across four registry variants
    "the 30B-A3B candidate",
    "the 35B",
    "the uniform-4bit arm",
    "the Opus-Distill",
    "gemma-4 was slower",              # partial: two registry variants
    "the hybrid MoE candidate",
    "the qat model",
])
def test_flags_bare_shorthand(text):
    assert MN.violations(text), f"should have flagged: {text!r}"


# -------------------------------------------------- it does NOT fire on the legal registry names
@pytest.mark.parametrize("text", [
    "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit ifeval n=200",
    "Ornith-1.0-35B-mlx-uniform-4bit wins every latency statistic",
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit forfeits nothing",
    "gemma-4-31B-it-qat-6bit vs gemma-4-26B-A4B-it-OptiQ-4bit",
    "gemma-4-26B-A4B-it-QAT-MLX-4bit is the lmstudio MoE package",
    "Qwen3.6-27B-MLX-8bit and Qwen3.6-27B-UD-MLX-6bit-kv16",
    "benchmark/results/gemma-4-31b-it-6bit/mbppplus.score.json",
    "caslca/Ornith-1.0-35B-mlx-uniform-4bit",
    "mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit",
    # ordinary technical prose about a CLASS, which the rule does not govern
    "the 4-bit quantization reduces memory",
    "the MoE architecture routes 8 of 256 experts",
    "the diff format requires byte-exact matching",
    "prefill TTFT and decode tok/s are reported separately",
    "the docker container exited with code 1",
    "the M5 Max worker has 64GB and the M4 Pro 48GB",
])
def test_does_not_flag_full_names(text):
    assert MN.violations(text) == [], f"false positive on a legal name: {text!r}"


def test_allow_marker_lets_the_rule_document_itself():
    """AGENTS.md's own enumerated ban-list, and this test file, must remain editable.

    Without an escape the checker would forbid every line that NAMES a banned form, so the rule
    could never be written down. The marker is verbose enough not to be typed by accident and
    greppable (`git grep -n allow-shorthand`) so overuse is auditable.
    """
    assert MN.violations("banned: bare Ornith and gemma  <!-- allow-shorthand -->") == []
    assert MN.violations("banned: bare Ornith and gemma") != []


def test_this_module_and_its_test_are_exempt_by_path():
    """A file that DEFINES the patterns must be able to contain them.

    Learned the hard way: the first commit of the checker was blocked by the checker, 62 times,
    because its docstring and fixtures necessarily name every banned form. Exempting the two files
    by path beats ~60 inline markers that would bury the code.
    """
    diff = ("+++ b/benchmark/bench/tests/test_model_name_check.py\n"
            "@@ -1 +1 @@\n"
            "+    \"Nemotron and Ornith and gemma\",\n")
    assert MN.diff_violations(diff) == []
    # ...but an ordinary file with the same content is still caught.
    other = ("+++ b/docs/notes.md\n"
             "@@ -1 +1 @@\n"
             "+    Nemotron and Ornith and gemma\n")
    assert MN.diff_violations(other) != []


def test_generated_paths_cover_every_configgen_target():
    """A new generated config must not silently become uncommittable.

    Generated files carry the registry's human-facing `display_name` labels, which are UI text and
    not identifiers, so they are exempt. If someone adds a configgen target without adding it here,
    the first commit that regenerates it gets blocked for content it does not control — so this
    fails loudly instead.
    """
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(MN.__file__).resolve().parents[2]))
    from configgen.targets import BENCH_TARGETS, TARGETS

    declared = set(MN.GENERATED_PATHS)
    emitted = set()
    for _n, _e, dest in [*TARGETS, *BENCH_TARGETS]:
        emitted.update(dest.values() if isinstance(dest, dict) else [dest])
    assert emitted <= declared, f"configgen targets missing from GENERATED_PATHS: {emitted - declared}"


def test_a_family_reference_is_not_an_under_specified_instance():
    """"the gemma-4 family" names a GROUP on purpose — there is no single full name to substitute.

    Same class-vs-instance distinction the category rule already makes. Without this, any doc
    discussing a model family becomes uncommittable, which is how a checker earns a --no-verify
    habit.
    """
    assert MN.violations("the gemma-4 family shares a tokenizer") == []
    assert MN.violations("across the Qwen3.6-27B family") == []
    # ...but naming one member incompletely is still a violation.
    assert MN.violations("gemma-4 was slower") != []


def test_a_number_is_not_a_model_shorthand():
    """`"temperature": 1.0` was flagged, because 1.0 is a segment of a real model name.

    That would have fired on essentially every sampling change in the repo — the kind of
    false positive that gets a pre-commit hook deleted rather than fixed.
    """
    for text in ['"temperature": 1.0', '"top_p": 0.95', "effective_bits 4.9835",
                 "opencode 1.18.15", "mlx-optiq 0.4.21"]:
        assert MN.violations(text) == [], f"false positive on a number: {text!r}"


def test_does_not_flag_run_tags():
    """Run tags like m1f-distill-java are provenance labels, not model references."""
    assert MN.violations("m1f-distill-java and m1g-distill-java recovered 21 cases") == []
    assert MN.violations("archived as .t03 / .t04 rungs") == []


# ------------------------------------------------------------------------ diff mode
def test_staged_diff_checks_only_ADDED_lines():
    """Removing a shorthand must never be blocked — otherwise cleanup commits are impossible."""
    diff = (
        "diff --git a/x.md b/x.md\n"
        "--- a/x.md\n"
        "+++ b/x.md\n"
        "@@ -1,2 +1,2 @@\n"
        "-Ornith is the runner-up\n"
        "+Ornith-1.0-35B-mlx-uniform-4bit is the runner-up\n"
    )
    assert MN.diff_violations(diff) == []


def test_staged_diff_flags_an_added_violation_with_its_file_and_line():
    diff = (
        "diff --git a/docs/x.md b/docs/x.md\n"
        "--- a/docs/x.md\n"
        "+++ b/docs/x.md\n"
        "@@ -10,0 +11,1 @@\n"
        "+Nemotron beat both winners\n"
    )
    v = MN.diff_violations(diff)
    assert len(v) == 1
    assert v[0].path == "docs/x.md"
    assert v[0].line == 11, "must report the NEW-file line number so it is clickable"
    assert "Nemotron" in v[0].text


def test_diff_header_lines_are_not_themselves_violations():
    """`+++ b/gemma-4-...` style headers start with '+' but are not content."""
    diff = ("diff --git a/gemma.md b/gemma.md\n"
            "--- a/gemma.md\n"
            "+++ b/gemma.md\n"
            "@@ -1 +1 @@\n"
            "+all clear here\n")
    assert MN.diff_violations(diff) == []


# ------------------------------------------------------------------------ commit-message mode
def test_commit_message_comments_are_ignored():
    msg = ("feat(bench): use the full name Ornith-1.0-35B-mlx-uniform-4bit\n"
           "\n"
           "# Please enter the commit message. Lines starting with '#' are ignored.\n"
           "# On branch main -- Ornith would be a violation if comments counted\n")
    assert MN.message_violations(msg) == []


def test_commit_message_body_is_checked():
    msg = "fix(bench): something\n\nOrnith vs Nemotron on ifeval\n"
    v = MN.message_violations(msg)
    assert len(v) == 2, f"expected both shorthands, got {v}"


def test_verbose_commit_diff_is_ignored():
    """`git commit -v` appends the diff below a scissors line; it is not the author's prose."""
    msg = ("fix: x\n\n"
           "# ------------------------ >8 ------------------------\n"
           "diff --git a/x.md b/x.md\n"
           "+Ornith was here\n")
    assert MN.message_violations(msg) == []
