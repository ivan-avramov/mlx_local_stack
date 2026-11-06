"""C296 (1) (session 18): P655 (`--base` resolved to a full sha), P656 items 1–5 (environmental preflight refusals are NOT_STARTED;
`prepare` builds the fork's lock dir + venv; the preflight keeps qualify's stderr tail and reaps its process group on timeout)."""
import json
import os
import subprocess
import sys
import time

import pytest

from . import helpers as H
from .fakes import ARMS, FakeOps


@pytest.fixture
def w(tmp_path, monkeypatch):
    return H.world(tmp_path, monkeypatch)


def main(w, *argv, base=None):
    top = ["--workdir", str(w.wd), "--repo", str(w.main)] + (["--base", base] if base else [])
    return H.K().main(top + list(argv), ops=FakeOps(w))


def state(w):
    return json.loads((w.wd / "p475" / "state.json").read_text())


# ------------------------------------------------------------------------------------------- P655: --base resolution
def test_a_short_base_is_resolved_to_the_full_sha_before_prepare_uses_it(w):
    assert main(w, "prepare", base=w.base[:8]) == 0
    assert state(w)["base"] == w.base


def test_a_short_base_matching_the_recorded_full_base_is_not_a_mismatch(w):
    assert main(w, "prepare", base=w.base) == 0
    assert main(w, "prepare", base=w.base[:8]) == 0
    assert state(w)["base"] == w.base


def test_a_short_base_naming_another_commit_than_the_recorded_one_refuses(w, capsys):
    assert main(w, "prepare", base=w.base) == 0
    assert main(w, "prepare", base="c" * 40) == 2
    assert "recorded base" in capsys.readouterr().err


def test_an_unresolvable_base_refuses_before_anything_is_written(w, capsys):
    w.unresolvable.add("nosuchrev")
    assert main(w, "prepare", base="nosuchrev") == 2
    assert "REFUSED" in capsys.readouterr().err
    assert not (w.wd / "p475" / "state.json").exists()


def test_run_resolves_the_base_too(w):
    H.ready(w)
    args = H.K().parse_args(["--workdir", str(w.wd), "--repo", str(w.main), "--base", w.base[:8], "run", "--smoke"])
    cfg = H.K().config_from_args(args, FakeOps(w))
    assert cfg.base == w.base


# ------------------------------------------------------------------------------------------- P656 1–2: NOT_STARTED preflights
ENVIRONMENTAL = {
    "lease": lambda w: setattr(w, "lease_refuse", True),
    "busy": lambda w: setattr(w, "busy_list", ["4242 python -m something_busy"]),
    "port": lambda w: w.listener.__setitem__(8000, 4243),
    "out_dir": lambda w: (w.wd / "p475" / "preflight" / "AF8.a1").mkdir(parents=True),
}


def clear(w, kind):
    w.lease_refuse, w.busy_list = False, []
    w.listener.pop(8000, None)
    if kind == "out_dir":
        (w.wd / "p475" / "preflight" / "AF8.a1").rmdir()


@pytest.mark.parametrize("kind", sorted(ENVIRONMENTAL))
def test_an_environmental_refusal_is_not_started_and_consumes_no_attempt(w, kind):
    ENVIRONMENTAL[kind](w)
    rec = H.preflight(w, "AF8")
    assert rec["status"] == "NOT_STARTED"
    assert rec["attempts"] == []
    assert w.run_calls == []
    assert rec["not_started"] and rec["not_started"][-1]["reason"]
    on_disk = H.K().read_preflight(H.cfg(w), "AF8")
    assert on_disk["status"] == "NOT_STARTED" and on_disk["attempts"] == []


@pytest.mark.parametrize("kind", sorted(ENVIRONMENTAL))
def test_a_not_started_record_is_never_final(w, kind):
    ENVIRONMENTAL[kind](w)
    assert H.preflight(w, "AF8")["status"] == "NOT_STARTED"
    clear(w, kind)
    rec = H.preflight(w, "AF8")
    assert rec["status"] == "PASS"
    assert len(rec["attempts"]) == 1 and len(rec["not_started"]) == 1


def test_repeated_environmental_refusals_never_finalise_as_refused(w):
    w.lease_refuse = True
    for _ in range(5):
        assert H.preflight(w, "AF8")["status"] == "NOT_STARTED"
    assert w.run_calls == []


def test_the_cli_preflight_exits_nonzero_on_not_started(w, capsys):
    w.lease_refuse = True
    assert main(w, "preflight", "--arm", "AF8", base=w.base) == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "NOT_STARTED"


def test_a_qualify_failure_still_consumes_attempts_and_finalises(w):
    w.preflight_plan["AF8"] = ["refuse"] * 9
    rec = H.preflight(w, "AF8")
    assert rec["status"] == "REFUSED" and len(rec["attempts"]) == 3


