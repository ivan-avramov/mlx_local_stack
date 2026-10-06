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
import pytest
import bench.provenance as P

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")   # M58: synthetic models



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
    # "mtp" added 2026-09-01: since M27 (3a200a9) the registry of record legitimately ships
    # draft_kind: mtp for certified picks; the load-bearing claim is observation-vs-missing,
    # not which drafter. Bench runs still measure draft-OFF via the stripped overlay (C35).
    assert st["draft_kind"] in ("off", "suffix", "mtp"), st
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
        # v7 manifests record the served attention policy / lazy-embedding state; a v3 harness
        # cannot express those, so a v3 `current` legitimately reads as `auto` and a manifest
        # written under `fused_v1` SHOULD refuse it (M57, 2026-10-05). They are not this test's
        # subject (v2 -> v3 non-destructiveness), so they are skipped here.
        if (existing.get("fingerprint_version") or 1) >= 7:
            continue
        # `current` = the SAME config, re-fingerprinted by a v3 harness: only the version and the
        # newly-populated draft key differ. Anything else differing would be a real config change.
        current = dict(existing)
        current["fingerprint_version"] = 3
        # A manifest that ALREADY records a served draft state (an honest ON-arm manifest, e.g. the
        # M6b/M6d mtp-ON rows) keeps it: this test guards v2->v3 non-destructiveness, not draft-state
        # refusal -- an ON-arm manifest SHOULD refuse a draft-off current (operator ruling 2026-08-30).
        recorded = (existing.get("runtime") or {}).get("draft_kind")
        current["runtime"] = {**(existing.get("runtime") or {}),
                              "draft_kind": recorded if recorded else "off"}
        assert P.is_compatible(existing, current) is True, f"v3 condemned {f.name}"


def test_unknown_draft_state_stays_a_wildcard():
    """If the registry could not be read we say so, and refuse to condemn on ignorance — the same
    asymmetry APC detection uses, for the same reason."""
    assert P.is_compatible(_v3(draft="unknown"), _v3(draft="suffix")) is True


def test_the_live_manifest_actually_carries_the_draft_state():
    """End-to-end: the bug was that nothing populated the key. Assert the real builder does."""
    man = P.current_manifest_lite("Ornith-1.0-35B-mlx-uniform-4bit", profile="deployed")
    assert man["fingerprint_version"] >= 3   # v3 introduced the populated draft state; v4 keeps it
    assert man["runtime"]["draft_kind"] in ("off", "suffix", "mtp")  # mtp: certified picks since M27
    assert P.config_fingerprint(man)["runtime"]["draft_kind"] is not None


# ------------------------------------------------------------------ reasoning_effort (M24)
def test_reasoning_effort_is_fingerprinted_and_guarded():
    """The depth_tokens invariant, applied again BEFORE the M24 arm runs: a knob that changes
    what we asked (the template's effort instruction) must be in the fingerprint AND in
    compare's must-match tier — an unrecorded effort is an O36-class hazard."""
    import bench.compare as CMP
    assert "reasoning_effort" in P._FINGERPRINT_SAMPLING
    assert "reasoning_effort" in CMP._MUST_MATCH_SAMPLING


def test_reasoning_effort_mismatch_is_incompatible_but_absent_on_both_is_fine():
    """Absent means "the template's own default" (xhigh for the Qwen3.8-27B family) — every
    existing row. Absent-on-both must compare equal so the corpus is not condemned; any
    observed difference, including absent-vs-set, is a different regime and never resumes."""
    med = _v3()
    med["sampling"]["reasoning_effort"] = "medium"
    med2 = _v3()
    med2["sampling"]["reasoning_effort"] = "medium"
    xh = _v3()
    xh["sampling"]["reasoning_effort"] = "xhigh"
    assert P.is_compatible(_v3(), _v3()) is True     # absent/absent: corpus stays live
    assert P.is_compatible(_v3(), med) is False      # template default vs explicit medium
    assert P.is_compatible(med, xh) is False         # observed differing
    assert P.is_compatible(med, med2) is True        # matched explicit effort resumes


# ---------------------------------------------------------- C35: served-vs-registry draft provenance
import pytest


def _c35_registry(tmp_path, draft=None):
    import yaml as _yaml
    entry = {"name": "modelX", "hf_path": "caslca/modelX-4bit"}
    if draft:
        entry["draft_kind"] = draft
        entry["draft_model"] = "caslca/modelX-drafter"
    p = tmp_path / "reg.yaml"
    p.write_text(_yaml.safe_dump({"models": [entry]}))
    return str(p)


def test_c35_registry_path_honors_MLX_SERVE_CONFIG_absolute(monkeypatch, tmp_path):
    from bench import paths
    ov = tmp_path / "overlay.yaml"
    ov.write_text("models: []")
    monkeypatch.setenv("MLX_SERVE_CONFIG", str(ov))
    assert paths.registry_path() == ov


def test_c35_registry_path_relative_env_resolves_against_repo_root(monkeypatch):
    from bench import paths
    monkeypatch.setenv("MLX_SERVE_CONFIG", "main_models.yaml")
    assert paths.registry_path() == paths.REPO_ROOT / "main_models.yaml"


def test_c35_registry_path_default_unchanged(monkeypatch):
    from bench import paths
    monkeypatch.delenv("MLX_SERVE_CONFIG", raising=False)
    assert paths.registry_path() == paths.REPO_ROOT / "main_models.yaml"


