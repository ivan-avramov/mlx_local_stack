"""Fake M64 arm probe implementing the recorded runner/probe CONTRACT for any arm (spec 5, 8). TESTS ONLY.

The c147 fake probe's contract (manifest BEFORE item one, then wait for the ack file; rows file rewritten atomically,
existing ids skipped; `m62_watch` heartbeats; cooperative cancel; SIGTERM -> cleanup-only exit 143; rc 0 only when every
expected item has a row) plus the arm fields: `--scaffold` names the arm's label (FAKE_ARM_LABELS = JSON label -> arm id),
the manifest and rows carry `arm`, `epoch_id`, `snapshot_sha256` and the per-arm generation composite, evidence lives
under `transcripts/<arm>/`. The worker identity comes from $FAKE_PROBE_STATE/worker.json.

Behaviour per invocation of ONE arm (FAKE_ARM_PLAN = JSON {arm: [step, ...]}, consumed in order, the last repeats; needs
FAKE_PROBE_STATE): "normal", or {"abort_after": k, "cause": "server_error" | null, "tokens": n} = complete k items, then
abort like a transport failure (manifest `transport_abort` with `cause` and the item's gate tokens, exit 1)."""
import argparse
import hashlib
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "benchmark"))
sys.path.insert(0, str(HERE.parents[1] / "c147"))
import fake_probe as fp  # noqa: E402
from bench import arm_adapter as aa, arm_specs, rowschema  # noqa: E402

OC = arm_specs.OC
CAMPAIGN = "d" * 64
SERVING = {"src/mlx-vlm": "5" * 64, "src/mlx-serve": "6" * 64}


def arm_of(label):
    return json.loads(os.environ.get("FAKE_ARM_LABELS", "{}")).get(label) or ("oc" if label == OC.label else None)


def composite(arm, runtime):
    return aa.arm_generation_sha256(arm, runtime, OC.generation_fields)


def build_manifest(arm, label, model, lang, seed_base, worker, run_id, epoch_id, frozen, override=None):
    h = lambda c: c * 64  # noqa: E731
    man = {
        "model": model, "run_id": run_id, "worker": worker, "sampling_profile": "deployed",
        "git": {"serving_path": dict(SERVING)}, "registry": {"sha256": os.environ.get("FAKE_REGISTRY_SHA", h("a"))},
        "runtime": {
            "scaffold": label, "scaffold_policy_sha256": os.environ.get(f"FAKE_POLICY_SHA_{arm.upper()}", CAMPAIGN),
            "probe_code_sha256": os.environ.get("FAKE_PROBE_CODE_SHA", h("9")), "opencode_version": "2.0.20",
            "opencode_exe_sha256": h("e"), "opencode_bench_config_sha256": h("c"), "carrier_source_sha256": h("d"),
            "agent_system_sha256": None, "polyglot_sha": "1" * 40, "policy": {"universe_sha256": h("2")},
            "seed_base": seed_base, "lang": lang, "draft_kind": fp.served_draft_kind(model),
            "sampling_profile": "deployed", "frozen_prompt_date": frozen,
            "arm": arm, "epoch_id": epoch_id, "snapshot_sha256": hashlib.sha256(arm.encode()).hexdigest(),
            "snapshot_complete": True,
        },
    }
    man["runtime"]["arm_identity_sha256"] = fp.arm_identity(model, man["runtime"]["draft_kind"])
    man["runtime"]["arm_identity"] = {"fake": True, "model": model}
    for dotted, value in (override or {}).items():
        d = man
        parts = dotted.split(".")
        for k in parts[:-1]:
            d = d[k]
        d[parts[-1]] = value
    if "runtime.generation_identity_sha256" not in (override or {}):
        man["runtime"]["generation_identity_sha256"] = composite(arm, man["runtime"])
    return man


def evidence_dir(wd, arm, model, out, run_id, item):
    lang, name = item.split("/", 1)
    return Path(wd) / "transcripts" / arm / model / f"{Path(out).stem}.{run_id}" / f"{lang}__{name}"


