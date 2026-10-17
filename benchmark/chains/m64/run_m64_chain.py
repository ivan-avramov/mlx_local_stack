"""M64 chain runner (spec docs/specs/m64-scaffold-arms.md sections 4, 8): the C147 chain, arm-aware.

  run_m64_chain.py chain [s1 s2 reload] --arms oc[,pi,dsh] --probe-code-sha oc=<sha> ... --epoch-id <sha> [--smoke]

It extends `run_tg1_chain.Chain` (supervision, barrier, idle predicate, escalation, STOP and the watch log are reused as
they are) and changes what the spec changes:

* the unit is a LEG = (block of <= 3 items, arm); one worker load serves a (session, pick) with all its arms; the schedule
  (seeded order, balanced arm permutations, reload control) is `bench.m64_schedule`, hashed into `schedule.json` before
  launch and checked against the realized order at the end;
* identities: `chain.json` freezes `epoch_id`, `arm_id -> generation_identity_sha256` (frozen at the arm's first manifest),
  one worker identity per (model, predictor) shared by every arm, and a pinned set per arm; entry (barrier), every leg and
  exit verify them; the arm's probe, label and pinned fields come from `bench.arm_specs`;
* stems `{model}.{session}.{arm}_{lang}`, evidence roots `transcripts/<arm>`, A4 per arm label, out-root
  `$STACK_WORKDIR/m64[-smoke]` (P340: always explicit and absolute);
* per leg: restart the search service; per arm switch: cache-session reset + one unscored warm-up (`bench.arm_ops` hooks,
  refusing for the real ops until the D2 service and the fork control endpoint exist);
* transport incidents (8.3): a leg whose probe aborts with a transport cause is an INCIDENT, not a score: record it (slot,
  attempt, cause, the failed attempt's tokens), recover (unload + reload the worker, new identity recorded, cache reset,
  warm-up), re-run the same slot in a NEW rows segment (`<stem>.w<n>.jsonl`: the probe keeps one worker instance per rows
  file); a second incident in the same slot writes a synthetic strict-fail row `nonconv_kind: transport_dnf` with both
  incidents to the sidecar `<stem>.dnf.jsonl` and the schedule continues. Anything else that fails is not retried: the
  load is archived and restarted once, then the chain aborts.

Exit codes as the base chain: 0 done, 2 chain abort, 3 STOP latch honoured, 1 unexpected error."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))
sys.path.insert(0, str(REPO / "benchmark/chains/c147"))
import run_tg1_chain as base  # noqa: E402
from bench import arm_adapter as aa  # noqa: E402
from bench import arm_specs  # noqa: E402
from bench import chain_ops as co  # noqa: E402
from bench import datefreeze  # noqa: E402
from bench import m64_schedule as ms  # noqa: E402

Timers, RecordInvalid, Stopped, Refused = base.Timers, base.RecordInvalid, base.Stopped, base.Refused
INCIDENT_CAUSES = ("server_error", "connection", "dropped_stream", "timeout", "client_timeout", "worker_crash",
                   "router_error")
LIFECYCLE = {"runner": "benchmark/chains/m64/run_m64_chain.py", "base_runner": "benchmark/chains/c147/run_tg1_chain.py",
             "chain_ops": "benchmark/bench/chain_ops.py", "schedule": "benchmark/bench/m64_schedule.py",
             "arm_specs": "benchmark/bench/arm_specs.py", "arm_ops": "benchmark/bench/arm_ops.py",
             "gate": "scripts/session_pinning_gate.py"}
STATE_KEYS = ("incidents", "dnf", "slot_attempts", "completed_loads", "realized")


class LoadIncomplete(Exception):
    """A leg ended in a way that is neither a validated leg nor a transport incident (the load is archived once)."""


def lifecycle_files(repo):
    return {name: Path(repo) / rel for name, rel in LIFECYCLE.items()}


def slot_key(epoch, arm, pick, session, lang, item):
    """Slot identity (spec 8.3): (epoch, arm, pick, session, language, item)."""
    return "|".join((epoch, arm, pick, session, lang, item))


def stem_of(leg):
    return f"{leg['pick']}.{leg['session']}.{leg['arm']}_{leg['lang']}"


def build_cmd(py, probe, leg, names, expect_ids, out, label, receipt, cancel, ack, *, universe=None, frozen=None,
              epoch=None):
    cmd = [str(py), str(probe), "--model", leg["pick"], "--items", ",".join(names), "--lang", leg["lang"],
           "--seed-base", str(leg["seed_base"]), "--out", str(out), "--scaffold", label,
           "--expect-items", ",".join(expect_ids), "--a4-v2-receipt", str(receipt), "--sampling-profile", "deployed",
           "--cancel-file", str(cancel), "--manifest-ack", str(ack)]
    if universe:
        cmd += ["--universe", str(universe)]
    if frozen:
        cmd += ["--frozen-prompt-date", frozen]
    if epoch:
        cmd += ["--epoch-id", epoch]
    return cmd


def slot_tokens(chain_doc, slot):
    """Output tokens the failed attempts of one slot already spent (they count toward that task, spec 8.3)."""
    return sum(i.get("output_tokens") or 0 for i in chain_doc.get("incidents", []) if i.get("slot") == slot)


def dnf_row(*, slot, arm, label, pick, session, lang, item, seed_base, incidents, worker, frozen, epoch, runtime):
    """The synthetic strict-fail row of a slot that failed on transport twice (spec 8.3). A row of the probe's rows
    schema where it has meaning; no evidence files exist, so it is a sidecar record, never a probe rows file entry."""
    from bench import rowschema
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
    if not (isinstance(inc, list) and len(inc) == 2 and all(i.get("slot") == slot for i in inc)
            and [i.get("attempt") for i in inc] == [1, 2]):
        why.append("dnf_incidents: a transport_dnf row carries exactly the two incidents of its slot")
    return why


# --------------------------------------------------------------------------- the chain
class ArmChain(base.Chain):
    def __init__(self, args, ops, timers, log, names, out_root, lifecycle_files_=None):
        self.a, self.ops, self.tm, self.log = args, ops, timers, log
        self.lifecycle_files = dict(lifecycle_files_) if lifecycle_files_ else lifecycle_files(REPO)
        self.lifecycle = None
        self.arms = {}                         # "<model>|<predictor>" -> worker arm_identity_sha256 (shared by every arm)
        self.out_root, self.stop_path = Path(out_root), Path(out_root) / "STOP"
        self.names = names
        self.clock = time.monotonic
        self.py = Path(args.python)
        self.arm_ids = list(args.arms)
        self.specs = {}
        self.epoch_id = args.epoch_id
        self.policies = {}                     # arm -> scaffold_policy_sha256 derived from the arm's probe
        self.arm_gen = {}                      # arm -> generation_identity_sha256, frozen at the arm's first manifest
        self.pinned_by_arm = {arm: {"probe_code_sha256": args.probe_code_sha[arm]} for arm in self.arm_ids}
        self.pinned_shared = {}                # serving_path, registry_sha256 (one router, one registry)
        self.universe = Path(args.universe).resolve() if args.universe else None
        self.frozen = None
        self.frozen_source = None
        self.attempts, self.restarts, self.stop_info = [], [], None
        self.attempt_no, self.seen_run_ids, self.block_workers = {}, set(), []
        self.loaded = None
        self.rc = None
        self.pred, self.explicit_pred = dict(base.PRED_S), {}
        for spec in args.pred_s or []:
            key, val = spec.rsplit("=", 1)
            lang, model = key.split(":", 1)
            self.explicit_pred[(lang, model)] = float(val)
        self.schedule = None
        self.schedule_sha = None
        self.incidents, self.dnf, self.slot_attempts = [], [], {}
        self.completed_loads, self.realized = [], []

    # -- spec lookup (refuses an arm that has no adapter before anything starts)
    def resolve_specs(self):
        for arm in self.arm_ids:
            self.specs[arm] = arm_specs.spec_for(arm)

    def probe_of(self, arm):
        given = (self.a.probe or {}).get(arm)
        return Path(given) if given else REPO / self.specs[arm].probe

    # -- the chain.json record
    @staticmethod
    def record_problem(doc):
        hexed = lambda v: isinstance(v, str) and bool(co.HEX64.match(v))      # noqa: E731
        if not isinstance(doc, dict):
            return "not a JSON object"
        lc = doc.get("lifecycle")
        if not (isinstance(lc, dict) and lc and all(hexed(v) for v in lc.values())):
            return "lifecycle absent or incomplete"
        for key in ("arms", "arm_generations", "policies", "pinned"):
            if not isinstance(doc.get(key), dict):
                return f"{key} absent or malformed"
        if not all(hexed(v) for v in {**doc["arms"], **doc["arm_generations"], **doc["policies"]}.values()):
            return "an identity is absent, null or malformed"
        if not hexed(doc.get("epoch_id")) or not hexed(doc.get("schedule_sha256")):
            return "epoch_id or schedule_sha256 absent or malformed"
        if not datefreeze.valid(doc.get("frozen_prompt_date")):
            return "frozen_prompt_date absent or malformed"
        for key in STATE_KEYS:
            if key not in doc:
                return f"{key} absent"
        return None

    def init_lifecycle(self):
        path = self.out_root / "chain.json"
        if path.exists():
            try:
                previous = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                raise RecordInvalid(f"existing chain.json unreadable ({type(exc).__name__}); use a new out-root")
            problem = self.record_problem(previous)
            if problem:
                raise RecordInvalid(f"existing chain.json is not a complete valid record ({problem}); use a new out-root")
            if previous["epoch_id"] != self.epoch_id:
                raise RecordInvalid(f"epoch {self.epoch_id} differs from the chain's frozen epoch {previous['epoch_id']} "
                                    "(a changed chain needs a new out-root)")
            if sorted(previous["policies"]) != sorted(self.arm_ids):
                raise RecordInvalid("the arms differ from the chain's frozen arms (a changed chain needs a new out-root)")
            self.lifecycle = previous["lifecycle"]
            self.arms = dict(previous["arms"])
            self.arm_gen = dict(previous["arm_generations"])
            self.policies = dict(previous["policies"])
            for arm, pinned in previous["pinned"].items():
                if arm == "shared":
                    self.pinned_shared = dict(pinned)
                elif arm in self.pinned_by_arm:
                    self.pinned_by_arm[arm].update(pinned)
            self.schedule_sha = previous["schedule_sha256"]
            for key in STATE_KEYS:
                setattr(self, key, previous[key])
            self.resolve_frozen(previous)
            self.verify_lifecycle("resume")
            return
        self.resolve_frozen(None)
        fresh = co.lifecycle_shas(self.lifecycle_files)
        if any(v is None for v in fresh.values()):
            raise co.ChainAbort("lifecycle file unreadable at chain creation: "
                                + ", ".join(k for k, v in fresh.items() if v is None))
        self.lifecycle = fresh

    def derive_policy(self):
        """Per arm: the expected scaffold_policy_sha256 is what the arm's probe reports for THIS box (P362)."""
        for arm in self.arm_ids:
            probe = self.probe_of(arm)
            cmd = [str(self.py), str(probe), "--print-identity", "--scaffold", self.specs[arm].label]
            if self.universe:
                cmd += ["--universe", str(self.universe)]
            try:
                got = subprocess.run(cmd, cwd=str(REPO), env=self.ops.env_base(), capture_output=True, text=True,
                                     timeout=300, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise co.ChainAbort(f"{arm}: probe --print-identity could not run ({type(exc).__name__})") from None
            lines = [ln for ln in got.stdout.splitlines() if ln.strip()]
            try:
                value = json.loads(lines[-1]).get("scaffold_policy_sha256") if got.returncode == 0 and lines else None
            except (ValueError, AttributeError):
                value = None
            if not (isinstance(value, str) and co.HEX64.match(value)):
                raise co.ChainAbort(f"{arm}: probe --print-identity gave no valid scaffold_policy_sha256 "
                                    f"(rc {got.returncode}: {(got.stderr or got.stdout)[-200:].strip()})")
            asserted = (self.a.policy_sha or {}).get(arm)
            if asserted and asserted != value:
                raise co.ChainAbort(f"{arm}: supplied --policy-sha {asserted} != the probe's policy {value}")
            if self.policies.get(arm) and self.policies[arm] != value:
                raise co.ChainAbort(f"{arm}: frozen policy {self.policies[arm]} != the probe's policy now {value}")
            self.policies[arm] = value
            self.pinned_by_arm[arm]["scaffold_policy_sha256"] = value
            self.log(f"policy[{arm}]: scaffold_policy_sha256 {value} derived from the probe's --print-identity")

    def write_json(self, status=None):
        lc = self.lifecycle or {}
        doc = dict(status=status, mode=self.a.mode, argv=sys.argv[1:], updated=co.utc_stamp(),
                   sha256=dict(runner=lc.get("runner"), chain_ops=lc.get("chain_ops"), gate=lc.get("gate"),
                               overlay=self.ops.overlay_sha()),
                   lifecycle=self.lifecycle, arms=self.arms, arm_generations=self.arm_gen, policies=self.policies,
                   epoch_id=self.epoch_id, schedule_sha256=self.schedule_sha, arm_ids=self.arm_ids,
                   frozen_prompt_date=self.frozen, frozen_prompt_date_source=self.frozen_source,
                   probe_code_sha=self.a.probe_code_sha, pinned={**self.pinned_by_arm, "shared": self.pinned_shared},
                   attempts=self.attempts, restarts=self.restarts, stop=self.stop_info, rc=self.rc,
                   block_workers=self.block_workers, smoke=getattr(self.a, "smoke", False),
                   incidents=self.incidents, dnf=self.dnf, slot_attempts=self.slot_attempts,
                   completed_loads=self.completed_loads, realized=self.realized)
        co.atomic_json(self.out_root / "chain.json", doc)

    # -- run
    def run(self):
        try:
            self.resolve_specs()
        except aa.ArmRefused as e:
            self.log(f"CHAIN ABORT: {e}")
            self.rc = 2
            return 2
        try:
            self.init_lifecycle()
        except RecordInvalid as e:
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
            return self.rc
        except co.ChainAbort as e:
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
            self.write_json("aborted")
            return self.rc
        try:
            self.derive_policy()
        except co.ChainAbort as e:
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
            return self.rc
        self.write_json("starting")
        if self.stop_requested():
            self.stop_info["where"] = "start"
            self.log("STOP present at start: nothing launched")
            self.rc = 3
            return 3
        try:
            self.ops.ensure_overlay()
            self.pinned_shared["registry_sha256"] = self.ops.overlay_sha()
            if not self.ops.power_ok():
                raise co.ChainAbort("power gate FAIL")
            self.freeze_schedule()
            if any(leg["lang"] == "go" for leg in ms.legs(self.schedule)) and not self.ops.docker_ok():
                raise co.ChainAbort("docker gate FAIL: Go grading needs a reachable docker daemon")
            self.ops.require_arm_ops()
            self.ops.start_router()
            self.log(f"START chain arms={self.arm_ids} epoch={self.epoch_id[:12]} loads="
                     f"{[(l['session'], l['pick']) for l in self.schedule['loads']]}")
            try:
                for idx, load in enumerate(self.schedule["loads"]):
                    if idx in self.completed_loads:
                        continue
                    self.run_load(idx, load)
                if self.loaded and not self.ops.unload(self.loaded):
                    raise co.ChainAbort("final unload failed")
                self.loaded = None
                try:
                    ms.check_realized(self.schedule, self.realized)
                except ValueError as exc:
                    raise co.ChainAbort(str(exc)) from None
                self.verify_lifecycle("exit")
                self.rc = 0
                self.log("ALL LEGS DONE")
            except Stopped as s:
                self.stop_info["where"] = self.stop_info.get("where") or str(s)
                self.log(f"STOP honoured at {self.stop_info['where']}: exit 3")
                self.rc = 3
        except co.ChainAbort as e:
            self.log(f"CHAIN ABORT: {e}")
            self.rc = e.code
        finally:
            self.write_json("finished")
            try:
                self.ops.stop_stack()
            finally:
                self.write_json("finished")
        return self.rc

    def freeze_schedule(self):
        """Hash the schedule BEFORE launch; a resumed chain must regenerate exactly the frozen one."""
        schedule = ms.build(self.arm_ids, self.names, sessions=[s for s in self.a.sessions if s != "reload"],
                            reload_control="reload" in self.a.sessions, smoke=getattr(self.a, "smoke", False))
        path = self.out_root / "schedule.json"
        if self.schedule_sha is not None:
            try:
                ms.require_frozen(schedule, self.schedule_sha)
            except ValueError as exc:
                raise co.ChainAbort(str(exc)) from None
        else:
            self.schedule_sha = ms.schedule_sha256(schedule)
            co.atomic_json(path, schedule)
        self.schedule = schedule
        self.write_json("schedule-frozen")

    # -- loads
    def session_dir(self, load):
        return self.out_root / load["session"]

    def run_load(self, idx, load):
        ctx = dict(idx=idx, session=load["session"], model=load["pick"], seed_base=load["seed_base"], segment=0,
                   last_arm=None, receipts={}, legs=[leg for leg in ms.legs(self.schedule) if leg["load"] == idx])
        restarted = False
        while True:
            self.prepare(ctx, restarted)
            try:
                done = self.execute_load(ctx)
            except LoadIncomplete as exc:
                self.log(f"LOAD INCOMPLETE {ctx['session']}/{ctx['model']}: {exc}")
                done = False
            if done:
                self.completed_loads.append(idx)
                self.write_json("load-done")
                return
            if restarted:
                raise co.ChainAbort(f"load {ctx['session']}/{ctx['model']} incomplete twice")
            dest = self.archive_load(ctx)
            ctx.update(segment=0, last_arm=None)
            self.realized = [r for r in self.realized if r[0] != idx]
            restarted = True
            self.restarts.append(dict(session=ctx["session"], model=ctx["model"], archive=str(dest), at=co.utc_stamp()))
            self.log(f"RESTART load {ctx['session']}/{ctx['model']}: archived to {dest}")
            self.write_json("restarting")

    def prepare(self, ctx, restart=False):
        self.check_stop("restart preparation" if restart else "block boundary")
        unloaded = False
        if self.loaded:
            if not self.ops.unload(self.loaded):
                raise co.ChainAbort(f"unload of {self.loaded} not verified")
            self.loaded, unloaded = None, True
        if unloaded:
            self.arm_idle()
        self.check_stop("restart preparation" if restart else "block boundary")
        st = self.ops.start_state()
        self.log(f"START STATE {ctx['session']}/{ctx['model']}: {json.dumps(st, default=str)}")
        if not self.ops.power_ok():
            raise co.ChainAbort("power gate FAIL before load")
        self.load_worker(ctx)
        n = len(self.block_workers) - 1
        for arm in self.arm_ids:
            ctx["receipts"][arm] = self.ops.a4_gate(ctx["model"], f"{ctx['session']}_{n}_{ctx['model']}_{arm}",
                                                    scaffold=self.specs[arm].label)
        self.write_json("block-loaded")

    def load_worker(self, ctx):
        ident = self.ops.load(ctx["model"])
        self.loaded = ctx["model"]
        key = (ident["pid"], ident["create_time"])
        if any(key == (w["pid"], w["create_time"]) for w in self.block_workers):
            raise co.ChainAbort("worker identity reused across blocks")
        self.block_workers.append(dict(pid=ident["pid"], create_time=ident["create_time"], cmdline=ident.get("cmdline"),
                                       session=ctx["session"], model=ctx["model"]))
        ctx["worker"], ctx["manifest_worker"] = dict(pid=ident["pid"], create_time=ident["create_time"]), None

    def execute_load(self, ctx):
        for leg in ctx["legs"]:
            self.check_stop("before launch")
            self.run_leg(ctx, leg)
            self.realized.append(ms.leg_key(leg))
            self.write_json("leg-done")
        return True

    def stems_of_load(self, ctx):
        return [f"{ctx['model']}.{ctx['session']}.{arm}_{lang}" for arm in self.arm_ids for lang in ms.LANGS]

    def archive_load(self, ctx):
        sdir = self.session_dir(ctx)
        dest = sdir / "incomplete" / f"{ctx['model']}.{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(sdir.iterdir()) if sdir.exists() else []:
            if f.is_file() and any(f.name.startswith(stem + ".") for stem in self.stems_of_load(ctx)):
                shutil.move(str(f), str(dest / f.name))
        return dest

    # -- legs
    def segment_out(self, ctx, leg):
        sdir = self.session_dir(ctx)
        seg = ctx["segment"]
        return sdir / (stem_of(leg) + ("" if seg == 0 else f".w{seg}") + ".jsonl")

    def scored_ids(self, ctx, leg):
        """Item ids of this stem already scored: rows in any segment plus the DNF sidecar."""
        sdir, stem, ids = self.session_dir(ctx), stem_of(leg), set()
        if sdir.exists():
            for f in sdir.iterdir():
                n = f.name
                if f.suffix == ".jsonl" and n.startswith(stem + ".") and not n.endswith(".dnf.jsonl"):
                    ids |= {r.get("id") for r in self.ops.rows(f)}
        ids |= {r["id"] for r in self.dnf if r["slot"].split("|")[1:5] == [leg["arm"], ctx["model"], ctx["session"], leg["lang"]]}
        return ids

    def arm_switch(self, ctx, leg):
        """Spec 5.5 / 8.1: the search service restarts before EVERY leg; an arm switch resets the cache session and
        sends one unscored warm-up request."""
        self.ops.search_restart(leg)
        if ctx["last_arm"] != leg["arm"]:
            self.ops.reset_cache_session(ctx["model"])
            self.ops.warmup(ctx["model"])
        ctx["last_arm"] = leg["arm"]

    def run_leg(self, ctx, leg):
        spec = self.specs[leg["arm"]]
        leg = dict(leg, model=leg["pick"], stem=stem_of(leg), label=spec.label)
        prefix = leg["lang"] + "/"
        pending = [n for n in leg["items"] if prefix + n not in self.scored_ids(ctx, leg)]
        while pending:
            self.arm_switch(ctx, leg)
            out = self.segment_out(ctx, leg)
            leg["out"] = str(out)
            done_ids = [r["id"] for r in self.ops.rows(out)] if out.exists() else []
            expect = done_ids + [prefix + n for n in pending if prefix + n not in done_ids]
            result = self.run_step(ctx, leg, pending, expect)
            scored = self.scored_ids(ctx, leg)
            pending = [n for n in pending if prefix + n not in scored]
            if result == "ok":
                if pending:
                    raise co.ChainAbort(f"{leg['stem']}: leg validated but items {pending} have no row")
                return
            incident = result                                # a dict: a transport incident
            failed = pending[0]
            self.handle_incident(ctx, leg, failed, incident)
            pending = [n for n in pending if prefix + n not in self.scored_ids(ctx, leg)]

    def handle_incident(self, ctx, leg, item, incident):
        slot = slot_key(self.epoch_id, leg["arm"], ctx["model"], ctx["session"], leg["lang"], item)
        n = self.slot_attempts.get(slot, 0) + 1
        self.slot_attempts[slot] = n
        rec = dict(incident, slot=slot, attempt=n, arm=leg["arm"], pick=ctx["model"], session=ctx["session"],
                   lang=leg["lang"], item=item, at=co.utc_stamp())
        self.incidents.append(rec)
        self.log(f"INCIDENT {leg['stem']} {item} attempt {n}: cause={rec['cause']} tokens={rec.get('output_tokens')}")
        self.write_json("incident")
        self.recover(ctx, leg)
        if n >= 2:
            mine = [i for i in self.incidents if i["slot"] == slot]
            runtime = self.pinned_by_arm[leg["arm"]]
            row = dnf_row(slot=slot, arm=leg["arm"], label=leg["label"], pick=ctx["model"], session=ctx["session"],
                          lang=leg["lang"], item=item, seed_base=leg["seed_base"], incidents=mine,
                          worker=self.worker_full(ctx), frozen=self.frozen, epoch=self.epoch_id,
                          runtime=dict(runtime, generation_identity_sha256=self.arm_gen.get(leg["arm"]),
                                       arm_identity_sha256=self.arms.get(self.arm_key(leg))))
            why = validate_dnf_row(row, arm=leg["arm"], slot=slot)
            if why:
                raise co.ChainAbort("; ".join(why))
            self.dnf.append(row)
            sidecar = self.session_dir(ctx) / (stem_of(leg) + ".dnf.jsonl")
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            with sidecar.open("a") as f:
                f.write(json.dumps(row) + "\n")
            self.log(f"DNF {slot}: transport_dnf row written ({sidecar.name}); the schedule continues")
            self.write_json("dnf")

    def worker_full(self, ctx):
        wk = ctx.get("manifest_worker")
        return wk if wk else dict(ctx["worker"])

    def recover(self, ctx, leg):
        """Spec 8.3 recovery before the next attempt: unload + reload the worker (new identity recorded), cache-session
        reset, one warm-up request. The next probe starts a new rows segment (one worker instance per rows file)."""
        if self.loaded and not self.ops.unload(self.loaded):
            raise co.ChainAbort(f"recovery: unload of {self.loaded} not verified")
        self.loaded = None
        self.load_worker(ctx)
        ctx["segment"] += 1
        ctx["last_arm"] = None
        self.ops.reset_cache_session(ctx["model"])
        self.ops.warmup(ctx["model"])
        self.write_json("recovered")

    def run_step(self, ctx, leg, names, expect):
        """One probe invocation for `names` on the current segment. Returns "ok" (validated), or the incident record
        of a classified transport failure; anything else raises `LoadIncomplete` / `ChainAbort`."""
        self.verify_lifecycle("launch")
        spec = self.specs[leg["arm"]]
        out = Path(leg["out"])
        sdir = out.parent
        sdir.mkdir(parents=True, exist_ok=True)
        stem_seg = out.stem
        n = self.attempt_no.get(stem_seg, 0) + 1
        self.attempt_no[stem_seg] = n
        stem = sdir / f"{stem_seg}.attempt{n}"
        cancel, ack = Path(str(stem) + ".CANCEL"), Path(str(stem) + ".ACK")
        logp, ajson = Path(str(stem) + ".log"), Path(str(stem) + ".json")
        if cancel.exists() or ack.exists():
            raise co.ChainAbort(f"stale cancel/ack file for attempt path {stem.name}")
        cur = self.ops.worker_ident(leg["model"])
        if not cur or (cur["pid"], cur["create_time"]) != (ctx["worker"]["pid"], ctx["worker"]["create_time"]):
            raise co.ChainAbort("worker identity changed before launch")
        if not self.ops.power_ok():
            raise co.ChainAbort("power gate FAIL before launch")
        if leg["lang"] == "go" and not self.ops.docker_ok():
            raise co.ChainAbort("docker gate FAIL before launch")
        step = dict(kind="leg", names=names, limit=None)
        cmd = build_cmd(self.py, self.probe_of(leg["arm"]), leg, names, expect, out, spec.label,
                        ctx["receipts"][leg["arm"]], cancel, ack, universe=self.universe, frozen=self.frozen,
                        epoch=self.epoch_id)
        att = dict(attempt=n, step="leg", stem=stem_seg, arm=leg["arm"], argv=cmd, cancel=str(cancel), ack=str(ack),
                   log=str(logp), worker=dict(ctx["worker"]), started=co.utc_stamp(), rc=None, cleanup_status=None,
                   run_id=None, probe_pid=None, probe_create_time=None, outcome=None)
        self.log(f"START {stem_seg} attempt {n} (leg {leg['block']}, {len(names)} items): {' '.join(cmd[2:])}")
        with logp.open("ab") as lf:
            proc = subprocess.Popen(cmd, cwd=str(REPO), env=self.ops.env_base(), stdout=lf, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
        att["probe_pid"] = proc.pid
        try:
            att["probe_create_time"] = self.ops.create_time(proc.pid)
        except Exception:  # noqa: BLE001
            pass
        self.attempts.append(att)
        co.atomic_json(ajson, att)
        self.write_json("running")
        sup = self.supervise(att, proc, dict(leg, stem=stem_seg), step, ctx)
        att["rc"] = proc.returncode
        man = self._manifest(dict(leg, out=str(out)))
        if man and att["run_id"] and man.get("run_id") == att["run_id"]:
            att["cleanup_status"] = base.receipt_from_manifest(man)
            att["cancelled_item"] = man.get("cancelled_item")
            att["transport_abort"] = man.get("transport_abort")
        att["outcome"] = sup["state"]
        co.atomic_json(ajson, att)
        self.log(f"END {stem_seg} attempt {n} rc={att['rc']} state={sup['state']}")
        self.write_json("attempt-ended")
        if sup["state"] == "barrier_mismatch":
            self.listing(att, leg)
            raise co.ChainAbort("first-manifest mismatch: " + "; ".join(sup["reasons"]))
        self.verify_lifecycle("validation")
        pinned = {**self.pinned_by_arm[leg["arm"]], **self.pinned_shared}
        vleg = dict(session=leg["session"], model=leg["model"], lang=leg["lang"], seed_base=leg["seed_base"],
                    expected_ids=expect, out=str(out), rc=att["rc"], draft_kind="off",
                    arm_identity_sha256=self.arms.get(self.arm_key(leg)))
        why = co.validate_leg(vleg, pinned, self.ops.wd, policy_sha=self.policies[leg["arm"]],
                              frozen_prompt_date=self.frozen, spec=spec) + self.arm_row_problems(leg, out)
        if not why:
            self.pin_from(leg, out)
            att["outcome"] = "validated"
            co.atomic_json(ajson, att)
            return "ok"
        for w in why:
            self.log(f"INCOMPLETE {stem_seg} attempt {n}: {w}")
        if sup["stop"]:
            dest = self.archive_stopped(ctx, dict(leg, stem=stem_seg))
            self.log(f"STOP: partial leg archived to {dest}")
            self.stop_info["where"] = "leg"
            raise Stopped("leg")
        incident = self.classify_incident(att, sup, man, leg, out, ctx)
        if incident is not None:
            return incident
        self.check_restart_eligible(att, leg, ctx)
        raise LoadIncomplete("; ".join(why[:3]))

    def arm_row_problems(self, leg, out):
        """Arm-identifying fields every row and the manifest must carry (rows: arm, epoch_id, snapshot_sha256)."""
        why = []
        man = self._manifest(dict(leg, out=str(out))) or {}
        rt = man.get("runtime") or {}
        for key, want in (("arm", leg["arm"]), ("epoch_id", self.epoch_id)):
            if rt.get(key) != want:
                why.append(f"runtime_{key}: {rt.get(key)!r} != {want!r}")
        for r in self.ops.rows(out) if Path(out).exists() else []:
            for key, want in (("arm", leg["arm"]), ("epoch_id", self.epoch_id),
                              ("snapshot_sha256", rt.get("snapshot_sha256"))):
                if r.get(key) != want or not want:
                    why.append(f"row_{key}: {r.get('id')} {r.get(key)!r} != {want!r}")
        return why

    def classify_incident(self, att, sup, man, leg, out, ctx):
        """A transport incident (8.3), or None when the failure is not one. The probe's abort stamp names the cause
        (classified from the client's own error shape); an idle-cancelled (hung) probe is a client timeout. The failed
        attempt's rows already written are validated first: anything wrong there is not an incident."""
        stamp = (man or {}).get("transport_abort") or {}
        cause = stamp.get("cause") if stamp.get("cause") in INCIDENT_CAUSES else None
        if cause is None and sup["state"] == "cancelled" and sup.get("cancel_reason") == "idle":
            cause = "client_timeout"
        if cause is None:
            return None
        cur = self.ops.worker_ident(leg["model"])
        if not cur or (cur["pid"], cur["create_time"]) != (ctx["worker"]["pid"], ctx["worker"]["create_time"]):
            cause = "worker_crash"
        cs = att.get("cleanup_status")
        if isinstance(cs, dict) and (cs.get("survivors") or cs.get("containers_remaining") or cs.get("uncertain") is not False):
            self.listing(att, leg)
            raise co.ChainAbort("incident refused: cleanup uncertain after the failed attempt")
        rows = self.ops.rows(out) if Path(out).exists() else []
        partial = dict(session=leg["session"], model=leg["model"], lang=leg["lang"], seed_base=leg["seed_base"],
                       expected_ids=[r["id"] for r in rows], out=str(out), rc=0, draft_kind="off",
                       arm_identity_sha256=self.arms.get(self.arm_key(leg)))
        bad = [w for w in co.validate_leg({**partial}, {**self.pinned_by_arm[leg["arm"]], **self.pinned_shared},
                                          self.ops.wd, policy_sha=self.policies[leg["arm"]],
                                          frozen_prompt_date=self.frozen, spec=self.specs[leg["arm"]])
               if not w.startswith(("manifest_abort", "rc_nonzero"))] if rows else []
        if bad:
            raise co.ChainAbort("incident refused: the rows of the failed attempt do not validate: " + "; ".join(bad[:3]))
        gate = stamp.get("gate") or {}
        archived = Path(str(out.with_suffix(".manifest.json")) + f".incident{att['attempt']}")
        try:
            shutil.move(str(out.with_suffix(".manifest.json")), str(archived))
        except OSError:
            archived = None
        return dict(cause=cause, output_tokens=gate.get("output_tokens_completed") or 0,
                    requests=gate.get("requests_completed"), attempt_file=str(att["log"]),
                    manifest=str(archived) if archived else None, worker=dict(ctx["worker"]),
                    error=str(stamp.get("error"))[:200])

    # -- archive / stop
    def archive_stopped(self, ctx, leg):
        sdir = self.session_dir(ctx)
        dest = sdir / "stopped" / f"{leg['stem']}.{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
        return self._move_prefix(sdir, leg["stem"] + ".", dest)

    # -- identity pinning and the barrier
    @staticmethod
    def arm_key(leg):
        return f"{leg['model']}|off"

    def evidence_root(self, leg, att):
        if not att.get("run_id"):
            return None
        return Path(self.ops.wd) / self.specs[leg["arm"]].evidence_dir / leg["model"] / \
            f"{Path(leg['out']).stem}.{att['run_id']}"

    def verify_manifest(self, man, leg, ctx):
        arm, spec = leg["arm"], self.specs[leg["arm"]]
        why = []
        drift = co.lifecycle_drift(self.lifecycle, self.lifecycle_files)
        if drift:
            why.append(f"lifecycle drift at barrier: {', '.join(drift)} changed since chain creation")
        rt, wk = man.get("runtime") or {}, man.get("worker")
        frozen_worker_arm = self.arms.get(self.arm_key(leg))
        if frozen_worker_arm is not None and rt.get("arm_identity_sha256") != frozen_worker_arm:
            why.append(f"arm_identity_sha256: {rt.get('arm_identity_sha256')!r} != frozen {frozen_worker_arm!r} for "
                       f"{self.arm_key(leg)}")
        chk = [("scaffold", rt.get("scaffold"), spec.label), ("arm", rt.get("arm"), arm),
               ("epoch_id", rt.get("epoch_id"), self.epoch_id),
               ("scaffold_policy_sha256", rt.get("scaffold_policy_sha256"), self.policies[arm]),
               ("frozen_prompt_date", rt.get("frozen_prompt_date"), self.frozen),
               ("draft_kind", rt.get("draft_kind"), "off"), ("seed_base", rt.get("seed_base"), leg["seed_base"]),
               ("lang", rt.get("lang"), leg["lang"]), ("model", man.get("model"), leg["model"]),
               ("sampling_profile", rt.get("sampling_profile", man.get("sampling_profile")), "deployed"),
               ("registry.sha256", (man.get("registry") or {}).get("sha256"), self.ops.overlay_sha())]
        if arm in self.arm_gen:
            chk.append(("generation_identity_sha256", rt.get("generation_identity_sha256"), self.arm_gen[arm]))
        ident = co.runtime_identity(man, spec.runtime_pinned)
        pinned = {**self.pinned_by_arm[arm], **self.pinned_shared}
        for k in spec.runtime_pinned:
            if k in pinned:
                chk.append((k, ident.get(k, "<absent>"), pinned[k]))
        if pinned.get("serving_path") is not None:
            chk.append(("git.serving_path", (man.get("git") or {}).get("serving_path"), pinned["serving_path"]))
        for k, got, want in chk:
            if got != want:
                why.append(f"{k}: {got!r} != {want!r}")
        if not getattr(self.a, "smoke", False) and rt.get("snapshot_complete") is not True:
            why.append("snapshot_complete: the arm's snapshot is incomplete (a real chain needs the registered epoch)")
        if not co.typed_worker(wk):
            why.append("worker identity untyped")
        else:
            if (wk["pid"], wk["create_time"]) != (ctx["worker"]["pid"], ctx["worker"]["create_time"]):
                why.append("worker identity differs from the load's loaded instance")
            if ctx.get("manifest_worker") and wk != ctx["manifest_worker"]:
                why.append("worker identity differs from the load's first manifest")
            if wk["registry_sha256"] != self.ops.overlay_sha():
                why.append("worker registry_sha256 differs from the overlay")
        if man.get("transport_abort"):
            why.append("manifest already records transport_abort")
        why += [f"{f}_invalid" for f in co.malformed_identity(man, spec)]
        return why

    def _barrier(self, att, leg, ctx, st, t_spawn):
        mp = Path(leg["out"]).with_suffix(".manifest.json")
        man = None
        try:
            man = json.loads(mp.read_text())
        except (OSError, ValueError):
            pass
        if not man or not man.get("run_id") or man["run_id"] in self.seen_run_ids:
            return
        why = self.verify_manifest(man, leg, ctx)
        self.seen_run_ids.add(man["run_id"])
        att["run_id"] = man["run_id"]
        if why:
            st["reasons"] = why
            self.log(f"BARRIER MISMATCH {leg['stem']}: {'; '.join(why)} -- no ack")
            return
        runtime, arm = man["runtime"] or {}, leg["arm"]
        if arm not in self.arm_gen:                                  # frozen at the arm's first manifest
            self.arm_gen[arm] = runtime.get("generation_identity_sha256")
            self.log(f"arm {arm}: generation_identity_sha256 frozen from first manifest {self.arm_gen[arm]}")
        if self.arm_key(leg) not in self.arms:                      # one worker identity per (model, predictor), all arms
            self.arms[self.arm_key(leg)] = runtime.get("arm_identity_sha256")
            self.log(f"worker {self.arm_key(leg)}: arm_identity_sha256 frozen from first manifest "
                     f"{self.arms[self.arm_key(leg)]}")
        self.write_json("barrier-ok")
        ctx["manifest_worker"] = ctx.get("manifest_worker") or man["worker"]
        Path(att["ack"]).write_text("ack\n")
        st["barrier_done"] = True
        att["worker_full"] = man["worker"]
        self.log(f"BARRIER ok {leg['stem']} run_id={man['run_id']}: ack created")

    def pin_from(self, leg, out):
        man = self._manifest(dict(leg, out=str(out))) or {}
        spec = self.specs[leg["arm"]]
        bad = co.malformed_identity(man, spec)
        if bad:
            raise co.ChainAbort(f"first complete leg has absent/null/malformed identity fields: {bad}")
        pinned, missing = self.pinned_by_arm[leg["arm"]], []
        ident = co.runtime_identity(man, spec.runtime_pinned)
        for k in spec.runtime_pinned:
            if k in pinned:
                continue
            if k in ident:
                pinned[k] = ident[k]
            else:
                missing.append(k)
        if "serving_path" not in self.pinned_shared:
            sp = (man.get("git") or {}).get("serving_path")
            if sp:
                self.pinned_shared["serving_path"] = sp
            else:
                missing.append("serving_path")
        if missing:
            raise co.ChainAbort(f"first complete leg lacks pinned identity fields: {missing}")


# --------------------------------------------------------------------------- entry
def _kv(values, what, ap, *, hexed=False):
    out = {}
    for item in values or []:
        arm, _, val = item.partition("=")
        if not val or not aa.valid_arm_id(arm):
            ap.error(f"{what} must be ARM=VALUE with a known arm, got {item!r}")
        if hexed and not co.HEX64.match(val):
            ap.error(f"{what} {arm} must be 64 lowercase hex")
        out[arm] = val
    return out


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["chain"])
    ap.add_argument("sessions", nargs="*")
    ap.add_argument("--arms", default="oc", help="comma-separated arms to schedule (oc, pi, dsh)")
    ap.add_argument("--probe-code-sha", action="append", default=[], metavar="ARM=SHA", help="required for every arm")
    ap.add_argument("--probe", action="append", default=[], metavar="ARM=PATH", help="override an arm's probe entry")
    ap.add_argument("--policy-sha", action="append", default=[], metavar="ARM=SHA",
                    help="an ASSERTION of the arm's scaffold_policy_sha256 (derived from its probe)")
    ap.add_argument("--epoch-id", required=True, help="the registered M64 epoch (64 hex)")
    ap.add_argument("--pred-s", action="append", default=[], metavar="LANG:MODEL=SECONDS")
    ap.add_argument("--arm-idle-s", type=float, default=None)
    ap.add_argument("--smoke", action="store_true", help="rehearsal: tiny cells, 60 s arm idle, own out-root")
    ap.add_argument("--out-root")
    ap.add_argument("--python", default=str(REPO / ".venv-bench/bin/python"))
    ap.add_argument("--universe")
    ap.add_argument("--frozen-prompt-date", default=None, metavar="'Www Mmm DD YYYY'")
    ap.add_argument("--frozen-date-from", default=None, metavar="CHAIN_JSON")
    a = ap.parse_args(argv)
    a.arms = [x for x in a.arms.split(",") if x]
    if not a.arms or len(set(a.arms)) != len(a.arms) or any(not aa.valid_arm_id(x) for x in a.arms):
        ap.error(f"--arms must be distinct known arms of {aa.ARM_IDS}")
    a.probe_code_sha = _kv(a.probe_code_sha, "--probe-code-sha", ap, hexed=True)
    a.probe = _kv(a.probe, "--probe", ap)
    a.policy_sha = _kv(a.policy_sha, "--policy-sha", ap, hexed=True)
    missing = [x for x in a.arms if x not in a.probe_code_sha]
    if missing:
        ap.error(f"--probe-code-sha ARM=SHA is required for every arm (missing {missing})")
    if not co.HEX64.match(a.epoch_id):
        ap.error("--epoch-id must be 64 lowercase hex")
    if a.frozen_prompt_date is not None and not datefreeze.valid(a.frozen_prompt_date):
        ap.error("--frozen-prompt-date must be 'Www Mmm DD YYYY' (e.g. 'Sat Oct 17 2026')")
    if a.arm_idle_s is None:
        a.arm_idle_s = base.SMOKE_ARM_IDLE_S if a.smoke else 600.0
    a.sessions = a.sessions or ["s1", "s2", "reload"]
    bad = [s for s in a.sessions if s not in ms.SESSION_SEEDS and s != "reload"]
    if bad:
        ap.error(f"unknown session {bad}")
    return a


def resolve_out_root(a, wd):
    """`$STACK_WORKDIR/m64` (real) or `m64-smoke`; absolute (P340: subprocesses run with cwd=REPO); a smoke run is
    refused inside the real directory, and neither may write inside another chain's directories."""
    root = Path(a.out_root) if a.out_root else Path(wd) / ("m64-smoke" if a.smoke else "m64")
    root = root.expanduser().absolute()
    if a.smoke and root.resolve() == (Path(wd) / "m64").resolve():
        raise Refused("REFUSED: --smoke must not write into the real chain directory")
    for d in ("c147", "c147-smoke", "m63", "m63-smoke"):
        other = (Path(wd) / d).resolve()
        if root.resolve() == other or other in root.resolve().parents:
            raise Refused(f"REFUSED: the M64 chain must not write into {other}")
    return root


def main(argv=None, ops=None, timers=None, log_out=None, lifecycle_files=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    wd = Path(ops.wd) if ops is not None else Path(os.environ["STACK_WORKDIR"])
    out_root = resolve_out_root(a, wd)
    out_root.mkdir(parents=True, exist_ok=True)
    log = co.RunLog(out_root / "RUNLOG.md", out=log_out)
    if ops is None:
        from bench import arm_ops
        overlay = os.environ.get("C147_OVERLAY") or str(out_root / "overlay_m64_draft_off.yaml")
        ops = arm_ops.M64ChainOps(REPO, wd, overlay, log, out_root=out_root)
    chain = ArmChain(a, ops, timers or Timers(), log, base.load_universe(a.universe), out_root, lifecycle_files)
    try:
        return chain.run()
    except BaseException:
        chain.rc = 1
        chain.write_json("crashed")
        raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as e:
        print(e.args[0], file=sys.stderr)
        sys.exit(2)
