"""Normalizer for baseline results (stdlib only: copied into the bundle and imported by the current tree alike).

Removes what legitimately differs between two runs of the SAME scenario: wall clocks, durations, pids, UUIDs, run ids,
timestamps and temp paths. Run ids / UUIDs are renumbered by first appearance on ONE `Normalizer`, so a document keeps
its identity relations (the same id twice stays the same label). Keys whose value is machine-dependent but not
scenario-dependent are listed in `VOLATILE_KEYS` and replaced by the `VOLATILE` marker (type information is dropped)."""
from __future__ import annotations

import re

VOLATILE = "<volatile>"
# key names (any depth) whose value is a clock, duration, pid, host or machine fingerprint
VOLATILE_KEYS = frozenset({
    "wall_s", "started", "updated", "at", "probe_pid", "probe_create_time", "sampled_at_s", "silent_s",
    "inflight_s_at_stop", "inflight_s", "cancel_wait_s", "graceful_wait_s", "elapsed_s", "tmp_window", "started_at",
    "finished_at", "timestamp", "ts", "hostname", "opencode_exe_sha256", "prompt_date_real",
    "decode_tps", "tracker_s_observed",
})
# (ancestor key, key) pairs: a key is volatile only under that ancestor (real pids of killed processes, report hashes
# whose bytes embed a duration)
VOLATILE_UNDER = frozenset({("killed", "pid"), ("killed", "create_time"), ("killed", "argv"), ("artifacts", "sha256"),
                            ("mem_kills", "pid"), ("orphans_unattributed", "pid")})
RUN_ID = re.compile(r"\d{8}T\d{6}-[0-9a-f]{12}")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
STAMP = re.compile(r"\d{8}T\d{6}Z?")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")


class Normalizer:
    def __init__(self, tmp_roots=(), extra_volatile=(), roots=(), volatile_under=()):
        pairs = [(str(r).rstrip("/"), "$TMP") for r in tmp_roots if r] + [(str(p).rstrip("/"), t) for p, t in roots if p]
        self.roots = sorted(set(pairs), key=lambda pt: len(pt[0]), reverse=True)
        self.volatile = set(VOLATILE_KEYS) | set(extra_volatile)
        self.under = set(VOLATILE_UNDER) | set(volatile_under)
        self.run_ids, self.uuids = {}, {}

    # -- strings
    def text(self, s):
        for root, token in self.roots:
            s = s.replace(root, token)
        s = RUN_ID.sub(lambda m: "<run-%d>" % self.run_ids.setdefault(m.group(0), len(self.run_ids) + 1), s)
        s = UUID.sub(lambda m: "<uuid-%d>" % self.uuids.setdefault(m.group(0), len(self.uuids) + 1), s)
        s = ISO.sub("<ts>", s)
        s = STAMP.sub("<ts>", s)
        return s

    def apply(self, node, key=None, stack=()):
        if key is not None and (key in self.volatile or any((anc, key) in self.under for anc in stack)):
            return VOLATILE
        if isinstance(node, dict):
            inner = stack + (key,) if key is not None else stack
            return {self.text(k) if isinstance(k, str) else k: self.apply(v, k, inner) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            inner = stack + (key,) if key is not None else stack
            return [self.apply(v, None, inner) for v in node]
        if isinstance(node, str):
            return self.text(node)
        return node
