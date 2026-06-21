"""Run generated code / commands against tests in an isolated temp dir with a timeout.
Reusable execution-gating primitive (e.g. for an agent to run repo tests while iterating).
Self-contained; no external deps."""
import os
import subprocess
import tempfile


def run_in_sandbox(files: dict, command: list, timeout: float = 60,
                   env_extra: dict | None = None) -> dict:
    """Write files (relpath -> content) into a fresh temp dir, run `command` there with a
    timeout, capture output. Returns {passed, returncode, stdout, stderr, timed_out}.
    `passed` = the command exited 0 and did not time out."""
    env = {**os.environ, **(env_extra or {})}
    with tempfile.TemporaryDirectory() as d:
        for rel, content in files.items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p) or d, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        try:
            proc = subprocess.run(command, cwd=d, env=env, capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            return {"passed": False, "returncode": None, "timed_out": True,
                    "stdout": (e.stdout or "") if isinstance(e.stdout, str) else "",
                    "stderr": (e.stderr or "") if isinstance(e.stderr, str) else ""}
        except Exception as e:  # noqa: BLE001 — bad command / launch failure
            return {"passed": False, "returncode": None, "timed_out": False,
                    "stdout": "", "stderr": f"{type(e).__name__}: {str(e)[:200]}"}
        return {"passed": proc.returncode == 0, "returncode": proc.returncode,
                "timed_out": False, "stdout": proc.stdout, "stderr": proc.stderr}
