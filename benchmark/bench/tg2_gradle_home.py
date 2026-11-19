"""C361 (2) / S26 §3: the one bench-owned, pre-filled Gradle home every tg2 Java item finds (`$STACK_WORKDIR/tg2-gradle-home/`,
the daemon off), instead of the operator's real `~/.gradle` (the JVM ignores `$HOME`) and a first-item network download.

  python -m bench.tg2_gradle_home prefill [--force]
  python -m bench.tg2_gradle_home check

`prefill` runs every VALID Java item of the committed tg2 universe with its reference applied (`./gradlew test`) under the agent's
spawn env, stops the daemons, then runs every item again `--offline`, and writes `PREFILL.json`. `check` (and `check_problems()`,
which `OpencodeArm.build_env` calls for every tg2 item) verifies the folder against `PREFILL.json`'s recorded facts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

GRADLE_HOME_REL = "tg2-gradle-home"
POLICY_PATH = "$STACK_WORKDIR/" + GRADLE_HOME_REL
PROPERTIES = "org.gradle.daemon=false\n"
PROPERTIES_FILE = "gradle.properties"
PREFILL_FILE = "PREFILL.json"
KIND = "tg2_gradle_home_prefill"
MANIFEST_ROOTS = ("wrapper/dists", "caches/modules-2/files-2.1")
LANG = "java"
GRADLE_TIMEOUT_S = 1800
TEST_ARGV = ("./gradlew", "test", "--console=plain")
STOP_ARGV = ("./gradlew", "--stop")
OFFLINE_ARGV = TEST_ARGV + ("--offline",)
REPO = Path(__file__).resolve().parents[2]
DEFAULT_UNIVERSE = REPO / "benchmark/m65/tg2_universe.json"


def workdir_of(workdir=None) -> Path:
    if workdir is not None:
        return Path(workdir)
    from . import paths
    return Path(paths.stack_workdir())


def folder(workdir=None) -> Path:
    return workdir_of(workdir) / GRADLE_HOME_REL


def _sha_file(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def committed_universe(path=DEFAULT_UNIVERSE):
    """(universe sha256, sorted VALID Java items) of the committed tg2 universe; ValueError when the file is not the pinned one."""
    from . import schedules
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != schedules.TG2_UNIVERSE_SHA256:
        raise ValueError("the tg2 universe file is not the pinned TG2_UNIVERSE_SHA256")
    doc = json.loads(raw)
    items = sorted(i for i, e in (doc.get("items") or {}).items()
                   if i.split("/", 1)[0] == LANG and isinstance(e, dict) and e.get("status") == "valid")
    return sha, items


def cache_manifest(root) -> list:
    """Sorted `[relative path, size]` of every file under `wrapper/dists/` and `caches/modules-2/files-2.1/` of `root`."""
    root = Path(root)
    out = []
    for rel in MANIFEST_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and not p.is_symlink():
                out.append([p.relative_to(root).as_posix(), p.stat().st_size])
    return sorted(out)


def agent_env(home, tmpdir, gradle_home) -> dict:
    """The agent's spawn env fields (`SCAFFOLD_ENV_POLICY_V2`), a scratch HOME / TMPDIR and GRADLE_USER_HOME — nothing else."""
    from .opencode_v2_core import SCAFFOLD_ENV_POLICY_V2
    return {**SCAFFOLD_ENV_POLICY_V2, "HOME": str(home), "TMPDIR": str(tmpdir).rstrip("/") + "/",
            "GRADLE_USER_HOME": str(gradle_home)}


