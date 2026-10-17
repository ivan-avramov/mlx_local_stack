"""Generation core of the hermetic, seeded opencode 2.x probes (M59/M62; P311-lite extraction).

Carrier selection, run-directory and environment construction, scratch and mtime freezing, the pinned-binary
check, the A4 receipt, worker load identity and the spawn-time prompt date. Both entries use it: the standard v2
probe (`run_opencode_probe_v2.py`, which also scores in-process) and the tg1 probe (`run_tg1_probe.py`, which does
not). It imports no scoring module (`answer_key`, `web_scan`, `web_audit*`, `tg1_score`), so the tg1 generation
identity (an import closure) is not orphaned by a scoring fix.

`bind(namespace)` copies this module's definitions into an entry module's namespace, rebinding every function to
that namespace's globals (the `opencode_common.reexport` pattern): a test or caller that patches a name on the
entry still reaches the function bodies that moved here."""

from __future__ import annotations

from contextlib import contextmanager
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
from types import FunctionType

# The shared `opencode_common` bodies are rebound to the importing namespace (`reexport` / `bind`), so every global
# they read must exist here: getpass, tempfile, progress_gate, the stdlib names above.
from bench import deny_rules, opencode_common, progress_gate, provenance

opencode_common.reexport(globals())


REPO = Path(__file__).resolve().parents[2]


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
            for pattern in deny_rules.shell_deny_patterns(extra_deny))
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



def bind(namespace):
    """Install this core into an entry module's namespace (see the module docstring). Entry-specific definitions
    follow the call and may shadow anything bound here."""
    for name, value in list(globals().items()):
        if name.startswith("__") or name in ("bind", "annotations"):
            continue
        if isinstance(value, FunctionType) and value.__module__ == __name__:
            decorated = hasattr(value, "__wrapped__")
            target = value.__wrapped__ if decorated else value
            fn = FunctionType(target.__code__, namespace, name, target.__defaults__, target.__closure__)
            fn.__kwdefaults__ = target.__kwdefaults__
            fn.__annotations__ = target.__annotations__
            fn.__doc__ = target.__doc__
            fn.__module__ = namespace.get("__name__", fn.__module__)
            namespace[name] = contextmanager(fn) if decorated else fn
        else:
            namespace[name] = value
