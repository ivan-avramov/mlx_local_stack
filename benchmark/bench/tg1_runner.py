"""The tg1 configuration of the shared item core (P371, plan 3.1): thin.

Holds the tg1 constants (re-exported from the modules that now own them: the opencode adapter, the tg1 corpus, the run
configuration), the static `TG1_POLICY` / `TG1_EVIDENCE` bindings, the pre-P371 `identity()` recipe (kept as the
reference derivation the generation policy is a strict superset of) and `main` / `print_identity`, which delegate to
`bench.arm_runner` with `OpencodeArm(mode="tg1")` and the tg1 corpus. The item loop, the grade worker and the worker /
router checks live in `bench.arm_runner`."""

from __future__ import annotations

from pathlib import Path

from . import arm_opencode as ao
from . import arm_runner as core
from . import corpus_tg1
from . import identity_closure as ic
from . import run_config as rc

SCAFFOLD = ao.TG1_LABEL
REPO = Path(__file__).resolve().parents[2]
CARRIER = ao.CARRIER
PLUGIN = ao.PLUGIN
DATEFREEZE_PLUGIN = ao.DATEFREEZE_PLUGIN
GENERATION_DATA = ao.GENERATION_DATA
GENERATION_FIELDS = ao.GENERATION_FIELDS
generation_fields = ao.generation_fields
generation_identity_sha256 = ao.p311_generation_identity_sha256
tool_bounds_rejections = ao.tool_bounds_rejections
# The scoring tool's closure (informational: `--print-identity` shows it; it is NOT part of the generation identity and
# this module must not import the scoring modules). `bench.row_scores` holds the same two constants (tested equal).
SCORING_ENTRY = "benchmark/bench/tg1_score.py"
SCORING_DATA = ("benchmark/web_audit_prompt.md",)

# C147 section 2: each inject kind lowers exactly ONE constant (the table lives in run_config; the prompt addenda in the
# tg1 corpus).
INJECT_POLICY = rc.INJECT_POLICY
INJECT_ADDENDA = corpus_tg1.INJECT_ADDENDA
inject_addendum_sha256 = corpus_tg1.inject_addendum_sha256
effective_policy = core.effective_policy

TG1_POLICY = rc.PolicyTemplate(config_id="tg1", langs=("python", "go"))
TG1_EVIDENCE = rc.EvidencePolicy(namespace="opencode_transcripts", web_evidence=True, final_tree=True,
                                 worker_receipts="absent", item_barrier="off")


def inject_label(kind):
    return SCAFFOLD + "-inject:" + kind


def identity(p, selection, universe_sha, version, binary, *, inject=None):
    """The pre-P371 probe identity recipe (the legacy 14-key policy). The core completes its policy into the
    `GenerationPolicy` (a strict superset); this is the reference the superset test pins."""
    extra = dict(inject_addendum_sha256=inject_addendum_sha256(inject)) if inject else {}
    return ao.OpencodeArm(p, mode="tg1").identity(selection=selection, universe_sha=universe_sha, version=version,
                                                  binary=binary, inject=inject, **extra)


def _corpus(p, a):
    return corpus_tg1.Tg1Corpus(getattr(a, "universe", None) or core.DEFAULT_UNIVERSE, polyglot_root=p._polyglot_root,
                                polyglot_sha=p._polyglot_sha)


def print_identity(p, a):
    """`--print-identity`: the probe's provenance identity as JSON; never touches the router or a worker."""
    def scoring():
        return dict(scoring_code_sha256=ic.closure_sha256(SCORING_ENTRY, REPO, data=SCORING_DATA))

    return core.print_identity(p, ao.OpencodeArm(p, mode="tg1"), a, template=TG1_POLICY, corpus=_corpus(p, a),
                               extras=scoring)


def main(p, a):
    return core.main(p, ao.OpencodeArm(p, mode="tg1"), a, template=TG1_POLICY, evidence=TG1_EVIDENCE,
                     corpus=_corpus(p, a))