def build_row(arm, label, model, item, seed_base, worker, wd, out, run_id, runtime, wall_s=1.0, tokens=1000):
    ev = evidence_dir(wd, arm, model, out, run_id, item)
    ev.mkdir(parents=True, exist_ok=True)
    files = {"events": ev / "events.jsonl", "stderr": ev / "stderr.txt", "export": ev / "export.json",
             "datefreeze": ev / "datefreeze.jsonl"}
    files["events"].write_bytes(b'{"type":"step_finish"}\n')
    files["stderr"].write_bytes(b"")
    files["datefreeze"].write_text("")
    files["export"].write_text(json.dumps({"id": item}))
    names = ("report.xml", "stdout.txt", "stderr.txt") if item.startswith("python/") else ("go.jsonl", "go.stderr")
    arts = {}
    for n in names:
        f = ev / "grades" / n
        f.parent.mkdir(exist_ok=True)
        f.write_text("ok " + n)
        arts[n] = {"path": fp._portable(wd, f), "sha256": fp._sha(f)}
    seed = rowschema.sample_seed(item, 0, seed_base)
    return {
        "id": item, "model": model, "sample": 0, "sampler_seed": seed, "passed": True, "converged": True,
        "nonconv_kind": None, "nonconv_flags": [], "wall_s": wall_s, "worker_before": worker, "worker_after": worker,
        "overlay_sha256": fp.seed_overlay_sha(model, seed), "scaffold": label,
        "evidence_sha256": {k: fp._sha(v) for k, v in files.items()},
        "generation_identity_sha256": runtime["generation_identity_sha256"],
        "arm_identity_sha256": runtime["arm_identity_sha256"], "prompt_date": runtime["frozen_prompt_date"],
        "prompt_date_real": fp.REAL_DATE(), "prompt_date_update_removed": False,
        "events_path": fp._portable(wd, files["events"]), "transcript_path": fp._portable(wd, files["export"]),
        "stderr_path": fp._portable(wd, files["stderr"]), "datefreeze_path": fp._portable(wd, files["datefreeze"]),
        "grade_reports": [{"boundary": 1, "seq": 1, "final": True, "outcome": "parsed", "artifacts": arts}],
        "gate": {"output_tokens_completed": tokens, "requests_completed": 5},
        "arm": arm, "epoch_id": runtime["epoch_id"], "snapshot_sha256": runtime["snapshot_sha256"],
    }


def write_leg(out, arm, label, model, lang, seed_base, ids, worker, wd, epoch_id="e" * 64, frozen=None, run_id="fixture-run",
              override=None):
    """Complete, valid rows + manifest for tests (the same builders the probe uses)."""
    man = build_manifest(arm, label, model, lang, seed_base, worker, run_id, epoch_id, frozen or fp.REAL_DATE(), override)
    rows = [build_row(arm, label, model, i, seed_base, worker, wd, out, run_id, man["runtime"]) for i in ids]
    fp._atomic(out, "".join(json.dumps(r) + "\n" for r in rows).encode())
    man["cleanup_status"] = {"survivors": [], "containers_remaining": [], "uncertain": False, "orphans_unattributed": []}
    fp._atomic(Path(out).with_suffix(".manifest.json"), json.dumps(man, indent=2).encode())


def print_identity(argv):
    env = os.environ
    label = argv[argv.index("--scaffold") + 1] if "--scaffold" in argv else OC.label
    arm = arm_of(label) or "oc"
    if env.get("FAKE_PROBE_STATE"):
        state = Path(env["FAKE_PROBE_STATE"])
        state.mkdir(parents=True, exist_ok=True)
        with (state / "identity_calls.jsonl").open("a") as f:
            f.write(json.dumps({"argv": list(argv), "arm": arm}) + "\n")
    if env.get("FAKE_PRINT_MODE") == "fail":
        print("print-identity failed", file=sys.stderr)
        return 1
    value = env.get(f"FAKE_PRINT_POLICY_SHA_{arm.upper()}", env.get(f"FAKE_POLICY_SHA_{arm.upper()}", CAMPAIGN))
    print(json.dumps({"arm": arm, "scaffold": label, "scaffold_policy_sha256": value}))
    return 0


