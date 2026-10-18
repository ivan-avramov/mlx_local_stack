"""P371 phase 2a test doubles: a NON-opencode adapter and a tiny corpus for driving the shared item core.

`NeutralArm` uses its own env var (`NEUTRAL_OVERLAY`), no carrier fields, no date-freeze receipts and no plugin names;
`NeutralCorpus` grades a one-file exercise without any grader. Together they prove the core knows no opencode name.
The scripted client is a `/bin/sh -c` one-liner that prints the gate's own event lines and writes the solution."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
from pathlib import Path

from bench import arm_adapter as aa
from bench import corpus as cp
from bench import token_turn_gate as tg
from bench.tests.test_token_turn_gate import event, usage

LABEL = "neutral-v1"
EVENTS = [event("step_start", "m1"), event("step_finish", "m1", tokens=usage(10, 100)),
          event("step_start", "m2"), event("step_finish", "m2", tokens=usage(10, 120))]
BASELINE = b"answer = 0\n"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class NeutralCorpus(cp.Corpus):
    corpus_id = "neutral"
    languages = ("fake",)

    def __init__(self, root):
        self.root = Path(root)
        self.sha = "7" * 40

    def load_universe(self, path=None):
        return {"items": {f"fake/{n}": {} for n in ("one", "two")}}, "u" * 64

    def items(self, lang):
        return ["fake/one", "fake/two"] if lang == "fake" else []

    @property
    def excluded(self):
        return frozenset()

    def source_root(self, lang):
        return self.root

    def source_sha(self):
        return self.sha

    def needs_docker(self, lang):
        return False

    def prepare(self, item, dest):
        dest = Path(dest)
        dest.mkdir(parents=True)
        (dest / "solution.txt").write_bytes(BASELINE)
        lang, name = item.split("/", 1)
        entry = dict(id=item, lang=lang, baseline_failing=1, leaves=[["t", "t", "t"]])
        return cp.PreparedItem(item_id=item, lang=lang, name=name, work=dest, entry=entry,
                               editable=("solution.txt",), baseline={"solution.txt": _sha(BASELINE)}, protected={},
                               prepared={"solution.txt": _sha(BASELINE)}, tests=("t",))

    def prompt(self, prepared, inject=None):
        return "set the answer to 42" + (" [inject:%s]" % inject if inject else "")

    def tampered(self, snap, prepared):
        return snap is None

    def grade(self, snap, prepared, private, guard, keep, seq, boundary, final):
        phase = dict(seq=seq, boundary=boundary, final=bool(final))
        if snap is None:
            return cp.GradeOutcome(failing=None, leaves=(), tampered=True, outcome="model",
                                   resources=dict(grader_mem_kill=False, grader_oom=False),
                                   phases=(dict(phase, outcome="tampered"),))
        done = b"42" in (Path(snap.path) / "solution.txt").read_bytes()
        return cp.GradeOutcome(failing=0 if done else 1, leaves=(("t", "t", "t"),) if done else (), tampered=False,
                               outcome="model", resources=dict(grader_mem_kill=False, grader_oom=False),
                               phases=(dict(phase, outcome="graded"),))

    def changed(self, prepared):
        return _sha((prepared.work / "solution.txt").read_bytes()) != prepared.baseline["solution.txt"]

    def final_tree(self, prepared, dest):
        dest = Path(dest)
        (dest / "objects").mkdir(parents=True)
        data = (prepared.work / "solution.txt").read_bytes()
        (dest / "objects" / _sha(data)).write_bytes(data)
        raw = json.dumps(dict(files={"solution.txt": _sha(data)}, missing=[]), sort_keys=True).encode()
        (dest / "manifest.json").write_bytes(raw)
        return cp.FinalTree(root=dest, files={"solution.txt": _sha(data)}, missing=(),
                            manifest_sha256=_sha(raw), manifest_path=dest / "manifest.json")

    def identity(self):
        return dict(corpus_id=self.corpus_id, universe_sha256="u" * 64, grader_version="neutral-grade-1",
                    grader_timeout_s=dict(fake=5), image=None)


class NeutralArm(aa.ArmAdapter):
    arm_id = "dsh"
    tool = "neutralclient"
    label = LABEL
    GENERATION_FIELDS = ("probe_code_sha256", "scaffold_policy_sha256", "neutral_version", "neutral_exe_sha256",
                         "neutral_config_sha256", "polyglot_sha", "sampling_profile")
    native_client_cuts = ()
    removed_tools = ()
    pinned_version = "1.0"
    date_receipt_key = None

    def __init__(self, p=None, *, workdir=None):
        self.p = p
        self.workdir = workdir
        self.binary_path = "/bin/sh"

    # identity / provenance
    def snapshot(self):
        return aa.Snapshot(tool=self.tool, fields=dict(label=self.label, version="1.0"), complete=True)

    def identity(self, *, selection, universe_sha, version, binary, inject=None, inject_addendum_sha256=None):
        label = self.label + "-inject:" + inject if inject else self.label
        policy = dict(
            gate=dict(tg.POLICY), hygiene=dict(__import__("bench.proc_guard", fromlist=["POLICY"]).POLICY),
            toolbounds_sha256="a" * 64, noretry_sha256="b" * 64, datefreeze_sha256="c" * 64,
            carrier_sha256=selection["fields"]["neutral_config_sha256"], universe_sha256=universe_sha,
            grader_version="neutral-grade-1", grader_timeout_s=dict(fake=5), grade_join_timeout_s=70,
            plugin_proof="none", env={"TERM": "dumb"}, scaffold=label,
            toolchain=__import__("bench.toolchain", fromlist=["current"]).current())
        if inject:
            policy["inject"] = dict(kind=inject, prompt_addendum_sha256="d" * 64)
        return dict(scaffold=label, policy=policy, probe_code_sha256="e" * 64, neutral_version=version,
                    neutral_exe_sha256="f" * 64,
                    scaffold_policy_sha256=hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest())

    def manifest_fields(self):
        return dict(arm=self.arm_id, tool=self.tool, label=self.label)

    def row_fields(self, *, version, rc, artifacts, sha_of, portable):
        return dict(neutral_version=version, neutral_rc=rc, events_path=portable(artifacts["events"]),
                    transcript_path=portable(artifacts["export"]), stderr_path=portable(artifacts["stderr"]),
                    evidence_sha256={k: sha_of(v) for k, v in artifacts.items()})

    # run construction
    def selection(self, system_file=None):
        return dict(bytes=b"{}", source=None, system_path=None,
                    fields=dict(scaffold=self.label, neutral_config_sha256="9" * 64))

    def declared_model(self, selection, model):
        return dict(body=dict(thinking_budget=81920, max_tokens=102400), limit=dict(context=262144)), \
            "http://127.0.0.1:1/v1"

    def require_binary(self):
        return self.binary_path

    def preflight(self, *, selection, path=None, router=None, limit=None, model=None, exe_sha=None):
        return None

    def make_run_dir(self, workdir, run_id, selection):
        run_dir = Path(workdir) / "neutral-runs" / run_id
        run_dir.mkdir(parents=True)
        return run_dir

    def seed_overlay(self, model, seed):
        return {"neutral_seed": int(seed), "model": model}

    def overlay_sha(self, env):
        return hashlib.sha256(env["NEUTRAL_OVERLAY"].encode()).hexdigest()

    def build_env(self, run_dir, scratch, overlay, *, receipts, frozen_date):
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TMPDIR": str(Path(run_dir).parent / "tmp" /
                                                                               Path(scratch).name) + "/",
                "NEUTRAL_OVERLAY": json.dumps(overlay, sort_keys=True), "PWD": str(scratch)}

    def verify_env(self, env, run_dir, selection, overlay):
        if env.get("NEUTRAL_OVERLAY") != json.dumps(overlay, sort_keys=True):
            raise tg.TransportAbort("neutral env drift")

    def discover(self, scratch, env, *, model=None, run_dir=None, binary=None, overlay=None, runner=None,
                 check_version=False):
        return "1.0", "http://127.0.0.1:1/v1"

    def command(self, binary, model, prompt):
        lines = "".join(json.dumps(e) + "\n" for e in EVENTS)
        return [binary, "-c", "printf %s " + shlex.quote(lines) + "; echo 'answer = 42' > solution.txt"]

    def evidence_suffixes(self):
        return {"events": ".events.jsonl", "stderr": ".stderr.txt", "export": ".json"}

    def guard_roots(self, work, env, private):
        return [work, env["TMPDIR"], private]

    # stream, transcript, reconciliation
    def new_stream(self, gate, on_complete):
        return tg.EventStream(gate, on_complete)

    def events(self, stream):
        return []

    def transcript(self, guard, env, work, stream, binary, raw_sink=None):
        messages = [dict(id=mid, type="assistant", finish="stop",
                         tokens=dict(output=10, reasoning=0, input=100 + 20 * i, cache=dict(read=0, write=0)))
                    for i, mid in enumerate(stream.starts)]
        raw = json.dumps(dict(info=dict(id="s1"), messages=messages))
        if raw_sink is not None:
            raw_sink(raw)
        return aa.Transcript(raw=raw, doc=json.loads(raw))

    def final_boundary(self, transcript):
        return len(transcript.doc["messages"])

    def reconcile(self, stream, transcript, receipts, rc, outcome):
        summary = tg.reconcile(stream, transcript.doc, rc, outcome)
        return aa.Reconciliation(outcome=outcome, unmatched_export_messages=summary["unmatched_export_messages"],
                                 trailing=summary["trailing"], uncharged_trailing=summary["uncharged_trailing"])

    def web_evidence(self, transcript, env):
        return []

    def tool_windows(self, stream):
        return []

    def tmp_escapes(self, transcript, env):
        return []

    def receipts_reconcile(self, paths, **kw):
        return {}

    def evidence_root(self, workdir):
        return Path(workdir) / "neutral_evidence"

    def row_identity_fields(self):
        return dict(bench="neutral", schema_version=3)

    def metrics(self, p, transcript, export):
        return dict(neutral_metric=1)

    def identity_binary(self):
        return Path(self.binary_path), True

    def identity_summary(self, ident, binary_exists):
        return dict(neutral_version=ident["neutral_version"])
