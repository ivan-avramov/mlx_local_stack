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


TG2_BRAND_FORMS = {"github": "?itHub", "githubusercontent": "?itHubUserContent", "sourcegraph": "?ourceGraph",
                   "searchcode": "?earchCode", "jsdelivr": "?sDelivr"}


def _case_forms(text: str, literal_short: bool = False) -> list:
    """S29 T4: the case forms of a pattern for opencode's case-sensitive `Wildcard.match`: the first letter of every word is
    `?` (any case) and the rest is lower or UPPER per word (plus the brand spelling, `TG2_BRAND_FORMS`), every combination.
    `literal_short`: a word of up to three letters is lower, UPPER or Title literally instead (a `?` lets `io` match `lo`)."""
    import itertools
    import re as _re
    parts = _re.split(r"([A-Za-z]+)", text)
    options = []
    for k, part in enumerate(parts):
        if k % 2 == 0 or not part:
            options.append([part])
            continue
        if literal_short and len(part) <= 3:
            forms = [part.lower(), part.upper(), part.title()]
        else:
            rest = part[1:]
            forms = ["?" + rest.lower(), "?" + rest.upper()] + ([TG2_BRAND_FORMS[part.lower()]]
                                                                if part.lower() in TG2_BRAND_FORMS else [])
        options.append(list(dict.fromkeys(forms)))
    return ["".join(c) for c in itertools.product(*options)]


# S29 T3 / T4: the tg2 lookup denies. A fetch of Exercism / problem-specifications content and the code-search sites stay
# denied in any case and inside a compound command, read whole or per parsed command (every pattern but the CLI-at-start
# forms is `*`-prefixed; the CLI forms also come after each command separator); the word alone (a local build flag such as
# `-DEXERCISM_RUN_ALL_TESTS=ON` / `-Dexercism.local=true`, a file or a path) is not a lookup and is allowed.
TG2_EXERCISM = _case_forms("exercism")
# the Exercism hosts in URL / host position only (after `//`, a subdomain `.`, `user@`, a space, `=` or a quote)
TG2_HOSTS = _case_forms("exercism.org", literal_short=True) + _case_forms("exercism.io", literal_short=True)
TG2_HOST_PREFIXES = ("//", ".", "@", " ", "=", "'", '"')
# the org on GitHub (web, ssh, raw, API repos / org / user, CDN): substring forms
TG2_ORG_FORMS = (
    "github.com/exercism", "github.com:exercism", "githubusercontent.com/exercism", "github.com/repos/exercism",
    "github.com/orgs/exercism", "github.com/users/exercism", "jsdelivr.net/gh/exercism", "github:exercism", "gh:exercism/",
)
TG2_CODE_SEARCH_FORMS = ("api.github.com/search", "github.com/search", "grep.app", "sourcegraph.com", "searchcode.com")
TG2_REPO_FETCHERS = ("degit", "tiged", "giget")
TG2_PACKAGE_TOOLS = ("npm", "npx", "yarn", "bun", "bunx")             # `*npm` covers pnpm, `*npx` covers pnpx
TG2_CLI_SEPARATORS = ("; ", ";", "| ", "|", "& ", "&", "( ", "(", "`", "\n")
TG2_PS_FETCHERS = ("curl", "wget", "git clone", "git submodule", "git remote", "git fetch", "git pull", "git archive",
                   "gh repo", "gh api", "svn", "urlopen(", "fetch(", "requests.get(") + TG2_REPO_FETCHERS + TG2_PACKAGE_TOOLS


def _tg2_shell_lookups() -> list:
    ex, ps = TG2_EXERCISM, _case_forms("problem-specifications")
    out = [f"*{p}{h}*" for h in TG2_HOSTS for p in TG2_HOST_PREFIXES]
    out += [f"*{c}*" for f in TG2_ORG_FORMS + TG2_CODE_SEARCH_FORMS for c in _case_forms(f, literal_short=f.startswith("gh:"))]
    # problem-specifications: URL, ssh / scp, `github:` shorthand and fetch-command forms only (a local path is allowed)
    out += [f"*://*{p}*" for p in ps] + [f"*@*:*{p}*" for p in ps]
    out += [f"*{g}*{p}*" for g in _case_forms("github:") + _case_forms("gh:", literal_short=True) for p in ps]
    out += [f"*{t}{'' if t.endswith('(') else ' '}*{p}*" for t in TG2_PS_FETCHERS for p in ps]
    # repository shorthand fetchers (`npx degit exercism/rust`) and package-manager specs of the org (`exercism/rust`,
    # `exercism`, `exercism@x`, `exercism#ref`); a scoped `@exercism/...` tooling package is not the org's repository
    out += [f"*{t} *{x}*" for t in TG2_REPO_FETCHERS for x in ex]
    out += [f"*{t} {mid}{x}{end}" for t in TG2_PACKAGE_TOOLS for mid in ("", "* ") for x in ex
            for end in (" *", "/*", "@*", "#*")]
    out += [f"*install {x}*" for x in ex]
    # the GitHub CLI: repositories, org / user API, code search; anywhere in the line
    out += [f"*gh repo * {x}/*" for x in ex] + [f"*gh repo list *{x}*" for x in ex]
    out += [f"*gh api *repos/{x}/*" for x in ex] + [f"*gh api *{k}/{x}*" for k in ("orgs", "users") for x in ex]
    out += ["*gh search *"]
    # the Exercism CLI: at the start of a command and after each command separator
    out += [f"{x} *" for x in ex] + [f"*{s}{x} *" for s in TG2_CLI_SEPARATORS for x in ex]
    return out


def tg2_permissions(tg1_permissions: list) -> list:
    """The tg1 carrier's permissions with its lookup denies (`*xercism*` and the code-search words) replaced by the S29 forms:
    webfetch keeps the broad Exercism word (a fetched URL is never local), shell denies the lookup forms only."""
    lookup = {"*xercism*", "*XERCISM*", "*problem-specifications*", "*PROBLEM-SPECIFICATIONS*"} | {
        f"*{f}*" for f in TG2_CODE_SEARCH_FORMS}
    kept = [p for p in tg1_permissions if not (p["action"] in ("webfetch", "shell") and p["effect"] == "deny"
                                               and p["resource"] in lookup)]
    tail = [p for p in kept if p["action"] == "subagent"]
    head = [p for p in kept if p["action"] != "subagent"]

    def rules(action, patterns):
        return [{"action": action, "resource": r, "effect": "deny"} for r in dict.fromkeys(patterns)]
    web = ["*xercism*", "*XERCISM*"] + [f"*{c}*" for f in ("problem-specifications",) + TG2_CODE_SEARCH_FORMS
                                        for c in _case_forms(f)]
    return head + rules("webfetch", web) + rules("shell", _tg2_shell_lookups()) + tail


def emit_opencode_bench_v2_web_tg2(source: Source) -> str:
    """M76 B4b-1: the tg2 carrier (`opencode-v2-web-tg2`) is tg1's carrier under its own path and label; S29: with the tg2
    lookup denies (`tg2_permissions`), so that the agent's own build / test commands are never denied."""
    doc = json.loads(emit_opencode_bench_v2_web_tg1(source))
    doc["permissions"] = tg2_permissions(doc["permissions"])
    return json.dumps(doc, indent=2) + "\n"


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
