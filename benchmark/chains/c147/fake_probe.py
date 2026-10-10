"""Fake tg1 probe implementing the recorded runner/probe CONTRACT (C147 spec 3). TESTS ONLY.

Honours: manifest written (atomic) BEFORE item one, then blocks until the ack file exists (<= FAKE_PROBE_ACK_WAIT s,
default 300; no ack -> nonzero exit having generated nothing); rows file rewritten atomically, existing ids skipped;
heartbeat JSON lines with key "m62_watch"; cooperative cancel file; SIGTERM -> cleanup-only exit 143; refuses to
start when the cancel or ack file already exists; rc 0 only when every expected item has a row and nothing aborted.

Knobs (environment): FAKE_PROBE_BEHAVIOUR = normal | hang_after_manifest | hang_in_item | no_manifest | abort_after_n |
stale_heartbeat_growing_events | ignore_cancel; FAKE_PROBE_PLAN = JSON list of behaviours consumed per invocation
(needs FAKE_PROBE_STATE, a directory; the last entry repeats); FAKE_N, FAKE_ITEM_S, FAKE_HB_S, FAKE_TICK_S,
FAKE_IGNORE_TERM=1, FAKE_CLEANUP_UNCERTAIN=1, FAKE_MANIFEST_OVERRIDE (JSON merged into the manifest, dotted keys),
FAKE_PROBE_CODE_SHA, FAKE_REGISTRY_SHA. The worker identity comes from $FAKE_PROBE_STATE/worker.json.
"""
import argparse
import hashlib
import json
import os
import signal
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench import rowschema  # noqa: E402

CAMPAIGN = "ba86ba16e40e5e7b3535d64de2de9e95b323158049358b1f41b2ed26a83bb15c"
SCAFFOLD = "opencode-v2-web-tg1"
SERVING = {"src/mlx-vlm": "5" * 64, "src/mlx-serve": "6" * 64}


def _atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def seed_overlay_sha(model, seed):
    ov = {"providers": {"mlx-local": {"models": {model: {"body": {"seed": int(seed)}}}}}}
    return hashlib.sha256(json.dumps(ov, sort_keys=True).encode()).hexdigest()


def build_manifest(model, lang, seed_base, worker, run_id, override=None):
    h = lambda c: c * 64  # noqa: E731
    man = {
        "model": model, "run_id": run_id, "worker": worker, "sampling_profile": "deployed",
        "git": {"serving_path": dict(SERVING)}, "registry": {"sha256": os.environ.get("FAKE_REGISTRY_SHA", h("a"))},
        "runtime": {
            "scaffold": SCAFFOLD, "scaffold_policy_sha256": CAMPAIGN,
            "probe_code_sha256": os.environ.get("FAKE_PROBE_CODE_SHA", h("9")), "opencode_version": "2.0.20",
            "opencode_exe_sha256": h("e"), "opencode_bench_config_sha256": h("c"), "carrier_source_sha256": h("d"),
            "agent_system_sha256": None, "polyglot_sha": "1" * 40, "universe_sha256": h("2"),
            "seed_base": seed_base, "lang": lang, "draft_kind": "off", "sampling_profile": "deployed",
        },
    }
    for dotted, value in (override or {}).items():
        d = man
        parts = dotted.split(".")
        for k in parts[:-1]:
            d = d[k]
        d[parts[-1]] = value
    return man


def _evidence_dir(wd, model, out, run_id, item):
    lang, name = item.split("/", 1)
    return Path(wd) / "opencode_transcripts" / model / f"{Path(out).stem}.{run_id}" / f"{lang}__{name}"


