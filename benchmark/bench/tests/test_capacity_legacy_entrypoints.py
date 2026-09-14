"""Historical entry points must not overwrite evidence or launder failed runs."""
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_rescore_is_retired_without_rewriting_files(tmp_path):
    result = tmp_path / 'capacity_retrieval.json'
    result.write_text('{"fits": false, "gate_gb": 46}')
    proc = subprocess.run(['python3', str(ROOT / 'rescore.py')], cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert 'Retired' in proc.stderr
    assert result.read_text() == '{"fits": false, "gate_gb": 46}'


def test_sequence_aborts_after_failed_model(tmp_path):
    import os
    for name, body in [('uv', 'exit 7'), ('curl', 'exit 0')]:
        p = tmp_path / name
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + ':' + os.environ['PATH']}
    proc = subprocess.run(['bash', str(ROOT / 'run_capacity_seq.sh'), 'first', 'second'],
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 7
    assert 'START second' not in proc.stdout
    assert 'ALL_DONE' not in proc.stdout
