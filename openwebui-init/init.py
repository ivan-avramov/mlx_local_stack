import requests
import os
import sys
import json

from _splicer import inline_family_defaults

BASE_URL = os.environ['OWUI_URL']
ADMIN_EMAIL = os.environ['OWUI_ADMIN_EMAIL']
ADMIN_PASSWORD = os.environ['OWUI_ADMIN_PASSWORD']

def get_token():
    r = requests.post(f"{BASE_URL}/api/v1/auths/signin", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if r.status_code == 200:
        print(f"Authentication successful: {r.json()}")
        return r.json()["token"]
    else:
        # If we can't log in, it likely means the admin credentials were changed
        # AFTER the initial setup, which implies the setup is already done.
        # (Or the container isn't fully booted yet).
        print(f"Authentication failed (Status {r.status_code}).")
        print("Assuming setup is already complete or credentials changed. Skipping init.")
        sys.exit(0)

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
    try:
        with open("models_config.json", "r") as f:
            models = json.load(f)
    except FileNotFoundError:
        print("models_config.json not found. Skipping model-specific configuration.")
        return
    except Exception as e:
        print(f"Failed to load models_config.json: {e}")
        return

    for model in models:
        model_id = model["id"]

        params = model.get("params", {})
        meta = model.get("meta", {})

        # Step 1: Create the model entity in the local DB.
        # This resolves the "model not found" error for subsequent updates.
        create_payload = {
            "id": model_id,
            "name": model.get("name", model_id),
            "params": params,
            "meta": meta
        }

        r_create = requests.post(f"{BASE_URL}/api/v1/models/create", headers=headers, json=create_payload)
        if r_create.status_code == 200:
            print(f"Created local DB entry for model: {model_id}: {r_create.json()}")
        elif r_create.status_code == 401:
            print(f"Local DB entry for model {model_id} already exists: {r_create.json()}")
        else:
            print(f"Failed to create model {model_id}: {r_create.status_code} {r_create.text}")
            continue

        # Step 2: Apply the full update payload to ensure strict configuration parity
        model["params"] = params
        model["meta"] = meta
        update_payload = {
            "id": model_id,
            "name": model.get("name", model_id),
            "meta": meta,
            "params": params,
            "data": model
        }

        r_update = requests.post(f"{BASE_URL}/api/v1/models/model/update?id={model_id}", headers=headers, json=update_payload)
        if r_update.status_code == 200:
            print(f"Successfully updated complete config for {model_id} : {r_update.json()}")
        else:
            print(f"Failed to update model {model_id}: {r_update.status_code} {r_update.text}")

def apply_task_model_config(headers):
    # Grab the model from the environment, fallback to a safe default if missing
    target_model = os.environ.get('TASK_MODEL', 'mlx-community/gemma-3-1b-it-4bit')

    # OpenWebUI splits read and write operations across different paths
    read_url = f"{BASE_URL}/api/v1/tasks/config"
    write_url = f"{BASE_URL}/api/v1/tasks/config/update"

    # Fetch the current task configuration
    r_get = requests.get(read_url, headers=headers)
    if r_get.status_code != 200:
        print(f"Failed to fetch task model config: {r_get.status_code} {r_get.text}")
        return

    config = r_get.json()

    # Avoid unnecessary writes if the state already matches
    if config.get("TASK_MODEL") == target_model and config.get("TASK_MODEL_EXTERNAL") == target_model:
        print(f"Task model already configured correctly as {target_model}. Skipping update.")
        return

    # Update both local and external task model references
    config["TASK_MODEL"] = target_model

    # Push the mutated state to the dedicated update endpoint
    r_post = requests.post(write_url, headers=headers, json=config)
    if r_post.status_code == 200:
        print(f"Successfully reconciled task model config to: {target_model}: {r_post.json()}")
    else:
        print(f"Failed to update task model config: {r_post.status_code} {r_post.text}")


def apply_openai_connection_config(headers):
    # Grab the model and port from the environment
    target_model = os.environ.get('TASK_MODEL', 'mlx-community/gemma-3-1b-it-4bit')
    task_port = os.environ.get('TASK_MODEL_PORT', '8092')
    task_model_url = f"http://host.docker.internal:{task_port}/v1"

    # OpenWebUI mounts OpenAI API configuration directly at /openai, not /api/v1/openai
    read_url = f"{BASE_URL}/openai/config"
    write_url = f"{BASE_URL}/openai/config/update"

    r_get = requests.get(read_url, headers=headers)

    # Defend against the SPA catch-all router returning an HTML page with a 200 OK
    if r_get.status_code != 200 or 'text/html' in r_get.headers.get('Content-Type', ''):
        print(f"Failed to fetch OpenAI connection config (Check API routing): HTTP {r_get.status_code}")
        return

    config = r_get.json()

    urls = config.get("OPENAI_API_BASE_URLS", [])
    keys = config.get("OPENAI_API_KEYS", [])
    api_configs = config.get("OPENAI_API_CONFIGS", {})

    # Check if our task backend is already registered in the array
    if task_model_url in urls:
        idx_str = str(urls.index(task_model_url))

        # Ensure the api_configs dict has an entry for this index
        if idx_str not in api_configs:
            api_configs[idx_str] = {}

        current_models = api_configs[idx_str].get("model_ids", [])
        if current_models == [target_model]:
            print(f"OpenAI connection for {task_model_url} already filtering by {target_model}. Skipping.")
            return

        # Enforce the allowlist to ensure it populates in the UI selector
        api_configs[idx_str]["model_ids"] = [target_model]
    else:
        # Inject the connection explicitly if it doesn't exist
        urls.append(task_model_url)
        keys.append("not-needed")
        idx_str = str(len(urls) - 1)
        api_configs[idx_str] = {
            "enable": True,
            "tags": [],
            "prefix_id": "",
            "model_ids": [target_model],
            "connection_type": "local"
        }

    config["OPENAI_API_BASE_URLS"] = urls
    config["OPENAI_API_KEYS"] = keys
    config["OPENAI_API_CONFIGS"] = api_configs

    # Push the mutated state to the dedicated update endpoint
    r_post = requests.post(write_url, headers=headers, json=config)
    if r_post.status_code == 200:
        print(f"Successfully reconciled OpenAI connection config for model: {target_model}: {r_post}")
    else:
        print(f"Failed to update OpenAI config: {r_post.status_code} {r_post.text}")


token = get_token()
headers = {"Authorization": f"Bearer {token}"}

ensure_function(headers, "thinking.py", "enable_extended_thinking", "Extended Thinking", "Enable extended thinking in models that support it")
ensure_function(headers, "advanced.py", "advanced_params", "Advanced Parameters", "Configure advanced model settings, such as temperature, top_p, and penalties")
ensure_function(headers, "profile_strict.py", "profile_strict", "Profile Strict", "Deterministic implementation tasks under explicit constraints (multi-rule coding prompts, refactoring, algorithm implementation)")
ensure_function(headers, "profile_math.py", "profile_math", "Profile Math", "Math / formal-logic profile for calculus, proofs, and step-by-step derivations")
ensure_function(headers, "profile_research.py", "profile_research", "Profile Research", "Exploration profile for design brainstorming, architectural research, and tech-doc writing")
ensure_function(headers, "profile_creative.py", "profile_creative", "Profile Creative", "Creative-writing profile for essays, fiction, and non-technical long-form prose")
ensure_function(headers, "profile_casual.py", "profile_casual", "Profile Casual", "Casual / conversational profile for quick everyday Q&A and factual-recall synthesis")
apply_model_configs(headers)
apply_openai_connection_config(headers)
apply_task_model_config(headers)

print("Init complete")
sys.exit(0)
