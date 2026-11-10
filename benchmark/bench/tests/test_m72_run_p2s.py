"""M72 P2' stage 1: the launcher `benchmark/spikes/m72_run_p2s.sh` exit-code contract (fake `uv` / `sleep` / `pmset` on PATH, no GPU,
no MLX) and the probe's `--mode` / `--arm-order` arguments (parsed from the source with `ast`: the probe imports MLX at module load).

Spec: two passes `p2s-1` (`--arm-order forward`) and `p2s-2` (`--arm-order reverse`), one 600 s idle between them, exit 10 when
`<out_dir>` already holds `p2s-1.json` / `p2s-2.json` (nothing run), exit 11 / 12 = the first failing pass (never masked), mode 755.
Each test is classed in its comment (new behaviour / preserves an invariant).
"""
from __future__ import annotations

import ast
import os
import stat
import subprocess
from pathlib import Path

import pytest

SPIKES = Path(__file__).resolve().parents[2] / "spikes"
LAUNCHER = SPIKES / "m72_run_p2s.sh"
PROBE = SPIKES / "m72_tq4_probe.py"

FAKE_UV = """#!/bin/sh
# fake `uv run python <probe> --mode p2s --out <json> ...`: log argv, succeed or fail by the pass's name
echo "$@" >>"$FAKE_LOG/uv.log"
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--out" ]; then out=$2; fi
  shift
done
echo "uv $(basename "$out")" >>"$FAKE_LOG/seq.log"
case "$out" in
  *p2s-1.json) rc=${FAKE_RC1:-0} ;;
  *p2s-2.json) rc=${FAKE_RC2:-0} ;;
  *) rc=99 ;;
esac
[ "$rc" = 0 ] && echo '{}' >"$out"
exit $rc
"""
FAKE_SLEEP = """#!/bin/sh
echo "sleep $*" >>"$FAKE_LOG/sleep.log"
echo "sleep $*" >>"$FAKE_LOG/seq.log"
exit 0
"""
FAKE_PMSET = """#!/bin/sh
echo " Currently drawing from 'AC Power'"
echo " -InternalBattery-0 (id=1)	80%; charging; 0:30 remaining present: true"
exit 0
"""


@pytest.fixture()
def box(tmp_path):
    bindir, log = tmp_path / "bin", tmp_path / "log"
    bindir.mkdir()
    log.mkdir()
    for name, body in (("uv", FAKE_UV), ("sleep", FAKE_SLEEP), ("pmset", FAKE_PMSET)):
        p = bindir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return tmp_path, bindir, log


