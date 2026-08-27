"""D7 part 1: `opencode` is the primary agentic harness for the "coding" role; `aider` (retired as a
harness 2026-08-16 -- see AGENTS.md client integrations table) is demoted to a diagnostic column and
must not be counted toward, or mistaken for, the "coding" role's headline verdict.
"""
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "scoreboard", Path(__file__).resolve().parents[2] / "m1" / "scoreboard.py")
SB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SB)


def _write_rows(root: Path, model: str, bench: str, rows: list[dict], score: dict | None = None):
    d = root / model
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{bench}.jsonl"
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    if score is not None:
        p.with_suffix(".score.json").write_text(json.dumps(score))
    return p


def _humaneval_rows(n=12):
    return [{"id": i, "wall_s": 1.0, "finish_reason": "stop", "completion_tokens": 10,
              "thinking_budget": 8192} for i in range(n)]


# --------------------------------------------------------------------------- ROLES / DIAGNOSTIC_ROLES
def test_opencode_is_in_the_coding_role():
    assert "opencode" in SB.ROLES["coding"]


def test_aider_is_not_in_the_coding_role():
    """aider must not publish under the coding role headline any more -- it moved to DIAGNOSTIC_ROLES."""
    assert "aider" not in SB.ROLES["coding"]


def test_aider_is_a_diagnostic_for_coding():
    assert "aider" in SB.DIAGNOSTIC_ROLES.get("coding", [])


def test_other_coding_benches_unaffected():
    for b in ("humanevalplus", "mbppplus", "livecodebench"):
        assert b in SB.ROLES["coding"]


# --------------------------------------------------------------------------- verdict()
def test_verdict_ignores_aider_for_coverage_math(monkeypatch, tmp_path):
    """A model with ONLY aider rows (no opencode/humanevalplus/mbppplus/livecodebench) must read as
    NOT MEASURED on the coding role -- aider no longer counts toward "have"."""
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "aider", _humaneval_rows(110),
                score={"acc": 0.5, "acc_strict": 0.5})
    data = SB.collect()
    assert SB.verdict(data["modelX"], "coding") == "NOT MEASURED"


def test_verdict_counts_opencode_toward_coding_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "opencode", _humaneval_rows(22),
                score={"acc": 0.7, "acc_strict": 0.7})
    data = SB.collect()
    v = SB.verdict(data["modelX"], "coding")
    assert "1/4 axes" in v
    assert "missing" in v and "aider" not in v.split("missing")[1]


# --------------------------------------------------------------------------- rendering (main --md)
def test_diagnostic_bench_marked_in_main_table(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "aider", _humaneval_rows(110),
                score={"acc": 0.5, "acc_strict": 0.5})
    _write_rows(tmp_path, "modelX", "opencode", _humaneval_rows(22),
                score={"acc": 0.7, "acc_strict": 0.7})
    SB.main(["--md"])
    out = capsys.readouterr().out
    assert "aider [diag]" in out
    assert "opencode" in out and "opencode [diag]" not in out


# --------------------------------------------------------------------------- kv column (operator 2026-08-26)
def _write_pair(root: Path, model: str, stem: str, n: int, kv: dict | None):
    """Rows + score + (optionally) a manifest carrying the kv provenance block."""
    d = root / model
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stem}.jsonl"
    with p.open("w") as f:
        for r in _humaneval_rows(n):
            f.write(json.dumps(r) + "\n")
    p.with_suffix(".score.json").write_text(json.dumps({"acc": 0.5, "acc_strict": 0.5}))
    if kv is not None:
        p.with_name(f"{stem}.manifest.json").write_text(json.dumps({"kv": kv}))
    return p


def test_kv_label_rendering():
    assert SB._kv_label({"kv_bits": 4, "kv_quant_scheme": "turboquant"}) == "TQ4"
    assert SB._kv_label({"kv_bits": 4, "kv_quant_scheme": "uniform"}) == "uniform4"
    assert SB._kv_label({"kv_bits": 0, "kv_quant_scheme": None}) == "fp16"
    assert SB._kv_label({}) is None                      # pre-provenance manifest -> unknown, never fp16


