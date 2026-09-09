#!/usr/bin/env python3
"""Run one persistent Codex campaign review; launchd supplies the five-minute clock."""
import argparse
import fcntl
import json
import os
import plistlib
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LABEL = "local.mlx-stack.codex-review"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def log(root, message):
    with (root / "scheduler.log").open("a") as f:
        f.write(f"{stamp()} {message}\n")


def notify(config, message):
    if not config.get("notifications", True):
        return
    # Arguments are passed as data, never interpolated into AppleScript or a shell.
    script = ('on run argv\n display notification (item 1 of argv) '
              'with title "MLX campaign review" sound name "Glass"\nend run')
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script, message],
                                capture_output=True, text=True, timeout=15)
        log(Path(config["state_dir"]), f"notification delivery command rc={result.returncode}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(Path(config["state_dir"]), f"notification failed: {exc}")


def process_identity(pid):
    """Birth time plus command protects against PID reuse after a restart."""
    if not pid:
        return None
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart=,command="],
                            capture_output=True, text=True, timeout=10)
    if result.stderr.strip():
        raise RuntimeError("Cannot inspect reviewer identity: " + result.stderr.strip())
    return result.stdout.strip() or None


def prior_reviewer_running(root, config):
    state_path = root / "state.json"
    if not state_path.exists():
        return False
    state = json.loads(state_path.read_text())
    pid = state.get("reviewer_pid")
    identity = process_identity(pid)
    if identity and (not state.get("reviewer_identity")
                     or identity == state["reviewer_identity"]):
        age = time.time() - datetime.fromisoformat(state["started_at"]).timestamp()
        if (age > config.get("timeout_seconds", 900)
                and identity == state.get("reviewer_identity")
                and os.getpgid(pid) == pid):
            os.killpg(pid, signal.SIGTERM)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and process_identity(pid) == identity:
                time.sleep(0.1)
            if process_identity(pid) == identity:
                os.killpg(pid, signal.SIGKILL)
            log(root, "RECOVER: stopped expired orphan reviewer; next tick resumes")
            notify(config, "Expired orphan Codex reviewer stopped; next tick resumes review.")
            return True
        log(root, "SKIP: prior reviewer is still running after scheduler exit")
        return True
    return False


def launch_agent(config, config_path, script):
    root = Path(config["state_dir"])
    return {
        "Label": LABEL,
        "ProgramArguments": [config.get("python", sys.executable), str(script),
                             "--config", str(config_path)],
        "WorkingDirectory": config["repo"],
        "RunAtLoad": True,
        "StartInterval": 300,
        "ProcessType": "Background",
        "StandardOutPath": str(root / "launchd.stdout.log"),
        "StandardErrorPath": str(root / "launchd.stderr.log"),
        "EnvironmentVariables": {"PATH": config.get("path", os.defpath),
                                 "STACK_REPO": config["repo"],
                                 "STACK_WORKDIR": config["workdir"]},
    }


def run_once(config):
    root = Path(config["state_dir"])
    root.mkdir(parents=True, exist_ok=True)
    if not config.get("enabled", False):
        log(root, "PAUSED by configuration")
        return 0
    with (root / "review.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(root, "SKIP: another review or operator holds the review lock")
            return 0
        # A detached Codex process can outlive a killed scheduler. Do not resume
        # the same thread twice, even though the scheduler's lock was released.
        if prior_reviewer_running(root, config):
            return 0
        return review_locked(config, root)


def review_locked(config, root):
    state_path = root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not state.get("thread_id") and state.get("run_id"):
        old_events = root / "runs" / state["run_id"] / "events.jsonl"
        if old_events.exists():
            for line in old_events.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "thread.started":
                    state["thread_id"] = event["thread_id"]
    run_id = str(time.time_ns())
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True)
    output = run_dir / "assessment.json"
    events = run_dir / "events.jsonl"
    previous = json.dumps(state, ensure_ascii=False)
    state.update(status="reviewing", started_at=stamp(), run_id=run_id,
                 supervisor_pid=os.getpid())
    save(state_path, state)
    log(root, f"START {run_id} thread={state.get('thread_id', 'new')}")
    cmd = list(config["codex"]) + ["exec", "--approve-for-me", "--add-dir",
                                  config["workdir"], "-C", config["repo"]]
    if state.get("thread_id"):
        cmd += ["resume", state["thread_id"]]
    cmd += ["--json", "--output-schema", config["schema"], "-o", str(output), "-"]
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("CODEX_") and key != "CODEX_HOME":
            env.pop(key)
    env.update(STACK_REPO=config["repo"], STACK_WORKDIR=config["workdir"])
    env.pop("APC_ENABLED", None)
    failure = None
    try:
        prompt = (Path(config["prompt"]).read_text() + "\n\nReview time: " + stamp()
                  + "\nPrevious supervisor state (verify live):\n" + previous
                  + "\nLatest prior assessment: " + str(root / "latest.json") + "\n")
        with events.open("w") as stdout, (run_dir / "stderr.log").open("w") as stderr:
            child = subprocess.Popen(cmd, cwd=config["repo"], env=env,
                                     stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                     text=True, start_new_session=True)
            state["reviewer_pid"] = child.pid
            state["reviewer_identity"] = process_identity(child.pid)
            save(state_path, state)
            try:
                child.communicate(prompt, timeout=config.get("timeout_seconds", 900))
            except subprocess.TimeoutExpired:
                # Stop this agent invocation, never select a benchmark PID by pattern.
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                raise RuntimeError("Codex review exceeded its time bound; next tick retries")
            if child.returncode:
                raise RuntimeError(f"Codex exited {child.returncode}; see {run_dir.name}/stderr.log")
        report = json.loads(output.read_text())
        if report.get("status") not in {"healthy", "recovered", "needs_attention",
                                        "waiting_for_approval", "complete"}:
            raise ValueError("Missing or invalid agent assessment status")
        if not report.get("summary") or not report.get("evidence"):
            raise ValueError("Agent assessment contains no summary/evidence")
        report.update(reviewed_at=stamp(), run_id=run_id)
        save(root / "latest.json", report)
        (root / "latest.md").write_text(
            f"{report['reviewed_at']} — {report['status']}\n\n{report['summary']}\n\n"
            + "\n".join("- " + str(e) for e in report["evidence"])
            + "\n\nActions: " + json.dumps(report.get("actions", []))
            + "\nNext: " + report.get("next_action", "") + "\n")
        state.update(status=report["status"], last_success_at=stamp(),
                     summary=report["summary"])
        state.pop("error", None)
        if report["status"] != "healthy":
            notify(config, report["summary"][:220])
    except Exception as exc:
        failure = str(exc)
        state.update(status="review_failed", error=failure)
        notify(config, "Agent review failed: " + failure[:180])
    finally:
        # Persist the thread even if it crashed after creating a session.
        if events.exists():
            for line in events.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "thread.started" and event.get("thread_id"):
                    state["thread_id"] = event["thread_id"]
        state.update(finished_at=stamp(), reviewer_pid=None)
        save(state_path, state)
        log(root, f"END {run_id} status={state['status']}" + (f" error={failure}" if failure else ""))
    return 1 if failure else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--write-plist", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.write_plist:
        args.write_plist.write_bytes(plistlib.dumps(
            launch_agent(config, args.config.resolve(), Path(__file__).resolve())))
        return 0
    return run_once(config)


if __name__ == "__main__":
    raise SystemExit(main())
