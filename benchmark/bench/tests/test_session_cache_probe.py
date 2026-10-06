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
    pinned = str(tmp_path / "pinned-bin" / "opencode")
    first = scp.opencode_cmd("M", tmp_path, "q1", first=True, binary=pinned)
    later = scp.opencode_cmd("M", tmp_path, "q2", first=False, binary=pinned)
    # C125: argv[0] is the absolute pinned binary, never the bare (PATH-resolved) name
    assert first[0] == pinned and later[0] == pinned and first[1] == "run"
    assert "opencode" not in (first[0], later[0])
    assert "--continue" not in first and first[-1] == "q1" and "--pure" in first
    assert "--continue" in later and "--pure" in later and f"mlx-local/M" in later
    assert "--dir" in later and later[later.index("--dir") + 1] == str(tmp_path)


def test_filler_tokens_scale_with_target():
    a, b = scp.filler(1, 8000), scp.filler(2, 32000)
    assert a != b and len(b) > 3 * len(a)


# ----------------------------------------------------------------------------- M48 A4: big tool result
def test_leg_b_prompts_insert_the_big_file_turn_only_when_asked():
    from bench.session_cache_probe import BIG_FILE_PROMPT, BIG_FILE_TURN, OPENCODE_PROMPTS, leg_b_prompts

    assert leg_b_prompts(4, 0) == OPENCODE_PROMPTS[:4]
    with_file = leg_b_prompts(4, 20000)
    assert with_file[BIG_FILE_TURN - 1] == BIG_FILE_PROMPT
    assert len(with_file) == 4 and with_file[0] == OPENCODE_PROMPTS[0]
    assert leg_b_prompts(2, 20000)[BIG_FILE_TURN - 1] == BIG_FILE_PROMPT  # turn after it kept


def test_write_big_file_puts_the_marker_first(tmp_path):
    from bench.session_cache_probe import _write_big_file

    marker = _write_big_file(tmp_path, 20000)
    body = (tmp_path / "big_notes.txt").read_text()
    assert body.startswith(f"MARKER NUMBER: {marker}\n")
    assert len(body) > 20000 * 3  # ~4 chars/token filler
    assert body.count("\n") > 400  # line-shaped, so opencode's read tool returns it whole


# ----------------------------------------------------------------------------- C125: pinned opencode for leg B
import json
import os
import stat

import pytest

from bench import provenance

PIN = "1.18.30"


