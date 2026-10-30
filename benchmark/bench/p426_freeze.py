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
KILL_CASES = ("kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted")
COUNTED_STATUSES = ("validated", "partial_incident", "hook_stopped")  # invocations whose rows belong to the leg
GITLINKS = (("mlx_vlm", "src/mlx-vlm"), ("mlx_serve", "src/mlx-serve"))
IDENTITY_KEYS = ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")
ENTRY_POINTS = (".venv/bin/python", ".venv-bench/bin/python", "src/mlx-vlm/.venv/bin/python",       # P514: the fork venv too
                "/".join(CHAIN_ENTRY), "benchmark/run_tg1_probe.py", "benchmark/m1/bench_watch.py")
HELP_ENTRIES = ("/".join(CHAIN_ENTRY), "benchmark/run_tg1_probe.py")                              # K3: the real entry point answers --help
PINS_RELATIVE = pr.PINS_RELATIVE
REHEARSAL_DIR = "p426/rehearsal"


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


def r1_difference_problems(entries) -> list:
    """Spec 6.5 / 16.7: every entry of `r1_env_difference` is on the closed allowed list: the three MTP flag pairs of the worker argv,
    the drafter snapshot, or a key of the closed volatile list. Anything else is named."""
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
            problems += [f"{e['slot']}: {p}" for p in prc.engagement_problems(requests, arm, item=not dnf)]
            judged += sum(1 for r in requests if not r.get("error") and int(r.get("generated_tokens") or 0) >= 2)
    if str(arm).lower() == "on" and not judged and not problems:
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
    if pr.arm_of(receipt) != arm:
        problems.append(f"the receipt's worker argv says {pr.arm_of(receipt)}, not {arm}")
    return problems + leg_items_problems(root, arm)


REHEARSAL_LEGS = (("R1 off", "tg1-p426-rehearsal-off", None), ("R1 on", "tg1-p426-rehearsal-on", None),
                  ("R2", "tg1-p426-rehearsal-mismatch", "reconcile-mismatch"), ("R3", "tg1-p426-rehearsal-kill", "stall-kill"))


def binding_problems(roots, manifest_path, manifest_sha, wd) -> list:
    """Each of R1-off / R1-on / R2 / R3 is a leg run under THIS rehearsal manifest (its `chain.json` names it as the frozen record,
    by path and sha256), with the expected leg name and, for R2 / R3, the expected `--inject` (R1: none). The manifest's own
    commits are not compared with the v8 arms (spec 1: rehearsals run on the B2 / throwaway commits)."""
    problems = []
    for (label, leg_name, inject), root in zip(REHEARSAL_LEGS, roots):
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


def rehearsal_problems(r1_off, r1_on, r2, r3, ops, *, manifest_path, manifest_sha, wd):
    """(problems, r1 differences): R1 VALID both arms and its pair gate passed; R2 INVALID for the injected reason; R3 VALID with
    a real kill classified; every leg bound to this manifest (`binding_problems`). R2 / R3 are excluded from the pair gate (spec 1)."""
    problems = binding_problems((r1_off, r1_on, r2, r3), manifest_path, manifest_sha, wd)
    problems += [f"R1 {arm}: {p}" for arm, root in (("off", r1_off), ("on", r1_on)) for p in valid_leg_problems(root, arm)]
    diffs = []
    if not problems:
        pair = pr.pair_problems(read_receipt(r1_off), read_receipt(r1_on))
        problems += [f"R1 pair gate: {p}" for p in pair]
        try:
            diffs = list((getattr(ops, "r1_differences", None) or receipt_differences)(r1_off, r1_on))
        except Refusal as exc:
            problems.append(f"R1: {exc}")
        problems += [f"R1 {p}" for p in r1_difference_problems(diffs)]
    try:
        leg = read_leg(r2)
        invalid = read_chain(r2).get("p426_invalid") or []
        if leg.get("state") != "INVALID":
            problems.append(f"R2: leg state is {leg.get('state')!r}, it must be INVALID for the injected mismatch")
        elif len(invalid) != 1 or invalid[0].get("reason") != R2_REASON or leg.get("reason") != R2_REASON:
            problems.append(f"R2: INVALID, but not for the injected reconciliation mismatch (reason {leg.get('reason')!r})")
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
def arm_problems(ops, off, on) -> list:
    """The two arm worktrees: clean, two commits, identical gitlinks, the ON commit = OFF + exactly the restore diff."""
    st, problems = {}, []
    for arm, path in (("off", off), ("on", on)):
        st[arm] = ops.worktree_state(path)
        if st[arm].get("clean") is not True:
            problems.append(f"the {arm} worktree is not clean")
    if st["off"].get("head") == st["on"].get("head"):
        problems.append("the OFF and ON worktrees are at the same commit (the arms are two commits)")
    for key, path in GITLINKS:
        a, b = st["off"].get("gitlinks", {}).get(path), st["on"].get("gitlinks", {}).get(path)
        if not a or a != b:
            problems.append(f"gitlink {path} differs between the arms ({str(a)[:12]} vs {str(b)[:12]})")
    return problems


