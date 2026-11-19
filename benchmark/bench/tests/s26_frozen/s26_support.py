"""S26 frozen tests: shared fixtures (spec docs/specs/s26-agent-env.md v1.1). TESTS ONLY; temp trees and fakes, no GPU / network /
docker / real Homebrew. Every fixture is in the format of the code it stands for (sources cited):

- `HostWorld`: a temp host (PATH dir, Cellar, bin dirs, npm global dir, HOME) the real `host_env.fingerprint` reads.
- `HostSeqOps`: `b2_frozen_add_support.SeqOps` (the sequencer fake) + the `host_env()` seam backed by a `HostWorld`.
- `PosOps`: the positives box ops (`p426_wave2.cmd_positives` seams) with real-shaped inject rows / events: the rows come from
  `test_m76_b4b1_impl_wave2._v2_stall_row` (the real `OpencodeArm.row_fields` over the real evidence suffixes and a recorded real
  `tg2_grade` tree), re-labelled per kind, with their events file rewritten (and its sha256 re-recorded).
- `GradleWorld`: a fake `./gradlew` (a real executable script) behind the real `Tg2Corpus` / `tg2_materialize` seams."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from bench.tests import b2_frozen_add_support as A

BENCH = Path(__file__).resolve().parents[3]
REPO = BENCH.parent
UNIVERSE_PATH = BENCH / "m65" / "tg2_universe.json"
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DATE = "Fri Nov 13 2026"
LANGS = ("rust", "javascript", "java", "cpp")
KINDS = ("stall", "loop", "alloc")
IDENT = dict(probe_code_sha256="a" * 64, scaffold_policy_sha256="b" * 64, generation_identity_sha256="c" * 64)
COMMIT = "1" * 40
GITLINKS = {"src/mlx-vlm": "3" * 40, "src/mlx-serve": "4" * 40}
MARKERS = {"loop": "sleep 600", "alloc": "bytearray("}                       # spec §4: the kind's marker


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p) -> str:
    return sha256_bytes(Path(p).read_bytes())


def rc_of(call, *args, **kw):
    """The exit code of a CLI `main(argv)` (a returned int, or a SystemExit code); 0 for None / 0."""
    try:
        rc = call(*args, **kw)
    except SystemExit as exc:
        rc = exc.code
    if rc in (None, 0):
        return 0
    return rc if isinstance(rc, int) else 1


# ------------------------------------------------------------------------------------------------------- the temp host
class HostWorld:
    """A temp host the real `host_env.fingerprint` reads: `bin` (the agent PATH), `brewbin` / `usrbin` (the two bin dirs), `Cellar`,
    `npm` (the global node_modules), `home`. `tool(...)` puts an executable in `bin` as a symlink to `real/<name>`."""

    def __init__(self, root):
        self.root = Path(root)
        self.bin, self.real = self.root / "bin", self.root / "real"
        self.cellar, self.brewbin, self.usrbin = self.root / "Cellar", self.root / "brewbin", self.root / "usrbin"
        self.npm, self.home = self.root / "npm", self.root / "home"
        for d in (self.bin, self.real, self.cellar, self.brewbin, self.usrbin, self.npm, self.home):
            d.mkdir(parents=True, exist_ok=True)
        self.tool("java", b"jdk-21 binary\n")
        self.formula("rust", "1.80.0")
        self.bin_file(self.brewbin, "brew-tool", b"x\n")

    # tools
    def tool(self, name, content=b"#!/bin/sh\nexit 0\n"):
        real = self.real / name
        real.write_bytes(content)
        real.chmod(0o755)
        link = self.bin / name
        if not link.is_symlink() and not link.exists():
            link.symlink_to(real)
        return real

    def rm_tool(self, name):
        (self.bin / name).unlink()

    # Cellar / bin dirs / npm / home
    def formula(self, name, version):
        (self.cellar / name / version).mkdir(parents=True, exist_ok=True)

    def rm_formula(self, name, version):
        (self.cellar / name / version).rmdir()

    def bin_file(self, d, name, content=b"x\n"):
        (Path(d) / name).write_bytes(content)

    def bin_link(self, d, name, target):
        link = Path(d) / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)

    def npm_pkg(self, name, version):
        d = self.npm / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "package.json").write_text(json.dumps({"name": name, "version": version}))

    def home_dir(self, rel):
        (self.home / rel).mkdir(parents=True, exist_ok=True)

    def rm_home_dir(self, rel):
        (self.home / rel).rmdir()

    def fingerprint(self, files=()):
        from bench import host_env
        return host_env.fingerprint(path=str(self.bin), cellar=self.cellar, bin_dirs=(self.brewbin, self.usrbin),
                                    npm_global=self.npm, home=self.home, files=tuple(files))


# ------------------------------------------------------------------------------------------------------- the sequencer
class HostSeqOps(A.SeqOps):
    """The sequencer fake of `b2_frozen_add_support` + the `host_env` seam (`BoxSeqOps.host_env`, spec §2) over a `HostWorld`.
    `on_launch(leg)` runs right after a chain launch (inside the leg region), `on_harvest(leg)` right after a leg's harvest (after
    the post-leg check, before the next pre-launch check). `publishes` holds `sequence.json`'s text at each run-file publication."""

    def __init__(self, *a, world, **kw):
        super().__init__(*a, **kw)
        self.world, self.host_calls = world, 0
        self.on_launch, self.on_harvest = None, None
        self.publishes = []

    def host_env(self):
        self.host_calls += 1
        return self.world.fingerprint()

    def launch(self, argv, **kw):
        h = super().launch(argv, **kw)
        if h.kind == "chain" and self.on_launch:
            self.on_launch(self._leg_of(h.argv))
        return h

    def harvest(self, leg_root, **kw):
        out = super().harvest(leg_root, **kw)
        if self.on_harvest:
            self.on_harvest(Path(leg_root).name.rsplit(".a", 1)[0])
        return out

    def publish_run_files(self, paths, *, emails=()):
        seq = [p for p in paths if Path(p).name == "sequence.json"]
        self.publishes.append(Path(seq[0]).read_text() if seq else None)
        return super().publish_run_files(paths, emails=emails)


