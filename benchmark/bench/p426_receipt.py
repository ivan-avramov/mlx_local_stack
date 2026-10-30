"""B2 (P426) arm-equality receipt, pair gate and pair dossier (spec 6.3 - 6.5, 16.1, 16.2, C238 / [d2]).

`arm_receipt` records, after load, what the arm's processes ARE: argv and environment of the router, the worker and the probe,
the interpreters' verified content inventories, the native libraries the worker loaded, the probe entry and the snapshot
hashes - with `<WT>` / `<OUT>` / `$STACK_WORKDIR` / `$HOME` canonicalized so the record is portable and two arms compare
equal. Credential KEYS are recorded per process; their values (and any hash of them) never enter a record. `pair_problems` is
the closed pair gate: the only differences it allows are the three MTP flag pairs of the ON worker argv, the drafter snapshot
(ON only) and the presence of keys on the volatile list; the roots are canonicalized away and the arm commit is not a receipt
field. Anything else is a problem (systemic in the chain)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import p426_hooks as ph
from . import p426_secrets as secrets

VOLATILE_KEYS = ("_", "OLDPWD", "PWD", "SHLVL", "TERM_SESSION_ID", "SECURITYSESSIONID")
VOLATILE_PREFIXES = ("__CF",)
VOLATILE = "<volatile>"
ALLOWED_DIFFERENCES = ("worker_argv.mtp_pairs", "snapshots.drafter")
MTP_FLAGS = ("--draft-kind", "--draft-model", "--mtp-verify-scan")
MTP_VALUES = {"--draft-kind": "mtp", "--mtp-verify-scan": "joint_v1"}       # --draft-model is the entry's drafter (checked vs the snapshot)
NATIVE_LIBRARIES = ("libmlx.dylib", "mlx.metallib")
EDITABLE_DISTRIBUTIONS = ("mlx-vlm", "mlx-serve")
PROCESSES = ("router", "worker", "probe")
PINS_RELATIVE = "src/mlx-vlm/dev/p369_phase2/pins.json"


class ReceiptError(Exception):
    """The receipt cannot be built or a check on its inputs failed (systemic in the chain)."""


def is_volatile(key: str, volatile=VOLATILE_KEYS) -> bool:
    return key in volatile or any(key.startswith(p) for p in VOLATILE_PREFIXES)


# -- canonical roots
class Canon:
    """Replaces the worktree, out-root, `$STACK_WORKDIR` and `$HOME` (given and realpath forms, longest first, at a path
    boundary) so a record carries no absolute path of this box."""

    def __init__(self, worktree, out_root, workdir=None, home=None, user=None):
        roots = []
        for raw, label in ((worktree, "<WT>"), (out_root, "<OUT>"), (workdir, "$STACK_WORKDIR"), (home, "$HOME")):
            if not raw:
                continue
            for form in {str(raw).rstrip("/"), str(Path(raw).resolve()).rstrip("/")}:
                if form:
                    roots.append((form, label))
        roots.sort(key=lambda r: -len(r[0]))
        self.rules = [(re.compile(re.escape(form) + r"(?![A-Za-z0-9_.+-])"), label) for form, label in roots]
        self.user = user

    def text(self, value):
        value = str(value)
        for rx, label in self.rules:
            value = rx.sub(label, value)
        return value

    def argv(self, tokens):
        return [self.text(t) for t in tokens]

    def env_value(self, key, value):
        if key in ("USER", "LOGNAME") and self.user and value == self.user:
            return "<user>"
        return self.text(value)


# -- the receipt
def environ_record(env, canon, credential_keys_out):
    """({key: value | '<volatile>'}, sorted credential keys): credential keys are listed and their values dropped."""
    record, creds = {}, []
    for key in sorted(env):
        if secrets.is_credential_key(key):
            creds.append(key)
        elif is_volatile(key):
            record[key] = VOLATILE
        else:
            record[key] = canon.env_value(key, env[key])
    credential_keys_out.extend(creds)
    return record


def probe_entry_of(argv):
    """The probe entry script: the first `.py` argument (the interpreter comes first)."""
    for token in argv[1:]:
        if str(token).endswith(".py"):
            return str(token)
    raise ReceiptError(f"the probe command line names no entry script: {argv[:3]}")


def interpreter_record(raw, canon):
    ed = {}
    for name, e in (raw.get("editables") or {}).items():
        tree = canon.text(e.get("tree"))
        if e.get("clean") is not True:
            raise ReceiptError(f"editable {name}: the source tree is not clean (git status --porcelain)")
        if tree != f"<WT>/src/{name}":
            raise ReceiptError(f"editable {name}: its source tree {tree!r} is not <WT>/src/{name}")
        ed[name] = dict(tree=tree, gitlink=e.get("gitlink"), clean=True)
    return dict(path=canon.text(raw["path"]), inventory_sha256=raw["inventory_sha256"], editables=ed)


def arm_receipt(ops, *, worktree, out_root, pids, model=None, probe_launch=None) -> dict:
    """The sealed arm-equality receipt (spec 6.4). `pids` = {router, worker, probe}; at the after-load checkpoint no probe
    process exists yet, so `pids['probe']` is None and `probe_launch` = {argv, env} (what the chain gives every probe) stands
    in for its command line and environment. `model` names the registry entry whose snapshots are recorded."""
    router_env = ops.proc_environ(pids["router"])
    canon = Canon(worktree, out_root, workdir=getattr(ops, "wd", None) or router_env.get("STACK_WORKDIR"),
                  home=router_env.get("HOME"), user=router_env.get("USER"))
    argvs, envs, creds, interpreters, exes = {}, {}, {}, {}, {}
    for proc in PROCESSES:
        pid = pids.get(proc)
        if pid is not None:
            argv, env = ops.proc_argv(pid), ops.proc_environ(pid)
        elif proc == "probe" and probe_launch:
            argv, env = list(probe_launch["argv"]), dict(probe_launch["env"])
        else:
            raise ReceiptError(f"no pid and no launch spec for the {proc}")
        argvs[proc], creds[proc] = argv, []
        envs[proc] = environ_record(env, canon, creds[proc])
        creds[proc].sort()
        inv = (ops.interpreter_inventory(pid) if pid is not None
               else ops.interpreter_inventory_at(argv[0]))               # the probe's: its launch interpreter, no process yet
        rec = interpreter_record(inv, canon)
        if interpreters.setdefault(rec["path"], rec) != rec:
            raise ReceiptError(f"interpreter {rec['path']}: its content inventory differs between the processes that use it ({proc})")
    images = sorted((dict(path=canon.text(i["path"]), sha256=i["sha256"]) for i in ops.loaded_images(pids["worker"])),
                    key=lambda i: i["path"])
    for lib in NATIVE_LIBRARIES:
        if not any(i["path"].rsplit("/", 1)[-1] == lib for i in images):
            raise ReceiptError(f"the worker did not load {lib} (not among its loaded images)")
    snaps = ops.snapshot_hashes(model)
    doc = dict(argv=dict(router=canon.argv(argvs["router"]), worker=canon.argv(argvs["worker"])), env=envs,
               credential_keys=creds, interpreters=sorted(interpreters.values(), key=lambda i: i["path"]), loaded_images=images,
               probe_entry=canon.text(probe_entry_of(argvs["probe"])), snapshots=snaps)
    return ph.seal(doc)


# -- argv and snapshot checks (spec 6.3, 3)
def worker_argv_problems(actual, expected, arm) -> list:
    """The worker's argv equals the one mlx-serve builds from the served entry EXACTLY (no tolerated leading tokens, spec
    16.7), and the arm's predictor flags are exactly its own: OFF none of the three, ON each exactly once."""
    problems = []
    actual, expected = [str(t) for t in actual], [str(t) for t in expected]
    if actual != expected:
        problems.append("argv.worker: the worker command line differs from the one mlx-serve builds from the served entry")
    for flag in MTP_FLAGS:
        n = sum(t == flag for t in actual)
        if arm == "off" and n:
            problems.append(f"argv.worker: the OFF worker carries {flag}")
        elif arm == "on" and n != 1:
            problems.append(f"argv.worker: the ON worker carries {flag} x{n} (exactly once)")
    return problems


