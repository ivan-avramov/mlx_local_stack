"""A manifest must never outlive the rows it describes.

MEASURED 2026-08-14, live, mid-run. Sequence that produced it:

  run 1  starts at max_kv_cache_size 262144 -> --clean-stale deletes the old jsonl AND manifest,
         then stamps a fresh manifest recording 262144. Run 1 generates ZERO rows and is killed,
         so no jsonl is ever created. The manifest survives.
  run 2  starts at max_kv_cache_size 131072. `provenance_precheck` skips the pair entirely because
         its staleness check is gated on `jsonl.exists()` (generate.py) and there is no jsonl. The
         stamping site then declines to write because it only writes `if not mp.exists()`.
  result rows generated at 131072, stamped with a manifest saying 262144.

Why this is severe rather than cosmetic — the manifest is what decides:
  - whether a LATER run treats these rows as resumable (`--clean-stale` compares against it),
  - what config gets published alongside the result,
  - and the RESOLVED THINKING BUDGET (`grade._run_budget_config` reads `kv.max_kv_cache_size` and
    `sampling.max_tokens` to detect the silent server-side clamp). A wrong context limit there
    yields a wrong convergence verdict — the very defect that fix exists to correct.

In the observed case the error was numerically harmless (both 262144 and 131072 exceed
max_tokens + prompt, so the resolved budget was 81920 either way). That was luck, not correctness.

The fix: stamp when the manifest is ABSENT **or INCOMPATIBLE** with the current config, rather than
only when absent.
"""
import json

from bench import generate, provenance


def _cfg(kv):
    """A manifest-shaped dict differing only in the KV cap."""
    return {
        "kv": {"max_kv_cache_size": kv, "kv_bits": 0, "prefill_step_size": 512,
               "hf_path": "x/y", "kv_quant_scheme": None, "quantized_kv_start": None},
        "sampling": {"temperature": 0.4, "max_tokens": 102400, "thinking_budget": 81920},
        "fingerprint_version": 1,
    }


def test_incompatible_orphaned_manifest_is_rewritten(tmp_path, monkeypatch):
    """The live failure: a manifest with no jsonl beside it, describing a DIFFERENT config."""
    mdir = tmp_path / "M"
    mdir.mkdir()
    mp = mdir / "humanevalplus.manifest.json"
    mp.write_text(json.dumps(_cfg(262144)))          # left over from the killed run
    assert not (mdir / "humanevalplus.jsonl").exists()   # ...with no rows: an ORPHAN

    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    written = {}
    monkeypatch.setattr(provenance, "write",
                        lambda m, b, **kw: written.setdefault((m, b), True))
    monkeypatch.setattr(provenance, "current_manifest_lite",
                        lambda m, profile="deployed", **kw: _cfg(131072))

    generate.stamp_manifests([("M", "humanevalplus")], profile="deployed", overrides=None)

    assert ("M", "humanevalplus") in written, (
        "an orphaned manifest describing a different config was NOT rewritten — rows would be "
        "stamped with a config that never produced them")


def test_compatible_manifest_is_left_alone(tmp_path, monkeypatch):
    """Idempotence: a correct manifest must not be rewritten on every resume. Rewriting would
    churn the timestamp and code SHAs on a resumed run, making a partial run look like it was
    produced at whatever moment it last resumed."""
    mdir = tmp_path / "M"
    mdir.mkdir()
    (mdir / "humanevalplus.manifest.json").write_text(json.dumps(_cfg(131072)))

    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    written = {}
    monkeypatch.setattr(provenance, "write",
                        lambda m, b, **kw: written.setdefault((m, b), True))
    monkeypatch.setattr(provenance, "current_manifest_lite",
                        lambda m, profile="deployed", **kw: _cfg(131072))

    generate.stamp_manifests([("M", "humanevalplus")], profile="deployed", overrides=None)

    assert written == {}, "a compatible manifest must not be rewritten"


def test_absent_manifest_is_written(tmp_path, monkeypatch):
    """The original behaviour, preserved."""
    (tmp_path / "M").mkdir()
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    written = {}
    monkeypatch.setattr(provenance, "write",
                        lambda m, b, **kw: written.setdefault((m, b), True))
    monkeypatch.setattr(provenance, "current_manifest_lite",
                        lambda m, profile="deployed", **kw: _cfg(131072))

    generate.stamp_manifests([("M", "mbppplus")], profile="deployed", overrides=None)
    assert ("M", "mbppplus") in written


def test_stamping_never_blocks_a_run(tmp_path, monkeypatch):
    """AGENTS.md: bench tooling graceful-degrades, never crashes the batch. A provenance failure
    must not take down a run that costs hours of the single worker."""
    (tmp_path / "M").mkdir()
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)

    def boom(*a, **kw):
        raise RuntimeError("registry unreadable")

    monkeypatch.setattr(provenance, "current_manifest_lite", boom)
    monkeypatch.setattr(provenance, "write", boom)

    generate.stamp_manifests([("M", "mbppplus")], profile="deployed", overrides=None)  # no raise


