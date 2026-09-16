import requests
import os
import sys
import json

from _splicer import inline_family_defaults
from reconcile_models import API, authenticate, load_desired, reconcile

MODELS, MODEL_SETTINGS = load_desired()
TASK_MODEL = MODEL_SETTINGS["task_model_id"]
if os.environ.get("TASK_MODEL", TASK_MODEL) != TASK_MODEL:
    raise ValueError("TASK_MODEL disagrees with generated registry settings")

BASE_URL = os.environ['OWUI_URL']
ADMIN_EMAIL = os.environ['OWUI_ADMIN_EMAIL']
ADMIN_PASSWORD = os.environ['OWUI_ADMIN_PASSWORD']

def remove_function(headers, func_id):
    """Delete a function if present (idempotent). Used to retire functions we
    no longer ship, so they don't linger in open-webui-data across restarts."""
    r = requests.delete(f"{BASE_URL}/api/v1/functions/id/{func_id}/delete", headers=headers)
    if r.status_code == 200:
        print(f"Removed retired function {func_id}.")
    elif r.status_code in (401, 404):
        print(f"Retired function {func_id} not present; nothing to remove.")
    else:
        print(f"Failed to remove function {func_id}: {r.status_code} {r.text}")

def ensure_function(headers, filepath, func_id, name, description):
    r = requests.get(f"{BASE_URL}/api/v1/functions/id/{func_id}", headers=headers)
    if r.status_code == 200:
        print(f"Function {func_id} already exists. Skipping registration.")
        return

    fcode = open(filepath).read()
    if os.path.basename(filepath).startswith("profile_"):
        fcode = inline_family_defaults(fcode)
    r = requests.post(f"{BASE_URL}/api/v1/functions/create", json={
        "id": func_id,
        "name": name,
        "meta": {
            "description": description
        },
        "content": fcode,
        "type": "filter"
    }, headers=headers)

    if r.status_code == 200:
        print(f"Function {func_id} registered successfully.")
    else:
        print(f"Failed to register function {func_id}: {r.status_code} {r.text}")
        sys.exit(1)

    r = requests.post(f"{BASE_URL}/api/v1/functions/id/{func_id}/toggle", headers=headers)
    if r.status_code != 200:
        print(f"Failed to enable function {func_id}: {r.status_code} {r.text}")
        sys.exit(1)

    print(f"Function {func_id} enabled successfully: {r.json()}")
    r = requests.post(f"{BASE_URL}/api/v1/functions/id/{func_id}/toggle/global", headers=headers)
    if r.status_code != 200:
        print(f"Failed to set function {func_id} as global: {r.status_code} {r.text}")
        sys.exit(1)
    print(f"Function {func_id} set as global successfully: {r.json()}")

def apply_model_configs(headers):
    reconcile(API(BASE_URL, headers), MODELS, MODEL_SETTINGS,
              f"http://host.docker.internal:{os.environ.get('MAIN_MODEL_PORT', '8000')}/v1",
              f"http://host.docker.internal:{os.environ.get('TASK_MODEL_PORT', '8092')}/v1",
              apply=True)