def drive(tmp_path, monkeypatch, cmd="run", *extra, script=None, ops_cls=HostSeqOps, world=None, before=None, records=True,
          emails=("op.erator@corp-mail.example",)):
    """`test_b2_frozen_add_sequencer.seq` with a choice of ops class: runs `p426_wave2.main` on the fake ops and fake clock.
    Returns dict(rc, err, ops, world, base, rec, wd, wts)."""
    from bench import p426_wave2
    wd = tmp_path / "wd"
    wd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    if records:
        A.sequencer_records(tmp_path)
    argv, wts = A.seq_argv(tmp_path, cmd, *extra)
    clock = A.Clock()
    if ops_cls is HostSeqOps:
        world = world or HostWorld(tmp_path / "host")
        ops = HostSeqOps(clock, script, main_root=tmp_path / "main", emails=emails, world=world)
    else:
        ops = ops_cls(clock, script, main_root=tmp_path / "main", emails=emails)
    if before:
        before(ops, clock)
    p426_wave2.__name__                                        # the module must import (not an ImportError 'refusal')
    rc, err = A.run_sequencer(argv, ops, clock)
    base = wd / ("p426/rehearsal" if cmd == "rehearsal" else "p426/wave2")
    return dict(rc=rc, err=err, ops=ops, world=world, base=base, rec=tmp_path / "records", wd=wd, wts=wts, clock=clock)


def legs_run(r):
    return [r["ops"]._leg_of(h.argv) for h in r["ops"].chain_launches()]


def sequence(r):
    return json.loads((r["base"] / "sequence.json").read_text())


def leg_json(r, leg, attempt=1):
    return json.loads((r["base"] / f"{leg}.a{attempt}" / "leg.json").read_text())


def seq_log(r):
    p = r["base"] / "sequence.log"
    return p.read_text() if p.exists() else ""


# ------------------------------------------------------------------------------------------------------- the positives
def _wave2_tests():
    return importlib.import_module("bench.tests.test_m76_b4b1_impl_wave2")


def ev_step(n):
    return [json.dumps(dict(type="step_start", sessionID="s1", part=dict(messageID=f"m{n}", id=f"s{n}"))),
            json.dumps(dict(type="step_finish", sessionID="s1", part=dict(messageID=f"m{n}", id=f"f{n}")))]


def ev_tool(call, tool, inputs):
    """A `tool_use` event as opencode 2.0.20 writes it (`test_p371_a4_unit.tool_use`; `inject_verify.derive` reads it)."""
    state = dict(status="completed", input=inputs, metadata={}, time=dict(start=1_000, end=2_000), output="x", title=tool)
    return json.dumps(dict(type="tool_use", sessionID="s1", part=dict(partID="p-" + call, id=call, messageID="m1", type="tool",
                                                                       tool=tool, state=state)))


