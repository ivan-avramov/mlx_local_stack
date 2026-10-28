"""P426 T3 frozen tests (`docs/specs/p426-t3-serving-build.md` v2.1): shared fixtures.

A hermetic box: stack worktrees as real git repositories in `tmp_path` (the fork / mlx-serve checkouts are git directories whose
detached HEAD names the pinned sha), real venvs carrying only the version metadata K2 reads, and fakes for every effect that would
touch a GPU, a router or the network. Every fixture is exercised against the baseline by `test_t3_frozen_support_check.py`.

Formats (cited at the line that writes or reads them on the baseline):
- frozen record under `s`: `benchmark/results/p426/wave1/run/frozen.json` (keys) read by `bench/p426_leg.py:717-719`.
- receipts: `bench/p426_leg.py:401-420` (`<name>.receipt.json`, `.refused-<ns>`); verdicts read by `bench/p426_wave1.py:60-75`.
- rows / server-log lines: `bench/tests/test_p426_leg.py:215-257` (the log grammar `bench/p426_leg.py:30,307-320`).
- qualify report / overlay: `src/mlx-vlm/dev/p369_phase2/qualify.py:943-952` (report.json), `:985` (`overlay-<entry>.yaml`).
- dossiers: `bench/p426_harvest.py:101-129` (`SCRUB_MANIFEST.json`), run files `:132-150`.
- fork layouts: `src/mlx-vlm/dev/ci.py:44-54` (`AUDITS`), `src/mlx-vlm/.upstream-sync-ref` (S′);
  `.github/workflows/upstream-parity.yml` `UPSTREAM_SYNC_REF:` (S; `bench/local_gate.py:52-56`, `bench/tests/test_local_gate.py:52-56`).
"""

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from bench.rowschema import sample_seed

REAL_RUN, REAL_POPEN, REAL_SLEEP = subprocess.run, subprocess.Popen, time.sleep
REPO = Path(__file__).resolve().parents[3]
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAFTER = f"caslca/{ENTRY}-mtp-drafter"
AXES = ("math500", "cjudge", "vision", "reasoning", "m1")
ARMS = ("off", "on")

# S: `benchmark/results/p426/wave1/run/frozen.json` (the committed record of S's Wave 1).
S_PINS = dict(mlx_vlm="0f30522c9ebf05281d7e68903c73e0761f849cf3", mlx_serve="86921f029d7e55b4d8b5882f2c05ed5e2ce31ef0",
              production_ref="0b603d032fbcfcd59fba46b1bf04482482e1ec81")
# S′: spec §4 "Expected build per label".
# POST-REVEAL tw-5: C242 pin move — mlx-vlm c688e722 → 1c7c8fa1 (uv.lock refresh), mlx-serve e6a7a5a → 1ddf6f84 (ruff format).
S2_PINS = dict(mlx_vlm="1c7c8fa166582ac1a1c23ae9063527b2b5215b11", mlx_serve="1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d",
               production_ref="b26fa7c9faf23bc3167db3419504ef0b2b82a8e6")
# spec A2 (the S′ resolution); mlx 0.32.4 is the expected build in both venvs (§4).
S2_VERSIONS = {"mlx": "0.32.4", "mlx-metal": "0.32.4", "transformers": "5.15.0", "huggingface-hub": "1.12.0",
               "datasets": "5.0.1", "mlx-audio": "0.6.2"}
VENVS = (".venv", ".venv-bench")

# The C177 lines as committed on B0 (`main_models.yaml:377,405,406`) and their restored form (S's ON overlay,
# `benchmark/results/p426/wave1/run/registry-on.yaml:527,555,556`).
C177 = {
    "    # mtp_verify_scan: joint_v1  # P369 INTERIM": "    mtp_verify_scan: joint_v1",
    "    # draft_kind: mtp  # P369 INTERIM (C177 2026-10-17)": "    draft_kind: mtp",
    f"    # draft_model: {DRAFTER}": f"    draft_model: {DRAFTER}",
}
PROVISIONAL_NOTE = "      # PROVISIONAL P426 2026-10-27: MTP ON restored for the Wave-1 rerun on S2 (C236)"
SEEDING_TEST = "benchmark/bench/tests/test_opencode_probe_seeding.py"
# POST-REVEAL tw-4: C241 / P511 — the seeding test's restore is the exact reverse of C177's seeding hunk (commit `78a730fe`,
# `benchmark/bench/tests/test_opencode_probe_seeding.py` @@ -169,8 +169,9 @@): its two comment lines and the `per_query`
# assertion go, the two original assertions come back.
SEEDING_OFF = ('    # C177 / P369 interim: the daily-driver registry runs the picks MTP-OFF, so the real registry resolves the default\n'
               '    # scan; restore `joint_v1` + source "registry" when MTP is re-certified and switched back on.\n'
               '    assert man["runtime"]["mtp_verify_scan"] == "per_query"\n')
SEEDING_ON = ('    assert man["runtime"]["mtp_verify_scan"] == "joint_v1"\n'
              '    assert man["runtime"]["mtp_verify_scan_source"] == "registry"\n')
# POST-REVEAL tw-4: the fork files the B4 overlay rule needs (`bench/p426_overlay.py:20-36`, `:62`), copied into every fake fork.
FORK_OVERLAY_FILES = ("dev/p369_phase2/registry_states.py", "mlx_vlm/tests/fixtures/stack_registry_golden.yaml")

ENGAGED = dict(draft_kind="mtp", draft_rounds=5, draft_n=10, draft_n_accepted=7)
PLAIN = dict.fromkeys(ENGAGED)
TS = "2026-10-27 01:00:00,000 - mlx_vlm.server - INFO - "
AC_LINE = "2026-10-27 01:00:00 -0700 Assertions  Summary- [System: x] Using AC(Charge: 80)\n"


