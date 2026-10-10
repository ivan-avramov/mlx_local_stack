import json
from ..source import Source
from ..transforms import sampling_openai, sampling_extra, input_limit

def emit_opencode_bench(source: Source) -> str:
    """opencode config for BENCHMARKING: shipped models AND `role: candidate` models.

    Same gap as the aider bench carrier. The client config filters on role == "main", so a candidate
    under test is absent — and an absent model cannot be selected with `opencode run --model`, let
    alone at its tuned sampling. P1a established that opencode DOES forward both standard params and
    non-standard extras (`thinking_budget`, `enable_thinking`), so the options block below is the
    carrier that makes a candidate's agentic row measured at `deployed` rather than at opencode's
    defaults. Deliberately NOT in TARGETS — see configgen/tests/test_opencode_bench.py.
    """
    return _emit_v1(source, roles=("main", "candidate"))


def emit_opencode(source: Source) -> str:
    return _emit(source)


def _emit_v1(source: Source, *, roles: tuple[str, ...]) -> str:
    main = [m for m in source.models if m.role in roles]
    task = next((m for m in source.models if m.role == "task"), None)
    local_models = {}
    for m in main:
        local_models[m.name] = {
            "name": m.display_name, "tool_call": True, "reasoning": True,
            "attachment": "vision" in m.capabilities,
            "modalities": {"input": ["text", "image"] if "vision" in m.capabilities else ["text"],
                           "output": ["text"]},
            "limit": {"context": m.context, "input": input_limit(m), "output": m.output},
            "options": {**sampling_openai(m), **sampling_extra(m)},
        }
    # NO `_generated` marker here, deliberately. opencode validates its config strictly and rejects
    # the WHOLE FILE on an unknown top-level key: on 1.18.15 the cosmetic provenance note produced
    # `Unrecognized key: _generated`, the config never loaded, and zero requests reached :8000 —
    # which read exactly like opencode#5674 ("custom endpoints unusable") and nearly got the
    # campaign's declared primary harness written off over a defect in our own emitter. JSON has no
    # comments and opencode offers no sanctioned slot for one, so the "generated, do not hand-edit"
    # note lives in opencode_config/README.md instead. Pinned by
    # configgen/tests/test_opencode.py:test_no_unrecognized_top_level_keys.
    doc = {"$schema": "https://opencode.ai/config.json",
           "provider": {"mlx-local": {
               "npm": "@ai-sdk/openai-compatible", "name": "mlx-serve (local)",
               "options": {"baseURL": "http://localhost:8000/v1", "apiKey": "not-needed"},
               "models": local_models}}}
    if task:
        doc["provider"]["mlx-task"] = {
            "npm": "@ai-sdk/openai-compatible", "name": "mlx task model (local)",
            "options": {"baseURL": f"http://localhost:{task.port}/v1", "apiKey": "not-needed"},
            "models": {task.name: {"name": task.display_name, "tool_call": False,
                                    "attachment": False,
                                    "modalities": {"input": ["text"], "output": ["text"]},
                                    "limit": {"context": task.context, "input": input_limit(task), "output": task.output}}}}
        doc["small_model"] = f"mlx-task/{task.name}"
    default = source.agent_defaults.get("opencode")
    if default:
        doc["model"] = f"mlx-local/{default}"
    doc.setdefault("plugin", ["superpowers@git+https://github.com/obra/superpowers.git"])
    return json.dumps(doc, indent=2) + "\n"