def test_c35_tripwire_refuses_registry_worker_mismatch(tmp_path):
    """The exact M12-pilot bug: registry certifies a drafter, worker verifiably serves draft-OFF.
    Recording either answer would be false provenance — the run must REFUSE."""
    reg = _c35_registry(tmp_path, draft="mtp")
    cmd = "python mlx_vlm.server --model caslca/modelX-4bit --port 8091"
    with pytest.raises(RuntimeError, match="C35"):
        P.registry_draft("modelX", reg, worker_lookup=lambda: cmd)


def test_c35_tripwire_confirms_on_match(tmp_path):
    reg = _c35_registry(tmp_path, draft="mtp")
    cmd = ("python mlx_vlm.server --model caslca/modelX-4bit "
           "--draft-kind mtp --draft-model caslca/modelX-drafter")
    st = P.registry_draft("modelX", reg, worker_lookup=lambda: cmd)
    assert st["draft_kind"] == "mtp"
    assert st["draft_source"] == "registry+worker"


def test_c35_tripwire_skips_when_worker_serves_another_model(tmp_path):
    """A live worker for a DIFFERENT model says nothing about this model's draft state."""
    reg = _c35_registry(tmp_path, draft="mtp")
    cmd = "python mlx_vlm.server --model caslca/some-other-model --port 8091"
    st = P.registry_draft("modelX", reg, worker_lookup=lambda: cmd)
    assert st["draft_kind"] == "mtp"
    assert st["draft_source"] == "registry"


def test_c35_tripwire_skips_when_no_worker_observable(tmp_path):
    reg = _c35_registry(tmp_path)
    st = P.registry_draft("modelX", reg, worker_lookup=lambda: None)
    assert st["draft_kind"] == "off"
    assert st["draft_source"] == "registry"


def test_c35_worker_path_that_merely_extends_the_requested_path_is_not_this_model(tmp_path):
    """Review C3: exact `--model` identification. A previous model whose hf_path EXTENDS the
    requested one must not trip the (now fatal) tripwire."""
    reg = _c35_registry(tmp_path, draft="mtp")
    cmd = "python mlx_vlm.server --model caslca/modelX-4bit-v2 --draft-kind off"
    st = P.registry_draft("modelX", reg, worker_lookup=lambda: cmd)
    assert st["draft_kind"] == "mtp" and st["draft_source"] == "registry"


def test_c35_an_unrelated_matching_process_does_not_hide_the_real_worker(tmp_path):
    reg = _c35_registry(tmp_path, draft="mtp")
    decoy = ["python", "other.py", "--note", "caslca/modelX-4bit-v2"]
    real = ["python", "mlx_vlm.server", "--model", "caslca/modelX-4bit", "--draft-kind", "off"]
    with pytest.raises(P.ServingStateError, match="C35 tripwire"):
        P.registry_draft("modelX", reg, worker_lookup=lambda: [decoy, real])


def test_c35_a_failed_worker_observation_refuses(tmp_path):
    reg = _c35_registry(tmp_path, draft="mtp")

    def boom():
        raise OSError("lsof failed")
    with pytest.raises(P.ServingStateError, match="C35 tripwire"):
        P.registry_draft("modelX", reg, worker_lookup=boom)


def test_c35_default_lookup_is_the_listener_based_worker_identification(tmp_path, monkeypatch):
    reg = _c35_registry(tmp_path, draft="mtp")
    seen = []
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: seen.append(doc) or [
        ["python", "mlx_vlm.server", "--model", "caslca/modelX-4bit", "--draft-kind", "off"]])
    with pytest.raises(P.ServingStateError, match="C35 tripwire"):
        P.registry_draft("modelX", reg)
    assert seen, "registry_draft did not use _worker_argvs"


# ----------------------------------------------------- M34 (moe_expand joins kv_extra)
def _moe_man(v, expand):
    return {"sampling_profile": "deployed", "fingerprint_version": v,
            "sampling": {"temperature": 0.4},
            "kv": {"kv_bits": 4, "hf_path": "org/m", "moe_expand": expand},
            "runtime": {}}


def test_moe_expand_difference_makes_two_v5_manifests_incompatible():
    """kv.moe_expand is OUTPUT-DETERMINING (M34): a run with the routing lever on must never
    resume/pool with the native-routing baseline."""
    assert P.is_compatible(_moe_man(5, "27-39:20:0.8:0.5"), _moe_man(5, None)) is False


def test_moe_expand_absent_key_compares_equal_to_explicit_none():
    """An old manifest with no `moe_expand` key at all (pre-M34) must pair with a new manifest
    that carries the key explicitly set to None (M34 build, lever unset) -- absent == None, or
    every pre-M34 row on disk reads STALE the moment the key is introduced."""
    old = {"sampling_profile": "deployed", "fingerprint_version": 5,
           "sampling": {"temperature": 0.4},
           "kv": {"kv_bits": 4, "hf_path": "org/m"},  # no moe_expand key at all
           "runtime": {}}
    new = _moe_man(5, None)
    assert P.is_compatible(old, new) is True


def test_registry_kv_extracts_moe_expand(tmp_path):
    yml = tmp_path / "reg.yaml"
    yml.write_text(
        "models:\n"
        "  - name: expanded\n"
        "    hf_path: org/expanded\n"
        "    moe_expand: \"27-39:20:0.8:0.5\"\n"
        "  - name: plain\n"
        "    hf_path: org/plain\n"
    )
    assert P.registry_kv("expanded", str(yml))["moe_expand"] == "27-39:20:0.8:0.5"
    assert P.registry_kv("plain", str(yml))["moe_expand"] is None


