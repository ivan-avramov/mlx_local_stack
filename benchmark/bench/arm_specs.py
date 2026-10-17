"""Per-arm chain-side facts (M64 spec 5: "the chain runner is arm-aware only through this contract"): the scaffold label
rows carry, the probe entry, which manifest fields are pinned and how the generation composite is computed. Data only: no
client, scoring or tg1-runner import, so the chain (a lifecycle file) and `chain_ops.validate_leg` can use it without
loading a client. `tests/test_m64_chain_ops.py` pins each spec equal to its adapter's attributes."""
from __future__ import annotations

from dataclasses import dataclass

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

    def composite(self, runtime):
        return aa.arm_generation_sha256(self.arm_id, runtime, self.generation_fields)

    @property
    def evidence_dir(self):
        return "transcripts/" + self.arm_id


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
)

SPECS = {"oc": OC}      # Pi and dsh register theirs with their adapters (build step 5)


def spec_for(arm_id):
    try:
        return SPECS[arm_id]
    except KeyError:
        raise aa.ArmRefused(f"arm {arm_id!r} has no chain spec (not built or its snapshot was REJECTED)") from None