def snapshot_problems(snapshots, pins, model, arm) -> list:
    """Every loaded snapshot is EXACTLY the pinned one (revision, file set, each sha256): the target always, the drafter ON
    only (OFF loads none)."""
    if model not in (pins or {}):
        return [f"snapshots: {model}: no reviewed pins"]
    problems = []
    for role in ("target", "drafter"):
        got, want = (snapshots or {}).get(role), pins[model][role]
        if role == "drafter" and arm == "off":
            if got:
                problems.append("snapshots.drafter: an OFF arm records a drafter snapshot")
            continue
        if not got:
            problems.append(f"snapshots.{role}: missing")
        elif (got.get("hf_path"), got.get("revision")) != (want["hf_path"], want["revision"]):
            problems.append(f"snapshots.{role}: {got.get('hf_path')}@{got.get('revision')} != pinned {want['hf_path']}@{want['revision']}")
        elif got.get("files") != want["files"]:
            diff = sorted(p for p in set(got.get("files") or {}) | set(want["files"]) if (got.get("files") or {}).get(p) != want["files"].get(p))
            problems.append(f"snapshots.{role}: files differ from the pins: {diff}")
    return problems


def load_pins(worktree) -> dict:
    path = Path(worktree) / PINS_RELATIVE
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        raise ReceiptError(f"the fork's pins.json is missing or unreadable at <WT>/{PINS_RELATIVE}") from None


