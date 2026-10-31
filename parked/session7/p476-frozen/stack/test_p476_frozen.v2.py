"""P476 — adversarial frozen tests for the registry prune (stack side, spec v2).

These tests pin the spec's acceptance criteria for the prune of `main_models.yaml`
(`docs/specs/p476-registry-prune.md` v2). They are written against the spec and its
interfaces BEFORE the implementation exists; tests that need the prune will fail on the
baseline (the 11-entry registry) — that is expected and reported.

Each test states its class in its docstring:
  - "reproduces a failure the spec fixes" : fails on the baseline, passes after P476.
  - "preserves an invariant"               : passes on the baseline and after P476.
  - "exercises new behaviour"              : covers behaviour the spec introduces.

Nothing here needs a GPU, model, network or server.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# --------------------------------------------------------------------------- locations
# This file is <repo>/benchmark/bench/tests/test_p476_frozen.py -> repo root is parents[3].
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))  # so `configgen` is importable (bench runs from benchmark/)
REGISTRY = REPO / "main_models.yaml"
BASELINE_COMMIT = "c4faf574"  # the stack baseline this copy is checked out at


def _git(*args: str) -> str:
    """Run a git command in the stack repo and return stdout (text)."""
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _baseline_registry_bytes() -> bytes:
    """The baseline `main_models.yaml` as committed at `BASELINE_COMMIT`."""
    return subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASELINE_COMMIT}:main_models.yaml"],
        check=True,
        capture_output=True,
    ).stdout


def _live_registry_text() -> str:
    return REGISTRY.read_text()


def _parse(text: str) -> dict:
    return yaml.safe_load(text) or {}


# --------------------------------------------------------------------------- the five / the six
PUBLISHED_FIVE = (
    "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed",
    "Qwen3.8-27B-mlx-uniform-4bit",
    "Ornith-1.0-35B-mlx-uniform-4bit",
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
    "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit",
)
PRUNED_SIX = (
    "gemma-4-31B-it-qat-6bit",
    "gemma-4-26B-A4B-it-OptiQ-4bit",
    "Qwen3.8-27B-static-mixed-4bit",
    "Qwen3.8-27B-OptiQ-4.5bpw-mixed",
    "Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit",
    "Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit",
)


def _live_model_names() -> list[str]:
    return [e["name"] for e in (_parse(_live_registry_text()).get("models") or [])
            if isinstance(e, dict) and e.get("name")]


# =========================================================================== AC1 — the registry
class TestRegistryNames:
    def test_models_entry_names_are_exactly_the_five(self):
        """reproduces a failure the spec fixes: the live `models:` names must equal the Goal's five."""
        assert set(_live_model_names()) == set(PUBLISHED_FIVE)

    def test_no_pruned_entry_remains_in_models(self):
        """reproduces a failure the spec fixes: every pruned name is gone from `models:`."""
        names = set(_live_model_names())
        assert not (names & set(PRUNED_SIX)), sorted(names & set(PRUNED_SIX))

    def test_task_model_is_not_a_models_entry(self):
        """preserves an invariant: `task_model` is a top-level block, never a `models:` entry."""
        doc = _parse(_live_registry_text())
        names = [e["name"] for e in (doc.get("models") or []) if isinstance(e, dict) and e.get("name")]
        assert doc.get("task_model", {}).get("name") not in names


class TestRemainingEntriesMatchBaseline:
    def test_every_remaining_entry_parsed_settings_equal_baseline(self):
        """preserves an invariant: each remaining entry's full parsed dict equals its baseline form.

        A byte change in a kept block (AC1: "a remaining entry whose parsed settings differ") is
        caught here even if the textual diff looks deletions-only.
        """
        base = {e["name"]: e for e in (_parse(_baseline_registry_bytes().decode())
                .get("models") or []) if isinstance(e, dict) and e.get("name")}
        live = {e["name"]: e for e in (_parse(_live_registry_text()).get("models") or [])
                if isinstance(e, dict) and e.get("name")}
        for name in PUBLISHED_FIVE:
            assert name in live, f"{name} missing from live registry"
            assert live[name] == base[name], f"{name}: parsed settings differ from baseline"

    def test_every_top_level_key_equals_baseline(self):
        """preserves an invariant (AC1 v3): every top-level non-`models` key stays byte-identical,
        except `openwebui` may add a `retired_model_ids` list naming exactly the six pruned entries."""
        base = _parse(_baseline_registry_bytes().decode())
        live = _parse(_live_registry_text())
        for key in base:
            if key == "models":
                continue
            assert key in live, f"top-level key {key!r} dropped"
            if key == "openwebui" and isinstance(base.get(key), dict):
                base_owui = dict(base[key] or {})
                live_owui = dict(live[key] or {})
                retired = live_owui.pop("retired_model_ids", None)
                # without the new list, openwebui must equal the baseline byte-for-byte
                assert live_owui == base_owui, "openwebui changed beyond retired_model_ids"
                # if the list is present (v3 candidate), it names exactly the six pruned entries
                if retired is not None:
                    assert len(retired) == 6 and set(retired) == set(PRUNED_SIX), (
                        f"openwebui.retired_model_ids != the six pruned entries: {retired}")
                continue
            assert live[key] == base[key], f"top-level key {key!r} changed"


