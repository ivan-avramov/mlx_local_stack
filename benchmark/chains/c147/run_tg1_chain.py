"""C147 tg1 chain runner (spec docs/specs/c147-tg1-chain-clearance.md section 3).

  run_tg1_chain.py pilot                      one block: pick 1 python, first 5 seeded-random items, s1 seed
  run_tg1_chain.py chain [s1 s2 reload] --probe-code-sha <sha>

Exit codes: 0 done, 2 chain abort (listing printed, nothing killed), 3 STOP latch honoured, 1 unexpected error.
Cancellation is cooperative only: the idle predicate (chain_ops.IdlePredicate) or `<out-root>/STOP`.
Detached launch: drive_chain.sh. Tests inject `ops` (chain_ops.ChainOps-shaped) and `timers`.
"""
import argparse
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import chain_ops as co  # noqa: E402

PICK1, PICK2 = co.PICK1, co.PICK2
SCAFFOLD = co.SCAFFOLD
SEEDS = {"s1": 1001, "s2": 2002, "reload": 1001}
LEGS = {"s1": [(PICK1, "python"), (PICK1, "go"), (PICK2, "python"), (PICK2, "go")],
        "s2": [(PICK2, "python"), (PICK2, "go"), (PICK1, "python"), (PICK1, "go")],
        "reload": [(PICK1, "python")]}
PRED_S = {("python", PICK1): 244, ("go", PICK1): 300, ("python", PICK2): 267, ("go", PICK2): 360}   # M59 table
PILOT_N = 5


class Stopped(Exception):
    pass


@dataclass
class Timers:
    poll_s: float = 1.0
    watch_s: float = 300.0
    idle_sample_s: float = 60.0
    hb_age_s: float = 900.0
    idle_needed: int = 3
    manifest_alarm_s: float = 120.0
    term_wait_s: float = 120.0
    kill_wait_s: float = 30.0
    barrier_exit_wait_s: float = 330.0
    t_coop_scale: float = 1.0


# --------------------------------------------------------------------------- schedule
def load_universe(path=None):
    d = json.loads(Path(path or REPO / "benchmark/m62/universe.json").read_text())["items"]
    names = {"python": [], "go": []}
    for k in d:
        lang, name = k.split("/", 1)
        names[lang].append(name)
    return {k: sorted(v) for k, v in names.items()}


def make_leg(session, model, lang, seed_base, names, out_dir, reload_ctl=False):
    pilot = random.Random(seed_base).sample(sorted(names[lang]), PILOT_N)
    full = sorted(pilot) if reload_ctl else sorted(names[lang])
    stem = f"{model}.{session}.opencode_{lang}"
    return dict(session=session, model=model, lang=lang, seed_base=seed_base, stem=stem,
                out=str(Path(out_dir) / session / (stem + ".jsonl")),
                pilot_names=sorted(pilot), full_names=full)


def schedule(mode, sessions, names, out_root):
    """List of blocks: {session, model, seed_base, legs}. A block = one model within one session (both languages)."""
    if mode == "pilot":
        leg = make_leg("pilot", PICK1, "python", SEEDS["s1"], names, out_root)
        return [dict(session="pilot", model=PICK1, seed_base=SEEDS["s1"], legs=[leg], pilot_only=True)]
    blocks = []
    for s in sessions:
        grouped = []
        for model, lang in LEGS[s]:
            if grouped and grouped[-1][0] == model:
                grouped[-1][1].append(lang)
            else:
                grouped.append((model, [lang]))
        for model, langs in grouped:
            legs = [make_leg(s, model, lang, SEEDS[s], names, out_root, reload_ctl=(s == "reload")) for lang in langs]
            blocks.append(dict(session=s, model=model, seed_base=SEEDS[s], legs=legs, pilot_only=False))
    return blocks


