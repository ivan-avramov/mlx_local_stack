"""params_for gains an `official` profile = each family's published recommended sampling
(quality-first eval). The default `production` profile (the daily-driver opencode.json
config) is unchanged.

Official: gemma-4 temp 1.0 / rep_pen 1.0 (Google); Qwen3.6 coding temp 0.6 / min_p 0.0 /
presence_penalty 0.0 (Qwen card). Our production temp-0.7 + Qwen min_p 0.03 / presence 0.3
diverge from these.
"""
import bench.model_params as MP


def test_production_profile_is_default_and_unchanged():
    g = MP.params_for("gemma-4-31b-it-6bit")
    assert g["temperature"] == 0.7                      # daily-driver baseline preserved
    q = MP.params_for("Qwen3.6-27B-UD-MLX-6bit")
    assert q["min_p"] == 0.03 and q["presence_penalty"] == 0.3


def test_official_profile_gemma():
    g = MP.params_for("gemma-4-31b-it-6bit", profile="official")
    assert g["temperature"] == 1.0
    assert g["repetition_penalty"] == 1.0
    assert g["top_k"] == 64
    assert g["enable_thinking"] is True


def test_official_profile_qwen_coding():
    # Qwen3.6-27B-MLX-8bit is not in PARAMS -> resolves to the Qwen family.
    q = MP.params_for("Qwen3.6-27B-MLX-8bit", profile="official")
    assert q["temperature"] == 0.6
    assert q["min_p"] == 0.0
    assert q["presence_penalty"] == 0.0
    assert q["top_k"] == 20


def test_official_qwen_budget_matches_documented_hard_problem_rec():
    # Qwen3.6's official rec for HARD programming problems is ~81,920 generation tokens; our
    # investigation confirmed hard LCB items need ~80K to genuinely converge. The convergence
    # guard flags completion_tokens >= thinking_budget as a non-convergence (loop). If the
    # budget is set below the documented requirement, genuine-but-long reasoning is FALSELY
    # flagged a loop. So the official thinking_budget must be >= 81920, and max_tokens must
    # exceed it (room for the answer AFTER thinking, else a converged trace truncates).
    q = MP.params_for("Qwen3.6-27B-MLX-8bit", profile="official")
    assert q["thinking_budget"] >= 81920
    assert q["max_tokens"] > q["thinking_budget"]
    # The harness clamps thinking_budget to 0.8*max_tokens (room for the answer after the
    # forced close). For the budget to be enforced at face value (not silently shrunk),
    # max_tokens must be >= thinking_budget / 0.8.
    assert q["max_tokens"] >= q["thinking_budget"] / 0.8


def test_production_qwen_budget_unchanged():
    # Daily-driver config is NOT touched by the eval correction.
    q = MP.params_for("Qwen3.6-27B-UD-MLX-6bit", profile="production")
    assert q["thinking_budget"] == 49152
    assert q["max_tokens"] == 81920


def test_coding_profile_gemma_lifts_budget_keeps_converging_sampling():
    # The CODING-capability profile: gemma's daily-driver thinking_budget (16384) truncates
    # hard LCB reasoning mid-think (median ~17K, most items <28K) -> all-INVALID budget-hits.
    # `coding` lifts the budget to 32768 so convergence is MEASURED, not the cap -- while
    # keeping gemma's CONVERGING production sampling (temp 0.7), NOT the loop-prone official 1.0.
    g = MP.params_for("gemma-4-26B-A4B-it-OptiQ-4bit", profile="coding")
    assert g["temperature"] == 0.7                    # production (converging) sampling, not 1.0
    assert g["repetition_penalty"] == 1.08
    assert g["thinking_budget"] == 32768              # lifted from the daily-driver 16384
    assert g["max_tokens"] >= g["thinking_budget"] / 0.8   # clamp-safe (room for the answer)


def test_coding_profile_qwen_has_converging_budget():
    # Qwen already needs (and gets, in its coding sampling) ~81920 to converge on hard LCB.
    q = MP.params_for("Qwen3.6-27B-MLX-8bit", profile="coding")
    assert q["thinking_budget"] >= 81920
    assert q["temperature"] == 0.6                    # qwen coding sampling
    assert q["max_tokens"] >= q["thinking_budget"] / 0.8


def test_production_and_official_profiles_unchanged_by_coding_addition():
    # Adding `coding` must not perturb the existing two profiles.
    assert MP.params_for("gemma-4-31b-it-6bit")["thinking_budget"] == 16384
    assert MP.params_for("gemma-4-31b-it-6bit", profile="official")["temperature"] == 1.0


def test_profile_names_exposes_all_profiles_for_cli_choices():
    # run.py's --sampling-profile choices derive from this, so adding a profile can't drift
    # out of sync with the CLI (which is exactly the bug that made `coding` an invalid choice).
    names = MP.profile_names()
    assert set(names) == {"production", "official", "coding", "deployed"}


def test_ornith_is_qwen_family_by_name_and_registry():
    # Ornith-1.0-35B is qwen3_5_moe arch -> must use Qwen sampling, NOT the
    # gemma name-fallback (no "qwen" substring in the name).
    m = "Ornith-1.0-35B-mlx-uniform-4bit"
    assert MP._family(m) == "qwen"
    off = MP.params_for(m, profile="official")
    assert off["temperature"] == 0.6
    assert off["thinking_budget"] == 81920
    assert off["presence_penalty"] == 0.0


# ------------------------------------------------- penalty overrides (queued presence_penalty OFAT)
def test_run_py_exposes_a_provenance_tracked_presence_penalty_override():
    """Without this flag the ONLY way to vary `presence_penalty` is the registry, which marks every
    existing row STALE and needs a router restart — unusable for an OFAT that must vary one knob on a
    fixed item set. `--temp` and `--thinking-budget` already work this way; the penalties did not.

    It must reach the MANIFEST, not just the request: `presence_penalty` is in _FINGERPRINT_SAMPLING and
    in compare's must-match guard, so an override that did not land in provenance would produce rows
    that silently pool with penalty-0 rows."""
    import subprocess, sys, pathlib
    run_py = pathlib.Path(__file__).resolve().parents[2] / "run.py"
    out = subprocess.run([sys.executable, str(run_py), "generate", "--help"],
                         capture_output=True, text=True).stdout
    assert "--presence-penalty" in out, out[:400]
    assert "--repetition-penalty" in out, out[:400]


def test_penalty_overrides_land_in_the_provenance_manifest(monkeypatch, tmp_path):
    """The override must appear in the fingerprint's sampling slice, or two arms differing only in a
    penalty would compare as identical."""
    from bench import provenance
    monkeypatch.setattr(provenance.model_params, "params_for",
                        lambda m, profile, **k: {"temperature": 0.4, "presence_penalty": 0.0})
    monkeypatch.setattr(provenance, "registry_kv", lambda m, path: {"kv_bits": 0})
    monkeypatch.setattr(provenance, "registry_draft", lambda m, path=None: {"draft_kind": "off"})
    monkeypatch.setattr(provenance, "apc_state", lambda **k: {"apc_enabled": "0", "source": "env"})
    man = provenance.current_manifest_lite("m", "deployed", overrides={"presence_penalty": 0.3})
    fp = provenance.config_fingerprint(man)
    assert fp["sampling"]["presence_penalty"] == 0.3, fp["sampling"]