# ----------------------------------------------------------------------------------------------- live re-verification
def live_problems(base, ops, wd) -> list:
    """The sequencer's and every leg's re-verification of v8 against the live state: each arm's HEAD equals the record's commit,
    the tree is clean, the gitlinks are the record's and the probe identity is unchanged."""
    problems = []
    for arm in ("off", "on"):
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
def entry_point_problems(worktree) -> list:
    return [f"entry point <WT>/{rel} is missing" for rel in ENTRY_POINTS if not (Path(worktree) / rel).exists()]


def venv_problems(worktree, build) -> list:
    want = (p426_plan.EXPECTED_BUILDS.get(build) or {}).get("mlx")
    problems = []
    for venv in p426_plan.VENVS:
        have = p426_plan.venv_versions(worktree, venv)
        for pkg in ("mlx", "mlx-metal"):
            if want and have.get(pkg) != want:
                problems.append(f"<WT>/{venv}: {pkg} {have.get(pkg)!r} is not the lock's {want}")
    return problems


def help_problems(worktree) -> list:
    """K3: the chain and probe entry points answer `--help` from the worktree's own venv."""
    problems = []
    for rel in HELP_ENTRIES:
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


def default_checks(kind, *, off_worktree, on_worktree, build="s2", production_ref=None, gitlinks=None) -> list:
    """The real preconditions (spec 16.8: every one goes through `checks`): the restore diff between the two arms, both
    worktrees' entry points, and for v8 the venvs against the lock, K3 (`--help`) and the production tree at the gitlink."""
    problems = [f"restore diff: {p}" for p in p426_plan.restore_diff_problems(off_worktree, on_worktree, p426_plan.p426_ids.ENTRY)]
    for arm, wt in (("off", off_worktree), ("on", on_worktree)):
        found = entry_point_problems(wt)
        problems += [f"{arm}: {p}" for p in found]
        if kind != "v8" or found:
            continue
        problems += [f"{arm}: {p}" for p in venv_problems(wt, build)]
        problems += [f"{arm}: {p}" for p in help_problems(wt)]
        problems += [f"{arm}: {p}" for p in production_tree_problems(wt, production_ref, (gitlinks or {}).get("mlx_vlm"))]
    return problems


