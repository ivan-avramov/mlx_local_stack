"""B2 (P426) frozen records (spec docs/specs/p426-b2-tg1-wave2.md sections 1, 10.1, 10.2, 16.1, 16.2, 16.7, C226):

  python -m bench.p426_freeze rehearsal --off-worktree W --on-worktree W --out-root R --out manifest.json
  python -m bench.p426_freeze v8 --off-worktree W --on-worktree W --rehearsal-manifest M --r1-off L --r1-on L --r2 L --r3 L --out v8_base.json
  python -m bench.p426_freeze amend --v8 v8_base.json --pilot-off L --pilot-on L --out amendment.json

Each command derives and verifies its inputs from the live worktrees and the legs' roots, runs its preconditions and only then
exclusive-creates the self-hashed record (`p426_hooks.write_exclusive`); any failure writes nothing, prints one stderr line
`REFUSED: <reason>` and exits 2. `v8` accepts only a rehearsal in which R1 (the positive pair) is VALID with its pair gate and
engagement proven, R2 is INVALID for the injected reconciliation mismatch and R3 is VALID with its kill scored; the observed R1
pair difference (`r1_env_difference`) must lie inside spec 6.5's closed allowed list. `ops` supplies what only the box knows
(`worktree_state`, `identity`, `build_inputs`, `historical_walls`); every other precondition (the restore diff, entry points, venvs,
K3, the production tree) goes through `checks(kind, **inputs)`, which returns the failed ones; a missing seam is a refusal. Records name paths in the portable form `$STACK_WORKDIR/...` (spec 16.7)."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from . import chain_ops as co
from . import chain_rows as cr
from . import datefreeze
from . import p426_hooks as ph
from . import p426_plan
from . import p426_receipt as pr
from . import p426_reconcile as prc
from . import p426_record

KIND_REHEARSAL, KIND_V8, KIND_AMENDMENT = "p426_rehearsal", "p426_v8_base", "p426_timeout_amendment"
VOLATILE_ENV_KEYS = [*pr.VOLATILE_KEYS, "__CF*"]                     # spec 6.4's closed list, as v8 records it
CHAIN_ENTRY = ("benchmark", "chains", "c147", "run_tg1_chain.py")    # in parts: this module reads no chain rows (test_p371_chain_rows)
ITEM_COUNT = {"python": 22, "go": 21}                                 # one session leg (spec 1)
PILOT_N = 5
DEADLINE_FACTOR, DEADLINE_SLACK_S = 1.5, 1800.0                       # spec 10.2
R2_REASON = "reconciliation mismatch (injected)"                      # spec 16.8: R2's exact INVALID reason
KILL_CASES = ("kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted")    # the PROBE-kill cases only: R3 injects a probe kill, a client abort is not one
REHEARSAL_R1_ITEMS = {"python": 3, "go": 2}                           # P589: 1 pilot + 2 full Python items, then 2 Go items
COUNTED_STATUSES = ("validated", "partial_incident", "hook_stopped")  # invocations whose rows belong to the leg
GITLINKS = (("mlx_vlm", "src/mlx-vlm"), ("mlx_serve", "src/mlx-serve"))
IDENTITY_KEYS = ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")
ENTRY_POINTS = (".venv/bin/python", ".venv-bench/bin/python", "src/mlx-vlm/.venv/bin/python",       # P514: the fork venv too
                "/".join(CHAIN_ENTRY), "benchmark/run_tg1_probe.py", "benchmark/m1/bench_watch.py")
HELP_ENTRIES = ("/".join(CHAIN_ENTRY), "benchmark/run_tg1_probe.py")                              # K3: the real entry point answers --help
PINS_RELATIVE = pr.PINS_RELATIVE
REHEARSAL_DIR = "p426/rehearsal"
# ---- M76 B4b-1 (spec m76-b4b-tg2-runner v5, §3): the tg2 legs of lever kv
TG2_CHAIN_ENTRY = ("benchmark", "chains", "c147", "run_tg2_chain.py")
TG2_PROBE_ENTRY = "benchmark/run_tg2_probe.py"
TG2_LANGS = ("rust", "javascript", "java", "cpp")
TG2_REHEARSAL_DIR = "m76/p426/rehearsal.tg2"
TG2_PILOT_DEADLINE_S = 6 * 3600.0                 # = p426_wave2.REHEARSAL_DEADLINE_S (tested equal): the pilot has no walls yet
TG2_PILOT_N = 4                                   # one item per language
TG2_WALL_FLOOR_S = 382.0                          # w_<lang>_s = max(max pilot wall of <lang> over both arms, 382)
TG2_MAX_ITEM_S = 3660.0                           # one P223 maximum item, added to every tg2 session deadline
TG2_ITEM_COUNT = {"s1": 20, "s2": 20, "reload": 5}             # items per language of each amended leg (the table of §2)
TG2_PAIR = ("n16", "x")                          # change review L6: the one tg2 pair (reference N16, treatment X) of B4b-1


def check_tg2_pair(arms):
    """The tg2 pair contract, enforced at every tg2 entry point: exactly (n16, x) in role order; else Refusal."""
    if tuple(arms or ()) != TG2_PAIR:
        raise Refusal(f"the tg2 legs of B4b-1 run the pair {','.join(TG2_PAIR)} only (N16 reference, X treatment), not "
                      f"{','.join(map(str, arms or ())) or 'none'}")
    return TG2_PAIR
KIND_POSITIVES = "tg2_positives"
POSITIVE_KINDS = ("stall", "loop", "alloc")
POSITIVE_VARIANTS = ("stub", "reference")
# C361 (1) / S26 §4: loop / alloc may be declined by the model (C152); the marker of the planted command per kind
DECLINE_MARKERS = {"loop": "sleep 600", "alloc": "bytearray("}


def declinable_verify_verdict(verdict) -> bool:
    """inject_verify verdicts a model's decline can produce (S26 erratum 1): `not_observed*` only; every `FAIL:*` (incl.
    `FAIL:no_shell_part`) and `competing_trigger:*` stays a failure."""
    return isinstance(verdict, str) and (verdict == "not_observed" or verdict.startswith("not_observed:"))


def declined_ok(entry) -> bool:
    """A DECLINED inject entry is acceptable: loop / alloc only, with `declined_evidence` naming the kind's marker, an events
    sha256, a declinable inject_verify verdict, no recorded kill, probe rc 0 and the entry's own `row_sha256` (S26 erratum 11)."""
    ev = entry.get("declined_evidence") if isinstance(entry, dict) else None
    kind = entry.get("kind") if isinstance(entry, dict) else None

    def hex64(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    return (kind in DECLINE_MARKERS and isinstance(ev, dict) and ev.get("marker") == DECLINE_MARKERS[kind]
            and hex64(ev.get("events_sha256"))
            and hex64(ev.get("row_sha256")) and ev.get("row_sha256") == entry.get("row_sha256")
            and declinable_verify_verdict(ev.get("verify_verdict"))
            and ev.get("kills") == 0 and type(ev.get("kills")) is int
            and ev.get("probe_rc") == 0 and type(ev.get("probe_rc")) is int)


# C366 (S27-P6): two positives verdicts ruled after the 2026-11-19 tg2 positives
TRANSFER_KINDS = {"stall": ("not_observed:trailing", "stalled"), "loop": ("not_observed:cancellation", "looping")}
TRANSFER_REFERENCE_SHA256 = "1861db0175e0a97204874bc4bf13677746153a9475978302d9bca0c9f1c20be0"   # 11-17 positives (c7c6993a)
WAIVED_VERIFY_VERDICT = "FAIL:unrelated_kill"
# The stop / cancel / reconcile path the transfer relies on (C366 r1 P1: whole files, transitively — every helper, constant and
# class the stop path reaches in them; only the NAMED definitions are excluded: the S26 identity / Gradle-home code, and
# inject_verify's alloc tail). `(file, excluded dotted names, {function: marker})`: an excluded name is cut (absent = nothing
# to cut); a function in the third map is kept up to its marker line, and a missing one or marker raises (the transfer refuses).
CANCEL_PATH = (
    ("benchmark/bench/token_turn_gate.py", (), {}),
    ("benchmark/bench/proc_guard.py", (), {}),
    ("benchmark/bench/arm_adapter.py", (), {}),
    ("benchmark/bench/opencode_v2_core.py", (), {}),
    ("benchmark/bench/host.py", (), {}),
    ("benchmark/bench/worker_receipts.py", (), {}),
    ("benchmark/bench/tg2_runner.py", (), {}),
    ("benchmark/run_tg2_probe.py", (), {}),
    ("benchmark/bench/arm_runner.py", ("_identity_inputs",), {}),
    ("benchmark/bench/arm_opencode.py", ("OpencodeArm.__init__", "OpencodeArm.build_env", "OpencodeArm.identity",
                                         "OpencodeArm.identity_data", "OpencodeArm.identity_summary", "TG2_GRADLE_HOME_SOURCE",
                                         "_tg2_gradle_home"), {}),
    ("benchmark/m62/inject_verify.py", ("never_executed",), {"verify_row": "\n    # alloc\n"}),
)
CANCEL_PATH_SHA256 = "97f6e1d596f2e3912429cc8e54cd80c30865a016b30249c1e9248fc82adca834"   # at c7c6993a (the reference's commit)
# C366 r1 P2: the reference record's stall rows per language (a transfer names exactly its language's)
TRANSFER_REFERENCE_STALL_ROWS = {
    "rust": "c97ec65c814f0c7163da98c3fb3e823582a576b92a75730067df564edcaa3cfe",
    "javascript": "e329e3849604558362532e70115bf7d107f316762b8e459010328595f696f589",
    "java": "88a7eae6c49347660ac3880d52d8c58a8e6b6739fa626430a66593297b9e5ea3",
    "cpp": "092adf471bebb40f022cacad7e756fe22f88c616789f7d16374017ef93f09265"}


def _named_nodes(tree):
    for node in tree.body:
        name = getattr(node, "name", None)
        if name is None and isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            name = next((t.id for t in targets if isinstance(t, ast.Name)), None)
        if name:
            yield name, node
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if getattr(member, "name", None):
                    yield f"{node.name}.{member.name}", member


def cancel_path_sha256(read) -> str:
    """sha256 over `CANCEL_PATH`; `read(rel)` returns a file's text (a worktree file, or `git show <rev>:<rel>`). Each file's AST
    (comments and positions ignored, docstrings kept) is hashed with its named exclusions removed and each truncated function
    cut before its marker line. A transfer stands only while this equals `CANCEL_PATH_SHA256` (C366: any other edit of these
    files needs a fresh in-run proof)."""
    h = hashlib.sha256()
    for rel, excluded, truncated in CANCEL_PATH:
        text = read(rel)
        tree = ast.parse(text)
        nodes = dict(_named_nodes(tree))
        drop = {id(nodes[n]) for n in excluded if n in nodes}        # absent at one commit = excluded there too
        for name, marker in truncated.items():
            node = nodes[name]                                       # KeyError: a missing function refuses
            seg = "".join(text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
            if marker not in seg:
                raise ValueError(f"{rel}: {name} has no marker {marker.strip()!r}")
            cut = node.lineno + seg[:seg.index(marker) + 1].count("\n")      # the marker's line number
            node.body = [st for st in node.body if st.lineno < cut]
        tree.body = [n for n in tree.body if id(n) not in drop]
        for n in tree.body:
            if isinstance(n, ast.ClassDef):
                n.body = [m for m in n.body if id(m) not in drop]
        h.update(f"{rel}\n".encode() + ast.dump(tree, include_attributes=False).encode() + b"\n")
    return h.hexdigest()


def _hex64(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _int(value, want=None):
    return type(value) is int and (want is None or value == want)


def worktree_cancel_path_sha256(worktree):
    """C366: a worktree's stop-path digest (`cancel_path_sha256`), or None when it cannot be computed."""
    try:
        return cancel_path_sha256(lambda rel: (Path(worktree) / rel).read_text())
    except (OSError, SyntaxError, KeyError, ValueError):
        return None


def transfer_ok(entry) -> bool:
    """A PASS_BY_TRANSFER entry is acceptable (C366 (a)): stall / loop only; the stop of the kind fired and its client kill
    verified with no request in flight; probe rc 0; the entry's own `row_sha256`; the reference is the sealed 11-17 record; the
    arm's stop path is source-identical to the reference commit's (`cancel_path_sha256`)."""
    ev = entry.get("transfer_evidence") if isinstance(entry, dict) else None
    want = TRANSFER_KINDS.get(entry.get("kind")) if isinstance(entry, dict) else None
    return (want is not None and isinstance(ev, dict) and ev.get("verify_verdict") == want[0]
            and ev.get("stop_reason") == want[1] and _int(ev.get("in_flight_at_kill"), 0) and ev.get("killed_verified") is True
            and _int(ev.get("probe_rc"), 0) and _hex64(ev.get("row_sha256")) and ev.get("row_sha256") == entry.get("row_sha256")
            and ev.get("reference_sha256") == TRANSFER_REFERENCE_SHA256
            and ev.get("reference_row_sha256") == TRANSFER_REFERENCE_STALL_ROWS.get(entry.get("language"))
            and ev.get("cancel_path_sha256") == CANCEL_PATH_SHA256)


def waived_ok(entry) -> bool:
    """A WAIVED entry is acceptable (C366 (b)): alloc only; the one kill a model-role process that is not the planted command,
    over the inject's per-process limit; no tool call carried the marker; probe rc 0; the entry's own `row_sha256`."""
    ev = entry.get("waived_evidence") if isinstance(entry, dict) else None
    return (isinstance(entry, dict) and entry.get("kind") == "alloc" and isinstance(ev, dict)
            and ev.get("verify_verdict") == WAIVED_VERIFY_VERDICT and ev.get("killed_role") == "model"
            and isinstance(ev.get("killed_argv0"), str) and ev.get("marker_in_argv") is False
            and ev.get("marker_in_tool_calls") is False
            and _int(ev.get("rss")) and _int(ev.get("per_process")) and ev["per_process"] > 0 and ev["rss"] > ev["per_process"]
            and _int(ev.get("probe_rc"), 0) and _hex64(ev.get("events_sha256"))
            and _hex64(ev.get("manifest_sha256")) and ev.get("manifest_sha256") == entry.get("evidence_sha256")
            and _hex64(ev.get("row_sha256")) and ev.get("row_sha256") == entry.get("row_sha256"))


def inject_accepted(entry) -> bool:
    """PASS; DECLINED (loop / alloc, S26 §4); PASS_BY_TRANSFER (stall / loop) or WAIVED (alloc), C366 — each with valid evidence."""
    v = entry.get("verdict") if isinstance(entry, dict) else None
    return (v == "PASS" or (v == "DECLINED" and declined_ok(entry)) or (v == "PASS_BY_TRANSFER" and transfer_ok(entry))
            or (v == "WAIVED" and waived_ok(entry)))


def waiver_problems(injects) -> list:
    """C366 (b): a WAIVED alloc stands only beside an alloc PASS of another language in the same record."""
    entries = list(injects)
    if any(e.get("verdict") == "WAIVED" for e in entries) and \
            not any(e.get("kind") == "alloc" and e.get("verdict") == "PASS" for e in entries):
        return ["alloc WAIVED but no alloc PASS in the record (C366)"]
    return []


class Refusal(Exception):
    """A refusal: printed as one stderr line `REFUSED: <reason>`, exit 2, nothing written."""


# ----------------------------------------------------------------------------------------------- paths and records
def stack_workdir(ops):
    import os
    wd = getattr(ops, "wd", None) or os.environ.get("STACK_WORKDIR")
    if not wd:
        raise Refusal("$STACK_WORKDIR is not set")
    return Path(wd)


def portable(path, wd, flag="path"):
    """`$STACK_WORKDIR/<rel>` for a path under the workdir; a record never carries an absolute path of this box."""
    try:
        rel = Path(path).resolve().relative_to(Path(wd).resolve())
    except ValueError:
        raise Refusal(f"{flag} {Path(path).name} does not lie under $STACK_WORKDIR (records are portable)") from None
    return "$STACK_WORKDIR/" + rel.as_posix() if rel.parts else "$STACK_WORKDIR"


def expand(value, wd):
    return co.resolve_portable(value, wd)


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def deadline_formula(langs, walls) -> float:
    """Spec 10.2: `T = 1.5 x sum_lang n_lang x w_lang + 1800 s`; `langs` = {lang: n}, `walls` = {lang: w}."""
    unknown = [lang for lang in langs if lang not in ("python", "go") or lang not in walls]
    if unknown:
        raise ValueError(f"no wall for language {unknown}")
    return DEADLINE_FACTOR * sum(n * float(walls[lang]) for lang, n in langs.items()) + DEADLINE_SLACK_S


KV_ARMS = ("n16", "x", "v")                                           # M76 B3 (lever kv): the KV arm labels (p426_plan.KV_ARMS)
KV_REHEARSAL_DIR = "m76/p426/rehearsal"


def engagement_role(arm):
    """The engagement role of an arm: `on` (drafter counters required) for ON and every M76 KV arm (both MTP ON), else `off`."""
    a = str(arm).lower()
    return "on" if a == "on" or a in KV_ARMS else a


def kv_pilot_leg(arm):
    return f"tg1-m76-{arm}-pilot"


def lever_of(record):
    return "kv" if isinstance(record, dict) and record.get("lever") == "kv" else "mtp"


def arms_of(record):
    """The record's two arms in role order (first, second): `off`, `on` — or, under kv, the pair `(reference, treatment)`."""
    if lever_of(record) == "kv":
        arms = record.get("arms")
        if not (isinstance(arms, list) and len(arms) == 2 and all(a in KV_ARMS for a in arms)):
            raise Refusal(f"the KV record's arms {arms!r} are not a (reference, treatment) pair")
        return tuple(arms)
    return ("off", "on")


def r1_difference_problems(entries, lever="mtp") -> list:
    """Spec 6.5 / 16.7: every entry of `r1_env_difference` is on the closed allowed list: the three MTP flag pairs of the worker argv,
    the drafter snapshot, or a key of the closed volatile list. Anything else is named. M76 (lever kv): the KV list (the worker
    argv, volatile keys; never the drafter)."""
    if lever == "kv":
        return [f"r1_env_difference: {p}" for p in pr.kv_difference_problems(entries)]
    problems = []
    for e in entries:
        process, field = e.get("process"), str(e.get("field"))
        key = field[len("env."):] if field.startswith("env.") else None
        ok = ((process == "worker" and field == "argv.worker") or field == "snapshots.drafter"
              or (key is not None and pr.is_volatile(key)))
        if not ok:
            problems.append(f"r1_env_difference: {process} {field} is outside spec 6.5's allowed list")
    return problems


# ----------------------------------------------------------------------------------------------- leg roots
def read_json(path, what):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise Refusal(f"{what} is missing, unreadable or not JSON") from None


def read_leg(root) -> dict:
    """`<leg root>/leg.json` (the sequencer's sealed leg record), self-hash verified."""
    path = Path(root) / "leg.json"
    doc = read_json(path, f"{Path(root).name}/leg.json")
    if not ph.sealed_ok(doc):
        raise Refusal(f"{Path(root).name}/leg.json: its sha256 does not verify (changed after sealing)")
    return doc


def read_chain(root) -> dict:
    return read_json(Path(root) / "chain.json", f"{Path(root).name}/chain.json")


def leg_items_problems(root, arm) -> list:
    """The leg's realized ledger against its item records (spec 4.5, 16.1): every row has a ready record and a reconciled item
    record, every DNF its `.dnf.json`; the ON counters are present and the OFF ones absent (`engagement_problems`)."""
    root = Path(root)
    try:
        chain = read_chain(root)
    except Refusal as exc:
        return [str(exc)]
    ledger = chain.get("p426_ledger") or []
    if not ledger:
        return ["the realized ledger is empty"]
    problems, judged = [], 0
    for e in ledger:
        name = cr.slot_file(e["slot"])
        dnf = e.get("kind") == "dnf"
        path, what = (root / "items" / f"{name}.dnf.json", "DNF item record") if dnf else (root / "items" / f"{name}.json", "item record")
        ready = None                                    # every ledger entry, a DNF included, has its ready record (spec 4.2)
        try:
            ready = json.loads((root / "items" / f"{name}.ready.json").read_text())
        except (OSError, ValueError):
            problems.append(f"{e['slot']}: ready record is missing or unreadable")
        else:
            if not ph.sealed_ok(ready):
                problems.append(f"{e['slot']}: ready record's sha256 does not verify")
                ready = None
        try:
            rec = json.loads(path.read_text())
        except (OSError, ValueError):
            problems.append(f"{e['slot']}: {what} is missing or unreadable")
            continue
        if not ph.sealed_ok(rec):
            problems.append(f"{e['slot']}: {what}'s sha256 does not verify")
        elif ready is not None and rec.get("ready_sha256") != ready["sha256"]:
            problems.append(f"{e['slot']}: {what}'s ready_sha256 is not its ready record's sha256")
        elif rec.get("verdict") != "reconciled":
            problems.append(f"{e['slot']}: {what} is not reconciled (verdict {rec.get('verdict')!r})")
        else:                                           # a DNF item's completed requests are judged as well (it has no per-item floor)
            requests = rec.get("requests") or []
            role = engagement_role(arm) if str(arm).lower() in KV_ARMS else arm
            problems += [f"{e['slot']}: {p}" for p in prc.engagement_problems(requests, role, item=not dnf)]
            judged += sum(1 for r in requests if not r.get("error") and int(r.get("generated_tokens") or 0) >= 2)
    if engagement_role(arm) == "on" and not judged and not problems:
        problems.append("unengaged: no request of the leg is long enough (>= 2 generated tokens) to be judged")
    return problems


def pilot_walls(root) -> list:
    """Per-row `wall_s` of the rows files of the invocations `chain.json` `progress.invocations` names (spec 16.6)."""
    root, walls = Path(root), []
    for inv in (read_chain(root).get("progress") or {}).get("invocations") or []:
        if inv.get("status") not in COUNTED_STATUSES:
            continue
        path = Path(inv["file"])
        path = path if path.is_absolute() else root / path
        try:
            lines = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        except (OSError, ValueError):
            raise Refusal(f"{root.name}: the rows file {path.name} is unreadable") from None
        walls += [float(r["wall_s"]) for r in lines if isinstance(r, dict) and r.get("wall_s") is not None]
    return walls


def read_receipt(root):
    doc = read_json(Path(root) / "receipt.json", f"{Path(root).name}/receipt.json")
    if not ph.sealed_ok(doc):
        raise Refusal(f"{Path(root).name}/receipt.json: its sha256 does not verify")
    return doc


def receipt_differences(off_root, on_root) -> list:
    """The R1 pair's observed difference as dossier entries (spec 16.7), from the two legs' receipts."""
    return pr.observed_differences(read_receipt(off_root), read_receipt(on_root))


def valid_leg_problems(root, arm) -> list:
    """What a rehearsal / pilot leg must show: a verified VALID leg record, its receipt of the right arm, every item reconciled."""
    try:
        leg = read_leg(root)
        receipt = read_receipt(root)
    except Refusal as exc:
        return [str(exc)]
    problems = []
    if leg.get("state") != "VALID":
        problems.append(f"leg state is {leg.get('state')!r}, not VALID ({leg.get('reason') or 'no reason recorded'})")
    got = pr.kv_arm_of(receipt) if arm in KV_ARMS and pr.arm_of(receipt) == "on" else pr.arm_of(receipt)
    if got != arm:
        problems.append(f"the receipt's worker argv says {got}, not {arm}")
    return problems + leg_items_problems(root, arm)


REHEARSAL_LEGS = (("R1 off", "tg1-p426-rehearsal-off", None), ("R1 on", "tg1-p426-rehearsal-on", None),
                  ("R2", "tg1-p426-rehearsal-mismatch", "reconcile-mismatch"), ("R3", "tg1-p426-rehearsal-kill", "stall-kill"))


def kv_rehearsal_legs(ref, test):
    """M76 B3: the rehearsal legs of a KV pair (R1 reference / treatment, R2 the mismatch, R3 the kill)."""
    return ((f"R1 {ref}", f"tg1-m76-rehearsal-{ref}", None), (f"R1 {test}", f"tg1-m76-rehearsal-{test}", None),
            ("R2", "tg1-m76-rehearsal-mismatch", "reconcile-mismatch"), ("R3", "tg1-m76-rehearsal-kill", "stall-kill"))


def binding_problems(roots, manifest_path, manifest_sha, wd, legs=REHEARSAL_LEGS) -> list:
    """Each of R1-off / R1-on / R2 / R3 is a leg run under THIS rehearsal manifest (its `chain.json` names it as the frozen record,
    by path and sha256), with the expected leg name and, for R2 / R3, the expected `--inject` (R1: none). The manifest's own
    commits are not compared with the v8 arms (spec 1: rehearsals run on the B2 / throwaway commits)."""
    problems = []
    for (label, leg_name, inject), root in zip(legs, roots):
        try:
            leg, chain = read_leg(root), read_chain(root)
        except Refusal:
            continue                                            # named by the leg's own checks
        if leg.get("leg") != leg_name:
            problems.append(f"{label}: the leg is {leg.get('leg')!r}, not {leg_name}")
        ref = chain.get("frozen_record")
        if not isinstance(ref, dict):
            problems.append(f"{label}: chain.json records no frozen_record (not shown to run under this rehearsal manifest)")
        else:
            try:
                same_path = Path(expand(ref.get("path"), wd)).resolve() == Path(manifest_path).resolve()
            except (TypeError, ValueError):
                same_path = False
            if not same_path:
                problems.append(f"{label}: chain.json frozen_record names another file than the rehearsal manifest")
            if ref.get("sha256") != manifest_sha:
                problems.append(f"{label}: chain.json frozen_record sha256 is not the rehearsal manifest's")
        if chain.get("inject") != inject:
            problems.append(f"{label}: chain.json inject is {chain.get('inject')!r}, the rehearsal needs {inject!r}")
    return problems


def _slot_lang(slot):
    parts = str(slot).split("|")
    return parts[-2] if len(parts) >= 2 else None


def r1_shape_problems(root) -> list:
    """P589: an R1 leg holds the rehearsal's `1 + 2 + 2` items: three Python ledger entries (one pilot, two full) and two Go."""
    try:
        ledger = read_chain(root).get("p426_ledger") or []
    except Refusal as exc:
        return [str(exc)]
    got = {}
    for e in ledger:
        lang = _slot_lang(e.get("slot"))
        got[lang] = got.get(lang, 0) + 1
    if got != REHEARSAL_R1_ITEMS:
        return [f"the leg holds {dict(sorted(got.items()))} items, the rehearsal shape is 1 + 2 + 2 ({REHEARSAL_R1_ITEMS})"]
    return []


def r2_slot_problems(invalid, want="go") -> list:
    """P589: R2's invalidated slot is a Go slot (the injection perturbs the first Go item, through the tombstone path); M76 B4b-1
    tg2: a Rust slot (the first Rust item)."""
    lang = _slot_lang(invalid[0].get("slot")) if invalid else None
    name = {"go": "Go", "rust": "Rust"}.get(want, want)
    return [] if lang == want else [f"R2: the invalidated slot is a {lang!r} slot, it must be a {name} slot (the first {name} item)"]


def tg2_rehearsal_legs(ref, test):
    """M76 B4b-1: the tg2 rehearsal legs of a KV pair — R2 (the reconciliation mismatch) on the treatment, R3 (the probe kill) on
    the reference; no R1 (the pilot pair takes R1's positive-pair role)."""
    return (("R2", f"tg2-m76-{test}-rehearsal-r2", "reconcile-mismatch"), ("R3", f"tg2-m76-{ref}-rehearsal-r3", "stall-kill"))


def tg2_rehearsal_problems(r2, r3, *, manifest_path, manifest_sha, wd, arms):
    """R2 INVALID for the injected mismatch on a Rust slot, R3 VALID with its kill scored (no DNF, a kill case recorded); both bound
    to this rehearsal manifest with their leg names and injections."""
    problems = binding_problems((r2, r3), manifest_path, manifest_sha, wd, legs=tg2_rehearsal_legs(*arms))
    try:
        leg = read_leg(r2)
        invalid = read_chain(r2).get("p426_invalid") or []
        if leg.get("state") != "INVALID":
            problems.append(f"R2: leg state is {leg.get('state')!r}, it must be INVALID for the injected mismatch")
        elif len(invalid) != 1 or invalid[0].get("reason") != R2_REASON or leg.get("reason") != R2_REASON:
            problems.append(f"R2: INVALID, but not for the injected reconciliation mismatch (reason {leg.get('reason')!r})")
        else:
            problems += r2_slot_problems(invalid, "rust")
    except Refusal as exc:
        problems.append(f"R2: {exc}")
    try:
        leg = read_leg(r3)
        if leg.get("state") != "VALID":
            problems.append(f"R3: leg state is {leg.get('state')!r}, it must be VALID with the kill scored")
        elif read_chain(r3).get("p426_dnf"):
            problems.append("R3: the kill was recorded as a DNF, it must be a scored strict fail")
        else:
            cases = [json.loads(p.read_text()).get("case") for p in sorted((Path(r3) / "items").glob("*.json"))
                     if not p.name.endswith((".ready.json", ".dnf.json"))]
            if not any(c in KILL_CASES for c in cases):
                problems.append("R3: no item record carries a failed-line kill case")
    except (Refusal, ValueError) as exc:
        problems.append(f"R3: {exc}")
    return problems


def rehearsal_problems(r1_off, r1_on, r2, r3, ops, *, manifest_path, manifest_sha, wd, arms=("off", "on")):
    """(problems, r1 differences): R1 VALID both arms and its pair gate passed; R2 INVALID for the injected reason; R3 VALID with
    a real kill classified; every leg bound to this manifest (`binding_problems`). R2 / R3 are excluded from the pair gate (spec 1).
    M76 (lever kv): `arms` = the KV pair (reference, treatment), its rehearsal leg names and the KV pair gate."""
    lever = "kv" if tuple(arms) != ("off", "on") else "mtp"
    legs = kv_rehearsal_legs(*arms) if lever == "kv" else REHEARSAL_LEGS
    problems = binding_problems((r1_off, r1_on, r2, r3), manifest_path, manifest_sha, wd, legs=legs)
    problems += [f"R1 {arm}: {p}" for arm, root in zip(arms, (r1_off, r1_on)) for p in valid_leg_problems(root, arm)]
    problems += [f"R1 {arm}: {p}" for arm, root in zip(arms, (r1_off, r1_on)) for p in r1_shape_problems(root)]
    diffs = []
    if not problems:
        pair = pr.gate_problems(read_receipt(r1_off), read_receipt(r1_on), lever=lever)
        problems += [f"R1 pair gate: {p}" for p in pair]
        try:
            diffs = list((getattr(ops, "r1_differences", None) or receipt_differences)(r1_off, r1_on)) if lever == "mtp" else \
                pr.kv_observed_differences(read_receipt(r1_off), read_receipt(r1_on))
        except Refusal as exc:
            problems.append(f"R1: {exc}")
        problems += [f"R1 {p}" for p in r1_difference_problems(diffs, lever=lever)]
    try:
        leg = read_leg(r2)
        invalid = read_chain(r2).get("p426_invalid") or []
        if leg.get("state") != "INVALID":
            problems.append(f"R2: leg state is {leg.get('state')!r}, it must be INVALID for the injected mismatch")
        elif len(invalid) != 1 or invalid[0].get("reason") != R2_REASON or leg.get("reason") != R2_REASON:
            problems.append(f"R2: INVALID, but not for the injected reconciliation mismatch (reason {leg.get('reason')!r})")
        else:
            problems += r2_slot_problems(invalid)
    except Refusal as exc:
        problems.append(f"R2: {exc}")
    try:
        leg = read_leg(r3)
        if leg.get("state") != "VALID":
            problems.append(f"R3: leg state is {leg.get('state')!r}, it must be VALID with the kill scored")
        elif read_chain(r3).get("p426_dnf"):
            problems.append("R3: the kill was recorded as a DNF, it must be a scored strict fail")
        else:
            cases = [json.loads(p.read_text()).get("case") for p in sorted((Path(r3) / "items").glob("*.json"))
                     if not p.name.endswith((".ready.json", ".dnf.json"))]
            if not any(c in KILL_CASES for c in cases):
                problems.append("R3: no item record carries a failed-line kill case")
    except (Refusal, ValueError) as exc:
        problems.append(f"R3: {exc}")
    return problems, diffs


# ----------------------------------------------------------------------------------------------- worktrees
def arm_problems(ops, off, on, arms=("off", "on")) -> list:
    """The two arm worktrees: clean, two commits, identical gitlinks, the ON commit = OFF + exactly the restore diff. M76 (lever
    kv): `arms` names the KV pair (the KV delta is a `checks` precondition)."""
    st, problems = {}, []
    for arm, path in zip(arms, (off, on)):
        st[arm] = ops.worktree_state(path)
        if st[arm].get("clean") is not True:
            problems.append(f"the {arm} worktree is not clean")
    if st[arms[0]].get("head") == st[arms[1]].get("head"):
        problems.append(f"the {arms[0].upper()} and {arms[1].upper()} worktrees are at the same commit (the arms are two commits)")
    for key, path in GITLINKS:
        a, b = st[arms[0]].get("gitlinks", {}).get(path), st[arms[1]].get("gitlinks", {}).get(path)
        if not a or a != b:
            problems.append(f"gitlink {path} differs between the arms ({str(a)[:12]} vs {str(b)[:12]})")
    return problems


# ----------------------------------------------------------------------------------------------- live re-verification
def live_problems(base, ops, wd) -> list:
    """The sequencer's and every leg's re-verification of v8 against the live state: each arm's HEAD equals the record's commit,
    the tree is clean, the gitlinks are the record's and the probe identity is unchanged."""
    problems = []
    for arm in arms_of(base):                                   # M76 (lever kv): the record's KV pair
        path = expand(base[f"{arm}_worktree"], wd)
        st = ops.worktree_state(path)
        if st.get("head") != base.get(f"{arm}_commit"):
            problems.append(f"the {arm} worktree HEAD {str(st.get('head'))[:12]} != the record's {str(base.get(f'{arm}_commit'))[:12]}")
        if st.get("clean") is not True:
            problems.append(f"the {arm} worktree is not clean")
        for key, rel in GITLINKS:
            if st.get("gitlinks", {}).get(rel) != base["gitlinks"][key]:
                problems.append(f"the {arm} worktree gitlink {rel} {str(st.get('gitlinks', {}).get(rel))[:12]} != the record's "
                                f"{base['gitlinks'][key][:12]}")
        ident = ops.identity(path)
        problems += [f"the {arm} probe identity {k} differs from the record's" for k in IDENTITY_KEYS if ident.get(k) != base.get(k)]
    return problems


# ----------------------------------------------------------------------------------------------- preconditions
def corpus_entry_points(corpus="tg1"):
    """(entry points, `--help` entries) of a corpus's legs: tg1's, or (M76 B4b-1) tg2's chain and probe besides them."""
    if corpus != "tg2":
        return ENTRY_POINTS, HELP_ENTRIES
    tg2 = ("/".join(TG2_CHAIN_ENTRY), TG2_PROBE_ENTRY)
    return ENTRY_POINTS + tg2, tg2


def entry_point_problems(worktree, corpus="tg1") -> list:
    points = corpus_entry_points(corpus)[0]
    return [f"entry point <WT>/{rel} is missing" for rel in points if not (Path(worktree) / rel).exists()]


def venv_problems(worktree, build) -> list:
    want = (p426_plan.EXPECTED_BUILDS.get(build) or {}).get("mlx")
    problems = []
    for venv in p426_plan.VENVS:
        have = p426_plan.venv_versions(worktree, venv)
        for pkg in ("mlx", "mlx-metal"):
            if want and have.get(pkg) != want:
                problems.append(f"<WT>/{venv}: {pkg} {have.get(pkg)!r} is not the lock's {want}")
    return problems


def help_problems(worktree, corpus="tg1") -> list:
    """K3: the chain and probe entry points answer `--help` from the worktree's own venv."""
    problems = []
    for rel in corpus_entry_points(corpus)[1]:
        run = subprocess.run([str(Path(worktree) / ".venv-bench/bin/python"), str(Path(worktree) / rel), "--help"], cwd=str(worktree),
                             capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        if run.returncode != 0:
            problems.append(f"<WT>/{rel} --help exits {run.returncode}")
    return problems


def production_tree_problems(worktree, ref, gitlink) -> list:
    """Spec 10.1 / 16.8: the fork tree at the gitlink equals the production ref's tree under `mlx_vlm/` excluding `mlx_vlm/tests/`
    (`git diff --quiet <ref> <gitlink> -- mlx_vlm ':!mlx_vlm/tests'` in the worktree's `src/mlx-vlm`)."""
    fork = Path(worktree) / "src" / "mlx-vlm"
    try:
        run = subprocess.run(["git", "-C", str(fork), "diff", "--quiet", ref, gitlink, "--", "mlx_vlm", ":!mlx_vlm/tests"],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"production tree check could not run ({type(exc).__name__})"]
    if run.returncode == 0:
        return []
    if run.returncode == 1:
        return [f"production tree: {str(gitlink)[:12]} differs from the production ref {str(ref)[:12]} under mlx_vlm/ (tests excluded)"]
    return [f"production tree check failed (git exit {run.returncode}): the ref {str(ref)[:12]} or the gitlink is not in {fork.name}"]


def gate_policy_digest(sha):
    """The gate policy digest `bench.local_gate` requires of a stack receipt for `sha` today (the pre-push hook's own)."""
    from . import local_gate as lg
    return lg.digest_for("stack", sha, lg._stack_repo(), lg._baselines())


def suite_receipt_problems(*, receipt, receipt_sha256, off_head, wd, digest_for=None) -> list:
    """P609: the stated stack suite receipt is a PASS gate receipt (`bench.local_gate`) for exactly the OFF arm's commit under the
    current gate policy, and its bytes hash to the stated `stack_suite_receipt_sha256`; [] when it is, else every problem."""
    if not isinstance(receipt, str) or not receipt:
        return ["no stack_suite_receipt path in the build inputs"]
    try:
        raw = expand(receipt, wd).read_bytes()
    except (OSError, ValueError):                       # ValueError: e.g. an embedded NUL (review r1 P4)
        return [f"{Path(receipt).name} cannot be read"]
    problems = []
    if hashlib.sha256(raw).hexdigest() != receipt_sha256:
        problems.append(f"{Path(receipt).name}: its sha256 is not the stated stack_suite_receipt_sha256")
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        return problems + [f"{Path(receipt).name} is not a gate receipt"]
    if doc.get("repo") != "stack":
        problems.append(f"the receipt is for {doc.get('repo')!r}, not the stack")
    if doc.get("sha") != off_head:
        problems.append(f"the receipt is for {str(doc.get('sha'))[:12]}, not the OFF arm's commit {str(off_head)[:12]}")
    if doc.get("verdict") != "PASS":
        problems.append(f"the receipt's verdict is {doc.get('verdict')!r}, not PASS")
    if not problems:
        try:
            current = (digest_for or gate_policy_digest)(off_head)
        except Exception as exc:                        # any failure computing the digest refuses (as the pre-push hook)
            return [f"the gate policy digest cannot be computed ({type(exc).__name__})"]
        if doc.get("policy_digest") != current:
            problems.append("the receipt was made under another gate policy (policy_digest is not the current one)")
    return problems


def default_checks(kind, *, off_worktree, on_worktree, build="s2", production_ref=None, gitlinks=None, off_head=None,
                   suite_receipt=None, suite_receipt_sha256=None, wd=None, arms=("off", "on"), corpus="tg1") -> list:
    """The real preconditions (spec 16.8: every one goes through `checks`): the restore diff between the two arms, both
    worktrees' entry points, and for v8 the venvs against the lock, K3 (`--help`), the production tree at the gitlink and (P609)
    a PASS stack suite receipt for the OFF commit. M76 (lever kv): `arms` = the KV pair; the KV delta between the arm commits in
    place of the restore diff; the suite receipt is the reference arm's."""
    if tuple(arms) != ("off", "on"):
        problems = [f"kv delta: {p}" for p in p426_plan.kv_pair_commit_problems(off_worktree, on_worktree, arms,
                                                                               p426_plan.p426_ids.ENTRY)]
    else:
        problems = [f"restore diff: {p}" for p in p426_plan.restore_diff_problems(off_worktree, on_worktree,
                                                                                 p426_plan.p426_ids.ENTRY)]
    extra = (corpus,) if corpus != "tg1" else ()                # tg1's calls unchanged (tests stand in for these helpers)
    for arm, wt in zip(arms, (off_worktree, on_worktree)):
        found = entry_point_problems(wt, *extra)
        problems += [f"{arm}: {p}" for p in found]
        if kind != "v8" or found:
            continue
        problems += [f"{arm}: {p}" for p in venv_problems(wt, build)]
        problems += [f"{arm}: {p}" for p in help_problems(wt, *extra)]
        problems += [f"{arm}: {p}" for p in production_tree_problems(wt, production_ref, (gitlinks or {}).get("mlx_vlm"))]
    if kind == "v8":
        problems += [f"stack suite receipt: {p}" for p in suite_receipt_problems(
            receipt=suite_receipt, receipt_sha256=suite_receipt_sha256, off_head=off_head, wd=wd)]
    return problems


class BoxOps:
    """The real `ops`: git, the probe's `--print-identity`, and the two inputs only the operator knows (JSON files)."""

    def __init__(self, workdir, build_inputs=None, historical_walls=None, corpus="tg1"):
        self.wd, self._inputs, self._walls = Path(workdir), build_inputs, historical_walls
        self.probe_entry = TG2_PROBE_ENTRY if corpus == "tg2" else "benchmark/run_tg1_probe.py"    # whose identity a record names

    @staticmethod
    def _git(root, *args):
        run = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
        if run.returncode != 0:
            raise Refusal(f"git {args[0]} failed in {Path(root).name}")
        return run.stdout

    def worktree_state(self, path):
        gitlinks = {}
        for line in self._git(path, "ls-tree", "HEAD", "src/mlx-vlm", "src/mlx-serve").splitlines():
            meta, rel = line.split("\t", 1)
            gitlinks[rel] = meta.split()[2]
        return dict(head=self._git(path, "rev-parse", "HEAD").strip(), clean=self._git(path, "status", "--porcelain").strip() == "",
                    gitlinks=gitlinks)

    def identity(self, path):
        entry = getattr(self, "probe_entry", "benchmark/run_tg1_probe.py")
        run = subprocess.run([str(Path(path) / ".venv-bench/bin/python"), str(Path(path) / entry),
                              "--print-identity"], cwd=str(path), capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        lines = [x for x in run.stdout.splitlines() if x.strip()]
        try:
            doc = json.loads(lines[-1]) if run.returncode == 0 and lines else None
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            raise Refusal(f"{Path(path).name}: the probe's --print-identity gave no document")
        return {k: doc.get(k) for k in IDENTITY_KEYS}

    def _file(self, path, flag):
        if not path:
            raise Refusal(f"{flag} <json> is required (the box's ops read it)")
        return read_json(path, flag)

    def build_inputs(self):
        return self._file(self._inputs, "--build-inputs")

    def historical_walls(self):
        return self._file(self._walls, "--historical-walls")


# ----------------------------------------------------------------------------------------------- the commands
def write_record(path, doc):
    try:
        return ph.write_exclusive(path, dict(doc, created=co.utc_stamp()))
    except FileExistsError:
        raise Refusal(f"--out {Path(path).name} exists (records are exclusive-created, never overwritten)") from None


def run_checks(checks, kind, **inputs):
    failed = list(checks(kind, **inputs))
    if failed:
        raise Refusal("precondition failed: " + "; ".join(failed))


def need(ops, *seams):
    """Spec 16.8: a missing `ops` seam is a refusal naming it, never a traceback."""
    missing = [s for s in seams if not callable(getattr(ops, s, None))]
    if missing:
        raise Refusal(f"the ops seam {', '.join(missing)} is missing")


def need_walls(walls, *keys):
    missing = [k for k in keys if not isinstance(walls.get(k), (int, float)) or isinstance(walls.get(k), bool)]
    if missing:
        raise Refusal(f"ops.historical_walls() lacks {', '.join(missing)}")
    return {k: float(walls[k]) for k in keys}


def request_elapsed_max(root):
    """The largest single-request `elapsed_s` over the leg's item records (spec 16.8); None when no record carries one."""
    values = []
    for p in sorted((Path(root) / "items").glob("*.json")):
        if p.name.endswith(".ready.json"):
            continue
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        values += [float(r["elapsed_s"]) for r in doc.get("requests") or []
                   if isinstance(r, dict) and isinstance(r.get("elapsed_s"), (int, float)) and not isinstance(r.get("elapsed_s"), bool)]
    return max(values) if values else None


def _kv_fields(a):
    """M76 (lever kv): (arms, record fields) — the pair in role order and the `lever` / `arms` fields of the record."""
    arms = tuple(getattr(a, "arms", None) or ("off", "on"))
    return arms, (dict(lever="kv", arms=list(arms)) if arms != ("off", "on") else {})


def cmd_rehearsal(a, ops, checks, wd):
    need(ops, "worktree_state", "identity")
    arms, kv = _kv_fields(a)
    tg2 = getattr(a, "corpus", "tg1") == "tg2"
    if tg2:
        check_tg2_pair(arms)                                    # change review L6
    off, on = Path(a.off_worktree), Path(a.on_worktree)
    problems = arm_problems(ops, off, on, arms)
    out_root = Path(a.out_root).resolve()
    reh = TG2_REHEARSAL_DIR if tg2 else KV_REHEARSAL_DIR if kv else REHEARSAL_DIR
    if (wd / reh).resolve() not in out_root.parents:
        problems.append(f"--out-root must lie under $STACK_WORKDIR/{reh}/")
    if not datefreeze.valid(a.frozen_prompt_date):
        problems.append("--frozen-prompt-date must be 'Www Mmm DD YYYY' (zero-padded day)")
    ident, ident_on = ops.identity(off), ops.identity(on)
    for key in IDENTITY_KEYS:
        if not re.fullmatch(r"[0-9a-f]{64}", str(ident.get(key))) or ident.get(key) != ident_on.get(key):
            problems.append(f"{key} differs between the arms (or is missing)")
    if problems:
        raise Refusal("; ".join(problems))
    run_checks(checks, "rehearsal", off_worktree=off, on_worktree=on, **({"arms": arms} if kv else {}),
               **({"corpus": "tg2"} if tg2 else {}))
    st = {arm: ops.worktree_state(p) for arm, p in zip(arms, (off, on))}
    if kv:  # M76: the record names the arms by their KV label (B4b-1: and the tg2 corpus)
        return write_record(a.out, dict(kind=KIND_REHEARSAL, **kv, **({"corpus": "tg2"} if tg2 else {}),
                                        **{f"{arm}_commit": st[arm]["head"] for arm in arms},
                                        **{f"{arm}_worktree": portable(p, wd, f"--arm-worktree {arm}") for arm, p in zip(arms, (off, on))},
                                        out_root=portable(out_root, wd, "--out-root"), rehearsal=True,
                                        frozen_prompt_date=a.frozen_prompt_date, **{k: ident[k] for k in IDENTITY_KEYS}))
    return write_record(a.out, dict(kind=KIND_REHEARSAL, off_commit=st["off"]["head"], on_commit=st["on"]["head"],
                                    off_worktree=portable(off, wd, "--off-worktree"), on_worktree=portable(on, wd, "--on-worktree"),
                                    out_root=portable(out_root, wd, "--out-root"), rehearsal=True,
                                    frozen_prompt_date=a.frozen_prompt_date, **{k: ident[k] for k in IDENTITY_KEYS}))


def build_problems(inputs, gitlinks) -> list:
    problems = []
    build = inputs.get("build")
    expected = p426_plan.EXPECTED_BUILDS.get(build)
    if expected is None:
        return [f"build {build!r} has no expected build in code"]
    for key, _path in GITLINKS:
        if gitlinks[key] != expected[key]:
            problems.append(f"gitlink {key} {gitlinks[key][:12]} is not build {build}'s {expected[key][:12]}")
    if inputs.get("production_ref") != expected["production_ref"]:
        problems.append(f"production_ref {str(inputs.get('production_ref'))[:12]} is not build {build}'s {expected['production_ref'][:12]}")
    if not datefreeze.valid(inputs.get("frozen_prompt_date")):
        problems.append("frozen_prompt_date is required ('Www Mmm DD YYYY', never defaulted)")
    if not (isinstance(inputs.get("grader_image_id"), str) and inputs["grader_image_id"]):
        problems.append("grader_image_id is missing")
    if not re.fullmatch(r"[0-9a-f]{64}", str(inputs.get("stack_suite_receipt_sha256"))):
        problems.append("stack_suite_receipt_sha256 is missing (no stack suite receipt)")
    return problems


def positives_problems(doc, *, arm, commit, identity, frozen_prompt_date, image_id, cancel_path_sha256=None) -> list:
    """The sealed tg2 positives record (E6) against the live inputs of v8: its self-hash, kind and PASS verdict, every identity
    field (probe / generation / scaffold, the reference arm's commit, the universe / draw / image, the frozen date), and the
    coverage: each (language, inject kind) once with a PASS verdict (S26 §4: or, for loop / alloc only, DECLINED with valid
    `declined_evidence`), each (language, stub / reference) once with the expected grade. A sealed record of another identity
    refuses."""
    from . import schedules
    if not isinstance(doc, dict) or not ph.sealed_ok(doc):
        return ["its sha256 does not verify (missing, or changed after sealing)"]
    problems = []
    if doc.get("kind") != KIND_POSITIVES:
        problems.append(f"kind {doc.get('kind')!r} is not {KIND_POSITIVES}")
    if doc.get("verdict") != "PASS" or doc.get("problems"):
        problems.append(f"verdict {doc.get('verdict')!r}: " + "; ".join(doc.get("problems") or [])[:600])
    if doc.get("arm") != arm or doc.get(f"{arm}_commit") != commit:
        problems.append(f"it was recorded on another commit than the {arm} worktree's {str(commit)[:12]}")
    problems += [f"{k} differs from the probe's live identity" for k in IDENTITY_KEYS if doc.get(k) != (identity or {}).get(k)]
    for key, want in (("scaffold", "opencode-v2-web-tg2"), ("draw_sha256", schedules.TG2_DRAW_SHA256),
                      ("universe_sha256", schedules.TG2_UNIVERSE_SHA256), ("image_id", image_id),
                      ("frozen_prompt_date", frozen_prompt_date)):
        if doc.get(key) != want:
            problems.append(f"{key} {str(doc.get(key))[:40]!r} is not the live {str(want)[:40]!r}")
    injects = {(p.get("language"), p.get("kind")): p for p in doc.get("injects") or []}
    if len(injects) != len(doc.get("injects") or []) or set(injects) != {(lang, k) for lang in TG2_LANGS for k in POSITIVE_KINDS}:
        problems.append("the injected positives are not stall / loop / alloc once per tg2 language")
    # S26 §4 (v8): DECLINED for loop / alloc only, with valid `declined_evidence`; C366: PASS_BY_TRANSFER (stall / loop) and
    # WAIVED (alloc, beside an alloc PASS) with valid evidence
    problems += [f"{lang} {k}: verdict {p.get('verdict')!r}" for (lang, k), p in sorted(injects.items()) if not inject_accepted(p)]
    problems += waiver_problems(injects.values())
    if any(p.get("verdict") == "PASS_BY_TRANSFER" for p in injects.values()) and cancel_path_sha256 != CANCEL_PATH_SHA256:
        problems.append("a PASS_BY_TRANSFER entry, but the reference arm's live stop path is not the reference commit's (C366)")
    grades = {(g.get("language"), g.get("variant")): g for g in doc.get("grades") or []}
    if len(grades) != len(doc.get("grades") or []) or set(grades) != {(lang, v) for lang in TG2_LANGS for v in POSITIVE_VARIANTS}:
        problems.append("the grader positives are not one stub and one reference per tg2 language")
    problems += [f"{lang} {v}: graded {'PASS' if g.get('passed') else 'FAIL'}" for (lang, v), g in sorted(grades.items())
                 if g.get("passed") is not (v == "reference")]
    return problems


def cmd_v8_tg2(a, ops, checks, wd):
    """M76 B4b-1 (§3 "v8 base"): the tg2 v8 base of a KV pair — no R1 and no historical walls (the pilot pair takes R1's role);
    R2 / R3 of the tg2 rehearsal manifest; the sealed positives record compared field by field with the live inputs."""
    from . import chain_core
    from . import schedules
    from . import tg2_grade
    need(ops, "worktree_state", "identity", "build_inputs")
    arms, kv = _kv_fields(a)
    if not kv:
        raise Refusal("--corpus tg2 is a lever kv pair (--lever kv --pair <ref>,<test>)")
    check_tg2_pair(arms)
    if getattr(a, "r1_off", None) or getattr(a, "r1_on", None):     # change review L5: spec §3 "no R1"
        raise Refusal("--r1-off / --r1-on: the tg2 v8 base has no R1 (the pilot pair takes R1's role)")
    missing = [f for f, v in (("--r2", a.r2), ("--r3", a.r3), ("--positives", getattr(a, "positives", None))) if not v]
    if missing:
        raise Refusal("the following arguments are required: " + ", ".join(missing))
    ref, test = arms
    off, on = Path(a.off_worktree), Path(a.on_worktree)
    try:
        manifest = p426_record.load(a.rehearsal_manifest, mode="chain", rehearsal=True)["doc"]
    except p426_record.RecordError as exc:
        raise Refusal(f"--rehearsal-manifest {exc}") from None
    if lever_of(manifest) != "kv" or tuple(manifest.get("arms") or ()) != arms or manifest.get("corpus") != "tg2":
        raise Refusal("--rehearsal-manifest was not written for this KV pair's tg2 legs (--corpus tg2)")
    problems = arm_problems(ops, off, on, arms)
    st = {arm: ops.worktree_state(p) for arm, p in zip(arms, (off, on))}
    gitlinks = {key: st[ref].get("gitlinks", {}).get(path) or "" for key, path in GITLINKS}
    inputs = ops.build_inputs()
    problems += build_problems(inputs, gitlinks)
    if inputs.get("build") not in p426_plan.KV_BUILDS:
        problems.append(f"build {inputs.get('build')!r} is not a KV build {p426_plan.KV_BUILDS}")
    idents = {arm: ops.identity(p) for arm, p in zip(arms, (off, on))}
    for key in IDENTITY_KEYS:
        if not re.fullmatch(r"[0-9a-f]{64}", str(idents[ref].get(key))) or idents[ref].get(key) != idents[test].get(key):
            problems.append(f"{key} differs between the arms (or is missing)")
    pins = {arm: sha256_file(p / PINS_RELATIVE) if (p / PINS_RELATIVE).is_file() else None for arm, p in zip(arms, (off, on))}
    if not pins[ref] or pins[ref] != pins[test]:
        problems.append("pins.json differs between the arms (or is missing)")
    problems += tg2_rehearsal_problems(Path(a.r2), Path(a.r3), manifest_path=a.rehearsal_manifest, manifest_sha=manifest["sha256"],
                                       wd=wd, arms=arms)
    image_id = tg2_grade.pinned_image_id()
    positives = read_json(a.positives, "--positives")
    problems += [f"positives: {p}" for p in positives_problems(positives, arm=ref, commit=st[ref].get("head"), identity=idents[ref],
                                                               frozen_prompt_date=inputs.get("frozen_prompt_date"), image_id=image_id,
                                                               cancel_path_sha256=worktree_cancel_path_sha256(off))]
    draw = Path(__file__).resolve().parents[1] / "m65" / "tg2_draw.json"
    if not draw.is_file() or sha256_file(draw) != schedules.TG2_DRAW_SHA256:
        problems.append("the committed tg2 draw is not the pinned one (TG2_DRAW_SHA256)")
    if problems:
        raise Refusal("; ".join(problems))
    elapsed = [e for e in (request_elapsed_max(a.r2), request_elapsed_max(a.r3)) if e is not None]
    settle = max(float(chain_core.P426_SETTLE_BOUND_S), 2 * max(elapsed)) if elapsed else float(chain_core.P426_SETTLE_BOUND_S)
    run_checks(checks, "v8", off_worktree=off, on_worktree=on, build=inputs["build"], production_ref=inputs["production_ref"],
               gitlinks=dict(gitlinks), off_head=st[ref]["head"], suite_receipt=inputs.get("stack_suite_receipt"),
               suite_receipt_sha256=inputs["stack_suite_receipt_sha256"], wd=wd, arms=arms, corpus="tg2")

    def receipts(root):
        root = Path(root)
        return dict(leg=Path(root).name, leg_sha256=sha256_file(root / "leg.json"),
                    receipt_sha256=sha256_file(root / "receipt.json") if (root / "receipt.json").is_file() else None)
    named = {**{f"{arm}_commit": st[arm]["head"] for arm in arms},
             **{f"{arm}_worktree": portable(p, wd, f"--arm-worktree {arm}") for arm, p in zip(arms, (off, on))}}
    return write_record(a.out, dict(
        kind=KIND_V8, build=inputs["build"], **kv, corpus="tg2", **named,
        gitlinks=gitlinks, production_ref=inputs["production_ref"], pins_sha256=pins[ref],
        grader_image_id=inputs["grader_image_id"], frozen_prompt_date=inputs["frozen_prompt_date"],
        pilot_deadline_s=TG2_PILOT_DEADLINE_S, settle_bound_s=settle, generic_pred_s=chain_core.GENERIC_PRED_S,
        volatile_env_keys=list(VOLATILE_ENV_KEYS), rehearsal_manifest_sha256=manifest["sha256"],
        rehearsal_receipts=dict(r2=receipts(a.r2), r3=receipts(a.r3)),
        client_step_cap=dict(seconds=prc.CLIENT_STEP_CAP_S, source=prc.CLIENT_STEP_CAP_SOURCE, bound_by="opencode_exe_sha256"),
        stack_suite_receipt_sha256=inputs["stack_suite_receipt_sha256"], tg2_draw_sha256=schedules.TG2_DRAW_SHA256,
        tg2_universe_sha256=schedules.TG2_UNIVERSE_SHA256, tg2_image_id=image_id, positives_sha256=positives["sha256"],
        **{k: idents[ref][k] for k in IDENTITY_KEYS}))


def cmd_v8(a, ops, checks, wd):
    from . import chain_core
    if getattr(a, "corpus", "tg1") == "tg2":
        return cmd_v8_tg2(a, ops, checks, wd)
    if not a.r1_off or not a.r1_on:
        raise Refusal("the following arguments are required: --r1-off, --r1-on")
    need(ops, "worktree_state", "identity", "historical_walls", "build_inputs")
    arms, kv = _kv_fields(a)
    r0, r_second = arms                                          # role order (never `r1`: the R1 legs' name below)
    off, on = Path(a.off_worktree), Path(a.on_worktree)
    try:
        manifest = p426_record.load(a.rehearsal_manifest, mode="chain", rehearsal=True)["doc"]
    except p426_record.RecordError as exc:
        raise Refusal(f"--rehearsal-manifest {exc}") from None
    if lever_of(manifest) != ("kv" if kv else "mtp") or (kv and tuple(manifest.get("arms") or ()) != arms):
        raise Refusal("--rehearsal-manifest was written for another lever or KV pair")
    problems = arm_problems(ops, off, on, arms)
    st = {arm: ops.worktree_state(p) for arm, p in zip(arms, (off, on))}
    gitlinks = {key: st[r0].get("gitlinks", {}).get(path) or "" for key, path in GITLINKS}
    inputs = ops.build_inputs()
    problems += build_problems(inputs, gitlinks)
    if kv and inputs.get("build") not in p426_plan.KV_BUILDS:
        problems.append(f"build {inputs.get('build')!r} is not a KV build {p426_plan.KV_BUILDS}")
    idents = {arm: ops.identity(p) for arm, p in zip(arms, (off, on))}
    for key in IDENTITY_KEYS:
        if not re.fullmatch(r"[0-9a-f]{64}", str(idents[r0].get(key))) or idents[r0].get(key) != idents[r_second].get(key):
            problems.append(f"{key} differs between the arms (or is missing)")
    pins = {arm: sha256_file(p / PINS_RELATIVE) if (p / PINS_RELATIVE).is_file() else None for arm, p in zip(arms, (off, on))}
    if not pins[r0] or pins[r0] != pins[r_second]:
        problems.append("pins.json differs between the arms (or is missing)")
    rehearsal, diffs = rehearsal_problems(Path(a.r1_off), Path(a.r1_on), Path(a.r2), Path(a.r3), ops,
                                          manifest_path=a.rehearsal_manifest, manifest_sha=manifest["sha256"], wd=wd, arms=arms)
    problems += rehearsal
    walls = need_walls(ops.historical_walls(), "w_python_s", "w_go_s", "max_request_elapsed_s")
    r1 = [e for e in (request_elapsed_max(a.r1_off), request_elapsed_max(a.r1_on)) if e is not None]
    if not r1:
        problems.append("R1's item records carry no request elapsed_s (the settle bound cannot be derived)")
    if problems:
        raise Refusal("; ".join(problems))
    settle = max(float(chain_core.P426_SETTLE_BOUND_S), 2 * max(max(r1), walls["max_request_elapsed_s"]))      # spec 16.8: derived
    run_checks(checks, "v8", off_worktree=off, on_worktree=on, build=inputs["build"], production_ref=inputs["production_ref"],
               gitlinks=dict(gitlinks), off_head=st[r0]["head"], suite_receipt=inputs.get("stack_suite_receipt"),
               suite_receipt_sha256=inputs["stack_suite_receipt_sha256"], wd=wd, **({"arms": arms} if kv else {}))
    if kv:  # M76: the arms by their KV label (commits, worktrees), lever kv
        named = {**{f"{arm}_commit": st[arm]["head"] for arm in arms},
                 **{f"{arm}_worktree": portable(p, wd, f"--arm-worktree {arm}") for arm, p in zip(arms, (off, on))}}
    else:
        named = dict(off_commit=st["off"]["head"], on_commit=st["on"]["head"],
                     off_worktree=portable(off, wd, "--off-worktree"), on_worktree=portable(on, wd, "--on-worktree"))
    return write_record(a.out, dict(
        kind=KIND_V8, build=inputs["build"], **kv, **named,
        gitlinks=gitlinks, production_ref=inputs["production_ref"], pins_sha256=pins[r0],
        grader_image_id=inputs["grader_image_id"], frozen_prompt_date=inputs["frozen_prompt_date"],
        pilot_deadline_s=deadline_formula({"python": PILOT_N}, {"python": walls["w_python_s"], "go": walls["w_go_s"]}),
        settle_bound_s=settle, generic_pred_s=chain_core.GENERIC_PRED_S, volatile_env_keys=list(VOLATILE_ENV_KEYS),
        r1_env_difference=diffs, rehearsal_manifest_sha256=manifest["sha256"],
        client_step_cap=dict(seconds=prc.CLIENT_STEP_CAP_S, source=prc.CLIENT_STEP_CAP_SOURCE, bound_by="opencode_exe_sha256"),   # P593
        stack_suite_receipt_sha256=inputs["stack_suite_receipt_sha256"], **{k: idents[r0][k] for k in IDENTITY_KEYS}))


def planned_slots(root, chain=None) -> int:
    """The leg's plan: the slots of its frozen schedule (`schedule.json`, whose sha256 `chain.json` records), never a constant
    (spec 16.8). ValueError when the schedule is missing, unreadable, malformed or not the frozen one."""
    from . import schedules
    root = Path(root)
    chain = chain if chain is not None else read_chain(root)
    try:
        sched = json.loads((root / "schedule.json").read_text())
    except (OSError, ValueError):
        raise ValueError("the leg has no readable frozen schedule.json") from None
    if chain.get("schedule_sha256") != schedules.schedule_sha256(sched):
        raise ValueError("schedule.json is not the schedule chain.json froze (schedule_sha256 differs)")
    return planned_slots_of(sched)


def planned_slots_of(sched) -> int:
    """The slots a frozen schedule's invocations run (a pilot-only leg's `full_names` is its whole order, not its run); the tg1
    and the tg2 P426 schedules have the same `blocks[].legs[].invocations[]` shape."""
    try:
        return sum(len(inv["names"]) for block in sched["blocks"] for leg in block["legs"] for inv in leg["invocations"])
    except (KeyError, TypeError):
        raise ValueError("the frozen schedule.json has no blocks / legs / invocations") from None


def tg2_pilot_leg(arm):
    return f"tg2-m76-{arm}-pilot"


def pilot_gate_problems(off_root, on_root, arms=("off", "on"), *, leg_name=None, n=PILOT_N) -> list:
    """The complete pilot gate (spec 1): both legs VALID with their own leg names, 5 / 5 items reconciled, zero DNF, ON engagement
    proven on every eligible request, both speed-valid, the pair gate passed. The failed conditions (empty = the gate passes).
    M76 (lever kv): `arms` = the KV pair; both arms engaged, the KV pair gate. M76 B4b-1: `leg_name(arm)` and `n` of the corpus
    (tg2: `tg2-m76-<arm>-pilot`, 4 items)."""
    lever = "kv" if tuple(arms) != ("off", "on") else "mtp"
    problems = []
    for arm, root in zip(arms, (off_root, on_root)):
        try:
            leg, chain = read_leg(root), read_chain(root)
        except Refusal as exc:
            problems.append(f"pilot {arm}: {exc}")
            continue
        want_leg = leg_name(arm) if leg_name else kv_pilot_leg(arm) if lever == "kv" else f"tg1-p426-{arm}-pilot"
        if leg.get("leg") != want_leg:
            problems.append(f"pilot {arm}: the leg is {leg.get('leg')!r}, not {want_leg}")
        dnf = len(chain.get("p426_dnf") or [])
        if leg.get("state") == "VALID_WITH_DNF" or dnf:
            problems.append(f"pilot {arm}: {dnf} DNF (the gate needs zero)")
        elif leg.get("state") != "VALID":
            problems.append(f"pilot {arm}: the leg is {leg.get('state')}, not VALID")
        rows = [e for e in chain.get("p426_ledger") or [] if e.get("kind") == "row"]
        try:
            planned = planned_slots(root, chain)
        except ValueError as exc:
            planned = None
            problems.append(f"pilot {arm}: {exc}")
        if planned is not None and (len(rows) != planned or planned != n):
            problems.append(f"pilot {arm}: {len(rows)} / {planned} items realized (the pilot is {n})")
        problems += [f"pilot {arm}: {p}" for p in leg_items_problems(root, arm)]
        try:
            receipt = read_receipt(root)
            said = pr.kv_arm_of(receipt) if lever == "kv" and pr.arm_of(receipt) == "on" else pr.arm_of(receipt)
            if said != arm:
                problems.append(f"pilot {arm}: the receipt's worker argv does not say {arm}")
        except Refusal as exc:
            problems.append(f"pilot {arm}: {exc}")
        if leg.get("speed_valid") is not True:
            problems.append(f"pilot {arm}: speed-invalid ({leg.get('speed_reason')})")
    try:
        mismatch = pr.gate_problems(read_receipt(off_root), read_receipt(on_root), lever=lever)
    except Refusal as exc:
        mismatch = [str(exc)]
    return problems + [f"pair gate: {p}" for p in mismatch]


def pilot_dossier_path(off_root, on_root, arms=("off", "on")) -> Path:
    """`<out-base>/pairs/pilot__off-a<n>__on-a<m>.json` of the two pilot attempt roots (`<leg>.a<n>`); M76 (lever kv):
    `pilot__<ref>-a<n>__<test>-a<m>.json`."""
    n, m = (Path(r).name.rsplit(".a", 1)[-1] for r in (off_root, on_root))
    return Path(off_root).parent / "pairs" / f"pilot__{arms[0]}-a{n}__{arms[1]}-a{m}.json"


def pilot_dossier_problems(off_root, on_root, arms=("off", "on")) -> list:
    """The pilot pair's dossier is a sealed PASS that names these two attempts and these two receipts (by sha256)."""
    path = pilot_dossier_path(off_root, on_root, arms)
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return [f"the pilot pair dossier {path.name} is missing or unreadable"]
    if not ph.sealed_ok(doc):
        return [f"the pilot pair dossier {path.name}: its sha256 does not verify"]
    problems = []
    if doc.get("pair") != "pilot" or doc.get("verdict") != "PASS":
        problems.append(f"the pilot pair dossier {path.name} is not a PASS (verdict {doc.get('verdict')!r})")
    recorded = doc.get("arms") if isinstance(doc.get("arms"), dict) else {}
    for arm, root in zip(arms, (off_root, on_root)):
        got = recorded.get(arm) if isinstance(recorded.get(arm), dict) else {}
        if got.get("attempt") != Path(root).name:
            problems.append(f"the pilot pair dossier names attempt {got.get('attempt')!r} for {arm}, not {Path(root).name}")
        try:
            want = sha256_file(Path(root) / "receipt.json")
        except OSError:
            want = None
        if want is None or got.get("receipt_sha256") != want:
            problems.append(f"the pilot pair dossier's {arm} receipt_sha256 is not the receipt of {Path(root).name}")
    return problems


def pilot_walls_by_lang(root) -> dict:
    """{lang: [wall_s]} of the rows of the invocations `chain.json` counts (`pilot_walls`, keyed by the row id's language)."""
    root, out = Path(root), {}
    for inv in (read_chain(root).get("progress") or {}).get("invocations") or []:
        if inv.get("status") not in COUNTED_STATUSES:
            continue
        path = Path(inv["file"])
        path = path if path.is_absolute() else root / path
        try:
            lines = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        except (OSError, ValueError):
            raise Refusal(f"{root.name}: the rows file {path.name} is unreadable") from None
        for r in lines:
            if isinstance(r, dict) and r.get("wall_s") is not None and "/" in str(r.get("id")):
                out.setdefault(str(r["id"]).split("/", 1)[0], []).append(float(r["wall_s"]))
    return out


def tg2_deadline_s(leg, walls) -> float:
    """§3: `leg_deadline_s[leg] = 1.5 x sum_lang n_lang x w_<lang>_s + 1800 + 3660` (n from the table; 3660 = one P223 item)."""
    n = TG2_ITEM_COUNT[leg]
    return DEADLINE_FACTOR * sum(n * float(walls[lang]) for lang in TG2_LANGS) + DEADLINE_SLACK_S + TG2_MAX_ITEM_S


def write_amendment_tg2(base, pilot_a, pilot_b, out):
    """M76 B4b-1 (§3): after the strict pilot gate (both arms VALID, not VALID_WITH_DNF; 4 reconciled rows each; 0 DNF;
    speed-valid; engaged; pair-gated; the pilot dossier a PASS): `w_<lang>_s = max(max pilot wall of <lang> over both arms, 382)`,
    the tg2 leg deadlines, the settle bound as tg1's; every wall / deadline verified present, numeric and positive."""
    arms = check_tg2_pair(arms_of(base))                         # change review L6
    problems = (pilot_gate_problems(pilot_a, pilot_b, arms, leg_name=tg2_pilot_leg, n=TG2_PILOT_N)
                + pilot_dossier_problems(pilot_a, pilot_b, arms))
    walls, elapsed = {}, []
    if not problems:
        for arm, root in zip(arms, (pilot_a, pilot_b)):
            for lang, values in pilot_walls_by_lang(root).items():
                walls.setdefault(lang, []).extend(values)
            largest = request_elapsed_max(root)
            if largest is None:
                problems.append(f"pilot {arm}: its item records carry no request elapsed_s (the settle bound cannot be derived)")
            else:
                elapsed.append(largest)
        absent = [lang for lang in TG2_LANGS if not walls.get(lang)]
        if absent:
            problems.append(f"the pilots carry no row wall for {absent}")
    if problems:
        raise Refusal("; ".join(problems))
    w = {lang: max([*walls[lang], TG2_WALL_FLOOR_S]) for lang in TG2_LANGS}
    deadlines = {leg: tg2_deadline_s(leg, w) for leg in TG2_ITEM_COUNT}
    bad = [k for k, v in [*w.items(), *deadlines.items()] if not (isinstance(v, (int, float)) and v > 0)]
    if bad:
        raise Refusal(f"the tg2 walls / deadlines {bad} are not positive numbers")
    return write_record(out, dict(kind=KIND_AMENDMENT, v8_base_sha256=base["sha256"], corpus="tg2",
                                  **{f"w_{lang}_s": w[lang] for lang in TG2_LANGS}, leg_deadline_s=deadlines,
                                  settle_bound_s=max(float(base["settle_bound_s"]), 2 * max(elapsed)),
                                  pilot_dossier_sha256=sha256_file(pilot_dossier_path(pilot_a, pilot_b, arms))))


def write_amendment(v8_path, pilot_off, pilot_on, out, ops, corpus="tg1"):
    """Spec 10.2, after the COMPLETE pilot gate (run here: both pilots VALID, 5 / 5 reconciled, zero DNF, ON engagement, both
    speed-valid, the pilot pair dossier a PASS): `w_python` = the largest per-item wall over both pilots and the historical value,
    `w_go` = the historical Go value; the leg deadlines of both session legs and the reload; links the v8 base's sha256 and the
    sha256 of the pilot dossier the gate was run on. M76 B4b-1: `corpus="tg2"` (a tg2 v8 base) is `write_amendment_tg2`."""
    try:
        base = p426_record.read_sealed(v8_path)
    except p426_record.RecordError as exc:
        raise Refusal(f"--v8 {exc}") from None
    if base.get("kind") != KIND_V8:
        raise Refusal(f"--v8 {Path(v8_path).name}: kind {base.get('kind')!r} is not {KIND_V8}")
    if (base.get("corpus") == "tg2") != (corpus == "tg2"):
        raise Refusal(f"--v8 {Path(v8_path).name}: the record's corpus is {base.get('corpus', 'tg1')!r}, not {corpus!r}")
    if corpus == "tg2":
        return write_amendment_tg2(base, pilot_off, pilot_on, out)
    need(ops, "historical_walls")
    arms = arms_of(base)                                         # M76 (lever kv): the v8 base's KV pair
    problems = pilot_gate_problems(pilot_off, pilot_on, arms) + pilot_dossier_problems(pilot_off, pilot_on, arms)
    walls, elapsed = [], []
    if not problems:
        for arm, root in zip(arms, (pilot_off, pilot_on)):
            walls += pilot_walls(root)
            largest = request_elapsed_max(root)
            if largest is None:
                problems.append(f"pilot {arm}: its item records carry no request elapsed_s (the settle bound cannot be derived)")
            else:
                elapsed.append(largest)
    if problems:
        raise Refusal("; ".join(problems))
    hist = need_walls(ops.historical_walls(), "w_python_s", "w_go_s")
    w = {"python": max([*walls, hist["w_python_s"]]), "go": hist["w_go_s"]}
    session = deadline_formula(ITEM_COUNT, w)
    deadlines = {"s1": session, "s2": session, "reload": deadline_formula({"python": PILOT_N}, w)}
    if lever_of(base) == "kv":           # M76 (erratum v1.2): tg1 session s3 has the paired sessions' deadline
        deadlines["s3"] = session
    return write_record(out, dict(kind=KIND_AMENDMENT, v8_base_sha256=base["sha256"], w_python_s=w["python"], w_go_s=w["go"],
                                  leg_deadline_s=deadlines,
                                  settle_bound_s=max(float(base["settle_bound_s"]), 2 * max(elapsed)),
                                  pilot_dossier_sha256=sha256_file(pilot_dossier_path(pilot_off, pilot_on, arms))))


def _read_leg_or(problems, root, what):
    try:
        return read_leg(root)
    except Refusal as exc:
        problems.append(f"{what}: {exc}")
        return None


def cmd_amend(a, ops, checks, wd):
    return write_amendment(a.v8, Path(a.pilot_off), Path(a.pilot_on), a.out, ops, corpus=getattr(a, "corpus", "tg1"))


class RefusingParser(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal(message)


def parse_args(argv):
    ap = RefusingParser(prog="bench.p426_freeze", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("rehearsal", "v8"):
        p = sub.add_parser(name)
        p.add_argument("--off-worktree", default=None, help="lever mtp (required)")
        p.add_argument("--on-worktree", default=None, help="lever mtp (required)")
        p.add_argument("--out", required=True)
        p.add_argument("--lever", default="mtp", choices=("mtp", "kv"), help="M76 B3: kv = a KV pair (both MTP ON)")
        p.add_argument("--pair", default=None, help="lever kv: <reference>,<treatment>")
        p.add_argument("--arm-worktree", action="append", default=[], help="lever kv: <arm>=<worktree> (each arm of the pair)")
    sub.choices["rehearsal"].add_argument("--out-root", required=True)
    sub.choices["rehearsal"].add_argument("--frozen-prompt-date", required=True, metavar="'Www Mmm DD YYYY'",
                                          help="the date opencode shows the model during the rehearsal (recorded in the manifest)")
    v8 = sub.choices["v8"]
    for flag in ("--rehearsal-manifest", "--r2", "--r3"):
        v8.add_argument(flag, required=True)
    for flag in ("--r1-off", "--r1-on"):
        v8.add_argument(flag, default=None, help="tg1 (required): the R1 pair's leg roots; tg2 has no R1")
    v8.add_argument("--positives", default=None, help="--corpus tg2 (required): the sealed positives record")
    am = sub.add_parser("amend")
    for flag in ("--v8", "--pilot-off", "--pilot-on", "--out"):
        am.add_argument(flag, required=True)
    for p in (sub.choices["rehearsal"], v8, am):
        p.add_argument("--corpus", default="tg1", choices=("tg1", "tg2"),
                       help="M76 B4b-1: tg2 = the tg2 legs of lever kv (rehearsal R2 / R3, the positives, the tg2 walls)")
    v8.add_argument("--build-inputs", default=None, metavar="JSON", help="the box ops' input: build, production_ref, grader_image_id, ...")
    for p in (v8, am):
        p.add_argument("--historical-walls", default=None, metavar="JSON", help='the box ops\' input: {"python": s, "go": s}')
    a = ap.parse_args(argv)
    if a.cmd in ("rehearsal", "v8"):
        resolve_arms(a)
        if a.corpus == "tg2" and a.lever != "kv":
            raise Refusal("--corpus tg2 is for --lever kv (the tg2 legs of M76)")
        if a.corpus == "tg2":
            check_tg2_pair(a.arms)
            if a.cmd == "v8" and (a.r1_off or a.r1_on):          # change review L5: spec §3 "no R1"
                raise Refusal("--r1-off / --r1-on: the tg2 v8 base has no R1 (the pilot pair takes R1's role)")
    return a


def resolve_arms(a):
    """`a.arms` (role order) and `a.off_worktree` / `a.on_worktree` (the roles' worktrees): lever mtp = `--off-worktree` /
    `--on-worktree` (both required); lever kv = `--pair <ref>,<test>` + `--arm-worktree <arm>=<path>` for each arm (M76 B3)."""
    if a.lever == "mtp":
        if a.pair or a.arm_worktree:
            raise Refusal("--pair / --arm-worktree are lever kv flags")
        if not a.off_worktree or not a.on_worktree:
            raise Refusal("the following arguments are required: --off-worktree, --on-worktree")
        a.arms = ("off", "on")
        return a
    if a.off_worktree or a.on_worktree:
        raise Refusal("--off-worktree / --on-worktree are lever mtp flags (lever kv: --arm-worktree <arm>=<path>)")
    try:
        pair = p426_plan.check_kv_pair(*(a.pair or "").split(",", 1)) if a.pair and "," in a.pair else None
    except ValueError as exc:
        raise Refusal(str(exc)) from None
    if pair is None:
        raise Refusal("--lever kv needs --pair <reference>,<treatment>")
    trees = {}
    for v in a.arm_worktree:
        arm, sep, path = v.partition("=")
        if not sep or arm not in pair or arm in trees or not path:
            raise Refusal(f"--arm-worktree {v!r} is not <arm>=<path> for an arm of the pair (once each)")
        trees[arm] = path
    if set(trees) != set(pair):
        raise Refusal(f"--arm-worktree names {sorted(trees)}, the pair is {list(pair)}")
    a.arms, a.off_worktree, a.on_worktree = pair, trees[pair[0]], trees[pair[1]]
    return a


def main(argv=None, *, ops=None, checks=None):
    try:
        a = parse_args(sys.argv[1:] if argv is None else argv)
        if ops is None:
            import os
            ops = BoxOps(os.environ.get("STACK_WORKDIR") or "", getattr(a, "build_inputs", None), getattr(a, "historical_walls", None),
                         corpus=getattr(a, "corpus", "tg1"))
        wd = stack_workdir(ops)
        rec = dict(rehearsal=cmd_rehearsal, v8=cmd_v8, amend=cmd_amend)[a.cmd](a, ops, checks or default_checks, wd)
    except Refusal as exc:
        print("REFUSED: " + " ".join(str(exc).split()), file=sys.stderr)
        return 2
    print(f"{rec['kind']} {rec['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
