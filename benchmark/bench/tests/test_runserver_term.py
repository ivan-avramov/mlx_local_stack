"""M51 (2026-09-28): `kill -TERM <runserver.sh pid>` must tear down router, workers, task model and
compose, then exit. Reproduced 2026-09-28: the shell AND the router survived TERM, a lean router then
failed to bind :8000 and a parity arm silently ran against the daily driver.

Mechanism (bash 3.2, measured on this box): a trapped signal that arrives while the shell is waiting
on a FOREGROUND child is not delivered until that child exits — `docker compose logs -f` never does.
Ctrl+C only works because SIGINT hits the whole foreground process group. Second fault: the trap is
installed only after both health loops pass, so a TERM during startup orphans both servers.

The test runs a COPY of runserver.sh with a stub bin dir on PATH: fake `uv` (spawns a child like the
real non-exec wrapper and relays TERM to it), fake router (spawns a worker grandchild, relays TERM to
it like mlx-serve's lifespan `unload()`), fake `docker` (`logs -f` blocks forever, `down` leaves a
marker), fake `git`/`curl`/`open`. Real subprocess timeouts throughout (no `timeout` on macOS).
"""
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")   # M58: synthetic models


REPO = Path(__file__).resolve().parents[3]

FAKE_UV = r'''#!/bin/bash
# fake uv: like the real one it does NOT exec; it spawns the child and relays TERM.
relay() { kill -TERM "$C" 2>/dev/null; }
case "$*" in
  "run python -c"*) echo task-model-id ;;
  "run python -u -m mlx_vlm.server"*)
    sleep 100000 & C=$!; echo $C > "$FAKE_STATE/task.pid"; trap relay TERM INT; wait $C; wait $C 2>/dev/null ;;
  "run mlx-serve start")
    "$FAKE_BIN/fake_router" & C=$!; trap relay TERM INT; wait $C; wait $C 2>/dev/null ;;
  *) exit 0 ;;
esac
'''

FAKE_ROUTER = r'''#!/bin/bash
# fake mlx-serve router: owns a worker grandchild; on TERM unloads it (lifespan) and exits.
echo $$ > "$FAKE_STATE/router.pid"
sleep 100000 & W=$!; echo $W > "$FAKE_STATE/worker.pid"
trap 'kill -TERM $W 2>/dev/null; wait $W 2>/dev/null; exit 0' TERM INT
wait $W
'''

FAKE_DOCKER = r'''#!/bin/bash
case "$*" in
  "compose logs -f") echo $$ > "$FAKE_STATE/logs.pid"; exec sleep 100000 ;;
  "compose down") echo down >> "$FAKE_STATE/compose_down" ;;
  *) exit 0 ;;
esac
'''

FAKE_LSOF = r'''#!/bin/bash
# the port check: reports a LISTEN line only while the test plants a "still_bound" file. The REAL
# lsof would see the live daily driver on :8000 and make every teardown take the 30 s slow path.
if [ -e "$FAKE_STATE/still_bound" ]; then printf 'COMMAND PID\nfakerouter 1 (LISTEN)\n'; fi
exit 0
'''

FAKE_CURL = r'''#!/bin/bash
# health probes succeed unless the test plants a "hold" file (startup-phase test).
[ -e "$FAKE_STATE/hold_health" ] && exit 1
exit 0
'''


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid(state: Path, name: str) -> int | None:
    p = state / f"{name}.pid"
    return int(p.read_text().strip()) if p.exists() and p.read_text().strip() else None


def _wait_for(pred, timeout_s: float, what: str):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if pred():
            return
        time.sleep(0.1)
    pytest.fail(f"timed out after {timeout_s}s waiting for {what}")


