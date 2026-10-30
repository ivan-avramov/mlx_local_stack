"""P426 P437: copy one Wave-1 leg's evidence into the MAIN checkout — the leg's rows / sidecars at their
`benchmark/results/<entry>/` path, everything else (receipts incl. refusals, wrapper / watch logs, power receipt, leg stdout,
the server-log slice, the M1 qualify directory) in `benchmark/results/p426/wave1/<leg>/` — scrubbed as the `evidence` branch is
(workdir / repo / home paths → `$STACK_WORKDIR` / `$STACK_REPO` / `$HOME`, username → `<user>`, hostname → `localhost`), with a
`SCRUB_MANIFEST.json` of original and published sha256. Fail closed: an existing destination, residual PII, a binary file
carrying PII or an oversized file refuses before anything is written. Commits are the operator session's (`data(bench)`).

Wave 2 (B2 spec 11; `python -m bench.p426_harvest wave2 --leg-root … --main-root … --evidence-stage …`, below `harvest_wave2`): one
attempt's leg root, the run / evidence directories its manifests name and the leg's server-log byte range are inventoried against a
closed rule table, every reference is resolved transitively, and the files are published in two stages (evidence, then `main`) with
`HARVEST.json` in the `main` destination as the single commit point. The Wave-1 entry points above are unchanged.
"""

import argparse
import dataclasses
import getpass
import hashlib
import json
import lzma
import os
import re
import shutil
import socket
import stat as statmod
import sys
import time
from pathlib import Path

from bench import piicheck

MAX_FILE_BYTES = 90 * 1024 * 1024  # GitHub refuses files over 100 MB
COMPRESS_BYTES = 8 * 1024 * 1024  # a larger dossier file is published `<name>.xz` (worker logs compress ≈ 4500×)
WAVE1 = Path("benchmark") / "results" / "p426" / "wave1"


def wave1_dir(build="s"):
    """`wave1` for S, `wave1.<label>` for any other build (T3 §4: a label never reads or writes another label's dossiers)."""
    from bench.p426_plan import check_build, is_s

    return WAVE1 if is_s(build) else WAVE1.with_name(f"wave1.{check_build(build)}")


class HarvestError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Scrub:
    workdir: Path
    repo: Path
    home: Path
    user: str
    hosts: tuple
    emails: tuple = ()          # Wave 2 (spec 16.5): the operator's address(es); the harvest refuses them and their domain
    # the exact in-memory credential values every publication scans for (never shown, compared or hashed with the scrub)
    secrets: dict = dataclasses.field(default_factory=dict, repr=False, compare=False, hash=False)

    def _paths(self):
        pairs = []
        for p, token in ((self.workdir, "$STACK_WORKDIR"), (self.repo, "$STACK_REPO"), (self.home, "$HOME")):
            for form in {str(Path(p)), str(Path(p).resolve())}:
                pairs.append((form, token))
        return sorted(pairs, key=lambda kv: -len(kv[0]))  # the longest (most specific) path first

    def text(self, s):
        for form, token in self._paths():
            s = s.replace(form, token)
        s = re.sub(rf"(?<![\w.-]){re.escape(self.user)}(?![\w-])", "<user>", s)
        for host in sorted(self.hosts, key=len, reverse=True):
            s = re.sub(rf"(?<![\w.-]){re.escape(host)}(?![\w-])", "localhost", s)
        return s

    def raw_markers(self):
        return [m.encode() for m in (self.user, *self.hosts, *(f for f, _ in self._paths()))]


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _publish(src_bytes, rel, scrub, compressible=False):
    """(published rel, scrubbed bytes, published bytes, problems) for one file; a compressible file over COMPRESS_BYTES is
    published as `<rel>.xz` of its scrubbed bytes."""
    try:
        text = src_bytes.decode("utf-8")
    except UnicodeDecodeError:
        hits = [m.decode() for m in scrub.raw_markers() if m and m in src_bytes]
        scrubbed, problems = src_bytes, ([f"{rel}: binary file carries PII markers {hits}"] if hits else [])
    else:
        out = scrub.text(text)
        scrubbed = out.encode("utf-8")
        problems = [f"{rel}: PII after scrub: {v}" for v in piicheck.violations(out, path=rel, line=1)]
    published = scrubbed
    if compressible and len(scrubbed) > COMPRESS_BYTES:
        rel, published = f"{rel}.xz", lzma.compress(scrubbed)
    if len(published) > MAX_FILE_BYTES:
        problems.append(f"{rel}: {len(published)} bytes > {MAX_FILE_BYTES}")
    return rel, scrubbed, published, problems


def _sources(name, plan, receipts, stdout, log_slice, dossier):
    """[(destination rel path, source path or None, bytes)] for the leg."""
    items = []
    if plan.get("kind") == "qualify":
        out_dir = Path(plan["out_dir"])
        if out_dir.exists():
            for p in sorted(q for q in out_dir.rglob("*") if q.is_file()):
                items.append((dossier / "m1" / p.relative_to(out_dir), p))
    else:
        res = Path(plan["results_dir"])
        if res.exists():
            for p in sorted(res.glob(f"{plan['stem']}.*")):
                if p.is_file():
                    items.append((Path("benchmark") / "results" / plan["entry"] / p.name, p))
    for p in sorted(Path(receipts).glob(f"{name}.*")):
        if p.is_file():
            items.append((dossier / p.name, p))
    out = [(rel, src, src.read_bytes()) for rel, src in items]
    out.append((dossier / "leg.stdout", None, stdout or b""))
    out.append((dossier / "server_log_slice.log", None, log_slice or b""))
    return out