def apply_task_model_config(headers):
    # Grab the model from the environment, fallback to a safe default if missing
    target_model = TASK_MODEL

    # OpenWebUI splits read and write operations across different paths
    read_url = f"{BASE_URL}/api/v1/tasks/config"
    write_url = f"{BASE_URL}/api/v1/tasks/config/update"

    # Fetch the current task configuration
    r_get = requests.get(read_url, headers=headers)
    if r_get.status_code != 200:
        raise RuntimeError(f"Failed to fetch task model config: HTTP {r_get.status_code}")

    config = r_get.json()

    # Autocomplete: on, with a bounded input. OWUI's autocomplete payload
    # (routers/tasks.py) carries NO max_tokens of its own and goes through the
    # normal chat path, so the only thing capping its output is the task model's
    # OWUI params -- which configgen now emits from main_models.yaml
    # (generation_defaults.max_tokens). The input side is this key: OWUI's own UI
    # describes it as "-1 for no limit, or a positive integer for a specific
    # limit", and the backend never reads it (grep of routers/tasks.py: it is
    # only mapped and exposed), so it is enforced client-side. 1000 is
    # conservative whether the unit is characters or tokens; -1 would re-prefill
    # an arbitrarily long draft on every autocomplete trigger.
    desired = {
        "TASK_MODEL": target_model,
        "TASK_MODEL_EXTERNAL": target_model,
        "ENABLE_AUTOCOMPLETE_GENERATION": True,
        "AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH": 1000,
    }

    # Avoid unnecessary writes if the state already matches. Compares EVERY key
    # we manage, not just the model: an early return keyed on the task model
    # alone would silently skip the autocomplete settings forever once the model
    # was right.
    if all(config.get(k) == v for k, v in desired.items()):
        print(f"Task config already correct (task model {target_model}, autocomplete on). Skipping update.")
        return

    # BOTH keys, because utils/task.py:get_task_model_id picks one of them based
    # on the CHAT model's connection_type and silently falls back to the chat
    # model itself when the chosen one is empty:
    #
    #   if models[chat_model]['connection_type'] == 'local': use TASK_MODEL
    #   else:                                                use TASK_MODEL_EXTERNAL
    #   neither set -> return the chat model
    #
    # Setting only TASK_MODEL is what sent every title/tags/follow-up call to
    # the 27B/35B/31B with thinking enabled: routers/openai.py defaults a
    # connection with no api_config entry to 'external', so the else-branch ran
    # and TASK_MODEL_EXTERNAL was ''. The shared reconciler marks
    # the main connection 'local' as well, so this is belt-and-braces: whichever
    # branch get_task_model_id takes, it lands on the task model.
    config.update(desired)

    # Push the mutated state to the dedicated update endpoint
    r_post = requests.post(write_url, headers=headers, json=config)
    if r_post.status_code == 200:
        applied = r_post.json()
        print(f"Successfully reconciled task model config to: {target_model}: {applied}")
        for k, v in desired.items():
            if applied.get(k) != v:
                raise RuntimeError(f"Task config verification failed: {k}")
    else:
        raise RuntimeError(f"Failed to update task model config: HTTP {r_post.status_code}")


# Web-search provider. DDGS (the library behind OWUI's "duckduckgo" engine) runs
# inside the OWUI container, so no sidecar and no API key are needed. The backend
# string is an ORDERED preference list tried in batches of ceil(count/10)+1 = 2
# (verified in scripts/websearch/test_ddgs_selection.py); it must be explicit --
# DDGS's default "auto" puts Wikipedia/Grokipedia first, and a wholly invalid
# list silently falls back to "auto". Override per box with OWUI_DDGS_BACKEND /
# OWUI_WEB_SEARCH_ENGINE (set OWUI_WEB_SEARCH_ENGINE=searxng to fall back to the
# sidecar while it is still in docker-compose.yml). Qualification evidence:
# docs/websearch-ddgs-qualification-2026-09-15.md.
WEB_SEARCH_ENGINE = os.environ.get("OWUI_WEB_SEARCH_ENGINE", "duckduckgo").strip() or "duckduckgo"
DDGS_BACKEND = os.environ.get("OWUI_DDGS_BACKEND", "google,duckduckgo,brave").strip() or "google,duckduckgo,brave"
DDGS_BACKENDS_KNOWN = {"google", "duckduckgo", "brave", "mojeek", "startpage", "yahoo", "wikipedia", "grokipedia"}


def validate_ddgs_backend(backend, known=DDGS_BACKENDS_KNOWN):
    """Refuse a backend list DDGS would silently widen or that names a reference backend.

    DDGS drops unknown names with a warning and, if NONE remain, falls back to "auto"
    (Wikipedia/Grokipedia first). Fail loudly here instead: every entry must be a known
    general-web engine. Returns the normalised comma-joined list.
    """
    entries = [b.strip().lower() for b in backend.split(",") if b.strip()]
    if not entries:
        raise RuntimeError("OWUI_DDGS_BACKEND is empty")
    bad = [b for b in entries if b not in known or b in ("auto", "all")]
    if bad:
        raise RuntimeError(f"OWUI_DDGS_BACKEND has unknown/disallowed backends {bad}; known: {sorted(known)}")
    ref = [b for b in entries if b in ("wikipedia", "grokipedia")]
    if ref:
        raise RuntimeError(f"OWUI_DDGS_BACKEND must not use reference backends as general-web search: {ref}")
    return ",".join(entries)


