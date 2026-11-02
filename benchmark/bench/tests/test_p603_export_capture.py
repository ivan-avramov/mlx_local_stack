"""P603: the opencode session export is captured to a FILE (not a pipe), with one re-export on an unparsable capture.

Live trigger (Wave 2b leg 4 `tg1-p426-on-s1.a1`, `go/bottle-song`): the piped capture of `opencode session export … --standalone`
ended at exactly 65,536 bytes mid-string, rc 0, empty stderr → `unparsable session export` → a systemic stop. 1 of 44 exports ≥ 64 KiB."""
import json
import os
import stat
import subprocess

import pytest

from bench import arm_opencode as ao
from bench import token_turn_gate as tg

WHOLE = json.dumps({"info": {"id": "ses_x"}, "messages": [{"id": "m", "type": "assistant", "pad": "x" * 70000}]})
CUT = WHOLE[:65536]


class Stream:
    session_id = "ses_x"


class Guard:
    """A fake `ProcessGuard.run_grader` that writes the scripted captures to the stdout it is given."""

    def __init__(self, captures, rc=0):
        self.captures, self.rc, self.calls = list(captures), rc, []

    def run_grader(self, cmd, *, capture_output=False, text=False, timeout=None, stdout=None, stderr=None, **kw):
        body = self.captures.pop(0)
        self.calls.append(dict(capture_output=capture_output, stdout_is_file=hasattr(stdout, "fileno")
                               and stat.S_ISREG(os.fstat(stdout.fileno()).st_mode)))
        if hasattr(stdout, "write"):
            stdout.write(body)
            return subprocess.CompletedProcess(cmd, self.rc, None, "")
        return subprocess.CompletedProcess(cmd, self.rc, body, "")


def run(guard, tmp_path):
    path = tmp_path / "go__x.json"
    return ao.OpencodeArm.transcript(None, guard, {}, tmp_path, Stream(), "opencode", raw_sink=None, capture_path=path), path


def test_the_export_goes_to_a_regular_file_not_a_pipe_P603(tmp_path):
    g = Guard([WHOLE])
    t, path = run(g, tmp_path)
    assert g.calls[0]["stdout_is_file"] and not g.calls[0]["capture_output"]
    assert t.doc["info"]["id"] == "ses_x" and t.raw == WHOLE and path.read_text() == WHOLE


def test_a_cut_capture_is_exported_once_more_P603(tmp_path, capsys):
    g = Guard([CUT, WHOLE])
    t, path = run(g, tmp_path)
    assert len(g.calls) == 2 and t.raw == WHOLE and path.read_text() == WHOLE
    assert "65536" in capsys.readouterr().err                      # the cut capture is logged (bytes, sha256)


def test_two_unparsable_captures_still_abort_P603(tmp_path):
    with pytest.raises(tg.TransportAbort, match="unparsable session export"):
        run(Guard([CUT, CUT]), tmp_path)


def test_a_failed_export_still_aborts_without_a_retry_P603(tmp_path):
    g = Guard(["", ""], rc=1)
    with pytest.raises(tg.TransportAbort, match="session export failed"):
        run(g, tmp_path)
    assert len(g.calls) == 1


def test_without_a_capture_path_the_pipe_path_is_unchanged_P603(tmp_path):
    g = Guard([WHOLE])
    t = ao.OpencodeArm.transcript(None, g, {}, tmp_path, Stream(), "opencode")
    assert g.calls[0]["capture_output"] and t.raw == WHOLE
