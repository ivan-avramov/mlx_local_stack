"""Hermetic A7 panel world for the P613 step-3 tests.

Built on the step-1 / step-2 worlds (`bench.tests.p613.a7world.World` inside `bench.tests.p613s2.wave1world.Wave1World`, so
`p426_verify all` accepts it), with three additions:

* the per-item final trees carry real solution text (the manifest sha = sha256 of the text bytes) and every row carries
  `evidence_sha256.events` (the sha of a synthetic events file);
* an `evidence` commit (git plumbing, `git fast-import`) holds `…/<lang>__<item>.final_tree/objects/<sha>` and
  `…/<lang>__<item>.events.jsonl`, at the repository-relative paths the committed `evidence` branch uses (no checkout of it exists);
* a fake polyglot tree (`<lang>/exercises/practice/<name>/…`) + a fake `universe.json` whose `prepared` shas match it.

Layout under `base` (`A7Case.base`): `repo/` (git; results under `benchmark/results/p426/`), `evidence_src/`, `polyglot/`,
`universe.json`, `judges.json`, `B8.json`, `evidence_ref.txt`.
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from bench.tests.p613 import a7world
from bench.tests.p613.a7world import MODEL, attempt_name, dumps, sha_bytes, sha_text

BENCH_DIR = Path(__file__).resolve().parents[3]          # .../benchmark  (the cwd the repository's commands run from)

# ------------------------------------------------------------------------------------------------------------------ items
S1_SEL = ["python/alpha", "python/beta", "python/book-store", "go/two-fer", "go/eta", "go/zeta"]      # both pass, differ
S1_IDENT = ["python/gamma"]                                                                           # both pass, identical
S1_ONE = {"python/delta": "off", "go/theta": "on"}                                                   # only this arm passes
S1_NEITHER = ["python/epsilon"]
S1_REJECTED = ["go/psi"]                                                                              # both pass, differ; key rejected
S2_SEL = ["python/iota", "python/kappa", "python/mu", "python/nu", "go/xi", "go/omicron", "go/pi", "go/rho"]
S2_IDENT = ["python/sigma", "go/tau"]
S2_ONE = {"go/upsilon": "on"}
S2_NEITHER = ["go/phi"]

START = "def f(x):\n    # TODO\n    raise NotImplementedError\n"
OFF_SOLUTION = "def f(x):\n    return x + 1\n"
ON_SOLUTION = "def f(x):\n    total = x\n    return total + 1\n"
TEST_TEXT = "import sol\n\n\ndef test_f():\n    assert sol.f(1) == 2\n"
APPEND_ID = "python/book-store"
KNOWN = ("s1", "python/alpha")            # the known case: diff + tool counts asserted verbatim
KNOWN_TOOLS = {"off": {"edit": 2, "read": 3, "shell": 2, "write": 1}, "on": {"read": 1}}
DEFAULT_TOOLS = {"off": {"read": 2, "edit": 1}, "on": {"edit": 2, "read": 1, "shell": 1}}
MARKERS = {"text": "NARRATIVE-MARKER-", "ref": "REFERENCE-SOLUTION-MARKER"}
TS0 = 1793675141102


def ids_for(with_rejected=True):
    s1 = S1_SEL + S1_IDENT + list(S1_ONE) + S1_NEITHER + (S1_REJECTED if with_rejected else [])
    s2 = S2_SEL + S2_IDENT + list(S2_ONE) + S2_NEITHER
    order = lambda ids: sorted(ids, key=lambda r: (r.split("/")[0] != "python", ids.index(r)))     # python first (language runs)
    return {"s1": order(s1), "s2": order(s2)}


def rows_for(with_rejected=True):
    rows = {}
    for session, one, neither in (("s1", S1_ONE, S1_NEITHER), ("s2", S2_ONE, S2_NEITHER)):
        for arm in ("off", "on"):
            patch = rows.setdefault((arm, session), {})
            for rid, passing in one.items():
                patch[rid] = {"passed": passing == arm, "converged": True}
            for rid in neither:
                patch[rid] = {"passed": False, "converged": True}
    return rows


def identical_for():
    return {("s1", r) for r in S1_IDENT} | {("s2", r) for r in S2_IDENT}


def lang_name(rid):
    return rid.split("/", 1)


def sol_name(rid):
    return "sol.py" if rid.startswith("python/") else "sol.go"


def test_name(rid):
    return "sol_test.py" if rid.startswith("python/") else "sol_test.go"


def instructions_of(rid):
    return f"# Instructions\n\nImplement {lang_name(rid)[1]}. INSTR-MARK-{lang_name(rid)[1]}\n"


def append_of(rid):
    return f"APPEND-MARK-{lang_name(rid)[1]}\n"


def expected_diff(start, final, rel):
    """The contract's unified diff: difflib, 3 lines of context, `a/<rel>` / `b/<rel>`."""
    return "".join(difflib.unified_diff(start.splitlines(keepends=True), final.splitlines(keepends=True),
                                        fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3))


