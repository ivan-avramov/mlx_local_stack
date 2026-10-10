import json
import hashlib
import subprocess
from pathlib import Path
import pytest
from bench import provenance as P
from bench.tests.test_opencode_v2_provenance import fixture_env, documents


def test_destination_can_use_owned_process_runner(tmp_path):
    run, env, _, _, overlay = fixture_env(tmp_path)
    calls = []

    def owned(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, json.dumps(documents(run, overlay)), ""
        )

    P.opencode_v2_destination(
        tmp_path, env, "m", run, "opencode", overlay, runner=owned
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "scaffold", ["opencode-v2", "opencode-v2-web", "opencode-v2-web-tg1"]
)
def test_plugin_allowlist_scaffold_and_sha(tmp_path, scaffold):
    run, env, carrier, plugin, overlay = fixture_env(tmp_path)
    path = run / "cfg/opencode/plugins/toolbounds.js"
    path.write_text("test plugin")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    kwargs = dict(scaffold=scaffold, toolbounds_sha=sha)
    if scaffold.endswith("tg1"):
        P.opencode_v2_env_check(env, run, carrier, plugin, overlay, **kwargs)
        path.write_text("changed")
    with pytest.raises(P.ServedConfigError):
        P.opencode_v2_env_check(env, run, carrier, plugin, overlay, **kwargs)


@pytest.mark.parametrize(
    "mutation", [None, "missing_log", "title", "compaction", "execute", "subagent"]
)
def test_tg1_destination_both_plugins_and_policy(tmp_path, monkeypatch, mutation):
    run, env, _, _, overlay = fixture_env(tmp_path)
    cfg = run / "cfg/opencode/opencode.json"
    doc = json.loads(cfg.read_text())
    doc.update(
        compaction={"auto": False},
        agents={"title": {"disabled": True}},
        permissions=[
            dict(action=a, resource="*", effect="deny") for a in ("execute", "subagent")
        ],
    )
    if mutation == "title":
        doc["agents"]["title"]["disabled"] = False
    if mutation == "compaction":
        doc["compaction"]["auto"] = True
    if mutation in ("execute", "subagent"):
        doc["permissions"] = [p for p in doc["permissions"] if p["action"] != mutation]
    cfg.write_text(json.dumps(doc))
    source = Path(P.__file__).resolve().parents[1] / "opencode_plugins/toolbounds.js"
    (cfg.parent / "plugins/toolbounds.js").write_bytes(source.read_bytes())
    names = ["noretry.js"] + ([] if mutation == "missing_log" else ["toolbounds.js"])
    stderr = "\n".join(
        f'msg="loading plugin" role=server id={cfg.parent / "plugins" / n}'
        for n in names
    )
    monkeypatch.setattr(
        P.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a, 0, json.dumps(documents(run, overlay)), stderr
        ),
    )
    if mutation:
        with pytest.raises(P.ServedConfigError):
            P.opencode_v2_destination(
                tmp_path,
                env,
                "m",
                run,
                "opencode",
                overlay,
                scaffold="opencode-v2-web-tg1",
            )
    else:
        P.opencode_v2_destination(
            tmp_path, env, "m", run, "opencode", overlay, scaffold="opencode-v2-web-tg1"
        )


def test_tg1_activation_discovery_awaits_plugins_and_preserves_noretry(tmp_path):
    run, env, _, _, overlay = fixture_env(tmp_path)
    cfg = run / 'cfg/opencode/opencode.json'
    doc = json.loads(cfg.read_text())
    doc.update(compaction={'auto':False}, agents={'title':{'disabled':True}},
               permissions=[dict(action=a, resource='*', effect='deny') for a in ('execute','subagent')])
    cfg.write_text(json.dumps(doc))
    for name in ('noretry.js','toolbounds.js'):
        source = Path(P.__file__).resolve().parents[1] / 'opencode_plugins' / name
        (cfg.parent / 'plugins' / name).write_bytes(source.read_bytes())
    calls = []
    def owned(cmd, **kw):
        endpoint = cmd[3]
        calls.append(endpoint)
        names = ('noretry.js',) if endpoint == '/api/config' else ('noretry.js','toolbounds.js')
        stderr = '\n'.join(f'msg="loading plugin" role=server id={cfg.parent / "plugins" / n}' for n in names)
        return subprocess.CompletedProcess(cmd, 0, json.dumps(documents(run, overlay) if endpoint == '/api/config' else {'data': []}), stderr)
    P.opencode_v2_destination(tmp_path, {**env,'OPENCODE_PRINT_LOGS':'1'}, 'm', run, 'opencode', overlay,
                              scaffold='opencode-v2-web-tg1', runner=owned)
    assert calls == ['/api/config','/api/integration']
