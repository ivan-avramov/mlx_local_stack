"""Test doubles for the ArmAdapter contract (no client): the smallest conforming adapter."""
from __future__ import annotations

from bench import arm_adapter as aa


class MinimalAdapter(aa.ArmAdapter):
    """The smallest conforming adapter: every abstract member present."""
    arm_id = "oc"
    tool = "opencode"
    label = "min-label"
    GENERATION_FIELDS = ("probe_code_sha256", "scaffold_policy_sha256")
    native_client_cuts = ()
    removed_tools = ("subagent",)

    def snapshot(self):
        return aa.Snapshot(tool="opencode", fields={"version": "1"}, complete=True)

    def selection(self, system_file=None):
        return {}

    def declared_model(self, selection, model):
        return {}, ""

    def require_binary(self):
        return "/x"

    def preflight(self, *, selection, path=None, router=None, limit=None, model=None, exe_sha=None):
        return None

    def seed_overlay(self, model, seed, *, attempt=None):
        return {}

    def overlay_sha(self, env):
        return "0" * 64

    def make_run_dir(self, workdir, run_id, selection):
        return workdir

    def build_env(self, run_dir, scratch, overlay, *, receipts, frozen_date, toolwindow_receipts=None, attempt=None):
        return {}

    def verify_env(self, env, run_dir, selection, overlay):
        return None

    def discover(self, scratch, env, **kw):
        return "1"

    def identity(self, **kw):
        return {}

    def command(self, binary, model, prompt):
        return [binary]

    def evidence_suffixes(self):
        return {"events": ".events.jsonl"}

    def guard_roots(self, work, env, private):
        return [work]

    def new_stream(self, gate, on_complete):
        return object()

    def events(self, stream):
        return []

    def transcript(self, guard, env, work, stream, binary, raw_sink=None):
        return aa.Transcript(raw="", doc={})

    def final_boundary(self, transcript):
        return 0

    def reconcile(self, stream, transcript, receipts, rc, outcome):
        return aa.Reconciliation(outcome=None)

    def manifest_fields(self):
        return {"arm": self.arm_id}

    def row_fields(self, **kw):
        return {}

    def tool_windows(self, stream, final=False):
        return []

    def tmp_escapes(self, transcript, env):
        return []

    def receipts_reconcile(self, paths, **kw):
        return {}

    def evidence_root(self, workdir):
        return workdir

    def row_identity_fields(self):
        return {}

    def metrics(self, p, transcript, export):
        return {}

    def identity_binary(self):
        return "/x", False

    def identity_summary(self, ident, binary_exists):
        return {}