class BoxOps:
    """The real `ops`: git, the probe's `--print-identity`, and the two inputs only the operator knows (JSON files)."""

    def __init__(self, workdir, build_inputs=None, historical_walls=None):
        self.wd, self._inputs, self._walls = Path(workdir), build_inputs, historical_walls

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
        run = subprocess.run([str(Path(path) / ".venv-bench/bin/python"), str(Path(path) / "benchmark/run_tg1_probe.py"),
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


def cmd_rehearsal(a, ops, checks, wd):
    need(ops, "worktree_state", "identity")
    off, on = Path(a.off_worktree), Path(a.on_worktree)
    problems = arm_problems(ops, off, on)
    out_root = Path(a.out_root).resolve()
    if (wd / REHEARSAL_DIR).resolve() not in out_root.parents:
        problems.append(f"--out-root must lie under $STACK_WORKDIR/{REHEARSAL_DIR}/")
    if not datefreeze.valid(a.frozen_prompt_date):
        problems.append("--frozen-prompt-date must be 'Www Mmm DD YYYY' (zero-padded day)")
    ident, ident_on = ops.identity(off), ops.identity(on)
    for key in IDENTITY_KEYS:
        if not re.fullmatch(r"[0-9a-f]{64}", str(ident.get(key))) or ident.get(key) != ident_on.get(key):
            problems.append(f"{key} differs between the arms (or is missing)")
    if problems:
        raise Refusal("; ".join(problems))
    run_checks(checks, "rehearsal", off_worktree=off, on_worktree=on)
    st = {arm: ops.worktree_state(p) for arm, p in (("off", off), ("on", on))}
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


def cmd_v8(a, ops, checks, wd):
    from . import chain_core
    need(ops, "worktree_state", "identity", "historical_walls", "build_inputs")
    off, on = Path(a.off_worktree), Path(a.on_worktree)
    try:
        manifest = p426_record.load(a.rehearsal_manifest, mode="chain", rehearsal=True)["doc"]
    except p426_record.RecordError as exc:
        raise Refusal(f"--rehearsal-manifest {exc}") from None
    problems = arm_problems(ops, off, on)
    st = {arm: ops.worktree_state(p) for arm, p in (("off", off), ("on", on))}
    gitlinks = {key: st["off"].get("gitlinks", {}).get(path) or "" for key, path in GITLINKS}
    inputs = ops.build_inputs()
    problems += build_problems(inputs, gitlinks)
    idents = {arm: ops.identity(p) for arm, p in (("off", off), ("on", on))}
    for key in IDENTITY_KEYS:
        if not re.fullmatch(r"[0-9a-f]{64}", str(idents["off"].get(key))) or idents["off"].get(key) != idents["on"].get(key):
            problems.append(f"{key} differs between the arms (or is missing)")
    pins = {arm: sha256_file(p / PINS_RELATIVE) if (p / PINS_RELATIVE).is_file() else None for arm, p in (("off", off), ("on", on))}
    if not pins["off"] or pins["off"] != pins["on"]:
        problems.append("pins.json differs between the arms (or is missing)")
    rehearsal, diffs = rehearsal_problems(Path(a.r1_off), Path(a.r1_on), Path(a.r2), Path(a.r3), ops,
                                          manifest_path=a.rehearsal_manifest, manifest_sha=manifest["sha256"], wd=wd)
    problems += rehearsal
    walls = need_walls(ops.historical_walls(), "w_python_s", "w_go_s", "max_request_elapsed_s")
    r1 = [e for e in (request_elapsed_max(a.r1_off), request_elapsed_max(a.r1_on)) if e is not None]
    if not r1:
        problems.append("R1's item records carry no request elapsed_s (the settle bound cannot be derived)")
    if problems:
        raise Refusal("; ".join(problems))
    settle = max(float(chain_core.P426_SETTLE_BOUND_S), 2 * max(max(r1), walls["max_request_elapsed_s"]))      # spec 16.8: derived
    run_checks(checks, "v8", off_worktree=off, on_worktree=on, build=inputs["build"], production_ref=inputs["production_ref"],
               gitlinks=dict(gitlinks))
    return write_record(a.out, dict(
        kind=KIND_V8, build=inputs["build"], off_commit=st["off"]["head"], on_commit=st["on"]["head"],
        off_worktree=portable(off, wd, "--off-worktree"), on_worktree=portable(on, wd, "--on-worktree"),
        gitlinks=gitlinks, production_ref=inputs["production_ref"], pins_sha256=pins["off"],
        grader_image_id=inputs["grader_image_id"], frozen_prompt_date=inputs["frozen_prompt_date"],
        pilot_deadline_s=deadline_formula({"python": PILOT_N}, {"python": walls["w_python_s"], "go": walls["w_go_s"]}),
        settle_bound_s=settle, generic_pred_s=chain_core.GENERIC_PRED_S, volatile_env_keys=list(VOLATILE_ENV_KEYS),
        r1_env_difference=diffs, rehearsal_manifest_sha256=manifest["sha256"],
        stack_suite_receipt_sha256=inputs["stack_suite_receipt_sha256"], **{k: idents["off"][k] for k in IDENTITY_KEYS}))


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
    try:                                    # what the invocations run (a pilot-only leg's `full_names` is its whole order, not its run)
        return sum(len(inv["names"]) for block in sched["blocks"] for leg in block["legs"] for inv in leg["invocations"])
    except (KeyError, TypeError):
        raise ValueError("the frozen schedule.json has no blocks / legs / invocations") from None


def pilot_gate_problems(off_root, on_root) -> list:
    """The complete pilot gate (spec 1): both legs VALID with their own leg names, 5 / 5 items reconciled, zero DNF, ON engagement
    proven on every eligible request, both speed-valid, the pair gate passed. The failed conditions (empty = the gate passes)."""
    problems = []
    for arm, root in (("off", off_root), ("on", on_root)):
        try:
            leg, chain = read_leg(root), read_chain(root)
        except Refusal as exc:
            problems.append(f"pilot {arm}: {exc}")
            continue
        if leg.get("leg") != f"tg1-p426-{arm}-pilot":
            problems.append(f"pilot {arm}: the leg is {leg.get('leg')!r}, not tg1-p426-{arm}-pilot")
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
        if planned is not None and (len(rows) != planned or planned != PILOT_N):
            problems.append(f"pilot {arm}: {len(rows)} / {planned} items realized (the pilot is {PILOT_N})")
        problems += [f"pilot {arm}: {p}" for p in leg_items_problems(root, arm)]
        try:
            if pr.arm_of(read_receipt(root)) != arm:
                problems.append(f"pilot {arm}: the receipt's worker argv does not say {arm}")
        except Refusal as exc:
            problems.append(f"pilot {arm}: {exc}")
        if leg.get("speed_valid") is not True:
            problems.append(f"pilot {arm}: speed-invalid ({leg.get('speed_reason')})")
    try:
        mismatch = pr.pair_problems(read_receipt(off_root), read_receipt(on_root))
    except Refusal as exc:
        mismatch = [str(exc)]
    return problems + [f"pair gate: {p}" for p in mismatch]


def pilot_dossier_path(off_root, on_root) -> Path:
    """`<out-base>/pairs/pilot__off-a<n>__on-a<m>.json` of the two pilot attempt roots (`<leg>.a<n>`)."""
    n, m = (Path(r).name.rsplit(".a", 1)[-1] for r in (off_root, on_root))
    return Path(off_root).parent / "pairs" / f"pilot__off-a{n}__on-a{m}.json"


def pilot_dossier_problems(off_root, on_root) -> list:
    """The pilot pair's dossier is a sealed PASS that names these two attempts and these two receipts (by sha256)."""
    path = pilot_dossier_path(off_root, on_root)
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return [f"the pilot pair dossier {path.name} is missing or unreadable"]
    if not ph.sealed_ok(doc):
        return [f"the pilot pair dossier {path.name}: its sha256 does not verify"]
    problems = []
    if doc.get("pair") != "pilot" or doc.get("verdict") != "PASS":
        problems.append(f"the pilot pair dossier {path.name} is not a PASS (verdict {doc.get('verdict')!r})")
    arms = doc.get("arms") if isinstance(doc.get("arms"), dict) else {}
    for arm, root in (("off", off_root), ("on", on_root)):
        got = arms.get(arm) if isinstance(arms.get(arm), dict) else {}
        if got.get("attempt") != Path(root).name:
            problems.append(f"the pilot pair dossier names attempt {got.get('attempt')!r} for {arm}, not {Path(root).name}")
        try:
            want = sha256_file(Path(root) / "receipt.json")
        except OSError:
            want = None
        if want is None or got.get("receipt_sha256") != want:
            problems.append(f"the pilot pair dossier's {arm} receipt_sha256 is not the receipt of {Path(root).name}")
    return problems


def write_amendment(v8_path, pilot_off, pilot_on, out, ops):
    """Spec 10.2, after the COMPLETE pilot gate (run here: both pilots VALID, 5 / 5 reconciled, zero DNF, ON engagement, both
    speed-valid, the pilot pair dossier a PASS): `w_python` = the largest per-item wall over both pilots and the historical value,
    `w_go` = the historical Go value; the leg deadlines of both session legs and the reload; links the v8 base's sha256 and the
    sha256 of the pilot dossier the gate was run on."""
    try:
        base = p426_record.read_sealed(v8_path)
    except p426_record.RecordError as exc:
        raise Refusal(f"--v8 {exc}") from None
    if base.get("kind") != KIND_V8:
        raise Refusal(f"--v8 {Path(v8_path).name}: kind {base.get('kind')!r} is not {KIND_V8}")
    need(ops, "historical_walls")
    problems = pilot_gate_problems(pilot_off, pilot_on) + pilot_dossier_problems(pilot_off, pilot_on)
    walls, elapsed = [], []
    if not problems:
        for arm, root in (("off", pilot_off), ("on", pilot_on)):
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
    return write_record(out, dict(kind=KIND_AMENDMENT, v8_base_sha256=base["sha256"], w_python_s=w["python"], w_go_s=w["go"],
                                  leg_deadline_s={"s1": session, "s2": session, "reload": deadline_formula({"python": PILOT_N}, w)},
                                  settle_bound_s=max(float(base["settle_bound_s"]), 2 * max(elapsed)),
                                  pilot_dossier_sha256=sha256_file(pilot_dossier_path(pilot_off, pilot_on))))


def _read_leg_or(problems, root, what):
    try:
        return read_leg(root)
    except Refusal as exc:
        problems.append(f"{what}: {exc}")
        return None


def cmd_amend(a, ops, checks, wd):
    return write_amendment(a.v8, Path(a.pilot_off), Path(a.pilot_on), a.out, ops)


class RefusingParser(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal(message)


def parse_args(argv):
    ap = RefusingParser(prog="bench.p426_freeze", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("rehearsal", "v8"):
        p = sub.add_parser(name)
        p.add_argument("--off-worktree", required=True)
        p.add_argument("--on-worktree", required=True)
        p.add_argument("--out", required=True)
    sub.choices["rehearsal"].add_argument("--out-root", required=True)
    sub.choices["rehearsal"].add_argument("--frozen-prompt-date", required=True, metavar="'Www Mmm DD YYYY'",
                                          help="the date opencode shows the model during the rehearsal (recorded in the manifest)")
    v8 = sub.choices["v8"]
    for flag in ("--rehearsal-manifest", "--r1-off", "--r1-on", "--r2", "--r3"):
        v8.add_argument(flag, required=True)
    am = sub.add_parser("amend")
    for flag in ("--v8", "--pilot-off", "--pilot-on", "--out"):
        am.add_argument(flag, required=True)
    v8.add_argument("--build-inputs", default=None, metavar="JSON", help="the box ops' input: build, production_ref, grader_image_id, ...")
    for p in (v8, am):
        p.add_argument("--historical-walls", default=None, metavar="JSON", help='the box ops\' input: {"python": s, "go": s}')
    return ap.parse_args(argv)


def main(argv=None, *, ops=None, checks=None):
    try:
        a = parse_args(sys.argv[1:] if argv is None else argv)
        if ops is None:
            import os
            ops = BoxOps(os.environ.get("STACK_WORKDIR") or "", getattr(a, "build_inputs", None), getattr(a, "historical_walls", None))
        wd = stack_workdir(ops)
        rec = dict(rehearsal=cmd_rehearsal, v8=cmd_v8, amend=cmd_amend)[a.cmd](a, ops, checks or default_checks, wd)
    except Refusal as exc:
        print("REFUSED: " + " ".join(str(exc).split()), file=sys.stderr)
        return 2
    print(f"{rec['kind']} {rec['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