# -- the pair gate (spec 6.5)
def arm_of(receipt):
    flags = [t for t in receipt["argv"]["worker"] if t in MTP_FLAGS]
    return "on" if "--draft-kind" in flags else "off"


def strip_pairs(argv):
    """(argv without the three flag pairs, {flag: [values]}); a flag at the end of the list has no value."""
    rest, pairs, i = [], {f: [] for f in MTP_FLAGS}, 0
    while i < len(argv):
        if argv[i] in MTP_FLAGS:
            pairs[argv[i]].append(argv[i + 1] if i + 1 < len(argv) else None)
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return rest, pairs


def sealed_problem(name, receipt):
    return None if ph.sealed_ok(receipt) else f"receipt.{name}: the receipt's sha256 does not verify (or it is not a receipt)"


def pair_problems(first, second) -> list:
    """Every difference between the two legs' receipts that the closed `ALLOWED_DIFFERENCES` list does not name (spec 6.5);
    the closed and volatile lists are module constants, not parameters (spec 16.7)."""
    allowed, volatile = ALLOWED_DIFFERENCES, VOLATILE_KEYS
    bad = [p for p in (sealed_problem("first", first), sealed_problem("second", second)) if p]
    if bad:
        return bad
    problems = []
    arms = (arm_of(first), arm_of(second))
    if sorted(arms) != ["off", "on"]:
        return ["receipt: a pair is one OFF and one ON leg (the worker argvs say " + " and ".join(arms) + ")"]
    off, on = (first, second) if arms[0] == "off" else (second, first)
    if first["argv"]["router"] != second["argv"]["router"]:
        problems.append("argv.router: differs between the legs")
    # worker argv: OFF's tokens in order plus exactly the three pairs, position-free
    rest, pairs = strip_pairs(on["argv"]["worker"])
    if "worker_argv.mtp_pairs" not in allowed:
        problems.append("argv.worker: the MTP flag pairs are not an allowed difference")
    elif strip_pairs(off["argv"]["worker"])[1] != {f: [] for f in MTP_FLAGS}:
        problems.append("argv.worker: the OFF worker carries an MTP flag")
    else:
        if rest != off["argv"]["worker"]:
            problems.append("argv.worker: differs between the legs beyond the three MTP flag pairs")
        for flag in MTP_FLAGS:
            if len(pairs[flag]) != 1 or pairs[flag][0] is None:
                problems.append(f"argv.worker: the ON worker must carry {flag} with one value (found {len(pairs[flag])})")
        for flag, value in MTP_VALUES.items():
            if pairs[flag] != [value]:
                problems.append(f"argv.worker: {flag} must be {value!r} in the ON worker")
    # environment, credential keys
    for proc in PROCESSES:
        a, b = first["env"][proc], second["env"][proc]
        for key in sorted(set(a) | set(b)):
            if is_volatile(key, volatile):
                continue
            if VOLATILE in (a.get(key), b.get(key)):
                problems.append(f"env.{proc}: {key} is marked volatile but is not on the closed volatile list")
            elif key not in a or key not in b:
                problems.append(f"env.{proc}: {key} is present in the {'first' if key in a else 'second'} leg only")
            elif a[key] != b[key]:
                problems.append(f"env.{proc}: {key} differs")          # never the values: a misclassified secret must not reach a log
        ca, cb = set(first["credential_keys"][proc]), set(second["credential_keys"][proc])
        for key in sorted(ca ^ cb):
            problems.append(f"credential_keys.{proc}: {key} is present in the {'first' if key in ca else 'second'} leg only")
    # interpreters, native images, probe entry
    if first["interpreters"] != second["interpreters"]:
        problems.append("interpreters: the interpreters' paths, content inventories or editable source trees differ")
    if first["loaded_images"] != second["loaded_images"]:
        problems.append("loaded_images: the native libraries the workers loaded differ")
    if first["probe_entry"] != second["probe_entry"]:
        problems.append("probe_entry: differs between the legs")
    # snapshots: the target equal, the drafter on the ON leg only and the one the ON worker names
    if first["snapshots"]["target"] != second["snapshots"]["target"]:
        problems.append("snapshots.target: the target snapshot revision or file hashes differ")
    d_off, d_on = off["snapshots"].get("drafter"), on["snapshots"].get("drafter")
    if d_off:
        problems.append("snapshots.drafter: the OFF leg records a drafter snapshot")
    if not d_on:
        problems.append("snapshots.drafter: the ON leg records no drafter snapshot")
    elif "snapshots.drafter" not in allowed:
        problems.append("snapshots.drafter: the drafter snapshot is not an allowed difference")
    elif pairs["--draft-model"] and pairs["--draft-model"][0] != d_on.get("hf_path"):
        problems.append("snapshots.drafter: the ON worker's --draft-model is not the drafter snapshot that was hashed")
    return problems


