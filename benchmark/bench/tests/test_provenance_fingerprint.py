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
def test_current_manifest_lite_is_current_version_and_carries_runtime(monkeypatch):
    """Asserts the CURRENT version rather than a hardcoded number, so a future bump does not fail a
    test whose subject is "the runtime block is populated". The version itself is pinned once, by
    test_the_live_manifest_actually_carries_the_draft_state, where the number is the point."""
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {"temperature": 0.4})
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "1", "source": "env"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "off"})
    man = P.current_manifest_lite("m", "deployed")
    assert man["fingerprint_version"] == P.FINGERPRINT_VERSION
    assert man["runtime"]["apc_enabled"] == "1"
    assert man["runtime"]["draft_kind"] == "off"


def test_runtime_overrides_are_merged_into_the_manifest(monkeypatch):
    """Phase 2's agentic knobs join the fingerprint through this seam — no further provenance
    surgery needed when the taxonomy lands."""
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {"temperature": 0.4})
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "0", "source": "env"})
    man = P.current_manifest_lite("m", "deployed", runtime={"max_turns": 30, "client": "internal"})
    assert man["runtime"]["max_turns"] == 30 and man["runtime"]["client"] == "internal"
    assert man["runtime"]["apc_enabled"] == "0"      # detection still present alongside


# ------------------------------------------------------------------ APC policy (revised 2026-08-13)
def _runserver_src():
    from pathlib import Path
    return (Path(__file__).resolve().parents[3] / "runserver.sh").read_text()


def test_runserver_does_NOT_enable_apc():
    """APC is OFF everywhere — daily driver included (operator decision 2026-08-13, on measurement).

    This REPLACES the previous guard, whose docstring read "guard the size, not the flag: APC stays ON
    for the daily driver". That policy was based on a Phase-2 win (TTFT 54.5x-147x) which does not
    reproduce on the current stack. Measured 2026-08-13: with `APC_ENABLED=1 APC_NUM_BLOCKS=2048` in
    both router and worker env, the worker reports `enabled: true` but `pool_used 0, lookups_hit 0,
    lookups_miss 0, stores 0, resident_bytes 0`, and a 9K prefix served three times shows no reuse
    (prefill 3.10/3.00/3.00s).

    The mechanism is structural, not a bug: `server/generation.py:2455-2464` dispatches any request
    with a `prompt_cache_state` to `_process_cached_request` and `continue`s past the BatchGenerator,
    which is the ONLY place `apc_manager` is passed. Session caching therefore SHADOWS APC on every
    request that resolves to a session — and anonymous requests resolve by chained message hashes, so
    that is all of our traffic. Session caching is also what actually makes multi-turn cheap (measured:
    incremental prefill, 17x cheaper per total token).

    Three reasons the flag comes off rather than staying on harmlessly:
      1. zero benefit now, and a ~6s-per-new-conversation ceiling even if repaired;
      2. a demonstrated OOM class — 16384 blocks measured ~33GB, leaving 4.1GB free with Ornith
         resident, and those failures were being scored as MODEL failures;
      3. it collapses the documented hazard that runserver.sh enabled APC while the benchmark recipe
         omitted it, which is why past benchmark runs silently differed from what we serve. Served
         config == measured config is worth more than 6s.
    """
    src = _runserver_src()
    import re
    enabled = re.findall(r"^[^#\n]*APC_ENABLED=([^\s]+)", src, re.MULTILINE)
    assert not [v for v in enabled if v not in ("0", '"0"', "'0'")], (
        f"runserver.sh enables APC ({enabled}). APC is off everywhere: session caching shadows it on "
        f"every session-resolved request, so it buys nothing and re-introduces a served-vs-measured "
        f"config difference."
    )


def test_if_apc_is_ever_re_enabled_its_pool_must_still_be_bounded():
    """The size guard survives the policy change, so a future re-enable cannot bring back the 33GB pool.

    Blocks are 16 tokens (`apc.py` DEFAULT_BLOCK_SIZE) at ~2MB each. 16384 blocks (a full 256K prefix)
    MEASURED ~33GB and put the box 4.1GB from a Metal OOM; the win it was meant to buy was measured at
    only 7.5K-25K of shared prefix, so nothing above a few thousand blocks was ever justified.
    """
    import re
    m = re.search(r"APC_NUM_BLOCKS=(\d+)", _runserver_src())
    if m is None:
        return          # not set at all — the expected state now that APC is off
    blocks = int(m.group(1))
    assert blocks <= 4096, (
        f"APC_NUM_BLOCKS={blocks} => {blocks * 16 // 1024}K cached tokens; at the measured "
        f"~2MB/block that is ~{blocks * 2 // 1024}GB of pool on a 48GB daily-driver box"
    )