def _portable(wd, p):
    return "$STACK_WORKDIR" + str(p)[len(str(wd)):]


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_row(model, item, seed_base, worker, wd, out, run_id, wall_s=1.0, events_extra=b""):
    ev = _evidence_dir(wd, model, out, run_id, item)
    ev.mkdir(parents=True, exist_ok=True)
    files = {"events": ev / "events.jsonl", "stderr": ev / "stderr.txt", "export": ev / "export.json"}
    if not files["events"].exists():
        files["events"].write_bytes(b'{"type":"step_finish"}\n' + events_extra)
    files["stderr"].write_bytes(b"")
    files["export"].write_text(json.dumps({"id": item}))
    names = ("report.xml", "stdout.txt", "stderr.txt") if item.startswith("python/") else ("go.jsonl", "go.stderr")
    arts = {}
    for n in names:
        f = ev / "grades" / n
        f.parent.mkdir(exist_ok=True)
        f.write_text("ok " + n)
        arts[n] = {"path": _portable(wd, f), "sha256": _sha(f)}
    seed = rowschema.sample_seed(item, 0, seed_base)
    return {
        "id": item, "model": model, "sample": 0, "sample_seed": seed, "passed": True, "converged": True,
        "nonconv_kind": None, "nonconv_flags": [], "wall_s": wall_s, "worker_before": worker,
        "worker_after": worker, "overlay_sha256": seed_overlay_sha(model, seed), "scaffold": SCAFFOLD,
        "evidence_sha256": {k: _sha(v) for k, v in files.items()},
        "events_path": _portable(wd, files["events"]), "transcript_path": _portable(wd, files["export"]),
        "stderr_path": _portable(wd, files["stderr"]),
        "grade_reports": [{"boundary": 1, "seq": 1, "final": True, "outcome": "parsed",
                           "artifacts": arts}],
        "gate": {"output_tokens_completed": 1000, "requests_completed": 5},
    }


def write_leg(out, model, lang, seed_base, ids, worker, wd, run_id="fixture-run", override=None):
    """Complete, valid rows + manifest for tests (the same builders the probe uses)."""
    rows = [build_row(model, i, seed_base, worker, wd, out, run_id) for i in ids]
    _atomic(out, "".join(json.dumps(r) + "\n" for r in rows).encode())
    man = build_manifest(model, lang, seed_base, worker, run_id, override)
    man["cleanup_status"] = {"survivors": [], "containers_remaining": [], "uncertain": False,
                             "orphans_unattributed": []}
    _atomic(Path(out).with_suffix(".manifest.json"), json.dumps(man, indent=2).encode())


