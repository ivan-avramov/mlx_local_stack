"""P371 (plan 3.1, R13 R23): chain-owned hooks, OUTSIDE every probe closure (never imported by a probe entry).

`before_attempt(slot)` runs at an item's `ready` barrier (D2 health / canary later): `accept`, or a
`pre_spawn_incident(cause)` (an infrastructure failure: the chain writes `.stop` before the spawn and applies the
config's transport policy to the slot). `after_attempt(slot, done)` runs at the `done` barrier: `accept`,
`rerun_same_slot(reason)` (P201 cheat: the chain stops the probe after this item, resets the cache and re-runs the slot
with re-run index + 1, same seed) or `block(reason)` (P201 unclear: the chain stops for the operator). The default
hooks accept everything. Dispositions are persisted by the chain (`chain.json.progress`) BEFORE the barrier file."""
from __future__ import annotations

from dataclasses import dataclass

KINDS = ("accept", "rerun_same_slot", "block", "pre_spawn_incident")
BEFORE_KINDS = ("accept", "pre_spawn_incident")
AFTER_KINDS = ("accept", "rerun_same_slot", "block")
_SLOT_DISPOSITION = {"accept": "accepted", "rerun_same_slot": "cheat", "block": "unclear"}


class HookInfrastructureError(Exception):
    """A hook could not decide because infrastructure failed (health probe unreachable ...): the transport class."""

    def __init__(self, cause):
        super().__init__(cause)
        self.cause = cause


@dataclass(frozen=True)
class Disposition:
    kind: str
    reason: str | None = None            # rerun_same_slot / block
    cause: str | None = None             # pre_spawn_incident

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"disposition kind must be one of {KINDS}, got {self.kind!r}")
        need = {"rerun_same_slot": "reason", "block": "reason", "pre_spawn_incident": "cause"}.get(self.kind)
        for name in ("reason", "cause"):
            value = getattr(self, name)
            if name == need and not (isinstance(value, str) and value):
                raise ValueError(f"a {self.kind} disposition needs a nonempty {name}")
            if name != need and value is not None:
                raise ValueError(f"a {self.kind} disposition carries no {name}")

    @classmethod
    def accept(cls):
        return cls("accept")

    @classmethod
    def rerun_same_slot(cls, reason):
        return cls("rerun_same_slot", reason=reason)

    @classmethod
    def block(cls, reason):
        return cls("block", reason=reason)

    @classmethod
    def pre_spawn_incident(cls, cause):
        return cls("pre_spawn_incident", cause=cause)

    @property
    def stops_probe(self):
        return self.kind != "accept"

    def as_dict(self):
        out = dict(kind=self.kind)
        for name in ("reason", "cause"):
            if getattr(self, name) is not None:
                out[name] = getattr(self, name)
        return out

    @classmethod
    def from_dict(cls, doc):
        if not isinstance(doc, dict) or set(doc) - {"kind", "reason", "cause"}:
            raise ValueError(f"not a disposition record: {doc!r}")
        return cls(kind=doc.get("kind"), reason=doc.get("reason"), cause=doc.get("cause"))


def slot_disposition(disposition):
    """The per-slot-attempt vocabulary of `chain_rows` (accepted | cheat | unclear; `exhausted` is the chain's call)."""
    try:
        return _SLOT_DISPOSITION[disposition.kind]
    except KeyError:
        raise ValueError(f"a {disposition.kind} disposition has no attempt row to classify") from None


class ChainHooks:
    """Default: no-op `accept`. Subclasses override the two hooks; the chain calls `run_before` / `run_after`."""

    def before_attempt(self, slot):
        return Disposition.accept()

    def after_attempt(self, slot, done):
        return Disposition.accept()

    @staticmethod
    def _checked(result, allowed, hook):
        if not isinstance(result, Disposition):
            raise TypeError(f"{hook} must return a Disposition, got {result!r}")
        if result.kind not in allowed:
            raise ValueError(f"{hook} may only return {allowed}, got {result.kind}")
        return result

    def run_before(self, slot):
        try:
            result = self.before_attempt(slot)
        except HookInfrastructureError as exc:
            return Disposition.pre_spawn_incident(exc.cause)
        return self._checked(result, BEFORE_KINDS, "before_attempt")

    def run_after(self, slot, done):
        return self._checked(self.after_attempt(slot, done), AFTER_KINDS, "after_attempt")
