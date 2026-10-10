import json
import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from configgen.source import load_source
from configgen.transforms import sampling_openai, sampling_extra
import pytest
from configgen.emitters.opencode import emit_opencode, emit_opencode_bench

def test_opencode_structure(sample_source):
    d = json.loads(emit_opencode(sample_source))
    ml = d["providers"]["mlx-local"]["models"]
    assert set(ml) == {"Qwen-A", "Gemma-B"}                 # task model NOT here
    assert d["providers"]["mlx-task"]["models"]["mlx-community/Task-C"]
    assert d["model"] == "mlx-local/Qwen-A"                 # from agent_defaults
    assert d["agents"]["title"]["model"] == "mlx-task/mlx-community/Task-C"
    assert ml["Qwen-A"]["body"]["temperature"] == 0.4
    assert ml["Qwen-A"]["body"]["presence_penalty"] == 0.0   # qwen extra
    assert ml["Gemma-B"]["body"]["repetition_penalty"] == 1.08  # gemma extra (fixture family; allow-shorthand)
    assert ml["Qwen-A"]["limit"]["context"] == 262144
    assert ml["Qwen-A"]["limit"]["input"] == 262144 - 102400


def test_nemotron_family_renders_as_main_with_vendor_sparse_extras(nemotron_source_tainted):
    # C64/F5: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit, role=main, family=nemotron. Taint-based:  # allow-shorthand
    # the fixture injects top_k/repetition_penalty, so the absence asserts below have teeth.
    d = json.loads(emit_opencode(nemotron_source_tainted))
    ml = d["providers"]["mlx-local"]["models"]
    m = ml["NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]
    assert m["body"]["temperature"] == 0.5
    assert m["body"]["presence_penalty"] == 0.0
    assert m["body"]["thinking_budget"] == 81920
    assert m["body"]["enable_thinking"] is True
    assert "top_k" not in m["body"] and "min_p" not in m["body"]
    assert "repetition_penalty" not in m["body"]


def test_no_unrecognized_top_level_keys(sample_source):
    """Emit only native v2 keys, even though 2.0.20 strips unknown keys."""
    d = json.loads(emit_opencode(sample_source))
    allowed = {"$schema", "providers", "model", "agents", "plugins", "update", "share", "compaction"}
    assert set(d) <= allowed, f"unrecognized top-level key(s): {sorted(set(d) - allowed)}"
    assert "_generated" not in d


def test_generated_marker_is_absent_from_every_nesting_level(sample_source):
    """Generated metadata belongs in the README, never inside the client document."""
    def walk(node, path="$"):
        if isinstance(node, dict):
            assert "_generated" not in node, f"_generated found at {path}"
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(json.loads(emit_opencode(sample_source)))

@pytest.mark.parametrize("emit", [emit_opencode, emit_opencode_bench])
def test_text_only_model_does_not_advertise_attachments(emit, nemotron_source, sample_source):
    provider = "providers" if emit is emit_opencode else "provider"
    text_only = json.loads(emit(nemotron_source))[provider]["mlx-local"]["models"]
    model = text_only["NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]
    if emit is emit_opencode:
        assert model["capabilities"]["input"] == ["text"]
    else:
        assert model["attachment"] is False
    vision = json.loads(emit(sample_source))[provider]["mlx-local"]["models"]
    for name in ("Qwen-A", "Gemma-B"):
        if emit is emit_opencode:
            assert "image" in vision[name]["capabilities"]["input"]
        else:
            assert vision[name]["attachment"] is True


@pytest.mark.parametrize("emit", [emit_opencode, emit_opencode_bench])
def test_resolved_provider_preserves_vision_input(emit, sample_source, nemotron_source):
    # OpenCode v1.18.30 provider/provider.ts resolves custom models' image
    # capability from modalities.input independently of attachment. Without
    # a catalogue entry, omitted image capability defaults to false and
    # provider/transform.ts replaces image parts with unsupported-input text.
    key = "capabilities" if emit is emit_opencode else "modalities"
    provider = "providers" if emit is emit_opencode else "provider"

    def accepts_image(model):
        return "image" in model[key]["input"]

    doc = json.loads(emit(sample_source))
    for model in doc[provider]["mlx-local"]["models"].values():
        assert accepts_image(model), "vision input would be replaced before delivery"
        assert model[key]["output"] == ["text"]
        assert "text" in model[key]["input"]
    task = doc[provider]["mlx-task"]["models"]["mlx-community/Task-C"]
    task_io = {k: task[key][k] for k in ("input", "output")} if emit is emit_opencode else task[key]
    assert task_io == {"input": ["text"], "output": ["text"]}
    text_only = json.loads(emit(nemotron_source))[provider]["mlx-local"]["models"]
    for model in text_only.values():
        assert not accepts_image(model)
        model_io = {k: model[key][k] for k in ("input", "output")} if emit is emit_opencode else model[key]
        assert model_io == {"input": ["text"], "output": ["text"]}

@pytest.mark.parametrize("emit", [emit_opencode, emit_opencode_bench])
@pytest.mark.parametrize("effective_output_limit", [32768, 102400])
def test_context_budget_reserves_output_once(emit, effective_output_limit, sample_source):
    # Installed OpenCode v1.18.30 session/overflow.ts: an explicit input limit
    # reserves the smaller of 20K and output; otherwise it subtracts output
    # from context. Supplying window-output as context reserves output twice.
    doc = json.loads(emit(sample_source))
    provider = "providers" if emit is emit_opencode else "provider"
    limit = doc[provider]["mlx-local"]["models"]["Qwen-A"]["limit"]
    reserved = min(20000, effective_output_limit)
    usable = (limit["input"] - reserved if limit.get("input")
              else limit["context"] - effective_output_limit)
    prompt_budget = 262144 - 102400
    assert usable == prompt_budget - reserved
    assert limit["context"] == 262144
    assert limit["output"] == 102400
    task = doc[provider]["mlx-task"]["models"]["mlx-community/Task-C"]["limit"]
    assert task["context"] == 30000
    assert task["input"] + task["output"] == task["context"]


def test_native_v2_policy_and_all_registry_sampling():
    root = Path(__file__).resolve().parents[2]
    source = load_source(str(root / "main_models.yaml"))
    doc = json.loads(emit_opencode(source))
    assert doc["update"] == "disable"
    assert doc["share"] == "disabled"
    assert doc["compaction"] == {"auto": True}
    assert doc["plugins"] == [
        "-opencode.provider.vllm", "-opencode.provider.ollama",
        "-opencode.provider.lmstudio", "-opencode.config.compatibility",
    ]  # superpowers uninstalled (operator, 2026-10-08): no external plugin in the daily client
    assert not {"provider", "plugin", "small_model", "permission", "permissions"} & doc.keys()
    for m in source.models:
        if m.role not in ("main", "task"):
            continue
        provider = doc["providers"]["mlx-local" if m.role == "main" else "mlx-task"]
        assert provider["package"] == "@opencode/ai/providers/openai-compatible"
        assert provider["settings"] == {
            "baseURL": f"http://localhost:{8000 if m.role == 'main' else m.port}/v1",
            "apiKey": "not-needed",
        }
        item = provider["models"][m.name]
        assert item["name"] == m.display_name
        assert item["compatibility"] == {"maxTokensField": "max_tokens"}
        assert item["capabilities"]["tools"] is (m.role == "main")
        expected = {**sampling_openai(m), **sampling_extra(m)}
        assert item.get("body", {}) == expected
        if m.role == "task" and not expected:
            assert "body" not in item
        assert not {"reasoning", "tool_call", "attachment", "modalities", "options"} & item.keys()


def _run_isolated_opencode(cmd, *, env, cwd, run_root, timeout):
    proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            raise
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    finally:
        processes = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True,
                                   text=True, check=True, timeout=10)
        survivors = [line for line in processes.stdout.splitlines() if str(run_root) in line]
        assert not survivors, f"surviving process under isolated tmp root: {survivors}"


def test_isolated_capture_kills_group_on_timeout(tmp_path, monkeypatch):
    proc = MagicMock()
    proc.pid = 12345
    proc.communicate.side_effect = [subprocess.TimeoutExpired(["opencode"], 1), ("", "")]
    popen = MagicMock(return_value=proc)
    killpg = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, ""))
    with pytest.raises(subprocess.TimeoutExpired):
        _run_isolated_opencode(["opencode"], env={}, cwd=tmp_path, run_root=tmp_path, timeout=1)
    assert popen.call_args.kwargs["start_new_session"] is True
    killpg.assert_called_once_with(12345, signal.SIGKILL)
    assert proc.communicate.call_count == 2


