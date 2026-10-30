"""P426 B2 frozen tests, delivery 1d: fixtures for the §16.5 seams (spec v3.2). TESTS ONLY.

Builds on the frozen `b2_frozen_support` (imported, never changed). Every fixture here is in the real format of the code it
stands for (sources cited) and is validated on the baseline by `test_b2_frozen_add_support_check.py`."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

from bench.tests import b2_frozen_support as S

GOOD_POWER = {"watts": 140, "volts": 28, "battery": 80, "on_battery_intervals": []}    # §16.4 `power()` / bench_watch
SHARED_ENV = {"HOME": "/Users/op", "STACK_WORKDIR": "/wd", "HF_TOKEN": S.FAKE_SECRET_40, "PWD": "/x",
              "MLX_VLM_CACHE_SESSION_MAX": "1"}                                       # one box: both legs of a pair


# ------------------------------------------------------------------------------------------------ the world + §16.5 seams
def world(tmp_path, monkeypatch, *, arm="off", out_name=None, shared_env=True, busy=(), descendants=(), rehearsal=False):
    """`b2_frozen_support.p426_world` + the §16.5 ChainOps seams: `expected_worker_argv(registry_path, model)` (mlx-serve's
    builder, `b2_frozen_support.served_worker_argv`), `busy_procs()` (`ChainOps.busy_procs`: `"<pid> <command>"` lines,
    chain_ops.py:335-347) and `descendants(pid) -> set[int]`. With `shared_env` the probe / router / worker environment is
    one box's (two worlds of a pair then differ only by their canonicalized roots)."""
    env = S.p426_world(tmp_path, monkeypatch, arm=arm, out_name=out_name, rehearsal=rehearsal)
    ops = env["ops"]
    ops.expected_worker_argv = lambda registry_path, model: S.served_worker_argv(registry_path, model)
    env["busy"], env["descendants"] = list(busy), set(descendants)
    ops.busy_procs = lambda: list(env["busy"])
    ops.descendants = lambda pid: set(env["descendants"])
    # `(pid, start)` of the owned processes as the census reads them: the worker's start is its load identity, the router's 1.0
    ops.create_time = lambda pid: ops.ident["create_time"] if ops.ident and pid == ops.ident["pid"] else 1.0
    if shared_env:
        wt = env["wt"]
        ops.proc_environ = lambda pid: dict(SHARED_ENV, MLX_SERVE_CONFIG=str(wt / "main_models.yaml"))
    return env


def pair_argv(env, mode=("pilot",), *, extra=()):
    """`b2_frozen_support.p426_argv` + `extra` flags (e.g. `--pair-receipt <path>`, §16.5). C238: no key, no `--hmac-fd`.
    Returns (argv, None)."""
    argv, _ = S.p426_argv(env, mode)
    return argv + list(extra), None


a4_gate_doc = S.a4_gate_doc                   # the frozen builder (gate.json, session_pinning_gate.py:284-304)


