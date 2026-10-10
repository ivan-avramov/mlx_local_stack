"""Tiny acceptance test for the M41 chain runner's --dry-run plan.

Runs `run.py --dry-run` via subprocess (real interpreter, real process -- not an import),
and asserts the three exact commands, the env facts, and the per-ladder bounds from
SPEC.md all appear in its combined stdout/stderr. Does NOT require a running server and
never starts a router or does GPU work under --dry-run. R4 (SPEC_FIX1): --dry-run DOES
now shell out to `<python> -m <module> --help` for the flag precheck (no server needed for
--help) -- this is the one bench-module subprocess --dry-run is allowed to run.

Run directly:
    "$STACK_REPO/.venv-bench/bin/python" test_run_dry.py
or via pytest:
    "$STACK_REPO/.venv-bench/bin/python" -m pytest test_run_dry.py -q
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = os.environ.get('STACK_REPO', '') and f"{os.environ['STACK_REPO']}/.venv-bench/bin/python"
PICK = 'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'


def _run_dry():
    assert 'STACK_REPO' in os.environ, 'STACK_REPO not set -- source config.sh first'
    assert 'STACK_WORKDIR' in os.environ, 'STACK_WORKDIR not set -- source config.sh first'
    result = subprocess.run([PY, str(HERE / 'run.py'), '--dry-run'], cwd=str(HERE),
                            env=os.environ.copy(), capture_output=True, text=True, timeout=120)
    return result


def test_dry_run_exits_zero_and_launches_nothing():
    result = _run_dry()
    combined = result.stdout + result.stderr
    assert result.returncode == 0, f'expected exit 0, got {result.returncode}:\n{combined}'
    # --dry-run must never mention an actual Popen/launch of the bench modules
    assert 'not launched (--dry-run)' in combined


def test_dry_run_shows_three_exact_commands():
    combined = _run_dry().stdout
    capacity_cmd = (
        f'-m bench.run_capacity --model {PICK} '
        '--grid 131072,196608,262144 --gate-gb 46 '
        '--sampling-profile deployed --out-tag m41on --request-timeout 7200'
    )
    retrieval_cmd = (
        f'-m bench.run_retrieval --model {PICK} '
        '--grid 8000,32000,64000,96000,128000 --samples 5 --threshold 0.85 '
        '--sampling-profile deployed --out-tag m41on --request-timeout 9600'
    )
    reasoning_cmd = (
        f'-m bench.run_reasoning --model {PICK} '
        '--grid 8000,16000,24000,32000,48000,64000,96000,128000,156000 --samples 5 '
        '--deep-from 96000 --deep-samples 3 --chain-len 4 --threshold 0.85 '
        '--sampling-profile deployed --out-tag m41on --request-timeout 9600'
    )
    for cmd in (capacity_cmd, retrieval_cmd, reasoning_cmd):
        assert cmd in combined, f'missing exact command:\n{cmd}\n--- full output ---\n{combined}'


def test_dry_run_shows_env_facts():
    combined = _run_dry().stdout
    overlay_abs = str(HERE / f'on_{PICK}.yaml')
    assert f'MLX_SERVE_CONFIG={overlay_abs}' in combined
    assert 'APC_ENABLED absent' in combined
    assert 'MLX_VLM_CACHE_SESSION_MAX=2' in combined


def test_dry_run_shows_bounds_and_worker_cmdline_expectation():
    combined = _run_dry().stdout
    assert 'bound_h=2' in combined      # capacity
    assert 'bound_h=5' in combined      # retrieval
    assert 'bound_h=10' in combined     # reasoning
    assert combined.count('expect --draft-kind mtp present') == 3


def test_dry_run_flag_precheck_runs_for_all_three_modules():
    """R4 (SPEC_FIX1): check_cli_flags runs `<python> -m <module> --help` under --dry-run too
    (no server needed) and logs a PRECHECK OK line per module when all required flags are
    present. If a required flag hasn't landed in the target module yet, the run FATALs naming
    it instead -- surface that clearly rather than a bare assertion failure."""
    result = _run_dry()
    combined = result.stdout + result.stderr
    expected = (
        ('bench.run_capacity', ['--sampling-profile', '--out-tag', '--request-timeout']),
        ('bench.run_retrieval', ['--sampling-profile', '--out-tag', '--request-timeout']),
        ('bench.run_reasoning', ['--sampling-profile', '--out-tag', '--request-timeout',
                                  '--deep-from', '--deep-samples']),
    )
    for module, flags in expected:
        ok_line = f'PRECHECK {module} --help OK: {flags} all present'
        if ok_line not in combined:
            assert f'{module} --help is missing required flag(s)' in combined, (
                f'neither the PRECHECK OK line nor a FATAL missing-flag line found for '
                f'{module}; full output:\n{combined}')
            raise AssertionError(
                f'{module} --help precheck FATALed (flag not landed yet, see TOOLING.md) -- '
                f'not a runner bug; re-run once the tooling fix lands. Full output:\n{combined}')


def test_dry_run_marker_is_the_dry_run_marker_never_the_live_one():
    """R5 (SPEC_FIX1): --dry-run ends with '=== M41 DRY-RUN DONE ===', never '=== M41 DONE ==='."""
    result = _run_dry()
    combined = result.stdout + result.stderr
    assert '=== M41 DRY-RUN DONE ===' in combined
    assert '=== M41 DONE ===' not in combined


def test_redact_paths_replaces_workdir_then_repo():
    """R6 (SPEC_FIX1): write_provenance's path-redaction helper replaces $STACK_WORKDIR then
    $STACK_REPO (in that order) with the placeholder strings, in every string field, recursively.
    Exercises run.py's `_redact_paths` directly with a fake cmdline string -- no launch."""
    sys.path.insert(0, str(HERE))
    import importlib
    run_mod = importlib.import_module('run')
    wd = os.environ['STACK_WORKDIR']
    repo = os.environ['STACK_REPO']
    fake_cmdline = (f'{repo}/.venv-bench/bin/python -m mlx_vlm.server --config '
                    f'{wd}/queue/m41_ladders/on_{PICK}.yaml --kv-cache-dir {repo}/kv')
    prov = {
        'worker_cmdline': fake_cmdline,
        'overlay': f'{wd}/queue/m41_ladders/on_{PICK}.yaml',
        'nested': {'note': f'see {repo}/benchmark/results'},
        'list_field': [f'{repo}/a', f'{wd}/b'],
        'router_pid': 12345,  # non-string fields must pass through unchanged
    }
    redacted = run_mod._redact_paths(prov)
    dumped = json.dumps(redacted)
    assert repo not in dumped, f'repo path leaked into redacted provenance:\n{dumped}'
    assert wd not in dumped, f'workdir path leaked into redacted provenance:\n{dumped}'
    assert '$STACK_REPO' in redacted['worker_cmdline']
    assert '$STACK_WORKDIR' in redacted['overlay']
    assert '$STACK_REPO' in redacted['nested']['note']
    assert redacted['list_field'] == ['$STACK_REPO/a', '$STACK_WORKDIR/b']
    assert redacted['router_pid'] == 12345


if __name__ == '__main__':
    test_dry_run_exits_zero_and_launches_nothing()
    test_dry_run_shows_three_exact_commands()
    test_dry_run_shows_env_facts()
    test_dry_run_shows_bounds_and_worker_cmdline_expectation()
    test_dry_run_flag_precheck_runs_for_all_three_modules()
    test_dry_run_marker_is_the_dry_run_marker_never_the_live_one()
    test_redact_paths_replaces_workdir_then_repo()
    print('OK: all M41 --dry-run assertions passed')
