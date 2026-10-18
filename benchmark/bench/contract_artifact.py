"""P371 phase 4 (A13, R8, P374): the per-arm CONTRACT ARTIFACT, pure data + verification (no client, no test import).

`benchmark/m64/contract_artifact.py --arm <arm>` runs the arm's contract suite on real core runs (the real pinned client
against the scripted mock provider) and writes one canonical JSON artifact:

    {schema, arm, snapshot_sha256, client_version,
     checks:   {<name>: "pass" | "fail" | "OWED"},        one entry per spec 6 check, exactly `CHECKS`
     owed_by:  {<name>: <build step>},                     for every OWED check
     details:  {<name>: <text>},                           for every failed check (scrubbed, portable)
     verdict:  "pass" | "fail" | "incomplete",             fail beats incomplete; incomplete = any OWED
     sha256:   sha256 of the canonical JSON of everything above}

`OWED` checks are the ones that need services that do not exist yet (P374: never faked): the D2 shared search tool and its
schema identity, the infrastructure-failure classification, the P201 cheat re-run through the arm. `ChainConfig` names each
arm's artifact (path + sha256 of the FILE); `chain_core` verifies it at entry, resume, every barrier and exit with `problems`:
a non-smoke chain refuses a missing, failed, incomplete (OWED), malformed or drifted artifact; a smoke chain allows
`incomplete` only. Chain-side module: no probe closure imports it."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

SCHEMA = 1
STATUSES = ("pass", "fail", "OWED")
VERDICTS = ("pass", "fail", "incomplete")

# the spec 6 checks, in report order: name -> the `ArmContractSuite` test method that runs it (a selftest pins both ways)
CHECKS = {
    "wire_controls": "test_wire_controls_every_request",
    "removed_tools_absent": "test_d1_tools_and_hosted_search_absent",
    "retries_off": "test_retries_off_injected_500_aborts_without_a_second_request",
    "accelerated_timeout": "test_accelerated_timeout_or_registered_native_cut",
    "compaction": "test_compaction_at_a_reduced_window",
    "terminal_shapes": "test_terminal_shapes",
    "event_normalization": "test_events_are_normalized",
    "tool_windows": "test_tool_windows_from_the_arms_events",
    "shell_watchdog_positives": "test_shell_watchdog_positives_foreground_background_detached",
    "gate_positives": "test_injected_stall_loop_hard_ceiling_through_the_arms_events",
    "cancel_sigterm_first": "test_cancel_is_sigterm_first",
    "identity_fields": "test_identity_and_manifest_fields",
    "refuses_without_search_service": "test_arm_refuses_without_the_search_service",
    "shared_search_tool": "test_shared_search_tool_identical_across_arms",
    "infrastructure_failures": "test_infrastructure_failure_classification",
    "p201_rerun": "test_p201_cheat_rerun",
}
# the checks that need unbuilt services, and the build step that owes them (P374)
OWED_BY = {
    "shared_search_tool": "M64 spec section 12 step 5 / D2: the shared SearXNG MCP search tool and its schema identity",
    "infrastructure_failures": "M64 spec section 12 step 5 / D2: infrastructure-failure classification "
                               "(container down, MCP crash, all engines erroring)",
    "p201_rerun": "M64 spec section 12 step 5: the P201 cheat re-run through the arm",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_DETAIL = 400


class ArtifactError(ValueError):
    """The artifact cannot be built or read."""


def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha_of(doc):
    """The artifact's own hash: sha256 of the canonical JSON of the document without its `sha256` key."""
    return hashlib.sha256(canonical({k: v for k, v in doc.items() if k != "sha256"}).encode()).hexdigest()


def verdict_of(checks):
    values = set(checks.values())
    return "fail" if "fail" in values else "incomplete" if "OWED" in values else "pass"


def scrub(text):
    """A portable failure detail: no home path, no temp path, one bounded line."""
    text = str(text).strip().splitlines()[0] if str(text).strip() else ""
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "$HOME")
    text = re.sub(r"/(?:private/)?(?:var/folders|tmp)/[^\s'\"]+", "<tmp>", text)
    text = re.sub(r"/Users/[^/\s'\"]+", "$HOME", text)
    return text[:MAX_DETAIL]