# ------------------------------------------------- max_kv_cache_size must be output-determining

def test_kv_cap_is_part_of_the_compatibility_fingerprint():
    """`max_kv_cache_size` changes the OUTPUT, so runs at different caps must never be pooled.

    Proven twice on 2026-08-14, both times the hard way:

    1. IT CHANGES THE TEXT. The server clamps `thinking_budget` to
       `0.8 * (max_kv_cache_size - prompt)`. At 65536 the IFEval runs' declared 81920 budget was
       really ~52390, so `ThinkingBudgetCriteria` cut reasoning short and the model answered from a
       truncated trace. At 131072 the same declared budget is fully in force. Same request, same
       sampling, DIFFERENT generation length limit — 33 rows were mis-scored as converged.
    2. IT CHANGES THE THROUGHPUT. Same box, same model, same sampling: at
       `kv_prealloc_tokens 262144` Ornith-1.0-35B-mlx-uniform-4bit produced ZERO completions in
       19.5 minutes; at 131072 it completed items in 13-27s at ~107 tok/s.

    Before this fix the fingerprint carried `kv_bits` but not the cap, so `--clean-stale` could not
    see the difference and `done_ids` resume would have silently MIXED rows generated under
    different effective budgets. That is the exact contamination the provenance guard exists to
    prevent.
    """
    a = _cfg(65536)
    b = _cfg(131072)
    assert not provenance.is_compatible(a, b), (
        "runs at different max_kv_cache_size compared as COMPATIBLE — resume would pool rows whose "
        "resolved thinking budgets differ")
    assert provenance.is_compatible(_cfg(131072), _cfg(131072))


def test_kv_cap_absent_on_both_sides_is_still_compatible():
    """Pre-manifest-era rows record no cap. Absent-on-both must not be read as a mismatch, or
    `--clean-stale` would delete historical results over a field neither side ever had."""
    a, b = _cfg(131072), _cfg(131072)
    del a["kv"]["max_kv_cache_size"]
    del b["kv"]["max_kv_cache_size"]
    assert provenance.is_compatible(a, b)


# ------------------------------------- the DEPLOYED CODE SHA is output-determining too

def _cfg_sha(vlm_sha, kv=131072):
    return {
        "kv": {"max_kv_cache_size": kv, "kv_bits": 0, "prefill_step_size": 512,
               "hf_path": "x/y", "kv_quant_scheme": None, "quantized_kv_start": None},
        "sampling": {"temperature": 0.4, "max_tokens": 102400, "thinking_budget": 81920},
        "git": {"submodules": {"src/mlx-vlm": vlm_sha, "src/mlx-serve": "aaa"}},
        "fingerprint_version": 1,
    }


def test_a_different_mlx_vlm_sha_is_INCOMPATIBLE():
    """PROVEN 2026-08-14, the hard way. Bumping src/mlx-vlm 8b7100b8 -> 0c1c8b17 (an upstream merge)
    changed generation on a MATCHED item: same prompt (161 tokens both), same sampling, deterministic
    3/3 -- but 2475 -> 3526 completion tokens and 24.8s -> 34.3s. The model implementation
    (qwen3_5_moe) and the sampler (sample_utils.py) were byte-unchanged; the divergence came from
    server/generation.py, models/cache.py or utils.py.

    Without the sha in the fingerprint, `--clean-stale` judged the pre-bump rows COMPATIBLE and
    done_ids skipped all 200 items, so a re-baseline job reported DONE in seconds having generated
    NOTHING -- and any partial run would have silently POOLED rows from two different code versions.
    That is the same failure mode as the missing max_kv_cache_size, one layer down.
    """
    assert not provenance.is_compatible(_cfg_sha("8b7100b8"), _cfg_sha("0c1c8b17")), (
        "rows from different mlx-vlm shas compared as COMPATIBLE — resume would pool outputs from "
        "code versions that provably generate different token streams")
    assert provenance.is_compatible(_cfg_sha("0c1c8b17"), _cfg_sha("0c1c8b17"))


def test_absent_git_block_on_both_sides_stays_compatible():
    """Pre-provenance rows carry no git block. Absent-on-both must not condemn historical results."""
    a, b = _cfg_sha("x"), _cfg_sha("x")
    del a["git"], b["git"]
    assert provenance.is_compatible(a, b)


def test_mlx_serve_sha_also_counts():
    """mlx-serve builds the worker command line (kv flags, generation-defaults, draft-kind), so a
    change there can alter what the worker is even asked to do."""
    a, b = _cfg_sha("same"), _cfg_sha("same")
    b["git"]["submodules"]["src/mlx-serve"] = "bbb"
    assert not provenance.is_compatible(a, b)
