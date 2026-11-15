"""S24-P17 follow-up (lead call, C334 light path; fail-closed, off the data path): a PII refusal names the file, line and pattern
but never echoes the matched text — Wave 1's refusal quoted it into `sequence.log`, which the sequencer then publishes, so every
later harvest refused the log (stage-3a Wave 1, 2026-11-15). Wave 2's refusal already reports the pattern name only. Class (a)."""
from __future__ import annotations

from bench import p426_harvest as h

MATCH = "/home/" + "zed" + "/"                       # split so this file's own text is not a literal match


def test_publish_refusal_does_not_echo_the_match(tmp_path):
    scrub = h.Scrub(workdir=tmp_path / "wd", repo=tmp_path / "repo", home=tmp_path / "home", user="b2opuser", hosts=("b2host",))
    _, _, _, problems = h._publish(f"cd {MATCH}project\n".encode(), "docs/notes.txt", scrub)
    assert problems, "the refusal itself must stand"
    assert all(MATCH not in p for p in problems), problems
    assert any("docs/notes.txt:1" in p and "/home/" in p for p in problems), problems      # file, line and the pattern's name


def _scrub(tmp_path):
    return h.Scrub(workdir=tmp_path / "wd", repo=tmp_path / "repo", home=tmp_path / "home", user="b2opuser", hosts=("b2host",))


def test_binary_refusal_does_not_echo_the_markers(tmp_path):                       # cold read (GLM F1, F2)
    scrub = _scrub(tmp_path)
    _, _, _, problems = h._publish(b"\x00\xff b2opuser \xfe b2host \x00", "evidence/blob.bin", scrub)
    assert problems, "the refusal itself must stand"
    assert all("b2opuser" not in p and "b2host" not in p for p in problems), problems
    assert any("evidence/blob.bin" in p for p in problems), problems


def test_no_pattern_echoes_its_match(tmp_path):                                    # cold read (GLM F3)
    samples = ["/Users/" + "zed" + "/x", MATCH + "x", "x-home-" + "zed" + "-y", "hf_" + "A" * 24, "sk-" + "B" * 24,
               "ghp_" + "C" * 24, "AKIA" + "D" * 16, "zedbox" + ".local"]
    scrub = _scrub(tmp_path)
    for text in samples:
        _, _, _, problems = h._publish(f"see {text} here\n".encode(), "docs/notes.txt", scrub)
        assert problems, text
        assert all(text not in p for p in problems), (text, problems)