def harvest(name, plan, *, main_root, receipts, stdout, log_slice, scrub, build="s"):
    main_root = Path(main_root)
    dossier = wave1_dir(build) / name
    problems, staged = [], []
    if (main_root / dossier).exists():
        problems.append(f"{dossier} exists (a leg is harvested once)")
    for rel, src, data in _sources(name, plan, receipts, stdout, log_slice, dossier):
        rel, scrubbed, published, found = _publish(data, str(rel), scrub, compressible=Path(rel).is_relative_to(dossier))
        if (main_root / rel).exists():
            problems.append(f"{rel} exists")
        problems += found
        staged.append((rel, src, data, scrubbed, published))
    if problems:
        raise HarvestError(f"{name}: " + "; ".join(problems)[:2000])
    manifest = dict(leg=name, files={})
    for rel, src, data, scrubbed, published in staged:
        dest = main_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(published)
        rec = dict(source=scrub.text(str(src)) if src else None, original_sha256=_sha(data), scrubbed_sha256=_sha(scrubbed),
                   published_sha256=_sha(published))
        if published is not scrubbed:
            rec["compression"] = "xz"
        manifest["files"][str(rel)] = rec
    (main_root / dossier / "SCRUB_MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    for rel, rec in manifest["files"].items():  # read back
        if _sha((main_root / rel).read_bytes()) != rec["published_sha256"]:
            raise HarvestError(f"{rel}: read-back sha mismatch")
    return manifest


def harvest_run_files(paths, *, main_root, scrub, overwrite=(), build="s"):
    """The run-level records (frozen.json, the ON overlay; `overwrite` = append-only logs refreshed each harvest)."""
    wave1 = wave1_dir(build)
    run = Path(main_root) / wave1 / "run"
    staged, problems = [], []
    for p in paths:
        p = Path(p)
        rel = str(wave1 / "run" / p.name)
        _, _, published, found = _publish(p.read_bytes(), rel, scrub)
        problems += found
        dest = run / p.name
        if dest.exists() and p.name not in overwrite and dest.read_bytes() != published:
            problems.append(f"{rel} differs from the harvested copy")
        staged.append((dest, published))
    if problems:
        raise HarvestError("; ".join(problems)[:2000])
    run.mkdir(parents=True, exist_ok=True)
    for dest, published in staged:
        if not dest.exists() or dest.read_bytes() != published:
            dest.write_bytes(published)


# ============================================================================================ Wave 2 (B2 spec 11, 16)
WAVE2 = Path("benchmark") / "results" / "p426" / "wave2"
LEG_STATES = ("VALID", "VALID_WITH_DNF", "INVALID", "NOT_STARTED", "OVERRUN")
ATTEMPT_RE = re.compile(r"^(?P<leg>[A-Za-z0-9][A-Za-z0-9-]*)\.a(?P<n>[1-9][0-9]*)$")
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}-[0-9a-f]{12}$")
BARRIER_RE = re.compile(r"^(?P<base>.+)\.item(?P<k>[0-9]+)\.(?P<kind>ready|go|done|continue|stop)$")
CONTROL_RE = re.compile(r"\.(ack|cancel)$", re.IGNORECASE)        # the chain names them `<stem>.ACK` / `<stem>.CANCEL`
LEG_MAIN = ("leg.json", "chain.json", "schedule.json", "receipt.json", "watch.jsonl", "log_bounds.json")
RAW_SUFFIXES = (".log", ".txt", ".stdout", ".stderr")
EVIDENCE_SUFFIXES = (".jsonl", ".json", ".txt", ".log", ".html")     # events, stderr, export, date-freeze / tool-window / web receipts
PRIVATE_RUN_DIRS = ("home", "data", "state", "cache", "tmp")          # opencode's own state: never copied
ROW_REFS = (("events_path", "events"), ("stderr_path", "stderr"), ("transcript_path", "export"), ("datefreeze_path", "datefreeze"),
            ("toolwindows_path", "toolwindows"))
PORTABLE_ROOT = "$STACK_WORKDIR"        # the portable form of a workdir path: what rows, manifests and records carry
OPERATOR_KIND = "operator_email"


def _rename(src, dst):
    """The one rename the commit protocol uses (a seam the tests interrupt)."""
    os.rename(src, dst)