def main(argv=None):
    raw = sys.argv[1:] if argv is None else list(argv)
    if "--print-identity" in raw:
        return print_identity(raw)
    ap = argparse.ArgumentParser()
    for f in ("--model", "--items", "--lang", "--out", "--scaffold", "--expect-items", "--a4-v2-receipt",
              "--sampling-profile", "--cancel-file", "--manifest-ack", "--tg1-inject", "--chain-total", "--universe",
              "--frozen-prompt-date", "--epoch-id"):
        ap.add_argument(f)
    ap.add_argument("--seed-base", type=int)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    env = os.environ
    arm = arm_of(a.scaffold)
    state = Path(env["FAKE_PROBE_STATE"]) if env.get("FAKE_PROBE_STATE") else None
    plan_step = "normal"
    if state:
        state.mkdir(parents=True, exist_ok=True)
        counter = state / f"count_{arm}"
        n_inv = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(n_inv + 1))
        with (state / "invocations.jsonl").open("a") as f:
            f.write(json.dumps({"argv": sys.argv[1:], "pid": os.getpid(), "arm": arm, "n": n_inv}) + "\n")
        if env.get("FAKE_ARM_PLAN"):
            plan = json.loads(env["FAKE_ARM_PLAN"]).get(arm) or ["normal"]
            plan_step = plan[min(n_inv, len(plan) - 1)]
    cancel, ack = Path(a.cancel_file), Path(a.manifest_ack)
    if cancel.exists() or ack.exists():
        print("REFUSED: cancel or ack file already exists", flush=True)
        return 2
    if arm is None or not a.expect_items or not a.a4_v2_receipt or a.sampling_profile != "deployed" or not a.epoch_id:
        print("REFUSED: bad arguments", flush=True)
        return 2
    if not fp.valid_date(a.frozen_prompt_date):
        print("REFUSED: --frozen-prompt-date is required ('Www Mmm DD YYYY')", flush=True)
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
        for r in rows:
            if r.get("worker_after") != worker:
                print("REFUSED: rows from another worker instance", flush=True)
                return 2
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    overrides = json.loads(env.get("FAKE_MANIFEST_OVERRIDE", "{}"))
    if state and env.get("FAKE_MANIFEST_PLAN"):
        plan_m = json.loads(env["FAKE_MANIFEST_PLAN"])
        overrides = {**overrides, **plan_m[min(n_inv, len(plan_m) - 1)]}
    man = build_manifest(arm, a.scaffold, a.model, a.lang, a.seed_base, worker, run_id, a.epoch_id,
                         a.frozen_prompt_date, overrides)
    cleanup = {"survivors": [], "containers_remaining": [], "uncertain": env.get("FAKE_CLEANUP_UNCERTAIN") == "1",
               "orphans_unattributed": []}

    def save():
        fp._atomic(mp, json.dumps(man, indent=2).encode())

    def abort(msg, item=None, **stamp):
        man["transport_abort"] = {"error": msg, **stamp}
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

    signal.signal(signal.SIGTERM, on_term)
    tick = float(env.get("FAKE_TICK_S", "0.02"))
    save()
    deadline = time.time() + float(env.get("FAKE_PROBE_ACK_WAIT", "300"))
    while not ack.exists():
        if cancel.exists():
            return abort("cancelled by runner")
        if time.time() > deadline:
            return abort("manifest not acknowledged")
        time.sleep(tick)
    t0 = time.time()
    names = [x for x in a.items.split(",") if x]
    items = [f"{a.lang}/{x}" for x in names]
    if a.limit:
        items = items[:a.limit]
    item_s = float(env.get("FAKE_ITEM_S", "0.05"))
    done_here = 0
    for item in items:
        if any(r["id"] == item for r in rows):
            continue
        if cancel.exists():
            return abort("cancelled by runner", item)
        if isinstance(plan_step, dict) and done_here >= plan_step["abort_after"]:
            extra = {"cause": plan_step["cause"]} if plan_step.get("cause") else {}
            extra["gate"] = {"output_tokens_completed": plan_step.get("tokens", 0), "requests_completed": 3}
            return abort("injected transport failure", item, **extra)
        time.sleep(item_s)
        print(json.dumps({"m62_watch": {"requests_completed": 3, "output_tokens_completed": 500, "no_progress_tokens": 0,
                                        "no_progress_requests": 0, "best_failing": 1, "baseline_failing": 2,
                                        "stop_reason": None, "last_prompt_tokens": 3000},
                          "phase": "run", "elapsed_s": time.time() - t0}), flush=True)
        rows.append(build_row(arm, a.scaffold, a.model, item, a.seed_base, worker, wd, out, run_id, man["runtime"],
                              wall_s=time.time() - t0))
        fp._atomic(out, "".join(json.dumps(r) + "\n" for r in rows).encode())
        print(f"{item}: passed=True nonconv=None", flush=True)
        done_here += 1
    expected = [x for x in a.expect_items.split(",") if x]
    if sorted(r["id"] for r in rows) != sorted(expected):
        return abort("expect-items mismatch")
    man["cleanup_status"] = cleanup
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