class World3(a7world.World):
    """a7world.World with solution text, events and `evidence_sha256.events` per row."""

    def __init__(self, base, *, texts=None, tools=None, extra=None, **kw):
        self.texts = dict(texts or {})            # {(arm, session, rid): solution text}
        self.extra = dict(extra or {})            # {(arm, session, rid): {file name: text}} further final-tree files
        self.tools = dict(tools or {})            # {(arm, session, rid): {tool: count}}
        super().__init__(base, **kw)

    def solution(self, arm, session, rid):
        if (arm, session, rid) in self.texts:
            return self.texts[(arm, session, rid)]
        if (session, rid) in self.identical:
            return OFF_SOLUTION
        return OFF_SOLUTION if arm == "off" else ON_SOLUTION

    def events(self, arm, session, rid):
        counts = self.tools.get((arm, session, rid))
        if counts is None:
            counts = KNOWN_TOOLS[arm] if (session, rid) == KNOWN else DEFAULT_TOOLS[arm]
        return events_text(arm, session, rid, counts)

    def files(self, arm, session, rid):
        return {sol_name(rid): self.solution(arm, session, rid), **self.extra.get((arm, session, rid), {})}

    def _manifest_doc(self, arm, session, rid):
        return {"files": {n: sha_text(t) for n, t in sorted(self.files(arm, session, rid).items())}, "missing": []}

    def default_row(self, arm, session, rid, idx):
        row = super().default_row(arm, session, rid, idx)
        row["final_tree"]["files"] = dict(self._manifest_doc(arm, session, rid)["files"])
        row["evidence_sha256"] = {"events": sha_text(self.events(arm, session, rid)), "stderr": sha_text("")}
        lang, item = lang_name(rid)
        row["final_tree"]["manifest"] = (f"$STACK_WORKDIR/opencode_transcripts/{MODEL}/{MODEL}.{session}.x.L0.full.a1."
                                         f"20261102T190300-45a138b82165/{lang}__{item}.final_tree/manifest.json")
        return row

    def scrubbed(self, arm, session, rid):
        return self.events(arm, session, rid).replace("$STACK_WORKDIR", "<scratch>")

    def _build_attempt(self, ns, arm, session, n, **kw):
        super()._build_attempt(ns, arm, session, n, **kw)
        att = self.p(ns, attempt_name(arm, session, n))
        h = json.loads((att / "HARVEST.json").read_text())
        ids = list(kw.get("ids") if kw.get("ids") is not None else self.ids[session])
        for rid in ids:
            lang, item = lang_name(rid)
            if rid in (kw.get("dnf") if kw.get("dnf") is not None else self.dnf).get((arm, session), []):
                continue
            h["files"].append({"destination": "evidence", "published": f"benchmark/results/p426/{ns}/{attempt_name(arm, session, n)}"
                               f"/evidence/20261102T190300-45a138b82165/{lang}__{item}.events.jsonl",
                               "published_sha256": sha_text(self.scrubbed(arm, session, rid)),
                               "sha256": sha_text(self.events(arm, session, rid)), "source": "evidence:x",
                               "compression": None, "exclusion_reason": None})
        (att / "HARVEST.json").write_text(dumps(a7world.sealed({k: v for k, v in h.items() if k != "sha256"})))


