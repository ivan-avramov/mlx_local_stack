"""
Reconcile OpenWebUI model registrations against the on-disk source of
truth (models_config.json), with cross-checks against main_models.yaml
(what mlx-serve can actually load) and _family_defaults.py (vendor
recommended params).

Workflow:
  1. Edit models_config.json (and main_models.yaml / _family_defaults.py
     as needed) by hand.
  2. Run `python publish_models.py` to see a diff (dry-run by default).
  3. Run `python publish_models.py --apply` to push the changes after
     reviewing.

The publisher does not touch OWU-side models that are absent from
models_config.json unless `--prune` is passed, and even then it asks
again before deleting.

Auth: tries the OWUI_URL / OWUI_ADMIN_EMAIL / OWUI_ADMIN_PASSWORD env
vars first; if the credentials are rejected, prompts interactively.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
MODELS_JSON = SCRIPT_DIR / "models_config.json"
YAML_PATH = SCRIPT_DIR.parent / "main_models.yaml"
FAMILY_DEFAULTS_PATH = SCRIPT_DIR / "_family_defaults.py"

# Fields the publisher owns. Anything else returned by OWU (created_at,
# urlIdx, user_id, etc.) is ignored when computing the diff.
OWNED_FIELDS = ("name", "params", "meta")


# --------------------------------------------------------------------- IO


def load_local_models() -> list[dict]:
    if not MODELS_JSON.exists():
        sys.exit(f"missing {MODELS_JSON}")
    with MODELS_JSON.open() as f:
        return json.load(f)


def load_yaml_model_names() -> set[str] | None:
    """Return the set of `name:` entries from main_models.yaml, or None
    if PyYAML isn't available or the file isn't there."""
    if not YAML_PATH.exists():
        return None
    try:
        import yaml
    except ImportError:
        return None
    with YAML_PATH.open() as f:
        doc = yaml.safe_load(f)
    return {m["name"] for m in (doc or {}).get("models", []) if "name" in m}


def load_family_defaults() -> tuple[list[tuple[str, str]], dict[str, dict]] | None:
    """Best-effort load of FAMILY_DETECTION + VENDOR_RECOMMENDED."""
    if not FAMILY_DEFAULTS_PATH.exists():
        return None
    ns: dict[str, Any] = {}
    exec(compile(FAMILY_DEFAULTS_PATH.read_text(), str(FAMILY_DEFAULTS_PATH), "exec"), ns)
    return ns.get("FAMILY_DETECTION", []), ns.get("VENDOR_RECOMMENDED", {})


def detect_family(model_id: str, table: list[tuple[str, str]]) -> str | None:
    m = (model_id or "").lower()
    if "/" in m:
        m = m.rsplit("/", 1)[-1]
    for substring, family_id in table:
        if substring in m:
            return family_id
    return None


# ------------------------------------------------------------------- Auth


def authenticate(base_url: str, email: str | None, password: str | None) -> str:
    """Return a bearer token. Prompts on failure."""
    while True:
        if not email:
            email = input("OWU admin email: ").strip()
        if not password:
            password = getpass.getpass("OWU admin password: ")
        r = requests.post(
            f"{base_url}/api/v1/auths/signin",
            json={"email": email, "password": password},
        )
        if r.status_code == 200:
            return r.json()["token"]
        print(f"  authentication failed (HTTP {r.status_code}). Try again.")
        email = None
        password = None


# ------------------------------------------------------------------- Diff


def project(entry: dict) -> dict:
    return {k: entry.get(k) for k in OWNED_FIELDS}


def dict_diff(a: dict, b: dict, prefix: str = "") -> list[str]:
    """Render a one-line-per-change unified-style diff of two dicts.
    Recurses into nested dicts, treats lists as opaque scalars."""
    lines: list[str] = []
    keys = sorted(set(a) | set(b))
    for k in keys:
        path = f"{prefix}.{k}" if prefix else k
        if k not in a:
            lines.append(f"    + {path} = {b[k]!r}")
        elif k not in b:
            lines.append(f"    - {path} = {a[k]!r}")
        elif isinstance(a[k], dict) and isinstance(b[k], dict):
            lines.extend(dict_diff(a[k], b[k], path))
        elif a[k] != b[k]:
            lines.append(f"    ~ {path}: {a[k]!r} -> {b[k]!r}")
    return lines


def compute_diff(local: list[dict], remote: list[dict]) -> dict:
    local_by_id = {m["id"]: m for m in local}
    remote_by_id = {m["id"]: m for m in remote}
    adds = [local_by_id[i] for i in local_by_id if i not in remote_by_id]
    removes = [remote_by_id[i] for i in remote_by_id if i not in local_by_id]
    updates = []
    for i in local_by_id:
        if i not in remote_by_id:
            continue
        l = project(local_by_id[i])
        r = project(remote_by_id[i])
        if l != r:
            updates.append((i, r, l))
    return {"add": adds, "update": updates, "remove": removes}


# ----------------------------------------------------------------- Render


def render_diff(diff: dict, prune: bool) -> bool:
    """Print the diff. Returns True if there is anything to apply."""
    has_change = False

    if diff["add"]:
        has_change = True
        print(f"\nADD ({len(diff['add'])}):")
        for m in diff["add"]:
            print(f"  + {m['id']}")
            for line in dict_diff({}, project(m)):
                print(line)

    if diff["update"]:
        has_change = True
        print(f"\nUPDATE ({len(diff['update'])}):")
        for model_id, remote, local in diff["update"]:
            print(f"  ~ {model_id}")
            for line in dict_diff(remote, local):
                print(line)

    if diff["remove"]:
        label = "REMOVE" if prune else "OWU-ONLY (not in JSON; pass --prune to remove)"
        print(f"\n{label} ({len(diff['remove'])}):")
        for m in diff["remove"]:
            print(f"  - {m['id']}")
        if prune:
            has_change = True

    if not has_change:
        print("\nIn sync. Nothing to do.")
    return has_change


def render_warnings(local: list[dict]) -> None:
    """Soft cross-checks against main_models.yaml and family defaults."""
    yaml_names = load_yaml_model_names()
    fam = load_family_defaults()

    if yaml_names is None:
        print("note: main_models.yaml cross-check skipped (file missing or PyYAML unavailable).")
    else:
        # JSON model whose `id` last segment doesn't match any yaml name
        json_short_ids = {m["id"].rsplit("/", 1)[-1] for m in local}
        missing_in_yaml = json_short_ids - yaml_names
        if missing_in_yaml:
            print("warn: in models_config.json but not in main_models.yaml (mlx-serve cannot load):")
            for n in sorted(missing_in_yaml):
                print(f"      - {n}")
        missing_in_json = yaml_names - json_short_ids
        if missing_in_json:
            print("note: in main_models.yaml but not in models_config.json (no OWU defaults):")
            for n in sorted(missing_in_json):
                print(f"      - {n}")

    if fam is None:
        print("note: _family_defaults.py cross-check skipped.")
    else:
        detection, vendor = fam
        for m in local:
            family = detect_family(m["id"], detection)
            if family is None or family not in vendor:
                continue
            params = m.get("params", {})
            recommended = {k: v for k, v in vendor[family].items() if not k.startswith("_")}
            drift = {k: (params[k], v) for k, v in recommended.items() if k in params and params[k] != v}
            if drift:
                print(f"note: {m['id']} ({family}) drifts from VENDOR_RECOMMENDED:")
                for k, (have, want) in drift.items():
                    print(f"      ~ {k}: have {have!r}, vendor card recommends {want!r}")


# ------------------------------------------------------------------ Apply


def fetch_remote(base_url: str, headers: dict) -> list[dict]:
    r = requests.get(f"{base_url}/api/v1/models/", headers=headers)
    if r.status_code != 200:
        sys.exit(f"failed to list OWU models: HTTP {r.status_code} {r.text}")
    return r.json()


def apply_create(base_url: str, headers: dict, model: dict) -> bool:
    payload = {
        "id": model["id"],
        "name": model.get("name", model["id"]),
        "params": model.get("params", {}),
        "meta": model.get("meta", {}),
    }
    r = requests.post(f"{base_url}/api/v1/models/create", headers=headers, json=payload)
    if r.status_code == 200:
        print(f"  created {model['id']}")
        return True
    print(f"  FAILED to create {model['id']}: HTTP {r.status_code} {r.text}")
    return False


def apply_update(base_url: str, headers: dict, model: dict) -> bool:
    payload = {
        "id": model["id"],
        "name": model.get("name", model["id"]),
        "meta": model.get("meta", {}),
        "params": model.get("params", {}),
        "data": model,
    }
    r = requests.post(
        f"{base_url}/api/v1/models/model/update?id={model['id']}",
        headers=headers,
        json=payload,
    )
    if r.status_code == 200:
        print(f"  updated {model['id']}")
        return True
    print(f"  FAILED to update {model['id']}: HTTP {r.status_code} {r.text}")
    return False


def apply_delete(base_url: str, headers: dict, model_id: str) -> bool:
    r = requests.delete(
        f"{base_url}/api/v1/models/model/delete?id={model_id}",
        headers=headers,
    )
    if r.status_code == 200:
        print(f"  deleted {model_id}")
        return True
    print(f"  FAILED to delete {model_id}: HTTP {r.status_code} {r.text}")
    return False


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


# -------------------------------------------------------------------- Main


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply the diff after confirmation. Default is dry-run.",
    )
    p.add_argument(
        "--prune",
        action="store_true",
        help="Treat OWU models absent from models_config.json as removals.",
    )
    p.add_argument(
        "--url",
        default=os.environ.get("OWUI_URL"),
        help="OWU base URL. Defaults to $OWUI_URL.",
    )
    p.add_argument(
        "--email",
        default=os.environ.get("OWUI_ADMIN_EMAIL"),
        help="Admin email. Defaults to $OWUI_ADMIN_EMAIL.",
    )
    args = p.parse_args()

    if not args.url:
        sys.exit("set --url or OWUI_URL")

    local = load_local_models()
    print(f"loaded {len(local)} models from {MODELS_JSON.name}")
    render_warnings(local)

    token = authenticate(args.url, args.email, os.environ.get("OWUI_ADMIN_PASSWORD"))
    headers = {"Authorization": f"Bearer {token}"}
    remote = fetch_remote(args.url, headers)
    print(f"fetched {len(remote)} models from {args.url}")

    diff = compute_diff(local, remote)
    has_change = render_diff(diff, prune=args.prune)
    if not has_change:
        return 0

    if not args.apply:
        print("\ndry-run. Re-run with --apply to push these changes.")
        return 0

    if not confirm("\napply add/update changes?"):
        print("aborted.")
        return 1

    ok = True
    for m in diff["add"]:
        ok &= apply_create(args.url, headers, m)
    for model_id, _remote, _local in diff["update"]:
        m = next(x for x in local if x["id"] == model_id)
        ok &= apply_update(args.url, headers, m)

    if args.prune and diff["remove"]:
        if confirm(f"\nDELETE {len(diff['remove'])} OWU model(s)? this is destructive."):
            for m in diff["remove"]:
                ok &= apply_delete(args.url, headers, m["id"])
        else:
            print("skipped removals.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