@pytest.fixture
def fake_stack(tmp_path):
    """A copy of runserver.sh in a scratch repo + the stub bin dir. Yields (repo, state, launch)."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "runserver.sh", repo / "runserver.sh")
    shutil.copy(REPO / "scripts" / "resolve_ca_bundle.sh", repo / "scripts" / "resolve_ca_bundle.sh")
    fake_bin = tmp_path / "bin"; fake_bin.mkdir()
    state = tmp_path / "state"; state.mkdir()
    for name, body in (("uv", FAKE_UV), ("fake_router", FAKE_ROUTER), ("docker", FAKE_DOCKER),
                       ("curl", FAKE_CURL), ("lsof", FAKE_LSOF), ("git", "#!/bin/bash\nexit 0\n"), ("open", "#!/bin/bash\nexit 0\n")):
        f = fake_bin / name
        f.write_text(body)
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "FAKE_BIN": str(fake_bin),
           "FAKE_STATE": str(state)}
    for k in ("STACK_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "COMPOSE_FILE"):
        env.pop(k, None)
    procs = []

    def launch():
        log = open(tmp_path / "runserver.out", "w")
        p = subprocess.Popen(["bash", "./runserver.sh"], cwd=repo, env=env, stdout=log,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        procs.append(p)
        return p, tmp_path / "runserver.out"

    yield repo, state, launch
    for p in procs:  # never leave fake sleepers behind, whatever the outcome
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
    for name in ("task", "router", "worker", "logs"):
        pid = _pid(state, name)
        if pid and _alive(pid):
            os.kill(pid, signal.SIGKILL)


def _assert_torn_down(proc, state, out, phase: str):
    _wait_for(lambda: proc.poll() is not None, 20, f"runserver.sh to exit after TERM ({phase})")
    pids = {n: _pid(state, n) for n in ("task", "router", "worker", "logs")}
    survivors = {n: pid for n, pid in pids.items() if pid and _alive(pid)}
    assert not survivors, f"{phase}: survivors after TERM: {survivors}\n--- log ---\n{out.read_text()[-2000:]}"
    return pids


@pytest.mark.skipif(sys.platform == "win32", reason="bash + signals")
def test_term_after_full_bringup_tears_down_router_workers_and_compose(fake_stack):
    """The 2026-09-28 incident shape: stack fully up, tailing compose logs, operator sends TERM."""
    repo, state, launch = fake_stack
    proc, out = launch()
    _wait_for(lambda: out.exists() and "All services started" in out.read_text(), 60,
              f"full bring-up\n--- log ---\n{out.read_text() if out.exists() else ''}")
    _wait_for(lambda: _pid(state, "logs") is not None, 10, "compose logs -f to start")
    for n in ("task", "router", "worker", "logs"):
        assert _pid(state, n) and _alive(_pid(state, n)), f"fake {n} not running before TERM"

    os.kill(proc.pid, signal.SIGTERM)
    pids = _assert_torn_down(proc, state, out, "after bring-up")
    assert pids["router"] and pids["worker"], "fake router/worker never recorded their pids"
    assert (state / "compose_down").exists(), f"docker compose down never ran\n{out.read_text()[-2000:]}"


@pytest.mark.skipif(sys.platform == "win32", reason="bash + signals")
def test_term_during_startup_wait_does_not_orphan_the_servers(fake_stack):
    """TERM while the script is still spinning on the main-model health loop must still tear down
    whatever it has already launched (both servers are up by then)."""
    repo, state, launch = fake_stack
    (state / "hold_health").write_text("")          # curl fails -> script parks in 'Waiting for main model'
    proc, out = launch()
    _wait_for(lambda: _pid(state, "router") is not None and _pid(state, "task") is not None, 60,
              "both fake servers to be launched")
    _wait_for(lambda: out.exists() and "Waiting for main model" in out.read_text(), 20, "the health wait")

    os.kill(proc.pid, signal.SIGTERM)
    _assert_torn_down(proc, state, out, "during startup")


@pytest.mark.skipif(sys.platform == "win32", reason="bash + signals")
def test_cleanup_exits_nonzero_when_the_port_stays_bound(fake_stack):
    """The stop must VERIFY, not assume: if something still listens on the router port after the
    sweep, runserver.sh says so and exits 1 (same contract as scripts/stack_stop.sh)."""
    repo, state, launch = fake_stack
    (state / "still_bound").write_text("")
    proc, out = launch()
    _wait_for(lambda: out.exists() and "All services started" in out.read_text(), 60, "full bring-up")
    os.kill(proc.pid, signal.SIGTERM)
    _wait_for(lambda: proc.poll() is not None, 60, "runserver.sh to exit")
    assert proc.returncode == 1, out.read_text()[-1500:]
    assert "STILL BOUND" in out.read_text()