# ------------------------------------------------------------------------------------------------ RECORD fixture trees
def _record_digest(data):
    """A `RECORD` digest as pip writes it: `sha256=` + urlsafe base64 without padding (PEP 376 / the venv's RECORDs)."""
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def site_tree(root, *, worktree, files=None):
    """A fixture `site-packages` with one installed distribution (`fakepkg 1.0`: METADATA, INSTALLER, RECORD, a module) and
    one editable distribution (`mlx_serve 0.3.0`: `direct_url.json` `{"url": "file://<worktree>/src/mlx-serve",
    "dir_info": {"editable": true}}` as the bench venv's, and a `__editable__` .pth). Returns the tree root."""
    root = Path(root)
    pkg = files or {"fakepkg/__init__.py": b"VALUE = 1\n", "fakepkg/core.py": b"def f():\n    return 2\n"}
    dist = root / "fakepkg-1.0.dist-info"
    dist.mkdir(parents=True)
    meta = {"fakepkg-1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: fakepkg\nVersion: 1.0\n",
            "fakepkg-1.0.dist-info/INSTALLER": b"uv\n"}
    rows = []
    for rel, data in {**pkg, **meta}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        rows.append(f"{rel},{_record_digest(data)},{len(data)}")
    rows.append("fakepkg-1.0.dist-info/RECORD,,")
    (dist / "RECORD").write_text("\n".join(rows) + "\n")
    ed = root / "mlx_serve-0.3.0.dist-info"
    ed.mkdir()
    (ed / "METADATA").write_text("Metadata-Version: 2.1\nName: mlx-serve\nVersion: 0.3.0\n")
    (ed / "direct_url.json").write_text(json.dumps({"url": f"file://{worktree}/src/mlx-serve", "dir_info": {"editable": True}}))
    pth = root / "__editable__.mlx_serve-0.3.0.pth"
    pth.write_text(f"{worktree}/src/mlx-serve/src\n")
    erows = [f"mlx_serve-0.3.0.dist-info/METADATA,{_record_digest((ed / 'METADATA').read_bytes())},"
             f"{len((ed / 'METADATA').read_bytes())}",
             f"mlx_serve-0.3.0.dist-info/direct_url.json,{_record_digest((ed / 'direct_url.json').read_bytes())},"
             f"{len((ed / 'direct_url.json').read_bytes())}",
             f"__editable__.mlx_serve-0.3.0.pth,{_record_digest(pth.read_bytes())},{len(pth.read_bytes())}",
             "mlx_serve-0.3.0.dist-info/RECORD,,"]
    (ed / "RECORD").write_text("\n".join(erows) + "\n")
    return root


def verify_record(tree, dist_info):
    """Every RECORD entry with a digest re-verified against the installed bytes (the PEP 376 check); returns bad paths."""
    bad = []
    for line in (Path(tree) / dist_info / "RECORD").read_text().splitlines():
        path, digest, _size = line.rsplit(",", 2)
        if digest and _record_digest((Path(tree) / path).read_bytes()) != digest:
            bad.append(path)
    return bad


def chain_ops(tmp_path):
    """A real `ChainOps` (chain_ops.py:225) whose shell / http / process seams are inert (no router, nothing spawned)."""
    from bench import chain_ops as co
    ov = Path(tmp_path) / "ov.yaml"
    ov.write_text(S.registry_text((S.MODEL,)))
    # rebase-amendment P520 (S′): `registry=` the synthetic file; before, ChainOps defaulted to `<repo>/main_models.yaml`,
    # the LIVE registry (chain_ops.py:239), which no test may read
    return co.ChainOps(S.REPO, tmp_path, ov, co.RunLog(Path(tmp_path) / "RL.md", out=lambda m: None), registry=ov,
                       sh=lambda *a, **k: co.Result(""), http=lambda *a, **k: b"{}",
                       popen=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no process may be spawned")),
                       sleep=lambda s: None, create_time=lambda p: 1.0, kill=lambda p, s: None, killpg=lambda p, s: None)


# ------------------------------------------------------------------------------------------------ the sequencer fakes (§16.4-16.5)
class Clock:
    def __init__(self, t=1_800_000_000.0, on_sleep=None):
        self.t, self.sleeps, self.on_sleep = t, 0, on_sleep

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps += 1
        self.t += max(float(s), 0.001)
        if self.on_sleep:
            self.on_sleep(self)


def arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


