#!/usr/bin/env python3
"""Render searxng/settings.yml -> searxng/settings.generated.yml.

The committed settings.yml never carries a real secret (the repo is public).
This fills in the server secret_key and any free-tier API keys from the
environment, leaving keyed engines inactive when their variable is unset.
docker-compose mounts the generated file, not the template.
"""
import os
import secrets
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "searxng" / "settings.yml"
DST = REPO_ROOT / "searxng" / "settings.generated.yml"

# engine name -> env var carrying its free-tier API key
API_KEY_ENGINES = {
    "braveapi": "BRAVE_SEARCH_API_KEY",
    "wolframalpha_api": "WOLFRAM_APP_ID",
}


def check_keep_only_covers_overrides(data: dict) -> list[str]:
    """Return override names that keep_only would turn into broken stubs.

    SearXNG's settings loader applies keep_only to the DEFAULT engine list and
    only then merges the user `engines:` list, APPENDING any entry whose name
    keep_only removed. Such an entry has no `engine:` module and breaks engine
    registration at startup. Overriding an engine therefore requires listing it
    in keep_only too.
    """
    # `use_default_settings` is either a bool or a mapping; only the mapping
    # form can carry keep_only.
    uds = data.get("use_default_settings")
    if not isinstance(uds, dict):
        return []
    keep_only = (uds.get("engines") or {}).get("keep_only")
    if not keep_only:
        return []
    return [e["name"] for e in data.get("engines", []) if e["name"] not in set(keep_only)]


def render(data: dict, env: dict) -> dict:
    orphans = check_keep_only_covers_overrides(data)
    if orphans:
        raise SystemExit(
            f"settings.yml: engine override(s) {orphans} are not in "
            f"use_default_settings.engines.keep_only. SearXNG would append them as "
            f"engine definitions with no module and fail to start. Add them to "
            f"keep_only or drop the override."
        )

    server = data.setdefault("server", {})
    # A fresh key per render is fine: it signs the image proxy and CSRF tokens,
    # neither of which needs to survive a restart. An explicit value wins so an
    # operator can pin one.
    server["secret_key"] = env.get("SEARXNG_SECRET_KEY", "").strip() or secrets.token_hex(32)

    by_name = {e["name"]: e for e in data.get("engines", [])}
    for name, env_var in API_KEY_ENGINES.items():
        entry = by_name.get(name)
        if entry is None:
            continue
        key = env.get(env_var, "").strip()
        if key:
            entry["api_key"] = key
            entry["inactive"] = False
        else:
            entry.pop("api_key", None)
            entry["inactive"] = True
    return data


def main() -> None:
    data = yaml.safe_load(SRC.read_text())
    data = render(data, dict(os.environ))
    DST.write_text(yaml.safe_dump(data, sort_keys=False))
    keep = (data.get("use_default_settings") or {}).get("engines", {}).get("keep_only", [])
    active = [
        e["name"] for e in data.get("engines", [])
        if not e.get("inactive") and e.get("disabled") is False
    ]
    print(f"wrote {DST.relative_to(REPO_ROOT)}: keep_only={keep} active_overrides={active}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
