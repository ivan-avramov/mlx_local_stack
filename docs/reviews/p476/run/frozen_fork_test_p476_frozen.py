"""P476 — adversarial frozen tests for the registry prune (fork side, spec v2).

These tests pin the spec's fork-side acceptance criteria
(`docs/specs/p476-registry-prune.md` v2 §S4 / AC5). They are written against the spec and its
interfaces BEFORE the implementation exists; tests that need the prune will fail on the
baseline (the 11-entry sibling registry / 7-entry qualify.ENTRIES) — that is expected and
reported.

Each test states its class in its docstring:
  - "reproduces a failure the spec fixes" : fails on the baseline, passes after P476.
  - "preserves an invariant"               : passes on the baseline and after P476.
  - "exercises new behaviour"              : covers behaviour the spec introduces.

Nothing here needs a GPU, model, network or server.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- locations
# This file is <fork>/mlx_vlm/tests/test_p476_frozen.py -> fork repo root is parents[2].
REPO = Path(__file__).resolve().parents[2]
DEV = REPO / "dev"
sys.path.insert(0, str(DEV))

from p369_phase2 import qualify  # noqa: E402
from p369_phase2 import registry_states as rs  # noqa: E402

BASELINE_COMMIT = "0f30522c"  # the fork baseline this copy is checked out at
SIBLING_REGISTRY = REPO.parent / "mlx_local_stack" / "main_models.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The four MTP-certified entries whose ON/OFF states the fixture pins.
MTP_FOUR = (
    "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed",
    "Qwen3.8-27B-mlx-uniform-4bit",
    "Ornith-1.0-35B-mlx-uniform-4bit",
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
)
# The three MTP entries qualify.ENTRIES keeps after the prune (S4).
MTP_THREE = (
    "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed",
    "Qwen3.8-27B-mlx-uniform-4bit",
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
)
# The four served entries the prune drops from ENTRIES (and from the reference table).
PRUNED_SERVED = (
    "Qwen3.8-27B-static-mixed-4bit",
    "Qwen3.8-27B-OptiQ-4.5bpw-mixed",
    "Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit",
    "Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit",
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True,
    ).stdout


def _fixture_verbatim() -> str:
    return rs.fixture_text(FIXTURES)


# =========================================================================== S4 — qualify.ENTRIES
class TestQualifyEntries:
    def test_entries_is_exactly_the_three_mtp_entries(self):
        """reproduces a failure the spec fixes: `qualify.ENTRIES` == the three MTP entries."""
        assert set(qualify.ENTRIES) == set(MTP_THREE), sorted(qualify.ENTRIES)

    def test_no_pruned_served_entry_in_entries(self):
        """reproduces a failure the spec fixes: the four served (pruned) entries are gone."""
        assert not (set(qualify.ENTRIES) & set(PRUNED_SERVED)), sorted(
            set(qualify.ENTRIES) & set(PRUNED_SERVED))

    def test_entries_scope_not_widened(self):
        """reproduces a failure the spec fixes (S4): no entry is added — the three MTP entries only."""
        assert len(qualify.ENTRIES) == 3, sorted(qualify.ENTRIES)


# =========================================================================== S4 — load_references on the real file
class TestLoadReferencesReal:
    def test_load_references_on_real_file_passes(self):
        """exercises new behaviour (S4/AC5): `load_references` on the REAL
        `dev/p415_reference_peaks.json` against the real `ENTRIES` passes.

        A reference row for a non-entry (a pruned entry left in the file) is the failure path.
        """
        refs = qualify.load_references(qualify.REFERENCES)
        assert set(refs) == set(qualify.ENTRIES), (
            "reference table names diverge from ENTRIES", sorted(refs), sorted(qualify.ENTRIES))

    def test_no_reference_row_for_a_pruned_entry(self):
        """reproduces a failure the spec fixes: the four pruned entries' rows are gone from the
        REAL `dev/p415_reference_peaks.json`."""
        table = json.loads(qualify.REFERENCES.read_text())
        left = set(table) & set(PRUNED_SERVED)
        assert not left, "reference rows remain for pruned entries: " + ", ".join(sorted(left))


# =========================================================================== S4 — the golden fixture
class TestGoldenFixture:
    def test_verbatim_part_hashes_to_fixture_sha256(self):
        """preserves an invariant (S4): the fixture's verbatim part hashes to
        `registry_states.FIXTURE_SHA256`."""
        got = hashlib.sha256(_fixture_verbatim().encode("utf-8")).hexdigest()
        assert got == rs.FIXTURE_SHA256, f"fixture sha {got} != pinned {rs.FIXTURE_SHA256}"

    def test_fixture_equals_pruned_sibling_with_four_mtp_on(self):
        """reproduces a failure the spec fixes (S4): the fixture's verbatim part equals the
        pruned sibling registry with the four MTP-certified entries turned ON per the header
        procedure.

        `apply(fixture, {four MTP-certified})` must reproduce the live sibling registry (all four
        OFF). On the baseline the sibling still has 11 entries while the fixture has 11 too, so
        this passes; after the prune both have 5. If the implementer prunes the registry but forgets
        to regenerate the fixture, the model-name lists diverge and this fails.
        """
        assert SIBLING_REGISTRY.exists(), f"sibling registry {SIBLING_REGISTRY} missing"
        live = SIBLING_REGISTRY.read_text()
        applied = rs.apply(_fixture_verbatim(), frozenset(MTP_FOUR))
        assert applied == live, (
            "apply(fixture, {four MTP ON->OFF}) != live sibling registry; "
            "the fixture was not regenerated from the pruned registry")


# =========================================================================== S4 — opt-in live classification
class TestOptInLiveClassification:
    def test_live_sibling_classifies_as_all_four_off(self):
        """preserves an invariant (S4/AC5): the opt-in live classification of the sibling
        `../mlx_local_stack/main_models.yaml` succeeds with all four MTP-certified entries OFF.

        Catches a registry that drifts out of the 16 accepted states, or a fixture not regenerated
        after the prune (model-name lists diverge -> classify returns None).
        """
        assert SIBLING_REGISTRY.exists(), f"sibling registry {SIBLING_REGISTRY} missing"
        off = rs.classify(SIBLING_REGISTRY.read_text(), _fixture_verbatim())
        assert off is not None, (
            "the live sibling registry is not one of the 16 accepted states "
            "(fixture not regenerated after the prune?)")
        assert off == frozenset(MTP_FOUR), (
            f"expected all four MTP-certified OFF, got {sorted(off)}")


# =========================================================================== AC5 — production code unchanged
class TestProductionCodeUnchanged:
    def test_mlx_vlm_production_diff_empty(self):
        """preserves an invariant (AC5/S settled constraints): production code under `mlx_vlm/`
        outside `mlx_vlm/tests/` is unchanged versus the baseline commit."""
        diff = _git("diff", BASELINE_COMMIT, "--", "mlx_vlm", ":(exclude)mlx_vlm/tests")
        assert diff == "", "production code under mlx_vlm/ changed:\n" + diff