class SeqOps:
    """`p426_wave2.main(argv, ops=…)`'s ops (§16.4): `launch(argv, *, cwd, pass_fds) -> handle`, `wait(handle) -> rc`,
    `alive(pid, start) -> bool`, `power() -> dict`, `harvest(leg_root, *, emails) -> {rc, harvest_json, harvest_sha256}`,
    `publish_dossier(path, *, emails)`, `publish_run_files(paths, *, emails)` ([d2] §16.6). A chain launch (argv with `--p426`) is a fake
    chain writes the leg's artifacts in the frozen formats (chain.json with
    `status` / `rc` / `p426_ledger` / `p426_dnf` / `p426_invalid` (§16.5), the §16.1 receipt / ready / item records, rows with
    `wall_s`, `log_bounds.json`); a watcher launch (argv with `--chain-json`) writes `watch.jsonl` (§16.1). `script[leg]` sets
    rc / dnf / runtime_s / watcher_dies / engaged / status / elapsed_s / shape; a handle carries `pid`, `start`, `argv`.
    post-reveal 3d (§16.8): also `operator_emails()`, `worktree_state(path)`, `identity(path)`, `harvest_path(attempt)` =
    `<main-root>/benchmark/results/p426/wave2/<attempt>/` (the fake harvest writes its `HARVEST.json` there) and
    `historical_walls()` (the sequencer's timeout amendment goes through `p426_freeze` with these ops)."""

    def __init__(self, clock, script=None, *, main_root, emails=(), walls=None):
        self.clock, self.script = clock, dict(script or {})
        self.main_root, self.emails = Path(main_root), list(emails)
        self.walls = dict(walls or dict(w_python_s=300.0, w_go_s=200.0, max_request_elapsed_s=100.0))
        self.launches, self.harvested, self.waits, self.harvest_emails = [], [], [], []
        self.dossiers, self.run_files = [], []
        self.next_pid = 5000
        self.handles = []

    # -- §16.8 seams
    def operator_emails(self):
        return list(self.emails)

    def worktree_state(self, path):
        """The arm worktree at the v8 base's commit, clean, at the base gitlinks (`b2_frozen_support.v8_base`)."""
        head = S.OFF_COMMIT if "off" in Path(path).name else S.ON_COMMIT
        return dict(head=head, clean=True, gitlinks=dict(S.BASE_GITLINKS))

    def identity(self, path):
        base = S.v8_base()
        return {k: base[k] for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}

    def harvest_path(self, attempt):
        return self.main_root / "benchmark/results/p426/wave2" / str(attempt)

    def historical_walls(self):
        return dict(self.walls)

    def _leg_of(self, argv):
        root = arg(argv, "--out-root")
        return Path(root).name.rsplit(".a", 1)[0] if root else None

    def launch(self, argv, *, cwd=None, pass_fds=()):
        argv = [str(a) for a in argv]
        self.next_pid += 1
        h = SimpleNamespace(pid=self.next_pid, start=self.clock.t, argv=argv, cwd=cwd, pass_fds=tuple(pass_fds), kind=None,
                            end=self.clock.t, rc=0, waited=False)
        if "--p426" in argv:
            h.kind = "chain"
            leg = self._leg_of(argv)
            sc = self.script.get(leg, {})
            h.rc, h.end = sc.get("rc", 0), self.clock.t + sc.get("runtime_s", 300.0)
            write_leg(Path(arg(argv, "--out-root")), leg, argv, sc)
        elif "--chain-json" in argv:
            h.kind = "watcher"
            leg_root = Path(arg(argv, "--chain-json")).parent
            sc = self.script.get(leg_root.name.rsplit(".a", 1)[0], {})
            chain = next((x for x in reversed(self.handles) if x.kind == "chain"), None)
            h.end = (self.clock.t + 1.0) if sc.get("watcher_dies") else (chain.end if chain else self.clock.t)
            write_watch(Path(arg(argv, "--out")), dies=sc.get("watcher_dies", False))
        self.launches.append(h)
        self.handles.append(h)
        return h

    def chain_launches(self):
        return [h for h in self.launches if h.kind == "chain"]

    def wait(self, handle):
        self.waits.append(handle)
        handle.waited = True
        if self.clock.t < handle.end:
            self.clock.t = handle.end
        return handle.rc

    def alive(self, pid, start):
        h = next((x for x in self.handles if x.pid == pid), None)
        return bool(h) and not h.waited and self.clock.t < h.end and start == h.start

    def power(self):
        return dict(GOOD_POWER)

    def harvest(self, leg_root, *, emails=()):
        """[d2] §16.6: `ops.harvest(leg_root, *, emails) -> {rc, harvest_json, harvest_sha256}`; a fake `HARVEST.json` (self-hashed)
        is written at `harvest_path(<attempt>)/HARVEST.json` (post-reveal 3d, §16.8) so its sha256 can be checked where the
        sequencer cites it (the pair dossier)."""
        self.harvested.append(str(leg_root))
        self.harvest_emails.append(tuple(emails))
        root = Path(leg_root)
        doc = S.self_hashed(dict(leg=root.name.rsplit(".a", 1)[0], attempt=int(root.name.rsplit(".a", 1)[1]), state="VALID",
                                 files=[], created="t"))
        hj = self.harvest_path(root.name) / "HARVEST.json"
        hj.parent.mkdir(parents=True, exist_ok=True)
        hj.write_text(json.dumps(doc))
        return {"rc": self.script.get("__harvest_rc__", 0), "harvest_json": str(hj),
                "harvest_sha256": hashlib.sha256(hj.read_bytes()).hexdigest()}

    def publish_dossier(self, path, *, emails=()):
        """[d2] §16.6: `ops.publish_dossier(path, *, emails)` (`p426_harvest.publish_dossier`), returns like `harvest`."""
        self.dossiers.append((str(path), tuple(emails)))
        return {"rc": 0, "harvest_json": None, "harvest_sha256": None}

    def publish_run_files(self, paths, *, emails=()):
        """[d2] §16.6 / §16.7: `ops.publish_run_files(paths, *, emails)`; `paths` are files (the frozen records, `sequence.json`)."""
        self.run_files.append(([str(p) for p in paths], tuple(emails)))
        return {"rc": 0, "harvest_json": None, "harvest_sha256": None}


