"""P371 (plan 3.2): the three frozen configuration objects. Pure data: no corpus, adapter, client, grader or process import.

- `GenerationPolicy`: the dict hashed into `scaffold_policy_sha256` (the generation identity). A strict SUPERSET of the
  pre-P371 tg1 policy recipe (`tg1_runner.identity`): every old key keeps its derivation, plus `config_id`, `corpus_id`
  + `corpus_identity`, `langs`, `inject_allowed`, `budgets`, `watchdog`, `compaction` (and the M64 `arm` block).
  `tg1_generation_policy` derives the old keys exactly as `tg1_runner` does (gate / hygiene / grader constants are
  imported lazily, only when the caller does not pass them).
- `EvidencePolicy`: manifest `runtime.evidence_policy`, verified by the chain, NOT in the generation identity.
- `ChainConfig`: chain-entry configuration serialized canonically into `chain.json` and the lifecycle closure.

`as_dict()` returns JSON-native canonical dicts (tuples become lists); `sha256()` of a policy uses the legacy recipe
`json.dumps(d, sort_keys=True)` so the hash recipe itself is unchanged by P371 (only its content moved)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields

SCAFFOLD_TG1 = "opencode-v2-web-tg1"
PLUGIN_PROOF = "GET /api/integration awaits Plugin.awaitActivation"
GRADE_JOIN_OVERHEAD_S = 60                       # = tg1_runner.GRADE_JOIN_OVERHEAD_S (tested equal)
DEFAULT_BUDGETS = dict(thinking_budget=81920, max_tokens=102400, context="carrier")
COMPACTION = ("off", "on_accounted")
INJECT_KINDS = ("stall", "loop", "alloc")
# C147 section 2: each inject kind lowers exactly ONE constant (copy of `tg1_runner.INJECT_POLICY`, tested equal).
INJECT_POLICY = {
    "stall": {"gate": {"no_progress_requests": 4}, "hygiene": {}},
    "loop": {"gate": {"identical_calls": 3}, "hygiene": {}},
    "alloc": {"gate": {}, "hygiene": {"per_process": 512 * 1024**2}},
}
TRANSPORT_POLICIES = ("abort_restart", "incident_retry", "p426_continue")
RESUME_POLICIES = ("restart_load", "new_segment")
ARM_SWITCH_OPS = ("search_restart", "cache_reset", "warmup")
ARM_IDS = ("oc", "pi", "dsh")
WORKER_RECEIPTS = ("absent", "required")
ITEM_BARRIER = ("off", "on")
P426_CONFIG_ID = "tg1-p426"                      # B2 spec 2: the P426 mode's ChainConfig (distinct from `tg1`, flat record layout)


def canonical(value):
    """JSON-native deep copy (tuples -> lists, keys kept); raises on anything not JSON-serializable."""
    return json.loads(json.dumps(value, sort_keys=True))


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def effective_policy_overrides(kind):
    """The single-constant override of an inject kind (`{gate, hygiene}`)."""
    return INJECT_POLICY[kind]


def watchdog_on(*, limit_s, grace_s, toolwindows_sha256):
    return dict(mode="on", limit_s=limit_s, grace_s=grace_s, toolwindows_sha256=toolwindows_sha256)


WATCHDOG_OFF = dict(mode="off")


def _frozen_set(obj, name, value):
    object.__setattr__(obj, name, value)


# ---------------------------------------------------------------- generation policy
@dataclass(frozen=True)
class GenerationPolicy:
    config_id: str
    scaffold: str
    corpus_id: str
    corpus_identity: dict
    langs: tuple
    gate: dict
    hygiene: dict
    toolbounds_sha256: str
    noretry_sha256: str
    datefreeze_sha256: str
    carrier_sha256: str
    universe_sha256: str
    grader_version: str
    grader_timeout_s: dict
    grade_join_timeout_s: int
    plugin_proof: str
    env: dict
    toolchain: dict
    inject: dict | None = None
    inject_allowed: tuple = INJECT_KINDS
    budgets: dict = field(default_factory=lambda: dict(DEFAULT_BUDGETS))
    watchdog: dict = field(default_factory=lambda: dict(WATCHDOG_OFF))
    compaction: str = "off"
    arm: dict | None = None

    def __post_init__(self):
        if not (isinstance(self.config_id, str) and self.config_id):
            raise ValueError("config_id must be a nonempty string")
        if not self.langs:
            raise ValueError("langs must be nonempty")
        if self.compaction not in COMPACTION:
            raise ValueError(f"compaction must be one of {COMPACTION}")
        wd = self.watchdog
        if not isinstance(wd, dict) or wd.get("mode") not in ("off", "on"):
            raise ValueError("watchdog.mode must be off or on")
        if wd["mode"] == "on" and not all(wd.get(k) for k in ("limit_s", "grace_s", "toolwindows_sha256")):
            raise ValueError("an on-watchdog needs limit_s, grace_s and toolwindows_sha256")
        if wd["mode"] == "off" and set(wd) != {"mode"}:
            raise ValueError("an off-watchdog carries no other keys")
        if self.inject is not None and self.inject.get("kind") not in self.inject_allowed:
            raise ValueError(f"inject kind {self.inject.get('kind')!r} is not allowed here")
        for f in fields(self):                                  # isolate from the caller's mutable dicts
            value = getattr(self, f.name)
            _frozen_set(self, f.name, tuple(value) if f.name in ("langs", "inject_allowed") else
                        canonical(value) if isinstance(value, (dict, list)) else value)

    def as_dict(self):
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None and f.name in ("inject", "arm"):       # inject-only / M64-only keys
                continue
            out[f.name] = value
        return canonical(out)

    def canonical_json(self):
        return canonical_json(self.as_dict())

    def sha256(self):
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True).encode()).hexdigest()


def tg1_generation_policy(*, config_id, scaffold, corpus_id, corpus_identity, langs, toolbounds_sha256, noretry_sha256,
                          datefreeze_sha256, carrier_sha256, universe_sha256, env, toolchain, inject=None,
                          inject_allowed=INJECT_KINDS, budgets=None, watchdog=None, compaction="off", arm=None,
                          gate=None, hygiene=None, grader_version=None, grader_timeout_s=None,
                          grade_join_timeout_s=None, plugin_proof=PLUGIN_PROOF, inject_addendum_sha256=None):
    """The tg1-family generation policy. `gate` / `hygiene` / grader constants default to what `tg1_runner.identity`
    derives (token_turn_gate.POLICY and proc_guard.POLICY with the inject kind's single override; structured_grade
    VERSION / TIMEOUTS; the join timeout from them), imported lazily so this module stays pure. `inject` is the kind
    (or None); the inject block is `{kind, prompt_addendum_sha256}` as before (the caller passes the corpus prompt's sha)."""
    if gate is None or hygiene is None:
        from . import proc_guard as pg, token_turn_gate as tg
        g, h = dict(tg.POLICY), dict(pg.POLICY)
        if inject is not None:
            if inject not in INJECT_POLICY:
                raise ValueError(f"inject kind {inject!r} is not allowed here")
            g.update(INJECT_POLICY[inject]["gate"])
            h.update(INJECT_POLICY[inject]["hygiene"])
        gate = g if gate is None else gate
        hygiene = h if hygiene is None else hygiene
    if grader_version is None or grader_timeout_s is None:
        from . import structured_grade as sg
        grader_version = sg.VERSION if grader_version is None else grader_version
        grader_timeout_s = dict(sg.TIMEOUTS) if grader_timeout_s is None else grader_timeout_s
    if grade_join_timeout_s is None:
        grade_join_timeout_s = 2 * max(grader_timeout_s.values()) + GRADE_JOIN_OVERHEAD_S
    inject_block = None
    if inject is not None:
        if inject not in INJECT_POLICY:
            raise ValueError(f"inject kind {inject!r} is not allowed here")
        if not inject_addendum_sha256:
            raise ValueError("an inject policy needs the prompt addendum sha256 (from the corpus)")
        inject_block = dict(kind=inject, prompt_addendum_sha256=inject_addendum_sha256)
    return GenerationPolicy(
        config_id=config_id, scaffold=scaffold, corpus_id=corpus_id, corpus_identity=corpus_identity,
        langs=tuple(langs), gate=gate, hygiene=hygiene, toolbounds_sha256=toolbounds_sha256,
        noretry_sha256=noretry_sha256, datefreeze_sha256=datefreeze_sha256, carrier_sha256=carrier_sha256,
        universe_sha256=universe_sha256, grader_version=grader_version, grader_timeout_s=grader_timeout_s,
        grade_join_timeout_s=grade_join_timeout_s, plugin_proof=plugin_proof, env=env, toolchain=toolchain,
        inject=inject_block, inject_allowed=tuple(inject_allowed),
        budgets=dict(DEFAULT_BUDGETS if budgets is None else budgets),
        watchdog=dict(WATCHDOG_OFF if watchdog is None else watchdog), compaction=compaction, arm=arm)


@dataclass(frozen=True)
class PolicyTemplate:
    """The STATIC part of a `GenerationPolicy`, bound by a probe entry (config id, languages, inject kinds, budgets,
    watchdog, compaction). The runtime inputs (plugin / carrier shas, universe, toolchain, ...) complete it in `build`."""
    config_id: str
    langs: tuple
    inject_allowed: tuple = INJECT_KINDS
    budgets: dict = field(default_factory=lambda: dict(DEFAULT_BUDGETS))
    watchdog: dict = field(default_factory=lambda: dict(WATCHDOG_OFF))
    compaction: str = "off"

    def __post_init__(self):
        if not (isinstance(self.config_id, str) and self.config_id):
            raise ValueError("config_id must be a nonempty string")
        if not self.langs:
            raise ValueError("langs must be nonempty")
        if self.compaction not in COMPACTION:
            raise ValueError(f"compaction must be one of {COMPACTION}")
        if any(k not in INJECT_KINDS for k in self.inject_allowed):
            raise ValueError(f"inject_allowed must be drawn from {INJECT_KINDS}")
        wd = self.watchdog
        if not isinstance(wd, dict) or wd.get("mode") not in ("off", "on"):
            raise ValueError("watchdog.mode must be off or on")
        if wd["mode"] == "on" and not all(wd.get(k) for k in ("limit_s", "grace_s", "toolwindows_sha256")):
            raise ValueError("an on-watchdog needs limit_s, grace_s and toolwindows_sha256")
        _frozen_set(self, "langs", tuple(self.langs))
        _frozen_set(self, "inject_allowed", tuple(self.inject_allowed))
        _frozen_set(self, "budgets", canonical(self.budgets))
        _frozen_set(self, "watchdog", canonical(self.watchdog))

    def build(self, **runtime):
        """The complete `GenerationPolicy` (via `tg1_generation_policy`); `runtime` carries scaffold, corpus_id,
        corpus_identity and the shas / env / toolchain inputs."""
        return tg1_generation_policy(config_id=self.config_id, langs=self.langs, inject_allowed=self.inject_allowed,
                                     budgets=self.budgets, watchdog=self.watchdog, compaction=self.compaction,
                                     **runtime)


# ---------------------------------------------------------------- evidence policy
@dataclass(frozen=True)
class EvidencePolicy:
    namespace: str                      # logical relative evidence namespace: opencode_transcripts | transcripts/<arm>
    web_evidence: bool
    final_tree: bool
    worker_receipts: str                # absent | required
    item_barrier: str                   # off | on

    def __post_init__(self):
        ns = self.namespace
        if not (isinstance(ns, str) and ns and not ns.startswith("/") and ".." not in ns.split("/")):
            raise ValueError(f"evidence namespace must be a relative path, got {ns!r}")
        if self.web_evidence is not True:
            raise ValueError("web evidence is on for every config")
        if not isinstance(self.final_tree, bool):
            raise ValueError("final_tree must be a bool")
        if self.worker_receipts not in WORKER_RECEIPTS:
            raise ValueError(f"worker_receipts must be one of {WORKER_RECEIPTS}")
        if self.item_barrier not in ITEM_BARRIER:
            raise ValueError(f"item_barrier must be one of {ITEM_BARRIER}")

    def as_dict(self):
        return canonical({f.name: getattr(self, f.name) for f in fields(self)})

    def sha256(self):
        return hashlib.sha256(canonical_json(self.as_dict()).encode()).hexdigest()


# ---------------------------------------------------------------- chain config
@dataclass(frozen=True)
class ArmBinding:
    arm: str                            # oc | pi | dsh
    probe: str                          # repo-relative probe entry
    label: str                          # scaffold label of rows / manifests
    arm_spec: str                       # id of the chain-side arm spec (data, `arm_specs`)
    probe_data: tuple = ()              # repo-relative non-Python inputs of the probe's identity (generation data files)

    def __post_init__(self):
        _frozen_set(self, "probe_data", tuple(self.probe_data))

    def as_dict(self):
        return dict(arm=self.arm, probe=self.probe, label=self.label, arm_spec=self.arm_spec,
                    probe_data=list(self.probe_data))


@dataclass(frozen=True)
class ContractArtifact:
    arm: str
    path: str
    sha256: str

    def as_dict(self):
        return dict(arm=self.arm, path=self.path, sha256=self.sha256)


@dataclass(frozen=True)
class ChainConfig:
    config_id: str
    arms: tuple                         # ArmBinding, ...
    schedule: dict                      # {builder, params, [draw_sha256, tier]}
    out_root_family: str
    predictor: str
    arm_switch_ops: tuple
    transport_policy: str
    resume_policy: str
    snapshot_complete_required: bool
    contract_artifacts: tuple = ()      # ContractArtifact, ...

    def __post_init__(self):
        if not (isinstance(self.config_id, str) and self.config_id):
            raise ValueError("config_id must be a nonempty string")
        if not self.arms:
            raise ValueError("a chain needs at least one arm")
        if self.transport_policy not in TRANSPORT_POLICIES:
            raise ValueError(f"transport_policy must be one of {TRANSPORT_POLICIES}")
        if self.resume_policy not in RESUME_POLICIES:
            raise ValueError(f"resume_policy must be one of {RESUME_POLICIES}")
        if any(op not in ARM_SWITCH_OPS for op in self.arm_switch_ops):
            raise ValueError(f"arm_switch_ops must be drawn from {ARM_SWITCH_OPS}")
        if not (isinstance(self.schedule, dict) and self.schedule.get("builder") and "params" in self.schedule):
            raise ValueError("schedule needs a builder and params")
        if self.config_id == P426_CONFIG_ID:
            params = self.schedule["params"]
            if self.schedule["builder"] != "tg1" or params.get("p426") is not True or len(params.get("models") or ()) != 1:
                raise ValueError(f"{P426_CONFIG_ID} is the tg1 builder in P426 mode with exactly one model")
        if self.transport_policy == "p426_continue" and self.config_id != P426_CONFIG_ID:
            raise ValueError(f"p426_continue is the transport policy of {P426_CONFIG_ID} only")
        arm_ids = {b.arm for b in self.arms}
        for art in self.contract_artifacts:
            if art.arm not in arm_ids:
                raise ValueError(f"contract artifact names arm {art.arm!r} which the chain does not run")
        _frozen_set(self, "arms", tuple(self.arms))
        _frozen_set(self, "arm_switch_ops", tuple(self.arm_switch_ops))
        _frozen_set(self, "contract_artifacts", tuple(self.contract_artifacts))
        _frozen_set(self, "schedule", canonical(self.schedule))

    def as_dict(self):
        return canonical(dict(
            config_id=self.config_id, arms=[b.as_dict() for b in self.arms], schedule=self.schedule,
            out_root_family=self.out_root_family, predictor=self.predictor, arm_switch_ops=list(self.arm_switch_ops),
            transport_policy=self.transport_policy, resume_policy=self.resume_policy,
            snapshot_complete_required=self.snapshot_complete_required,
            contract_artifacts=[a.as_dict() for a in self.contract_artifacts]))

    def canonical_json(self):
        return canonical_json(self.as_dict())

    def sha256(self):
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()
