"""`run.py <subcommand> --help` must not crash.

WHY THIS EXISTS. Measured 2026-08-14: `run.py generate --help` raised
``ValueError: unsupported format character ...`` from argparse's ``_expand_help``, which does
``help_string % params``. The ``--samples`` help text contained a BARE ``%`` ("gives -55%."), so
every attempt to read the generate options died with a traceback instead of printing help.

This is not cosmetic. `generate` is the entry point whose flags decide whether a run measures the
sampling we ship (`--sampling-profile`), whether a slow model gets a survivable timeout
(`--probe-timeout`), and whether existing rows are DELETED (`--clean-stale`). An operator who
cannot read that help is one who guesses, and two of those flags destroy or invalidate data.

Every literal ``%`` in an argparse help string must be escaped as ``%%``.
"""
import subprocess
import sys

from bench import paths

SUBCOMMANDS = ["list", "generate", "grade", "status", "compare"]


def _help(*argv):
    return subprocess.run(
        [sys.executable, str(paths.BENCHMARK_DIR / "run.py"), *argv, "--help"],
        capture_output=True, text=True,
        cwd=str(paths.repo_root()),
        env={"PYTHONPATH": str(paths.BENCHMARK_DIR), "PATH": "/usr/bin:/bin"},
    )


def test_every_subcommand_help_exits_clean():
    """A crash here is invisible until someone reads the help — and it hid for months."""
    for cmd in SUBCOMMANDS:
        r = _help(cmd)
        assert r.returncode == 0, (
            f"`run.py {cmd} --help` exited {r.returncode}. argparse expands help strings with "
            f"`% params`, so a BARE '%' in any help text raises. stderr:\n{r.stderr[-800:]}")
        assert "Traceback" not in r.stderr, f"`run.py {cmd} --help` traceback:\n{r.stderr[-800:]}"


def test_generate_help_actually_lists_the_dangerous_flags():
    """Guards against 'fixed' by deleting the help text rather than escaping the percent."""
    out = _help("generate").stdout
    for flag in ("--sampling-profile", "--clean-stale", "--probe-timeout", "--samples"):
        assert flag in out, f"{flag} missing from `generate --help`"


def test_no_bare_percent_in_any_help_string():
    """Static guard: the next person to write '5%' in a help string gets a failing test, not a
    traceback at the CLI. Checks the source for a '%' inside a help= string that is not '%%'."""
    src = (paths.BENCHMARK_DIR / "run.py").read_text()
    offenders = []
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        # Only continuation/help lines carry the risk; skip f-string print formatting.
        if stripped.startswith("print(") or stripped.startswith("hdr") or "f\"" in stripped:
            continue
        if not (stripped.startswith('help=') or stripped.startswith('"')):
            continue
        cleaned = stripped.replace("%%", "")
        if "%" in cleaned:
            offenders.append(f"{lineno}: {stripped[:90]}")
    assert not offenders, (
        "bare '%' in an argparse help string — escape it as '%%' or argparse's _expand_help "
        "raises at --help time:\n" + "\n".join(offenders))


def test_generate_help_documents_reasoning_effort():
    """M24: the effort arm must be launchable ONLY through a provenance-tracked flag."""
    r = _help("generate")
    assert "--reasoning-effort" in r.stdout