def events_text(arm, session, rid, counts):
    """A transcript with timestamps, session ids, narrative text, paths and tokens; only tool_use names may reach a packet."""
    lines, n = [], 0
    names = [name for name in sorted(counts) for _ in range(counts[name])]
    names = names[::2] + names[1::2]                                   # interleave: order is not sorted order
    sid = f"ses_{arm}{session}{rid.replace('/', '_')}"
    def ev(kind, part):
        nonlocal n
        n += 1
        lines.append(json.dumps({"type": kind, "timestamp": TS0 + n * 977, "sessionID": sid, "part": part}))
    ev("step_start", {"type": "step-start", "sessionID": sid})
    for name in names:
        ev("tool_use", {"type": "tool", "tool": name, "id": f"call-{n}",
                        "state": {"status": "completed", "input": {"path": "$STACK_WORKDIR/scratch/oc/x"}, "output": "ok"}})
        ev("text", {"type": "text", "text": f"{MARKERS['text']}{arm}-{n}"})
    ev("step_finish", {"type": "step-finish", "tokens": {"input": 1234, "output": 5678}, "cost": 0})
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------------------------- git
GIT_ENV = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_AUTHOR_DATE": "1700000000 +0000",
           "GIT_COMMITTER_DATE": "1700000000 +0000"}


def git(repo, *args, data=None):
    r = subprocess.run(["git", "-C", str(repo), *map(str, args)], input=data, capture_output=True, env=GIT_ENV)
    if r.returncode:
        raise RuntimeError(f"git {args}: {r.stderr.decode(errors='replace')}")
    return r.stdout.decode(errors="replace").strip()


def commit_files(repo, files, ref, message="evidence"):
    """Commit exactly `files` ({repo-relative path: bytes}) as a parentless commit on `ref` (git fast-import); the work tree and
    the index of `repo` are untouched. Returns the commit sha."""
    repo = Path(repo)
    if not (repo / ".git").exists():
        git(repo, "init", "-q")
    out = bytearray()
    msg = message.encode()
    out += b"commit " + ref.encode() + b"\ncommitter t <t@example.invalid> 1700000000 +0000\ndata " + str(len(msg)).encode() + b"\n" + msg + b"\n"
    for path in sorted(files):
        out += b"M 100644 inline " + path.encode() + b"\ndata " + str(len(files[path])).encode() + b"\n" + files[path] + b"\n"
    r = subprocess.run(["git", "-C", str(repo), "fast-import", "--quiet"], input=bytes(out), capture_output=True, env=GIT_ENV)
    if r.returncode:
        raise RuntimeError(f"fast-import: {r.stderr.decode(errors='replace')}")
    return git(repo, "rev-parse", ref)


def read_tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


# -------------------------------------------------------------------------------------------------------------- judges
CLAUDE_JUDGE = {"label": "claude-opus-5-5", "family": "anthropic", "client": "claude-code:blind-judge", "model": "claude-opus-5-5"}
CURSOR_JUDGE = {"label": "cursor:gpt-5.6-sol-high", "family": "openai", "client": "cursor-agent", "model": "gpt-5.6-sol-high"}
JUDGES = {"box": "test-box", "ruling": "test", "text": [CLAUDE_JUDGE, CURSOR_JUDGE],
          "image": [CLAUDE_JUDGE, {"label": "cursor:gemini-3.1-pro", "family": "google", "client": "cursor-agent",
                                   "model": "gemini-3.1-pro"}]}


