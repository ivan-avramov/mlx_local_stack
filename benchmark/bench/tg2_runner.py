"""M76 B4b-1 (spec docs/specs/m76-b4b-tg2-runner.md v5, §1): the tg2 configuration of the shared item core — thin, like
`tg1_runner`: the fixed `TG2_POLICY`, the evidence policies (tg1's: the P426 one with the item barrier on), the tg2 corpus,
and `main` / `print_identity`, which delegate to `bench.arm_runner` with `OpencodeArm(mode="tg1", scaffold="tg2")`."""
from __future__ import annotations

from . import arm_opencode as ao
from . import arm_runner as core
from . import corpus_tg2
from . import run_config as rc
from .tg1_runner import TG1_EVIDENCE, TG1_P426_EVIDENCE

SCAFFOLD = ao.TG2_LABEL
CARRIER = ao.TG2_CARRIER
GENERATION_DATA = ao.TG2_GENERATION_DATA
TG2_POLICY = rc.PolicyTemplate(config_id="tg2", langs=("rust", "javascript", "java", "cpp"),
                               inject_allowed=rc.ALL_INJECT_KINDS)        # S27 §4.5: + the deterministic interrupt positive
TG2_EVIDENCE = TG1_EVIDENCE
TG2_P426_EVIDENCE = TG1_P426_EVIDENCE           # B2 spec 2: the item barrier on (the chain answers it)


def _corpus(p, a):
    return corpus_tg2.Tg2Corpus(getattr(a, "universe", None) or corpus_tg2.DEFAULT_UNIVERSE, polyglot_root=p._polyglot_root,
                                polyglot_sha=p._polyglot_sha)


def print_identity(p, a):
    """`--print-identity`: the probe's provenance identity as JSON; never touches the router or a worker."""
    return core.print_identity(p, ao.OpencodeArm(p, mode="tg1", scaffold="tg2"), a, template=TG2_POLICY, corpus=_corpus(p, a))


def main(p, a):
    p426 = getattr(a, "evidence", None) == "p426"
    return core.main(p, ao.OpencodeArm(p, mode="tg1", p426=p426, scaffold="tg2"), a, template=TG2_POLICY,
                     evidence=TG2_P426_EVIDENCE if p426 else TG2_EVIDENCE, corpus=_corpus(p, a))