def test_registry_kv_normalizes_empty_string_moe_expand_to_none(tmp_path):
    """An operator may write `moe_expand: ""` in the registry to document 'off' explicitly.
    registry_kv must normalize that to None -- ModelConfig's own default is "" (mlx-serve), so
    without normalization a manifest built from this entry fingerprints as '' while an absent
    key fingerprints as None, is_compatible(old-no-key, new-'') reads False, and --clean-stale
    deletes rows that ran the exact same (native) routing (M34 verifier FIX-6)."""
    yml = tmp_path / "reg.yaml"
    yml.write_text(
        "models:\n"
        "  - name: documented-off\n"
        "    hf_path: org/documented-off\n"
        "    moe_expand: \"\"\n"
    )
    kv = P.registry_kv("documented-off", str(yml))
    assert kv["moe_expand"] is None

    old = {"sampling_profile": "deployed", "fingerprint_version": 5,
           "sampling": {"temperature": 0.4},
           "kv": {"kv_bits": 4, "hf_path": "org/m"},  # no moe_expand key at all
           "runtime": {}}
    new = {"sampling_profile": "deployed", "fingerprint_version": 5,
           "sampling": {"temperature": 0.4},
           # kv.moe_expand as registry_kv would actually stamp it for this entry
           "kv": {"kv_bits": 4, "hf_path": "org/m", "moe_expand": kv["moe_expand"]},
           "runtime": {}}
    assert P.is_compatible(old, new) is True


def test_startup_preserves_committed_dependency_revisions():
    import shlex
    commands = [shlex.split(line) for line in _runserver_src().splitlines()
                if line.strip().startswith("git submodule update")]
    assert commands, "Startup must initialize pinned dependencies"
    assert all("--remote" not in command for command in commands), (
        "Startup must use committed gitlinks, not unvalidated remote branch tips"
    )


# ----------------------------------------------------- M50 (served-config tripwire, 2026-09-28)
# The process that OWNS :8000 is the serving truth for which registry is live. On 2026-09-28 a lean
# overlay router failed to bind, the daily driver kept the port, and a parity arm ran against it
# with the overlay stamped as provenance. C35 only compares draft_kind, and only when a worker for
# the requested model is already up. M50 compares the router's MLX_SERVE_CONFIG (resolved against
# ITS cwd, exactly as mlx-serve does) with the driver's `paths.registry_path()` and REFUSES on any
# difference, on no owner, and on an unreadable environ.
import json
import os
import sys

import pytest


def _owner(tmp_path, config, cwd=None, pid=4242, env_ok=True):
    """A fake :8000 owner as `router_owner` reports it."""
    return {"pid": pid, "cmdline": "python mlx-serve start", "cwd": str(cwd or tmp_path),
            "env": ({"MLX_SERVE_CONFIG": config} if config is not None else {}) if env_ok else None}


def _driver_registry(monkeypatch, tmp_path, name="overlay.yaml"):
    reg = tmp_path / name
    reg.write_text("models: []")
    monkeypatch.setenv("MLX_SERVE_CONFIG", str(reg))
    return reg


def test_m50_refuses_when_no_process_owns_the_port(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="M50") as ei:
        P.assert_served_config("http://localhost:8000", lookup=lambda port: None)
    assert ":8000" in str(ei.value)


def test_m50_refuses_on_config_mismatch(monkeypatch, tmp_path):
    """The exact 2026-09-28 failure: driver launched with the overlay, daily driver still on :8000."""
    _driver_registry(monkeypatch, tmp_path)
    (tmp_path / "main_models.yaml").write_text("models: []")
    owner = _owner(tmp_path, "main_models.yaml")          # relative, as runserver.sh launches it
    with pytest.raises(RuntimeError, match="M50") as ei:
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)
    msg = str(ei.value)
    assert "main_models.yaml" in msg and "overlay.yaml" in msg and "4242" in msg


def test_m50_confirms_relative_config_resolved_against_the_router_cwd(monkeypatch, tmp_path):
    reg = _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml", cwd=tmp_path)
    blk = P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)
    assert blk["pid"] == 4242
    assert blk["config_raw"] == "main_models.yaml"
    assert os.path.realpath(blk["config"].replace("$HOME", os.path.expanduser("~"))) == \
        os.path.realpath(str(reg))
    assert blk["port"] == 8000


def test_m50_confirms_absolute_overlay_and_home_normalizes_the_record(monkeypatch, tmp_path):
    reg = _driver_registry(monkeypatch, tmp_path)
    owner = _owner(tmp_path, str(reg), cwd="/")
    blk = P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)
    home = os.path.expanduser("~")
    assert not blk["config"].startswith(home), "results are TRACKED — no absolute home path"


def test_m50_same_file_through_a_symlink_or_dotdot_is_a_match(monkeypatch, tmp_path):
    reg = _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    sub = tmp_path / "sub"; sub.mkdir()
    owner = _owner(tmp_path, "../main_models.yaml", cwd=sub)
    assert P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)["pid"] == 4242
    assert os.path.realpath(str(reg))  # sanity


