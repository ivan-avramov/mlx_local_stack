"""render_settings: keep_only/override coherence, secrets, and key gating.

The keep_only guard exists because of a real failure mode in SearXNG's settings
loader, not a hypothetical one: keep_only filters the DEFAULT engine list and
only THEN merges the user `engines:` list, appending any override whose name it
already removed. The appended entry has no `engine:` module and breaks engine
registration. The committed settings.yml carried exactly such a stub for
`karmasearch`, an engine upstream had deleted.
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_settings as rs  # noqa: E402

SETTINGS = Path(__file__).resolve().parent / "settings.yml"


@pytest.fixture
def shipped():
    return yaml.safe_load(SETTINGS.read_text())


# ------------------------------------------------- the shipped file is coherent
def test_shipped_settings_render_without_error(shipped):
    rs.render(shipped, {})


def test_every_engine_override_is_whitelisted(shipped):
    assert rs.check_keep_only_covers_overrides(shipped) == []


def test_shipped_pool_is_the_qualified_three(shipped):
    """Changing the shipped engine pool must be a deliberate, evidenced edit."""
    keep = shipped["use_default_settings"]["engines"]["keep_only"]
    web = [n for n in keep if n not in ("braveapi", "wolframalpha_api")]
    assert web == ["duckduckgo web", "startpage", "google"]


def test_engines_upstream_ships_disabled_are_explicitly_enabled(shipped):
    """keep_only SELECTS an engine; it does not enable one. Upstream ships
    `duckduckgo web` and `google` disabled and `startpage` inactive, so without
    these overrides the instance would register an empty pool."""
    by_name = {e["name"]: e for e in shipped["engines"]}
    assert by_name["duckduckgo web"]["disabled"] is False
    assert by_name["google"]["disabled"] is False
    assert by_name["startpage"]["disabled"] is False
    assert by_name["startpage"]["inactive"] is False


# ------------------------------------------------------------- the guard bites
def test_orphan_override_is_rejected():
    data = {
        "use_default_settings": {"engines": {"keep_only": ["google"]}},
        "engines": [{"name": "google", "disabled": False},
                    {"name": "karmasearch", "disabled": True}],
    }
    assert rs.check_keep_only_covers_overrides(data) == ["karmasearch"]
    with pytest.raises(SystemExit, match="karmasearch"):
        rs.render(data, {})


def test_no_guard_when_keep_only_absent():
    data = {"use_default_settings": True, "engines": [{"name": "whatever"}]}
    assert rs.check_keep_only_covers_overrides(data) == []


# ------------------------------------------------------------------- secrets
def test_placeholder_secret_key_is_always_replaced(shipped):
    placeholder = shipped["server"]["secret_key"]
    out = rs.render(shipped, {})
    assert out["server"]["secret_key"] != placeholder
    assert len(out["server"]["secret_key"]) >= 32


def test_explicit_secret_key_wins(shipped):
    out = rs.render(shipped, {"SEARXNG_SECRET_KEY": "pinned-by-operator"})
    assert out["server"]["secret_key"] == "pinned-by-operator"


def test_committed_template_carries_no_real_secret():
    """The repo is public."""
    raw = yaml.safe_load(SETTINGS.read_text())
    assert "PLACEHOLDER" in raw["server"]["secret_key"]
    for engine in raw["engines"]:
        assert "api_key" not in engine


# ----------------------------------------------------------------- key gating
def test_keyed_engines_stay_inactive_without_a_key(shipped):
    out = rs.render(shipped, {})
    by_name = {e["name"]: e for e in out["engines"]}
    assert by_name["braveapi"]["inactive"] is True
    assert "api_key" not in by_name["braveapi"]


def test_key_activates_its_engine(shipped):
    out = rs.render(shipped, {"BRAVE_SEARCH_API_KEY": "bsk-test"})
    by_name = {e["name"]: e for e in out["engines"]}
    assert by_name["braveapi"]["inactive"] is False
    assert by_name["braveapi"]["api_key"] == "bsk-test"
    # the other keyed engine is untouched
    assert by_name["wolframalpha_api"]["inactive"] is True