def run_gradle(argv, *, cwd, env):
    """One gradle invocation; its rc (124 on the timeout)."""
    try:
        return subprocess.run(list(argv), cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=GRADLE_TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        return 124


def gradle_version(work):
    """The wrapper's Gradle version (`distributionUrl … gradle-<v>-bin.zip`), or None."""
    try:
        text = (Path(work) / "gradle/wrapper/gradle-wrapper.properties").read_text()
    except OSError:
        return None
    m = re.search(r"gradle-([0-9][0-9A-Za-z.\-]*?)-(?:bin|all)\.zip", text)
    return m.group(1) if m else None


def java_realpath():
    from .opencode_v2_core import SCAFFOLD_ENV_POLICY_V2
    exe = shutil.which("java", path=SCAFFOLD_ENV_POLICY_V2["PATH"])
    if exe is None:
        return None
    from . import host_env
    return host_env.portable(os.path.realpath(exe))


def _default_reference(corpus, slug, work):
    from . import tg2_materialize as mat
    root = corpus.polyglot_root()
    mat.apply_reference(root, mat.read_plan(root, LANG, slug), work)


def _exc_line(exc):
    from . import host_env
    return host_env.portable(f"{type(exc).__name__}: {' '.join(str(exc).split())[:300]}")


def prefill(*, workdir=None, force=False, universe=None, corpus=None, reference=None, run=None, clock=time.time, log=print):
    """§3 `prefill`: returns the rc (0 only when every offline pass succeeded; 2 a refusal)."""
    wd = workdir_of(workdir)
    root = folder(wd)
    if root.exists() and any(root.iterdir()) and not force:
        log(f"REFUSED: {GRADLE_HOME_REL}/ is not empty (--force removes it first)")
        return 2
    universe_sha, items = universe if universe is not None else committed_universe()
    if corpus is None:
        from . import corpus_tg2
        corpus = corpus_tg2.Tg2Corpus()
    reference = reference or _default_reference
    run = run or run_gradle
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / PROPERTIES_FILE).write_text(PROPERTIES)
    scratch = wd / "scratch" / f"tg2-gradle-prefill-{os.getpid()}-{int(clock())}"
    home, tmp = scratch / "home", scratch / "tmp"
    results, works, versions = {i: dict(id=i, online_rc=None, offline_rc=None) for i in items}, {}, set()
    stop_rc = None
    try:
        home.mkdir(parents=True)
        tmp.mkdir(parents=True)
        env = agent_env(home, tmp, root)
        for item in items:
            slug = item.split("/", 1)[1]
            work = scratch / "work" / slug
            try:
                prepared = corpus.prepare(item, work)
                reference(corpus, slug, prepared.work)
            except Exception as exc:  # noqa: BLE001  (recorded per item; the run continues)
                results[item]["error"] = _exc_line(exc)
                log(f"{item}: not prepared ({results[item]['error']})")
                continue
            works[item] = Path(prepared.work)
            versions.add(gradle_version(prepared.work))
            results[item]["online_rc"] = run(TEST_ARGV, cwd=prepared.work, env=env)
            log(f"{item}: online rc {results[item]['online_rc']}")
        if works:
            stop_rc = run(STOP_ARGV, cwd=next(iter(works.values())), env=env)
        for item, work in works.items():
            results[item]["offline_rc"] = run(OFFLINE_ARGV, cwd=work, env=env)
            log(f"{item}: offline rc {results[item]['offline_rc']}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    known = sorted(v for v in versions if v)
    doc = dict(kind=KIND, path=POLICY_PATH, properties=PROPERTIES, universe_sha256=universe_sha,
               items=[results[i] for i in items], stop_rc=stop_rc,
               gradle_version=known[0] if len(known) == 1 else known or None, java=java_realpath(),
               cache_manifest=cache_manifest(root), created=_stamp(clock()))
    _write_exclusive_json(root / PREFILL_FILE, doc)
    failed = [r["id"] for r in doc["items"] if r["offline_rc"] != 0]
    if failed or not items:
        log(f"FAILED: the offline pass did not succeed for {', '.join(failed) or 'any item (no Java item)'}")
        return 1
    log(f"PREFILLED {GRADLE_HOME_REL}/: {len(items)} Java items, offline pass rc 0 for every item")
    return 0


def _write_exclusive_json(path, doc):
    """Exclusive-create `path` with `doc` (no self-seal, S26 erratum 6: the identity's `prefill_sha256` binds the file)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def _stamp(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_problems(*, workdir=None, universe=None) -> list:
    """[] iff the folder exists, `gradle.properties` equals `PROPERTIES`, `PREFILL.json` exists for the committed universe's
    sha with exactly its VALID Java items and every offline pass rc 0, and the live cache manifest holds every recorded entry
    with its size; else the problems, the first one first. No self-seal is required (erratum 6)."""
    try:
        root = folder(workdir)
    except Exception as exc:  # noqa: BLE001  ($STACK_WORKDIR unresolvable)
        return [f"the folder cannot be located ({type(exc).__name__})"]
    if not root.is_dir():
        return [f"{POLICY_PATH}/ does not exist (run `python -m bench.tg2_gradle_home prefill`)"]
    try:
        props = (root / PROPERTIES_FILE).read_text()
    except OSError:
        return [f"{PROPERTIES_FILE} is missing"]
    if props != PROPERTIES:
        return [f"{PROPERTIES_FILE} is not exactly {PROPERTIES.strip()!r}"]
    try:
        doc = json.loads((root / PREFILL_FILE).read_text())
    except (OSError, ValueError):
        return [f"{PREFILL_FILE} is missing or unreadable (the folder was never prefilled)"]
    if not isinstance(doc, dict):
        return [f"{PREFILL_FILE} is not a prefill record"]
    try:
        universe_sha, items = universe if universe is not None else committed_universe()
    except (OSError, ValueError) as exc:
        return [f"the committed tg2 universe cannot be read ({type(exc).__name__})"]
    if doc.get("universe_sha256") != universe_sha:
        return [f"{PREFILL_FILE} was written for another tg2 universe"]
    recorded = doc.get("items") if isinstance(doc.get("items"), list) else []
    ids = [r.get("id") for r in recorded if isinstance(r, dict)]
    if len(ids) != len(recorded) or sorted(ids) != list(items) or len(set(ids)) != len(ids):
        return [f"{PREFILL_FILE} does not name exactly the universe's {len(items)} valid Java items"]
    bad = [r["id"] for r in recorded if r.get("offline_rc") != 0]
    if bad:
        return [f"the offline pass did not succeed for {', '.join(bad[:5])}"]
    manifest = doc.get("cache_manifest")
    if not isinstance(manifest, list) or not manifest:
        return [f"{PREFILL_FILE} records no cache manifest"]
    live = {rel: size for rel, size in cache_manifest(root)}
    for entry in manifest:
        if not (isinstance(entry, list) and len(entry) == 2):
            return [f"{PREFILL_FILE}: a malformed cache manifest entry"]
        rel, size = entry
        if rel not in live:
            return [f"the cache file {rel} is missing"]
        if live[rel] != size:
            return [f"the cache file {rel} has size {live[rel]}, the prefill recorded {size}"]
    return []


def identity_policy(workdir=None) -> dict:
    """The tg2 generation policy's `gradle_user_home` block: the portable path, sha256 of `gradle.properties` and of
    `PREFILL.json` (None when absent)."""
    try:
        root = folder(workdir)
    except Exception:  # noqa: BLE001
        return dict(path=POLICY_PATH, properties_sha256=None, prefill_sha256=None)
    return dict(path=POLICY_PATH, properties_sha256=_sha_file(root / PROPERTIES_FILE), prefill_sha256=_sha_file(root / PREFILL_FILE))


def main(argv=None, **kw) -> int:
    ap = argparse.ArgumentParser(prog="bench.tg2_gradle_home", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prefill")
    p.add_argument("--force", action="store_true", help="remove the folder first")
    sub.add_parser("check")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if a.cmd == "prefill":
        return prefill(force=a.force, **kw)
    problems = check_problems(**{k: v for k, v in kw.items() if k in ("workdir", "universe")})
    if problems:
        print("FAILED: " + problems[0], file=sys.stderr)
        return 1
    print(f"OK: {GRADLE_HOME_REL}/ verifies against {PREFILL_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