def test_m50_refuses_when_the_router_environ_is_unreadable(monkeypatch, tmp_path):
    """Stricter than C35's skip-when-unobservable: the point is POSITIVE verification."""
    _driver_registry(monkeypatch, tmp_path)
    owner = _owner(tmp_path, None, env_ok=False)
    with pytest.raises(RuntimeError, match="M50.*environ"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


def test_m50_router_without_MLX_SERVE_CONFIG_is_a_mismatch_against_our_registry(monkeypatch, tmp_path):
    """mlx-serve then falls back to ./models.yaml etc. — never main_models.yaml. Refuse, and say so."""
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, None)
    with pytest.raises(RuntimeError, match="M50.*MLX_SERVE_CONFIG"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


def test_m50_port_comes_from_the_driver_base_url(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    seen = {}

    def lookup(port):
        seen["port"] = port
        return _owner(tmp_path, "main_models.yaml")

    blk = P.assert_served_config("http://127.0.0.1:8123/", lookup=lookup)
    assert seen["port"] == 8123 and blk["port"] == 8123
    P.assert_served_config("http://localhost", lookup=lookup)
    assert seen["port"] == 80


def test_m50_router_block_rides_the_manifest_but_not_the_fingerprint(monkeypatch, tmp_path):
    """Every manifest records router.pid + router.config — the block verified at ENTRY (or at the
    restart re-check), not a fresh process walk per manifest; a pid change across restarts must NOT
    make resumable rows stale."""
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {"temperature": 0.4})
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "0", "source": "env"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "off"})
    # M57 T2: an unresolved control (model "m" is not in the registry) is incompatible with
    # everything, so resolve both controls to known defaults for this router-block test.
    monkeypatch.setattr(P, "registry_attention_policy", lambda m, path=None: {
        "attention_policy": "auto", "attention_policy_source": "registry"})
    monkeypatch.setattr(P, "registry_lazy_prompt_embeddings", lambda m, path=None: {
        "lazy_prompt_embeddings": False, "lazy_prompt_embeddings_source": "registry"})
    monkeypatch.setattr(P, "registry_mtp_verify_scan", lambda m, path=None: {
        "mtp_verify_scan": "per_query", "mtp_verify_scan_source": "registry"})
    monkeypatch.setattr(P, "router_owner", lambda port: _owner(tmp_path, "main_models.yaml", pid=1))
    P.assert_served_config("http://localhost:8000")            # entry
    a = P.gather("m", profile="deployed")
    monkeypatch.setattr(P, "router_owner", lambda port: _owner(tmp_path, "main_models.yaml", pid=2))
    assert P.gather("m", profile="deployed")["router"]["pid"] == 1, "no re-walk per manifest"
    P.assert_served_config("http://localhost:8000")            # restart re-check refreshes it
    b = P.gather("m", profile="deployed")
    assert a["router"]["pid"] == 1 and b["router"]["pid"] == 2
    assert a["router"]["config"] == b["router"]["config"]
    assert P.is_compatible(a, b)
    assert P.config_fingerprint(a) == P.config_fingerprint(b)


def test_m50_gather_never_raises_when_the_tripwire_would(monkeypatch, tmp_path):
    """gather() is best-effort by contract; REFUSAL is the ENTRY POINTS' job (assert_served_config)."""
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {"temperature": 0.4})
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "0", "source": "env"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "off"})
    monkeypatch.setattr(P, "router_owner", lambda port: None)
    man = P.gather("m", profile="deployed")
    assert man["router"]["pid"] is None and "M50" in man["router"]["error"]


class _FakeConn:
    def __init__(self, ip, port, status="LISTEN"):
        import collections
        self.laddr = collections.namedtuple("addr", "ip port")(ip, port)
        self.status = status


class _FakeProc:
    def __init__(self, pid, conns, denied=False):
        self.pid, self._conns, self._denied = pid, conns, denied

    def net_connections(self, kind="inet"):
        if self._denied:
            raise PermissionError("AccessDenied")
        return self._conns


def _fake_psutil(monkeypatch, procs):
    import types
    mod = types.SimpleNamespace(CONN_LISTEN="LISTEN", process_iter=lambda attrs=None: iter(procs))
    monkeypatch.setitem(sys.modules, "psutil", mod)
    monkeypatch.setattr(P, "_lsof_listeners", lambda port: [])


def test_m50_psutil_walk_finds_the_listener_and_skips_denied_and_client_sockets(monkeypatch):
    _fake_psutil(monkeypatch, [
        _FakeProc(10, [], denied=True),
        _FakeProc(11, [_FakeConn("127.0.0.1", 8000, "ESTABLISHED")]),    # a client, not the owner
        _FakeProc(12, [_FakeConn("0.0.0.0", 8000), _FakeConn("::", 8000)]),  # v4+v6, same pid
        _FakeProc(13, [_FakeConn("127.0.0.1", 8092)]),
    ])
    assert P._psutil_listeners(8000) == [(12, "0.0.0.0"), (12, "::")]
    monkeypatch.setattr(P, "_process_facts", lambda pid: {"pid": pid, "cmdline": "mlx-serve", "cwd": "/", "env": {}})
    own = P._real_router_owner(8000)
    assert own["pid"] == 12 and own["bound_ips"] == ["0.0.0.0", "::"]


def test_m50_two_different_listening_pids_is_ambiguous_and_refuses(monkeypatch):
    """A stale router on IPv4 and a new one on IPv6 (or any two owners) — never pick the first."""
    _fake_psutil(monkeypatch, [_FakeProc(20, [_FakeConn("127.0.0.1", 8000)]),
                               _FakeProc(21, [_FakeConn("::1", 8000)])])
    with pytest.raises(RuntimeError, match="M50.*ambiguous"):
        P._real_router_owner(8000)