def steps_for(block, idx):
    leg = block["legs"][idx]
    pilot = dict(kind="pilot", names=leg["pilot_names"], limit=PILOT_N)
    full = dict(kind="full", names=leg["full_names"], limit=None)
    if block.get("pilot_only"):
        return [pilot]
    if idx > 0:
        return [full]
    return [pilot] if leg["pilot_names"] == leg["full_names"] else [pilot, full]


def build_cmd(py, probe, leg, step, receipt, cancel, ack):
    ids = [f"{leg['lang']}/{n}" for n in step["names"]]
    cmd = [str(py), str(probe), "--model", leg["model"], "--items", ",".join(step["names"]), "--lang", leg["lang"],
           "--seed-base", str(leg["seed_base"]), "--out", leg["out"], "--scaffold", SCAFFOLD,
           "--expect-items", ",".join(ids), "--a4-v2-receipt", str(receipt), "--sampling-profile", "deployed",
           "--cancel-file", str(cancel), "--manifest-ack", str(ack)]
    if step["limit"]:
        cmd += ["--limit", str(step["limit"])]
    return cmd


# --------------------------------------------------------------------------- helpers
class Heartbeat:
    def __init__(self, logpath, clock, t0):
        self.path, self.clock, self.seen, self.line, self.data = Path(logpath), clock, t0, None, {}

    def poll(self):
        try:
            with self.path.open("rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 262144))
                text = f.read().decode(errors="replace")
        except OSError:
            return
        lines = [ln for ln in text.splitlines() if '"m62_watch"' in ln]
        if lines and lines[-1] != self.line:
            self.line = lines[-1]
            self.seen = self.clock()
            try:
                self.data = json.loads(self.line)
            except ValueError:
                self.data = {}

    def age(self):
        return self.clock() - self.seen

    def watch(self):
        return self.data.get("m62_watch") or {}

    def last_prompt(self):
        return self.watch().get("last_prompt_tokens") or 0


def dir_bytes(root):
    total = 0
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            try:
                total += os.stat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total


def receipt_from_manifest(man):
    """The probe's cleanup receipt: TOP-LEVEL manifest `cleanup_status` on every abort (one location, both sides)."""
    cs = man.get("cleanup_status")
    return cs if isinstance(cs, dict) else None


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


# --------------------------------------------------------------------------- the chain
class Chain:
    def __init__(self, args, ops, timers, log, names, out_root):
        self.a, self.ops, self.tm, self.log = args, ops, timers, log
        self.out_root, self.stop_path = Path(out_root), Path(out_root) / "STOP"
        self.names = names
        self.clock = time.monotonic
        self.py = Path(args.python)
        self.probe = Path(args.probe)
        # a key is present once pinned; a pinned None (e.g. agent_system_sha256 without an overlay) is a value
        self.pinned = {"scaffold_policy_sha256": co.CAMPAIGN_POLICY_SHA}
        if args.probe_code_sha:
            self.pinned["probe_code_sha256"] = args.probe_code_sha
        self.attempts, self.restarts, self.stop_info = [], [], None
        self.attempt_no, self.seen_run_ids, self.block_workers = {}, set(), []
        self.loaded = None
        self.rc = None
        self.pred, self.explicit_pred = dict(PRED_S), {}
        for spec in args.pred_s or []:
            key, val = spec.rsplit("=", 1)
            lang, model = key.split(":", 1)
            self.explicit_pred[(lang, model)] = float(val)

    # -- chain.json
    def write_json(self, status=None):
        gate = REPO / "scripts/session_pinning_gate.py"
        doc = dict(status=status, mode=self.a.mode, argv=sys.argv[1:], updated=co.utc_stamp(),
                   sha256=dict(runner=co.file_sha(__file__), chain_ops=co.file_sha(co.__file__),
                               gate=co.file_sha(gate), overlay=self.ops.overlay_sha()),
                   probe=str(self.probe), probe_code_sha=self.a.probe_code_sha, pinned=self.pinned,
                   attempts=self.attempts, restarts=self.restarts, stop=self.stop_info, rc=self.rc,
                   block_workers=self.block_workers)
        co.atomic_json(self.out_root / "chain.json", doc)

    # -- STOP
    def stop_requested(self):
        if self.stop_path.exists():
            if self.stop_info is None:
                self.stop_info = dict(at=co.utc_stamp())
                self.log("STOP latched")
            return True
        return False

    def check_stop(self, where):
        if self.stop_requested():
            self.stop_info["where"] = where
            raise Stopped(where)

    # -- run
    def run(self):
        self.write_json("starting")
        if self.stop_requested():
            self.stop_info["where"] = "start"
            self.log("STOP present at start: nothing launched")
            self.rc = 3
            return 3
        try:
            self.ops.ensure_overlay()
            self.pinned["registry_sha256"] = self.ops.overlay_sha()
            if not self.ops.power_ok():
                raise co.ChainAbort("power gate FAIL")
            self.ops.start_router()
            blocks = schedule(self.a.mode, self.a.sessions, self.names, self.out_root)
            self.log(f"START {self.a.mode} blocks={[(b['session'], b['model']) for b in blocks]}")
            try:
                for block in blocks:
                    self.run_block(block)
                if self.loaded and not self.ops.unload(self.loaded):
                    raise co.ChainAbort("final unload failed")
                self.loaded = None
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

    # -- block
    def session_dir(self, block):
        return self.out_root / block["session"]

    def run_block(self, block):
        restarted = False
        while True:
            self.prepare(block, restarted)
            if self.execute_block(block) == "ok":
                return
            if restarted:
                raise co.ChainAbort(f"block {block['session']}/{block['model']} incomplete twice")
            dest = self.archive_block(block)
            restarted = True
            self.restarts.append(dict(session=block["session"], model=block["model"], archive=str(dest),
                                      at=co.utc_stamp()))
            self.log(f"RESTART block {block['session']}/{block['model']}: archived to {dest}")
            self.write_json("restarting")

    def prepare(self, block, restart=False):
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
        self.log(f"START STATE {block['session']}/{block['model']}: {json.dumps(st, default=str)}")
        if not self.ops.power_ok():
            raise co.ChainAbort("power gate FAIL before load")
        ident = self.ops.load(block["model"])
        self.loaded = block["model"]
        key = (ident["pid"], ident["create_time"])
        if any(key == (w["pid"], w["create_time"]) for w in self.block_workers):
            raise co.ChainAbort("worker identity reused across blocks")
        n = len(self.block_workers)
        self.block_workers.append(dict(pid=ident["pid"], create_time=ident["create_time"], cmdline=ident.get("cmdline"),
                                       session=block["session"], model=block["model"]))
        block["worker"], block["manifest_worker"] = dict(pid=ident["pid"], create_time=ident["create_time"]), None
        block["receipt"] = self.ops.a4_gate(block["model"], f"{block['session']}_{n}_{block['model']}")
        self.write_json("block-loaded")

    def arm_idle(self):
        end = self.clock() + self.a.arm_idle_s
        self.log(f"ARM idle {self.a.arm_idle_s}s")
        while self.clock() < end:
            self.check_stop("block boundary")
            time.sleep(min(self.tm.poll_s, max(0.0, end - self.clock())))

    def execute_block(self, block):
        for i, leg in enumerate(block["legs"]):
            for step in steps_for(block, i):
                self.check_stop("before launch")
                if self.run_step(block, leg, step) != "ok":
                    return "incomplete"
        return "ok"

    # -- archive
    def _move_prefix(self, sdir, prefix, dest):
        dest.mkdir(parents=True, exist_ok=True)
        for f in sorted(sdir.iterdir()):
            if f.is_file() and f.name.startswith(prefix):
                shutil.move(str(f), str(dest / f.name))
        return dest

    def archive_block(self, block):
        sdir = self.session_dir(block)
        dest = sdir / "incomplete" / f"{block['model']}.{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
        return self._move_prefix(sdir, f"{block['model']}.{block['session']}.opencode_", dest)

    def archive_stopped(self, block, leg):
        sdir = self.session_dir(block)
        dest = sdir / "stopped" / f"{leg['stem']}.{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
        return self._move_prefix(sdir, leg["stem"] + ".", dest)

    # -- step / attempt
    def run_step(self, block, leg, step):
        sdir = self.session_dir(block)
        sdir.mkdir(parents=True, exist_ok=True)
        n = self.attempt_no.get(leg["stem"], 0) + 1
        self.attempt_no[leg["stem"]] = n
        base = sdir / f"{leg['stem']}.attempt{n}"
        cancel, ack = Path(str(base) + ".CANCEL"), Path(str(base) + ".ACK")
        logp, ajson = Path(str(base) + ".log"), Path(str(base) + ".json")
        if cancel.exists() or ack.exists():
            raise co.ChainAbort(f"stale cancel/ack file for attempt path {base.name}")
        cur = self.ops.worker_ident(leg["model"])
        if not cur or (cur["pid"], cur["create_time"]) != (block["worker"]["pid"], block["worker"]["create_time"]):
            raise co.ChainAbort("worker identity changed before launch")
        if not self.ops.power_ok():
            raise co.ChainAbort("power gate FAIL before launch")
        ids = [f"{leg['lang']}/{x}" for x in step["names"]]
        cmd = build_cmd(self.py, self.probe, leg, step, block["receipt"], cancel, ack)
        att = dict(attempt=n, step=step["kind"], stem=leg["stem"], argv=cmd, cancel=str(cancel), ack=str(ack),
                   log=str(logp), worker=dict(block["worker"]), started=co.utc_stamp(), rc=None,
                   cleanup_status=None, run_id=None, probe_pid=None, probe_create_time=None, outcome=None)
        self.log(f"START {leg['stem']} attempt {n} ({step['kind']}, {len(ids)} items): {' '.join(cmd[2:])}")
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
        sup = self.supervise(att, proc, leg, step, block)
        att["rc"] = proc.returncode
        man = self._manifest(leg)
        if man and att["run_id"] and man.get("run_id") == att["run_id"]:
            att["cleanup_status"] = receipt_from_manifest(man)
            att["cancelled_item"] = man.get("cancelled_item")
            att["transport_abort"] = man.get("transport_abort")
        att["outcome"] = sup["state"]
        co.atomic_json(ajson, att)
        self.log(f"END {leg['stem']} attempt {n} rc={att['rc']} state={sup['state']}")
        self.write_json("attempt-ended")
        if sup["state"] == "barrier_mismatch":
            self.listing(att, leg)
            raise co.ChainAbort("first-manifest mismatch: " + "; ".join(sup["reasons"]))
        vleg = dict(session=leg["session"], model=leg["model"], lang=leg["lang"], seed_base=leg["seed_base"],
                    expected_ids=ids, out=leg["out"], rc=att["rc"])
        why = co.validate_leg(vleg, self.pinned, self.ops.wd)
        if not why:
            self.pin_from(leg)
            att["outcome"] = "validated"
            co.atomic_json(ajson, att)
            return "ok"
        for w in why:
            self.log(f"INCOMPLETE {leg['stem']} attempt {n}: {w}")
        if sup["stop"]:
            dest = self.archive_stopped(block, leg)
            self.log(f"STOP: partial leg archived to {dest}")
            self.stop_info["where"] = "leg"
            raise Stopped("leg")
        self.check_restart_eligible(att, leg, block)
        return "incomplete"

    def pin_from(self, leg):
        man = self._manifest(leg) or {}
        rt = man.get("runtime") or {}
        missing = []
        for k in co.RUNTIME_PINNED:
            if k in self.pinned:
                continue
            if k in rt:
                self.pinned[k] = rt[k]
            else:
                missing.append(k)
        if "serving_path" not in self.pinned:
            sp = (man.get("git") or {}).get("serving_path")
            if sp:
                self.pinned["serving_path"] = sp
            else:
                missing.append("serving_path")
        if missing:
            raise co.ChainAbort(f"first complete leg lacks pinned identity fields: {missing}")

    def _manifest(self, leg):
        try:
            return json.loads(Path(leg["out"]).with_suffix(".manifest.json").read_text())
        except (OSError, ValueError):
            return None

    def listing(self, att, leg):
        for line in self.ops.leftovers([str(self.ops.tmpdir)], [att.get("run_id")] if att.get("run_id") else []):
            self.log("LEFTOVER (listed, not killed): " + line)

    def check_restart_eligible(self, att, leg, block):
        why = []
        cs = att.get("cleanup_status")
        if not isinstance(cs, dict):
            why.append("cleanup uncertain: no cleanup_status recorded")
        else:
            if cs.get("survivors"):
                why.append("cleanup uncertain: survivors recorded")
            if cs.get("containers_remaining"):
                why.append("cleanup uncertain: containers remaining")
            if cs.get("uncertain") is not False:
                why.append("cleanup uncertain: uncertain flag set")
        fl = co.in_flight(self.ops.worker_metrics() or {})
        if fl != 0:
            why.append(f"worker health: metrics unreadable or in_flight={fl}")
        ident = self.ops.worker_ident(leg["model"])
        if not ident or (ident["pid"], ident["create_time"]) != (block["worker"]["pid"], block["worker"]["create_time"]):
            why.append("worker health: identity changed or worker gone")
        if why:
            self.listing(att, leg)
            raise co.ChainAbort("restart refused: " + "; ".join(why))

    # -- barrier
    def verify_manifest(self, man, leg, block):
        why = []
        rt, wk = man.get("runtime") or {}, man.get("worker")
        chk = [("scaffold", rt.get("scaffold"), SCAFFOLD),
               ("scaffold_policy_sha256", rt.get("scaffold_policy_sha256"), co.CAMPAIGN_POLICY_SHA),
               ("draft_kind", rt.get("draft_kind"), "off"), ("seed_base", rt.get("seed_base"), leg["seed_base"]),
               ("lang", rt.get("lang"), leg["lang"]), ("model", man.get("model"), leg["model"]),
               ("sampling_profile", rt.get("sampling_profile", man.get("sampling_profile")), "deployed"),
               ("registry.sha256", (man.get("registry") or {}).get("sha256"), self.ops.overlay_sha())]
        for k in co.RUNTIME_PINNED:
            if k in self.pinned:
                chk.append((k, rt.get(k, "<absent>"), self.pinned[k]))
        if self.pinned.get("serving_path") is not None:
            chk.append(("git.serving_path", (man.get("git") or {}).get("serving_path"), self.pinned["serving_path"]))
        for k, got, want in chk:
            if got != want:
                why.append(f"{k}: {got!r} != {want!r}")
        if self.a.probe_code_sha is None and self.pinned.get("probe_code_sha256") is None and not rt.get("probe_code_sha256"):
            why.append("probe_code_sha256 absent")
        if not co.typed_worker(wk):
            why.append("worker identity untyped")
        else:
            if (wk["pid"], wk["create_time"]) != (block["worker"]["pid"], block["worker"]["create_time"]):
                why.append("worker identity differs from the block's loaded instance")
            if block.get("manifest_worker") and wk != block["manifest_worker"]:
                why.append("worker identity differs from the block's first manifest")
            if wk["registry_sha256"] != self.ops.overlay_sha():
                why.append("worker registry_sha256 differs from the overlay")
        if man.get("transport_abort"):
            why.append("manifest already records transport_abort")
        return why

    def _barrier(self, att, leg, block, st, t_spawn):
        mp = Path(leg["out"]).with_suffix(".manifest.json")
        man = None
        try:
            man = json.loads(mp.read_text())
        except (OSError, ValueError):
            pass
        if not man or not man.get("run_id") or man["run_id"] in self.seen_run_ids:
            return
        why = self.verify_manifest(man, leg, block)
        self.seen_run_ids.add(man["run_id"])
        att["run_id"] = man["run_id"]
        if why:
            st["reasons"] = why
            self.log(f"BARRIER MISMATCH {leg['stem']}: {'; '.join(why)} -- no ack")
            return
        if self.a.probe_code_sha is None and self.pinned.get("probe_code_sha256") is None:
            self.pinned["probe_code_sha256"] = (man["runtime"] or {}).get("probe_code_sha256")
            self.log(f"pilot: probe_code_sha256 pinned from first manifest {self.pinned['probe_code_sha256']}")
        block["manifest_worker"] = block.get("manifest_worker") or man["worker"]
        Path(att["ack"]).write_text("ack\n")
        st["barrier_done"] = True
        att["worker_full"] = man["worker"]
        self.log(f"BARRIER ok {leg['stem']} run_id={man['run_id']}: ack created")

    # -- supervise
    def evidence_root(self, leg, att):
        if not att.get("run_id"):
            return None
        return Path(self.ops.wd) / "opencode_transcripts" / leg["model"] / f"{Path(leg['out']).stem}.{att['run_id']}"

    def _signals(self, att, leg, block):
        """Activity inputs for the idle predicate and the escalation re-evaluation."""
        root = self.evidence_root(leg, att)
        ev = dir_bytes(root) if root and root.exists() else 0
        out = Path(leg["out"])
        try:
            s = out.stat()
            rows_sig = (s.st_size, s.st_mtime_ns)
        except OSError:
            rows_sig = None
        metrics = self.ops.worker_metrics()
        ident = self.ops.worker_ident(leg["model"])
        key = (ident["pid"], ident["create_time"]) if ident else None
        if key and key != (block["worker"]["pid"], block["worker"]["create_time"]):
            self.log("ALARM worker identity changed during the leg")
            key = None
        return dict(events_bytes=ev, rows_sig=rows_sig, metrics=metrics, ident=key)

    def _cancel(self, att, st, reason, hb, leg, tcoop=None):
        Path(att["cancel"]).write_text(reason + "\n")
        t = tcoop if tcoop is not None else co.t_coop(hb.last_prompt(), leg["lang"]) * self.tm.t_coop_scale
        st["cancel_at"], st["tcoop"], st["stage"] = self.clock(), t, 0
        st["deadline"] = st["cancel_at"] + t
        st["base"] = None
        st["cancel_reason"] = reason
        if reason == "STOP":
            st["stop"] = True
        self.log(f"CANCEL file written ({reason}) for {Path(att['cancel']).name}; T_coop={t:.0f}s "
                 f"(last_prompt_tokens={hb.last_prompt()}, lang={leg['lang']})")

    def _escalate(self, att, proc, st, hb, leg, block):
        now = self.clock()
        hb.poll()
        if st["base"] is None:
            st["base"], st["base_hb"] = self._signals(att, leg, block), hb.line
        if now < st["deadline"]:
            return
        cur = self._signals(att, leg, block)
        fl = co.in_flight(cur["metrics"]) if cur["metrics"] is not None else None
        if cur["ident"] is None or fl is None:
            self.listing(att, leg)
            raise co.ChainAbort("restart refused: worker identity drift or unreadable metrics at escalation; "
                                "no signal sent")
        resumed = (cur["events_bytes"] != st["base"]["events_bytes"] or cur["rows_sig"] != st["base"]["rows_sig"]
                   or fl != 0 or hb.line != st["base_hb"])
        if resumed:
            self.log(f"ESCALATION HELD (stage {st['stage']}): activity resumed (events/rows/heartbeat changed or "
                     f"in_flight={fl}); waiting another {st['tcoop']:.0f}s")
            st["base"], st["base_hb"], st["deadline"] = cur, hb.line, now + st["tcoop"]
            return
        if st["stage"] == 0:
            self.log(f"ESCALATE SIGTERM probe pid {proc.pid} (cleanup-only path)")
            os.kill(proc.pid, signal.SIGTERM)
            st["stage"], st["deadline"] = 1, now + self.tm.term_wait_s
        elif st["stage"] == 1:
            self.log(f"ESCALATE SIGKILL probe pid {proc.pid}")
            os.kill(proc.pid, signal.SIGKILL)
            st["stage"], st["deadline"] = 2, now + self.tm.kill_wait_s
        else:
            raise co.ChainAbort(f"probe pid {proc.pid} survived SIGKILL")
        st["base"], st["base_hb"] = cur, hb.line

    def supervise(self, att, proc, leg, step, block):
        clock, tm = self.clock, self.tm
        t0 = clock()
        hb = Heartbeat(att["log"], clock, t0)
        idle = co.IdlePredicate(tm.idle_sample_s, tm.hb_age_s, tm.idle_needed)
        st = dict(barrier_done=False, reasons=None, cancel_at=None, tcoop=None, stage=0, deadline=None, base=None,
                  stop=False, cancel_reason=None)
        halt = threading.Event()

        def loop():
            while not halt.wait(tm.watch_s):
                try:
                    self.stop_requested()
                    self.watch_tick(att, leg, step, block, hb, st, t0)
                except Exception as e:  # noqa: BLE001
                    self.log(f"WATCH error {type(e).__name__}: {e}")

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        last_idle = t0
        try:
            while proc.poll() is None:
                now = clock()
                hb.poll()
                if not st["barrier_done"] and st["reasons"] is None:
                    self._barrier(att, leg, block, st, t0)
                    if st["reasons"] is not None:
                        self._cancel(att, st, "barrier mismatch", hb, leg, tcoop=tm.barrier_exit_wait_s)
                if st["cancel_at"] is None and self.stop_requested():
                    self._cancel(att, st, "STOP", hb, leg)
                if st["cancel_at"] is None and st["barrier_done"] and now - last_idle >= tm.idle_sample_s:
                    last_idle = now
                    sg = self._signals(att, leg, block)
                    if idle.sample(now, hb_age=hb.age(), **sg):
                        hb.poll()
                        if idle.recheck(hb_age=hb.age(), **self._signals(att, leg, block)):
                            self._cancel(att, st, "idle", hb, leg)
                        else:
                            self.log("idle predicate recheck failed: activity resumed, no cancel")
                if st["cancel_at"] is not None:
                    self._escalate(att, proc, st, hb, leg, block)
                time.sleep(tm.poll_s)
        finally:
            halt.set()
            th.join(5)
        state = "barrier_mismatch" if st["reasons"] else ("cancelled" if st["cancel_at"] is not None else "exited")
        return dict(state=state, reasons=st["reasons"] or [], stop=st["stop"], cancel_reason=st["cancel_reason"])

    # -- watcher
    def watch_tick(self, att, leg, step, block, hb, st, t0):
        ids = [f"{leg['lang']}/{x}" for x in step["names"]]
        try:
            rows = [r for r in self.ops.rows(leg["out"]) if r.get("id") in ids]
        except Exception:  # noqa: BLE001
            rows = []
        n, total = len(rows), len(ids)
        walls = [r.get("wall_s") or 0 for r in rows]
        mean = sum(walls) / n if n else None
        key = (leg["lang"], leg["model"])
        if key in self.explicit_pred:
            pred = self.explicit_pred[key]
        elif n >= PILOT_N:
            pred = sum(walls[:PILOT_N]) / PILOT_N       # default: the pilot mean once >= 5 rows exist
        else:
            pred = self.pred.get(key, 250)
        m = mean if mean is not None else pred
        remaining = total - n
        eta = remaining * m
        ratio = (eta / (remaining * pred)) if remaining and pred else (m / pred if pred else 0)
        kinds = {}
        for r in rows:
            k = r.get("nonconv_kind") or "ok"
            kinds[k] = kinds.get(k, 0) + 1
        conv = (sum(bool(r.get("converged")) for r in rows) / n) if n else None
        toks = [((r.get("gate") or {}).get("output_tokens_completed") or 0) for r in rows]
        bhits = sum(1 for r in rows if "budget" in str(r.get("nonconv_kind")) or "budget" in str(r.get("nonconv_flags")))
        ps = self.ops.power_state()
        free = self.ops.free_mem_mb()
        hb.poll()
        w = hb.watch()
        elapsed = self.clock() - t0
        alarm = co.alarm_s(remaining, m, max(walls) if walls else 0)
        try:
            logtext = Path(att["log"]).read_text(errors="replace")
        except OSError:
            logtext = ""
        aborts = "TransportAbort" in logtext or "REFUSED" in logtext
        flags = []
        if ratio > 1.5 or aborts:
            flags.append("CORRECTION?")
        if elapsed > alarm:
            flags.append(f"ALARM elapsed={elapsed:.0f}s>{alarm:.0f}s")
        if not st["barrier_done"] and elapsed > self.tm.manifest_alarm_s and st["reasons"] is None:
            flags.append(f"ALARM manifest missing/unacked after {elapsed:.0f}s")
        self.log(
            f"WATCH {leg['stem']} a{att['attempt']}: {n}/{total} passed={sum(bool(r.get('passed')) for r in rows)} "
            f"mean={m:.0f}s eta={eta/60:.0f}min pred={pred:.0f}s ratio={ratio:.2f} kinds={kinds} "
            f"conv={'n/a' if conv is None else f'{conv:.0%}'} out_tok_p50/p90/max={quantile(toks,.5)}/{quantile(toks,.9)}/"
            f"{max(toks) if toks else None} budget_hits={bhits} adapter={ps['watts']}W {ps['volts']}V "
            f"batt={ps['batt']}% free_mem_mb={free} hb_age={hb.age():.0f}s hb={json.dumps(w, sort_keys=True)} "
            f"hb_elapsed={hb.data.get('elapsed_s')} {' '.join(flags)}".rstrip())


# --------------------------------------------------------------------------- entry
def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["pilot", "chain"])
    ap.add_argument("sessions", nargs="*")
    ap.add_argument("--pred-s", action="append", default=[], metavar="LANG:MODEL=SECONDS")
    ap.add_argument("--arm-idle-s", type=float, default=600.0)
    ap.add_argument("--probe-code-sha")
    ap.add_argument("--out-root")
    ap.add_argument("--probe", default=str(REPO / "benchmark/run_opencode_probe_v2.py"))
    ap.add_argument("--python", default=str(REPO / ".venv-bench/bin/python"))
    ap.add_argument("--universe")
    a = ap.parse_args(argv)
    if a.mode == "chain":
        if not a.probe_code_sha:
            ap.error("--probe-code-sha is required for chain")
        a.sessions = a.sessions or ["s1", "s2", "reload"]
        bad = [s for s in a.sessions if s not in LEGS]
        if bad:
            ap.error(f"unknown session {bad}")
    return a


def main(argv=None, ops=None, timers=None, log_out=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    wd = Path(ops.wd) if ops is not None else Path(os.environ["STACK_WORKDIR"])
    out_root = Path(a.out_root or wd / "c147")
    out_root.mkdir(parents=True, exist_ok=True)
    log = co.RunLog(out_root / "RUNLOG.md", out=log_out)
    if ops is None:
        overlay = os.environ.get("C147_OVERLAY") or str(wd / "c147/overlay_c147_draft_off.yaml")
        ops = co.ChainOps(REPO, wd, overlay, log)
    chain = Chain(a, ops, timers or Timers(), log, load_universe(a.universe), out_root)
    try:
        return chain.run()
    except BaseException:
        chain.rc = 1
        chain.write_json("crashed")
        raise


if __name__ == "__main__":
    sys.exit(main())