def launch(box, rc1=0, rc2=0, direct=False, existing=()):
    """Run the launcher with the fakes on PATH. ``direct``: execute the file itself (shebang) instead of ``zsh <file>``;
    ``existing``: names created in <out_dir> before the run (e.g. "p2s-1.json")."""
    tmp, bindir, log = box
    out = tmp / "out"
    if existing:
        out.mkdir()
        for name in existing:
            (out / name).write_text("{}")
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(log),
           "FAKE_RC1": str(rc1), "FAKE_RC2": str(rc2)}
    argv = [str(LAUNCHER), str(out)] if direct else ["zsh", str(LAUNCHER), str(out)]
    r = subprocess.run(argv, cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
    uv = (log / "uv.log").read_text().splitlines() if (log / "uv.log").exists() else []
    sl = (log / "sleep.log").read_text().splitlines() if (log / "sleep.log").exists() else []
    return r, out, uv, sl


def sequence(box):
    log = box[2] / "seq.log"
    return log.read_text().splitlines() if log.exists() else []


# class: new behaviour (the monitor's own `sleep 60` calls are allowed; exactly one `sleep 600`, between the passes)
def test_launcher_runs_two_passes_with_mode_p2s_and_idles_600(box):
    r, out, uv, sl = launch(box)
    assert r.returncode == 0, r.stderr
    assert len(uv) == 2
    for line, name in zip(uv, ("p2s-1", "p2s-2")):
        assert "m72_tq4_probe.py" in line and "--mode p2s" in line
        assert f"--out {out}/{name}.json" in line
    assert sl.count("sleep 600") == 1
    events = [e for e in sequence(box) if e.startswith("uv ") or e == "sleep 600"]
    assert events == ["uv p2s-1.json", "sleep 600", "uv p2s-2.json"]
    assert (out / "p2s-1.json").exists() and (out / "p2s-2.json").exists()


# class: new behaviour (counterbalanced arm order: pass 1 forward, pass 2 reverse)
def test_launcher_pass_one_forward_pass_two_reverse(box):
    r, _out, uv, _sl = launch(box)
    assert r.returncode == 0, r.stderr
    assert "--arm-order forward" in uv[0] and "--arm-order reverse" not in uv[0]
    assert "--arm-order reverse" in uv[1] and "--arm-order forward" not in uv[1]


# class: new behaviour (refuse to overwrite a previous run: exit 10, nothing run, nothing created or overwritten)
@pytest.mark.parametrize("existing", [("p2s-1.json",), ("p2s-2.json",), ("p2s-1.json", "p2s-2.json")])
def test_launcher_refuses_an_out_dir_holding_a_previous_pass(box, existing):
    r, out, uv, sl = launch(box, existing=existing)
    assert r.returncode == 10, (r.returncode, r.stderr)
    assert r.stderr.strip() or r.stdout.strip()
    assert uv == [] and sl == [] and sequence(box) == []
    assert sorted(p.name for p in out.iterdir()) == sorted(existing)
    assert all((out / n).read_text() == "{}" for n in existing)


# class: new behaviour (the refusal is about the two pass files only; the other modes' files do not refuse)
@pytest.mark.parametrize("other", ("notes.txt", "mma-1.json", "mma-2.json", "probe-nax-on-1.json"))
def test_launcher_accepts_an_out_dir_with_unrelated_files(box, other):
    r, out, uv, _sl = launch(box, existing=(other,))
    assert r.returncode == 0, r.stderr
    assert len(uv) == 2 and (out / other).exists()


# class: new behaviour (executable, mode 755, runs when invoked directly)
def test_launcher_is_executable_mode_755():
    assert stat.S_IMODE(LAUNCHER.stat().st_mode) == 0o755


# class: new behaviour
def test_launcher_runs_when_invoked_directly(box):
    r, out, uv, _sl = launch(box, direct=True)
    assert r.returncode == 0, r.stderr
    assert len(uv) == 2 and (out / "p2s-2.json").exists()


# class: new behaviour (the exit-10 refusal also works when invoked directly)
def test_launcher_direct_invocation_refuses_too(box):
    r, _out, uv, _sl = launch(box, direct=True, existing=("p2s-1.json",))
    assert r.returncode == 10 and uv == []


# class: new behaviour (exit code = first failing pass, never masked; 5 = the probe's idle-GPU gate)
@pytest.mark.parametrize("rc1,rc2,want", [(5, 0, 11), (1, 0, 11), (3, 0, 11), (0, 5, 12), (0, 1, 12), (5, 5, 11)])
def test_launcher_exit_code_is_the_first_failing_pass(box, rc1, rc2, want):
    r, _out, _uv, _sl = launch(box, rc1=rc1, rc2=rc2)
    assert r.returncode == want, (r.returncode, r.stderr)


# class: new behaviour (a failing pass 1 stops the run: no idle, no pass 2)
def test_launcher_stops_after_a_failing_first_pass(box):
    r, _out, uv, sl = launch(box, rc1=5)
    assert r.returncode == 11
    assert len(uv) == 1 and "sleep 600" not in sl


# class: preserves an invariant (a pass-2 failure does not erase pass 1)
def test_launcher_keeps_pass_one_json_when_pass_two_fails(box):
    r, out, _uv, _sl = launch(box, rc2=1)
    assert r.returncode == 12
    assert (out / "p2s-1.json").exists()


# class: new behaviour (creates a missing out_dir; usage error without an argument)
def test_launcher_creates_the_out_dir_and_rejects_a_missing_argument(box):
    r, out, _uv, _sl = launch(box)
    assert r.returncode == 0 and out.is_dir()
    bad = subprocess.run(["zsh", str(LAUNCHER)], capture_output=True, text=True, timeout=30)
    assert bad.returncode == 2 and bad.stderr.strip()


def probe_argument(flag):
    tree = ast.parse(PROBE.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == flag):
            return {kw.arg: kw.value for kw in node.keywords}
    pytest.fail(f"probe has no {flag} argument")


# class: new behaviour (the probe gains `--mode p2s`); preserves `full` / `mq` / `mma` and the default
def test_probe_mode_choices_include_p2s_and_keep_the_others():
    kw = probe_argument("--mode")
    choices = ast.literal_eval(kw["choices"])
    assert {"full", "mq", "mma", "p2s"} <= set(choices)
    assert ast.literal_eval(kw["default"]) == "full"


# class: preserves an invariant (`--arm-order` keeps forward / reverse and the forward default)
def test_probe_arm_order_argument_still_defaults_to_forward():
    kw = probe_argument("--arm-order")
    assert "choices" in kw  # its real values (forward, reverse) are checked in test_m72_p2s_probe_gpu.py
    assert ast.literal_eval(kw["default"]) == "forward"