def test_m50_router_owner_none_when_nothing_listens(monkeypatch):
    _fake_psutil(monkeypatch, [_FakeProc(30, [_FakeConn("127.0.0.1", 9999)])])
    assert P._real_router_owner(8000) is None


def test_m50_lsof_field_output_is_parsed_with_addresses(monkeypatch):
    class R:
        stdout = "p777\nf12\nn*:8000\nf13\nn[::1]:8000\np778\nf3\nn127.0.0.1:8000\np779\n"
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        return R()
    monkeypatch.setattr(P.subprocess, "run", fake_run)
    assert P._lsof_listeners(8000) == [(777, "*"), (777, "::1"), (778, "127.0.0.1"), (779, None)]
    assert P._lsof_listener_pids(8000) == [777, 778, 779]
    assert "-iTCP:8000" in seen["argv"] and "-sTCP:LISTEN" in seen["argv"] and "-Fpn" in seen["argv"]


def test_m50_lsof_union_with_psutil_catches_a_second_owner(monkeypatch):
    _fake_psutil(monkeypatch, [_FakeProc(40, [_FakeConn("127.0.0.1", 8000)])])
    monkeypatch.setattr(P, "_lsof_listeners", lambda port: [(41, "127.0.0.1")])
    with pytest.raises(RuntimeError, match="ambiguous"):
        P._real_router_owner(8000)