class TestRegistryDiffIsDeletionsOnly:
    def test_diff_against_baseline_is_deletions_only(self):
        """preserves an invariant (AC1 v3): the textual diff is deletions plus, solely, the added
        `openwebui.retired_model_ids` list (the six pruned names) — no other `+` content lines.

        Diff headers (`diff --git`, `index`, `---`, `+++`, `@@`) are not content and are skipped.
        """
        diff = _git("diff", BASELINE_COMMIT, "--", "main_models.yaml")
        if not diff:
            return  # no change (baseline)
        added = []
        for line in diff.splitlines():
            # skip diff headers — they are not content lines
            if line.startswith(("diff --git", "index ", "--- ", "+++ ", "@@")):
                continue
            if line.startswith("+"):
                added.append(line[1:])  # strip the leading `+`
        # the ONLY allowed additions are the `retired_model_ids` list under `openwebui:`
        expected_key = "  retired_model_ids:"
        expected_items = {f"    - {name}" for name in PRUNED_SIX}
        key_lines = [a for a in added if a == expected_key]
        item_lines = [a for a in added if a in expected_items]
        other = [a for a in added if a != expected_key and a not in expected_items]
        assert not other, (
            "diff adds content lines beyond the openwebui.retired_model_ids list:\n"
            + "\n".join(other))
        # if a retired_model_ids list is added, it is exactly the key plus the six pruned names
        if key_lines:
            assert len(key_lines) == 1, "retired_model_ids key added more than once"
            assert len(item_lines) == 6 and set(item_lines) == expected_items, (
                "retired_model_ids list items != the six pruned entries:\n" + "\n".join(item_lines))

    def test_no_orphan_comment_block_is_dropped(self):
        """preserves an invariant (AC1): a comment block that documents NO pruned entry stays.

        The spec names the `RETIRED 2026-08-26 (C33 …)` note on the removed `Qwen3.8-27-4bit`
        (already gone, not one of the six) as the example of an orphan block that must survive.
        A dropped orphan comment is the failure path this catches.
        """
        text = _live_registry_text()
        assert "RETIRED 2026-08-26 (C33, operator)" in text, (
            "the orphan RETIRED Qwen3.8-27B-4bit comment block was dropped")
        assert "Qwen3.8-27B-4bit" in text, (
            "the orphan comment's subject name `Qwen3.8-27B-4bit` was dropped")


# =========================================================================== AC2 — configgen carriers
def _configgen_check_rc() -> int:
    """Run `configgen check` in this copy and return its exit code."""
    return subprocess.run(
        [str(REPO.parent / "run_configgen.sh"), "check"],
        capture_output=True, text=True,
    ).returncode


def _carrier_files() -> list[Path]:
    """Every configgen-generated carrier file path (TARGETS + BENCH + DEPLOYMENT)."""
    from configgen.targets import TARGETS, BENCH_TARGETS, DEPLOYMENT_TARGETS
    out: list[Path] = []
    for _, _, paths in [*TARGETS, *BENCH_TARGETS, *DEPLOYMENT_TARGETS]:
        if isinstance(paths, dict):
            out.extend(REPO / p for p in paths.values())
        else:
            out.append(REPO / paths)
    return [p for p in out if p.exists()]


def _carrier_model_ids(path: Path) -> set[str]:
    """All model-id strings a carrier exposes, parsed generically.

    A string is treated as a model id when it is a known model name (a live registry
    `models:` name, the task_model name, or one of the six pruned names). This detects a
    stale/pruned id in any carrier format without per-format parsing.
    """
    doc = _parse(_live_registry_text())
    task_name = (doc.get("task_model") or {}).get("name", "")
    known = set(_live_model_names()) | {task_name} | set(PRUNED_SIX)

    text = path.read_text()
    try:
        parsed = yaml.safe_load(text)
    except Exception:
        parsed = None

    found: set[str] = set()
    if isinstance(parsed, (dict, list)):
        stack = [parsed]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(k, str) and k in known:
                        found.add(k)
                    if isinstance(v, str) and v in known:
                        found.add(v)
                    stack.append(v)
            elif isinstance(node, list):
                stack.extend(node)
    # also catch `mlx-local/<name>` / `mlx-task/<name>` / `openai/<name>` ref forms
    for prefix in ("mlx-local/", "mlx-task/", "openai/"):
        for line in text.splitlines():
            for tok in line.split():
                if tok.startswith(prefix) and tok[len(prefix):] in known:
                    found.add(tok[len(prefix):])
    return found


