#!/usr/bin/env python3
"""M59: hermetic, seeded opencode 2.x sessions with fail-closed transport classification."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from bench import answer_key, opencode_common, progress_gate, provenance

opencode_common.reexport(globals())
PINNED_OPENCODE_VERSION_V2 = "2.0.20"
BENCH_OPENCODE_CONFIG = REPO / "benchmark/opencode_bench_v2.json"
BENCH_OPENCODE_WEB_CONFIG = REPO / "benchmark/opencode_bench_v2_web.json"
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
    "first_write_tokens",
    "decode_tok_s",
    "scaffold",
    "carrier_source",
    "carrier_source_sha256",
    "agent_system_file",
    "agent_system_sha256",
    "extra_deny",
    "extra_deny_sha256",
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


# P230: the pinned binary is bench-owned (never the laptop-wide brew install, which upgrades). 2.0.20 is not on npm;
# scripts/install_bench_opencode.sh extracts it from the sha-pinned Homebrew bottle, byte-identical to the M59-M62 rows.
OPENCODE_V2_BIN_RELPATH = "opencode-2.0.20/bin/opencode"
OPENCODE_V2_EXE_SHA256 = "da6c61cd188189a0bd44450ae3e19cb654a958f0b1615c83ebe47a48d0b519ae"


def _default_opencode_bin():
    return _stack_workdir() / OPENCODE_V2_BIN_RELPATH


def _require_opencode_bin():
    path = Path(os.environ.get("OPENCODE_PROBE_BIN") or _default_opencode_bin())
    if not path.is_absolute():
        sys.exit("REFUSED: OPENCODE_PROBE_BIN must be absolute")
    path = path.resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        sys.exit(f"REFUSED: pinned opencode binary {_portable(path)} is missing or not executable "
                 "(run scripts/install_bench_opencode.sh)")
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
        # Per ITEM with a stable name, never per run: opencode prints `<TMPDIR>/opencode` into its
        # system prompt (capture r01 line 48), so a per-run id there made same-seed passes differ
        # (smoke attempt 6). A dir shared by back-to-back invocations clashes on opencode's leftovers,
        # so each spawn gets `<base>/tmp/<scratch name>`, cleared first (`_fresh_tmpdir`).
        "TMPDIR": str(root.parent / "tmp" / Path(scratch).name) + "/",
        "OPENCODE_CONFIG_DIR": str(root / "cfg/opencode"),
        **SCAFFOLD_ENV_POLICY_V2,
        "OPENCODE_CONFIG_CONTENT": json.dumps(overlay, sort_keys=True),
        "PWD": str(scratch),
    }


def _fresh_tmpdir(env):
    """Clear and recreate the item's TMPDIR once per item, before its first spawn (the destination
    check); the run and the export reuse it. No survivor is left from the previous item, which the
    probe verifies, so nothing live is removed."""
    path = Path(env["TMPDIR"])
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


DECODE_RATES = REPO / "benchmark" / "decode_rates.json"
DEFAULT_FIRST_WRITE_TOKENS = 48000  # C139 (operator, 2026-10-08); M59 chain rows ran at 16000


def _gate_window(model, first_write_tokens, tick_s_override, stall_ticks=progress_gate.DEFAULT_STALL_TICKS):
    """C136: the first-write allowance is denominated in TOKENS. The documented draft-OFF decode
    rate of `model` (benchmark/decode_rates.json, source line recorded) turns it into a per-model
    window: tick_s = ceil(tokens / (2 * rate)), so the stall rule (2 flat ticks) equals the window
    and loop detection (3 identical ticks) is 1.5 windows. An explicit --tick-s bypasses the table
    and is recorded as a manual source; a model without an entry refuses otherwise."""
    if tick_s_override is not None:
        return {
            "first_write_tokens": first_write_tokens,
            "decode_tok_s": None,
            "decode_tok_s_source": "manual:--tick-s",
            "tick_s": int(tick_s_override),
            "stall_ticks": int(stall_ticks),
            "first_write_window_s": int(tick_s_override) * int(stall_ticks),
        }
    try:
        entry = json.loads(DECODE_RATES.read_text())["models"][model]
        rate = float(entry["tok_s"])
        source = str(entry["source"])
    except (OSError, ValueError, KeyError, TypeError):
        sys.exit(
            f"REFUSED: no documented draft-OFF decode rate for {model!r} in "
            f"{DECODE_RATES.name}; add the measured rate with its source line, or pass --tick-s explicitly"
        )
    if rate <= 0 or first_write_tokens <= 0:
        sys.exit("REFUSED: decode rate and --first-write-tokens must be positive")
    tick = math.ceil(first_write_tokens / (int(stall_ticks) * rate))
    return {
        "first_write_tokens": int(first_write_tokens),
        "decode_tok_s": rate,
        "decode_tok_s_source": source,
        "tick_s": tick,
        "stall_ticks": int(stall_ticks),
        "first_write_window_s": tick * int(stall_ticks),
    }


FIXED_MTIME = 1759708800  # 2025-10-06 00:00:00 UTC: one constant mtime for every prepared file


def _freeze_mtimes(work):
    """Set one fixed mtime on the prepared tree (`.git` included). Attempt 7 (2026-10-07): with
    identical prompts, the first divergence between two same-seed passes was the model's `ls -la`
    output showing the prepared files' modification times. Files the model writes later carry real
    times; those are the model's own actions, not the scaffold's."""
    root = Path(work)
    for path in [root, *root.rglob("*")]:
        try:
            os.utime(path, (FIXED_MTIME, FIXED_MTIME), follow_symlinks=False)
        except OSError:
            pass


def _prompt_date():
    """The local date exactly as opencode prints it into every system prompt ("Today's date: ...").
    Same-seed identity holds only while this is equal (C135); recorded on every row."""
    return time.strftime("%a %b %d %Y")


def _carrier_selection(scaffold, system_file, *, repo=None, source=None, extra_deny_file=None):
    """Resolve and snapshot approved inputs before creating a run or spawning a client."""
    repo = REPO if repo is None else repo
    extra_deny, extra_sha = [], None
    extra_path = Path(extra_deny_file) if extra_deny_file is not None else None
    if extra_path is not None:
        if scaffold != "opencode-v2-web":
            sys.exit("REFUSED: --extra-deny-file requires --scaffold opencode-v2-web")
        try:
            data = extra_path.read_bytes()
            extra_deny = json.loads(data)
            if (not isinstance(extra_deny, list) or any(
                    not isinstance(p, str) or not p.strip() or any(ord(c) < 32 for c in p)
                    for p in extra_deny)):
                raise ValueError("expected a JSON array of nonempty pattern strings")
            extra_sha = hashlib.sha256(data).hexdigest()
        except (OSError, ValueError, UnicodeError) as exc:
            sys.exit("REFUSED: invalid --extra-deny-file: " + _scrub_error(exc))
    if source is None:
        source = BENCH_OPENCODE_CONFIG if scaffold == "opencode-v2" else BENCH_OPENCODE_WEB_CONFIG
    system_path, system_bytes = None, None
    if system_file is not None:
        relative = Path(system_file)
        system_path = (repo / relative).resolve()
        allowed = (repo / "benchmark/opencode_prompts").resolve()
        if (relative.is_absolute() or not system_path.is_relative_to(allowed)
                or not system_path.is_file()):
            sys.exit("REFUSED: --agent-system-file must be a repo-relative file "
                     "under benchmark/opencode_prompts/")
        try:
            system_bytes = system_path.read_bytes()
            system_text = system_bytes.decode("utf-8")
        except (OSError, UnicodeError):
            sys.exit("REFUSED: --agent-system-file must be readable UTF-8")
    raw = source.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    system_sha = hashlib.sha256(system_bytes).hexdigest() if system_bytes is not None else None
    if system_file is not None or extra_path is not None:
        doc = json.loads(raw)
        if system_file is not None:
            doc.setdefault("agents", {}).setdefault("build", {})["system"] = system_text
        for pattern in extra_deny:
            doc.setdefault("permissions", []).append(
                {"action": "webfetch", "resource": pattern, "effect": "deny"})
        doc.setdefault("permissions", []).extend(
            {"action": "shell", "resource": pattern, "effect": "deny"}
            for pattern in answer_key.shell_deny_patterns(extra_deny))
        raw = json.dumps(doc, sort_keys=True, indent=2).encode()
    fields = {
        "scaffold": scaffold + ("+sys:" + system_sha[:8] if system_sha else ""),
        "carrier_source": (source.relative_to(repo).as_posix()
                           if source.is_relative_to(repo) else _portable(source)),
        "carrier_source_sha256": source_sha,
        "agent_system_file": system_path.relative_to(repo).as_posix() if system_path else None,
        "agent_system_sha256": system_sha,
        "extra_deny": extra_deny,
        "extra_deny_sha256": extra_sha,
        "opencode_bench_config_sha256": hashlib.sha256(raw).hexdigest(),
    }
    return {"source": source, "system_path": system_path, "extra_path": extra_path,
            "bytes": raw, "fields": fields}


def _make_run_dir(workdir, run_id, selection=None):
    selection = selection or _carrier_selection("opencode-v2", None)
    root = (workdir / "opencode-probe-v2" / ("run-" + run_id)).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for name in ("home", "cfg/opencode/plugins", "data", "state", "cache"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root.parent / "tmp").mkdir(parents=True, exist_ok=True)   # shared across runs: it reaches the prompt
    for source, target in [
        (NORETRY_PLUGIN, root / "cfg/opencode/plugins/noretry.js"),
    ]:
        target.write_bytes(source.read_bytes())
        if _sha_of(target) != _sha_of(source):
            raise provenance.ServedConfigError("M50 tripwire: non-verbatim config/plugin copy")
    config = root / "cfg/opencode/opencode.json"
    config.write_bytes(selection["bytes"])
    if _sha_of(config) != selection["fields"]["opencode_bench_config_sha256"]:
        raise provenance.ServedConfigError("M50 tripwire: written carrier sha256 differs")
    rg = shutil.which("rg", path="/opt/homebrew/bin:/usr/bin:/bin")
    if rg:
        dest = root / "cache/opencode/bin/rg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(rg).resolve(), dest)
    return root


def _scratch_root():
    return str(_stack_workdir() / "scratch/octmp.noindex")


@contextmanager
def _item_scratch_dir(name: str):
    """A FIXED scratch path per item (`<root>/oc-<name>`), never a random one.

    Smoke finding 2026-10-07: opencode's system prompt ("Working directory: ...") and every tool
    path carry the scratch directory, so a random per-run name made two same-seed sessions see
    different prompts and diverge (pilot-twice p1 vs p2 differed on all five items). A stale
    directory from a crashed run refuses (nothing is deleted silently); the directory is removed
    on exit, success or error. The 1.18 helper (`opencode_common._scratch_dir`) stays random.
    """
    root = Path(_scratch_root())
    root.mkdir(parents=True, exist_ok=True)
    path = Path(os.path.realpath(root / f"oc-{name}"))
    if path.exists():
        sys.exit(f"REFUSED: stale scratch directory {_portable(path)} exists (a crashed run?); "
                 f"inspect and remove it before rerunning this item")
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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
    # The final `step_finish` is OPTIONAL: FACTS 7b saw it absent in every normal run, but a real
    # run under test emitted it (stream-close timing), so starts == finishes or finishes + 1 are both
    # complete sequences; a retry still shows as two consecutive `step_start` (checked above).
    starts, finishes = kinds.count("step_start"), kinds.count("step_finish")
    if stop_reason != "completed" or starts == 0 or starts not in (finishes, finishes + 1):
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
    assistants = [message for message in export["messages"] if message.get("type") == "assistant"]
    for index, message in enumerate(assistants):
        if message.get("retry"):
            raise TransportAbort("export records an assistant retry")
        error = message.get("error")
        if not error:
            continue
        if nonconv == "context_overflow" and _context_overflow(error):
            continue
        if (
            nonconv in ("stalled", "looping", "hard_ceiling")
            and index == len(assistants) - 1
            and isinstance(error, dict)
            and error.get("type") == "aborted"
        ):
            continue
        raise TransportAbort("export records an assistant error")


NET_SHELL = re.compile(
    r"\b(curl\b|wget\b|git\s+(clone|fetch|pull)\b|go\s+(get|install)\b|"
    r"pip3?\s+(download|install)\b|uv\s+(pip|add)\b|cargo\s+(add|install)\b|"
    r"npx\s|gh\s|brew\s|npm\s+(view|install)\b|https?://)"
)
NET_OUTPUT_FILE = re.compile(r"(?:^|\s)(?:-[oO](?:\s|$|[^\s]+)|--output(?:=|\s|$))|>|\btee\b")


def _web_audit(export, item_dir, transcript_target, *, scaffold="opencode-v2-web"):
    """Audit failures exclude a row without interrupting generation or grading."""
    result = {"web_fetches": [], "net_shell": [], "web_denied": 0, "subagent_calls": 0,
              "web_audit_incomplete": False, "answer_key_contact": False, "answer_key_evidence": []}
    try:
        _collect_web_audit(export, item_dir, transcript_target, scaffold, result)
    except Exception as exc:
        result["web_audit_error"] = f"{type(exc).__name__}: {exc}"
    return result


def _collect_web_audit(export, item_dir, transcript_target, scaffold, result):
    """Audit native v2 tool parts; permission.rejected is pinned by real mock captures."""
    fetches, commands, texts = result["web_fetches"], result["net_shell"], []
    result["subagent_calls"] = sum(
        isinstance(part, dict) and part.get("type") == "tool" and part.get("name") == "subagent"
        for message in export["messages"] for part in (message.get("content") or []))
    result["web_audit_incomplete"] = (
        scaffold.startswith("opencode-v2-web") and result["subagent_calls"] > 0)
    for message in export["messages"]:
        for part in message.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            name, state = part.get("name"), part.get("state", {})
            if name not in ("webfetch", "shell"):
                continue
            inputs = state.get("input", {})
            error = state.get("error", {})
            rejected = (state.get("status") == "error" and isinstance(error, dict)
                        and error.get("type") == "permission.rejected")
            source = inputs.get("url" if name == "webfetch" else "command", "")
            if name == "shell" and not NET_SHELL.search(source):
                continue
            result["web_denied"] += int(rejected)
            if name == "shell" and NET_OUTPUT_FILE.search(source):
                result["web_audit_incomplete"] = True
            content = state.get("content") or []
            chunks = ([content] if isinstance(content, str) else [
                c["text"] for c in content
                if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str)
            ])
            # Preserve text blocks verbatim, without injecting separator bytes.
            text = "".join(chunks)
            status = "denied" if rejected else (
                "completed" if state.get("status") == "completed" else "error")
            if name == "webfetch":
                entry = {"url": source, "status": status}
                fetches.append(entry)
            else:
                entry = {"command": source, "status": status}
                commands.append(entry)
            if rejected:
                entry["error"] = {"message": error.get("message")}
            target = transcript_target.with_suffix(".web") / f"{len(fetches) + len(commands) - 1}.txt"
            root = _stack_workdir().resolve()
            relative = target.resolve().relative_to(root / "opencode_transcripts")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = text.encode("utf-8", errors="surrogatepass")
            target.write_bytes(data)
            entry.update(path="$STACK_WORKDIR/opencode_transcripts/" + relative.as_posix(),
                         sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            if text:
                texts.append({"source": source, "text": text})
    contact = answer_key.contact(item_dir, texts)
    result.update(answer_key_contact=contact["flag"], answer_key_evidence=contact["evidence"])


def _identity(a, version, binary, run_dir, poly_sha):
    selection = a.carrier_selection
    fields = selection["fields"]
    policy = {
        "opencode_bench_config_sha256": fields["opencode_bench_config_sha256"],
        "noretry_plugin_sha256": _sha_of(NORETRY_PLUGIN),
        "overlay_schema": OVERLAY_SCHEMA_V2,
        "env_switches": dict(SCAFFOLD_ENV_POLICY_V2),
        "scratch_git_init": True,
        "standalone": True,
        "opencode_version": version,
        "opencode_exe_sha256": _sha_of(binary),
        "cache": "per-run",
    }
    # Preserve the exact M59 recipe for the unmodified legacy scaffold.
    if fields["scaffold"] != "opencode-v2":
        policy.update(fields)
    digest = hashlib.sha256()
    for p in (
        Path(__file__),
        Path(opencode_common.__file__),
        Path(progress_gate.__file__),
        Path(provenance.__file__),
        Path(answer_key.__file__),
    ):
        digest.update(p.name.encode())
        digest.update(p.read_bytes())
    return {
        **policy,
        **fields,
        "prompt_date_at_start": _prompt_date(),
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
        **{
            k: a.gate_window[k]
            for k in ("first_write_tokens", "decode_tok_s", "decode_tok_s_source", "first_write_window_s")
        },
        "cache_bin_inventory_sha256": _cache_bin_inventory_sha256(run_dir / "cache"),
    }


def _check_resume_v2(previous, identity, router, model, *, rerun_transition=False):
    if not previous:
        sys.exit("REFUSED: rows have no manifest")
    if previous.get("served_config_drift"):
        sys.exit("REFUSED: manifest carries served_config_drift")
    old = previous.get("runtime", {})
    for key in RESUME_IDENTITY_KEYS_V2:
        # Only an explicitly linked, seed-checked P202 attempt may change the deny overlay.
        # The source carrier, prompt, model, seed and every other identity remain pinned.
        if rerun_transition and key in ("extra_deny", "extra_deny_sha256",
                                        "opencode_bench_config_sha256", "scaffold_policy_sha256"):
            continue
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


def _worker_load_identity(model, router):
    """Observe the attributed worker; absence or a racing load cannot prove identity."""
    try:
        doc = provenance.yaml.safe_load(provenance.paths.registry_path().read_text())
        before = provenance._port_listener_pids(int(doc['mlx_port']))
        workers = provenance._worker_argvs(doc)
        after = provenance._port_listener_pids(int(doc['mlx_port']))
        if len(before) != 1 or before != after or len(workers) != 1:
            return None
        pid = before[0]
        model_path = provenance._flag_value(workers[0], '--model')
        entries = doc.get('models', [])
        if (not model_path or not any(e.get('name') == model and e.get('hf_path') == model_path for e in entries)
                or not provenance._descends_from(pid, {router['pid']})):
            return None
        return {'pid': pid, 'model_path': _scrub_pii(model_path)}
    except (OSError, ValueError, TypeError, KeyError, provenance.ServingStateError):
        return None


def _same_worker(previous, current):
    return (isinstance(previous, dict) and isinstance(current, dict)
            and type(previous.get('pid')) is int and previous['pid'] > 0
            and bool(previous.get('model_path'))
            and all(previous.get(key) == current.get(key) for key in ('pid', 'model_path')))


def _rerun_resume(a, rows, out, previous, identity, router):
    """Validate an explicit per-item continuation; keep ordinary resume fail-closed."""
    states = answer_key.audit_states(rows, audit_sidecar=str(out) + '.webaudit.jsonl')
    latest = {answer_key.item_key(s['row']): s for s in states}
    try:
        answer_key.require_audits(latest.values())
    except answer_key.AuditMissing as exc:
        sys.exit(str(exc))
    done = {(s['row']['id'], s['row'].get('sample', 0)) for s in latest.values()
            if not s['cheat'] or s['row'].get('rerun_index', 0) == 2}
    transition = False
    if a.rerun_of:
        item = a.lang + '/' + a.items.strip()
        candidates = [s for s in states if s['row']['id'] == item and s['row'].get('model') == a.model]
        if not candidates:
            sys.exit("REFUSED: rerun_of has no prior item row")
        latest_state = candidates[-1]
        row = latest_state['row']
        already_written = (row.get('rerun_of') == a.rerun_of and row.get('rerun_index') == a.rerun_index)
        if already_written:
            # Reissuing a completed attempt is idempotent even if its audit still needs a retry.
            done.add((item, 0))
        else:
            plan = answer_key.rerun_plan(latest_state)
            if (not latest_state['rerun_eligible'] or plan['needs_operator']
                    or not identity['extra_deny']):
                sys.exit("REFUSED: cheat_review needs_operator; no re-run may launch")
            if (row.get('session_id') != a.rerun_of or not latest_state['cheat']
                    or a.rerun_index != row.get('rerun_index', 0) + 1):
                sys.exit("REFUSED: rerun_of/index must link the latest cheated attempt")
            if row.get('sampler_seed') != _item_seed(item, a.seed_base):
                sys.exit("REFUSED: rerun seed differs from the superseded attempt")
            if not set(plan['extra_deny']) <= set(identity['extra_deny']):
                sys.exit("REFUSED: rerun must include all planned source and prior extra deny patterns")
            done.discard((item, 0))
            old = (previous or {}).get('runtime', {})
            # An interrupted attempt has already written its new identity: compare it exactly.
            same_attempt = old.get('rerun_of') == a.rerun_of and old.get('rerun_index') == a.rerun_index
            transition = not same_attempt
        if (previous or {}).get('router', {}).get('pid') != router.get('pid'):
            sys.exit("REFUSED: rerun requires the same router instance")
        if not _same_worker(row.get('worker'), _worker_load_identity(a.model, router)):
            sys.exit("REFUSED: rerun requires the same worker load identity (pid + model_path)")
    elif any((a.lang + '/' + name.strip(), 0) not in done for name in a.items.split(',')
             if any(s['row']['id'] == a.lang + '/' + name.strip() for s in states)):
        sys.exit("REFUSED: cheated item requires explicit --rerun-of and --rerun-index")
    if rows or previous is not None:
        _check_resume_v2(previous, identity, router, a.model, rerun_transition=transition)
    return done


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
                "error": _scrub_error(error, 1000),
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
        and (
            receipt["router"].get("config_sha256") is None
            or router.get("config_sha256") is None
            or receipt["router"]["config_sha256"] == router["config_sha256"]
        )
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


def _sigterm_exit(signum, frame):
    """SIGTERM -> SystemExit(143) so `finally` blocks run: the scratch dir is removed and the opencode
    child is killed. Python's default SIGTERM action skips them (2026-10-07: a stopped runner left
    `oc-affine-cipher` behind and the relaunch refused on the stale-scratch guard)."""
    raise SystemExit(143)


def _install_sigterm_exit():
    signal.signal(signal.SIGTERM, _sigterm_exit)


def main():
    """Run the v2 probe, reporting policy refusals without grading them."""
    _install_sigterm_exit()
    try:
        return _main()
    except provenance.ServedConfigError as e:
        sys.exit("REFUSED: " + _scrub_error(e))


def _print_identity_requested():
    return "--print-identity" in sys.argv[1:]


def _main():
    if _print_identity_requested():
        # C147 §3: read-only provenance identity; no router, worker or model is touched.
        pre = argparse.ArgumentParser(allow_abbrev=False)
        pre.add_argument("--print-identity", action="store_true")
        pre.add_argument("--universe", type=Path)
        pre.add_argument("--agent-system-file")
        pre.add_argument("--tg1-inject", choices=("stall", "loop", "alloc"))
        known, _ = pre.parse_known_args()
        from bench import tg1_runner
        return tg1_runner.print_identity(sys.modules[__name__], known)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--seed-base", type=int, required=True)
    ap.add_argument("--scaffold", choices=["opencode-v2-web", "opencode-v2", "opencode-v2-web-tg1"], default="opencode-v2-web")
    ap.add_argument("--universe", type=Path)
    ap.add_argument("--expect-items")
    ap.add_argument("--agent-system-file")
    ap.add_argument("--extra-deny-file", type=Path)
    ap.add_argument("--rerun-of")
    ap.add_argument("--rerun-index", type=int, choices=(1, 2))
    ap.add_argument(
        "--lang", choices=["python", "go", "rust", "java", "javascript"], default="python"
    )
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--chain-total", type=int, default=0)
    ap.add_argument("--a4-v2-receipt")
    ap.add_argument("--allow-version-drift", action="store_true")
    ap.add_argument(
        "--tick-s", type=int, default=None,
        help="explicit gate tick (seconds); default: derived per model from --first-write-tokens (C136)",
    )
    ap.add_argument(
        "--first-write-tokens", type=int, default=DEFAULT_FIRST_WRITE_TOKENS,
        help="C136: token allowance before the stall rule may fire, converted per model with "
             "benchmark/decode_rates.json",
    )
    for key, default in [
        ("hard-ceiling-s", progress_gate.DEFAULT_HARD_CEILING_S),
        ("stall-ticks", progress_gate.DEFAULT_STALL_TICKS),
        ("loop-repeats", progress_gate.DEFAULT_LOOP_REPEATS),
    ]:
        ap.add_argument("--" + key, type=int, default=default)
    ap.add_argument("--poll-s", type=float, default=5.0)
    # C147 (tg1 only): injected positives, cooperative cancellation, manifest barrier, sampling profile.
    ap.add_argument("--tg1-inject", choices=("stall", "loop", "alloc"))
    ap.add_argument("--cancel-file")
    ap.add_argument("--manifest-ack")
    ap.add_argument("--sampling-profile", choices=("deployed",))
    ap.add_argument("--print-identity", action="store_true", help="print the probe identity JSON and exit")
    a = ap.parse_args()
    if a.scaffold != "opencode-v2-web-tg1" and (
        a.tg1_inject or a.cancel_file or a.manifest_ack or a.sampling_profile
    ):
        sys.exit("REFUSED: --tg1-inject/--cancel-file/--manifest-ack/--sampling-profile require "
                 "--scaffold opencode-v2-web-tg1")
    if a.scaffold == "opencode-v2-web-tg1":
        ap.allow_abbrev = False
        a = ap.parse_args()
        from bench import tg1_runner
        return tg1_runner.main(sys.modules[__name__], a)
    if bool(a.rerun_of) != (a.rerun_index is not None):
        sys.exit("REFUSED: --rerun-of and --rerun-index must be supplied together")
    if a.rerun_of and (a.scaffold != "opencode-v2-web" or a.extra_deny_file is None
                       or len(a.items.split(',')) != 1):
        sys.exit("REFUSED: reruns require opencode-v2-web, --extra-deny-file and exactly one item")
    a.carrier_selection = _carrier_selection(a.scaffold, a.agent_system_file,
                                             extra_deny_file=a.extra_deny_file)
    if (a.tick_s is not None and a.tick_s <= 0) or a.first_write_tokens <= 0 or any(
        getattr(a, k) <= 0
        for k in ("hard_ceiling_s", "stall_ticks", "loop_repeats", "poll_s")
    ) or (a.limit is not None and a.limit <= 0):
        sys.exit("REFUSED: gate parameters and limit must be positive")
    a.gate_window = _gate_window(a.model, a.first_write_tokens, a.tick_s, stall_ticks=a.stall_ticks)
    a.tick_s = a.gate_window["tick_s"]
    items = list(dict.fromkeys(s.strip() for s in a.items.split(",") if s.strip()))
    if not items or any(Path(s).name != s or s in (".", "..") for s in items):
        sys.exit("REFUSED: items must be exercise basenames")
    if a.limit:
        items = items[: a.limit]
    workdir = _stack_workdir().resolve()
    if not workdir.is_dir():
        sys.exit("REFUSED: STACK_WORKDIR must exist")
    binary = _require_opencode_bin()
    selection = a.carrier_selection
    carrier = json.loads(selection["bytes"])
    model = carrier["providers"]["mlx-local"]["models"].get(a.model)
    if model is None:
        sys.exit("REFUSED: model absent from v2 bench carrier")
    base = carrier["providers"]["mlx-local"]["settings"]["baseURL"]
    # Check the configured local owner before creating run directories or starting a client.
    router = provenance.assert_served_config(base, env={})
    receipt = _a4_receipt(
        a.a4_v2_receipt, router, a.limit, a.model, _sha_of(binary),
        selection["fields"]["opencode_bench_config_sha256"],
    )
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    run_dir = _make_run_dir(workdir, run_id, selection)
    carrier_sha = selection["fields"]["opencode_bench_config_sha256"]
    plugin_sha = _sha_of(NORETRY_PLUGIN)

    def env_check(env, overlay):
        """Env check."""
        provenance.opencode_v2_env_check(env, run_dir, carrier_sha, plugin_sha, overlay)
        if (_sha_of(selection["source"]) != selection["fields"]["carrier_source_sha256"]
                or _sha_of(NORETRY_PLUGIN) != plugin_sha
                or (selection["system_path"] and _sha_of(selection["system_path"])
                    != selection["fields"]["agent_system_sha256"])
                or (selection["extra_path"] and _sha_of(selection["extra_path"])
                    != selection["fields"]["extra_deny_sha256"])):
            raise provenance.ServedConfigError(
                "M50 tripwire: repository carrier/plugin/system prompt/extra deny changed during run"
            )

    with _scratch_dir("discovery") as scratch:
        _git_init_scratch(scratch)
        overlay = _seed_overlay(a.model, _item_seed(a.lang + "/" + items[0], a.seed_base))
        env = _opencode_env(run_dir, scratch, overlay)
        _fresh_tmpdir(env)
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
    shutil.rmtree(Path(env["TMPDIR"]), ignore_errors=True)   # the discovery TMPDIR is random-named: never leave it
    polyglot = _polyglot_root()
    identity = _identity(a, version, binary, run_dir, _polyglot_sha(polyglot))
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / "opencode-v2.jsonl"
    mp = out.with_suffix(".manifest.json")
    _load_rows(out)  # Preserve the shared malformed/truncated-file refusal before reading rows.
    rows = ([json.loads(line) for line in out.read_text().splitlines() if line.strip()]
            if out.exists() else [])
    try:
        previous = json.loads(mp.read_text()) if mp.exists() else None
    except (ValueError, OSError) as e:
        sys.exit("REFUSED: unreadable existing manifest: " + _scrub_error(e))
    done = _rerun_resume(a, rows, out, previous, identity, router)
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
            with _item_scratch_dir(name) as tmp:   # fixed path: identical prompt across same-seed passes
                work = tmp / name
                _prepare(src, work)
                _git_init_scratch(work)
                _freeze_mtimes(work)   # reproducible `ls -la` output (attempt 7)
                seed = _item_seed(item, a.seed_base)
                overlay = _seed_overlay(a.model, seed)
                env = _opencode_env(run_dir, work, overlay)
                _fresh_tmpdir(env)
                env_check(env, overlay)
                if not wrote:
                    runtime = {
                        **identity,
                        "rerun_of": a.rerun_of,
                        "rerun_index": a.rerun_index or 0,
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
                    prompt_date = _prompt_date()   # captured at spawn; opencode prints this date into the prompt
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
                    tag = out.stem + (f".rerun-{a.rerun_index}.{run_id}" if a.rerun_of else "")
                    target, transcript = _transcript_target(a.model, a.lang, name, tag=tag)
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
                        **selection["fields"],
                        **json.loads(_scrub_pii(json.dumps(_web_audit(
                            export, src, target, scaffold=a.scaffold)))),
                        "schema_version": 3,
                        "id": item,
                        "model": a.model,
                        "sample": 0,
                        "prompt_date": prompt_date,
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
                        "rerun_of": a.rerun_of,
                        "rerun_index": a.rerun_index or 0,
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
                if a.scaffold == "opencode-v2-web":
                    row["worker"] = _worker_load_identity(a.model, router)
                    if a.rerun_of:
                        source = next(r for r in reversed(rows) if r.get('session_id') == a.rerun_of)
                        if not _same_worker(source.get('worker'), row['worker']):
                            _abort(mp, run_id, item, work, rc, stop_reason, "worker load identity changed during rerun")
                    _stamp_manifest(mp, {"worker": row["worker"]})
                with out.open("a") as stream:
                    stream.write(json.dumps(row) + "\n")
                done.add((item, 0))
                if row["answer_key_contact"]:
                    print(f"{item}: flagged: answer-key contact (requires P202 re-run)", flush=True)
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