# ---------------------------------------------------------- v3: the DRAFT/SUFFIX state (2026-08-16)
# WHY v3 EXISTS. `draft_kind` was already NAMED in _FINGERPRINT_RUNTIME from v2 on, and it was still
# useless: nothing ever POPULATED it, so every manifest on disk carried it as absent -> None, and
# _runtime_compatible treats None as an unobserved wildcard. Measured 2026-08-16: of 50 manifests,
# 37 had no runtime block at all and 13 carried exactly {apc_enabled, apc_source}. ZERO carried
# draft_kind. Meanwhile suffix decoding was ON for exactly the two winners and OFF for every other
# candidate, which made every cross-model comparison in the corpus a (model x serving-path)
# composite that nothing refused. A declared-but-unpopulated fingerprint key is worse than an
# absent one: it reads as covered.
def _v3(temp=0.7, profile="production", kv_bits=0, draft="off", **runtime):
    m = _v1(temp, profile, kv_bits)
    m["fingerprint_version"] = 3
    m["runtime"] = {"apc_enabled": "0", "draft_kind": draft, **runtime}
    return m


def test_absent_suffix_is_recorded_as_off_not_as_unobserved():
    """The load-bearing distinction. "off" must be an OBSERVATION, not a missing value — otherwise
    the wildcard rule silently exonerates exactly the mismatch v3 exists to catch."""
    st = P.registry_draft("Ornith-1.0-35B-mlx-uniform-4bit")
    assert st["draft_kind"] in ("off", "suffix"), st
    assert st["draft_kind"] is not None
    missing = P.registry_draft("no-such-model-in-the-registry")
    assert missing["draft_kind"] == "unknown", missing


def test_two_v3_manifests_differing_only_in_draft_state_are_INCOMPATIBLE():
    assert P.is_compatible(_v3(draft="suffix"), _v3(draft="off")) is False
    assert P.is_compatible(_v3(draft="off"), _v3(draft="off")) is True


def test_a_v3_current_does_NOT_condemn_the_REAL_corpus_on_disk():
    """The same non-destructiveness requirement v2 had, tested against the ACTUAL manifests rather
    than a synthetic one — because the synthetic `_v2()` above sets draft_kind and NO real manifest
    does. Measured: 37 of 50 are v1, 13 are v2 carrying only {apc_enabled, apc_source}. For each,
    adding the v3 draft key must not make it stale, or --clean-stale deletes the corpus."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[3] / "benchmark/results"
    real = list(root.glob("*/*.manifest.json"))
    assert real, "no manifests found — this test would vacuously pass"
    for f in real:
        existing = json.loads(f.read_text())
        # `current` = the SAME config, re-fingerprinted by a v3 harness: only the version and the
        # newly-populated draft key differ. Anything else differing would be a real config change.
        current = dict(existing)
        current["fingerprint_version"] = 3
        current["runtime"] = {**(existing.get("runtime") or {}), "draft_kind": "off"}
        assert P.is_compatible(existing, current) is True, f"v3 condemned {f.name}"


def test_unknown_draft_state_stays_a_wildcard():
    """If the registry could not be read we say so, and refuse to condemn on ignorance — the same
    asymmetry APC detection uses, for the same reason."""
    assert P.is_compatible(_v3(draft="unknown"), _v3(draft="suffix")) is True


def test_the_live_manifest_actually_carries_the_draft_state():
    """End-to-end: the bug was that nothing populated the key. Assert the real builder does."""
    man = P.current_manifest_lite("Ornith-1.0-35B-mlx-uniform-4bit", profile="deployed")
    assert man["fingerprint_version"] >= 3   # v3 introduced the populated draft state; v4 keeps it
    assert man["runtime"]["draft_kind"] in ("off", "suffix")
    assert P.config_fingerprint(man)["runtime"]["draft_kind"] is not None