def slot_file(slot):
    """§16.1: the slot with `|` -> `__` and `/` -> `--` (the fixture's own copy: `chain_rows.slot_file` arrives with s3)."""
    return slot.replace("|", "__").replace("/", "--")


def _slot(session, lang, item):
    from bench import chain_rows as cr
    return cr.slot_for(f"tg1-p426|oc|{S.MODEL}|{session}|{lang}", f"{lang}/{item}")


LEG_SHAPE = {"pilot": [("python", 5)], "reload": [("python", 5)], "s1": [("python", 22), ("go", 21)],
             "s2": [("go", 21), ("python", 22)]}                  # §1: the realized ledger equals the leg's plan (§5.1)
SESSION_SEED = {"pilot": 1001, "s1": 1001, "reload": 1001, "s2": 2002}


def _sealed(path, doc):
    """post-reveal 3c: ready / item / DNF records are immutable self-hashed records (§16 classes); written sealed."""
    path.write_text(json.dumps(S.self_hashed(doc), sort_keys=True))
    return path


def _plan(session, argv, shape=None):
    """[(session_of_items, lang, [items])] of the leg: §1's shape (or `shape`), or the canonical occurrences file of a make-up
    leg."""
    if shape is not None:
        return [(session, lang, [f"{lang[0]}{i}" for i in range(1, n + 1)]) for lang, n in shape]
    if session == "makeup":
        occ = arg(argv, "--occurrences")
        groups = {}
        for line in (Path(occ).read_text().splitlines() if occ and Path(occ).exists() else []):
            if line.strip():
                o = json.loads(line)
                groups.setdefault((o["session"], o["language"]), []).append(o["item"])
        return [(s, lang, items) for (s, lang), items in groups.items()] or [("s1", "python", ["p1", "p2"])]
    return [(session, lang, [f"{lang[0]}{i}" for i in range(1, n + 1)]) for lang, n in LEG_SHAPE[session]]