# ----------------------------------------------------------------------------------------------------------------- CLI
def run_cli(module, args, *, cwd=BENCH_DIR, path_prefix=None, env_extra=None, home=None):
    path = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
    if path_prefix:
        path = f"{path_prefix}:{path}"
    env = {"PYTHONPATH": str(cwd), "PATH": path, "HOME": str(home or cwd), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, **(env_extra or {})}
    args = list(args)
    if args and args[0] == "a7-export" and "--results-root" in args:     # d4: a7-export regrades A1 via bench.grade (fix report P1)
        env.setdefault("MLX_BENCH_RESULTS", str(Path(args[args.index("--results-root") + 1]).parent))
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=cwd, capture_output=True, text=True,
                          timeout=1800, env=env)


FAKE_CURSOR = '''#!{python}
import json, os, re, sys
if "--version" in sys.argv:
    print("9.9.9-fake")
    sys.exit(0)
pkt = re.search(r"file (p\\d+)\\.md", sys.argv[-1]).group(1)
log = os.environ.get("FAKE_CURSOR_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(pkt + "\\n")
if pkt in os.environ.get("FAKE_CURSOR_FAIL", "").split(","):
    sys.exit(3)
mode = os.environ.get("FAKE_CURSOR_MODE", "A")
plan = os.environ.get("FAKE_CURSOR_PLAN")
if plan:
    mode = json.load(open(plan)).get(pkt, mode)
if mode == "garbage":
    print("not json at all")
else:
    print(json.dumps({{"choice": mode, "rationale": "fake judge"}}))
'''


def install_fake_cursor(directory):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    exe = d / "cursor-agent"
    exe.write_text(FAKE_CURSOR.format(python=sys.executable))
    exe.chmod(0o755)
    return d


