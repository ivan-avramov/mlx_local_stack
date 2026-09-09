"""Exercise reviewer persistence, failure handling and exclusion without an LLM."""
import fcntl
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "campaign_review.py"
spec = importlib.util.spec_from_file_location("campaign_review", SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.fixture
def setup(tmp_path):
    fake = tmp_path / "fake_codex.py"
    fake.write_text('''import json, pathlib, sys
root = pathlib.Path(__file__).parent
with (root / "calls.jsonl").open("a") as f: f.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"type": "thread.started", "thread_id": "review-thread"}), flush=True)
if (root / "fail").exists(): sys.exit(7)
out = pathlib.Path(sys.argv[sys.argv.index("-o") + 1])
out.write_text(json.dumps({"status": "healthy", "summary": "fixture progressed", "evidence": ["2/15 to 3/15"], "actions": [], "next_action": "continue"}))
''')
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review the fixture.")
    schema = tmp_path / "schema.json"
    schema.write_text("{}")
    config = dict(codex=[sys.executable, str(fake)], repo=str(tmp_path),
                  workdir=str(tmp_path), prompt=str(prompt), schema=str(schema),
                  state_dir=str(tmp_path / "state"), timeout_seconds=10,
                  enabled=True, notifications=False)
    return tmp_path, config


def test_next_process_resumes_persisted_thread(setup):
    root, config = setup
    assert review.run_once(config) == 0
    assert review.run_once(json.loads(json.dumps(config))) == 0
    calls = [json.loads(s) for s in (root / "calls.jsonl").read_text().splitlines()]
    assert "resume" not in calls[0]
    assert calls[1][calls[1].index("resume") + 1] == "review-thread"
    state = json.loads((root / "state/state.json").read_text())
    assert state["thread_id"] == "review-thread"
    assert state["status"] == "healthy"
    assert (root / "state/latest.md").exists()


def test_agent_crash_is_recorded_and_next_tick_can_retry(setup):
    root, config = setup
    (root / "fail").touch()
    assert review.run_once(config) != 0
    state = json.loads((root / "state/state.json").read_text())
    assert state["status"] == "review_failed"
    assert state["thread_id"] == "review-thread"
    assert not state.get("last_success_at")
    (root / "fail").unlink()
    assert review.run_once(config) == 0


def test_never_overlaps_another_reviewer(setup):
    root, config = setup
    state = Path(config["state_dir"])
    state.mkdir()
    with (state / "review.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert review.run_once(config) == 0
    assert not (root / "calls.jsonl").exists()


def test_pause_survives_restart(setup):
    root, config = setup
    config["enabled"] = False
    assert review.run_once(config) == 0
    assert not (root / "calls.jsonl").exists()


def test_missing_report_is_not_success(setup):
    root, config = setup
    (root / "fake_codex.py").write_text("print('no report')\n")
    assert review.run_once(config) != 0
    assert json.loads((root / "state/state.json").read_text())["status"] == "review_failed"


def test_launch_agent_runs_at_login_and_every_five_minutes(setup):
    root, config = setup
    job = review.launch_agent(config, root / "config.json", SCRIPT)
    assert job["RunAtLoad"] is True
    assert job["StartInterval"] == 300
    assert "--config" in job["ProgramArguments"]
    assert job["WorkingDirectory"] == config["repo"]


@pytest.mark.parametrize("expired", [False, True])
def test_scheduler_crash_does_not_start_a_second_live_reviewer(setup, expired):
    root, config = setup
    fake = root / "fake_codex.py"
    fake.write_text("import time\n" + fake.read_text().replace(
        'out = pathlib.Path', 'time.sleep(30)\nout = pathlib.Path'))
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config))
    parent = subprocess.Popen([sys.executable, str(SCRIPT), "--config", str(config_path)])
    state_path = root / "state/state.json"
    child_pid = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            child_pid = state.get("reviewer_pid")
            if child_pid and (root / "calls.jsonl").exists():
                break
            time.sleep(0.02)
        assert child_pid
        parent.kill()
        parent.wait(timeout=5)
        if expired:
            config["timeout_seconds"] = 0
        assert review.run_once(config) == 0
        assert len((root / "calls.jsonl").read_text().splitlines()) == 1
        if expired:
            assert "expired orphan" in (root / "state/scheduler.log").read_text()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if child_pid:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