def observed_differences(first, second) -> list:
    """The allowed differences actually present, as dossier entries `{process: router|worker|probe|-, field, off, on}` (spec
    16.7; `field` is the dotted receipt path; the receipts are already canonicalized and hold no credential value, so an
    entry never carries one). Sorted by (process, field); `off` / `on` are the OFF leg's and the ON leg's value."""
    arms = (arm_of(first), arm_of(second))
    off, on = (first, second) if arms[0] == "off" else (second, first)
    out = []
    if arms[0] != arms[1]:
        _rest, flags = strip_pairs(on["argv"]["worker"])
        out.append(dict(process="worker", field="argv.worker", off=None,
                        on=" ".join(f"{f} {v}" for f in MTP_FLAGS for v in flags[f])))
    d_off, d_on = off["snapshots"].get("drafter") or None, on["snapshots"].get("drafter") or None
    if d_off != d_on:
        out.append(dict(process="-", field="snapshots.drafter", off=(d_off or {}).get("revision"),
                        on=(d_on or {}).get("revision")))
    for proc in PROCESSES:
        for key in sorted(set(off["env"][proc]) | set(on["env"][proc])):
            if is_volatile(key) and (key in off["env"][proc]) != (key in on["env"][proc]):
                out.append(dict(process=proc, field=f"env.{key}", off=off["env"][proc].get(key), on=on["env"][proc].get(key)))
    return sorted(out, key=lambda d: (d["process"], d["field"]))


# -- the pair dossier (spec 6.5, 16.1, 16.7)
PAIRS = ("r1", "pilot", "s1", "s2", "reload", "makeup")
ATTEMPT = re.compile(r"^.+\.a([1-9][0-9]*)$")


def _file_sha256(path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_dossier(path, *, pair, off, on, differences, verdict) -> dict:
    """Exclusive-create the immutable dossier of one pair attempt (spec 16.1 / 16.7):
    `{pair, arms: {off: {attempt, receipt_sha256, harvest_sha256}, on: {...}}, differences, verdict, at, sha256}`.
    `off` / `on` = `{attempt, receipt, harvest}`: `attempt` the attempt name `<leg>.a<n>`, `receipt` / `harvest` PATHS of the
    receipt and the `HARVEST.json`; the dossier records the files' sha256. `path` is
    `pairs/<pair>__off-a<n>__on-a<m>.json`. `differences` = `{process, field, off, on}` entries."""
    from . import chain_ops as co
    if pair not in PAIRS:
        raise ValueError(f"pair must be one of {PAIRS}, not {pair!r}")
    arms, nums = {}, {}
    for arm, spec in (("off", off), ("on", on)):
        m = ATTEMPT.match(str(spec["attempt"]))
        if not m:
            raise ValueError(f"{arm}.attempt must be the attempt name <leg>.a<n>, not {spec['attempt']!r}")
        nums[arm] = m.group(1)
        arms[arm] = dict(attempt=spec["attempt"], receipt_sha256=_file_sha256(spec["receipt"]),
                         harvest_sha256=_file_sha256(spec["harvest"]))
    path = Path(path)
    name = f"{pair}__off-a{nums['off']}__on-a{nums['on']}.json"
    if path.name != name:
        raise ValueError(f"the dossier's name must be {name}, not {path.name}")
    if verdict == "PASS":                                  # P43: a passing dossier is consistent with its own receipts
        try:
            found = pair_problems(json.loads(Path(off["receipt"]).read_text()), json.loads(Path(on["receipt"]).read_text()))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            found = [f"a receipt is unreadable or malformed ({type(exc).__name__})"]
        if found:
            raise ValueError("a PASS dossier cannot carry pair problems: " + "; ".join(found)[:400])
    return ph.write_exclusive(path, dict(pair=pair, arms=arms, differences=list(differences), verdict=verdict,
                                         at=co.utc_stamp()))