def ev_text(text):
    return json.dumps(dict(type="text", sessionID="s1", part=dict(messageID="m1", type="text", text=text)))


def write_inject_run(run_dir, wd, kind, attempt, event_lines, *, gate_stop=None, shape=None, mutate=None):
    """`<run_dir>/<kind>.attempt<attempt>.jsonl` + `.manifest.json`: a real-shaped tg2 inject row (recorded grade reports, real
    `row_fields`, `$STACK_WORKDIR`-relative evidence paths as the probe's `portable` writes them) whose events file holds
    `event_lines` and whose `evidence_sha256` is re-recorded to match. Returns (row, manifest, events_path).

    `shape` (erratum v1.1b item 9): `"completed"` - a normally completed run, the shape of a genuine decline (row `stop_reason`
    "completed", `gate.stop_reason` None, `mem_kills == []` AND `termination.killed == []`); `"client_kill"` - not-observed but the
    client was killed (`termination.killed` holds a client kill); `"mem_kill"` - a memory kill (`mem_kills` holds one, no client
    kill); `"keep"` - the stall-positive row as recorded (a client kill). Default: `"keep"` for stall, `"completed"` otherwise.
    `mutate(row, manifest)` edits the dicts before they are written."""
    shape = shape or ("keep" if kind == "stall" else "completed")
    base = Path(wd) / "m65" / "arts" / f"{Path(run_dir).name}-{kind}-{attempt}"
    row, manifest = _wave2_tests()._v2_stall_row(base)
    events = Path(row["events_path"])
    events.write_text("".join(line + "\n" for line in event_lines))
    row["evidence_sha256"]["events"] = sha256_file(events)
    label = f"opencode-v2-web-tg2-inject:{kind}"
    row["scaffold"], manifest["runtime"]["scaffold"] = label, label
    manifest["runtime"]["inject"]["kind"] = kind
    row["gate"]["stop_reason"] = gate_stop
    row["mem_kills"] = []
    if shape in ("completed", "mem_kill"):
        row["stop_reason"] = "completed"
        row["termination"] = dict(row["termination"], reason=None, killed=[])
    if shape == "client_kill":
        row["stop_reason"] = "completed"
    if shape == "mem_kill":
        row["mem_kills"] = [dict(role="model", argv=["python3", "-c", "x = bytearray(1 << 40)"], rss=10 ** 9, tool_call_id="c-mem")]
    if mutate:
        mutate(row, manifest)
    for field in ("events_path", "transcript_path", "stderr_path", "datefreeze_path"):
        row[field] = str(row[field]).replace(str(wd), "$STACK_WORKDIR")
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    stem = run_dir / f"{kind}.attempt{attempt}"
    Path(str(stem) + ".jsonl").write_text(json.dumps(row) + "\n")
    Path(str(stem) + ".manifest.json").write_text(json.dumps(manifest))
    return row, manifest, events


def default_events():
    """What a model that did nothing special leaves: steps, a harmless tool call, a text part (no marker anywhere)."""
    lines = []
    for n in range(1, 4):
        lines += ev_step(n)
    return lines + [ev_tool("c1", "shell", {"command": "ls"}), ev_text("done")]