# ------------------------------------------------------------------ git / files
def git(cwd, *a, check=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    r = REAL_RUN(["git", "-C", str(cwd), "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *a],
                 capture_output=True, text=True, env=env)
    if check and r.returncode:
        raise RuntimeError(f"git {a}: {r.stderr}")
    return r.stdout.strip()


def init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.invalid")
    git(path, "config", "user.name", "t")


def commit_all(path, msg):
    git(path, "add", "-A")
    git(path, "commit", "-q", "--allow-empty", "-m", msg)
    return git(path, "rev-parse", "HEAD")


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sha256_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def snapshot(*roots):
    """{path: bytes} of every file under the roots (a missing root is recorded as absent)."""
    out = {}
    for root in roots:
        root = Path(root)
        if root.is_file():
            out[str(root)] = root.read_bytes()
        elif root.is_dir():
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    out[str(p)] = p.read_bytes()
        else:
            out[str(root)] = None
    return out


# ------------------------------------------------------------------ registry texts
def off_registry():
    return (REPO / "main_models.yaml").read_bytes().decode("utf-8")


def _restore_lines(text):
    lines, done = text.split("\n"), set()
    start = lines.index(f"  - name: {ENTRY}")
    for i in range(start, len(lines)):
        if i > start and lines[i].startswith("  - name: "):
            break
        for prefix, restored in C177.items():
            if lines[i].startswith(prefix) and prefix not in done:
                lines[i] = restored
                done.add(prefix)
    assert len(done) == 3, f"the C177 lines moved: {set(C177) - done}"
    return lines, start


def overlay_on(off_text):
    """S's ON overlay: the three C177 lines restored in place (`bench.p426_overlay`; S's `registry-on.yaml`)."""
    return "\n".join(_restore_lines(off_text)[0])


def fork_overlay_on(off_text):
    """POST-REVEAL tw-4 (C241 / P511): the fork's own B4 rule, `registry_states.overlay_on(OFF, fixture, entry)`, loaded from
    this copy's `src/mlx-vlm` exactly as `bench.p426_overlay.load_registry_states` loads it from a worktree."""
    from bench import p426_overlay

    rs = p426_overlay.load_registry_states(REPO)
    on, _ = rs.overlay_on(off_text, rs.fixture_text(REPO / "src" / "mlx-vlm" / "mlx_vlm" / "tests" / "fixtures"), ENTRY)
    return on


def restored_registry(off_text, note=PROVISIONAL_NOTE):
    """POST-REVEAL tw-4 (C241 / P511): the ON arm's committed registry = the fork's `overlay_on(OFF)` + exactly one
    `<child indent># PROVISIONAL P426[ free text]` line as the first child of the entry's `generation_defaults:`."""
    lines = fork_overlay_on(off_text).split("\n")
    start = lines.index(f"  - name: {ENTRY}")
    gd = next(i for i in range(start, len(lines)) if lines[i] == "    generation_defaults:")
    lines.insert(gd + 1, note)
    return "\n".join(lines)


def restored_seeding(text):
    """POST-REVEAL tw-4 (C241 / P511): OFF with the exact reverse of C177's seeding hunk."""
    assert text.count(SEEDING_OFF) == 1
    return text.replace(SEEDING_OFF, SEEDING_ON)


# ------------------------------------------------------------------ venvs
def make_venv(path, versions):
    """A real venv (no pip) whose only installed distributions are `versions` (dist-info METADATA, the files
    `importlib.metadata` / `uv pip list` read); built once per directory, copied (symlinks kept) for its siblings."""
    tpl = Path(path).parents[2] / ".t3-venv-template" if len(Path(path).parents) > 2 else None
    if tpl is None or not tpl.exists():
        target = tpl or Path(path)
        REAL_RUN([sys.executable, "-m", "venv", "--without-pip", str(target)], check=True, capture_output=True)
    if tpl is not None:
        shutil.copytree(tpl, path, symlinks=True)
    for name, version in versions.items():
        set_version(path, name, version)
    return path


def site_packages(venv):
    return next(Path(venv).glob("lib/python3*/site-packages"))


def set_version(venv, name, version):
    sp = site_packages(venv)
    norm = name.replace("-", "_")
    for d in sp.glob(f"{norm}-*.dist-info"):
        shutil.rmtree(d)
    d = sp / f"{norm}-{version}.dist-info"
    d.mkdir()
    (d / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    (d / "INSTALLER").write_text("uv\n")
    (d / "RECORD").write_text("")


def installed(venv):
    out = {}
    for d in site_packages(venv).glob("*.dist-info"):
        meta = dict(line.split(": ", 1) for line in (d / "METADATA").read_text().splitlines() if ": " in line)
        out[meta["Name"]] = meta["Version"]
    return out


# ------------------------------------------------------------------ fork / mlx-serve checkouts
FAKE_ORCHESTRATE = f'''"""T3 frozen-test stand-in for the fork's p369_phase2.orchestrate (pins only)."""
def load_pins(path=None):
    return {{{ENTRY!r}: {{"target": {{"hf_path": "caslca/{ENTRY}"}}, "drafter": {{"hf_path": {DRAFTER!r}}}}}}}


def weights_record(hf_path):
    return {{"hf_path": hf_path}}


def pins_problems(pins, pick, target, drafter):
    return []
'''
FAKE_QUALIFY = '''"""T3 frozen-test stand-in for the fork's p369_phase2.qualify (the battery parser only; the script never runs)."""
def battery_intervals(log_text, start, end):
    return []
'''


def make_checkout(path, sha, *, fork=False):
    """A git directory whose detached HEAD is `sha` (what `git -C <path> rev-parse HEAD` reports)."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    git(path, "init", "-q")
    (path / ".git" / "HEAD").write_text(sha + "\n")
    if fork:
        pkg = path / "dev" / "p369_phase2"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "orchestrate.py").write_text(FAKE_ORCHESTRATE)
        (pkg / "qualify.py").write_text(FAKE_QUALIFY)
        for rel in FORK_OVERLAY_FILES:  # POST-REVEAL tw-4: the real B4 rule and its golden fixture, byte-copied
            (path / rel).parent.mkdir(parents=True, exist_ok=True)
            (path / rel).write_bytes((REPO / "src" / "mlx-vlm" / rel).read_bytes())
    return path


def tracked_files():
    """The committed inputs a P426 leg plans from (ids.json and its M40 sources: `bench/p426_ids.py:16-23`)."""
    from bench import p426_ids

    out = {rel: (REPO / rel).read_bytes() for rel in [p426_ids.OUT, *p426_ids.SOURCES.values(), SEEDING_TEST]}
    out["uv.lock"] = b"version = 1\n# T3 frozen-test stand-in\n"
    out["benchmark/requirements-bench.lock"] = b"# T3 frozen-test stand-in\nmlx==0.32.4\n"
    out["README.md"] = b"stack\n"
    return out


def populate_untracked(wt, *, vlm, serve, versions):
    make_checkout(wt / "src" / "mlx-vlm", vlm, fork=True)
    make_checkout(wt / "src" / "mlx-serve", serve)
    (wt / "logs").mkdir(exist_ok=True)
    for v in VENVS:
        if (wt / v).exists():
            shutil.rmtree(wt / v)
        make_venv(wt / v, versions.get(v, versions) if isinstance(versions.get(v), dict) else versions)


def make_stack(wt, registry_text, *, vlm, serve, versions=S2_VERSIONS, extra=None):
    init_repo(wt)
    for rel, data in {**tracked_files(), **(extra or {})}.items():
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_bytes(data)
    (wt / "main_models.yaml").write_bytes(registry_text.encode("utf-8"))
    (wt / ".gitignore").write_text("logs/\n.venv/\n.venv-bench/\nsrc/\n")  # src/: stand-ins for the two gitlinks
    head = commit_all(wt, "stack")
    populate_untracked(wt, vlm=vlm, serve=serve, versions=versions)
    return head


# ------------------------------------------------------------------ the S world (label `s`, today's interface)
@dataclasses.dataclass
class SWorld:
    tmp: Path
    wd: Path
    main: Path
    root: Path
    overlay: Path
    frozen: Path
    out: Path


def make_s_world(tmp):
    tmp = Path(tmp).resolve()
    wd, main = tmp / "wd", tmp / "main"
    root = wd / "worktrees" / "stack-p426"
    (main / "benchmark" / "results").mkdir(parents=True, exist_ok=True)
    off = off_registry()
    head = make_stack(root, off, vlm=S_PINS["mlx_vlm"], serve=S_PINS["mlx_serve"],
                      versions={"mlx": "0.32.3", "mlx-metal": "0.32.3"})
    overlay = wd / "p426" / "registry-on.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    on = overlay_on(off)
    overlay.write_bytes(on.encode("utf-8"))
    frozen = wd / "p426" / "frozen.json"
    frozen.write_text(json.dumps(dict(stack_head=head, stack_clean=True, mlx_vlm=S_PINS["mlx_vlm"],
                                      mlx_serve=S_PINS["mlx_serve"], registry_off_sha=sha256_text(off),
                                      registry_on_sha=sha256_text(on), production_ref=S_PINS["production_ref"]), indent=1))
    return SWorld(tmp=tmp, wd=wd, main=main, root=root, overlay=overlay, frozen=frozen, out=wd / "p426" / "wave1")


# POST-REVEAL tw-3: the S-world support checks pass `--build s` where the sequencer has the option (spec §4: required).
def s_build():
    """`"s"` when `bench.p426_wave1` offers `--build` (its own `--help`), else None (B0, which has no label)."""
    from bench import p426_wave1

    _, text = run_main(p426_wave1.main, ["--help"])
    return "s" if "--build" in text else None


def s_argv(w, *, build=None, axes=None):
    """Today's sequencer argv (`bench/p426_wave1.py:5-6,142-151`), optionally with `--build`."""
    argv = ["--stack-root", str(w.root), "--main-root", str(w.main), "--workdir", str(w.wd), "--registry-on", str(w.overlay),
            "--out", str(w.out)]
    if axes:
        argv += ["--axes", ",".join(axes)]
    return argv + (["--build", build] if build else [])


def committed_evidence(main):
    """{rel: bytes} of everything a harvest left under `main/benchmark/results` (what `main` commits)."""
    base = Path(main)
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted((base / "benchmark" / "results").rglob("*")) if p.is_file()}


def s_leg_names():
    return [f"{a}-p426-{arm}-smoke" for a in AXES for arm in ARMS] + [
        f"{a}-p426-{arm}-b{b}" for a in AXES for arm, b in (("off", 1), ("on", 1), ("on", 2), ("off", 2))]


# ------------------------------------------------------------------ the S′ world (label `s2`, two committed arms)
@dataclasses.dataclass
class ArmsWorld:
    tmp: Path
    wd: Path
    main: Path
    off: Path
    on: Path
    frozen: Path
    out: Path
    pins: dict


def make_arms_world(tmp, *, pins=S2_PINS, versions=S2_VERSIONS, extra=None):
    """`$STACK_WORKDIR/worktrees/stack-p426-s2-off` (= the frozen commit) and `…-s2-on` (= it + the restore commit on
    `p426-on-s2`, a linked worktree), each with its own fork / mlx-serve checkout and venvs; `frozen.s2.json` written from
    the live state (spec §4 'The frozen record under b'). `extra` = further tracked files of the frozen commit (S's
    harvested evidence, as `main` commits it)."""
    tmp = Path(tmp).resolve()
    wd, main = tmp / "wd", tmp / "main"
    off_wt, on_wt = wd / "worktrees" / "stack-p426-s2-off", wd / "worktrees" / "stack-p426-s2-on"
    (main / "benchmark" / "results").mkdir(parents=True, exist_ok=True)
    make_stack(off_wt, off_registry(), vlm=pins["mlx_vlm"], serve=pins["mlx_serve"], versions=versions, extra=extra)
    git(off_wt, "worktree", "add", "-q", "-b", "p426-on-s2", str(on_wt))
    (on_wt / "main_models.yaml").write_bytes(restored_registry(off_registry()).encode("utf-8"))
    seeding = on_wt / SEEDING_TEST
    seeding.write_text(restored_seeding(seeding.read_text()))
    commit_all(on_wt, "P426 restore (plan §11)")
    populate_untracked(on_wt, vlm=pins["mlx_vlm"], serve=pins["mlx_serve"], versions=versions)
    w = ArmsWorld(tmp=tmp, wd=wd, main=main, off=off_wt, on=on_wt, frozen=wd / "p426" / "frozen.s2.json",
                  out=wd / "p426" / "wave1.s2", pins=dict(pins))
    write_frozen_s2(w)
    return w


# POST-REVEAL tw-3: the designer's ruling on the record's field names (the names the candidate reads).
FROZEN_S2_FIELDS = ("build", "stack_head_off", "stack_head_on", "stack_clean_off", "stack_clean_on", "mlx_vlm", "mlx_serve",
                    "production_ref", "registry_off_sha", "registry_on_sha", "uv_lock_sha256", "bench_lock_sha256", "venvs")


def frozen_s2_doc(w, **override):
    """The `s2` frozen record: spec §4 field list, under the field names the designer ruled (POST-REVEAL tw-3):
    `FROZEN_S2_FIELDS`, `venvs.{off,on}.{.venv,.venv-bench}.{mlx, mlx-metal, transformers, huggingface-hub, datasets,
    mlx-audio}`."""
    doc = dict(
        build="s2",
        stack_head_off=git(w.off, "rev-parse", "HEAD"), stack_head_on=git(w.on, "rev-parse", "HEAD"),
        stack_clean_off=git(w.off, "status", "--porcelain", "--untracked-files=no") == "",
        stack_clean_on=git(w.on, "status", "--porcelain", "--untracked-files=no") == "",
        mlx_vlm=w.pins["mlx_vlm"], mlx_serve=w.pins["mlx_serve"], production_ref=w.pins["production_ref"],
        registry_off_sha=sha256_file(w.off / "main_models.yaml"), registry_on_sha=sha256_file(w.on / "main_models.yaml"),
        uv_lock_sha256=sha256_file(w.off / "uv.lock"),
        bench_lock_sha256=sha256_file(w.off / "benchmark/requirements-bench.lock"),
        venvs={arm: {v: {d: installed(wt / v).get(d) for d in S2_VERSIONS} for v in VENVS}
               for arm, wt in (("off", w.off), ("on", w.on))},
    )
    doc.update(override)
    return doc


def write_frozen_s2(w, **override):
    w.frozen.parent.mkdir(parents=True, exist_ok=True)
    w.frozen.write_text(json.dumps(frozen_s2_doc(w, **override), indent=1))
    return w.frozen


def s2_argv(w, *, build="s2", axes=None, extra=()):
    argv = ["--build", build, "--stack-root-off", str(w.off), "--stack-root-on", str(w.on), "--main-root", str(w.main),
            "--workdir", str(w.wd), "--out", str(w.out)]
    if axes:
        argv += ["--axes", ",".join(axes)]
    return argv + list(extra)


def s2_leg_names(axes=AXES, b="s2"):
    return [f"{a}-p426{b}-{arm}-smoke" for a in axes for arm in ARMS] + [
        f"{a}-p426{b}-{arm}-b{n}" for a in axes for arm, n in (("off", 1), ("on", 1), ("on", 2), ("off", 2))]


# ------------------------------------------------------------------ the fake box (every effect a leg / sequencer has)
class FakeProc:
    def __init__(self, pid, rc=None):
        self.pid, self.returncode, self._rc = pid, None, rc

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = self._rc if self._rc is not None else 0
        return self.returncode

    def terminate(self):
        self.returncode = -15 if self.returncode is None else self.returncode

    kill = terminate


class FakeChainOps:
    """`bench.chain_ops.ChainOps` stand-in: records which worktree / registry the leg's router serves; the served
    registry decides the arm (a router serving `draft_kind: mtp` engages the drafter)."""

    box = None

    def __init__(self, repo, workdir, overlay, log, **kw):
        self.repo, self.wd, self.overlay, self.kw = Path(repo), Path(workdir), str(overlay), kw
        self.router_config_sha = None
        self.box.ops.append(self)

    def power_ok(self):
        return True

    def busy_procs(self):
        return []

    def start_state(self):
        return {"watts": 140, "volts": 28, "batt": 80, "busy": [], "orphans_clean": True}

    def env_base(self):
        env = {k: v for k, v in os.environ.items() if k != "APC_ENABLED"}
        env.update(STACK_WORKDIR=str(self.wd), MLX_SERVE_CONFIG=self.overlay, MLX_VLM_CACHE_SESSION_MAX="1")
        return env

    def _entry(self):
        doc = yaml.safe_load(Path(self.overlay).read_text())
        return {m["name"]: m for m in doc["models"]}[ENTRY]

    def start_router(self):
        self.router_config_sha = sha256_text(Path(self.overlay).read_bytes().decode("utf-8"))
        self.box.serving = self
        return 101

    def engaged(self):
        return self._entry().get("draft_kind") == "mtp"

    def load(self, model):
        e = self._entry()
        cmd = f"202 python -m mlx_vlm.server --model {e['hf_path']} --port 8091"
        if e.get("draft_kind") == "mtp":
            cmd += f" --draft-kind mtp --draft-model {e['draft_model']} --mtp-verify-scan {e['mtp_verify_scan']}"
        return {"pid": 202, "create_time": 1.0, "cmdline": cmd}

    def worker_ident(self, model):
        return {"pid": 202, "create_time": 1.0}

    def router_ok(self):
        return True

    def stop_stack(self):
        self.box.serving = None
        return 0

    def listeners(self, port=8000):
        return []


def _flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


class Box:
    """Installs the fakes (monkeypatch): ChainOps, the driver / watcher / pmset processes, the in-process leg launched by
    the sequencer, and a virtual monotonic clock (the 600 s idle gaps take no time). git and venv interpreters run for
    real. Hooks: `before_leg[name]` / `during_driver[name]` callables mutate the world at those points."""

    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self.ops, self.serving, self.drivers, self.launches, self.legs_run = [], None, [], [], []
        self.before_leg, self.during_driver, self.qualify_overlay = {}, {}, {}
        self.t, self.n = 1000.0, 0
        FakeChainOps.box = self
        from bench import chain_ops, p426_leg

        monkeypatch.setattr(chain_ops, "ChainOps", FakeChainOps)
        monkeypatch.setattr(p426_leg, "ChainOps", FakeChainOps, raising=False)  # a module-level import, if the leg has one
        monkeypatch.setattr(subprocess, "run", self._run)
        monkeypatch.setattr(subprocess, "Popen", self._popen)
        monkeypatch.setattr(time, "sleep", self._sleep)
        monkeypatch.setattr(time, "monotonic", self._monotonic)
        saved_path = list(sys.path)
        saved_mods = {k: v for k, v in sys.modules.items() if k == "p369_phase2" or k.startswith("p369_phase2.")}
        for k in saved_mods:
            monkeypatch.delitem(sys.modules, k)
        self._restore = (saved_path, saved_mods)

    def close(self):
        saved_path, saved_mods = self._restore
        for k in [k for k in sys.modules if k == "p369_phase2" or k.startswith("p369_phase2.")]:
            del sys.modules[k]
        sys.modules.update(saved_mods)
        sys.path[:] = saved_path

    # -- clock
    def _sleep(self, s):
        self.t += max(0.0, float(s))
        REAL_SLEEP(0)

    def _monotonic(self):
        self.t += 0.001
        return self.t

    # -- processes
    @staticmethod
    def _is_driver(argv):
        return any(str(a).endswith(("run.py", "vision_gate.py", "qualify.py")) or a == "bench.run_reasoning" for a in argv)

    FORBIDDEN = ("mlx_vlm.server", "mlx-serve start", "opencode run", "run.py generate", "run_tg1_probe", "runserver.sh")

    def _guard(self, argv):
        line = " ".join(str(x) for x in argv) if isinstance(argv, (list, tuple)) else str(argv)
        hit = [f for f in self.FORBIDDEN if f in line]
        if hit:
            raise AssertionError(f"T3 frozen tests never start {hit}: {line[:300]}")

    def _run(self, argv, *a, **kw):
        if isinstance(argv, (list, tuple)) and argv and argv[0] == "pmset":
            return subprocess.CompletedProcess(argv, 0, stdout=AC_LINE, stderr="")
        if isinstance(argv, (list, tuple)) and self._is_driver([str(x) for x in argv]):
            rc = self.driver([str(x) for x in argv], dict(kw.get("env") or os.environ), kw.get("cwd"))
            return subprocess.CompletedProcess(argv, rc, stdout="", stderr="")
        self._guard(argv)
        return REAL_RUN(argv, *a, **kw)

    def _popen(self, argv, *a, **kw):
        sargv = [str(x) for x in argv] if isinstance(argv, (list, tuple)) else [str(argv)]
        if any(x.endswith("bench_watch.py") for x in sargv):
            out = _flag(sargv, "--out")
            if out:
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_text("===== 2026-10-27 01:00:00 driver=alive\n")
            self.n += 1
            return FakeProc(9000 + self.n)
        if "bench.p426_leg" in sargv:
            return self._leg(sargv, kw)
        self._guard(argv)
        return REAL_POPEN(argv, *a, **kw)

    def _leg(self, argv, kw):
        from bench import p426_leg

        args = argv[argv.index("bench.p426_leg") + 1:]
        self.launches.append(dict(argv=argv, cwd=str(kw.get("cwd")) if kw.get("cwd") is not None else None))
        name = self._leg_name(args)
        hook = self.before_leg.get(name)
        if hook:
            hook()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rc = p426_leg.main(args)
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 2
        self.legs_run.append(dict(name=name, rc=rc, out=buf.getvalue()))
        f = kw.get("stdout")
        if f is not None and hasattr(f, "write"):
            f.write(buf.getvalue().encode())
            f.flush()
        self.n += 1
        return FakeProc(5000 + self.n, rc)

    @staticmethod
    def _leg_name(args):
        build = _flag(args, "--build") or "s"
        tag = "p426" if build == "s" else f"p426{build}"
        sel = "smoke" if "--smoke" in args else f"b{_flag(args, '--block')}"
        return f"{_flag(args, '--axis')}-{tag}-{_flag(args, '--arm')}-{sel}"

    # -- the drivers (what the real run.py / vision_gate.py / run_reasoning / qualify.py would leave behind)
    def driver(self, argv, env, cwd):
        prefix = env.get("MLX_BENCH_SESSION_PREFIX")
        rec = dict(argv=argv, cwd=str(cwd) if cwd is not None else None, prefix=prefix,
                   serving=str(self.serving.repo) if self.serving else None,
                   served_config=self.serving.overlay if self.serving else None)
        self.drivers.append(rec)
        hook = self.during_driver.get(prefix[len("p426-"):] if prefix else _flag(argv, "--out"))
        if hook:
            hook()
        if any(x.endswith("qualify.py") for x in argv):
            return self._qualify(argv)
        on = self.serving is not None and self.serving.engaged()
        draft = ENGAGED if on else PLAIN
        records, rows = [], []
        k = 0

        def req(extra=None):
            nonlocal k
            k += 1
            sid, pt = f"{prefix}-{k}", 100 + k
            records.append((sid, pt, draft if extra is None else extra))
            return dict(session_id=sid, prompt_tokens=pt, draft=dict(draft) if extra is None else None, completion_tokens=5)

        if any(x.endswith("run.py") for x in argv):
            script = Path(next(x for x in argv if x.endswith("run.py")))
            axis, tune = _flag(argv, "--benches"), _flag(argv, "--tune")
            ids = _flag(argv, "--ids").split("=", 1)[1].split(":")
            res = script.parent / "results" / ENTRY
            for i in ids:
                rows.append(dict(id=i, content=f"answer {i}", sampler_seed=sample_seed(i, 0, base=0), sample=0, seed_base=0,
                                 **req()))
            path = res / f"{axis}.{tune}.jsonl"
            manifest = res / f"{axis}.{tune}.manifest.json"
        elif any(x.endswith("vision_gate.py") for x in argv):
            path = Path(_flag(argv, "--out"))
            for i in _flag(argv, "--ids").split(":"):
                first = req()
                rows.append(dict(id=i, description=f"image {i}", seed=sample_seed(i, 0), **first,
                                 turn2=dict(seed=sample_seed(i, 1), **req())))
            manifest = Path(str(path).replace(".jsonl", ".manifest.json"))
        else:  # bench.run_reasoning
            repo = Path(argv[0]).parents[2]
            ids = json.loads((repo / "benchmark/results/p426/ids.json").read_text())
            seeds = ids["axes"]["reasoning"]["request_seeds"]
            t0, n, tune = int(_flag(argv, "--task-seed-base")), int(_flag(argv, "--samples")), _flag(argv, "--out-tag")
            path = repo / "benchmark" / "results" / ENTRY / f"reasoning.{tune}.partial.jsonl"
            for t in range(t0, t0 + n):
                rows.append(dict(seed=t, content=f"chain {t}", score=1.0, sampler_seed=seeds[str(t)], **req()))
            cal = f"{prefix}-cal"
            records.append((cal, 9, {}))
            path.parent.mkdir(parents=True, exist_ok=True)
            Path(f"{path}.provenance.json").write_text(json.dumps({"calibration_session_id": cal}))
            manifest = None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        if manifest is not None:
            manifest.write_text(json.dumps({"tune": path.name, "argv": argv}))
        log = self.serving.repo / "logs" / "mlx_vlm.log"
        with log.open("a") as f:
            for sid, pt, d in records:
                f.write(f"{TS}Request started: endpoint=/chat/completions model=m stream=True in_flight=1\n")
                dr = (f" draft_kind=mtp draft_n={d['draft_n']} draft_n_accepted={d['draft_n_accepted']} "
                      f"draft_rounds={d['draft_rounds']}") if d.get("draft_n") is not None else ""
                f.write(f"{TS}Request completed: endpoint=/chat/completions model=m stream=True backend=cached_session "
                        f"session={sid} cached_tokens=0 prompt_tokens={pt} generated_tokens=5 elapsed=1.000s prefill=1.0 "
                        f"tok/s decode=1.0 tok/s finish_reason=stop in_flight=0{dr}\n")
        return 0

    def _qualify(self, argv):
        out, arm, stack = Path(_flag(argv, "--out")), _flag(argv, "--predictor"), Path(_flag(argv, "--stack-root"))
        out.mkdir(parents=True, exist_ok=True)
        registry = (stack / "main_models.yaml").read_bytes()
        if arm == "on":
            (out / f"overlay-{ENTRY}.yaml").write_bytes(self.qualify_overlay.get(str(out), registry))
        report = dict(predictor=arm, reviewed_head=_flag(argv, "--reviewed-head"), production=_flag(argv, "--production-ref"),
                      registry_sha256=hashlib.sha256(registry).hexdigest(),
                      entries={_flag(argv, "--entry"): {"status": "COMPLETED", "arm": f"mtp_{arm}"}})
        (out / "report.json").write_text(json.dumps(report, indent=1))
        return 0


def run_main(fn, argv):
    """(rc, stdout + stderr) of a CLI `main`; argparse's SystemExit is an exit code like any other."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = fn(argv)
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 2)
    return rc, out.getvalue() + err.getvalue()


def text_of(rc_text, *paths):
    """Everything a refusal could be read from: the CLI output plus the named files (sequence.log, receipts)."""
    parts = [rc_text]
    for p in paths:
        p = Path(p)
        if p.is_file():
            parts.append(p.read_text(errors="replace"))
        elif p.is_dir():
            parts += [q.read_text(errors="replace") for q in sorted(p.rglob("*")) if q.is_file()]
    return "\n".join(parts)


def receipt(dir_, name):
    p = Path(dir_) / f"{name}.receipt.json"
    return json.loads(p.read_text()) if p.exists() else None


def all_receipts(dir_, name):
    d = Path(dir_)
    return [json.loads(p.read_text()) for p in [d / f"{name}.receipt.json", *sorted(d.glob(f"{name}.refused-*.receipt.json"))]
            if p.exists()]


# ------------------------------------------------------------------ pytest fixtures
import pytest  # noqa: E402


@pytest.fixture
def box(monkeypatch):
    b = Box(monkeypatch)
    try:
        yield b
    finally:
        b.close()


def drive_once(box, wd, wt, axis, arm, sel, *, served=None):
    """One planned driver call (today's planner, `bench/p426_plan.py:36-98`) served from `wt` through the fake box:
    returns (plan, rows, the server-log lines the call appended)."""
    from bench import p426_leg, p426_plan

    plan = p426_plan.plan_leg(wt, axis, arm, None if sel == "smoke" else sel, smoke=sel == "smoke", workdir=wd,
                              reviewed_head="v" * 40, production_ref="p" * 40)
    ops = FakeChainOps(wt, wd, served or wt / "main_models.yaml", lambda m: None)
    ops.start_router()
    log = wt / "logs" / "mlx_vlm.log"
    before = log.stat().st_size if log.exists() else 0
    name = f"{axis}-p426-{arm}-{sel if sel == 'smoke' else f'b{sel}'}"
    box.driver(plan["driver_argv"], dict(MLX_BENCH_SESSION_PREFIX=f"p426-{name}"), plan["cwd"])
    ops.stop_stack()
    lines = log.read_bytes()[before:].decode().splitlines() if log.exists() else []
    rows = p426_leg.read_rows(plan["rows_path"]) if plan["rows_path"] else []
    return plan, rows, lines


# ------------------------------------------------------------------ the local gate's fork fixtures
OLD_REF = "952d4f6b"  # `bench/tests/test_local_gate.py:53`
OLD_WORKFLOW = f"name: upstream-parity\non: [push]\nenv:\n  # the last merged upstream ref\n  UPSTREAM_SYNC_REF: {OLD_REF}\njobs: {{}}\n"
OLD_AUDITS = [("check_upstream_parity.py", ()), ("check_upstream_symbols.py", ()), ("check_upstream_deletions.py", ("--strict",)),
              ("check_fork_markers.py", ()), ("check_dead_helpers.py", ()), ("check_body_divergence.py", ()),
              ("check_upstream_registries.py", ()), ("check_call_arguments.py", ())]
S2_REF = "2ceff4c1"  # `src/mlx-vlm/.upstream-sync-ref`
S2_AUDITS = OLD_AUDITS + [("check_upstream_test_copies.py", ())]  # `src/mlx-vlm/dev/ci.py:44-54`


def ci_py(audits):
    """A `dev/ci.py` in the fork's format (`src/mlx-vlm/dev/ci.py:42-54`)."""
    body = "".join(f"    ({name!r}, {tuple(extra)!r}),\n" for name, extra in audits)
    return ('"""Local CI (T3 frozen-test fixture in the fork\'s format)."""\n\nfrom typing import List\n\n'
            f"AUDITS: List[tuple] = [\n{body}]\n")


def sync_ref_file(ref):
    """`.upstream-sync-ref` in the fork's format (comment lines, then the ref)."""
    return ("# The upstream ref the fork last merged. dev/ci.py audits against it.\n"
            f"# Bump it in the same commit as every upstream sync.\n{ref}\n")


def fork_commit(repo, *, workflow=None, ci=None, sync_ref=None, msg="fork"):
    """Commit one fork layout: present files written, `None` files removed."""
    files = {".github/workflows/upstream-parity.yml": workflow, "dev/ci.py": ci, ".upstream-sync-ref": sync_ref}
    for rel, text in files.items():
        p = repo / rel
        if text is None:
            if p.exists():
                p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    names = [n for n, _ in ast_audits(ci)] if ci else []
    for name in names:
        (repo / "dev" / name).write_text("raise SystemExit(0)\n")
    return commit_all(repo, msg)


def ast_audits(text):
    import ast

    tree = ast.parse(text)
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if isinstance(node, ast.Assign) else None)
        if getattr(target, "id", None) == "AUDITS":
            return ast.literal_eval(node.value)
    return []


def make_fork_repo(path):
    init_repo(path)
    git(path, "remote", "add", "origin", "git@github.com:ivan-avramov/mlx-vlm")  # `bench/local_gate.py:30` (canonical)
    (path / "pyproject.toml").write_text("[project]\nname='mlx-vlm'\n")
    (path / "uv.lock").write_text("version = 1\n")
    return path


def old_layout(path):
    """The fork at S: the ref in the parity workflow, eight audits."""
    repo = make_fork_repo(path)
    return repo, fork_commit(repo, workflow=OLD_WORKFLOW, ci=ci_py(OLD_AUDITS), msg="old layout")


def s2_layout(path):
    """The fork at S′: the real `dev/ci.py` and `.upstream-sync-ref` bytes, no parity workflow. POST-REVEAL tw-5: C242 pin
    move — the bytes are read from the tree's `src/mlx-vlm` (`c688e722` here, `1c7c8fa1` in the candidate; identical there)."""
    repo = make_fork_repo(path)
    real = REPO / "src" / "mlx-vlm"
    return repo, fork_commit(repo, ci=(real / "dev" / "ci.py").read_text(), sync_ref=(real / ".upstream-sync-ref").read_text(),
                             msg="s2 layout")


class GateRunner:
    """The mocked step runner (`bench/tests/test_local_gate.py:93-113`): records argvs, writes the junit file."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, cwd, env):
        self.calls.append((list(argv), str(cwd)))
        for a in argv:
            if str(a).startswith("--junitxml="):
                Path(str(a).split("=", 1)[1]).write_text("<testsuites><testsuite></testsuite></testsuites>")
        return 0, ""

    def audits(self):
        """[(script, upstream ref, extra args)] of every audit invocation, in order."""
        out = []
        for argv, _ in self.calls:
            if len(argv) > 3 and str(argv[1]).startswith("dev/check_") and "--upstream-ref" in argv:
                i = argv.index("--upstream-ref")
                out.append((str(argv[1])[len("dev/"):], argv[i + 1], tuple(argv[i + 2:])))
        return out


def gate_run(tmp, repo, sha):
    from bench import local_gate as G

    baselines = Path(tmp) / "baselines"
    baselines.mkdir(parents=True, exist_ok=True)
    (baselines / "mlx-vlm.skips.txt").write_text("")
    runner = GateRunner()
    path = G.run("mlx-vlm", sha, live=repo, gate_dir=Path(tmp) / "gate", baselines=baselines, runner=runner,
                 busy=lambda: [], dirty=lambda scratch, after_step: False, artifacts=lambda d: True)
    return json.loads(Path(path).read_text()), runner


# ------------------------------------------------------------------ naming / panel fixtures
def fragment():
    """A registry-name fragment built at runtime (a literal one would trip the repository's own naming hook)."""
    return "-".join(ENTRY.split("-")[2:4])


def names_root(tmp):
    root = Path(tmp) / "names"
    root.mkdir(exist_ok=True)
    (root / "main_models.yaml").write_bytes((REPO / "main_models.yaml").read_bytes())
    return str(root)


def added_line_diff(path, line):
    """A unified diff adding one line at `path` (the shape `git diff --cached --unified=0` emits)."""
    return f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+{line}\n"


def verdict(item, order, judge, choice, on_tune, off_tune, on_is_a=True):
    """An ingested verdict row (`bench/tests/test_p426_panel.py:117-120`) for the given tunes."""
    on, off = f"{ENTRY}@{on_tune}::{item}", f"{ENTRY}@{off_tune}::{item}"
    a, b = (on, off) if on_is_a else (off, on)
    return {"item_id": item, "order": order, "judge": judge, "a_key": a, "b_key": b, "choice": choice}


# ------------------------------------------------------------------ one whole S′ Wave-1 run (module scope)
@dataclasses.dataclass
class Run:
    world: object
    box: Box
    rc: int
    text: str

    def why(self):
        return self.text + "\n".join(f"{r['name']} rc {r['rc']}: {r['out'][-600:]}" for r in self.box.legs_run)


def run_sequencer(world, box, argv, monkeypatch):
    from bench import p426_wave1

    monkeypatch.setenv("STACK_WORKDIR", str(world.wd))
    rc, text = run_main(p426_wave1.main, argv)
    return Run(world=world, box=box, rc=rc, text=text)


@pytest.fixture(scope="module")
def s2_full_run(tmp_path_factory):
    """The success path of spec §4: `bench.p426_wave1 --build s2 --stack-root-off … --stack-root-on … --out
    $STACK_WORKDIR/p426/wave1.s2` over both arms' committed worktrees — all 30 legs."""
    mp = pytest.MonkeyPatch()
    b = Box(mp)
    try:
        w = make_arms_world(tmp_path_factory.mktemp("s2run"))
        yield run_sequencer(w, b, s2_argv(w), mp)
    finally:
        b.close()
        mp.undo()


def launched_names(box):
    return [r["name"] for r in box.legs_run]


def assert_refused_before_launch(run, *, allow_usage=False):
    """Refused: nonzero, no leg launched, no S′ run file harvested; unless `allow_usage`, a refusal of the tool itself
    (an argparse usage error is the baseline's reaction to the new options)."""
    assert run.rc not in (0, None), run.why()
    assert run.box.launches == [] and run.box.legs_run == [], run.why()
    assert not (run.world.main / "benchmark/results/p426/wave1.s2/run").exists(), run.why()
    if not allow_usage:
        assert "usage:" not in run.text, run.text


# POST-REVEAL tw-3: a refusal must be shown to be its own check's — the same world without the defect gets past it.
def assert_twin_runs(w, box, monkeypatch, undo, axes=("m1",)):
    """The control twin: `undo()` removes exactly the defect (and rewrites nothing else); the same world, into a fresh
    `--out`, then runs every leg of `axes` VALID — so the refusal before it was caused by the defect alone."""
    undo()
    w.out = w.wd / "p426" / f"wave1.s2.twin{len(box.launches)}"
    before = len(box.legs_run)
    run = run_sequencer(w, box, s2_argv(w, axes=list(axes)), monkeypatch)
    assert run.rc == 0, "control twin (defect removed) did not run: " + run.why()
    assert len(box.legs_run) - before == 6 * len(axes), run.why()
    return run


def recommit_on(w, *, registry=None, seeding=None, files=None, chmod=None, commits=1):
    """Replace the ON arm's restore commit (reset to the OFF head, write, commit) and rewrite a self-consistent record."""
    git(w.on, "reset", "-q", "--hard", git(w.off, "rev-parse", "HEAD"))
    (w.on / "main_models.yaml").write_text(registry if registry is not None else restored_registry(off_registry()))
    seed = w.on / SEEDING_TEST
    seed.write_text(seeding if seeding is not None else restored_seeding(seed.read_text()))
    for rel, text in (files or {}).items():
        (w.on / rel).parent.mkdir(parents=True, exist_ok=True)
        (w.on / rel).write_text(text)
    if chmod:
        (w.on / chmod).chmod(0o755)
    commit_all(w.on, "restore")
    for i in range(commits - 1):
        commit_all(w.on, f"extra {i}")
    write_frozen_s2(w)