# --------------------------------------------------------------------------- the probe
def main(argv=None):
    ap = argparse.ArgumentParser()
    for f in ("--model", "--items", "--lang", "--out", "--scaffold", "--expect-items", "--a4-v2-receipt",
              "--sampling-profile", "--cancel-file", "--manifest-ack", "--tg1-inject", "--chain-total"):
        ap.add_argument(f)
    ap.add_argument("--seed-base", type=int)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    env = os.environ
    state = Path(env["FAKE_PROBE_STATE"]) if env.get("FAKE_PROBE_STATE") else None
    behaviour = env.get("FAKE_PROBE_BEHAVIOUR", "normal")
    if state:
        state.mkdir(parents=True, exist_ok=True)
        counter = state / "count"
        n_inv = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(n_inv + 1))
        with (state / "invocations.jsonl").open("a") as f:
            f.write(json.dumps({"argv": sys.argv[1:], "pid": os.getpid()}) + "\n")
        if env.get("FAKE_PROBE_PLAN"):
            plan = json.loads(env["FAKE_PROBE_PLAN"])
            behaviour = plan[min(n_inv, len(plan) - 1)]
    cancel, ack = Path(a.cancel_file), Path(a.manifest_ack)
    if cancel.exists() or ack.exists():
        print("REFUSED: cancel or ack file already exists", flush=True)
        return 2
    if a.scaffold != SCAFFOLD or not a.expect_items or not a.a4_v2_receipt or a.sampling_profile != "deployed":
        print("REFUSED: bad arguments", flush=True)
        return 2
    wd = env.get("STACK_WORKDIR", "")
    out = Path(a.out)
    mp = out.with_suffix(".manifest.json")
    worker = json.loads((state / "worker.json").read_text()) if state and (state / "worker.json").exists() else {
        "pid": 1, "create_time": 1.0, "model_path": "caslca/" + a.model, "registry_sha256": "a" * 64}
    rows = []
    if out.exists():
        rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
        old = json.loads(mp.read_text()) if mp.exists() else {}
        if old.get("transport_abort"):
            print("REFUSED: rows file has a manifest recording transport_abort", flush=True)
            return 2
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    man = build_manifest(a.model, a.lang, a.seed_base, worker, run_id, json.loads(env.get("FAKE_MANIFEST_OVERRIDE", "{}")))
    cleanup = {"survivors": [], "containers_remaining": [], "uncertain": env.get("FAKE_CLEANUP_UNCERTAIN") == "1",
               "orphans_unattributed": []}

    def save():
        _atomic(mp, json.dumps(man, indent=2).encode())

    def abort(msg, item=None):
        man["transport_abort"] = {"error": msg}
        if item is not None:
            man["cancelled_item"] = {"id": item}
        man["cleanup_status"] = cleanup
        save()
        print(f"TransportAbort: {msg}", flush=True)
        return 1

    def on_term(signum, frame):
        man["cleanup_status"] = cleanup
        man["transport_abort"] = {"error": "SIGTERM"}
        save()
        os._exit(143)

    if env.get("FAKE_IGNORE_TERM") == "1":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGTERM, on_term)
    tick = float(env.get("FAKE_TICK_S", "0.02"))
    if behaviour == "no_manifest":       # hangs before the first manifest; honours the cancel file
        while not cancel.exists():
            time.sleep(tick)
        return abort("cancelled by runner")
    save()
    deadline = time.time() + float(env.get("FAKE_PROBE_ACK_WAIT", "300"))
    while not ack.exists():
        if cancel.exists():
            return abort("cancelled by runner")
        if time.time() > deadline:
            return abort("manifest not acknowledged")
        time.sleep(tick)
    ignore_cancel = behaviour == "ignore_cancel"
    t0 = time.time()

    def heartbeat(item):
        print(json.dumps({"m62_watch": {"requests_completed": 3, "output_tokens_completed": 500, "no_progress_tokens": 0,
                                        "no_progress_requests": 0, "best_failing": 1, "baseline_failing": 2,
                                        "stop_reason": None, "last_prompt_tokens": 3000},
                          "phase": "run", "elapsed_s": time.time() - t0}), flush=True)

    def cancelled():
        return cancel.exists() and not ignore_cancel

    if behaviour == "hang_after_manifest":
        while not cancelled():
            time.sleep(tick)
        return abort("cancelled by runner")
    names = [x for x in a.items.split(",") if x]
    items = [f"{a.lang}/{x}" for x in names]
    if a.limit:
        items = items[:a.limit]
    item_s, hb_s = float(env.get("FAKE_ITEM_S", "0.1")), float(env.get("FAKE_HB_S", "0.05"))
    done_here = 0
    for item in items:
        if any(r["id"] == item for r in rows):
            continue
        if cancelled():
            return abort("cancelled by runner")
        ev = _evidence_dir(wd, a.model, out, run_id, item)
        ev.mkdir(parents=True, exist_ok=True)
        evf = ev / "events.jsonl"
        evf.write_bytes(b"")
        if behaviour in ("hang_in_item", "ignore_cancel", "stale_heartbeat_growing_events"):
            heartbeat(item)
            while True:
                if cancelled():
                    return abort("cancelled by runner", item)
                if behaviour == "stale_heartbeat_growing_events":
                    with evf.open("ab") as f:
                        f.write(b'{"type":"x"}\n')
                time.sleep(tick)
        start, last_hb = time.time(), 0.0
        while time.time() - start < item_s:
            if cancelled():
                return abort("cancelled by runner", item)
            with evf.open("ab") as f:
                f.write(b'{"type":"x"}\n')
            if time.time() - last_hb >= hb_s:
                heartbeat(item)
                last_hb = time.time()
            time.sleep(tick)
        rows.append(build_row(a.model, item, a.seed_base, worker, wd, out, run_id, wall_s=time.time() - start))
        _atomic(out, "".join(json.dumps(r) + "\n" for r in rows).encode())
        print(f"{item}: passed=True nonconv=None", flush=True)
        done_here += 1
        if behaviour == "abort_after_n" and done_here >= int(env.get("FAKE_N", "1")):
            return abort("injected transport failure")
    expected = [x for x in a.expect_items.split(",") if x]
    if sorted(r["id"] for r in rows) != sorted(expected):
        return abort("expect-items mismatch")
    man["cleanup_status"] = cleanup
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