def write_leg(root, leg, argv, sc):
    """The artifacts a P426 chain leaves in its out-root, in the frozen formats: §16.1 records (sealed), the §16.5 ledger keys,
    a ledger of the leg's full plan (post-reveal 3c: §1 sizes; it was 5 items for every leg)."""
    root.mkdir(parents=True, exist_ok=True)
    arm = "on" if arg(argv, "--predictor") == "mtp" else "off"
    session = (argv[argv.index("chain") + 1] if "chain" in argv else "makeup" if "makeup" in argv else "pilot")
    dnf_n = sc.get("dnf", 0)
    ledger, dnf, invocations, blocks = [], [], [], []
    (root / "items").mkdir(exist_ok=True)
    engaged = sc.get("engaged", True)
    k = 0
    for item_session, lang, items in _plan(session, argv, sc.get("shape")):
        rows = []
        stem = f"{S.MODEL}.{session}.opencode_{lang}"
        blocks.append(dict(session=item_session, model=S.MODEL, seed_base=SESSION_SEED.get(item_session, 1001),
                           pilot_only=session == "pilot",
                           legs=[dict(lang=lang, stem=stem, pilot_names=list(items), full_names=list(items),
                                      invocations=[dict(phase="pilot" if session == "pilot" else "full", names=list(items),
                                                        limit=len(items), expect=[f"{lang}/{i}" for i in items])])]))
        for item in items:
            slot = _slot(session, lang, item)
            kind = "dnf" if k < dnf_n else "row"
            ledger.append(dict(slot=slot, kind=kind, invocation=len(invocations) + (1 if kind == "dnf" else dnf_n), index=k))
            # post-reveal 3h (§16.8): `dnf_engaged` = whether a DNF item's completed requests carry the ON counters
            on_counters = engaged if kind == "row" else sc.get("dnf_engaged", engaged)
            req = dict(session=f"ses_{k:026d}", backend="cached_session", prompt_tokens=3000 + k, generated_tokens=120,
                       decode_tok_s=50.0, error=None, elapsed_s=float(sc.get("elapsed_s", 100.0)),   # 3d (§16.8): elapsed
                       **(S.draft_counters(30, 60, 40) if arm == "on" and on_counters else
                          dict(draft_rounds=None, draft_n=None, draft_n_accepted=None, draft_kind=None)))
            ready = _sealed(root / "items" / (slot_file(slot) + ".ready.json"), dict(slot=slot, item=f"{lang}/{item}", k=k))
            ready_sha = json.loads(ready.read_text())["sha256"]
            if kind == "dnf" and sc.get("dnf_ready") == "missing":       # post-reveal 3i (§16.8): a DNF without its ready record
                ready.unlink()
            rec = dict(slot=slot, ready_sha256=ready_sha,                  # 3h (§16.8): the ready self-hash
                       log_range=dict(start=0, end=100, sha256="1" * 64), worker_before=S.summary(), worker_after=S.summary(),
                       case="dnf_boundary" if kind == "dnf" else "completed", requests=[req],
                       totals=dict(requests=1, prompt_tokens=3000 + k, generated_tokens=120, decode_s=2.4,
                                   accepted=req["draft_n_accepted"] or 0, proposed=req["draft_n"] or 0),
                       checks={"equalities": {"ok": True, "detail": ""}}, verdict="reconciled")
            _sealed(root / "items" / (slot_file(slot) + (".dnf.json" if kind == "dnf" else ".json")), rec)
            if kind == "dnf":
                # post-reveal 3h (§16.8 after the strict verify round 1): sealed (immutable), with `load`
                dnf.append(S.self_hashed(dict(slot=slot, item=f"{lang}/{item}", session=session, language=lang,
                                              seed=SESSION_SEED.get(item_session, 1001), arm=arm, pick=S.MODEL,
                                              attempt=int(root.name.rsplit(".a", 1)[1]), invocation=0, load=0, load_gen=1,
                                              abort=dict(cause="connection", error="x", evidence=None),
                                              item_record=f"items/{slot_file(slot)}.dnf.json")))
            else:
                rows.append(dict(id=f"{lang}/{item}", wall_s=100.0 * (k % 5 + 1), passed=True, converged=True))
            k += 1
        rel = f"{session}/{stem}.L{len(invocations)}.{'pilot' if session == 'pilot' else 'full'}.a1.jsonl"
        (root / session).mkdir(exist_ok=True)
        (root / rel).write_text("".join(json.dumps(r) + "\n" for r in rows))
        invocations.append(dict(file=rel, status="validated", phase="pilot" if session == "pilot" else "full",
                                expected_slots=[_slot(session, lang, i) for i in items]))
    if sc.get("drop_slots"):                                     # a realized ledger short of its frozen schedule (§5.1)
        ledger = ledger[:len(ledger) - int(sc["drop_slots"])]
    # post-reveal 3d (§16.8): the leg's frozen schedule (`<out-root>/schedule.json`, the `schedules.tg1` shape) — the plan the
    # sequencer reads; `chain.json` names it by `schedule_sha256`
    from bench import schedules
    schedule = dict(schema=schedules.SCHEMA, builder="tg1", mode="pilot" if session == "pilot" else "chain", smoke=False,
                    predictor="mtp" if arm == "on" else "off", picks=[S.MODEL], blocks=blocks)
    (root / "schedule.json").write_text(json.dumps(schedule, sort_keys=True, indent=1) + "\n")
    (root / "chain.json").write_text(json.dumps(dict(
        status=sc.get("status", "finished"), rc=sc.get("rc", 0), p426_ledger=ledger, p426_dnf=dnf,
        p426_invalid=sc.get("invalid", []), schedule_sha256=schedules.schedule_sha256(schedule),
        progress=dict(invocations=invocations))))
    S.write_record(root / "receipt.json", S.arm_receipt_doc(arm))
    (root / "log_bounds.json").write_text(json.dumps(dict(files=[], created="t0", finalized="t1")))