def test_run_stops_on_a_not_started_preflight_without_refusing_the_arm(w):
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    w.lease_refuse = True
    rc = H.run_all(w, ops=ops, smoke=True)
    assert rc != 0
    st = state(w)
    assert st["refused_arms"] == []
    assert H.K().read_preflight(H.cfg(w), "N16")["status"] == "NOT_STARTED"
    assert w.spawns == []


# ------------------------------------------------------------------------------------------- P656 3: prepare builds the fork's needs
def test_prepare_creates_the_forks_qualify_lock_dir(w):
    assert H.prepare(w) == []
    assert (w.wd / "p369" / "phase2").is_dir()


def _uv(w, word):
    return [c for c in w.run_calls if c.argv[0] == "uv" and word in c.argv]


def test_prepare_builds_a_missing_fork_venv_pinned_to_the_arm_venv(w):
    fork = w.wt("AF8") / "src" / "mlx-vlm"
    import shutil
    shutil.rmtree(fork / ".venv")
    assert H.prepare(w) == []
    assert (fork / ".venv" / "bin" / "python").exists()
    (freeze,) = _uv(w, "freeze")
    assert freeze.argv[freeze.argv.index("--python") + 1] == str(w.wt("AF8") / ".venv" / "bin" / "python")
    (venv,) = _uv(w, "venv")
    assert str(fork / ".venv") in venv.argv and "3.12" in venv.argv
    (inst,) = _uv(w, "install")
    a = inst.argv
    assert a[a.index("--python") + 1] == str(fork / ".venv" / "bin" / "python")
    assert a[a.index("-e") + 1] == str(fork)
    constraints = (w.wd / a[a.index("-c") + 1]) if not os.path.isabs(a[a.index("-c") + 1]) else a[a.index("-c") + 1]
    text = open(constraints).read()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert "mlx==0.32.4" in lines and "mlx-metal==0.32.4" in lines and "transformers==5.15.0" in lines
    assert not any(ln.startswith("-e") or " @ " in ln for ln in lines)
    assert not any(ln.split("==")[0] in ("mlx-vlm", "mlx-serve", "mlx-local-stack") for ln in lines)


def test_prepare_leaves_an_existing_fork_venv_alone(w):
    assert H.prepare(w) == []
    assert [c for c in w.run_calls if c.argv[0] == "uv"] == []


def test_a_failing_fork_venv_build_is_a_prepare_problem(w):
    import shutil
    shutil.rmtree(w.wt("TQ8") / "src" / "mlx-vlm" / ".venv")
    w.uv_rc = 1
    problems = H.prepare(w)
    assert any(p.startswith("TQ8:") for p in problems)


# ------------------------------------------------------------------------------------------- P656 4–5: stderr tail, group reap
def test_the_preflight_attempt_keeps_qualifys_stderr_tail(w):
    w.preflight_plan["AF8"] = ["rc1", "pass"]
    w.qualify_stderr = "x" * 9000 + "REFUSED: the reason qualify gave"
    rec = H.preflight(w, "AF8")
    tail = rec["attempts"][0]["stderr_tail"]
    assert tail.endswith("REFUSED: the reason qualify gave")
    assert 0 < len(tail) <= 4000


def test_a_timed_out_qualify_keeps_its_stderr_tail_and_is_an_attempt(w):
    w.preflight_plan["AF8"] = ["timeout", "pass"]
    w.qualify_stderr = "qualify: rung 3 of 7"
    rec = H.preflight(w, "AF8")
    assert rec["status"] == "PASS" and len(rec["attempts"]) == 2
    first = rec["attempts"][0]
    assert first["stderr_tail"].endswith("qualify: rung 3 of 7")
    assert any("TimeoutExpired" in p for p in first["problems"])


def _gone(ops, pgid, deadline_s=5.0):
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if not ops.group_alive(pgid):
            return True
        time.sleep(0.1)
    return False


@pytest.mark.parametrize("ignore_term", [False, True])
def test_realops_run_reaps_the_whole_process_group_on_timeout(tmp_path, ignore_term):
    ops = H.K().RealOps(tmp_path)
    pidfile = tmp_path / "pgid"
    trap = "trap '' TERM; " if ignore_term else ""
    script = f"{trap}echo $$ > {pidfile}; echo started >&2; sleep 60 & sleep 60 & wait"
    with pytest.raises(subprocess.TimeoutExpired) as exc:
        ops.run(["/bin/sh", "-c", script], str(tmp_path), dict(os.environ), 5, grace=1)
    pgid = int(pidfile.read_text())
    assert not ops.group_alive(pgid)               # returned only after the group was empty
    assert "started" in (exc.value.stderr or "")


def test_realops_run_returns_output_and_status_like_subprocess_run(tmp_path):
    ops = H.K().RealOps(tmp_path)
    cp = ops.run([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"],
                 str(tmp_path), dict(os.environ), 30)
    assert (cp.returncode, cp.stdout.strip(), cp.stderr.strip()) == (3, "out", "err")