# ----------------------------------------------------------------------------------------------------------------- case
class A7Case:
    """The hermetic A7 case. `A7Case(base)` builds; `A7Case.attach(base)` re-opens a (copied) directory."""

    def __init__(self, base, *, with_rejected=True, texts=None, tools=None, extra=None):
        from _pytest.monkeypatch import MonkeyPatch
        from bench import p426_verify as V
        from bench.tests.p613s2 import wave1world as WW

        self.base = Path(base)
        with MonkeyPatch.context() as mp:
            mp.setattr(a7world, "World", World3)
            spec = dict(ids=ids_for(with_rejected), rows=rows_for(with_rejected), identical=identical_for(), texts=texts,
                        tools=tools, extra=extra)
            self.w1 = WW.Wave1World(self.base, mp, with_a7=True, a7=spec)
            self.b8 = V.verify_all(self.w1.p426, self.w1.rows_root, self.w1.repo)
        w = self.w1.a7
        self._write_evidence_src(w)
        self._write_exercises(w)
        if with_rejected:
            self._reject(S1_REJECTED[0], "s1")
        self.b8_path.write_text(dumps(self.b8))
        (self.base / "judges.json").write_text(json.dumps(JUDGES, indent=1) + "\n")
        sha = commit_files(self.repo, read_tree(self.base / "evidence_src"), "refs/heads/evidence")
        (self.base / "evidence_ref.txt").write_text(sha + "\n")
        git(self.repo, "add", "-A")                       # B8.json and universe.json are COMMITTED, the tree is clean (fix 7)
        git(self.repo, "commit", "-q", "-m", "world: committed B8 and universe")

    @classmethod
    def attach(cls, base):
        self = cls.__new__(cls)
        self.base = Path(base)
        self.w1 = None
        self.b8 = json.loads((self.base / "repo" / "benchmark" / "results" / "p426" / "B8.json").read_text())
        return self

    # ---- paths
    @property
    def repo(self):
        return self.base / "repo"

    @property
    def rows_root(self):
        return self.repo / "benchmark" / "results"

    @property
    def results_root(self):
        return self.rows_root / "p426"

    @property
    def polyglot(self):
        return self.base / "polyglot"

    @property
    def universe(self):
        return self.repo / "benchmark" / "m62" / "universe.json"

    @property
    def judges(self):
        return self.base / "judges.json"

    @property
    def b8_path(self):
        return self.results_root / "B8.json"

    @property
    def evidence_ref(self):
        return (self.base / "evidence_ref.txt").read_text().strip()

    def attempt(self, arm, session):
        return self.results_root / "wave2" / f"tg1-p426-{arm}-{session}.a1"

    def item_dir(self, arm, session, rid):
        lang, item = lang_name(rid)
        (found,) = sorted(self.attempt(arm, session).glob(f"evidence/*/{lang}__{item}.final_tree"))
        return found

    # ---- build
    def _write_evidence_src(self, w):
        src = self.base / "evidence_src"
        for att in sorted((w.root / "wave2").glob("tg1-p426-*.a1")):
            arm, session = att.name.split("-")[2], att.name.split("-")[3].split(".")[0]
            for manifest in sorted(att.glob("evidence/*/*.final_tree/manifest.json")):
                tree = manifest.parent
                lang, item = tree.name[: -len(".final_tree")].split("__", 1)
                rid = f"{lang}/{item}"
                rel = tree.relative_to(self.repo).as_posix()
                doc = json.loads(manifest.read_text())
                for fname, sha in doc["files"].items():
                    text = w.files(arm, session, rid)[fname]
                    assert sha_text(text) == sha
                    self._put(src / rel / "objects" / sha, text.encode())
                self._put(src / (rel[: -len(".final_tree")] + ".events.jsonl"), w.scrubbed(arm, session, rid).encode())

    @staticmethod
    def _put(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _write_exercises(self, w):
        items = {}
        for session in ("s1", "s2"):
            for rid in w.ids[session]:
                lang, name = lang_name(rid)
                d = self.polyglot / lang / "exercises" / "practice" / name
                prepared = {".docs/instructions.md": instructions_of(rid), sol_name(rid): START, test_name(rid): TEST_TEXT}
                if rid == APPEND_ID:
                    prepared[".docs/instructions.append.md"] = append_of(rid)
                for rel, text in prepared.items():
                    self._put(d / rel, text.encode())
                self._put(d / ".meta" / "example.py", f"# {MARKERS['ref']}\n".encode())      # must never reach a packet
                items[rid] = {"baseline_failing": 1, "grader_version": "m62-structured-v3", "leaves": [],
                              "prepared": {k: sha_text(v) for k, v in prepared.items()},
                              "protected": {test_name(rid): sha_text(TEST_TEXT)}, "solution": sol_name(rid),
                              "test": test_name(rid)}
        self.universe.parent.mkdir(parents=True, exist_ok=True)
        self.universe.write_text(json.dumps({"grader_version": "m62-structured-v3", "items": items}, indent=1) + "\n")

    def _reject(self, rid, session):
        for pair in self.b8["axes"]["A7"]["pairs"]:
            if pair["pair"] == session and pair["role"] == "pair":
                keep = []
                for k in pair["keys"]:
                    if k["key"] == [session, rid]:
                        pair["keys_rejected"].append({"key": [session, rid], "reason": "test: key rejected"})
                        pair["keys_accepted"] -= 1
                    else:
                        keep.append(k)
                pair["keys"] = keep

    def reverify(self):
        """Re-run B8 over the (edited) rows and rewrite B8.json (R3: a changed row needs a fresh B8, a stale one is refused)."""
        from _pytest.monkeypatch import MonkeyPatch
        from bench import generate
        from bench import p426_verify as V

        with MonkeyPatch.context() as mp:
            mp.setattr(generate, "RESULTS", self.rows_root)
            self.b8 = V.verify_all(self.results_root, self.rows_root, self.repo)
        self.b8_path.write_text(dumps(self.b8))
        return self.b8

    def a1_eligible(self):
        """(identical eligible keys, not-both-correct keys) of the Wave 1 pairs (E3), from the synthetic rows: math500 keys where
        both arms answer correctly are eligible; the other axes are all eligible."""
        import re
        w1 = self.w1
        elig = bad = 0
        for p in self.b8["axes"]["wave1"]["pairs"]:
            n = p["identical"]["n"]
            if p["kind"] == "math500":
                per = {}
                for arm in ("on", "off"):
                    for r in w1.read_rows("math500", arm, p["block"]):
                        m = re.search(r"\\boxed\{([^}]*)\}", r["content"])
                        per.setdefault(r["id"], []).append(m is not None and m.group(1) == r["answer_gold"])
                ok = sum(1 for v in per.values() if all(v))
                elig += ok
                bad += n - ok
            elif p["kind"] in ("cjudge", "vision", "reasoning"):
                elig += n
        return elig, bad

    # ---- the code under test
    def select(self, panel):
        return panel.a7_select(self.results_root, self.b8)

    def packet(self, panel, item, *, evidence_ref=None, polyglot=None, universe=None, repo=None, b8=None):
        return panel.a7_packet(self.results_root, b8 or self.b8, item, evidence_ref or self.evidence_ref,
                               polyglot or self.polyglot, universe or self.universe, repo or self.repo)

    def export_args(self, out, *, evidence_ref=None, b8_path=None):
        return ["a7-export", "--results-root", self.results_root, "--b8", b8_path or self.b8_path, "--evidence-ref",
                evidence_ref or self.evidence_ref, "--repo", self.repo, "--polyglot-root", self.polyglot, "--universe",
                self.universe, "--judges", self.judges, "--out", out]

    def export(self, out, **kw):
        return run_cli("bench.p426_panel", self.export_args(out, **kw))

    def tamper_evidence(self, fn):
        """A new evidence commit (a separate ref) whose file bytes `fn(files)` altered; returns its sha."""
        files = read_tree(self.base / "evidence_src")
        fn(files)
        n = len(git(self.repo, "for-each-ref", "--format=%(refname)", "refs/heads/evidence-").split())
        return commit_files(self.repo, files, f"refs/heads/evidence-t{n}", "evidence (tampered)")


def refuses(fn, *args, **kw):
    """`fn(*args, **kw)` must raise a DELIBERATE refusal: any exception except a programming error (a missing attribute, a bad
    call), so a not-yet-built interface never counts as a refusal. Returns the exception."""
    try:
        fn(*args, **kw)
    except (AttributeError, TypeError, NameError, ImportError) as exc:
        raise AssertionError(f"programming error, not a refusal: {type(exc).__name__}: {exc}") from None
    except Exception as exc:                                  # noqa: BLE001
        return exc
    raise AssertionError("no refusal was raised")


def refused_cli(proc):
    """A CLI refusal: rc != 0, a message on stderr, and not an argparse usage error (which a missing subcommand would be)."""
    assert proc.returncode != 0, "rc 0: nothing was refused (or the command does not exist)"
    assert proc.stderr.strip() and "usage:" not in proc.stderr, proc.stderr[-400:]
    return proc


def packets_of(out):
    return sorted(Path(out).glob("*/batch*/p*.md"))


def manifest_of(out):
    return [json.loads(l) for l in (Path(out) / "manifest.jsonl").read_text().splitlines() if l.strip()]


def sha_file(path):
    return sha_bytes(Path(path).read_bytes())


def short_id(item_id, known):
    """Map a manifest `item_id` (maybe `s1/python/alpha` or `python/alpha`) to the short `lang/name` id."""
    for rid in known:
        if item_id == rid or item_id.endswith("/" + rid):
            return rid
    raise KeyError(item_id)
