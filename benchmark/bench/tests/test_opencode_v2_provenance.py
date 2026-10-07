"""P151: fail-closed environment and raw-document destination proof."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from bench import provenance as P


@pytest.fixture(autouse=True)
def workdir(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))


def fixture_env(tmp_path):
    run = tmp_path / 'run'
    for d in ('home', 'cfg/opencode/plugins', 'data', 'state', 'cache', 'tmp'):
        (run / d).mkdir(parents=True, exist_ok=True)
    carrier = {'providers': {'mlx-local': {'settings': {'baseURL': 'http://127.0.0.1:12345/v1', 'apiKey': 'not-needed'}}}, 'plugins': ['-opencode.provider.vllm']}
    cfg = run / 'cfg/opencode/opencode.json'
    cfg.write_text(json.dumps(carrier))
    plugin = run / 'cfg/opencode/plugins/noretry.js'
    plugin.write_bytes((Path(P.__file__).resolve().parents[1] / 'opencode_plugins/noretry.js').read_bytes())
    overlay = {'providers': {'mlx-local': {'models': {'model': {'body': {'seed': 1}}}}}}
    env = {'HOME': str(run / 'home'), 'OPENCODE_CONFIG_DIR': str(run / 'cfg/opencode'),
           'OPENCODE_DISABLE_PROJECT_CONFIG': '1', 'OPENCODE_CONFIG_CONTENT': json.dumps(overlay),
           'PWD': str(tmp_path)}
    env.update({f'XDG_{key}_HOME': str(run / d) for key, d in [('CONFIG', 'cfg'), ('DATA', 'data'), ('STATE', 'state'), ('CACHE', 'cache')]})
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    return run, env, sha(cfg), sha(plugin), overlay


def test_env_happy(tmp_path):
    assert hasattr(P, 'opencode_v2_env_check'), 'M50 v2 environment checker is missing'
    P.opencode_v2_env_check(*fixture_env_args(tmp_path))


def fixture_env_args(tmp_path):
    run, env, carrier, plugin, overlay = fixture_env(tmp_path)
    return env, run, carrier, plugin, overlay


@pytest.mark.parametrize('mutation', ['config', 'dir', 'extra_file', 'extra_dir', 'extra_plugin', 'missing_plugin', 'carrier_sha', 'plugin_sha', 'overlay_json', 'overlay_extra', 'overlay_seed', 'overlay_bool', 'project', 'home', 'xdg_config', 'xdg_data', 'xdg_state', 'xdg_cache', 'xdg_extra', 'symlink'])
def test_env_refuses_each_clause(tmp_path, mutation):
    env, run, carrier, plugin, overlay = fixture_env_args(tmp_path)
    cfg = run / 'cfg/opencode'
    if mutation == 'config': env['OPENCODE_CONFIG'] = ''
    elif mutation == 'dir': env['OPENCODE_CONFIG_DIR'] = str(tmp_path)
    elif mutation == 'extra_file': (cfg / 'opencode.jsonc').write_text('{}')
    elif mutation == 'extra_dir': (cfg / 'agents').mkdir()
    elif mutation == 'extra_plugin': (cfg / 'plugins/other.js').write_text('')
    elif mutation == 'missing_plugin': (cfg / 'plugins/noretry.js').unlink()
    elif mutation == 'carrier_sha': carrier = 'different'
    elif mutation == 'plugin_sha': plugin = 'different'
    elif mutation == 'overlay_json': env['OPENCODE_CONFIG_CONTENT'] = '{'
    elif mutation.startswith('overlay_'):
        value = copy.deepcopy(overlay)
        if mutation == 'overlay_extra': value['plugins'] = []
        else: value['providers']['mlx-local']['models']['model']['body']['seed'] = True if mutation == 'overlay_bool' else 13
        env['OPENCODE_CONFIG_CONTENT'] = json.dumps(value)
    elif mutation == 'project': env.pop('OPENCODE_DISABLE_PROJECT_CONFIG')
    elif mutation == 'home': env['HOME'] = str(tmp_path)
    elif mutation.startswith('xdg_'): env['XDG_' + mutation[4:].upper() + '_HOME'] = str(tmp_path)
    elif mutation == 'symlink':
        p = cfg / 'plugins/noretry.js'; raw = p.read_bytes(); p.unlink()
        outside = tmp_path / 'outside.js'; outside.write_bytes(raw); p.symlink_to(outside)
    with pytest.raises(P.ServedConfigError, match='^M50 tripwire:'):
        P.opencode_v2_env_check(env, run, carrier, plugin, overlay)


def documents(run, overlay):
    cfg = run / 'cfg/opencode/opencode.json'
    return [{'type': 'document', 'path': str(cfg), 'info': json.loads(cfg.read_text())},
            {'type': 'directory', 'path': str(cfg.parent)},
            {'type': 'document', 'info': overlay}]


@pytest.mark.parametrize('mutation', [None, 'extra', 'duplicate', 'overlay', 'settings', 'base', 'plugins', 'empty', 'unknown', 'rc', 'json', 'plugin_log', 'plugin_path', 'plugin_prefix', 'plugin_missing', 'plugin_sha', 'content_settings', 'missing_key', 'pwd'])
def test_destination_documents(tmp_path, monkeypatch, mutation):
    run, env, _, _, overlay = fixture_env(tmp_path)
    docs = documents(run, overlay)
    if mutation == 'extra': docs.append({'type': 'document', 'path': str(tmp_path / 'opencode.json'), 'info': {}})
    elif mutation == 'duplicate': docs.append(copy.deepcopy(docs[0]))
    elif mutation == 'overlay': docs[2]['info'] = {}
    elif mutation == 'settings': docs[0]['info']['providers']['mlx-local']['settings']['extra'] = 'unexpected'
    elif mutation == 'missing_key': del docs[0]['info']['providers']['mlx-local']['settings']['apiKey']
    elif mutation == 'content_settings':
        docs[2]['info']['providers']['mlx-local']['settings'] = {}
    elif mutation == 'plugin_missing': (run / 'cfg/opencode/plugins/noretry.js').unlink()
    elif mutation == 'plugin_sha': (run / 'cfg/opencode/plugins/noretry.js').write_text('changed')
    elif mutation == 'base': docs[0]['info']['providers']['mlx-local']['settings']['baseURL'] = 'http://127.0.0.1:1/v1'
    elif mutation == 'plugins': docs[0]['info']['plugins'] = []
    elif mutation == 'empty': docs = []
    elif mutation == 'unknown': docs.append({'type': 'directory', 'path': str(tmp_path)})
    elif mutation == 'pwd': env['PWD'] = str(run)
    env['OPENCODE_PRINT_LOGS'] = '1'
    plugin_path = run / 'cfg/opencode/plugins/noretry.js'
    if mutation == 'plugin_path': plugin_path = tmp_path / 'other/noretry.js'
    if mutation == 'plugin_prefix': plugin_path = Path(str(plugin_path) + '.other')
    calls = []
    def fake(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 1 if mutation == 'rc' else 0,
            stdout='bad' if mutation == 'json' else json.dumps(docs),
            stderr='' if mutation == 'plugin_log' else f'msg="loading plugin" id={plugin_path.resolve()} entrypoint={plugin_path.resolve().as_uri()} role=server\n')
    monkeypatch.setattr(P.subprocess, 'run', fake)
    if mutation:
        with pytest.raises(P.ServedConfigError, match='^M50 tripwire:'):
            P.opencode_v2_destination(tmp_path, env, 'model', run, str(tmp_path / 'opencode'), overlay)
    else:
        assert P.opencode_v2_destination(tmp_path, env, 'model', run, str(tmp_path / 'opencode'), overlay) == 'http://127.0.0.1:12345/v1'
        cmd, kw = calls[0]
        assert cmd == [str(tmp_path / 'opencode'), 'api', 'GET', '/api/config', '--standalone']
        assert kw['cwd'] == str(tmp_path) and kw['env']['PWD'] == str(tmp_path)
        assert kw['timeout'] == 120 and kw['stdin'] == subprocess.DEVNULL
