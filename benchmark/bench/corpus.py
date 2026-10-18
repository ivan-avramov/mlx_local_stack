"""P371 (plan 3.1): the Corpus contract and its typed records. Pure: no grader, process, client or adapter import.

A corpus owns everything item-specific: the frozen universe, the prepared tree, the prompt, the tamper check, the
grade, the "untouched solution fails" rule and the final-tree snapshot. The item core (`arm_runner`) and the chain
know a corpus only through this contract; entries inject the concrete corpus (`corpus_tg1` today, tg2 later).

Records:
- `PreparedItem`: work dir, the corpus entry, editable paths, the editable-tree baseline manifest (relative path ->
  sha256 at prepare time), the protected manifest, the whole prepared-tree manifest and the test paths.
- `GradeOutcome`: failing count (None iff the tree was tampered), the passing leaf set, `tampered`, `outcome` (`model`:
  the grade is a statement about the model's tree; `infrastructure`: it is not and must not be scored), grader resource
  flags, one phase record per grade taken, and the report artifacts.
- `FinalTree`: the content-addressed bytes of the graded editable tree plus its sha256 manifest."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path

OUTCOMES = ("model", "infrastructure")
RESOURCE_FLAGS = ("grader_mem_kill", "grader_oom")


@dataclass(frozen=True)
class PreparedItem:
    item_id: str                     # `<lang>/<name>`
    lang: str
    name: str
    work: Path
    entry: dict
    editable: tuple
    baseline: dict                   # editable relative path -> sha256 at prepare time
    protected: dict                  # protected relative path -> sha256
    prepared: dict                   # whole prepared tree: relative path -> sha256
    tests: tuple

    def __post_init__(self):
        if not (isinstance(self.item_id, str) and self.item_id.count("/") >= 1 and self.item_id.split("/", 1)[0]
                == self.lang and self.item_id.split("/", 1)[1] == self.name):
            raise ValueError(f"item id {self.item_id!r} must be `<lang>/<name>` matching lang and name")
        if not self.editable:
            raise ValueError("a prepared item needs at least one editable path")
        for rel in self.editable:
            if rel not in self.baseline:
                raise ValueError(f"editable path {rel!r} has no baseline hash")
        object.__setattr__(self, "editable", tuple(self.editable))
        object.__setattr__(self, "tests", tuple(self.tests))
        object.__setattr__(self, "work", Path(self.work))


@dataclass(frozen=True)
class GradeOutcome:
    failing: int | None
    leaves: tuple                    # sorted passing leaves of the universe
    tampered: bool
    outcome: str                     # model | infrastructure
    resources: dict
    phases: tuple                    # one dict per grade taken: seq, boundary, final, outcome
    reports: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}")
        if self.tampered != (self.failing is None):
            raise ValueError("failing is None exactly when the tree was tampered")
        if self.failing is not None and not (type(self.failing) is int and self.failing >= 0):
            raise ValueError("failing must be a non-negative integer")
        if set(self.resources) != set(RESOURCE_FLAGS):
            raise ValueError(f"resources must carry exactly {RESOURCE_FLAGS}")
        object.__setattr__(self, "leaves", tuple(self.leaves))
        object.__setattr__(self, "phases", tuple(self.phases))

    @property
    def passed(self):
        return self.failing == 0 and not self.tampered


@dataclass(frozen=True)
class FinalTree:
    root: Path
    files: dict                      # relative path -> sha256 of the file graded
    missing: tuple                   # editable paths absent at snapshot time
    manifest_sha256: str
    manifest_path: Path


class Corpus(abc.ABC):
    """The corpus contract (plan 3.1). `corpus_id` names it in policies and rows."""
    corpus_id: str

    @abc.abstractmethod
    def load_universe(self, path=None):
        """Load and verify the frozen universe; returns `(doc, sha256)`."""

    @abc.abstractmethod
    def items(self, lang):
        """Item ids (`<lang>/<name>`) of the corpus for one language, sorted."""

    @property
    @abc.abstractmethod
    def excluded(self):
        """Item ids the corpus refuses even when present in a universe."""

    @abc.abstractmethod
    def source_root(self, lang):
        """Directory holding the language's source exercises."""

    @abc.abstractmethod
    def prepare(self, item, dest):
        """Materialize `item` at `dest` and verify it against the frozen universe. Returns a `PreparedItem`."""

    @abc.abstractmethod
    def prompt(self, prepared, inject=None):
        """The user prompt (with the inject kind's addendum when given)."""

    @abc.abstractmethod
    def manifest(self, work):
        """The relative-path -> sha256 manifest of the work tree as the corpus's grader sees it (the core's change
        detector for grade coalescing); raises `OSError` / `ValueError` when the tree cannot be read."""

    @abc.abstractmethod
    def snapshot(self, work, private, boundary):
        """Context manager yielding a content-stable capture of the work tree (an object with `.path`, `.boundary`
        and `.manifest`) or None when no stable capture could be taken; captures live under `private`, never in the
        model's scratch."""

    @abc.abstractmethod
    def tampered(self, snap, prepared):
        """True when the snapshot (None = unsnapshottable) violates the protected inputs."""

    @abc.abstractmethod
    def grade(self, snap, prepared, private, guard, keep, seq, boundary, final):
        """Grade one snapshot. Returns a `GradeOutcome`; a tampered tree runs no grader."""

    @abc.abstractmethod
    def changed(self, prepared):
        """The "untouched solution fails" rule: did the model change an editable file."""

    @abc.abstractmethod
    def final_tree(self, prepared, dest):
        """Content-addressed copy of the editable files + sha256 manifest at `dest`. Returns a `FinalTree`."""

    @property
    @abc.abstractmethod
    def languages(self):
        ...

    @abc.abstractmethod
    def needs_docker(self, lang):
        ...

    def inject_addendum_sha256(self, kind):
        """sha256 of the prompt addendum of an injected-positive kind (the corpus prompt owns the text)."""
        raise NotImplementedError(f"corpus {self.corpus_id!r} has no inject addenda")

    def source_sha(self):
        """sha of the corpus source tree (the `polyglot_sha` of the generation composite); None when not applicable."""
        return None

    @abc.abstractmethod
    def identity(self):
        """Corpus sha, grader version, timeouts and image: the corpus part of the generation policy."""