def test_isolated_capture_detects_surviving_process(tmp_path, monkeypatch):
    proc = MagicMock()
    proc.communicate.return_value = ("[]", "")
    proc.returncode = 0
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: proc)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
        a[0], 0, f"12345 opencode serve --cwd {tmp_path}/scratch\n"))
    with pytest.raises(AssertionError, match="surviving process"):
        _run_isolated_opencode(["opencode"], env={}, cwd=tmp_path, run_root=tmp_path, timeout=1)


def test_v2_real_config_load_and_unknown_key_control(tmp_path):
    """CPU-only schema proof: the standalone API must return the complete generated document."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmark"))
    from bench import paths
    workdir = paths.resolve_stack_workdir(required=False) or Path("/nonexistent")
    binary = Path(os.environ.get("OPENCODE_PROBE_BIN") or workdir / "opencode-2.0.20/bin/opencode")
    if not binary.is_file():
        pytest.skip("bench opencode 2.0.20 not installed (scripts/install_bench_opencode.sh); schema capture requires it")
    root = Path(__file__).resolve().parents[2]
    config = tmp_path / "cfg/opencode"
    scratch = tmp_path / "scratch"
    env = {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"), "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "TMPDIR": str(tmp_path / "tmp") + "/", "OPENCODE_CONFIG_DIR": str(config),
        "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_FILEWATCHER": "1",
        "PWD": str(scratch), "TERM": "dumb", "NO_COLOR": "1",
    }
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TMPDIR", "OPENCODE_CONFIG_DIR", "PWD"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(scratch)], env=env, cwd=scratch, check=True,
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    version = _run_isolated_opencode([str(binary), "--version"], env=env, cwd=scratch,
                                    run_root=tmp_path, timeout=30)
    if version.returncode != 0 or version.stdout.strip().removeprefix("opencode v") != "2.0.20":
        pytest.skip(f"brew schema capture requires 2.0.20; rc={version.returncode}, version={version.stdout.strip()!r}")
    expected = json.loads(emit_opencode(load_source(str(root / "main_models.yaml"))))
    path = config / "opencode.json"
    path.write_text(json.dumps(expected))

    def capture():
        return _run_isolated_opencode([str(binary), "api", "GET", "/api/config", "--standalone"],
                                     env=env, cwd=scratch, run_root=tmp_path, timeout=60)

    result = capture()
    assert result.returncode == 0, result.stderr
    docs = json.loads(result.stdout)
    loaded = [d for d in docs if d.get("path") == str(path)]
    assert len(loaded) == 1, result.stdout
    normalized = json.loads(json.dumps(expected))
    for holder in (normalized, normalized["agents"]["title"]):
        provider, model = holder["model"].split("/", 1)
        holder["model"] = {"providerID": provider, "model": model}
    assert loaded[0]["info"] == normalized  # v2 normalizes model references; bodies stay exact
    print(f"v2 /api/config: loaded {sum(len(p['models']) for p in expected['providers'].values())} models; body and plugins intact")
    path.write_text(json.dumps({**expected, "_unknown_m59_control": True}))
    bad = capture()
    assert bad.returncode == 0, bad.stderr
    unknown_docs = json.loads(bad.stdout)
    unknown_loaded = [d for d in unknown_docs if d.get("path") == str(path)]
    assert len(unknown_loaded) == 1
    assert unknown_loaded[0]["info"] == normalized
    print("unknown-key control: v2 strips the unknown key and retains the document (rc 0)")
    # Unlike v1, unknown keys do not invalidate v2. Use malformed JSON to prove
    # this test detects silent whole-document rejection on the actual binary.
    path.write_text("{ invalid JSON")
    bad = capture()
    assert bad.returncode == 0, bad.stderr
    bad_docs = json.loads(bad.stdout)
    assert not any(d.get("path") == str(path) for d in bad_docs), bad.stdout
    assert not any("mlx-local" in d.get("info", {}).get("providers", {}) for d in bad_docs)
    print("known-positive: malformed JSON silently drops the whole document (rc 0)")
