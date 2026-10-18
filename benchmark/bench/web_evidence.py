"""P371 (plan 4 A12): chain-side extraction of RAW web evidence from the hashed transcript the probe stored.

`extract(rules, transcript_path, transcript_sha256, dest)` re-verifies the transcript's sha256 FIRST (a mismatch
raises and nothing is written), then writes `<dest>` (JSONL, one record per web-capable or shell tool call:
`{request, tool, id, status, input, output}`, `output` = the content the tool returned to the model: fetch body,
search result, shell command output, or None when the call never returned) and returns `{path, sha256, count}`.
Classification (fetch vs search vs networking) is scoring's job, not this module's. No transcript, or an export that
cannot be read, yields `unavailable(reason)` (P201: unauditable, never "no contact").

The per-arm extraction rules are DATA: `ArmSpec.web_evidence_rules` (`bench.arm_specs`; `OPENCODE_RULES` is the oc
spec's dict), so a second client is a rules dict, not code. Only the chain imports this module; a probe closure never does."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import arm_specs
from . import token_turn_gate as tg

RULES_SCHEMA = 1
OPENCODE_RULES = arm_specs.OC.web_evidence_rules       # the data lives in the arm spec (R30); kept here as an alias
_RULE_KEYS = tuple(OPENCODE_RULES)


class WebEvidenceError(tg.TransportAbort):
    """The evidence file cannot be written (it already exists: evidence is immutable)."""


class TranscriptShaMismatch(tg.TransportAbort):
    """The stored transcript no longer hashes to the recorded sha256."""


def validate_rules(rules):
    if not isinstance(rules, dict) or rules.get("schema") != RULES_SCHEMA or any(k not in rules for k in _RULE_KEYS):
        raise ValueError(f"web evidence rules must be a schema {RULES_SCHEMA} dict with keys {_RULE_KEYS}")
    return rules


def unavailable(reason):
    if not (isinstance(reason, str) and reason):
        raise ValueError("an unavailable record needs a reason")
    return dict(web_evidence="unavailable", reason=reason)


def _dig(value, path):
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _selected(rules, part):
    if not isinstance(part, dict) or part.get(rules["part_type_field"]) != rules["part_type"]:
        return False
    name = part.get(rules["name_field"])
    return name in rules["tool_names"] or any(s in str(name) for s in rules["name_contains"])


def _records(rules, doc):
    request = 0
    for message in doc.get(rules["messages"]) or []:
        if not isinstance(message, dict) or message.get(rules["message_role_field"]) != rules["message_role"]:
            continue
        request += 1
        for part in message.get(rules["parts"]) or []:
            if not _selected(rules, part):
                continue
            output = None
            for path in rules["output_paths"]:
                output = _dig(part, path)
                if output is not None:
                    break
            yield dict(request=request, tool=part.get(rules["name_field"]), id=part.get(rules["id_field"]),
                       status=_dig(part, rules["status_path"]), input=_dig(part, rules["input_path"]), output=output)


def extract(rules, transcript_path, transcript_sha256, dest):
    validate_rules(rules)
    if transcript_path is None:
        return unavailable("no transcript")
    path = Path(transcript_path)
    try:
        raw = path.read_bytes()
    except OSError:
        return unavailable("transcript file missing")
    if hashlib.sha256(raw).hexdigest() != transcript_sha256:
        raise TranscriptShaMismatch(f"transcript {path.name} differs from its recorded sha256")
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError("not an object")
    except ValueError:
        return unavailable("transcript unreadable (export failed or malformed)")
    body = b"".join((json.dumps(r, sort_keys=True) + "\n").encode() for r in _records(rules, doc))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise WebEvidenceError("web evidence is immutable: " + dest.name + " exists") from None
    with os.fdopen(fd, "wb") as fp:
        fp.write(body)
        fp.flush()
        os.fsync(fp.fileno())
    return dict(path=str(dest), sha256=hashlib.sha256(body).hexdigest(), count=body.count(b"\n"))
