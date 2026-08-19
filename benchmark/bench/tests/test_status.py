"""D5 Part 3: a read-only, one-screen status aggregator.

WHY A SEPARATE SCRIPT from `bench.workqueue --aggregate`. That existing writer produces a
markdown TABLE, on a schedule, as a side effect of the daemon it lives inside -- exactly what an
operator wants tailing a file. This is the complementary read-only case: a human (or another
agent) asking "what's going on RIGHT NOW" from a terminal, without needing to know the daemon's
internals or wait for its next write. It reads the same underlying data (queue state, per-item
watcher output) but never writes anything -- no daemon, no side effects, safe to run at any time
including against a queue that is mid-run.
"""
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "status", Path(__file__).resolve().parents[2] / "m1" / "status.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


def _q(tmp_path, entries, name="work-queue.json"):
    p = tmp_path / name
    p.write_text(json.dumps(entries, indent=1))
    return p


# ---------------------------------------------- queue state counts


def test_queue_state_counts_by_state(tmp_path):
    q = _q(tmp_path, [{"id": "a", "state": "done"}, {"id": "b", "state": "done"},
                       {"id": "c", "state": "queued"}, {"id": "d"}])
    counts = S.queue_state_counts(S._load_queue(q))
    assert counts == {"done": 2, "queued": 1, "pending": 1}


def test_load_queue_tolerates_a_missing_file(tmp_path):
    assert S._load_queue(tmp_path / "nope.json") == []


def test_load_queue_tolerates_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert S._load_queue(p) == []


# ---------------------------------------------- render(): the one-screen summary


def test_render_includes_queue_item_count_and_state_counts(tmp_path):
    q = _q(tmp_path, [{"id": "a", "state": "done"}, {"id": "b", "state": "queued"}])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    text = S.render(q, status_dir)
    assert "2 item" in text
    assert "done: 1" in text
    assert "queued: 1" in text


def test_render_reports_no_watchers_when_status_dir_has_none(tmp_path):
    q = _q(tmp_path, [])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    text = S.render(q, status_dir)
    assert "no watcher" in text.lower()


def test_render_tolerates_a_missing_status_dir(tmp_path):
    q = _q(tmp_path, [])
    text = S.render(q, tmp_path / "does-not-exist")
    assert "no watcher" in text.lower()


def test_render_shows_the_LAST_tick_not_the_first(tmp_path):
    """Per-run last tick (progress/rate/errors) -- must reflect the most recent state, not the
    file's first line, or a healthy long-running watch reads as stuck at its first tick forever."""
    q = _q(tmp_path, [])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    (status_dir / "watch_M_ifeval.md").write_text(
        "===== 10:00:00  driver=ALIVE =====\n"
        "M\n"
        "  1 PROGRESS  n=5/100  +5 since last tick\n"
        "  2 RATE      mean 25.0s/item -> ETA 0.7h for 95 left\n"
        "  3 OUTPUT    errors=0 nonconverged=0 kinds={} degen=0 (wall 0%)\n"
        "  4 CORRECTION none\n"
        "===== 10:05:00  driver=ALIVE =====\n"
        "M\n"
        "  1 PROGRESS  n=8/100  +3 since last tick\n"
        "  2 RATE      mean 24.0s/item -> ETA 0.6h for 92 left\n"
        "  3 OUTPUT    errors=1 nonconverged=0 kinds={} degen=0 (wall 0%)\n"
        "  4 CORRECTION none\n"
    )
    text = S.render(q, status_dir)
    assert "watch_M_ifeval" in text
    assert "n=8/100" in text
    assert "n=5/100" not in text
    assert "errors=1" in text
    assert "driver=ALIVE" in text


def test_render_flags_a_gone_driver(tmp_path):
    q = _q(tmp_path, [])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    (status_dir / "watch_M_ifeval.md").write_text(
        "===== 10:00:00  driver=GONE =====\nM\n  1 PROGRESS  n=5/100\n"
    )
    text = S.render(q, status_dir)
    assert "GONE" in text


def test_render_handles_a_watch_file_with_no_ticks_yet(tmp_path):
    q = _q(tmp_path, [])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    (status_dir / "watch_M_ifeval.md").write_text("")
    text = S.render(q, status_dir)
    assert "watch_M_ifeval" in text


def test_render_ignores_current_md_written_by_the_workqueue_aggregator(tmp_path):
    """current.md is bench.workqueue's own output file, not a per-item watcher -- must not be
    double-counted or mistaken for a watch file."""
    q = _q(tmp_path, [])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    (status_dir / "current.md").write_text("STALE AGGREGATE TABLE\n")
    text = S.render(q, status_dir)
    assert "STALE AGGREGATE TABLE" not in text
    assert "no watcher" in text.lower()


def test_render_lists_multiple_watchers(tmp_path):
    q = _q(tmp_path, [])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    (status_dir / "watch_A_ifeval.md").write_text(
        "===== 10:00:00  driver=ALIVE =====\nA\n  1 PROGRESS  n=1/10\n")
    (status_dir / "watch_B_mbppplus.md").write_text(
        "===== 10:00:00  driver=ALIVE =====\nB\n  1 PROGRESS  n=2/10\n")
    text = S.render(q, status_dir)
    assert "watch_A_ifeval" in text and "watch_B_mbppplus" in text


# ---------------------------------------------- CLI


def test_cli_main_prints_the_report_and_returns_zero(tmp_path, capsys):
    q = _q(tmp_path, [{"id": "a", "state": "done"}])
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    rc = S.main(["--queue", str(q), "--status-dir", str(status_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "done: 1" in out


def test_cli_queue_and_status_dir_default_without_being_given(monkeypatch, tmp_path):
    """Defaults resolve the same way bench.workqueue's do -- $STACK_WORKDIR/status when set, and
    <repo>/docs/work-queue.json for the queue -- so the operator never has to pass either flag on
    the box the daemon actually runs on."""
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    from bench import paths
    assert S._default_queue_path() == paths.repo_root() / "docs" / "work-queue.json"


def test_cli_status_dir_honors_STACK_WORKDIR(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    assert S._default_status_dir() == tmp_path / "status"
