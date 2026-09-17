#!/bin/bash
# Resolve the CA bundle to mirror into the stack's containers.
#
# PRINCIPLE (operator 2026-09-16): the containers get the same level of trust
# the host environment has. The host declares that with the standard OpenSSL /
# requests variables, so this reads them rather than inventing a second thing
# to configure. `STACK_CA_BUNDLE` is the explicit override, for a host that
# wants the containers trusting something other than what its own shell does.
#
# Contract:
#   exit 0, path on stdout   -> mirror this file into the containers
#   exit 0, no output        -> host declares nothing; leave the containers
#                               exactly as they ship (the common case)
#   exit 1, reason on stderr -> declared but unusable; the caller must ABORT
#
# Why a declared-but-broken bundle aborts rather than degrading: Docker
# bind-mounts a NONEXISTENT host path by creating a DIRECTORY at it, so a typo
# would silently break TLS in every container AND write outside $STACK_WORKDIR.
#
# Why the containers are not probed here: the stack must come up in airplane
# mode, so nothing in the startup path may depend on reaching the network.
set -uo pipefail

candidate="${STACK_CA_BUNDLE:-${SSL_CERT_FILE:-${REQUESTS_CA_BUNDLE:-}}}"
[ -n "$candidate" ] || exit 0

if [ ! -e "$candidate" ]; then
  echo "CA bundle does not exist: $candidate" >&2
  echo "  (set STACK_CA_BUNDLE, SSL_CERT_FILE or REQUESTS_CA_BUNDLE to a readable PEM file, or unset it)" >&2
  exit 1
fi

if [ ! -f "$candidate" ]; then
  echo "CA bundle is not a regular file: $candidate" >&2
  exit 1
fi

if [ ! -r "$candidate" ]; then
  echo "CA bundle is not readable: $candidate" >&2
  exit 1
fi

# SSL_CERT_FILE REPLACES the trust store rather than adding to it, so pointing
# it at a non-PEM file breaks every TLS connection the container makes. This
# checks the shape only -- it deliberately does not validate the chain, which
# is the host's business and cannot be judged offline.
if ! grep -q -- "-----BEGIN CERTIFICATE-----" "$candidate" 2>/dev/null; then
  echo "CA bundle contains no PEM certificate: $candidate" >&2
  exit 1
fi

# A RELATIVE bind-mount source becomes a docker NAMED VOLUME, which mounts an
# empty directory instead of the bundle (docs/box-notes.md).
case "$candidate" in
  /*) printf '%s\n' "$candidate" ;;
  *)  printf '%s\n' "$(cd "$(dirname "$candidate")" && pwd)/$(basename "$candidate")" ;;
esac
