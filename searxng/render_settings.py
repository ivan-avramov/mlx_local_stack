#!/usr/bin/env python3
"""Render searxng/settings.yml -> searxng/settings.generated.yml.

The committed settings.yml never carries a real API key (the repo is public).
This fills in free-tier keys from the environment for engines that require
one, and leaves them inactive when the corresponding env var is unset.
docker-compose mounts the generated file, not the template.
"""
import os
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


def main() -> None:
    data = yaml.safe_load(SRC.read_text())
    by_name = {e["name"]: e for e in data.get("engines", [])}

    for name, env_var in API_KEY_ENGINES.items():
        entry = by_name.get(name)
        if entry is None:
            continue
        key = os.environ.get(env_var, "").strip()
        if key:
            entry["api_key"] = key
            entry["inactive"] = False
        else:
            entry.pop("api_key", None)
            entry["inactive"] = True

    DST.write_text(yaml.safe_dump(data, sort_keys=False))


if __name__ == "__main__":
    main()