def emit_opencode_bench_v2(source: Source) -> str:
    """M59 native 2.x benchmark carrier (main + candidate, fixed caps, no title)."""
    models = {
        m.name: {
            'capabilities': {'tools': True,
                             'input': ['text', 'image'] if 'vision' in m.capabilities else ['text'],
                             'output': ['text']},
            'limit': {'context': m.context, 'input': input_limit(m), 'output': m.output},
            'compatibility': {'maxTokensField': 'max_tokens'},
            'body': {**sampling_openai(m), **sampling_extra(m), 'seed': 0},
        } for m in source.models if m.role in ('main', 'candidate')
    }
    return json.dumps({
        '$schema': 'https://opencode.ai/config.json',
        'plugins': ['-opencode.provider.vllm', '-opencode.provider.ollama',
                    '-opencode.provider.lmstudio', '-opencode.config.compatibility'],
        'compaction': {'auto': False}, 'agents': {'title': {'disabled': True}},
        'update': 'disable', 'share': 'disabled',
        'permissions': [dict(action=a, resource='*', effect='deny') for a in
                        ('external_directory', 'question', 'websearch', 'webfetch', 'execute')],
        'providers': {
            'vllm': {'settings': {'baseURL': 'http://127.0.0.1:9/v1'}},
            'mlx-local': {'name': 'mlx-serve (local)',
                          'package': '@opencode/ai/providers/openai-compatible',
                          'settings': {'baseURL': 'http://localhost:8000/v1', 'apiKey': 'not-needed'}, 'models': models},
        },
    }, indent=2) + '\n'


def emit_opencode_bench_v2_web(source: Source) -> str:
    """M61 audited-web carrier; preserve every other M59 setting."""
    doc = json.loads(emit_opencode_bench_v2(source))
    doc["permissions"] = [
        {"action": action, "resource": resource, "effect": effect}
        for action, resource, effect in [
            ("external_directory", "*", "deny"), ("question", "*", "deny"),
            ("websearch", "*", "deny"), ("execute", "*", "deny"),
            ("webfetch", "*", "allow"), ("webfetch", "*xercism*", "deny"),
            ("webfetch", "*problem-specifications*", "deny"),
            ("shell", "*xercism*", "deny"), ("shell", "*problem-specifications*", "deny"),
        ] + [(action, pattern, "deny") for action in ("webfetch", "shell")
             for pattern in ("*XERCISM*", "*PROBLEM-SPECIFICATIONS*",
                             "*api.github.com/search*", "*github.com/search*", "*grep.app*",
                             "*sourcegraph.com*", "*searchcode.com*")]
    ]
    return json.dumps(doc, indent=2) + "\n"


def emit_opencode_bench_v2_web_tg1(source: Source) -> str:
    """M62 passive gate carrier; plugins are installed by the isolated probe."""
    doc = json.loads(emit_opencode_bench_v2_web(source))
    doc['permissions'].append(dict(action='subagent', resource='*', effect='deny'))
    return json.dumps(doc, indent=2) + '\n'


def _emit(source: Source) -> str:
    """Native v2 daily-driver carrier; the pinned 1.18 benchmark stays on _emit_v1."""
    def model(m, *, tools: bool) -> dict:
        item = {
            "name": m.display_name,
            "capabilities": {"tools": tools,
                             "input": ["text", "image"] if tools and "vision" in m.capabilities else ["text"],
                             "output": ["text"]},
            "limit": {"context": m.context, "input": input_limit(m), "output": m.output},
            "compatibility": {"maxTokensField": "max_tokens"},
        }
        sampling = {**sampling_openai(m), **sampling_extra(m)}
        if tools or sampling:
            item["body"] = sampling
        return item

    doc = {
        "$schema": "https://opencode.ai/config.json",
        "update": "disable", "share": "disabled", "compaction": {"auto": True},
        "plugins": ["-opencode.provider.vllm", "-opencode.provider.ollama",
                    "-opencode.provider.lmstudio", "-opencode.config.compatibility"],
        "providers": {"mlx-local": {
            "name": "mlx-serve (local)", "package": "@opencode/ai/providers/openai-compatible",
            "settings": {"baseURL": "http://localhost:8000/v1", "apiKey": "not-needed"},
            "models": {m.name: model(m, tools=True) for m in source.models if m.role == "main"},
        }},
    }
    task = next((m for m in source.models if m.role == "task"), None)
    if task:
        doc["providers"]["mlx-task"] = {
            "name": "mlx task model (local)", "package": "@opencode/ai/providers/openai-compatible",
            "settings": {"baseURL": f"http://localhost:{task.port}/v1", "apiKey": "not-needed"},
            "models": {task.name: model(task, tools=False)},
        }
        doc["agents"] = {"title": {"model": f"mlx-task/{task.name}"}}
    default = source.agent_defaults.get("opencode")
    if default:
        doc["model"] = f"mlx-local/{default}"
    return json.dumps(doc, indent=2) + "\n"