class PosOps:
    """`p426_wave2.cmd_positives`'s box ops, in the formats of `test_m76_b4b1_impl_wave2.PosOps` + the `host_env` seam (spec §2).
    `verdicts[(lang, kind)]` is what `inject_verify` returns (a bare verdict string: `PASS`, `not_observed:kill`, `FAIL:rss`, ...);
    `events[(lang, kind)]` the event lines of that run's events file; `hooks` are callables run at named points
    (`grade`, `inject`, `session_enter`, `session_exit`), each given the (lang, kind) or variant."""

    def __init__(self, tmp_path, world, *, verdicts=None, events=None, aborts=None, hooks=None, shapes=None, probe_rc=None,
                 bad_row_sha=(), mutates=None):
        self.wd = Path(tmp_path) / "wd"
        self.mutates = dict(mutates or {})
        self.world = world
        self.shapes, self.probe_rc, self.bad_row_sha = dict(shapes or {}), dict(probe_rc or {}), set(bad_row_sha)
        self.verdicts, self.events = dict(verdicts or {}), dict(events or {})
        self.aborts, self.hooks = dict(aborts or {}), dict(hooks or {})
        self.served, self.runs, self.verified = [], [], []
        self.host_calls = 0

    def host_env(self):
        self.host_calls += 1
        return self.world.fingerprint()

    def worktree_state(self, path):
        return dict(head=COMMIT, clean=True, gitlinks=dict(GITLINKS))

    def identity(self, path):
        return dict(IDENT)

    def _hook(self, name, *args):
        fn = self.hooks.get(name)
        if fn:
            fn(*args)

    def positives_session(self, worktree, *, frozen_prompt_date):
        ops = self

        class Session:
            def __enter__(self):
                ops.served.append("start")
                ops._hook("session_enter")
                return self

            def __exit__(self, *exc):
                ops.served.append("stop")
                ops._hook("session_exit")
                return False
        return Session()

    def positive_grade(self, lang, item, variant):
        self._hook("grade", lang, variant)
        passed = variant == "reference"
        return dict(outcome="parsed", passed=passed, failing=0 if passed else 3, leaves=5 if passed else 2)

    def positive_inject(self, lang, item, kind, *, seed, attempt):
        self.runs.append((lang, kind, attempt))
        self._hook("inject", lang, kind)
        if self.aborts.get((lang, kind), 0) >= attempt:
            return dict(transport_abort=True, run=str(self.wd / "m65" / "inject" / f"{lang}-{kind}-{attempt}"))
        run = self.wd / "m65" / "inject" / f"{lang}-{kind}"
        _, _, events_path = write_inject_run(run, self.wd, kind, attempt, self.events.get((lang, kind), default_events()),
                                             shape=self.shapes.get((lang, kind)), mutate=self.mutates.get((lang, kind)))
        stem = run / f"{kind}.attempt{attempt}"
        shas = dict(row_sha256=sha256_file(str(stem) + ".jsonl"), evidence_sha256=sha256_file(str(stem) + ".manifest.json"))
        if (lang, kind) in self.bad_row_sha:                              # the row the probe reported is not the row on disk
            shas["row_sha256"] = "0" * 64
        self._hook("after_write", lang, kind, events_path, run)           # a test may damage the run's files after the probe wrote them
        if self.probe_rc.get((lang, kind)):                               # BoxSeqOps: a nonzero exit leaves the row, no `row_sha256`
            return dict(transport_abort=False, run=str(run), rc=self.probe_rc[(lang, kind)])
        return dict(transport_abort=False, run=str(run), rc=0, **shas)

    def inject_verify(self, run, kind):
        lang = Path(run).name.split("-")[0]
        self.verified.append((lang, kind))
        return self.verdicts.get((lang, kind), "PASS")


def positives(tmp_path, monkeypatch, ops, name="positives.json"):
    """`p426_wave2 positives` through `main` (the existing tests' invocation); returns (rc, record path)."""
    from bench import p426_wave2 as W2
    wd = Path(tmp_path) / "wd"
    wd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    out = wd / "run" / name
    rc = W2.main(["positives", "--corpus", "tg2", "--lever", "kv", "--arm-worktree", f"n16={Path(tmp_path) / 'wt-n16'}", "--out",
                  str(out), "--frozen-prompt-date", DATE], ops=ops)
    return rc, out


def record(out):
    return json.loads(Path(out).read_text())


def inject_of(doc, lang, kind):
    (entry,) = [e for e in doc["injects"] if e["language"] == lang and e["kind"] == kind]
    return entry


# ------------------------------------------------------------------------------------------------------- the Gradle home
def universe_java_items():
    """The VALID Java items of the committed tg2 universe (exactly the set `prefill` / `check` cover, spec §3)."""
    doc = json.loads(UNIVERSE_PATH.read_text())
    return sorted(i for i, e in doc["items"].items() if i.split("/", 1)[0] == "java" and e.get("status") == "valid")


def safe(item):
    return item.replace("/", "__")


GRADLE_JAR = "wrapper/dists/gradle-8.7-bin/h/gradle-8.7/gradle.jar"


def dep_rel(item):
    return f"caches/modules-2/files-2.1/{safe(item)}/dep.jar"


