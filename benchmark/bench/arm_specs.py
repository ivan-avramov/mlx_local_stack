"""Per-arm chain-side facts (M64 spec 5: "the chain runner is arm-aware only through this contract"): the scaffold label
rows carry, the probe entry, which manifest fields are pinned and how the generation composite is computed. Data only: no
client, scoring or tg1-runner import, so the chain (a lifecycle file) and `chain_ops.validate_leg` can use it without
loading a client. `tests/test_m64_chain_ops.py` pins each spec equal to its adapter's attributes."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import arm_adapter as aa


@dataclass(frozen=True)
class ArmSpec:
    arm_id: str
    label: str                 # the scaffold label of rows / manifests (`runtime.scaffold`)
    probe: str                 # repo-relative probe entry
    generation_fields: tuple   # inputs of the per-arm generation composite
    runtime_pinned: tuple      # manifest fields pinned at the arm's first complete leg
    sha_fields: tuple          # mandatory 64-hex identity fields
    version_field: str         # the client-named version field of the manifest runtime
    # R30: how the chain extracts raw web evidence from this arm's hashed transcript, as DATA consumed by
    # `bench.web_evidence.extract` (a second client is a rules dict, not adapter code)
    web_evidence_rules: dict = field(default_factory=dict, hash=False)
    # P371 3b: the evidence policy (`run_config.EvidencePolicy.as_dict()`) the arm's probe records in every manifest's
    # `runtime.evidence_policy`; the chain verifies it at the barrier (data here, so the chain imports no adapter module)
    evidence_policy: dict = field(default_factory=dict, hash=False)
    # P371 phase 4 (C179): the non-Python inputs of the arm probe's identity (`probe_code_sha256` = the probe entry's import
    # closure + these files); the campaign core's per-arm probe closure is computed over them (= the adapter's
    # `generation_data`, tested equal)
    generation_data: tuple = ()

    def __post_init__(self):
        if not (isinstance(self.web_evidence_rules, dict) and self.web_evidence_rules):
            raise ValueError(f"arm {self.arm_id!r}: web_evidence_rules must be a nonempty dict (R30)")

    def composite(self, runtime):
        return aa.arm_generation_sha256(self.arm_id, runtime, self.generation_fields)

    @property
    def evidence_dir(self):
        return "transcripts/" + self.arm_id


OC_WEB_EVIDENCE_RULES = dict(
    schema=1, client="opencode",
    messages="messages", message_role_field="type", message_role="assistant",
    parts="content", part_type_field="type", part_type="tool",
    name_field="name", id_field="id", tool_names=["webfetch", "websearch", "shell"], name_contains=["search"],
    input_path=["state", "input"], output_paths=[["state", "output"], ["state", "content"]],
    status_path=["state", "status"])

OC = ArmSpec(
    arm_id="oc",
    label="opencode-v2-web-tg1c",
    probe="benchmark/run_oc_probe.py",
    generation_fields=("probe_code_sha256", "scaffold_policy_sha256", "opencode_version", "opencode_exe_sha256",
                       "opencode_bench_config_sha256", "carrier_source_sha256", "agent_system_sha256", "polyglot_sha",
                       "sampling_profile"),
    runtime_pinned=("scaffold_policy_sha256", "probe_code_sha256", "opencode_version", "opencode_exe_sha256",
                    "opencode_bench_config_sha256", "carrier_source_sha256", "agent_system_sha256", "polyglot_sha",
                    "universe_sha256", "generation_identity_sha256"),
    sha_fields=("scaffold_policy_sha256", "probe_code_sha256", "opencode_exe_sha256", "opencode_bench_config_sha256",
                "carrier_source_sha256", "universe_sha256", "generation_identity_sha256"),
    version_field="opencode_version",
    web_evidence_rules=OC_WEB_EVIDENCE_RULES,
    # = `arm_opencode.m64_evidence().as_dict()` (tested equal). Production worker receipts are `required` (plan 3.2); they
    # refuse before any spawn until the fork endpoint exists (P372); the chain answers the item barrier since P371 3b.
    evidence_policy=dict(namespace="transcripts/oc", web_evidence=True, final_tree=True, worker_receipts="required",
                         item_barrier="on"),
    generation_data=("benchmark/opencode_plugins/toolbounds.js", "benchmark/opencode_plugins/noretry.js",
                     "benchmark/opencode_plugins/datefreeze.js", "benchmark/opencode_bench_v2_web_tg1.json"),
)

SPECS = {"oc": OC}      # Pi and dsh register theirs with their adapters (build step 5)


def spec_for(arm_id):
    try:
        return SPECS[arm_id]
    except KeyError:
        raise aa.ArmRefused(f"arm {arm_id!r} has no chain spec (not built or its snapshot was REJECTED)") from None