class TestConfiggenCheck:
    def test_configgen_check_rc_zero(self):
        """preserves an invariant (AC2): `configgen check` returns 0 after the prune."""
        assert _configgen_check_rc() == 0


class TestCarrierIds:
    def test_every_carrier_id_is_in_registry_or_task_model(self):
        """preserves an invariant (AC2/S3b): every model id in every carrier ⊆ registry
        `models:` names ∪ {task_model}."""
        doc = _parse(_live_registry_text())
        task_name = (doc.get("task_model") or {}).get("name", "")
        allowed = set(_live_model_names()) | {task_name}
        offenders: dict[str, set[str]] = {}
        for carrier in _carrier_files():
            ids = _carrier_model_ids(carrier)
            bad = ids - allowed
            if bad:
                offenders[str(carrier.relative_to(REPO))] = bad
        assert not offenders, "carriers expose ids outside registry ∪ {task_model}:\n" + json.dumps(
            {k: sorted(v) for k, v in offenders.items()}, indent=2)

    def test_no_carrier_names_a_pruned_entry(self):
        """reproduces a failure the spec fixes (AC2): no generated file names a pruned entry."""
        offenders: list[str] = []
        for carrier in _carrier_files():
            text = carrier.read_text()
            for name in PRUNED_SIX:
                if name in text:
                    offenders.append(f"{carrier.relative_to(REPO)}: {name}")
        assert not offenders, "generated carriers still name pruned entries:\n" + "\n".join(offenders)


class TestOwuiMenu:
    def test_owui_menu_equals_openwebui_models(self):
        """preserves an invariant (AC2/S3b): the OWUI menu == `openwebui.models` (four entries)."""
        doc = _parse(_live_registry_text())
        menu = list((doc.get("openwebui") or {}).get("models") or [])
        owui = json.loads((REPO / "openwebui-init" / "models_config.json").read_text())
        task_name = (doc.get("task_model") or {}).get("name", "")
        owui_main = [m["id"] for m in owui if m.get("id") != task_name]
        assert owui_main == menu, (owui_main, menu)
        assert len(menu) == 4, menu


# =========================================================================== AC3 — untouched paths
class TestUntouchedPaths:
    def test_benchmark_results_unchanged(self):
        """preserves an invariant (AC3): `benchmark/results/` is untouched."""
        assert _git("diff", BASELINE_COMMIT, "--", "benchmark/results/") == ""

    def test_model_params_py_unchanged(self):
        """preserves an invariant (AC3): `benchmark/bench/model_params.py` is untouched."""
        assert _git("diff", BASELINE_COMMIT, "--", "benchmark/bench/model_params.py") == ""

    def test_configgen_code_unchanged(self):
        """preserves an invariant (AC3): `configgen/` code is untouched."""
        assert _git("diff", BASELINE_COMMIT, "--", "configgen/") == ""

    def test_scripts_unchanged(self):
        """preserves an invariant (AC3): `scripts/` is untouched."""
        assert _git("diff", BASELINE_COMMIT, "--", "scripts/") == ""

    def test_readme_unchanged(self):
        """preserves an invariant (AC3): `README.md` is untouched."""
        assert _git("diff", BASELINE_COMMIT, "--", "README.md") == ""

    def test_docs_unchanged_except_spec_and_reviews(self):
        """preserves an invariant (AC3): `docs/` is untouched except the spec and its review record."""
        diff = _git("diff", BASELINE_COMMIT, "--", "docs/")
        if not diff:
            return
        changed = subprocess.run(
            ["git", "-C", str(REPO), "diff", "--name-only", BASELINE_COMMIT, "--", "docs/"],
            check=True, capture_output=True, text=True,
        ).stdout.split()
        allowed = {
            "docs/specs/p476-registry-prune.md",
        }
        # the review record dir for P476 is allowed to change
        unexpected = [p for p in changed if p not in allowed and not p.startswith("docs/reviews/p476/")]
        assert not unexpected, "docs changed outside the spec / review record:\n" + "\n".join(unexpected)


# =========================================================================== operator ruling Q1 — model_params
class TestModelParamsRetained:
    def test_model_params_still_has_the_six_entries(self):
        """preserves an invariant (operator ruling Q1): `model_params.PARAMS` keeps the six entries.

        The six pruned entries stay registered in `model_params.PARAMS` (per-model knowledge used
        by regrading old rows; harmless). A retire-`model_params` mistake is the failure path.
        """
        import bench.model_params as MP
        for name in PRUNED_SIX:
            assert name in MP.PARAMS, f"{name} dropped from model_params.PARAMS"