def build(arm, snapshot_sha256, client_version, outcomes):
    """The artifact document. `outcomes` is `{check: ("pass"|"fail"|"OWED", detail)}` for EVERY name of `CHECKS` (a missing
    check is a failure of the build, never an implicit pass)."""
    missing = sorted(set(CHECKS) - set(outcomes))
    extra = sorted(set(outcomes) - set(CHECKS))
    if missing or extra:
        raise ArtifactError(f"outcomes must cover exactly the spec 6 checks (missing {missing}, unknown {extra})")
    checks, owed, details = {}, {}, {}
    for name in CHECKS:
        status, detail = outcomes[name]
        if status == "OWED" and name not in OWED_BY:
            status, detail = "fail", f"skipped as owed but not an owed check: {detail}"
        if status not in STATUSES:
            raise ArtifactError(f"check {name}: status {status!r} is not one of {STATUSES}")
        checks[name] = status
        if status == "OWED":
            owed[name] = OWED_BY[name]
        elif status == "fail":
            details[name] = scrub(detail)
    doc = dict(schema=SCHEMA, arm=arm, snapshot_sha256=snapshot_sha256, client_version=client_version, checks=checks,
               owed_by=owed, details=details, verdict=verdict_of(checks))
    doc["sha256"] = sha_of(doc)
    return doc


def dump(doc):
    """The file bytes: canonical JSON and a newline (what the chain hashes)."""
    return (canonical(doc) + "\n").encode()


def file_sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, doc):
    """Atomic write of the canonical bytes; returns the file's sha256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = dump(doc)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return file_sha256(raw)


def validate(doc, *, arm):
    """Why `doc` is not a well-formed, self-consistent artifact of `arm` (a list, empty when it is)."""
    if not isinstance(doc, dict):
        return ["not a JSON object"]
    out = []
    if doc.get("schema") != SCHEMA:
        out.append(f"schema {doc.get('schema')!r} is not {SCHEMA}")
    if doc.get("arm") != arm:
        out.append(f"names arm {doc.get('arm')!r}, not {arm!r}")
    if not (isinstance(doc.get("snapshot_sha256"), str) and HEX64.match(doc["snapshot_sha256"])):
        out.append("snapshot_sha256 absent or malformed")
    if not (isinstance(doc.get("client_version"), str) and doc["client_version"]):
        out.append("client_version absent")
    checks = doc.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        out.append("checks are not exactly the spec 6 checks")
        return out
    bad = sorted(n for n, v in checks.items() if v not in STATUSES)
    if bad:
        return out + [f"unknown status for {bad}"]
    owed = doc.get("owed_by")
    if not isinstance(owed, dict) or set(owed) != {n for n, v in checks.items() if v == "OWED"}:
        out.append("owed_by does not name exactly the OWED checks")
    else:
        wrong = sorted(n for n in owed if n not in OWED_BY or owed[n] != OWED_BY[n])
        if wrong:
            out.append(f"OWED checks {wrong} are not the checks owed to an unbuilt service (or name another step)")
    if not isinstance(doc.get("details"), dict) or set(doc["details"]) != {n for n, v in checks.items() if v == "fail"}:
        out.append("details do not cover exactly the failed checks")
    if doc.get("verdict") != verdict_of(checks):
        out.append(f"verdict {doc.get('verdict')!r} contradicts the checks ({verdict_of(checks)!r})")
    if doc.get("sha256") != sha_of(doc):
        out.append("sha256 does not match the content (edited after it was written)")
    return out


def problems(path, *, arm, file_sha256_frozen, smoke, snapshot_sha256=None):
    """Why the chain must refuse the arm's artifact at `path` (a list; empty = accepted). `file_sha256_frozen` is the sha256 of
    the FILE recorded in `ChainConfig` / `chain.json`; any other bytes are drift (also a replacement mid-chain).
    Non-smoke accepts verdict `pass` only; smoke also accepts `incomplete`; `fail` is always refused. When the chain froze the
    arm's snapshot, the artifact must be of that snapshot."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        return [f"contract artifact of {arm} is missing or unreadable ({type(exc).__name__})"]
    if file_sha256(raw) != file_sha256_frozen:
        return [f"contract artifact of {arm} changed since the chain froze it (sha256 drift)"]
    try:
        doc = json.loads(raw)
    except ValueError:
        return [f"contract artifact of {arm} is not valid JSON"]
    why = [f"contract artifact of {arm}: {x}" for x in validate(doc, arm=arm)]
    if why:
        return why
    if snapshot_sha256 is not None and doc["snapshot_sha256"] != snapshot_sha256:
        why.append(f"contract artifact of {arm} is of another snapshot ({doc['snapshot_sha256'][:12]} != "
                   f"{snapshot_sha256[:12]})")
    if doc["verdict"] == "fail":
        failed = sorted(n for n, v in doc["checks"].items() if v == "fail")
        why.append(f"contract artifact of {arm} FAILED: {', '.join(failed)}")
    elif doc["verdict"] == "incomplete" and not smoke:
        owed = sorted(doc["owed_by"])
        why.append(f"contract artifact of {arm} is incomplete (OWED: {', '.join(owed)}); a non-smoke chain needs verdict pass")
    return why
