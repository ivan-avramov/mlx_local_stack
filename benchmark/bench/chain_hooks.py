"""P371 (plan 3.1, R13 R23): chain-owned hooks, OUTSIDE every probe closure (never imported by a probe entry).

`before_attempt(slot)` runs at an item's `ready` barrier (D2 health / canary later): `accept`, or a
`pre_spawn_incident(cause)` (an infrastructure failure: the chain writes `.stop` before the spawn and applies the
config's transport policy to the slot). `after_attempt(slot, done)` runs at the `done` barrier: `accept`,
`rerun_same_slot(reason)` (P201 cheat: the chain stops the probe after this item, resets the cache and re-runs the slot
with re-run index + 1, same seed) or `block(reason)` (P201 unclear: the chain stops for the operator). The default
hooks accept everything. Dispositions are persisted by the chain (`chain.json.progress`) BEFORE the barrier file."""
from __future__ import annotations

from dataclasses import dataclass

KINDS = ("accept", "rerun_same_slot", "block", "pre_spawn_incident", "invalidate", "harness_fault", "accounting_fault", "hold")
BEFORE_KINDS = ("accept", "pre_spawn_incident", "invalidate")
AFTER_KINDS = ("accept", "rerun_same_slot", "block", "invalidate", "harness_fault", "accounting_fault", "hold")
# S27 §5.3 / §8.2: an accounting fault keeps the item's outcome (an accepted attempt, flagged); a hold stops at an accepted
# item. §5.2 / §5.7: a harness fault is its own attempt disposition (the same slot reruns once, rerun index 1).
_SLOT_DISPOSITION = {"accept": "accepted", "rerun_same_slot": "cheat", "block": "unclear", "harness_fault": "harness_fault",
                     "accounting_fault": "accepted", "hold": "accepted"}


class HookInfrastructureError(Exception):
    """A hook could not decide because infrastructure failed (health probe unreachable ...): the transport class."""

    def __init__(self, cause, *, not_evaluated=()):
        super().__init__(cause)
        self.cause = cause
        self.not_evaluated = tuple(not_evaluated)     # S27 X16: the checks the failing hook never reached (recorded only)


@dataclass(frozen=True)
class Disposition:
    kind: str
    reason: str | None = None            # rerun_same_slot / block / invalidate
    cause: str | None = None             # pre_spawn_incident

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"disposition kind must be one of {KINDS}, got {self.kind!r}")
        need = {"rerun_same_slot": "reason", "block": "reason", "pre_spawn_incident": "cause",
                "invalidate": "reason", "harness_fault": "reason", "accounting_fault": "reason",
                "hold": "reason"}.get(self.kind)
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

    @classmethod
    def invalidate(cls, reason):
        """B2 (P426): a barrier check failed; the leg is INVALID (persisted, `.stop`, rc 2)."""
        return cls("invalidate", reason=reason)

    @classmethod
    def harness_fault(cls, reason):
        """S27 §5.2: a pre-outcome harness fault; the same item reruns once (same seed) after the cache reset and settle."""
        return cls("harness_fault", reason=reason)

    @classmethod
    def accounting_fault(cls, reason):
        """S27 §5.3: a post-outcome accounting check failed after §4; the outcome is kept, a sidecar sealed, no rerun."""
        return cls("accounting_fault", reason=reason)

    @classmethod
    def hold(cls, reason):
        """S27 §8.2: hold at this accepted item boundary (`.stop` cleanup-only; the chain waits for the release)."""
        return cls("hold", reason=reason)

    @property
    def stops_probe(self):
        return self.kind not in ("accept", "accounting_fault")

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

    def before_attempt(self, slot, context=None):
        return Disposition.accept()

    def after_attempt(self, slot, done, context=None):
        return Disposition.accept()

    @staticmethod
    def _checked(result, allowed, hook):
        if not isinstance(result, Disposition):
            raise TypeError(f"{hook} must return a Disposition, got {result!r}")
        if result.kind not in allowed:
            raise ValueError(f"{hook} may only return {allowed}, got {result.kind}")
        return result

    def run_before(self, slot, context=None, systemic=False):
        """`context` (P426: ready record, row, load context) is passed only when given: a legacy hook keeps `(slot)`.
        `systemic`: a `HookInfrastructureError` propagates (the chain stops the leg) instead of a `pre_spawn_incident`."""
        try:
            result = self.before_attempt(slot) if context is None else self.before_attempt(slot, context)
        except HookInfrastructureError as exc:
            if systemic:
                raise
            return Disposition.pre_spawn_incident(exc.cause)
        return self._checked(result, BEFORE_KINDS, "before_attempt")

    def run_after(self, slot, done, context=None):
        result = self.after_attempt(slot, done) if context is None else self.after_attempt(slot, done, context)
        return self._checked(result, AFTER_KINDS, "after_attempt")
