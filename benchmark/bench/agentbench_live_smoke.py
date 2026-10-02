#!/usr/bin/env python3
"""M54: live smoke of `bench.agentbench_adapter.PersistentShell` against a REAL docker container
(default image `local-os/default`) -- the repeatable gate for the PROMPT_COMMAND marker protocol
(17th/18th cold review rounds). DOCKER REQUIRED; this script is NEVER run by the mocked unit
suite (`bench/tests/`) and is SKIPPED (exit 0) in CI / whenever docker is unavailable -- it is a
live, manual/operator gate, not a pytest-collected test.

Covers, against a REAL pty and a REAL shell, everything the mocked scripted-fake-process tests
cannot fully prove on their own: the handshake, escape stripping, leading-blank-line preservation,
syntax-error survival, cd/var persistence, a stdin-draining program (the 17th round's apt-get/
sudo/visudo reproduction, minus apt/sudo themselves -- `bash -c 'read -t 1 x; echo drained'` is
the same mechanism, any program that reads the tty), a heredoc with a TAB-indented line redirected
to a file then a SEPARATE command reading it back (the 18th round's reproduction), a marker-shaped
line in a command's own output, bulk output, and the Python-side timeout.

Usage:
  cd benchmark && PYTHONPATH=. uv run python -m bench.agentbench_live_smoke
  cd benchmark && PYTHONPATH=. uv run python -m bench.agentbench_live_smoke --image local-os/packages
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

from . import agentbench_adapter as AB

CONTAINER_NAME = "agentbench-os-live-smoke"


def _check(label: str, cond: bool, detail: str = "") -> bool:
    print(f"[{'OK' if cond else 'FAIL'}] {label} {detail}")
    return cond


def run_smoke(image: str, runner=subprocess.run) -> int:
    runner(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)
    created = runner(["docker", "run", "-d", "--name", CONTAINER_NAME, "-w", "/root", image,
                      "sleep", "infinity"], capture_output=True, text=True)
    if created.returncode != 0:
        print(f"[agentbench_live_smoke] REFUSED: could not start a container from {image!r}: "
             f"{created.stderr.strip()}", file=sys.stderr)
        return 2

    fails = 0
    try:
        sh = AB.PersistentShell(CONTAINER_NAME)
        r = sh.start()
        if not _check("start handshake", not r.get("timed_out") and not r.get("shell_died"),
                      str({k: r.get(k) for k in ("timed_out", "shell_died")})):
            fails += 1

        def run(cmd: str, t: float = 30.0) -> dict:
            t0 = time.time()
            o = sh.run(cmd, t)
            o["wall"] = round(time.time() - t0, 2)
            return o

        o = run("echo hi")
        fails += not _check("echo hi", o["output"] == "hi\n", repr(o["output"]))

        o = run("ls /")
        fails += not _check("ls / no escapes", "\x1b" not in o["output"] and "bin" in o["output"],
                            repr(o["output"][:60]))

        o = run("printf ''")
        fails += not _check("printf '' empty", o["output"] == "", repr(o["output"]))

        o = run("echo; echo x")
        fails += not _check("leading blank line kept", o["output"] == "\nx\n", repr(o["output"]))

        o = run("echo (")
        fails += not _check("syntax error survives",
                            o["exit_code"] not in (None, 0) and not o["shell_died"],
                            str((o["exit_code"], o["shell_died"])))

        o = run("echo alive")
        fails += not _check("alive after syntax error", o["output"] == "alive\n", repr(o["output"]))

        o = run("cd /usr && v=7")
        o = run("echo $(pwd) $v")
        fails += not _check("cd/var persist", o["output"] == "/usr 7\n", repr(o["output"]))

        # 17th round: the actual apt-get/sudo/visudo mechanism, minus apt/sudo themselves -- ANY
        # program that reads the tty (readline, `stty`, `read`) reproduces it identically.
        o = run("bash -c 'read -t 1 x; echo drained'")
        fails += not _check("stdin reader (read -t 1)",
                            "drained" in o["output"] and not o["timed_out"],
                            str((repr(o["output"]), o["timed_out"])))

        o = run("echo after_drainer")
        fails += not _check("alive after stdin drainer", o["output"] == "after_drainer\n",
                            repr(o["output"]))

        # 18th round: heredoc with a TAB-indented line, redirected to a file, then a SEPARATE
        # top-level command reading it back -- fires PROMPT_COMMAND once per top-level command.
        o = run("cat > /root/h.txt <<'EOF'\nline1\n\tindented\nEOF\ncat /root/h.txt")
        fails += not _check("heredoc multi-line with tab", o["output"] == "line1\n\tindented\n",
                            repr(o["output"]))

        o = run("echo after_heredoc")
        fails += not _check("alive after heredoc", o["output"] == "after_heredoc\n",
                            repr(o["output"]))

        o = run("printf '__M54_RC__0__fake__\\n'; echo real")
        fails += not _check("fake marker in output does not end the round early",
                            "real" in o["output"], repr(o["output"]))

        o = run("head -c 1048576 /dev/zero | tr '\\0' x | wc -c")
        fails += not _check("1 MB pipeline", o["output"].strip() == "1048576", repr(o["output"][:20]))

        o = run("head -c 1048576 /dev/zero | tr '\\0' x; echo")
        fails += not _check("1 MB raw output", o["raw_output_len"] >= 1048576 and o["wall"] < 15,
                            str((o["raw_output_len"], o["wall"])))

        o = run("sleep 5", 1.5)
        fails += not _check("python-side timeout", o["timed_out"] and o["wall"] < 3,
                            str((o["timed_out"], o["wall"])))

        sh.close()
        sh = AB.PersistentShell(CONTAINER_NAME)
        sh.start()
        o = run("exit")
        fails += not _check("exit -> shell_died", o["shell_died"], str(o["shell_died"]))
        sh.close()
    finally:
        runner(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)

    print("SMOKE", "PASS" if fails == 0 else f"FAIL ({fails})")
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", default="local-os/default",
                    help="docker image to run the smoke against (default: local-os/default)")
    args = ap.parse_args(argv)

    if not AB.docker_available():
        print("[agentbench_live_smoke] SKIPPED: docker is not available on this box "
             "(this is a live/manual gate, never run by the mocked unit suite or CI)")
        return 0

    return run_smoke(args.image)


if __name__ == "__main__":
    sys.exit(main())