def write_watch(path, *, dies):
    """`<out-root>/watch.jsonl` (§16.1): one JSON line per tick, then one `exit_state` line (absent when the watcher died)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # post-reveal 3e (s6 P52 ruling): a tick carries `t` in epoch seconds; `interval_s` as the watcher records it (§8 gap rule)
    t0, step = 1_800_000_000.0, 300.0
    ticks = [dict(t=t0 + i * step, at=f"t{i}", interval_s=step, watts=140, volts=28, battery=80, driver_alive=True)
             for i in range(3)]
    lines = ticks[:1] if dies else ticks + [dict(exit_state="driver_exited", t=t0 + 3 * step, interval_s=step,
                                                 battery_intervals=[])]
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))


def sequencer_records(tmp_path):
    """`--record-dir`: `v8_base.json` (§16.1 recipe; the sequencer later adds `amendment.json`, §16.5)."""
    d = Path(tmp_path) / "records"
    S.write_record(d / "v8_base.json", S.v8_base(off_worktree="$STACK_WORKDIR/stack-p426-off",      # post-reveal 3c: the
                                                 on_worktree="$STACK_WORKDIR/stack-p426-on"))      # seq_argv worktrees
    return d


def seq_argv(tmp_path, cmd="run", *extra):
    """post-reveal 3c: the worktrees lie under `$STACK_WORKDIR` (`<tmp>/wd`, as the records name them, §16.7) and a rehearsal's
    out-base under `$STACK_WORKDIR/p426/rehearsal/` (§1: a rehearsal writes only there)."""
    off, on = Path(tmp_path) / "wd/stack-p426-off", Path(tmp_path) / "wd/stack-p426-on"
    off.mkdir(parents=True, exist_ok=True)
    on.mkdir(parents=True, exist_ok=True)
    base = [cmd]
    if cmd in ("run", "makeup"):
        base += ["--record-dir", str(Path(tmp_path) / "records")]
    out_base = Path(tmp_path) / ("wd/p426/rehearsal" if cmd == "rehearsal" else "wd/p426/wave2")
    base += ["--worktree-off", str(off), "--worktree-on", str(on), "--out-base", str(out_base)]
    extra = list(extra)
    if cmd == "rehearsal":                       # post-reveal 3d (§16.8): `rehearsal` requires `--frozen-prompt-date`
        if "--no-frozen-prompt-date" in extra:   # (a test's marker for omitting it)
            extra.remove("--no-frozen-prompt-date")
        else:
            base += ["--frozen-prompt-date", S.EPOCH_DATE]
    return base + extra, dict(off=off, on=on)


def run_sequencer(argv, ops, clock, timeout=120):
    """`p426_wave2.main(argv, ops=…, clock=…, sleep=…)` in a thread; rc (or the refusal's exit code) and its stderr."""
    import io
    from contextlib import redirect_stderr
    res, err = {}, io.StringIO()

    def target():
        from bench import p426_wave2
        try:
            with redirect_stderr(err):
                res["rc"] = p426_wave2.main(list(argv), ops=ops, clock=clock.clock, sleep=clock.sleep)
        except SystemExit as e:
            res["rc"] = e.code if isinstance(e.code, int) else 2
        except BaseException as e:  # noqa: BLE001
            res["exc"] = e
    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        raise AssertionError("the sequencer did not finish")
    if "exc" in res:
        raise res["exc"]
    return res["rc"], err.getvalue()


def is_subsequence(small, big):
    it = iter(big)
    return all(any(x == y for y in it) for x in small)
