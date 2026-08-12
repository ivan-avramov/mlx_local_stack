"""Fingerprint v2: record the runtime knobs that change results — WITHOUT invalidating v1 rows.

Two requirements pull in opposite directions.

1. The fingerprint must cover every knob that changes the output distribution. Today it covers
   sampling + kv_bits only, so a run at `APC_ENABLED=1` resumes on top of one at `APC_ENABLED=0`,
   and (from Phase 2 on) an agentic run at max_turns=30 resumes on top of one at 12.

2. Adding keys to a compared dict is DESTRUCTIVE here. Existing manifests on both boxes have no
   runtime block, so a naive extension makes `config_fingerprint(existing) != current` for every
   result ever produced -> every (model, bench) pair reports STALE, and `--clean-stale` DELETES
   them. Results are gitignored and unversioned; that is unrecoverable.

So the fingerprint is VERSIONED and comparison happens on the slice both sides declare
(`min(existing_v, current_v)`). A v1 manifest compares exactly as it did before — bit-for-bit
the old behaviour — while two v2 manifests compare on the full set. The guard gets stronger for
new results and cannot retroactively condemn old ones.
"""
import bench.provenance as P


def _v1(temp=0.7, profile="production", kv_bits=0):
    """A manifest as written by the pre-v2 harness: no `fingerprint_version`, no `runtime`."""
    return {"sampling_profile": profile, "sampling": {"temperature": temp},
            "kv": {"kv_bits": kv_bits}}


def _v2(temp=0.7, profile="production", kv_bits=0, **runtime):
    m = _v1(temp, profile, kv_bits)
    m["fingerprint_version"] = 2
    m["runtime"] = {"apc_enabled": "0", "draft_kind": "suffix", **runtime}
    return m


# ------------------------------------------------------------------ v1 behaviour is preserved
def test_v1_pair_compares_exactly_as_before():
    assert P.is_compatible(_v1(), _v1()) is True
    assert P.is_compatible(_v1(temp=0.7), _v1(temp=0.3)) is False
    assert P.is_compatible(_v1(kv_bits=0), _v1(kv_bits=4)) is False
    assert P.is_compatible(None, _v1()) is False          # unknown provenance is never resumed


def test_existing_v1_results_are_not_condemned_by_a_v2_current():
    """THE regression this test exists for: every existing per-box result is v1. A v2 harness
    must resume them, not flag them stale (which under --clean-stale means delete)."""
    assert P.is_compatible(_v1(temp=0.4), _v2(temp=0.4)) is True


def test_v1_vs_v2_still_catches_a_real_sampling_difference():
    """Degrading to the common slice must not degrade to 'always compatible'."""
    assert P.is_compatible(_v1(temp=0.7), _v2(temp=0.3)) is False


# ------------------------------------------------------------------ v2 adds real coverage
def test_v2_pair_detects_an_apc_difference():
    assert P.is_compatible(_v2(apc_enabled="0"), _v2(apc_enabled="1")) is False


def test_v2_pair_detects_agentic_knob_differences():
    a = _v2(max_turns=12, deadline_s=None, client="internal", edit_format="diff")
    b = _v2(max_turns=30, deadline_s=None, client="internal", edit_format="diff")
    assert P.is_compatible(a, b) is False
    c = _v2(max_turns=30, deadline_s=None, client="internal", edit_format="whole")
    assert P.is_compatible(b, c) is False


def test_v2_pair_ignores_samples():
    """`samples` does not change the output distribution — including it would mark every
    single-sample result stale the moment --samples is used."""
    a, b = _v2(), _v2()
    a["samples"], b["samples"] = 1, 5
    assert P.is_compatible(a, b) is True


def test_an_unobserved_runtime_value_is_a_wildcard_not_a_mismatch():
    """APC state is detected best-effort by scanning the router process, so it can come back
    "unknown" on one run and "1" on the next. Under strict equality that flip would report an
    existing results file STALE and `--clean-stale` would DELETE it — real generation lost to a
    detection failure, unrecoverably (results are gitignored). Refusing to condemn on ignorance
    is the safe direction; the manifest still records apc_source="unknown" for auditing."""
    assert P.is_compatible(_v2(apc_enabled="unknown"), _v2(apc_enabled="unknown")) is True
    assert P.is_compatible(_v2(apc_enabled="unknown"), _v2(apc_enabled="1")) is True
    assert P.is_compatible(_v2(apc_enabled="1"), _v2(apc_enabled="unknown")) is True
    # ...but two OBSERVED, differing values are still a real mismatch.
    assert P.is_compatible(_v2(apc_enabled="0"), _v2(apc_enabled="1")) is False