def _canon_sha(doc):
    body = {k: v for k, v in doc.items() if k != "sha256"}
    return _sha(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _self_hash_problem(rel, doc):
    if isinstance(doc, dict) and isinstance(doc.get("sha256"), str) and doc["sha256"] != _canon_sha(doc):
        return f"{rel}: its sha256 is not the record's self-hash"
    return None


def _is_immutable(rel):
    """The §16-intro immutable records inside a leg root: the leg record, the receipt, the item records (ready / item / `.dnf`)
    and the `p426_dnf` sidecars."""
    return rel in ("leg.json", "receipt.json") or rel.startswith("items/") or "/p426_dnf/" in rel


def _immutable_problem(rel, doc):
    """An immutable record carries a PRESENT `sha256` equal to its self-hash: a missing hash fails like a wrong one."""
    if not isinstance(doc, dict) or not isinstance(doc.get("sha256"), str):
        return f"{rel}: an immutable record without its sha256"
    return _self_hash_problem(rel, doc)


# -------------------------------------------------------------------------------------------- the closed rule table
def classify(kind, rel):
    """(destination, reason) of one regular file, or None when no rule matches (the harvest fails). `kind` ∈ leg / run / evidence;
    `rel` is the posix path below that root. `main` = parsed / structured artifacts; `evidence` = raw logs and streams."""
    parts = rel.split("/")
    name = parts[-1]
    tree = next((i for i, seg in enumerate(parts[:-1]) if seg.endswith(".final_tree")), None)
    if tree is not None:                                  # a model's final tree (any root): its manifest, its content-addressed objects
        below = parts[tree + 1:]
        if len(below) == 1 and name == "manifest.json":
            return "main", None
        return ("evidence", None) if len(below) == 2 and below[0] == "objects" else None
    if kind == "leg":
        if len(parts) == 1:
            if name in LEG_MAIN:
                return "main", None
            if name in ("RUNLOG.md", "STOP") or name.endswith(RAW_SUFFIXES):
                return "evidence", None
            return None
        top = parts[0]
        if top in ("quarantine", "archive"):
            return "evidence", None
        if top == "items":
            return ("main", None) if len(parts) == 2 and name.endswith(".json") else None
        if top == "a4":
            if len(parts) != 2:
                return None
            if name.endswith(".json"):
                return "main", None
            return ("evidence", None) if name.endswith(RAW_SUFFIXES + (".jsonl",)) else None
        if len(parts) == 2:                                               # a session directory's file
            if BARRIER_RE.match(name) or CONTROL_RE.search(name):
                return "evidence", None
            if name.endswith((".manifest.json", ".json", ".jsonl")):
                return "main", None
            return ("evidence", None) if name.endswith(RAW_SUFFIXES) else None
        if len(parts) == 3 and parts[1] == "p426_dnf" and name.endswith(".json"):
            return "main", None
        return None
    if kind == "run":
        top = parts[0]
        if top in PRIVATE_RUN_DIRS:
            return "excluded", "private_state"
        if top == "grading-private" and len(parts) >= 2:
            if name.endswith((".json", ".diff", ".patch")):
                return "main", None
            return ("evidence", None) if name.endswith((".log", ".txt", ".out", ".err")) else None
        if top == "cfg" and (rel == "cfg/opencode/opencode.json" or (len(parts) == 4 and parts[:3] == ["cfg", "opencode", "plugins"]
                                                                       and name.endswith(".js"))):
            return "evidence", None
        return None
    if kind == "evidence":
        return ("evidence", None) if name.endswith(EVIDENCE_SUFFIXES + (".xml",)) else None       # flat, or in a per-item directory
    return None


def _in_final_tree(kind, rel):
    """True for a path BELOW a `*.final_tree` directory (the tree directory itself is not inside it)."""
    return any(seg.endswith(".final_tree") for seg in rel.split("/")[:-1])


# -------------------------------------------------------------------------------------------- reading without following links
def _read_regular(path):
    """The bytes of a regular file, opened without following a symlink; anything else is a HarvestError."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise HarvestError(f"{Path(path).name}: cannot be read as a regular file ({type(exc).__name__})") from None
    try:
        if not statmod.S_ISREG(os.fstat(fd).st_mode):
            raise HarvestError(f"{Path(path).name}: not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as f:
            return f.read()
    finally:
        os.close(fd)


def _stream_sha(path):
    h = hashlib.sha256()
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise HarvestError(f"{Path(path).name}: cannot be hashed ({type(exc).__name__})") from None
    try:
        with os.fdopen(fd, "rb", closefd=False) as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    finally:
        os.close(fd)
    return h.hexdigest()


def _walk(base):
    """[(rel posix, mode, absolute path)] of everything below `base`; a symlink is listed, never descended into."""
    out = []
    stack = [(Path(base), "")]
    while stack:
        directory, prefix = stack.pop()
        with os.scandir(directory) as it:
            for e in sorted(it, key=lambda x: x.name):
                rel = prefix + e.name
                mode = e.stat(follow_symlinks=False).st_mode
                if statmod.S_ISDIR(mode):
                    stack.append((Path(e.path), rel + "/"))
                else:
                    out.append((rel, mode, Path(e.path)))
    return sorted(out)


def _plain_dir(path):
    try:
        return statmod.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


# -------------------------------------------------------------------------------------------- the secret / email / scrub gate
def _emails(text):
    """Email-shaped addresses of `text` (anchored on `@`, bounded scans: linear on long lines)."""
    found, at = [], text.find("@")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._%+-")
    while at != -1:
        i = at
        while i > 0 and at - i < 64 and text[i - 1] in allowed:
            i -= 1
        m = _DOMAIN.match(text, at + 1)
        if i < at and m:
            found.append(text[i:m.end()])
        at = text.find("@", at + 1)
    return found


_DOMAIN = re.compile(r"[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,8}\.[A-Za-z]{2,}")


def _operator_domains(emails):
    return {e.rsplit("@", 1)[1].lower() for e in emails if "@" in e}


def _is_operator(addr, operator, domains):
    lowered = addr.lower()
    if lowered in operator:
        return True
    domain = lowered.rsplit("@", 1)[1]
    return any(domain == d or domain.endswith("." + d) for d in domains)


FOREIGN_KIND = "email"                          # a `main`-bound file carrying a non-reserved address (spec 16.8, after 3f)
RESERVED_DOMAINS = ("example.com", "example.net", "example.org", "localhost")
RESERVED_TLDS = ("example", "test", "invalid", "localhost")


def _is_reserved(addr):
    """RFC 2606 reserved names: `example.com` / `.net` / `.org` (and their subdomains), `*.example`, `*.test`, `*.invalid`,
    `localhost`."""
    domain = addr.lower().rsplit("@", 1)[1]
    return (any(domain == d or domain.endswith("." + d) for d in RESERVED_DOMAINS) or domain.rsplit(".", 1)[-1] in RESERVED_TLDS)


class Gate:
    """The refusal scan of one harvest: credential formats and exact values over the original AND the scrubbed bytes, the operator's
    address / domain, the P437 scrub. It never returns, prints or hashes a credential value: findings are pattern names."""

    def __init__(self, scrub, secrets):
        from bench import p426_secrets
        self.sec, self.scrub = p426_secrets, scrub
        self.secrets = dict(secrets or {})
        self.operator = {str(e).lower() for e in scrub.emails}
        self.domains = _operator_domains(self.operator)
        self.foreign = {}                       # address -> sorted sources
        self.lossy = set()                      # sources decoded with surrogateescape (not valid UTF-8)

    def _scan(self, text, kinds, addrs):
        for f in self.sec.scan(text):
            kinds.add(f.kind)
        for f in self.sec.exact_hits(text, self.secrets):
            kinds.add(f.kind)
        for a in _emails(text):
            addrs.add(a)

    def check(self, source, data, dest=None):
        """(scrubbed bytes, sorted refusal kinds). Foreign addresses are recorded under `source`; in a file bound for `main`
        (`dest == "main"`) a foreign address other than an RFC 2606 reserved name is a refusal kind (a public `main` carries no
        address), in an `evidence` file it goes to the review list."""
        kinds, addrs = set(), set()
        try:
            text, errors = data.decode("utf-8"), "strict"
        except UnicodeDecodeError:                 # not valid UTF-8: scrubbed and scanned through surrogateescape, recorded lossy
            text, errors = data.decode("utf-8", "surrogateescape"), "surrogateescape"
            self.lossy.add(source)
        self._scan(text, kinds, addrs)
        out = self.scrub.text(text)
        scrubbed = data if out == text else out.encode("utf-8", errors)
        if out != text:
            self._scan(out, kinds, addrs)
        if errors != "strict" and any(m and m in scrubbed for m in self.scrub.raw_markers()):      # what the scrub could not remove
            kinds.add("pii_marker")
        for a in addrs:
            if _is_operator(a, self.operator, self.domains):
                kinds.add(OPERATOR_KIND)
            elif dest == "main":
                if not _is_reserved(a):
                    kinds.add(FOREIGN_KIND)
            else:
                self.foreign.setdefault(a, set()).add(source)
        return scrubbed, sorted(kinds)

    def review_emails(self):
        return [dict(address=a, sources=sorted(s)) for a, s in sorted(self.foreign.items())]


def _problem_text(problems, limit=3000):
    text = "; ".join(problems)
    return text if len(text) <= limit else text[:limit] + f"; … ({len(problems)} problems)"


# -------------------------------------------------------------------------------------------- the inventory
class Entry:
    """One inventoried file: its typed source, where it lives, its destination and published path."""

    def __init__(self, source, path, kind, rel, dest, reason=None, link=None, data=None):
        self.source, self.path, self.kind, self.rel = source, Path(path) if path else None, kind, rel
        self.dest, self.reason, self.link, self.data = dest, reason, link, data
        self.sha = self.published = self.published_sha = self.compression = self.lossy = None

    def record(self):
        return dict(source=self.source, sha256=self.sha, destination=self.dest, published=self.published,
                    published_sha256=self.published_sha, compression=self.compression, exclusion_reason=self.reason,
                    **({"link_target": self.link} if self.link is not None else {}),
                    **({"lossy_decode": self.lossy} if self.lossy else {}))


def _manifest_runs(leg_root, workdir, problems):
    """[(run id, run dir or None, evidence dir or None)] of every probe invocation this attempt's manifests name."""
    runs, seen = [], set()
    for rel, mode, path in _walk(leg_root):
        if not rel.endswith(".manifest.json") or not statmod.S_ISREG(mode):
            continue
        try:
            run_id = json.loads(_read_regular(path)).get("run_id")
        except (ValueError, AttributeError):
            problems.append(f"{rel}: not a JSON object")
            continue
        if run_id is None or run_id in seen:
            continue
        if not isinstance(run_id, str) or not RUN_ID_RE.match(run_id):
            problems.append(f"{rel}: run_id is not a probe run id")
            continue
        seen.add(run_id)
        run_dirs = [p for p in sorted(workdir.glob(f"opencode-probe*/run-{run_id}")) if _plain_dir(p)]
        ev_dirs = [p for p in sorted(workdir.glob(f"opencode_transcripts/*/*.{run_id}")) if _plain_dir(p)]
        if not run_dirs and not ev_dirs:
            problems.append(f"{rel}: its run id {run_id} resolves to no run or evidence directory")
        if len(run_dirs) > 1 or len(ev_dirs) > 1:
            problems.append(f"{rel}: its run id {run_id} resolves to more than one "
                            f"{'run' if len(run_dirs) > 1 else 'evidence'} directory")
        runs.append((run_id, run_dirs, ev_dirs))
    return runs


def _inventory(leg_root, workdir, problems):
    """Every file of the leg root and of each run / evidence directory the manifests name -> {source: Entry}."""
    inv, roots = {}, {}

    def add(kind, label, base):
        roots[(kind, label)] = Path(base)
        for rel, mode, path in _walk(base):
            source = f"{kind}:{rel}" if kind == "leg" else f"{kind}:{label}/{rel}"
            if statmod.S_ISLNK(mode):
                if _in_final_tree(kind, rel):
                    inv[source] = Entry(source, path, kind, rel, "excluded", "symlink", link=os.readlink(path))
                else:
                    problems.append(f"{source}: a symlink outside a final tree (never followed)")
                continue
            if not statmod.S_ISREG(mode):
                problems.append(f"{source}: not a regular file")
                continue
            rule = classify(kind, rel)
            if rule is None:
                problems.append(f"{source}: no harvest rule matches this file")
                continue
            inv[source] = Entry(source, path, kind, rel, rule[0], rule[1])

    add("leg", "", leg_root)
    for run_id, run_dirs, ev_dirs in _manifest_runs(leg_root, workdir, problems):
        for d in run_dirs:
            add("run", run_id, d)
        for d in ev_dirs:
            add("evidence", run_id, d)
    # the sequencer's launch log of this attempt: `<out-base>/logs/<attempt>.stdout` (outside the out-root the chain creates fresh)
    launch = Path(leg_root).parent / "logs" / (Path(leg_root).name + ".stdout")
    if os.path.lexists(launch):
        source = f"record:logs/{Path(leg_root).name}.stdout"
        if not statmod.S_ISREG(os.lstat(launch).st_mode):
            problems.append(f"{source}: the launch log is a link or not a regular file (never followed)")
        else:
            inv[source] = Entry(source, launch, "launch", "logs/launch.stdout", "evidence")
    return inv, roots


def _load_json(entry, what=None):
    try:
        return json.loads(_read_regular(entry.path))
    except ValueError:
        raise HarvestError(f"{what or entry.source}: not valid JSON") from None


def _expand(value, workdir):
    s = str(value)
    if s == PORTABLE_ROOT or s.startswith(PORTABLE_ROOT + "/"):
        return os.path.normpath(str(workdir) + s[len(PORTABLE_ROOT):])
    return None


def _locate(path, roots):
    """The inventory source name of an absolute path inside one of the inventoried roots, else None."""
    for (kind, label), base in roots.items():
        b = os.path.normpath(str(base))
        if path == b or not path.startswith(b + os.sep):
            continue
        rel = path[len(b) + 1:].replace(os.sep, "/")
        return f"{kind}:{rel}" if kind == "leg" else f"{kind}:{label}/{rel}"
    return None


def _ref(value, what, workdir, roots, inv, problems, sha=None):
    """Resolve one `$STACK_WORKDIR/…` reference to an inventory entry (it must exist, lie in the roots, be harvested)."""
    path = _expand(value, workdir)
    if path is None:
        problems.append(f"{what}: reference {Path(str(value)).name} is not a $STACK_WORKDIR path")
        return None
    source = _locate(path, roots)
    if source is None:
        problems.append(f"{what}: reference {Path(path).name} lies outside the inventoried roots")
        return None
    entry = inv.get(source)
    if entry is None:
        problems.append(f"{what}: referenced file {source} is missing")
        return None
    if entry.dest == "excluded":
        problems.append(f"{what}: referenced file {source} is excluded ({entry.reason})")
        return None
    if sha is not None:
        entry.data = entry.data if entry.data is not None else _read_regular(entry.path)
        if _sha(entry.data) != sha:
            problems.append(f"{what}: {source} changed after its record was written (sha256 differs)")
    return entry


def _artifact_refs(doc, found=None):
    """Every `{path: "$STACK_WORKDIR/…", sha256: …}` shaped reference inside a row / manifest / sidecar."""
    found = [] if found is None else found
    if isinstance(doc, dict):
        if isinstance(doc.get("path"), str) and doc["path"].startswith(PORTABLE_ROOT) and "sha256" in doc:
            found.append((doc["path"], doc["sha256"]))
        for v in doc.values():
            _artifact_refs(v, found)
    elif isinstance(doc, list):
        for v in doc:
            _artifact_refs(v, found)
    return found


def _check_row(row, what, workdir, roots, inv, problems):
    if not isinstance(row, dict):
        problems.append(f"{what}: a row is not a JSON object")
        return
    digests = row.get("evidence_sha256") if isinstance(row.get("evidence_sha256"), dict) else {}
    for key, name in ROW_REFS:
        if isinstance(row.get(key), str):
            _ref(row[key], f"{what} {key}", workdir, roots, inv, problems, sha=digests.get(name))
    tree = row.get("final_tree")
    if isinstance(tree, dict) and isinstance(tree.get("manifest"), str):
        entry = _ref(tree["manifest"], f"{what} final_tree", workdir, roots, inv, problems, sha=tree.get("manifest_sha256"))
        if entry is not None:
            try:
                files = json.loads(entry.data).get("files", {})
            except (ValueError, AttributeError):
                problems.append(f"{what} final_tree: {entry.source} is not a final-tree manifest")
                files = {}
            base = entry.source.rsplit("/", 1)[0]
            for rel, digest in files.items():
                obj = inv.get(f"{base}/objects/{digest}")
                if obj is None or obj.dest == "excluded":
                    problems.append(f"{what} final_tree: object of {rel} is missing")
    for path, digest in _artifact_refs({k: v for k, v in row.items() if k != "final_tree"}):
        if digest is not None:
            _ref(path, f"{what} artifact", workdir, roots, inv, problems, sha=digest)


def _check_references(leg_root, state, chain, inv, roots, workdir, problems):
    """Transitive references: chain.json → rows / manifests / item records / DNF sidecars → transcripts, sidecars, final trees,
    grader reports, and every object they name."""
    from bench import chain_rows

    def need(rel, what):
        entry = inv.get(f"leg:{rel}")
        if entry is None:
            problems.append(f"{what}: referenced file {rel} is missing")
        return entry

    for inv_rec in ((chain.get("progress") or {}).get("invocations") or []):
        if inv_rec.get("status") != "validated":
            continue
        for key in ("file", "manifest"):
            if isinstance(inv_rec.get(key), str):
                need(inv_rec[key], f"chain.json invocation {key}")
    sched_sha = chain.get("schedule_sha256")
    if sched_sha:
        sched = need("schedule.json", "chain.json schedule_sha256")
        if sched is not None:
            from bench import schedules
            if schedules.schedule_sha256(_load_json(sched)) != sched_sha:
                problems.append("schedule.json: not the schedule chain.json froze (schedule_sha256 differs)")
    ready_hashes = {}
    for led in chain.get("p426_ledger") or []:
        sf = chain_rows.slot_file(led.get("slot"))
        if led.get("kind") in ("row", "dnf"):                    # every ledger entry, a DNF included, has its ready record
            ready = need(f"items/{sf}.ready.json", f"ledger {sf}")
            item = need(f"items/{sf}.json" if led.get("kind") == "row" else f"items/{sf}.dnf.json", f"ledger {sf}")
            if ready is not None:                                # the self-hash itself is checked with every immutable record below
                ready_hashes[sf] = _load_json(ready).get("sha256")
            if item is not None:
                want = ready_hashes.get(sf)                      # §4.5: `ready_sha256` is the ready record's self-hash, one value
                if want is not None and _load_json(item).get("ready_sha256") != want:
                    problems.append(f"{item.source}: ready_sha256 is not the ready record's sha256")
    for dnf in chain.get("p426_dnf") or []:
        sf = chain_rows.slot_file(dnf.get("slot"))
        if isinstance(dnf.get("item_record"), str):
            need(dnf["item_record"], f"p426_dnf {sf} item_record")
        sidecars = [e for s, e in inv.items() if s.startswith("leg:") and s.endswith(f"/p426_dnf/{sf}.json")]
        if not sidecars:
            problems.append(f"p426_dnf {sf}: its sidecar is missing")
        elif _load_json(sidecars[0]) != dnf:
            problems.append(f"p426_dnf {sf}: the chain.json entry differs from its sidecar")
    for source, entry in sorted(inv.items()):
        if entry.dest == "excluded" or entry.kind != "leg":
            continue
        rel = entry.rel
        if _is_immutable(rel):
            p = _immutable_problem(source, _load_json(entry))
            if p:
                problems.append(p)
        if rel.endswith(".manifest.json") or "/p426_dnf/" in rel:
            for path, digest in _artifact_refs(_load_json(entry)):
                if digest is not None:
                    _ref(path, source, workdir, roots, inv, problems, sha=digest)
        elif rel.endswith(".jsonl") and "/" in rel and not rel.startswith(("quarantine/", "archive/", "a4/")):
            entry.data = _read_regular(entry.path)
            for n, line in enumerate(entry.data.decode("utf-8", "replace").splitlines(), 1):
                if line.strip():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        problems.append(f"{source}: line {n} is not JSON")
                        continue
                    _check_row(row, f"{source}:{n}", workdir, roots, inv, problems)
            entry.data = None


def _check_barrier(state, chain, inv, problems):
    """Barrier and control files against the leg state: a `.stop` per `invalidate`, every `.go` answers a `.ready`, a VALID leg
    answered every `.ready` and `.done`; a NOT_STARTED leg launched nothing."""
    groups = {}
    for source, entry in inv.items():
        if entry.kind != "leg":
            continue
        m = BARRIER_RE.match(entry.rel)
        if m:
            groups.setdefault((m["base"], int(m["k"])), set()).add(m["kind"])
    if state == "NOT_STARTED":
        stray = sorted(s for s, e in inv.items() if e.kind == "leg" and (BARRIER_RE.match(e.rel) or e.rel.endswith((".jsonl", ".manifest.json"))
                                                                      and "/" in e.rel))
        if stray:
            problems.append(f"NOT_STARTED leg carries launch artifacts: {', '.join(stray[:5])}")
        return
    stops = 0
    for (base, k), kinds in sorted(groups.items()):
        tag = f"{base}.item{k}"
        if "go" in kinds and "ready" not in kinds:
            problems.append(f"{tag}: a .go without its .ready")
        if "continue" in kinds and "done" not in kinds:
            problems.append(f"{tag}: a .continue without its .done")
        if "done" in kinds and "ready" not in kinds:
            problems.append(f"{tag}: a .done without its .ready")
        if "stop" in kinds:
            stops += 1
            if not kinds & {"ready", "done"}:
                problems.append(f"{tag}: a .stop that answers nothing")
        if state in ("VALID", "VALID_WITH_DNF"):
            if "ready" in kinds and "go" not in kinds:
                problems.append(f"{tag}: a .ready never answered with .go in a {state} leg")
            if "done" in kinds and "continue" not in kinds:
                problems.append(f"{tag}: a .done never answered with .continue in a {state} leg")
    invalidated = len(chain.get("p426_invalid") or [])
    if stops != invalidated:
        problems.append(f"barrier: {stops} .stop file(s) for {invalidated} invalidate record(s) in chain.json (one .stop per invalidate)")


def _log_slices(leg_root, state, inv, worktree, problems):
    """`log_bounds.json` (finalized) → [Entry] of the leg's byte range of each server log; the live log is checked against the
    recorded device / inode / size and sliced."""
    entry = inv.get("leg:log_bounds.json")
    if entry is None:
        if state in ("VALID", "VALID_WITH_DNF"):
            problems.append("log_bounds.json: missing (a VALID leg's server-log range is required)")
        return []
    doc = _load_json(entry)
    files = doc.get("files")
    if not isinstance(files, list):
        problems.append("log_bounds.json: has no files list")
        return []
    if not doc.get("finalized"):                 # null / false / empty: the two-phase record was never finalized
        problems.append("log_bounds.json: not finalized (the chain never closed the leg's byte ranges); the operator decides")
        return []
    if doc.get("problems"):
        problems.append("log_bounds.json: records problems (truncated / replaced / vanished log); the operator decides")
        return []
    out = []
    for f in files:
        name = Path(str(f.get("path"))).name
        start, end = f.get("offset_start"), f.get("offset_end")
        if not isinstance(start, int) or not isinstance(end, int) or end < start or start < 0 or not str(f.get("path")).startswith("<WT>/logs/") \
                or name in ("", ".", ".."):
            problems.append(f"log_bounds.json: {name or 'an entry'} has no usable byte range")
            continue
        if worktree is None:
            problems.append("log_bounds.json: the arm's worktree cannot be resolved (pass --worktree); the server-log range cannot be read")
            return []
        path = Path(worktree) / "logs" / name
        try:
            st = os.lstat(path)
        except OSError:
            problems.append(f"{name}: the server log is gone")
            continue
        if not statmod.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (f.get("device"), f.get("inode")) or st.st_size < end:
            problems.append(f"{name}: the live log is not the file log_bounds.json recorded (replaced, truncated or a link)")
            continue
        source = f"log:{name}:{start}-{end}"
        data = _read_regular(path)[start:end]
        e = Entry(source, path, "log", f"logs/{name}.{start}-{end}.log", "evidence", data=data)
        out.append(e)
    return out


# -------------------------------------------------------------------------------------------- staging, publication, retry
def _remove_tree(path, parent):
    """Delete one of THIS attempt's destinations / stages (a plain directory directly below `parent`); never a link, never above."""
    path = Path(path)
    if not os.path.lexists(path):
        return
    if path.parent != Path(parent) or os.path.islink(path):
        raise HarvestError(f"{path.name}: refusing to delete a path that is not this attempt's own directory")
    shutil.rmtree(path)


def _prune_empty(path, stop):
    path, stop = Path(path), Path(stop)
    while path != stop and stop in path.parents:
        try:
            path.rmdir()
        except OSError:
            return
        path = path.parent


def _write_stage(base, rel, data):
    target = Path(base) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _verified(doc, main_dest, main_root, evidence_stage, name):
    """A committed destination: `HARVEST.json` self-hashed, naming this attempt, and every file it maps present with its sha256."""
    try:
        if (not isinstance(doc, dict) or doc.get("sha256") != _canon_sha(doc) or f"{doc.get('leg')}.a{doc.get('attempt')}" != name):
            return False
        for f in doc["files"]:
            if f.get("published"):
                base = main_root if f["destination"] == "main" else evidence_stage
                p = Path(base) / f["published"]
                if os.path.islink(p) or not p.is_file() or _sha(p.read_bytes()) != f["published_sha256"]:
                    return False
        return True
    except (KeyError, TypeError, OSError):
        return False


def harvest_wave2(leg_root, *, main_root, evidence_stage, scrub, secrets=None, worktree=None, workdir=None, absent_sources=()):
    """Harvest one attempt (B2 spec 11): `HARVEST.json` (a dict) or a `HarvestError` with nothing published. `secrets` = the credential
    values (`p426_secrets.credential_values`, in memory only); `worktree` = the arm worktree whose `logs/` hold the server logs;
    `workdir` = `$STACK_WORKDIR` (default: `scrub.workdir`)."""
    leg_root, main_root, evidence_stage = Path(leg_root), Path(main_root), Path(evidence_stage)
    workdir = Path(workdir) if workdir is not None else Path(scrub.workdir)
    if not _plain_dir(leg_root):
        raise HarvestError(f"--leg-root {leg_root.name} is not a directory")
    m = ATTEMPT_RE.match(leg_root.name)
    if not m:
        raise HarvestError(f"--leg-root {leg_root.name} is not an attempt root <leg>.a<n>")
    name = leg_root.name
    main_dest, ev_dest = main_root / WAVE2 / name, evidence_stage / WAVE2 / name
    main_stage, ev_stage = main_dest.with_name(name + ".stage"), ev_dest.with_name(name + ".stage")
    # a committed destination is done (idempotent); anything else of THIS attempt is incomplete and replaced below
    committed = main_dest / "HARVEST.json"
    if committed.is_file() and not os.path.islink(committed):
        try:
            doc = json.loads(committed.read_bytes())
        except ValueError:
            doc = None
        if _verified(doc, main_dest, main_root, evidence_stage, name):
            return doc

    problems = []
    leg_entry = None
    if not os.path.lexists(leg_root / "leg.json"):
        raise HarvestError("leg.json: missing (the sequencer's leg record is the leg's state)")
    inv, roots = _inventory(leg_root, workdir, problems)
    leg_entry = inv.get("leg:leg.json")
    if leg_entry is None or leg_entry.dest != "main":
        raise HarvestError(_problem_text(problems + ["leg.json: not a regular file"]))
    leg = _load_json(leg_entry)
    state = leg.get("state") if isinstance(leg, dict) else None
    if state not in LEG_STATES:
        raise HarvestError(f"leg.json: state {state!r} is not one of {', '.join(LEG_STATES)}")
    if f"{leg.get('leg')}.a{leg.get('attempt')}" != name:
        raise HarvestError(f"leg.json: names attempt {leg.get('leg')}.a{leg.get('attempt')}, not the leg root {name}")
    chain = {}
    if state != "NOT_STARTED":
        chain_entry = inv.get("leg:chain.json")
        if chain_entry is None:
            problems.append(f"chain.json: missing in a {state} leg")
        else:
            chain = _load_json(chain_entry)
    if state in ("VALID", "VALID_WITH_DNF") and "leg:watch.jsonl" not in inv:
        problems.append(f"watch.jsonl: missing in a {state} leg (the watcher's journal is the leg's speed receipt)")
    _check_references(leg_root, state, chain, inv, roots, workdir, problems)
    _check_barrier(state, chain, inv, problems)
    slices = _log_slices(leg_root, state, inv, worktree, problems)
    for e in slices:
        inv[e.source] = e
    if problems:
        raise HarvestError(_problem_text(problems))

    gate = Gate(scrub, secrets)
    entries = sorted(inv.values(), key=lambda e: e.source)
    stages = {"main": (main_root, main_stage), "evidence": (evidence_stage, ev_stage)}
    for _, stage in stages.values():                     # a stage of THIS attempt left by an interrupted run is never reused
        _remove_tree(stage, stage.parent)
    quarantine, written = [], []
    try:
        for e in entries:
            if e.dest == "excluded":
                e.sha = None if e.link is not None else _stream_sha(e.path)
                if e.link is not None:
                    e.link = scrub.text(e.link)
                continue
            data = e.data if e.data is not None else _read_regular(e.path)
            e.data = None
            e.sha = _sha(data)
            scrubbed, kinds = gate.check(e.source, data, e.dest)
            if e.source in gate.lossy:
                e.lossy = "surrogateescape"                  # decoded lossily for the scrub and the scan (spec 11.3)
            if kinds:                                    # quarantined: not staged, listed by path and pattern name only
                quarantine.append(f"{e.source}: {', '.join(kinds)}")
                continue
            if e.dest == "main":
                if scrubbed != data:
                    problems.append(f"{e.source}: the scrub would change this main record (not portable at creation)")
                    continue
                problems += [f"{e.source}: PII: {v.why}" for v in piicheck.violations(data.decode("utf-8", "replace"), path=e.source, line=1)]
                published = data
            else:
                published = scrubbed
                if len(published) > COMPRESS_BYTES:
                    published, e.compression = lzma.compress(published), "xz"
            if len(published) > MAX_FILE_BYTES:
                problems.append(f"{e.source}: {len(published)} bytes > {MAX_FILE_BYTES}")
                continue
            sub = _published_sub(e) + (".xz" if e.compression else "")
            e.published, e.published_sha = (WAVE2 / name / sub).as_posix(), _sha(published)
            if not (problems or quarantine):
                _write_stage(stages[e.dest][1], sub, published)
                written.append((e, stages[e.dest][1] / sub))
        if quarantine or problems:
            raise HarvestError(_problem_text([f"quarantined {q}" for q in quarantine] + problems))
        paths = [e.published for e in entries if e.published]
        if len(paths) != len(set(paths)):
            raise HarvestError("two files map to one published path")
        review_emails = gate.review_emails()
        doc = dict(leg=leg["leg"], attempt=leg["attempt"], state=state, files=[e.record() for e in entries],
                   review=dict(emails_count=len(review_emails), emails_file=f"{PORTABLE_ROOT}/p426/review/{name}.emails.json",
                               absent_secret_sources=sorted(absent_sources)),
                   created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        doc["sha256"] = _canon_sha(doc)
        body = (json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        scrubbed, kinds = gate.check("HARVEST.json", body, "main")
        if kinds or scrubbed != body:
            raise HarvestError("HARVEST.json: quarantined or not portable" + (f" ({', '.join(kinds)})" if kinds else ""))
        _write_stage(main_stage, "HARVEST.json", body)
        for e, staged in written:                        # the staged bytes are verified before anything becomes visible
            if _sha(staged.read_bytes()) != e.published_sha:
                raise HarvestError(f"{e.source}: its staged copy does not verify")
    except BaseException:
        for _, stage in stages.values():
            _remove_tree(stage, stage.parent)
            _prune_empty(stage.parent, stages["main"][0] if stage is main_stage else evidence_stage)
        raise
    # publish: this attempt's incomplete destinations go, then evidence, then `main`: the rename of the `main` destination that
    # carries HARVEST.json is the single commit point
    # the other addresses (spec 11.3 / 16.8) go to a local review file for the operator, never published
    review = workdir / "p426" / "review" / f"{name}.emails.json"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(json.dumps(review_emails, indent=1, sort_keys=True) + "\n")
    for dest in (ev_dest, main_dest):
        _remove_tree(dest, dest.parent)
    if ev_stage.exists():
        _rename(ev_stage, ev_dest)
    _rename(main_stage, main_dest)
    return doc


def _published_sub(entry):
    """The path of a file below its attempt's destination: the leg-root path as is; `run/<id>/…`, `evidence/<id>/…`, `logs/…`."""
    if entry.kind in ("leg", "log", "launch"):
        return entry.rel
    return f"{entry.kind}/{entry.source.split(':', 1)[1].split('/', 1)[0]}/{entry.rel}"


# -------------------------------------------------------------------------------------------- records: the pair dossier, the run files
def _publish_records(paths, *, main_root, scrub, sub, require_self_hash, may_advance=(), exempt=()):
    """Publish single record files to `<main>/benchmark/results/p426/wave2/<sub>/<name>`: every file is validated first (a regular
    file, never a link; self-hash; the scrub is byte-identity; no credential format, no operator address; no PII), staged beside its
    destination, verified, then renamed into place. An existing destination with the same bytes is done; a different one is
    refused unless its name is in `may_advance` (a state file the sequencer replaces atomically)."""
    gate = Gate(scrub, scrub.secrets)                        # the same exact in-memory credential values as the leg harvest
    main_root = Path(main_root)
    pending, published, problems = [], [], []
    for p in paths:
        p = Path(p)
        try:
            data = _read_regular(p)
        except HarvestError as exc:
            problems.append(str(exc) if p.name in str(exc) else f"{p.name}: {exc}")
            continue
        rel = (WAVE2 / sub / p.name).as_posix()
        try:
            doc = json.loads(data)
        except ValueError:
            doc = None
        if require_self_hash and p.name not in exempt:           # an immutable record: a present, valid self-hash
            bad = _immutable_problem(p.name, doc)
            if bad:
                problems.append(bad)
        elif isinstance(doc, dict):
            bad = _self_hash_problem(p.name, doc)
            if bad:
                problems.append(bad)
        scrubbed, kinds = gate.check(f"record:{p.name}", data, "main")
        if kinds:
            problems.append(f"quarantined {p.name}: {', '.join(kinds)}")
            continue
        if scrubbed != data:
            problems.append(f"{p.name}: the scrub would change this record (not portable at creation)")
            continue
        problems += [f"{p.name}: PII: {v.why}" for v in piicheck.violations(data.decode("utf-8", "replace"), path=rel, line=1)]
        dest = main_root / rel
        if os.path.lexists(dest):
            same = os.path.isfile(dest) and not os.path.islink(dest) and dest.read_bytes() == data
            if not same and p.name not in may_advance:
                problems.append(f"{rel} exists and differs from {p.name} (published records are immutable)")
                continue
            if not same:
                pending.append((p, data, dest))
        else:
            pending.append((p, data, dest))
        published.append(dict(source=f"record:{p.name}", destination=rel, sha256=_sha(data)))
    if problems:
        raise HarvestError(_problem_text(problems))
    staged = []
    try:
        for p, data, dest in pending:
            dest.parent.mkdir(parents=True, exist_ok=True)
            stage = dest.with_name(dest.name + ".stage")
            if os.path.lexists(stage):                   # any type (a link included): never followed, never reused
                raise HarvestError(f"{stage.name}: a stage path already exists (never followed or reused; the operator removes it)")
            try:
                fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
            except OSError as exc:
                raise HarvestError(f"{stage.name}: the stage cannot be created exclusively ({type(exc).__name__})") from None
            staged.append((stage, dest))                 # ours from here on: removed again if anything below fails
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            if _sha(_read_regular(stage)) != _sha(data):
                raise HarvestError(f"{p.name}: its staged copy does not verify")
    except BaseException:
        for stage, _dest in staged:
            try:
                os.unlink(stage)
            except OSError:
                pass
        raise
    for stage, dest in staged:
        os.replace(stage, dest) if dest.exists() else _rename(stage, dest)
        if not statmod.S_ISREG(os.lstat(dest).st_mode):
            raise HarvestError(f"{dest.name}: the published destination is not a regular file (a link or something else)")
    return dict(published=published, harvest_sha256=None)


def load_credentials(*, environ, home, env_files=()) -> dict:
    """The exact in-memory credential values of the box (machine config, `<WT>/.env` files, environment, token files): what the
    leg harvest and every publication scan for. An unreadable or unparseable source is a `HarvestError`, never an unscanned run."""
    from bench import p426_secrets
    home = Path(home)
    config = Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / "mlx_local_stack" / "config.sh"
    try:
        return p426_secrets.credential_values(home=home, config_path=config, environ=environ, env_files=list(env_files))
    except p426_secrets.SecretsError as exc:
        raise HarvestError(str(exc)) from None


def publish_dossier(path, *, main_root, evidence_stage, scrub):
    """Publish one pair dossier (a self-hashed record) to `main` `wave2/pairs/`, staged and verified like a leg's `main` destination.
    Returns `{published: [{source, destination, sha256}], harvest_sha256}`; a dossier has no HARVEST.json, so `harvest_sha256` is
    None. `evidence_stage` is part of the pinned signature; a dossier has no evidence side."""
    return _publish_records([path], main_root=main_root, scrub=scrub, sub="pairs", require_self_hash=True)


def publish_run_files(paths, *, main_root, scrub):
    """Publish the run-level records (the frozen-record directory's files, the sequencer's `sequence.json`) to `main` `wave2/run/`.
    Every frozen record is immutable and needs a valid self-hash; `sequence.json` (a state file) is the one exemption and is
    replaced atomically as it advances. The credential values are `scrub.secrets`, as for the leg harvest."""
    return _publish_records(paths, main_root=main_root, scrub=scrub, sub="run", require_self_hash=True,
                            may_advance=("sequence.json",), exempt=("sequence.json",))


# -------------------------------------------------------------------------------------------- the CLI
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise HarvestError(message)


def _arm_of(leg):
    """The arm whose worktree served a leg: `off` / `on` in the leg name; the rehearsal's negative legs by the §1 table."""
    if leg.endswith("rehearsal-mismatch"):
        return "on"
    if leg.endswith("rehearsal-kill"):
        return "off"
    m = re.search(r"-(off|on)(?:-|$)", leg)
    return m.group(1) if m else None


def leg_worktrees(leg_root, workdir):
    """({arm: worktree path}) from the frozen record the chain was launched with (`--frozen-record` in chain.json's argv: the v8 base
    beside an amendment, or the rehearsal manifest itself); {} when it cannot be read."""
    try:
        argv = json.loads((Path(leg_root) / "chain.json").read_bytes()).get("argv") or []
        rec = next((argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--frozen-record"), None)
        path = _expand(rec, workdir) if rec else None
        if path is None:
            return {}
        folder = Path(path).parent
        doc = {}
        for cand in (folder / "v8_base.json", Path(path)):
            if cand.is_file() and not cand.is_symlink():
                doc = json.loads(cand.read_bytes())
                if "off_worktree" in doc:
                    break
        out = {}
        for arm in ("off", "on"):
            wt = _expand(doc.get(f"{arm}_worktree"), workdir) if doc.get(f"{arm}_worktree") else None
            if wt:
                out[arm] = Path(wt)
        return out
    except (OSError, ValueError, AttributeError, IndexError, TypeError):
        return {}


def _parse(argv):
    ap = _Parser(prog="bench.p426_harvest", description="P426 Wave-2 harvest (B2 spec 11)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w2 = sub.add_parser("wave2", help="harvest one attempt's leg root")
    w2.add_argument("--leg-root", required=True)
    w2.add_argument("--main-root", required=True)
    w2.add_argument("--evidence-stage", required=True)
    w2.add_argument("--operator-email", action="append", default=[], help="the address the harvest refuses (repeatable)")
    w2.add_argument("--worktree", default=None, help="the arm worktree whose logs/ hold the server logs (default: from the frozen record)")
    w2.add_argument("--env-file", action="append", default=[], help="an extra <WT>/.env credential source (repeatable)")
    return ap.parse_args(argv)


def main(argv=None, *, environ=None, home=None):
    """`wave2` entry. A `HarvestError` prints one stderr line `REFUSED: <reason>` and exits 2, with nothing published."""
    environ = os.environ if environ is None else environ
    try:
        a = _parse(sys.argv[1:] if argv is None else argv)
        if not environ.get("STACK_WORKDIR"):
            raise HarvestError("STACK_WORKDIR is not set")
        from bench import p426_secrets
        workdir, home = Path(environ["STACK_WORKDIR"]), Path(home) if home is not None else Path.home()
        leg_root = Path(a.leg_root)
        if not _plain_dir(leg_root):
            raise HarvestError(f"--leg-root {leg_root.name} is not a directory")
        host = socket.gethostname()
        scrub = Scrub(workdir=workdir, repo=Path(a.main_root), home=home, user=getpass.getuser(),
                      hosts=tuple(sorted({host, host.split(".")[0]} - {""})), emails=tuple(a.operator_email))
        trees = leg_worktrees(leg_root, workdir)
        arm = _arm_of(leg_root.name.rsplit(".a", 1)[0])
        worktree = Path(a.worktree) if a.worktree else trees.get(arm)
        env_files = [Path(p) for p in a.env_file] + [t / ".env" for t in trees.values()
                                                       if (t / ".env").exists() or os.path.islink(t / ".env")]
        env_files = list(dict.fromkeys(env_files))
        config = Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / "mlx_local_stack" / "config.sh"
        try:
            values = p426_secrets.credential_values(home=home, config_path=config, environ=environ, env_files=env_files)
        except p426_secrets.SecretsError as exc:
            raise HarvestError(str(exc)) from None
        absent = p426_secrets.absent_sources(home=home, config_path=config, env_files=env_files)
        harvest_wave2(leg_root, main_root=a.main_root, evidence_stage=a.evidence_stage, scrub=scrub, secrets=values,
                      worktree=worktree, workdir=workdir, absent_sources=absent)
    except HarvestError as exc:
        print("REFUSED: " + " ".join(str(exc).split()), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: harvest I/O failure ({type(exc).__name__}: {exc.strerror or 'see the destination'}); nothing was committed",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
