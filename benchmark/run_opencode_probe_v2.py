#!/usr/bin/env python3
"""M59: hermetic, seeded opencode 2.x sessions with fail-closed transport classification."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from bench import opencode_common, progress_gate, provenance

opencode_common.reexport(globals())
PINNED_OPENCODE_VERSION_V2 = "2.0.20"
BENCH_OPENCODE_CONFIG = REPO / "benchmark/opencode_bench_v2.json"
NORETRY_PLUGIN = REPO / "benchmark/opencode_plugins/noretry.js"
OVERLAY_SCHEMA_V2 = "OPENCODE_CONFIG_CONTENT:providers.mlx-local.models.<model>.body.seed"
MAX_TOKENS_EVIDENCE = "mock-capture:test_real_wire_seed_sampling_title_headers_and_export"
SCAFFOLD_ENV_POLICY_V2 = {
    "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
    "TERM": "dumb",
    "NO_COLOR": "1",
    "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
    "OPENCODE_DISABLE_MODELS_FETCH": "1",
    "OPENCODE_DISABLE_AUTOUPDATE": "1",
    "OPENCODE_DISABLE_FILEWATCHER": "1",
}
RESUME_IDENTITY_KEYS_V2 = (
    "scaffold",
    "seed_base",
    "overlay_schema",
    "opencode_bench_config_sha256",
    "noretry_plugin_sha256",
    "scaffold_policy_sha256",
    "env_switches",
    "standalone",
    "scratch_git_init",
    "opencode_version",
    "opencode_exe_sha256",
    "probe_code_sha256",
    "lang",
    "polyglot_sha",
    "tick_s",
    "hard_ceiling_s",
    "stall_ticks",
    "loop_repeats",
    "poll_s",
    "cache_bin_inventory_sha256",
)


class TransportAbort(RuntimeError):
    """An item cannot produce a gradeable row."""


def _require_opencode_bin():
    path = Path(os.environ.get("OPENCODE_PROBE_BIN", "/opt/homebrew/bin/opencode"))
    if not path.is_absolute():
        sys.exit("REFUSED: OPENCODE_PROBE_BIN must be absolute")
    path = path.resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        sys.exit(f"REFUSED: pinned opencode binary {_portable(path)} is missing or not executable")
    return str(path)


def _parse_version(output):
    return re.sub(r"^opencode v", "", output.strip())


def _seed_overlay(model, seed):
    return {"providers": {"mlx-local": {"models": {model: {"body": {"seed": int(seed)}}}}}}


def _opencode_env(run_dir, scratch, overlay):
    root = Path(run_dir).resolve()
    return {
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "cfg"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_STATE_HOME": str(root / "state"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "TMPDIR": str(root / "tmp") + "/",
        "OPENCODE_CONFIG_DIR": str(root / "cfg/opencode"),
        **SCAFFOLD_ENV_POLICY_V2,
        "OPENCODE_CONFIG_CONTENT": json.dumps(overlay, sort_keys=True),
        "PWD": str(scratch),
    }


def _make_run_dir(workdir, run_id):
    root = (workdir / "opencode-probe-v2" / ("run-" + run_id)).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name in ("home", "cfg/opencode/plugins", "data", "state", "cache", "tmp"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for source, target in [
        (BENCH_OPENCODE_CONFIG, root / "cfg/opencode/opencode.json"),
        (NORETRY_PLUGIN, root / "cfg/opencode/plugins/noretry.js"),
    ]:
        target.write_bytes(source.read_bytes())
        if _sha_of(target) != _sha_of(source):
            raise provenance.ServedConfigError("M50 tripwire: non-verbatim config/plugin copy")
    rg = shutil.which("rg", path="/opt/homebrew/bin:/usr/bin:/bin")
    if rg:
        dest = root / "cache/opencode/bin/rg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(rg).resolve(), dest)
    return root


def _scratch_root():
    return str(_stack_workdir() / "scratch/octmp.noindex")


def _spawn(cmd, scratch, env, **kwargs):
    if env.get("PWD") != str(scratch):
        raise provenance.ServedConfigError("M50 tripwire: PWD differs from scratch cwd")
    return subprocess.Popen(cmd, cwd=scratch, env=env, stdin=subprocess.DEVNULL, **kwargs)


def _capture(cmd, scratch, env, timeout):
    with _spawn(
        cmd, scratch, env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as proc:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def _run_opencode(
    model,
    cwd,
    prompt,
    sol,
    test,
    grade,
    before_sol,
    *,
    tick_s,
    hard_ceiling_s,
    poll_s,
    stall_ticks,
    loop_repeats,
    env,
    opencode_bin,
):
    events = cwd / ".opencode_probe_events.jsonl"
    stderr = cwd / ".opencode_probe_stderr.txt"
    with events.open("w") as stdout, stderr.open("w") as err:
        proc = _spawn(
            [
                opencode_bin,
                "run",
                "--standalone",
                "--model",
                f"mlx-local/{model}",
                "--format",
                "json",
                "--title",
                "probe",
                prompt,
            ],
            cwd,
            env,
            stdout=stdout,
            stderr=err,
            text=True,
        )
        try:
            snapshot = _tick_snapshot_fn(
                cwd, sol, test, before_sol, grade, events, tmp_dir=env["TMPDIR"]
            )
            result = progress_gate.run_progress_gated(
                proc,
                snapshot,
                tick_s=tick_s,
                hard_ceiling_s=hard_ceiling_s,
                poll_s=poll_s,
                stall_ticks=stall_ticks,
                loop_repeats=loop_repeats,
            )
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    return proc.returncode, events.read_text(errors="replace"), result.elapsed_s, result


def _events(path):
    parsed = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    parsed.append(event)
            except ValueError:
                pass
    return parsed


def _context_overflow(error):
    if (
        not isinstance(error, dict)
        or error.get("type") != "provider.invalid-request"
        or error.get("status") != 400
    ):
        return False
    body = (error.get("response") or {}).get("body", "")
    text = json.dumps(body) if not isinstance(body, str) else body
    text += " " + str(error.get("message", ""))
    return bool(
        re.search(
            r"maximum context length is \d+ tokens.*messages resulted in \d+ tokens",
            text,
            re.I | re.S,
        )
    )


def _classify(events, rc, stop_reason):
    kinds = [e.get("type") for e in events]
    if any(a == b == "step_start" for a, b in zip(kinds, kinds[1:])):
        raise TransportAbort("consecutive step_start: provider retry")
    errors = [e.get("error") for e in events if e.get("type") == "error"]
    if errors:
        if rc == 1 and len(errors) == 1 and _context_overflow(errors[0]):
            return "context_overflow"
        raise TransportAbort("error event: " + json.dumps(errors, sort_keys=True))
    if stop_reason in ("stalled", "looping", "hard_ceiling"):
        return stop_reason
    if rc != 0:
        raise TransportAbort(f"exit {rc} without an allowed context-overflow error")
    if stop_reason != "completed" or kinds.count("step_start") != kinds.count("step_finish") + 1:
        raise TransportAbort("incomplete or unrecognised event sequence")
    return None


def _export_session(session_id, env, cwd, opencode_bin):
    path = cwd / ".opencode_probe_export.json"
    if not session_id:
        raise TransportAbort("missing sessionID")
    try:
        result = _capture(
            [opencode_bin, "session", "export", session_id, "--standalone"], cwd, env, 120
        )
        path.write_text(result.stdout)
        if result.returncode:
            raise TransportAbort(f"export exit {result.returncode}: {result.stderr}")
        export = json.loads(result.stdout)
        if not isinstance(export, dict) or not isinstance(export.get("messages"), list):
            raise TransportAbort("export has no messages list")
        return export
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        raise TransportAbort(f"missing/unparsable export: {e}") from e


def _metric_export(export):
    """Normalize the native v2 export into the shared, unchanged 1.18 metric input."""
    messages = []
    for m in export["messages"]:
        messages.append(
            {
                "info": {"role": m.get("type"), "tokens": m.get("tokens", {})},
                "parts": [
                    {
                        **p,
                        "tool": p.get("name"),
                        "state": {
                            **p.get("state", {}),
                            "output": p.get("state", {}).get("content"),
                        },
                    }
                    for p in m.get("content", [])
                    if isinstance(p, dict)
                ],
            }
        )
    return {"messages": messages}


def _check_export(export, nonconv):
    for message in export["messages"]:
        if message.get("type") != "assistant":
            continue
        if message.get("retry"):
            raise TransportAbort("export records an assistant retry")
        error = message.get("error")
        if not error:
            continue
        if nonconv == "context_overflow" and _context_overflow(error):
            continue
        if (
            nonconv in ("stalled", "looping", "hard_ceiling")
            and isinstance(error, dict)
            and error.get("type") == "aborted"
        ):
            continue
        raise TransportAbort("export records an assistant error")


def _identity(a, version, binary, run_dir, poly_sha):
    policy = {
        "opencode_bench_config_sha256": _sha_of(BENCH_OPENCODE_CONFIG),
        "noretry_plugin_sha256": _sha_of(NORETRY_PLUGIN),
        "overlay_schema": OVERLAY_SCHEMA_V2,
        "env_switches": dict(SCAFFOLD_ENV_POLICY_V2),
        "scratch_git_init": True,
        "standalone": True,
        "opencode_version": version,
        "opencode_exe_sha256": _sha_of(binary),
        "cache": "per-run",
    }
    digest = hashlib.sha256()
    for p in (
        Path(__file__),
        Path(opencode_common.__file__),
        Path(progress_gate.__file__),
        Path(provenance.__file__),
    ):
        digest.update(p.name.encode())
        digest.update(p.read_bytes())
    return {
        **policy,
        "scaffold": "opencode-v2",
        "seed_base": a.seed_base,
        "scaffold_policy_sha256": hashlib.sha256(
            json.dumps(policy, sort_keys=True).encode()
        ).hexdigest(),
        "probe_code_sha256": digest.hexdigest(),
        "lang": a.lang,
        "polyglot_sha": poly_sha,
        **{
            k: getattr(a, k)
            for k in ("tick_s", "hard_ceiling_s", "stall_ticks", "loop_repeats", "poll_s")
        },
        "cache_bin_inventory_sha256": _cache_bin_inventory_sha256(run_dir / "cache"),
    }


def _check_resume_v2(previous, identity, router, model):
    if not previous:
        sys.exit("REFUSED: rows have no manifest")
    if previous.get("served_config_drift"):
        sys.exit("REFUSED: manifest carries served_config_drift")
    old = previous.get("runtime", {})
    for key in RESUME_IDENTITY_KEYS_V2:
        if key not in old or old[key] != identity[key]:
            sys.exit(f"REFUSED: resume identity {key} differs")
    if previous.get("model") != model:
        sys.exit("REFUSED: resume model differs")
    if previous.get("router", {}).get("config_sha256") != router.get(
        "config_sha256"
    ) or previous.get("router", {}).get("config") != router.get("config"):
        sys.exit("REFUSED: resume served config differs")
    if previous.get("git", {}).get("serving_path") != provenance._git_shas().get("serving_path"):
        sys.exit("REFUSED: resume serving-code identity differs")


def _abort(mp, run_id, item, work, rc, stop_reason, error, *, signature=None):
    target = _stack_workdir() / "opencode-probe-v2/aborted" / run_id / item
    target.mkdir(parents=True, exist_ok=True)
    for source, name in [
        (".opencode_probe_events.jsonl", "events.jsonl"),
        (".opencode_probe_stderr.txt", "stderr.txt"),
        (".opencode_probe_export.json", "export.json"),
    ]:
        path = work / source
        target.joinpath(name).write_text(
            _scrub_pii(path.read_text(errors="replace")) if path.exists() else ""
        )
    _stamp_manifest(
        mp,
        {
            "transport_abort": {
                "item": item,
                "rc": rc,
                "stop_reason": stop_reason,
                "signature": signature or _scrub_error(error, 1000),
            }
        },
    )
    sys.exit("ABORT: " + _scrub_error(error, 300))


def _drift(mp, router, error):
    _stamp_manifest(
        mp,
        {
            "served_config_drift": {
                "entry_sha256": router.get("config_sha256"),
                "error": _scrub_error(error),
            }
        },
    )


def _a4_receipt(path, router, limit, model, exe_sha, carrier_sha):
    receipt = None
    if path:
        try:
            receipt = json.loads(Path(path).read_text())
        except (OSError, ValueError) as e:
            sys.exit("REFUSED: unreadable A4 v2 receipt: " + _scrub_error(e))
    valid = (
        isinstance(receipt, dict)
        and receipt.get("pass") is True
        and bool(receipt.get("run_id"))
        and isinstance(receipt.get("router"), dict)
        and receipt["router"].get("pid") == router["pid"]
        and receipt.get("router_pid") == router["pid"]
        and receipt.get("model") == model
        and receipt.get("opencode_version") == PINNED_OPENCODE_VERSION_V2
        and receipt.get("exe_sha256") == exe_sha
        and receipt.get("carrier_sha256") == carrier_sha
    )
    if not valid and (path or limit is None or limit > 5):
        sys.exit(
            "REFUSED: A4 v2 PASS matching router/model/binary/carrier required outside --limit <= 5 smoke"
        )
    return receipt if valid else None


def _instruction_sources(scratch, bench_home):
    """Inventory instruction files in scratch ancestors and the isolated bench HOME."""
    scratch = Path(scratch).resolve()
    home = Path(bench_home).resolve()
    directories = (scratch, *scratch.parents, home, home / ".claude")
    sources = {}
    for directory in directories:
        for name in ("AGENTS.md", "CLAUDE.md"):
            path = directory / name
            if path.is_file():
                sources[_portable(path)] = _sha_of(path)
    return sources


def main():
    """Run the v2 probe, reporting policy refusals without grading them."""
    try:
        return _main()
    except provenance.ServedConfigError as e:
        sys.exit("REFUSED: " + _scrub_error(e))


def _main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--seed-base", type=int, required=True)
    ap.add_argument(
        "--lang", choices=["python", "go", "rust", "java", "javascript"], default="python"
    )
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--chain-total", type=int, default=0)
    ap.add_argument("--a4-v2-receipt")
    ap.add_argument("--allow-version-drift", action="store_true")
    for key, default in [
        ("tick-s", progress_gate.DEFAULT_TICK_S),
        ("hard-ceiling-s", progress_gate.DEFAULT_HARD_CEILING_S),
        ("stall-ticks", progress_gate.DEFAULT_STALL_TICKS),
        ("loop-repeats", progress_gate.DEFAULT_LOOP_REPEATS),
    ]:
        ap.add_argument("--" + key, type=int, default=default)
    ap.add_argument("--poll-s", type=float, default=5.0)
    a = ap.parse_args()
    if any(
        getattr(a, k) <= 0
        for k in ("tick_s", "hard_ceiling_s", "stall_ticks", "loop_repeats", "poll_s")
    ) or (a.limit is not None and a.limit <= 0):
        sys.exit("REFUSED: gate parameters and limit must be positive")
    items = list(dict.fromkeys(s.strip() for s in a.items.split(",") if s.strip()))
    if not items or any(Path(s).name != s or s in (".", "..") for s in items):
        sys.exit("REFUSED: items must be exercise basenames")
    if a.limit:
        items = items[: a.limit]
    workdir = _stack_workdir().resolve()
    if not workdir.is_dir():
        sys.exit("REFUSED: STACK_WORKDIR must exist")
    binary = _require_opencode_bin()
    carrier = json.loads(BENCH_OPENCODE_CONFIG.read_text())
    model = carrier["providers"]["mlx-local"]["models"].get(a.model)
    if model is None:
        sys.exit("REFUSED: model absent from v2 bench carrier")
    base = carrier["providers"]["mlx-local"]["settings"]["baseURL"]
    # Check the configured local owner before creating run directories or starting a client.
    router = provenance.assert_served_config(base, env={})
    receipt = _a4_receipt(
        a.a4_v2_receipt, router, a.limit, a.model, _sha_of(binary), _sha_of(BENCH_OPENCODE_CONFIG)
    )
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    run_dir = _make_run_dir(workdir, run_id)
    carrier_sha, plugin_sha = _sha_of(BENCH_OPENCODE_CONFIG), _sha_of(NORETRY_PLUGIN)

    def env_check(env, overlay):
        """Env check."""
        provenance.opencode_v2_env_check(env, run_dir, carrier_sha, plugin_sha, overlay)
        if _sha_of(BENCH_OPENCODE_CONFIG) != carrier_sha or _sha_of(NORETRY_PLUGIN) != plugin_sha:
            raise provenance.ServedConfigError(
                "M50 tripwire: repository carrier/plugin changed during run"
            )

    with _scratch_dir("discovery") as scratch:
        _git_init_scratch(scratch)
        overlay = _seed_overlay(a.model, _item_seed(a.lang + "/" + items[0], a.seed_base))
        env = _opencode_env(run_dir, scratch, overlay)
        env_check(env, overlay)
        result = _capture([binary, "--version"], scratch, env, 30)
        version = _parse_version(result.stdout)
        if result.returncode or not version:
            sys.exit("REFUSED: cannot determine opencode version: " + _scrub_error(result.stderr))
        if version != PINNED_OPENCODE_VERSION_V2 and not a.allow_version_drift:
            sys.exit(f"REFUSED: opencode {version} != pinned {PINNED_OPENCODE_VERSION_V2}")
        discovery = provenance.opencode_v2_destination(
            scratch,
            {**env, "OPENCODE_PRINT_LOGS": "1"},
            a.model,
            run_dir,
            binary,
            overlay,
            require_plugin=True,
        )
        if provenance.assert_served_config(discovery, env=env)["pid"] != router["pid"]:
            raise provenance.ServedConfigError(
                "M50 tripwire: discovery router pid differs from entry"
            )
    polyglot = _polyglot_root()
    identity = _identity(a, version, binary, run_dir, _polyglot_sha(polyglot))
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / "opencode-v2.jsonl"
    mp = out.with_suffix(".manifest.json")
    done = _load_rows(out)
    try:
        previous = json.loads(mp.read_text()) if mp.exists() else None
    except (ValueError, OSError) as e:
        sys.exit("REFUSED: unreadable existing manifest: " + _scrub_error(e))
    if done or previous is not None:
        _check_resume_v2(previous, identity, router, a.model)
    docker_ok = a.lang == "python" or _docker_available()
    grade = (
        _grade_python
        if a.lang == "python"
        else lambda w, t: globals()["_grade_" + a.lang](w, t, docker_ok=docker_ok)
    )
    wrote = False
    try:
        for name in items:
            item = a.lang + "/" + name
            if (item, 0) in done:
                print("[resume] " + item + " skipped", flush=True)
                continue
            src = polyglot / a.lang / "exercises/practice" / name
            if not src.is_dir():
                sys.exit("REFUSED: missing exercise " + item)
            with _scratch_dir(name) as tmp:
                work = tmp / name
                _prepare(src, work)
                _git_init_scratch(work)
                seed = _item_seed(item, a.seed_base)
                overlay = _seed_overlay(a.model, seed)
                env = _opencode_env(run_dir, work, overlay)
                env_check(env, overlay)
                if not wrote:
                    runtime = {
                        **identity,
                        "client": "opencode",
                        "opencode_config_dir": _portable(run_dir / "cfg/opencode"),
                        "opencode_bin": _portable(Path(binary)),
                        "a4_v2_pass": bool(receipt),
                        "noretry_plugin_loaded_from": _portable(
                            (run_dir / "cfg/opencode/plugins/noretry.js").resolve()
                        ),
                        "a4_gate_run_id": receipt["run_id"] if receipt else None,
                        "compaction": "off",
                        "title_generation": "disabled (agents.title.disabled + --title; v2.0.20 capture 2026-10-06)",
                        "hermetic_env": dict(SCAFFOLD_ENV_POLICY_V2),
                        "instruction_sources": _instruction_sources(work, env["HOME"]),
                        "max_tokens_semantics": (
                            "fixed-by-carrier"
                            if "max_tokens" in model.get("body", {})
                            else "v2-dynamic"
                        ),
                        "max_tokens_evidence": MAX_TOKENS_EVIDENCE,
                        "opencode_config_sha256": _sha_of(REPO / "opencode_config/opencode.json"),
                    }
                    man = provenance.gather(
                        a.model, profile="deployed", runtime=runtime, router=router
                    )
                    if previous:
                        man["continuation_history"] = list(
                            previous.get("continuation_history") or []
                        ) + [
                            {
                                key: previous.get(key)
                                for key in (
                                    "timestamp",
                                    "model",
                                    "git",
                                    "router",
                                    "router_exit",
                                    "runtime",
                                )
                            }
                        ]
                        man["router_history"] = previous.get("router_history", []) + (
                            [previous["router"]]
                            if previous.get("router", {}).get("pid") != router["pid"]
                            else []
                        )
                    out.parent.mkdir(parents=True, exist_ok=True)
                    mp.write_text(_scrub_pii(json.dumps(man, indent=2)))
                    wrote = True
                else:
                    man = json.loads(mp.read_text())
                    man["runtime"]["instruction_sources"].update(
                        _instruction_sources(work, env["HOME"])
                    )
                    _stamp_manifest(mp, {"runtime": man["runtime"]})
                try:
                    destination = provenance.opencode_v2_destination(
                        work, env, a.model, run_dir, binary, overlay
                    )
                except Exception as e:
                    _abort(
                        mp,
                        run_id,
                        item,
                        work,
                        None,
                        "not_started",
                        e,
                        signature="destination_check",
                    )
                try:
                    owner = provenance.assert_served_config(destination, env=env)
                    if owner["pid"] != router["pid"] or owner.get("config_sha256") != router.get(
                        "config_sha256"
                    ):
                        raise provenance.ServedConfigError(
                            "M50 tripwire: per-item router identity differs from entry"
                        )
                except provenance.ServedConfigError as e:
                    try:
                        provenance.assert_served_config_unchanged(router, destination)
                    except provenance.ServedConfigError as drift:
                        _drift(mp, router, drift)
                    _abort(mp, run_id, item, work, None, "not_started", e)
                sol, test = _solution_and_test(work, src, a.lang)
                before, test_before = sol.read_text(errors="replace"), test.read_text(
                    errors="replace"
                )
                prompt = (
                    f"Implement the solution in {sol.name} so that the tests in {test.name} pass. "
                    f"The specification is in .docs/instructions.md — read it first. "
                    f"Do NOT modify {test.name}. Do not create new files unless required by the spec."
                )
                rc, stop_reason, session_id = None, "completed", None
                try:
                    rc, log, duration, gate = _run_opencode(
                        a.model,
                        work,
                        prompt,
                        sol,
                        test,
                        grade,
                        before,
                        **{
                            k: getattr(a, k)
                            for k in (
                                "tick_s",
                                "hard_ceiling_s",
                                "poll_s",
                                "stall_ticks",
                                "loop_repeats",
                            )
                        },
                        env=env,
                        opencode_bin=binary,
                    )
                    stop_reason = gate.stop_reason
                    if stop_reason in ("stalled", "looping", "hard_ceiling"):
                        try:
                            provenance.assert_served_config_unchanged(router, destination)
                        except provenance.ServedConfigError as e:
                            _drift(mp, router, e)
                            raise TransportAbort(str(e)) from e
                    parsed = _events(work / ".opencode_probe_events.jsonl")
                    session_id = next((e["sessionID"] for e in parsed if e.get("sessionID")), None)
                    nonconv = _classify(parsed, rc, stop_reason)
                    export = _export_session(session_id, env, work, binary)
                    _check_export(export, nonconv)
                except Exception as e:
                    if session_id and not (work / ".opencode_probe_export.json").exists():
                        try:
                            _export_session(session_id, env, work, binary)
                        except Exception:
                            pass  # preserve the original failure; export is diagnostic after an abort
                    _abort(mp, run_id, item, work, rc, stop_reason, e)
                try:
                    target, transcript = _transcript_target(a.model, a.lang, name, tag=out.stem)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(_scrub_pii(json.dumps(export, indent=1)))
                    events_target = target.with_suffix(".events.jsonl")
                    events_target.write_text(_scrub_pii(log))
                    normalized = _metric_export(export)
                    changed = sol.exists() and sol.read_text(errors="replace") != before
                    if nonconv == "context_overflow":
                        passed, tail, modified = (
                            False,
                            "context overflow",
                            not test.exists() or test.read_text(errors="replace") != test_before,
                        )
                    elif not docker_ok:
                        passed, tail, modified = (
                            None,
                            "docker unavailable — grading skipped (acc:null)",
                            not test.exists() or test.read_text(errors="replace") != test_before,
                        )
                    else:
                        passed, tail, modified = _grade_result(
                            work, test, test_before, changed, grade
                        )
                    row = {
                        "bench": "opencode",
                        "scaffold": "opencode-v2",
                        "schema_version": 3,
                        "id": item,
                        "model": a.model,
                        "sample": 0,
                        "passed": passed,
                        "acc": None if passed is None else int(passed),
                        "file_changed": changed,
                        "test_modified": modified,
                        "opencode_rc": rc,
                        "opencode_version": version,
                        "polyglot_sha": identity["polyglot_sha"],
                        "wall_s": round(duration, 1),
                        "stop_reason": stop_reason,
                        "timed_out": stop_reason != "completed",
                        "gate_ticks": len(gate.ticks),
                        "gate_failure_trajectory": [t.n_failing for t in gate.ticks],
                        "gate_effective_bound_s": round(gate.elapsed_s, 1),
                        "nonconv_kind": nonconv,
                        "session_id": session_id,
                        "requests_observed": sum(e.get("type") == "step_start" for e in parsed),
                        "events_path": _portable(events_target),
                        "transcript_path": transcript,
                        "loop_metrics": loop_metrics(normalized),
                        "traffic": traffic_metrics(normalized),
                        **_seed_row_fields(
                            item,
                            a.seed_base,
                            hashlib.sha256(env["OPENCODE_CONFIG_CONTENT"].encode()).hexdigest(),
                        ),
                        "max_tokens_semantics": runtime["max_tokens_semantics"],
                        "max_tokens_evidence": MAX_TOKENS_EVIDENCE,
                        **({"skipped": True} if passed is None else {}),
                        "grade_tail": _scrub_then_tail(tail, 300),
                        "log_tail": _scrub_then_tail(log, 500),
                    }
                except Exception as e:
                    _abort(mp, run_id, item, work, rc, stop_reason, e)
                with out.open("a") as stream:
                    stream.write(json.dumps(row) + "\n")
                done.add((item, 0))
                identity["cache_bin_inventory_sha256"] = _cache_bin_inventory_sha256(
                    run_dir / "cache"
                )
                man = json.loads(mp.read_text())
                man["runtime"]["cache_bin_inventory_sha256"] = identity[
                    "cache_bin_inventory_sha256"
                ]
                man["runtime"]["max_tokens_semantics"] = row["max_tokens_semantics"]
                _stamp_manifest(mp, {"runtime": man["runtime"]})
                print(
                    f'{item}: passed={passed} requests={row["requests_observed"]} stop={stop_reason}',
                    flush=True,
                )
    finally:
        try:
            exit_block = provenance.assert_served_config_unchanged(router, base)
            if wrote:
                _stamp_manifest(mp, {"router_exit": exit_block})
        except provenance.ServedConfigError as e:
            if wrote:
                _drift(mp, router, e)
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