def test_kv_column_read_from_manifest(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_pair(tmp_path, "modelX", "humanevalplus", 12,
                kv={"kv_bits": 4, "kv_quant_scheme": "turboquant"})
    SB.main(["--md"])
    out = capsys.readouterr().out
    assert "| kv |" in out.splitlines()[0] + out.splitlines()[0]
    assert " TQ4 " in out.replace("|", " ")


def test_kv_missing_manifest_reads_na(monkeypatch, tmp_path, capsys):
    """No manifest (pre-manifest run) must render n/a — unknown is never mistaken for fp16."""
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_pair(tmp_path, "modelX", "humanevalplus", 12, kv=None)
    SB.main(["--md"])
    out = capsys.readouterr().out
    row = [l for l in out.splitlines() if "humanevalplus" in l][0]
    assert row.rstrip().endswith("n/a |")


def test_kv_comes_from_the_selected_variant(monkeypatch, tmp_path, capsys):
    """collect() keeps the largest-n variant; the kv cell must come from THAT file's manifest."""
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_pair(tmp_path, "modelX", "humanevalplus", 5,
                kv={"kv_bits": 4, "kv_quant_scheme": "uniform"})
    _write_pair(tmp_path, "modelX", "humanevalplus.big", 20,
                kv={"kv_bits": 4, "kv_quant_scheme": "turboquant"})
    data = SB.collect()
    assert data["modelX"]["humanevalplus"]["kv"] == "TQ4"


# --------------------------------------------------------------------------- attn-fraction marker (operator 2026-08-26)
def test_attn_layers_qwen3_5_style():
    cfg = {"text_config": {"layer_types": ["linear_attention"] * 3 + ["full_attention"]}}
    assert SB._attn_layers(cfg) == (1, 4)


def test_attn_layers_gemma4_style():
    """sliding_attention layers are RotatingKVCache — quantize_entry skips them, so they do
    NOT count toward the quantizable-KV numerator."""
    cfg = {"text_config": {"layer_types": ["sliding_attention"] * 5 + ["full_attention"]}}
    assert SB._attn_layers(cfg) == (1, 6)


def test_attn_layers_nemotron_h_style():
    cfg = {"layers_block_type": ["mamba", "moe", "attention", "moe", "mamba"]}
    assert SB._attn_layers(cfg) == (1, 5)


def test_attn_layers_full_attention_arch_is_none():
    """No layer typing => every layer grows quantizable KV => no marker."""
    assert SB._attn_layers({"num_hidden_layers": 32}) is None


def test_kv_marker_appended_for_hybrid(monkeypatch, tmp_path):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    SB._ATTN_CACHE.clear()
    monkeypatch.setattr(SB, "_config_for", lambda hf: {
        "text_config": {"layer_types": ["linear_attention"] * 48 + ["full_attention"] * 16}})
    _write_pair(tmp_path, "modelX", "humanevalplus", 12,
                kv={"kv_bits": 4, "kv_quant_scheme": "turboquant", "hf_path": "org/m"})
    data = SB.collect()
    assert data["modelX"]["humanevalplus"]["kv"] == "TQ4·attn16/64"


def test_kv_marker_absent_when_config_unresolvable(monkeypatch, tmp_path):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    SB._ATTN_CACHE.clear()
    monkeypatch.setattr(SB, "_config_for", lambda hf: None)
    _write_pair(tmp_path, "modelX", "humanevalplus", 12,
                kv={"kv_bits": 4, "kv_quant_scheme": "turboquant", "hf_path": "org/m"})
    data = SB.collect()
    assert data["modelX"]["humanevalplus"]["kv"] == "TQ4"


def test_role_coverage_section_shows_diagnostic_separately(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "aider", _humaneval_rows(110),
                score={"acc": 0.5, "acc_strict": 0.5})
    SB.main([])
    out = capsys.readouterr().out
    assert "coding" in out and "NOT MEASURED" in out
    assert "coding [diag]" in out
    assert "aider" in out.split("coding [diag]")[1].split("\n")[0]


# --------------------------------------------------------------------------- C34: samples-sidecar shadowing


def test_tune_suffixed_samples_sidecar_never_shadows_graded_variant(monkeypatch, tmp_path):
    """C34 (2026-08-26): evalplus grading writes padded FULL-CORPUS `<bench>.<tune>_samples.jsonl`
    sidecars (bare task_id+solution rows, no score file beside them). The `_samples` skip tested
    only the bench prefix (`f.stem.split(".")[0]`), which catches `humanevalplus_samples.jsonl`
    but NOT `humanevalplus.m23_samples.jsonl` — so the sidecar entered largest-n variant
    selection and the pair printed `164 ungraded`, shadowing a genuinely graded variant."""
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "humanevalplus.t06", _humaneval_rows(47),
                {"acc": 0.894, "acc_strict": 0.84, "conv_rate": 1.0, "loop_ids": []})
    _write_rows(tmp_path, "modelX", "humanevalplus.m23_samples",
                [{"task_id": f"HumanEval/{i}", "solution": "pass"} for i in range(164)])
    rec = SB.collect()["modelX"]["humanevalplus"]
    assert rec["n"] == 47
    assert rec["acc"] == 0.894


def test_unsuffixed_samples_sidecar_still_skipped(monkeypatch, tmp_path):
    """The pre-C34 behavior that DID work must keep working: a tune-less
    `humanevalplus_samples.jsonl` sidecar never becomes a variant."""
    monkeypatch.setattr(SB.paths, "default_results_root", lambda: tmp_path)
    _write_rows(tmp_path, "modelX", "humanevalplus.t06", _humaneval_rows(10),
                {"acc": 0.9, "acc_strict": 0.9, "conv_rate": 1.0, "loop_ids": []})
    _write_rows(tmp_path, "modelX", "humanevalplus_samples",
                [{"task_id": f"HumanEval/{i}", "solution": "pass"} for i in range(164)])
    rec = SB.collect()["modelX"]["humanevalplus"]
    assert rec["n"] == 10
    assert rec["acc"] == 0.9