def test_a_knob_absent_from_one_axis_does_not_condemn():
    """`generate` runs have no max_turns; an agentic manifest does. None = not applicable."""
    assert P.is_compatible(_v2(max_turns=None), _v2(max_turns=30)) is True


# ------------------------------------------------------------------ APC detection
def test_apc_state_prefers_the_explicit_operator_declaration(monkeypatch):
    monkeypatch.setenv("MLX_BENCH_APC", "1")
    st = P.apc_state(process_env_lookup=lambda: {"APC_ENABLED": "0"})
    assert st == {"apc_enabled": "1", "source": "env"}


def test_apc_state_falls_back_to_the_router_process_env():
    st = P.apc_state(process_env_lookup=lambda: {"APC_ENABLED": "1", "APC_NUM_BLOCKS": "16384"})
    assert st == {"apc_enabled": "1", "source": "process"}


def test_apc_state_reports_unknown_rather_than_guessing():
    assert P.apc_state(process_env_lookup=lambda: None) == \
        {"apc_enabled": "unknown", "source": "unknown"}


def test_apc_state_absent_from_router_env_means_off():
    """runserver.sh sets APC_ENABLED=1 explicitly; a router started from the AGENTS.md
    benchmarking recipe has it unset, which is OFF — not unknown."""
    st = P.apc_state(process_env_lookup=lambda: {"MLX_SERVE_CONFIG": "main_models.yaml"})
    assert st == {"apc_enabled": "0", "source": "process"}


def test_apc_state_survives_a_raising_lookup():
    def boom():
        raise RuntimeError("psutil denied")
    assert P.apc_state(process_env_lookup=boom)["apc_enabled"] == "unknown"


# ------------------------------------------------------------------ manifest assembly
def test_current_manifest_lite_is_v2_and_carries_runtime(monkeypatch):
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {"temperature": 0.4})
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "1", "source": "env"})
    man = P.current_manifest_lite("m", "deployed")
    assert man["fingerprint_version"] == 2
    assert man["runtime"]["apc_enabled"] == "1"


def test_runtime_overrides_are_merged_into_the_manifest(monkeypatch):
    """Phase 2's agentic knobs join the fingerprint through this seam — no further provenance
    surgery needed when the taxonomy lands."""
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {"temperature": 0.4})
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "0", "source": "env"})
    man = P.current_manifest_lite("m", "deployed", runtime={"max_turns": 30, "client": "internal"})
    assert man["runtime"]["max_turns"] == 30 and man["runtime"]["client"] == "internal"
    assert man["runtime"]["apc_enabled"] == "0"      # detection still present alongside


# ------------------------------------------------------------------ APC pool sizing
def test_runserver_apc_pool_fits_the_daily_driver():
    """The APC pool is sized in 16-token blocks (`apc.py` DEFAULT_BLOCK_SIZE), and it is NOT
    free: 16384 blocks (= a full 256K prefix) MEASURED ~33GB, which put the daily driver 4.1GB
    from a Metal OOM with `Ornith-1.0-35B-mlx-uniform-4bit` resident (54.2GB footprint vs 20.8GB
    with APC absent) and killed an M1 benchmark arm. The Phase-2 win that justifies APC at all was
    measured at 7.5K-25K of shared prefix (54.5x-147x TTFT), so a 32K pool buys the whole
    demonstrated benefit for ~4GB. Guard the size, not the flag: APC stays ON for the daily driver.
    """
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[3] / "runserver.sh").read_text()
    m = re.search(r"APC_NUM_BLOCKS=(\d+)", src)
    assert m, "runserver.sh no longer sets APC_NUM_BLOCKS — re-derive the pool cost before removing"
    blocks = int(m.group(1))
    assert blocks <= 4096, (
        f"APC_NUM_BLOCKS={blocks} => {blocks * 16 // 1024}K cached tokens; at the measured "
        f"~2MB/block that is ~{blocks * 2 // 1024}GB of pool on a 48GB daily-driver box"
    )
