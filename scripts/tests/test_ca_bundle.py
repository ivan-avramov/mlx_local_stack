"""The container CA-bundle mechanism: resolution, guards, and overlay shape.

Principle (operator, 2026-09-16): give the containers the same level of trust
the host environment has. The host declares it with the standard variables;
these tests pin that we mirror the FILE while never leaking the HOST PATH into
a container, and that the base compose file stays inert without it.
"""

import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[2]
RESOLVER = REPO / "scripts" / "resolve_ca_bundle.sh"
BASE_COMPOSE = REPO / "docker-compose.yml"
CA_COMPOSE = REPO / "docker-compose.ca.yml"

CONTAINER_PATH = "/etc/ssl/stack-ca-bundle.pem"
PEM = ("-----BEGIN CERTIFICATE-----\n"
       "MIIBkTCB+wIJAJ\n"
       "-----END CERTIFICATE-----\n")


def run(env=None, cwd=None):
    """Run the resolver with a scrubbed environment."""
    base = {k: v for k, v in os.environ.items()
            if k not in ("STACK_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")}
    base.update(env or {})
    return subprocess.run([str(RESOLVER)], capture_output=True, text=True,
                          env=base, cwd=str(cwd or REPO))


@pytest.fixture
def bundle(tmp_path):
    p = tmp_path / "corporate-ca.pem"
    p.write_text(PEM)
    return p


# ------------------------------------------------------------------ resolution
def test_no_declared_trust_is_silent_and_successful():
    """The common case. Nothing mounted, nothing exported, stack unchanged."""
    r = run()
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_it_follows_the_host_ssl_cert_file(bundle):
    r = run({"SSL_CERT_FILE": str(bundle)})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(bundle)


def test_requests_ca_bundle_is_the_fallback(bundle):
    r = run({"REQUESTS_CA_BUNDLE": str(bundle)})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(bundle)


def test_explicit_override_wins(tmp_path, bundle):
    other = tmp_path / "explicit.pem"
    other.write_text(PEM)
    r = run({"STACK_CA_BUNDLE": str(other), "SSL_CERT_FILE": str(bundle)})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(other)


def test_a_relative_path_is_made_absolute(tmp_path):
    """A relative bind-mount source becomes a docker NAMED VOLUME, silently
    mounting an empty directory instead of the bundle (docs/box-notes.md)."""
    (tmp_path / "rel.pem").write_text(PEM)
    r = run({"STACK_CA_BUNDLE": "rel.pem"}, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(tmp_path / "rel.pem")


# ---------------------------------------------------------------------- guards
def test_a_missing_file_aborts(tmp_path):
    """Docker bind-mounts a nonexistent host path by CREATING A DIRECTORY there,
    so a typo would break TLS and pollute the filesystem outside $STACK_WORKDIR."""
    r = run({"STACK_CA_BUNDLE": str(tmp_path / "nope.pem")})
    assert r.returncode != 0
    assert "nope.pem" in r.stderr


def test_a_directory_aborts(tmp_path):
    r = run({"STACK_CA_BUNDLE": str(tmp_path)})
    assert r.returncode != 0


def test_a_file_that_is_not_pem_aborts(tmp_path):
    """SSL_CERT_FILE replaces the trust store wholesale; pointing it at junk
    breaks every TLS connection the container makes."""
    junk = tmp_path / "notes.txt"
    junk.write_text("this is not a certificate\n")
    r = run({"STACK_CA_BUNDLE": str(junk)})
    assert r.returncode != 0


# --------------------------------------------------------------------- overlay
def _services(path):
    return yaml.safe_load(path.read_text())["services"]


def test_the_base_compose_file_stays_inert():
    """A consumer who declares no CA bundle must get today's behaviour exactly."""
    text = BASE_COMPOSE.read_text()
    assert "stack-ca-bundle" not in text
    assert "SSL_CERT_FILE" not in text


def test_the_overlay_covers_every_service():
    """Uniformity (operator P20): no per-service special-casing. SearXNG does
    not strictly need it today, but the containers get the same trust the host
    has, rather than a per-service guess about who needs what."""
    assert set(_services(CA_COMPOSE)) == set(_services(BASE_COMPOSE))


def test_every_service_gets_the_bundle_at_the_same_container_path():
    for name, svc in _services(CA_COMPOSE).items():
        mounts = [v for v in svc["volumes"] if v.endswith(f":{CONTAINER_PATH}:ro")]
        assert mounts, f"{name} does not mount the bundle read-only"
        assert mounts[0].startswith("${STACK_CA_BUNDLE}"), \
            f"{name} must take the host path from the variable, not a literal"


def test_the_container_vars_point_at_the_container_path_not_the_host_path():
    """The footgun this mechanism exists to avoid: `environment: - SSL_CERT_FILE`
    makes compose resolve the name from the INVOKING SHELL, injecting a host
    path that does not exist inside the container -> FileNotFoundError."""
    for name, svc in _services(CA_COMPOSE).items():
        env = svc["environment"]
        assert not any("=" not in e for e in env), \
            f"{name} passes a bare variable through from the host shell"
        pairs = dict(e.split("=", 1) for e in env)
        for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
            assert pairs.get(var) == CONTAINER_PATH, f"{name}.{var}"


def test_runserver_activates_the_overlay_and_aborts_on_a_bad_bundle():
    text = (REPO / "runserver.sh").read_text()
    assert "resolve_ca_bundle.sh" in text
    assert "docker-compose.ca.yml" in text
    # AGENTS.md: `rc=$?` inside `if ! cmd; then` is always 0.
    assert "set +e" in text and "set -e" in text
