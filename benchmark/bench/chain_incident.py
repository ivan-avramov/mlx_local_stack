"""P371 phase 3b (plan 4 A6, A7; M64 spec 8.3): the PURE parts of the `incident_retry` transport policy of the shared chain core
(`chain_core`): incident classification, the exact cleanup-receipt schema, slot keys, the synthetic `transport_dnf` row and the
per-slot token count of failed attempts. No process, client or adapter import.

A transport INCIDENT is a failed invocation the chain retries: the router and the worker are checked INDEPENDENTLY first
(worker gone / replaced -> `worker_crash`, router gone / replaced -> `router_error`), then the client's own cause (the probe's
abort stamp), then an idle-cancelled (hung) probe is a `client_timeout`; no cause -> not transport (None). A retry requires the
EXACT `proc_guard.ProcessGuard.status()` schema with a certain, completed, empty cleanup (A7)."""
from __future__ import annotations

from . import chain_ops as co

INCIDENT_CAUSES = ("server_error", "connection", "dropped_stream", "timeout", "client_timeout", "worker_crash",
                   "router_error")
CLEANUP_KEYS = ("survivors", "containers_remaining", "uncertain", "orphans_unattributed", "unknown", "completed")
CLEANUP_LISTS = ("survivors", "containers_remaining", "orphans_unattributed", "unknown")
MAX_INCIDENTS = 2                      # the second incident of a slot is a `transport_dnf` row (spec 8.3)


def classify_incident_cause(*, stamp_cause, cancelled_idle, worker_ok, router_ok):
    """The incident cause, or None when the failure is not transport (A6)."""
    if stamp_cause == "worker_crash" or not worker_ok:
        return "worker_crash"
    if not router_ok:
        return "router_error"
    if stamp_cause in INCIDENT_CAUSES:
        return stamp_cause
    if cancelled_idle:
        return "client_timeout"
    return None


def cleanup_problems(receipt):
    """Reasons a probe's cleanup receipt is not the exact certain / completed / empty `ProcessGuard.status()` (A7); [] = ok."""
    if not isinstance(receipt, dict):
        return ["no cleanup receipt recorded"]
    why = []
    keys = set(receipt)
    if keys != set(CLEANUP_KEYS):
        extra, missing = sorted(keys - set(CLEANUP_KEYS)), sorted(set(CLEANUP_KEYS) - keys)
        why.append(f"cleanup receipt is not the exact schema (extra {extra}, missing {missing})")
    for name in CLEANUP_LISTS:
        if name in receipt and (not isinstance(receipt[name], list) or receipt[name]):
            why.append(f"cleanup {name} is not an empty list")
    if "uncertain" in receipt and receipt["uncertain"] is not False:
        why.append("cleanup uncertain flag is not false")
    if "completed" in receipt and receipt["completed"] is not True:
        why.append("cleanup did not complete")
    return why


def slot_key(epoch, arm, pick, session, lang, item):
    """Slot identity (spec 8.3): (epoch, arm, pick, session, language, item)."""
    return "|".join((epoch, arm, pick, session, lang, item))


def incident_tokens(stamp):
    """`(tokens, gate_tokens, receipt_tokens)` of a failed attempt from the probe's abort stamp: the fenced worker receipts'
    completion tokens are the better count when the probe took the fence, else what the client's gate saw."""
    gate = ((stamp or {}).get("gate") or {}).get("output_tokens_completed") or 0
    rec = (stamp or {}).get("receipts")
    taken = isinstance(rec, dict) and rec.get("fence_taken") is True and isinstance(rec.get("completion_tokens"), int)
    receipts = rec["completion_tokens"] if taken else None
    return (receipts if receipts is not None else gate), gate, receipts


def slot_tokens(chain_doc, slot):
    """Output tokens the FAILED attempts of one slot already spent (they count toward that task, spec 8.3): its incidents
    plus its cheat attempts (re-run, P201), never the scored attempt."""
    total = sum(i.get("output_tokens") or 0 for i in chain_doc.get("incidents", []) if i.get("slot") == slot)
    for a in (chain_doc.get("progress") or {}).get("slot_attempts", []):
        if a.get("slot") == slot and a.get("disposition") == "cheat" and a.get("status") != "archived":
            total += a.get("output_tokens") or 0
    return total


def dnf_row(*, slot, arm, label, pick, session, lang, item, seed_base, incidents, worker, frozen, epoch, runtime):
    """The synthetic strict-fail row of a slot that failed on transport twice (spec 8.3). A row of the probe's rows schema
    where it has meaning; no evidence files exist, so it is a sidecar record, never a probe rows file entry."""
    from . import rowschema
    seed = rowschema.sample_seed(f"{lang}/{item}", 0, seed_base)
    return {
        "id": f"{lang}/{item}", "model": pick, "sample": 0, "sampler_seed": seed, "passed": False, "acc": 0,
        "converged": False, "nonconv_kind": "transport_dnf", "nonconv_flags": ["transport_dnf"], "synthetic": True,
        "slot": slot, "arm": arm, "scaffold": label, "epoch_id": epoch, "prompt_date": frozen,
        "overlay_sha256": co.seed_overlay_sha(pick, seed), "incidents": list(incidents),
        "failed_attempt_output_tokens": sum(i.get("output_tokens") or 0 for i in incidents),
        "worker_after": worker, "generation_identity_sha256": runtime.get("generation_identity_sha256"),
        "arm_identity_sha256": runtime.get("arm_identity_sha256"),
    }


def validate_dnf_row(row, *, arm, slot):
    """Reasons a transport_dnf row is not what spec 8.3 describes (empty: valid)."""
    why = []
    if row.get("nonconv_kind") != "transport_dnf" or row.get("synthetic") is not True or row.get("passed") is not False:
        why.append("dnf_shape: not a synthetic strict-fail transport_dnf row")
    if row.get("arm") != arm or row.get("slot") != slot:
        why.append("dnf_slot: arm or slot differs")
    inc = row.get("incidents")
    if not (isinstance(inc, list) and len(inc) == MAX_INCIDENTS and all(i.get("slot") == slot for i in inc)
            and [i.get("attempt") for i in inc] == [1, 2]):
        why.append("dnf_incidents: a transport_dnf row carries exactly the two incidents of its slot")
    return why
