"""M45: session-cache mechanics probe — parser / attribution / command-shape tests (no HTTP)."""
from bench import session_cache_probe as scp

LINE = ("2026-09-21 12:37:24,503 - mlx_vlm.server - INFO - Request completed: endpoint=/chat/completions "
        "model=caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed stream=True backend=cached_session "
        "session=anon:f0a482b60a1f4d92 cached_tokens=75004 prompt_tokens=79198 generated_tokens=412 "
        "elapsed=31.250s prefill=134.2 tok/s decode=24.9 tok/s finish_reason=stop in_flight=0")


def test_parse_completed_line_extracts_reuse_fields():
    rows = scp.parse_completed_lines(LINE + "\nnoise line\n" + LINE.replace("75004", "0"))
    assert len(rows) == 2
    r = rows[0]
    assert r["session"] == "anon:f0a482b60a1f4d92"
    assert r["cached_tokens"] == 75004 and r["prompt_tokens"] == 79198
    assert r["generated_tokens"] == 412 and r["elapsed_s"] == 31.25
    assert r["prefill_tps"] == 134.2 and r["backend"] == "cached_session"
    assert r["ts"].startswith("2026-09-21T12:37:24")
    assert rows[1]["cached_tokens"] == 0


def test_reuse_summary_counts_prefilled_tokens_per_request():
    rows = scp.parse_completed_lines(LINE + "\n" + LINE.replace("75004", "0"))
    s = scp.reuse_summary(rows)
    assert s["requests"] == 2
    assert s["prefilled_tokens"] == (79198 - 75004) + 79198
    assert s["reuse_fraction"] == [round(75004 / 79198, 4), 0.0]


def test_footprint_parse_reads_phys_footprint_in_gb():
    txt = "python3.12 [99999]: 64-bit    Footprint: 1360 KB (16384 bytes per page)\n    phys_footprint: 31457280 KB\n    phys_footprint_peak: 33554432 KB\n"
    assert scp.parse_footprint(txt) == {"footprint_gb": 30.0, "peak_gb": 32.0}
    # the tool switches units with size: the live worker printed "37 GB" / "40 GB"
    assert scp.parse_footprint("    phys_footprint: 37 GB\n    phys_footprint_peak: 40 GB\n") == {"footprint_gb": 37.0, "peak_gb": 40.0}
    assert scp.parse_footprint("    phys_footprint: 512 MB\n") == {"footprint_gb": 0.5}


def test_opencode_command_continues_after_first_turn(tmp_path):
    first = scp.opencode_cmd("M", tmp_path, "q1", first=True)
    later = scp.opencode_cmd("M", tmp_path, "q2", first=False)
    assert first[:2] == ["opencode", "run"] and "--continue" not in first and first[-1] == "q1"
    assert "--continue" in later and "--pure" in later and f"mlx-local/M" in later
    assert "--dir" in later and later[later.index("--dir") + 1] == str(tmp_path)


def test_filler_tokens_scale_with_target():
    a, b = scp.filler(1, 8000), scp.filler(2, 32000)
    assert a != b and len(b) > 3 * len(a)