SCRIPT = """#!/bin/sh
KEYS=$(/usr/bin/env | /usr/bin/cut -d= -f1 | /usr/bin/sort | /usr/bin/paste -sd, -)
printf 'CALL|%s|%s|%s|%s|%s|%s|%s|%s\\n' '{item}' "$*" "$KEYS" "$HOME" "$TMPDIR" "$GRADLE_USER_HOME" "$PATH" "$(pwd)" >> '{log}'
case " $* " in
  *" --stop "*) exit 0;;
  *" --version "*) echo 'Gradle 8.7'; exit 0;;
esac
[ -f "$GRADLE_USER_HOME/gradle.properties" ] || exit 9
case " $* " in
  *" --offline "*)
    [ -f "$GRADLE_USER_HOME/{dep}" ] || exit 3
    exit {off_rc};;
esac
/bin/mkdir -p "$GRADLE_USER_HOME/wrapper/dists/gradle-8.7-bin/h/gradle-8.7" "$GRADLE_USER_HOME/caches/modules-2/files-2.1/{safe}" "$GRADLE_USER_HOME/daemon/8.7"
printf 'dist' > "$GRADLE_USER_HOME/{jar}"
printf '%s' '{item}' > "$GRADLE_USER_HOME/{dep}"
printf 'noise' > "$GRADLE_USER_HOME/daemon/8.7/daemon.log"
exit {on_rc}
"""

SHELL_NOISE = {"PWD", "SHLVL", "_", "OLDPWD", "__CF_USER_TEXT_ENCODING"}


class GradleWorld:
    """The prefill's collaborators faked at their real seams: `Tg2Corpus.prepare` (a work tree holding an executable `./gradlew`
    script that logs its argv and environment to `log` and fills / reads `$GRADLE_USER_HOME`), `Tg2Corpus.polyglot_root`,
    `tg2_materialize.read_plan` / `apply_reference`. `fail_offline` / `fail_online`: item ids whose pass exits 1."""

    def __init__(self, tmp_path, monkeypatch, *, fail_offline=(), fail_online=()):
        from bench import corpus_tg2
        from bench import tg2_materialize as mat
        self.tmp = Path(tmp_path)
        self.wd = self.tmp / "wd"
        self.wd.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("STACK_WORKDIR", str(self.wd))
        monkeypatch.setenv("S26_LEAK_PROBE", "must-not-reach-gradle")      # a sentinel: the agent env is built, never inherited
        self.log = self.tmp / "gradle-calls.log"
        self.folder = self.wd / "tg2-gradle-home"
        self.fail_offline, self.fail_online = set(fail_offline), set(fail_online)
        self.prepared, self.references = [], []
        world = self

        def prepare(self_, item, dest):
            dest = Path(dest)
            dest.mkdir(parents=True, exist_ok=True)
            world.prepared.append((item, dest))
            body = SCRIPT.format(item=item, log=world.log, dep=dep_rel(item), safe=safe(item), jar=GRADLE_JAR,
                                 off_rc=1 if item in world.fail_offline else 0, on_rc=1 if item in world.fail_online else 0)
            g = dest / "gradlew"
            g.write_text(body)
            g.chmod(0o755)
            return SimpleNamespace(work=dest, item_id=item, lang="java", name=item.split("/", 1)[1])

        monkeypatch.setattr(corpus_tg2.Tg2Corpus, "prepare", prepare)
        monkeypatch.setattr(corpus_tg2.Tg2Corpus, "polyglot_root", lambda self_: self.tmp / "polyglot")
        monkeypatch.setattr(mat, "read_plan", lambda root, lang, slug: ("plan", lang, slug))
        monkeypatch.setattr(mat, "apply_reference", lambda root, plan, tree: world.references.append((plan, Path(tree))))

    def calls(self):
        """Every `./gradlew` invocation (a `--version` probe, if the prefill makes one, is not a prefill pass and is left out)."""
        out = []
        if not self.log.exists():
            return out
        for line in self.log.read_text().splitlines():
            _, item, args, keys, home, tmpdir, guh, path, cwd = line.split("|")
            if args.split() == ["--version"]:
                continue
            out.append(dict(item=item, args=args.split(), keys=set(keys.split(",")) - SHELL_NOISE, home=home, tmpdir=tmpdir,
                            guh=guh, path=path, cwd=cwd))
        return out

    def prefill(self, *flags):
        from bench import tg2_gradle_home as G
        return rc_of(G.main, ["prefill", *flags])

    def check(self):
        from bench import tg2_gradle_home as G
        return rc_of(G.main, ["check"])

    def prefill_doc(self):
        return json.loads((self.folder / "PREFILL.json").read_text())

    def write_prefill_doc(self, doc):
        (self.folder / "PREFILL.json").write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")


def expected_manifest(items):
    rows = [[GRADLE_JAR, 4]] + [[dep_rel(i), len(i)] for i in items]
    return sorted(rows)
