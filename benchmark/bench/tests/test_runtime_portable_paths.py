"""Handoff 2026-10-06 item 4: `vision_gate` wrote an unscrubbed absolute `corpus` path into its
manifest (the adoption manifest was hand-scrubbed; the PII hook caught it). The fix is central:
every string the caller declares in `runtime` is rewritten to placeholder form by
`provenance.portable_path` ($STACK_WORKDIR first, then $HOME) inside `_runtime_block`, so no
driver can leak an absolute home path through its manifest again. Readers that turn a manifest
path back into a filesystem path go through `provenance.expand_portable`."""
import os
from pathlib import Path
from types import SimpleNamespace

import bench.paths as paths
import bench.provenance as P


def _homes(monkeypatch, tmp_path):
    home = tmp_path / "home"
    wd = home / "ws" / "workdir"
    wd.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home), 1) if p.startswith("~") else p)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    return home, wd


def test_portable_path_prefers_the_workdir_placeholder_over_home(monkeypatch, tmp_path):
    home, wd = _homes(monkeypatch, tmp_path)
    assert P.portable_path(str(wd / "m54" / "x.jsonl")) == "$STACK_WORKDIR/m54/x.jsonl"
    assert P.portable_path(str(home / "repo" / "c.jsonl")) == "$HOME/repo/c.jsonl"
    assert P.portable_path("/tmp/elsewhere") == "/tmp/elsewhere"
    assert P.portable_path(None) is None
    assert P.portable_path(7) == 7


def test_portable_path_survives_a_missing_workdir(monkeypatch, tmp_path):
    home, _ = _homes(monkeypatch, tmp_path)
    monkeypatch.delenv("STACK_WORKDIR")
    monkeypatch.setattr(paths, "resolve_stack_workdir", lambda required=True: None)
    assert P.portable_path(str(home / "a")) == "$HOME/a"


def test_expand_portable_round_trips(monkeypatch, tmp_path):
    home, wd = _homes(monkeypatch, tmp_path)
    for raw in (str(wd / "m54" / "t"), str(home / "x"), "/tmp/plain"):
        assert P.expand_portable(P.portable_path(raw)) == raw
    assert P.expand_portable(None) is None


def test_runtime_block_scrubs_nested_caller_strings(monkeypatch, tmp_path):
    home, wd = _homes(monkeypatch, tmp_path)
    monkeypatch.setattr(P, "apc_state", lambda *a, **k: {"apc_enabled": False, "source": "t"})
    monkeypatch.setattr(P, "session_retention_state", lambda: {})
    blk = P._runtime_block({"corpus": str(home / "c.jsonl"),
                            "paths": [str(wd / "a"), {"deep": str(home / "d")}],
                            "n": 3}, model=None)
    assert blk["corpus"] == "$HOME/c.jsonl"
    assert blk["paths"] == ["$STACK_WORKDIR/a", {"deep": "$HOME/d"}]
    assert blk["n"] == 3


def test_agentbench_resume_expands_a_placeholder_transcripts_dir(monkeypatch, tmp_path):
    """The resume path reads `runtime.transcripts_dir` back from the manifest; with the manifest
    now in placeholder form it must expand, or every resume would land under a literal
    `$STACK_WORKDIR` directory."""
    import json
    import bench.run_agentbench_os as R
    home, wd = _homes(monkeypatch, tmp_path)
    mp = tmp_path / "rows.manifest.json"
    mp.write_text(json.dumps({"runtime": {"transcripts_dir": "$STACK_WORKDIR/m54/transcripts/m/20261001T000000Z"}}))
    args = SimpleNamespace(transcripts_dir=None, model="m")
    assert R.run_transcripts_dir(args, mp, True) == wd / "m54" / "transcripts" / "m" / "20261001T000000Z"


# --------------------------------------------------------------------------- cold review 1 (B1, B3): boundaries
def test_portable_path_is_boundary_aware(monkeypatch, tmp_path):
    home, wd = _homes(monkeypatch, tmp_path)
    h = str(home)
    assert P.portable_path(f"cwd={h}") == "cwd=$HOME"                       # bare root after '='
    assert P.portable_path(f"a {h}/x b") == "a $HOME/x b"                    # embedded, space-delimited
    assert P.portable_path(f"/backup{h}/ws") == f"/backup{h}/ws"             # no leading boundary: untouched
    assert P.portable_path(f"{h}y/ws") == f"{h}y/ws"                         # longer sibling name: untouched
    assert P.portable_path(f"{h}/a:{h}/b") == "$HOME/a:$HOME/b"              # every bounded occurrence


def test_expand_portable_leaves_literal_placeholders_inside_paths(monkeypatch, tmp_path):
    home, wd = _homes(monkeypatch, tmp_path)
    assert P.expand_portable("$STACK_WORKDIR/runs/$HOME/session") == f"{wd}/runs/$HOME/session"
    assert P.expand_portable("$HOMEwork/x") == "$HOMEwork/x"
    assert P.expand_portable("x=$HOME") == f"x={home}"


# --------------------------------------------------------------------------- cold review 1 (Claude B1/B2/B3)
def test_portable_path_handles_url_double_slash_trailing_dot_and_pathlike(monkeypatch, tmp_path):
    home, wd = _homes(monkeypatch, tmp_path)
    h = str(home)
    assert P.portable_path(f"file://{h}/x") == "file://$HOME/x"
    assert P.portable_path(f"/{h}/a") == "/$HOME/a"
    assert P.portable_path(f"see {h}.") == "see $HOME."
    assert P.portable_path(Path(h) / "p") == "$HOME/p"
    blk = P._portable_deep({f"{h}/k": 1})
    assert blk == {"$HOME/k": 1}


def test_expand_portable_strict_refuses_an_unresolvable_placeholder(monkeypatch, tmp_path):
    import pytest
    _homes(monkeypatch, tmp_path)
    monkeypatch.delenv("STACK_WORKDIR")
    monkeypatch.setattr(paths, "stack_workdir", lambda required=True: None)
    assert P.expand_portable("$STACK_WORKDIR/x") == "$STACK_WORKDIR/x"          # lenient: unchanged
    with pytest.raises(P.UnresolvedPlaceholderError):
        P.expand_portable("$STACK_WORKDIR/x", strict=True)


def test_expand_portable_resolves_the_workdir_through_the_writer_resolver(monkeypatch, tmp_path):
    """The expanded value becomes a WRITE target (AgentBench transcripts), so it must go through
    `paths.stack_workdir` (the name the test conftest traps), not the display-only resolver."""
    home, wd = _homes(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(paths, "stack_workdir", lambda required=True: seen.append(1) or wd)
    assert P.expand_portable("$STACK_WORKDIR/x") == f"{wd}/x"
    assert seen == [1]