def apply_web_search_config(headers):
    """Enable Web Search and pin the provider (DDGS by default, SearXNG on request).

    OWUI >=0.10 flattened this out of the old rag.web.search.* nesting
    (still what the checked-in openwebui_config.json DB-export uses) into
    a top-level web.search.* config namespace served by the retrieval
    router. The docker-compose `cp openwebui_config.json
    open-webui-data/config.json` seed step only applies to a brand-new
    config store, so a box whose DB predates this schema silently stays
    at OWUI's defaults (search disabled) no matter what the checked-in
    file says. Pushing it live here, every run, keeps it in sync instead --
    and overrides any value an admin later saved through the UI (the UI
    dropdown can only pick a single DDGS backend; the list lives here).
    """
    read_url = f"{BASE_URL}/api/v1/retrieval/config"
    write_url = f"{BASE_URL}/api/v1/retrieval/config/update"

    r_get = requests.get(read_url, headers=headers)
    if r_get.status_code != 200:
        raise RuntimeError(f"Failed to fetch web search config: HTTP {r_get.status_code}")

    # The update endpoint replaces every field in `web` wholesale, so we
    # must merge into the existing dict rather than send a partial one.
    web = r_get.json().get("web", {})
    desired = {
        "ENABLE_WEB_SEARCH": True,
        "WEB_SEARCH_ENGINE": WEB_SEARCH_ENGINE,
        "DDGS_BACKEND": validate_ddgs_backend(DDGS_BACKEND),
        # SearXNG sidecar settings are kept so OWUI_WEB_SEARCH_ENGINE=searxng still works
        # while the sidecar is being deprecated.
        "SEARXNG_QUERY_URL": "http://searxng:8080/search?q=<query>&format=json",
        "SEARXNG_LANGUAGE": "all",
        "WEB_SEARCH_RESULT_COUNT": 10,
        # Semaphore over the queries of one chat-turn fan-out (NOT requests/second, and
        # the DDGS adapter's own use of it is a no-op -- see the qualification report).
        "WEB_SEARCH_CONCURRENT_REQUESTS": 5,
        "WEB_SEARCH_DOMAIN_FILTER_LIST": [],
    }
    web.update(desired)

    r_post = requests.post(write_url, headers=headers, json={"web": web})
    if r_post.status_code != 200:
        raise RuntimeError(f"Failed to apply web search config: HTTP {r_post.status_code}")
    applied = r_post.json().get("web", {})
    for k, v in desired.items():
        if applied.get(k) != v:
            raise RuntimeError(f"Web search config verification failed: {k}={applied.get(k)!r} (wanted {v!r})")
    print(f"Web search config applied: engine={applied['WEB_SEARCH_ENGINE']} "
          f"ddgs_backend={applied['DDGS_BACKEND']} enabled={applied['ENABLE_WEB_SEARCH']}")