def _fake_bin(path, version, log=None, envlog=None):
    """Executable stand-in: prints `version` for --version, records every argv line to `log` and,
    on --version, the env that matters to `envlog`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = f'echo "$0 $@" >> "{log}"\n' if log else ""
    if envlog:
        rec += (f'if [ "$1" = "--version" ]; then env | /usr/bin/grep -E '
                f'"^(HOME|XDG_CONFIG_HOME|XDG_DATA_HOME|XDG_STATE_HOME|TMPDIR|OPENCODE_[A-Z_]*)=" >> "{envlog}"; fi\n')
    path.write_text(f'#!/bin/sh\n{rec}if [ "$1" = "--version" ]; then echo {version}; exit 0; fi\nexit 0\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class _NoLog:
    def __init__(self, path):
        pass

    def new_rows(self):
        return []


@pytest.fixture
def probe(tmp_path, monkeypatch):
    """Everything network/process-shaped is stubbed; returns the call recorders."""
    calls = {"served": 0, "dest": [], "post": 0}

    def served(base=None, *a, **k):
        calls["served"] += 1
        return {"pid": 4242, "config_sha256": "x"}

    def dest(cwd, env, expected_pid, opencode_bin="opencode", pure=False):
        calls["dest"].append({"opencode_bin": opencode_bin, "pure": pure})
        return "http://localhost:8000"

    def post(*a, **k):
        calls["post"] += 1
        return {}

    monkeypatch.setattr(provenance, "assert_served_config", served)
    monkeypatch.setattr(provenance, "assert_opencode_destination", dest)
    monkeypatch.setattr(provenance, "assert_served_config_unchanged", lambda *a, **k: {})
    monkeypatch.setattr(scp, "_post", post)
    monkeypatch.setattr(scp, "worker_pid", lambda hint: 1)
    monkeypatch.setattr(scp, "footprint", lambda pid: {})
    monkeypatch.setattr(scp, "LogTail", _NoLog)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "stack"))
    (tmp_path / "stack").mkdir()
    calls["home"] = tmp_path / "fake-operator-home"      # the preflight must never touch the operator's home
    calls["home"].mkdir()
    monkeypatch.setenv("HOME", str(calls["home"]))
    for v in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TMPDIR"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    calls["wd"] = tmp_path / "stack" / "wd"
    calls["out"] = tmp_path / "out.json"
    return calls


def _run(calls, legs="B", extra=()):
    return scp.main(["--model", "M", "--legs", legs, "--turns", "2", "--workdir", str(calls["wd"]),
                     "--out", str(calls["out"]), "--log", str(calls["wd"] / "x.log"), *extra])


def _refused(calls, rc, *, spawned=False):
    assert rc not in (0, None)
    assert calls["served"] == 0 and calls["post"] == 0 and not calls["wd"].exists()
    assert not list(calls["home"].iterdir())
    if not spawned:   # refused before any spawn: nothing was created under the workdir either
        assert not (calls["wd"].parent / "opencode-probe").exists()


def test_leg_b_refuses_when_no_pinned_binary_is_installed(probe, capsys):
    rc = _run(probe)
    _refused(probe, rc)
    assert "opencode-1.18.30" in capsys.readouterr().err


def test_leg_b_refuses_a_relative_binary_override(probe, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_PROBE_BIN", "opencode")
    _refused(probe, _run(probe))
    assert "absolute" in capsys.readouterr().err


def test_leg_b_refuses_a_non_executable_binary(probe, monkeypatch, tmp_path, capsys):
    b = _fake_bin(tmp_path / "b" / "opencode", PIN)
    b.chmod(0o644)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    _refused(probe, _run(probe))
    assert "not executable" in capsys.readouterr().err


def test_leg_b_refuses_a_wrong_version_and_names_the_pin(probe, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(_fake_bin(tmp_path / "b" / "opencode", "2.0.20")))
    _refused(probe, _run(probe), spawned=True)
    err = capsys.readouterr().err
    assert PIN in err and "2.0.20" in err


def test_leg_b_with_the_pinned_version_proceeds_and_records_it(probe, monkeypatch, tmp_path):
    bin_ = _fake_bin(tmp_path / "stack" / "bin" / "opencode", PIN)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(bin_))
    assert _run(probe) == 0
    res = json.loads(probe["out"].read_text())
    assert res["opencode_version"] == PIN
    assert res["opencode_bin"] == "$STACK_WORKDIR/bin/opencode"
    import hashlib
    assert res["opencode_exe_sha256"] == hashlib.sha256(bin_.read_bytes()).hexdigest()
    assert str(tmp_path) not in probe["out"].read_text()


def test_leg_b_never_resolves_opencode_through_path(probe, monkeypatch, tmp_path):
    """KNOWN POSITIVE: a decoy `opencode` first on PATH writes a marker if it is ever invoked."""
    marker = tmp_path / "decoy-invoked"
    decoy = tmp_path / "decoy" / "opencode"
    decoy.parent.mkdir()
    decoy.write_text(f'#!/bin/sh\necho "$@" >> "{marker}"\nexit 0\n')
    decoy.chmod(0o755)
    monkeypatch.setenv("PATH", f"{decoy.parent}{os.pathsep}{os.environ['PATH']}")
    spawn_log = tmp_path / "spawns.log"
    bin_ = _fake_bin(tmp_path / "stack" / "bin" / "opencode", PIN, log=spawn_log)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(bin_))
    assert _run(probe) == 0
    assert not marker.exists(), "decoy opencode on PATH was invoked"
    runs = [ln for ln in spawn_log.read_text().splitlines() if " run " in ln]
    assert len(runs) == 2
    assert all(ln.startswith(str(bin_) + " run") and "--pure" in ln.split() for ln in runs)
    assert len(probe["dest"]) == 2
    assert all(d == {"opencode_bin": str(bin_), "pure": True} for d in probe["dest"])


def test_legs_a_and_c_never_resolve_a_binary(probe, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("binary resolution attempted without leg B")

    monkeypatch.setattr(scp, "leg_a_control", lambda *a, **k: {})
    monkeypatch.setattr(scp, "leg_c_eviction", lambda *a, **k: {})
    import run_opencode_probe as oc
    for fn in ("_require_opencode_bin", "_opencode_version", "_opencode_bin"):
        monkeypatch.setattr(oc, fn, boom)
    assert _run(probe, legs="A,C") == 0
    res = json.loads(probe["out"].read_text())
    assert "opencode_bin" not in res and "opencode_version" not in res


# ----------------------------------------------------------------------------- C125 review fixes
def test_preflight_version_runs_in_a_bench_owned_env(probe, monkeypatch, tmp_path):
    envlog = tmp_path / "env.log"
    bin_ = _fake_bin(tmp_path / "stack" / "bin" / "opencode", PIN, envlog=envlog)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(bin_))
    monkeypatch.setenv("OPENCODE_CONFIG", "/x")        # a stray operator switch must not reach the child
    assert _run(probe) == 0
    got = dict(ln.split("=", 1) for ln in envlog.read_text().splitlines())
    v = str(tmp_path / "stack" / "opencode-probe" / "version-env")
    for k in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "TMPDIR"):
        assert got[k].startswith(v + "/"), (k, got[k])
    assert "OPENCODE_CONFIG" not in got      # only the bench policy switches survive (SCAFFOLD_ENV_POLICY)
    assert not list(probe["home"].iterdir())


def test_preflight_refuses_when_stack_workdir_is_not_a_directory(probe, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "nonexistent"))
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(_fake_bin(tmp_path / "b" / "opencode", PIN)))
    _refused(probe, _run(probe))
    assert "STACK_WORKDIR" in capsys.readouterr().err
    assert not (tmp_path / "nonexistent").exists()


def test_persisted_binary_path_scrubs_the_login_name(probe, monkeypatch, tmp_path):
    import run_opencode_probe as oc
    monkeypatch.setattr(oc, "_login_name", lambda: "zzfakeuser")
    bin_ = _fake_bin(tmp_path / "zzfakeuser" / "opencode", PIN)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(bin_))
    assert _run(probe) == 0
    text = probe["out"].read_text()
    assert "zzfakeuser" not in text and json.loads(text)["opencode_bin"].endswith("/$USER/opencode")


def test_preflight_stat_permission_error_is_a_refusal(probe, monkeypatch, tmp_path, capsys):
    bin_ = _fake_bin(tmp_path / "b" / "opencode", PIN)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(bin_))
    real = type(bin_).is_file

    def is_file(self):
        if self.name == "opencode":
            raise PermissionError(13, "denied", str(self))
        return real(self)

    monkeypatch.setattr(type(bin_), "is_file", is_file)
    _refused(probe, _run(probe))
    assert "[m45] REFUSED" in capsys.readouterr().err


def test_preflight_version_exiting_nonzero_is_a_refusal(probe, monkeypatch, tmp_path, capsys):
    b = tmp_path / "b" / "opencode"
    b.parent.mkdir()
    b.write_text("#!/bin/sh\nexit 1\n")
    b.chmod(0o755)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    _refused(probe, _run(probe), spawned=True)
    assert "version" in capsys.readouterr().err


def test_preflight_version_timeout_is_a_refusal(probe, monkeypatch, tmp_path, capsys):
    import subprocess as sp
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(_fake_bin(tmp_path / "b" / "opencode", PIN)))

    def hang(*a, **k):
        raise sp.TimeoutExpired("opencode", 30)

    monkeypatch.setattr(sp, "check_output", hang)
    _refused(probe, _run(probe), spawned=True)
    assert "version" in capsys.readouterr().err
