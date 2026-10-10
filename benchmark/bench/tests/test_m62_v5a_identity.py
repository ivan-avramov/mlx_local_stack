import json
from pathlib import Path
import sys
import pytest
from bench import tg1_runner as runner, convergence
from bench.tests.test_tg1_integration import tg_fixture
from bench.tests.test_opencode_v2_probe import probe, MODEL
from m62 import build_replay_manifest as builder


@pytest.mark.parametrize('module', ['convergence.py', 'rowschema.py', 'answer_key.py', 'paths.py', 'model_params.py'])
def test_scoring_dependency_mutation_changes_identity(probe, monkeypatch, module):
    selection = {'fields': {'opencode_bench_config_sha256': 'fixture'}}
    before = runner.identity(probe, selection, 'universe', '2.0.20', probe.__file__)
    read = Path.read_bytes
    def mutated(path):
        data = read(path)
        if path == runner.REPO / 'benchmark/bench' / module:
            return data.replace(b'THINKING_BUDGET_CLAMP_RATIO = 0.8', b'THINKING_BUDGET_CLAMP_RATIO = 0.7') if module == 'convergence.py' else data + b'\n# mutation\n'
        return data
    monkeypatch.setattr(Path, 'read_bytes', mutated)
    after = runner.identity(probe, selection, 'universe', '2.0.20', probe.__file__)
    assert after['probe_code_sha256'] != before['probe_code_sha256']


def test_clamp_mutation_refuses_append(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f['run']() == 0
    before = f['out'].read_bytes()
    read = Path.read_bytes
    def mutate(path):
        data = read(path)
        return data.replace(b'THINKING_BUDGET_CLAMP_RATIO = 0.8', b'THINKING_BUDGET_CLAMP_RATIO = 0.7') if path == Path(convergence.__file__) else data
    monkeypatch.setattr(Path, 'read_bytes', mutate)
    with pytest.raises(SystemExit, match='resume provenance differs'):
        f['run']('two')
    assert f['out'].read_bytes() == before


@pytest.mark.parametrize('flag', ['--tick', '--first-write', '--hard-ceiling', '--stall-t', '--loop-rep', '--poll'])
@pytest.mark.parametrize('equals', [False, True])
def test_tg1_refuses_abbreviated_legacy_flags(probe, monkeypatch, flag, equals):
    monkeypatch.setattr(runner, '_main', lambda *a: pytest.fail('accepted legacy option'))
    monkeypatch.setattr(sys, 'argv', ['probe','--model',MODEL,'--items','one','--seed-base','1',
        '--scaffold','opencode-v2-web-tg1', *([flag+'=1'] if equals else [flag,'1'])])
    with pytest.raises(SystemExit):
        probe.main()


def test_replay_manifest_refuses_overwrite(tmp_path, monkeypatch, capsys):
    out = tmp_path / 'benchmark/m62/replay_manifest.json'; out.parent.mkdir(parents=True)
    out.write_bytes(b'frozen\n')
    monkeypatch.setattr(builder, 'REPO', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['builder'])
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    with pytest.raises(SystemExit):
        builder.main()
    assert 'exists; pass --refreeze' in capsys.readouterr().err
    assert out.read_bytes() == b'frozen\n'


def test_replay_manifest_refreeze_atomic(tmp_path, monkeypatch):
    out = tmp_path / 'benchmark/m62/replay_manifest.json'; out.parent.mkdir(parents=True)
    out.write_bytes(b'frozen\n')
    monkeypatch.setattr(builder, 'REPO', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['builder', '--refreeze'])
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    calls = []
    def interrupted_replace(src, dst):
        calls.append((src, dst))
        assert out.read_bytes() == b'frozen\n'
        assert json.loads(Path(src).read_text())['entries'] == []
        raise OSError('interrupted replacement')
    monkeypatch.setattr(runner.pg.os, 'replace', interrupted_replace)
    with pytest.raises(OSError, match='interrupted replacement'):
        builder.main()
    assert calls and out.read_bytes() == b'frozen\n'
    assert list(out.parent.iterdir()) == [out]


def test_rows_expose_converged_for_watchers(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f['run']() == 0
    row = json.loads(f['out'].read_text())
    assert row['converged'] is (row['nonconv_kind'] is None)