def assert_task_model_routing(headers):
    """Fail the init container if OWUI would route task calls to a chat model.

    Everything above is a declarative push; this is the check that it LANDED.
    It reimplements utils/task.py:get_task_model_id against the LIVE config and
    the LIVE model list, for every non-task model, and exits nonzero if any of
    them resolves to something other than the task model.

    Why an assertion and not a comment: this misroute is silent by construction.
    OWUI keeps working, titles/tags/follow-ups keep appearing, and the only
    symptom is that each one costs a full thinking generation on a 27-35B model
    instead of ~1s on the 1.5B. It went unnoticed through several stack updates.
    The image is also deliberately unpinned (docker-compose.yml pulls :main every
    run), so the gate this depends on can change under us at any time -- an
    assertion turns that into a loud bring-up failure instead of a slow regression.
    """
    target_model = TASK_MODEL

    r_cfg = requests.get(f"{BASE_URL}/api/v1/tasks/config", headers=headers)
    r_models = requests.get(f"{BASE_URL}/api/models", headers=headers)
    if r_cfg.status_code != 200 or r_models.status_code != 200:
        print(
            f"Task-routing assertion could not read state "
            f"(tasks/config HTTP {r_cfg.status_code}, models HTTP {r_models.status_code})."
        )
        sys.exit(1)

    cfg = r_cfg.json()
    task_model = cfg.get("TASK_MODEL") or ""
    task_model_external = cfg.get("TASK_MODEL_EXTERNAL") or ""

    payload = r_models.json()
    entries = payload.get("data", payload) if isinstance(payload, dict) else payload
    models = {m.get("id"): m for m in entries if isinstance(m, dict) and m.get("id")}

    def resolve(chat_model_id):
        """Mirror of utils/task.py:get_task_model_id (OWUI 0.11.0)."""
        if models.get(chat_model_id, {}).get("connection_type") == "local":
            if task_model and task_model in models:
                return task_model
        else:
            if task_model_external and task_model_external in models:
                return task_model_external
        return chat_model_id

    misrouted = {}
    for model_id, model in models.items():
        if model_id == target_model or model.get("owned_by") == "arena":
            continue
        resolved = resolve(model_id)
        if resolved != target_model:
            misrouted[model_id] = (model.get("connection_type"), resolved)

    if misrouted:
        print("\n*** TASK MODEL ROUTING ASSERTION FAILED ***")
        print(f"  expected every chat model's task calls to resolve to: {target_model}")
        print(f"  TASK_MODEL={task_model!r} TASK_MODEL_EXTERNAL={task_model_external!r}")
        for model_id, (conn_type, resolved) in sorted(misrouted.items()):
            print(f"  {model_id!r}: connection_type={conn_type!r} -> resolves to {resolved!r}")
        print(
            "\n  Consequence: OWUI's title / tags / follow-up / search-query generation\n"
            "  would run on that chat model (thinking enabled) after every response,\n"
            "  instead of the dedicated task model. See reconcile_models.connection_config.\n"
            "  If OWUI changed get_task_model_id, re-read utils/task.py from the image\n"
            "  and update both that function and resolve() above."
        )
        sys.exit(1)

    print(
        f"Task-model routing verified: all {len(models) - 1} chat model(s) resolve "
        f"task calls to {target_model}."
    )


def main():
    headers = authenticate(BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD)

    # Retired: thinking is now enabled server-side for all main models, so the
    # per-chat Extended Thinking toggle is gone. Delete any lingering copy.
    remove_function(headers, "enable_extended_thinking")

    ensure_function(headers, "advanced.py", "advanced_params", "Advanced Parameters", "Configure advanced model settings, such as temperature, top_p, and penalties")
    ensure_function(headers, "profile_strict.py", "profile_strict", "Strict", "Deterministic implementation tasks under explicit constraints (multi-rule coding prompts, refactoring, algorithm implementation)")
    ensure_function(headers, "profile_math.py", "profile_math", "Math", "Math / formal-logic profile for calculus, proofs, and step-by-step derivations")
    ensure_function(headers, "profile_research.py", "profile_research", "Research", "Exploration profile for design brainstorming, architectural research, and tech-doc writing")
    ensure_function(headers, "profile_creative.py", "profile_creative", "Creative", "Creative-writing profile for essays, fiction, and non-technical long-form prose")
    ensure_function(headers, "profile_casual.py", "profile_casual", "Casual", "Casual / conversational profile for quick everyday Q&A and factual-recall synthesis")
    apply_model_configs(headers)
    apply_task_model_config(headers)
    apply_web_search_config(headers)

    # Verify the routing actually landed. Must run LAST: it reads the live state
    # back, so it validates the pushes above rather than restating their intent.
    assert_task_model_routing(headers)

    print("Init complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