def test_m50_refuses_a_remote_destination(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    with pytest.raises(RuntimeError, match="M50.*not this box"):
        P.assert_served_config("http://10.0.0.7:8000", lookup=lambda port: owner)


def test_m50_refuses_an_owner_that_is_not_an_mlx_serve_router(monkeypatch, tmp_path):
    """A proxy/worker/anything else carrying an inherited MLX_SERVE_CONFIG is not the router."""
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    owner["cmdline"] = "python -m mlx_vlm.server --model x --port 8000"
    with pytest.raises(RuntimeError, match="M50.*not an mlx-serve router"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


def test_m50_tilde_expands_with_the_ROUTER_home_not_the_drivers(monkeypatch, tmp_path):
    router_home = tmp_path / "rhome"; router_home.mkdir()
    reg = router_home / "reg.yaml"; reg.write_text("models: []")
    monkeypatch.setenv("MLX_SERVE_CONFIG", str(reg))
    monkeypatch.setenv("HOME", str(tmp_path / "driver_home"))     # driver's HOME differs
    owner = _owner(tmp_path, "~/reg.yaml")
    owner["env"]["HOME"] = str(router_home)
    assert P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)["pid"] == 4242
    del owner["env"]["HOME"]
    with pytest.raises(RuntimeError, match="M50.*HOME"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)
    owner["env"]["MLX_SERVE_CONFIG"] = "~other/reg.yaml"
    with pytest.raises(RuntimeError, match="M50.*~user"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


def test_m50_refuses_when_the_served_file_no_longer_exists(monkeypatch, tmp_path):
    """Both sides naming the same MISSING file is not a match: mlx-serve raises on a missing explicit
    path at start, so a running router whose file vanished is serving something unidentifiable."""
    monkeypatch.setenv("MLX_SERVE_CONFIG", str(tmp_path / "gone.yaml"))
    owner = _owner(tmp_path, str(tmp_path / "gone.yaml"))
    with pytest.raises(RuntimeError, match="M50.*no longer exists"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


def test_m50_relative_config_with_unreadable_cwd_refuses(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml"); owner["cwd"] = None
    with pytest.raises(RuntimeError, match="M50.*cwd"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


def test_m50_a_real_symlink_to_the_same_file_matches(monkeypatch, tmp_path):
    reg = _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    link = tmp_path / "link.yaml"; link.symlink_to(reg)
    owner = _owner(tmp_path, str(link), cwd="/")
    assert P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)["pid"] == 4242


def test_m50_every_persisted_router_string_is_home_scrubbed(monkeypatch, tmp_path):
    """benchmark/results is TRACKED: config, config_raw, cmdline and the error text must all be
    $HOME-form."""
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    reg = home / "ws" / "reg.yaml"; reg.parent.mkdir(); reg.write_text("models: []")
    monkeypatch.setenv("MLX_SERVE_CONFIG", str(reg))
    owner = _owner(tmp_path, str(reg), cwd=str(home))
    owner["cmdline"] = f"{home}/ws/.venv/bin/python {home}/ws/.venv/bin/mlx-serve start"
    blk = P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)
    for k in ("config", "config_raw", "cmdline"):
        assert str(home) not in blk[k] and blk[k].startswith("$HOME"), (k, blk[k])
    monkeypatch.setattr(P, "_LAST_VERIFIED", {})
    monkeypatch.setattr(P, "router_owner", lambda port: {**owner, "env": {"MLX_SERVE_CONFIG": str(home / "other.yaml")}})
    (home / "other.yaml").write_text("x")
    err = P.router_block("http://localhost:8000")["error"]
    assert str(home) not in err and "$HOME" in err


def _fake_opencode(monkeypatch, stdout, rc=0, stderr=""):
    seen = {}

    class R:
        returncode = rc
    R.stdout, R.stderr = stdout, stderr

    def fake_run(argv, **kw):
        seen["argv"], seen["cwd"], seen["env"] = argv, kw.get("cwd"), kw.get("env")
        return R()
    monkeypatch.setattr(P.subprocess, "run", fake_run)
    return seen


def test_m50_opencode_router_base_is_what_opencode_itself_resolves(monkeypatch, tmp_path):
    """Bound to `opencode debug config` run in the CHILD's cwd with the CHILD's env — every config
    source opencode merges (global json/jsonc, config dir, ancestor projects) is opencode's problem."""
    seen = _fake_opencode(monkeypatch, 'some preamble\n{"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8123/v1"}}}}\n')
    env = {"PATH": "/usr/bin", "XDG_DATA_HOME": str(tmp_path)}
    assert P.opencode_router_base(tmp_path, env) == "http://localhost:8123/v1"
    assert seen["argv"][:3] == ["opencode", "debug", "config"]
    assert seen["cwd"] == str(tmp_path) and seen["env"]["XDG_DATA_HOME"] == str(tmp_path)


def test_m50_opencode_router_base_refuses_when_opencode_cannot_resolve(monkeypatch, tmp_path):
    _fake_opencode(monkeypatch, "", rc=1, stderr="boom")
    with pytest.raises(P.ServedConfigError, match="opencode debug config"):
        P.opencode_router_base(tmp_path, {})
    _fake_opencode(monkeypatch, '{"provider": {"other": {}}}')
    with pytest.raises(P.ServedConfigError, match="mlx-local"):
        P.opencode_router_base(tmp_path, {})


# ----------------------------------------------------- M50 round 3 (Codex cold review #2)
@pytest.mark.parametrize("argv,ok", [
    (["/x/.venv/bin/python3", "/x/.venv/bin/mlx-serve", "start"], True),
    (["python", "-m", "mlx_serve", "start"], True),
    (["python", "-m", "mlx_serve.main"], True),
    (["/opt/mlx-serve/.venv/bin/python", "-m", "http.server", "8000"], False),   # substring trap
    (["python", "-m", "http.server", "8000", "--directory", "/opt/mlx-serve"], False),  # arg trap
    (["python", "-u", "-X", "dev", "-m", "mlx_serve"], True),
    (["python", "script.py", "mlx-serve"], False),
    (["node", "mlx-serve"], False),
    (["python", "-m", "mlx_vlm.server", "--model", "x"], False),
    ([], False),
])
def test_m50_router_identity_is_argv_based(argv, ok):
    assert P._is_router_argv(argv) is ok


def test_m50_non_router_owner_under_an_mlx_serve_path_refuses(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    owner["argv"] = ["/opt/mlx-serve/.venv/bin/python", "-m", "http.server", "8000"]
    owner["cmdline"] = " ".join(owner["argv"])
    with pytest.raises(P.ServedConfigError, match="not an mlx-serve router"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


@pytest.mark.parametrize("host,bound,ok", [
    ("127.0.0.1", ["::1"], False),           # sole v6 loopback does not answer a v4 destination
    ("::1", ["127.0.0.1"], False),
    ("127.0.0.1", ["0.0.0.0"], True),
    ("127.0.0.1", ["::"], True),             # wildcard v6 is dual-stack here
    ("::1", ["0.0.0.0"], False),             # a v4 wildcard cannot answer v6
    ("::1", ["::"], True),
    ("localhost", ["0.0.0.0"], True),
    ("localhost", ["::1"], True),
    ("localhost", ["127.0.0.1"], True),
    ("127.0.0.1", [], True),                 # lsof could not tell -> pid found is enough
    ("127.0.0.1", ["*"], True),
])
def test_m50_listener_must_cover_the_destination_family(monkeypatch, tmp_path, host, bound, ok):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml"); owner["bound_ips"] = bound
    if ok:
        assert P.assert_served_config(f"http://{host if ':' not in host else '[' + host + ']'}:8000",
                                      lookup=lambda port: owner)["pid"] == 4242
    else:
        with pytest.raises(P.ServedConfigError, match="does not answer"):
            P.assert_served_config(f"http://{host if ':' not in host else '[' + host + ']'}:8000",
                                   lookup=lambda port: owner)


def test_m50_router_home_is_scrubbed_even_when_it_differs_from_the_drivers(monkeypatch, tmp_path):
    rhome = tmp_path / "router-other"; (rhome / "ws").mkdir(parents=True)
    reg = rhome / "ws" / "reg.yaml"; reg.write_text("models: []")
    monkeypatch.setenv("MLX_SERVE_CONFIG", str(reg))
    owner = _owner(tmp_path, str(reg), cwd=str(rhome))
    owner["env"]["HOME"] = str(rhome)
    owner["argv"] = [f"{rhome}/ws/.venv/bin/python", f"{rhome}/ws/.venv/bin/mlx-serve", "start"]
    owner["cmdline"] = " ".join(owner["argv"])
    blk = P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)
    for k in ("config", "config_raw", "cmdline"):
        assert str(rhome) not in blk[k], (k, blk[k])


def test_m50_all_refusals_are_the_fatal_ServedConfigError(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path)
    with pytest.raises(P.ServedConfigError):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: None)
    assert issubclass(P.ServedConfigError, RuntimeError)


@pytest.mark.parametrize("var", ["OPENCODE_CONFIG_CONTENT", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR"])
def test_m50_opencode_env_overrides_refuse(monkeypatch, tmp_path, var):
    _fake_opencode(monkeypatch, '{"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"}}}}')
    with pytest.raises(P.ServedConfigError, match=var):
        P.opencode_router_base(tmp_path, {var: "x"})


def test_m50_opencode_destination_must_be_the_entry_router(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    _fake_opencode(monkeypatch, '{"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"}}}}')
    monkeypatch.setattr(P, "router_owner", lambda port: _owner(tmp_path, "main_models.yaml", pid=5))
    assert P.assert_opencode_destination(tmp_path, {}, 5) == "http://localhost:8000/v1"
    with pytest.raises(P.ServedConfigError, match="not the router verified at entry"):
        P.assert_opencode_destination(tmp_path, {}, 6)


def test_m50_gather_uses_the_callers_verified_block_over_client_BASE(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    monkeypatch.setattr(P.model_params, "params_for", lambda m, profile, **k: {"temperature": 0.4})
    monkeypatch.setattr(P, "registry_kv", lambda m, path: {"kv_bits": 4})
    monkeypatch.setattr(P, "apc_state", lambda **k: {"apc_enabled": "0", "source": "env"})
    monkeypatch.setattr(P, "registry_draft", lambda m, path=None: {"draft_kind": "off"})
    blk = {"pid": 8123, "config": "$HOME/x", "port": 8123}
    assert P.gather("m", profile="deployed", router=blk)["router"] == blk


# ----------------------------------------------------- M50 round 5 (Codex cold review #4)
@pytest.mark.parametrize("base", ["", None, 42, "localhost:8123/v1", "ftp://x"])
def test_m50_opencode_empty_or_non_http_baseURL_refuses_instead_of_defaulting_to_8000(monkeypatch, tmp_path, base):
    _fake_opencode(monkeypatch, json.dumps({"provider": {"mlx-local": {"options": {"baseURL": base},
                                                                        "api": "http://localhost:8123/v1"}}}))
    with pytest.raises(P.ServedConfigError, match="empty/non-http"):
        P.opencode_router_base(tmp_path, {})


def test_m50_http_proxy_in_the_driver_env_refuses_unless_bypassed(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    for k in ("http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("http_proxy", "http://proxy.example:8888")
    with pytest.raises(P.ServedConfigError, match="http_proxy"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1")
    assert P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)["pid"] == 4242
    monkeypatch.setenv("no_proxy", "example.com")
    with pytest.raises(P.ServedConfigError, match="http_proxy"):
        P.assert_served_config("http://127.0.0.1:8000", lookup=lambda port: owner)


def test_m50_child_env_proxy_is_judged_for_opencode(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    for k in ("http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY"):
        monkeypatch.delenv(k, raising=False)
    _fake_opencode(monkeypatch, '{"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"}}}}')
    monkeypatch.setattr(P, "router_owner", lambda port: _owner(tmp_path, "main_models.yaml", pid=5))
    with pytest.raises(P.ServedConfigError, match="child environment"):
        P.assert_opencode_destination(tmp_path, {"HTTP_PROXY": "http://proxy.example:8888"}, 5)
    assert P.assert_opencode_destination(tmp_path, {"HTTP_PROXY": "http://proxy.example:8888",
                                                    "NO_PROXY": "localhost"}, 5)


# ----------------------------------------------------- M50 round 6 (Codex cold review #5: proxy precedence)
def _no_proxy_env(monkeypatch):
    for k in list(os.environ):
        if k.lower().endswith("_proxy"):
            monkeypatch.delenv(k, raising=False)


def test_m50_env_proxies_matches_urllib_precedence_exactly(monkeypatch):
    """Cross-check the replica against CPython on the same environment — including the reproduced
    `http_proxy=X NO_PROXY=* no_proxy=` case (lowercase empty clears the bypass)."""
    from urllib.request import getproxies_environment
    cases = [
        {"http_proxy": "http://p:1", "NO_PROXY": "*", "no_proxy": ""},
        {"HTTP_PROXY": "http://p:1", "http_proxy": "http://q:2"},
        {"HTTP_PROXY": "http://p:1", "http_proxy": ""},
        {"https_proxy": "http://p:1", "NO_PROXY": "localhost"},
        {"HTTP_PROXY": "http://p:1", "NO_PROXY": "localhost,127.0.0.1"},
    ]
    for case in cases:
        _no_proxy_env(monkeypatch)
        for k, v in case.items():
            monkeypatch.setenv(k, v)
        assert P._env_proxies(dict(os.environ)) == getproxies_environment(), case


def test_m50_reproduced_case_lowercase_empty_no_proxy_still_proxies(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    _no_proxy_env(monkeypatch)
    monkeypatch.setenv("http_proxy", "http://proxy.example:8888")
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "")
    with pytest.raises(P.ServedConfigError, match="proxy"):
        P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)


def test_m50_https_destination_uses_https_proxy(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    _no_proxy_env(monkeypatch)
    monkeypatch.setenv("https_proxy", "http://proxy.example:8888")
    with pytest.raises(P.ServedConfigError, match="https_proxy"):
        P.assert_served_config("https://localhost:8000", lookup=lambda port: owner)
    assert P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)["pid"] == 4242


def test_m50_child_env_case_conflict_is_ambiguous_and_refuses(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    _no_proxy_env(monkeypatch)
    _fake_opencode(monkeypatch, '{"provider": {"mlx-local": {"options": {"baseURL": "http://localhost:8000/v1"}}}}')
    monkeypatch.setattr(P, "router_owner", lambda port: _owner(tmp_path, "main_models.yaml", pid=5))
    with pytest.raises(P.ServedConfigError, match="ambiguous"):
        P.assert_opencode_destination(tmp_path, {"HTTP_PROXY": "http://p:1", "http_proxy": "http://q:2",
                                                 "NO_PROXY": "localhost"}, 5)
    with pytest.raises(P.ServedConfigError, match="ambiguous"):
        P.assert_opencode_destination(tmp_path, {"HTTP_PROXY": "http://p:1", "NO_PROXY": "*", "no_proxy": ""}, 5)
    assert P.assert_opencode_destination(tmp_path, {"HTTP_PROXY": "http://p:1", "NO_PROXY": "localhost"}, 5)
    assert P.assert_opencode_destination(tmp_path, {}, 5)


# ----------------------------------------------------- M50 round 7 (Codex cold review #6: URL canon + no_proxy port)
@pytest.mark.parametrize("base", [" https://localhost:8000", "http://localhost:8000 ", "", "localhost:8000",
                                  "ftp://localhost:8000", "http:///v1"])
def test_m50_non_canonical_base_url_refuses(monkeypatch, tmp_path, base):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    with pytest.raises(P.ServedConfigError, match="base URL"):
        P.assert_served_config(base, lookup=lambda port: owner)


def test_m50_reproduced_whitespace_https_case_is_refused_not_misjudged(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    _no_proxy_env(monkeypatch)
    monkeypatch.setenv("https_proxy", "http://proxy.example:8888")
    with pytest.raises(P.ServedConfigError):
        P.assert_served_config(" https://localhost:8000", lookup=lambda port: owner)


def test_m50_no_proxy_with_port_bypasses_like_urllib(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    _no_proxy_env(monkeypatch)
    monkeypatch.setenv("http_proxy", "http://proxy.example:8888")
    monkeypatch.setenv("no_proxy", "localhost:8000")
    assert P.assert_served_config("http://localhost:8000", lookup=lambda port: owner)["pid"] == 4242
    with pytest.raises(P.ServedConfigError, match="proxy"):
        P.assert_served_config("http://localhost:8001", lookup=lambda port: owner)


def test_m50_router_block_survives_a_non_canonical_base(monkeypatch):
    blk = P.router_block(" http://localhost:8000")
    assert blk["pid"] is None and "base URL" in blk["error"]


def test_m50_port_from_base_defaults(monkeypatch):
    assert P._port_from_base(None) == 8000
    assert P._port_from_base("https://localhost") == 443
    assert P._split_base("http://127.0.0.1:8123/v1") == ("http", "127.0.0.1", 8123)


# ----------------------------------------------------- M50 round 8 (Codex cold review #7: authority as spelled)
class _Routed(Exception):
    def __init__(self, host):
        self.host = host


def _urllib_destination(url, env, monkeypatch):
    """What urllib's REAL ProxyHandler would connect to for `url` under `env` — captured by a stub
    HTTP handler that raises with the final request host instead of opening a socket."""
    import urllib.request as ur
    for k in list(os.environ):
        if k.lower().endswith("_proxy"):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    class Stub(ur.BaseHandler):
        handler_order = 10_000

        def http_open(self, req):
            raise _Routed(req.host)

        def https_open(self, req):
            raise _Routed(req.host)
    opener = ur.OpenerDirector()
    opener.add_handler(ur.ProxyHandler())          # env-derived, as the bench client's default opener
    opener.add_handler(Stub())
    try:
        opener.open(url)
    except _Routed as r:
        return r.host
    raise AssertionError("stub did not fire")


@pytest.mark.parametrize("url,env", [
    ("http://localhost:08000", {"http_proxy": "http://proxy.example:8888", "no_proxy": "localhost:8000"}),
    ("http://localhost", {"http_proxy": "http://proxy.example:8888", "no_proxy": "localhost:80"}),
    ("http://[::1]:8000", {"http_proxy": "http://proxy.example:8888", "no_proxy": "::1"}),
    ("http://localhost:8000", {"http_proxy": "http://proxy.example:8888", "no_proxy": "localhost:8000"}),
    ("http://localhost:8000", {"http_proxy": "http://proxy.example:8888", "no_proxy": "localhost"}),
    ("http://localhost:8001", {"http_proxy": "http://proxy.example:8888", "no_proxy": "localhost:8000"}),
    ("http://127.0.0.1:8000", {"http_proxy": "http://proxy.example:8888", "NO_PROXY": "*", "no_proxy": ""}),
    ("https://localhost:8000", {"https_proxy": "http://proxy.example:8888"}),
    ("https://localhost:8000", {"http_proxy": "http://proxy.example:8888"}),
    ("http://localhost:8000", {"HTTP_PROXY": "http://proxy.example:8888", "http_proxy": ""}),
    ("http://localhost:8000", {}),
])
def test_m50_proxy_decision_is_differential_against_urllibs_ProxyHandler(monkeypatch, url, env):
    """The guard must say 'proxied' exactly when urllib's own transport would connect to the proxy."""
    dest = _urllib_destination(url, env, monkeypatch)
    urllib_proxied = dest.startswith("proxy.example")
    assert (P._proxy_for(url, env) is not None) is urllib_proxied, (url, env, dest)


def test_m50_reproduced_authority_cases_refuse(monkeypatch, tmp_path):
    _driver_registry(monkeypatch, tmp_path, "main_models.yaml")
    owner = _owner(tmp_path, "main_models.yaml")
    _no_proxy_env(monkeypatch)
    monkeypatch.setenv("http_proxy", "http://proxy.example:8888")
    for url, bypass in (("http://localhost:08000", "localhost:8000"), ("http://localhost", "localhost:80"),
                        ("http://[::1]:8000", "::1")):
        monkeypatch.setenv("no_proxy", bypass)
        with pytest.raises(P.ServedConfigError, match="proxy"):
            P.assert_served_config(url, lookup=lambda port: owner)
