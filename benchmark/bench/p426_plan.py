"""P426 stack code round 1 K3 / K4: the leg planner — everything a Wave-1 leg depends on, derived from (axis, arm, block) and the
committed `benchmark/results/p426/ids.json` (`docs/specs/p426-fable-mtp-recert.md` §4–§5): the driver argv and cwd, every output
of the leg's stem (none may exist), the planned membership, the expected seeds per row and the expected request count.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path

from bench import p426_ids
from bench.rowschema import sample_seed

ARMS = ("off", "on")
REQUEST_SEED_BASE = p426_ids.SEED  # A4's explicit per-draw request seeds (ids.json request_seeds)

# T3 §4: a build label names one serving build (S = `s`, historical; S′ = `s2`); every name a leg writes carries it
DEFAULT_BUILD = "s"
BUILD_LABEL = re.compile(r"^[a-z][a-z0-9]{0,7}$")
EXPECTED_BUILDS = {  # in code, not in the record: a self-consistent record of another build is still refused
    "s2": dict(mlx_vlm="1c7c8fa166582ac1a1c23ae9063527b2b5215b11", mlx_serve="1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d",
               production_ref="b26fa7c9faf23bc3167db3419504ef0b2b82a8e6", mlx="0.32.4"),
}
VENVS = (".venv", ".venv-bench")
VENV_PACKAGES = ("mlx", "mlx-metal", "transformers", "huggingface-hub", "datasets", "mlx-audio")
AMBIGUOUS = "more than one dist-info:"  # the value of a checked package with two or more dist-infos in one venv
SEEDING_TEST = "benchmark/bench/tests/test_opencode_probe_seeding.py"
REGISTRY = "main_models.yaml"
SEEDING_C177 = (  # C177's seeding hunk (`78a730fe`) as it stands in OFF, and its exact reverse
    "    # C177 / P369 interim: the daily-driver registry runs the picks MTP-OFF, so the real registry resolves the default\n"
    "    # scan; restore `joint_v1` + source \"registry\" when MTP is re-certified and switched back on.\n"
    '    assert man["runtime"]["mtp_verify_scan"] == "per_query"\n')
SEEDING_RESTORED = ('    assert man["runtime"]["mtp_verify_scan"] == "joint_v1"\n'
                    '    assert man["runtime"]["mtp_verify_scan_source"] == "registry"\n')


def check_build(build):
    if not isinstance(build, str) or not BUILD_LABEL.match(build):
        raise ValueError(f"build label {build!r} is not {BUILD_LABEL.pattern}")
    return build


def is_s(build):
    return build == DEFAULT_BUILD


def tune_prefix(build=DEFAULT_BUILD):
    return "p426" if is_s(build) else f"p426{check_build(build)}"


def leg_name(axis, arm, sel, build=DEFAULT_BUILD):
    return f"{axis}-{tune_prefix(build)}-{arm}-{'smoke' if sel == 'smoke' else f'b{sel}'}"


def frozen_path(workdir, build=DEFAULT_BUILD):
    """The one frozen-build record of a label: `frozen.json` (S) or `frozen.<label>.json`; no other path is ever read."""
    return Path(workdir) / "p426" / ("frozen.json" if is_s(build) else f"frozen.{check_build(build)}.json")


def m1_out_dir(workdir, tune, build=DEFAULT_BUILD):
    base = Path(workdir) / "p426"
    return (base if is_s(build) else base / check_build(build)) / "m1" / tune


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def venv_versions(root, venv):
    """{package: installed version} of `<root>/<venv>` for VENV_PACKAGES, read from the dist-info directories (no process). Two or
    more dist-infos of one package (V4) give `AMBIGUOUS` + their versions: never a pick, never equal to a pinned version."""
    found = {}
    for site in sorted((Path(root) / venv / "lib").glob("python3*/site-packages")):
        for info in site.glob("*.dist-info"):
            name, _, version = info.name[: -len(".dist-info")].rpartition("-")
            name = re.sub(r"[-_.]+", "-", name).lower()
            if name in VENV_PACKAGES:
                found.setdefault(name, []).append(version)
    return {p: (found[p][0] if len(found[p]) == 1 else f"{AMBIGUOUS} {', '.join(sorted(found[p]))}") if p in found else None
            for p in VENV_PACKAGES}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60).stdout.strip()


def arm_state(root):
    """T3 §4: what a worktree is now — both heads, tracked cleanliness, the submodules, the registry, both locks, the venvs."""
    root = Path(root)
    return dict(
        stack_head=_git(root, "rev-parse", "HEAD"),
        stack_clean=_git(root, "status", "--porcelain", "--untracked-files=no") == "",
        mlx_vlm=_git(root / "src" / "mlx-vlm", "rev-parse", "HEAD"),
        mlx_serve=_git(root / "src" / "mlx-serve", "rev-parse", "HEAD"),
        registry_sha=file_sha256(root / REGISTRY),
        uv_lock_sha256=file_sha256(root / "uv.lock"),
        bench_lock_sha256=file_sha256(root / "benchmark" / "requirements-bench.lock"),
        venvs={v: venv_versions(root, v) for v in VENVS},
    )


def build_pins(record, arm):
    """The pinned values one arm's worktree must show, from a label's frozen record."""
    return dict(stack_head=record.get(f"stack_head_{arm}"), stack_clean=record.get(f"stack_clean_{arm}") is True,
                mlx_vlm=record.get("mlx_vlm"), mlx_serve=record.get("mlx_serve"),
                registry_sha=record.get(f"registry_{arm}_sha"), uv_lock_sha256=record.get("uv_lock_sha256"),
                bench_lock_sha256=record.get("bench_lock_sha256"), venvs=(record.get("venvs") or {}).get(arm))


def record_problems(record, build):
    """The frozen record of a non-`s` label against that label's expected build (in code) and its own completeness."""
    expected = EXPECTED_BUILDS.get(build)
    if expected is None:
        return [f"build {build!r} has no expected build in code"]
    problems = []
    if record.get("build") != build:
        problems.append(f"record build {record.get('build')!r} != {build!r}")
    for key in ("mlx_vlm", "mlx_serve", "production_ref"):
        if record.get(key) != expected[key]:
            problems.append(f"{key}: record {record.get(key)!r} != expected {expected[key]!r} for build {build}")
    for arm in ARMS:
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get(f"stack_head_{arm}"))):
            problems.append(f"stack_head_{arm}: {record.get(f'stack_head_{arm}')!r} is not a commit")
        if record.get(f"stack_clean_{arm}") is not True:
            problems.append(f"stack_clean_{arm}: the {arm.upper()} tree was not recorded clean")
        for key in (f"registry_{arm}_sha",):
            if not re.fullmatch(r"[0-9a-f]{64}", str(record.get(key))):
                problems.append(f"{key} missing")
        for venv in VENVS:
            got = ((record.get("venvs") or {}).get(arm) or {}).get(venv) or {}
            for pkg in VENV_PACKAGES:
                if not got.get(pkg):
                    problems.append(f"venvs.{arm}.{venv}.{pkg} missing")
                elif str(got[pkg]).startswith(AMBIGUOUS):
                    problems.append(f"venvs.{arm}.{venv}.{pkg} {got[pkg]}")
            for pkg in ("mlx", "mlx-metal"):
                if got.get(pkg) and got[pkg] != expected["mlx"]:
                    problems.append(f"venvs.{arm}.{venv}.{pkg} {got[pkg]} != {expected['mlx']}")
    if record.get("stack_head_off") == record.get("stack_head_on"):
        problems.append("stack_head_off == stack_head_on (the arms are two commits)")
    for key in ("uv_lock_sha256", "bench_lock_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(record.get(key))):
            problems.append(f"{key} missing")
    return problems


def arm_problems(record, arm, root):
    """The live worktree of one arm against the record (the K2 comparison, at the sequencer's start)."""
    state, want = arm_state(root), build_pins(record, arm)
    return [f"{arm.upper()} worktree {k}: {state.get(k)!r} != recorded {want.get(k)!r}" for k in want if state.get(k) != want.get(k)]


def _entry_block(text, entry):
    """(first, last) 1-based line numbers of the registry entry `- name: <entry>`, through the line before the next entry."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if re.match(rf"\s*- name:\s*{re.escape(entry)}\s*$", line)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"\s*- name:", lines[i]) or re.match(r"\S", lines[i])),
               len(lines))
    return start + 1, end


def _first_difference(path, got, want):
    """`<path>: line N: …` for the first line where two texts differ (1-based), else None."""
    a, b = got.split("\n"), want.split("\n")
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        if x != y:
            return f"{path}: line {i + 1}: got {x!r}, expected {y!r} (the restore is not exactly the pinned bytes)"
    return None


def _registry_problems(off_root, off_text, on_text, entry):
    """P511: ON `main_models.yaml` = the fork's `overlay_on(OFF)` (the B4 rule, loaded from the OFF worktree's `src/mlx-vlm`) plus
    exactly one `# PROVISIONAL P426[ free text]` line as the first child of the entry's `generation_defaults:`, byte for byte."""
    from bench import p426_overlay

    try:
        rs = p426_overlay.load_registry_states(off_root)
        base, _ = rs.overlay_on(off_text, rs.fixture_text(Path(off_root) / "src" / "mlx-vlm" / "mlx_vlm" / "tests" / "fixtures"), entry)
    except (OSError, RuntimeError, ValueError) as exc:
        return [f"{REGISTRY}: the fork's overlay rule cannot derive the ON registry from OFF: {exc}"]
    block = _entry_block(base, entry)
    lines = base.split("\n")
    gds = [i for i in range(block[0] - 1, block[1]) if re.match(r"\s*generation_defaults:\s*$", lines[i])] if block else []
    if len(gds) != 1:
        return [f"{REGISTRY}: {entry} has {len(gds)} generation_defaults lines (exactly one expected)"]
    gd = gds[0]
    outer = len(lines[gd]) - len(lines[gd].lstrip())
    child = next((line for line in lines[gd + 1:] if line.strip()), "")
    indent = child[: len(child) - len(child.lstrip())]
    if len(indent) <= outer:
        return [f"{REGISTRY}: {entry} generation_defaults has no child to take the note's indentation from"]
    got = on_text.split("\n")
    pos = gd + 1
    ok = pos < len(got) and re.fullmatch(rf"{re.escape(indent)}# PROVISIONAL P426(?: [^\r]*)?", got[pos]) is not None
    want = lines[:pos] + [got[pos] if ok else f"{indent}# PROVISIONAL P426[ free text]"] + lines[pos:]
    diff = _first_difference(REGISTRY, on_text, "\n".join(want))
    if diff:
        return [diff]
    return [] if ok else [f"{REGISTRY}: line {pos + 1}: got {got[pos]!r}, expected the `# PROVISIONAL P426` note"]


def _seeding_problems(off_text, on_text):
    """P511: ON seeding test = OFF with the exact reverse of C177's seeding hunk (`78a730fe`), byte for byte."""
    if off_text.count(SEEDING_C177) != 1:
        return [f"{SEEDING_TEST}: the OFF text does not hold C177's seeding hunk exactly once"]
    return [d for d in [_first_difference(SEEDING_TEST, on_text, off_text.replace(SEEDING_C177, SEEDING_RESTORED))] if d]


def restore_diff_problems(off_root, on_root, entry):
    """T3 §4 arms as commits: the ON worktree's HEAD is the OFF worktree's HEAD plus ONE commit that changes exactly
    `main_models.yaml` and the seeding test (regular files, content only), and (P511) both files equal, byte for byte, the
    texts derived from OFF: the registry is the fork's `overlay_on(OFF)` plus one `PROVISIONAL P426` note line; the seeding
    test is OFF with the reverse of C177's seeding hunk. A refusal names the file and its first differing line."""

    off_head, on_head = _git(off_root, "rev-parse", "HEAD"), _git(on_root, "rev-parse", "HEAD")
    if not off_head or not on_head:
        return ["a worktree has no HEAD"]
    problems = []
    if _git(on_root, "rev-list", "--count", f"{off_head}..{on_head}") != "1" or _git(on_root, "rev-parse", f"{on_head}^") != off_head:
        problems.append("the ON HEAD is not the OFF HEAD plus exactly one commit")
    raw = subprocess.run(["git", "-C", str(on_root), "diff", "--raw", "--no-renames", "-z", off_head, on_head],
                         capture_output=True, text=True, timeout=60).stdout.split("\0")
    changed = {}
    for meta, path in zip(raw[0::2], raw[1::2]):
        if not meta.startswith(":"):
            continue
        old_mode, new_mode, _, _, status = meta[1:].split()
        changed[path] = (old_mode, new_mode, status)
    if set(changed) != {REGISTRY, SEEDING_TEST}:
        problems.append(f"the restore commit changes {sorted(changed)}, not exactly {[REGISTRY, SEEDING_TEST]}")
    for path, (old_mode, new_mode, status) in sorted(changed.items()):
        if status != "M" or old_mode != new_mode or new_mode != "100644":
            problems.append(f"{path}: status {status} mode {old_mode} -> {new_mode} (a content-only change of a regular file)")
    if problems:
        return problems

    def text(root, rel):  # bytes decoded, never universal-newline normalized
        return (Path(root) / rel).read_bytes().decode("utf-8")

    try:
        return (_registry_problems(off_root, text(off_root, REGISTRY), text(on_root, REGISTRY), entry)
                + _seeding_problems(text(off_root, SEEDING_TEST), text(on_root, SEEDING_TEST)))
    except (OSError, UnicodeDecodeError) as exc:
        return [f"the restore files cannot be read: {exc}"]


def load_ids(repo, text=None):
    """The committed ids.json, refused unless it equals a rebuild from the M40 sources (K3: membership comes from it)."""
    repo = Path(repo)
    doc = json.loads(text if text is not None else (repo / p426_ids.OUT).read_text())
    want = dict(p426_ids.build(repo), sources_sha256=p426_ids.source_shas(repo))
    if doc != want:
        raise ValueError(f"{p426_ids.OUT}: not the committed rebuild of its sources")
    return doc


def _tune(arm, block, smoke, build=DEFAULT_BUILD):
    if arm not in ARMS:
        raise ValueError(f"arm {arm!r} not in {ARMS}")
    prefix = tune_prefix(build)
    if smoke:
        return f"{prefix}-{arm}-smoke"
    if block not in (1, 2):
        raise ValueError(f"block {block!r} not in (1, 2)")
    return f"{prefix}-{arm}-b{block}"


def plan_leg(repo, axis, arm, block, smoke=False, results_root=None, workdir=None, reviewed_head=None, production_ref=None,
             build=DEFAULT_BUILD):
    repo = Path(repo)
    ids = load_ids(repo)
    entry = ids["entry"]
    tune = _tune(arm, block, smoke, build)
    if axis == "m1":  # K3: the in-process qualify leg (no router, directory evidence)
        if not workdir or not reviewed_head:
            raise ValueError("an m1 leg needs the workdir and the frozen build's reviewed head")
        if not production_ref:  # P452 F1: S's production tree, attested by qualify (B1's log-only counters)
            raise ValueError("an m1 leg needs the production ref (frozen.json production_ref)")
        out_dir = m1_out_dir(workdir, tune, build)
        fork = repo / "src" / "mlx-vlm"
        return dict(
            axis=axis, arm=arm, block=block, smoke=smoke, tune=tune, entry=entry, kind="qualify", cwd=str(repo),
            out_dir=out_dir, rows_path=None, planned=[], row_key=None, expected_requests=0, expected_extra=0, seeds={},
            stem=None,
            driver_argv=[str(repo / ".venv" / "bin" / "python"), str(fork / "dev" / "p369_phase2" / "qualify.py"),
                         "--stack-root", str(repo), "--fork-root", str(fork), "--out", str(out_dir),
                         "--reviewed-head", reviewed_head, "--entry", entry, "--predictor", arm,
                         "--production-ref", production_ref],
        )
    if axis not in ids["axes"]:
        raise ValueError(f"unknown axis {axis!r}")
    sel = ids["axes"][axis]["smoke" if smoke else f"block{block}"]
    results = Path(results_root) if results_root else repo / "benchmark" / "results"
    out_dir = results / entry
    py = str(repo / ".venv-bench" / "bin" / "python")
    leg = dict(axis=axis, arm=arm, block=block, smoke=smoke, tune=tune, entry=entry, cwd=str(repo), results_dir=out_dir)
    if axis in ("math500", "cjudge"):
        stem = f"{axis}.{tune}"
        leg.update(
            driver_argv=[py, str(repo / "benchmark" / "run.py"), "generate", "--models", entry, "--benches", axis,
                         "--limit", f"{axis}=0", "--ids", f"{axis}=" + ":".join(sel), "--sampling-profile", "deployed",
                         "--tune", tune, "--order", "roundrobin", "--seed", "0", "--seed-base", "0", "--samples", "1"],
            rows_path=out_dir / f"{stem}.jsonl", planned=list(sel), row_key="id", expected_requests=len(sel),
            expected_extra=0, seeds={i: {"sampler_seed": sample_seed(i, 0, base=0), "sample": 0, "seed_base": 0} for i in sel},
        )
    elif axis == "vision":
        stem = f"vision_gate.{tune}"
        leg.update(
            driver_argv=[py, str(repo / "benchmark" / "vision_gate.py"), "--model", entry, "--ids", ":".join(sel),
                         "--out", str(out_dir / f"{stem}.jsonl")],
            rows_path=out_dir / f"{stem}.jsonl", planned=list(sel), row_key="id", expected_requests=2 * len(sel),
            expected_extra=0, seeds={i: {"seed": sample_seed(i, 0), "turn2_seed": sample_seed(i, 1)} for i in sel},
        )
    elif axis == "reasoning":
        stem = f"reasoning.{tune}"
        tasks = list(sel)
        if tasks != list(range(tasks[0], tasks[0] + len(tasks))):
            raise ValueError(f"reasoning tasks {tasks} are not contiguous (--task-seed-base + trial)")
        leg.update(
            driver_argv=[py, "-m", "bench.run_reasoning", "--model", entry, "--grid", "128000", "--samples", str(len(tasks)),
                         "--chain-len", "4", "--sampling-profile", "deployed", "--out-tag", tune,
                         "--task-seed-base", str(tasks[0]), "--request-seed-base", str(REQUEST_SEED_BASE)],
            cwd=str(repo / "benchmark"), rows_path=out_dir / f"{stem}.partial.jsonl", planned=tasks, row_key="seed",
            expected_requests=len(tasks) + 1, expected_extra=1,  # + the chars-per-token calibration request
            seeds={t: {"sampler_seed": ids["axes"]["reasoning"]["request_seeds"][str(t)]} for t in tasks},
        )
    else:
        raise ValueError(f"axis {axis!r} has no Wave-1 leg")
    leg["stem"] = stem
    leg["kind"] = {"math500": "rows", "cjudge": "rows"}.get(axis, axis)
    return leg


def existing_outputs(leg):
    """Every file of the leg's stem already on disk (rows, manifest, score, summary, journal, provenance …); for an M1 leg its
    output directory."""
    if leg.get("kind") == "qualify":
        return [leg["out_dir"]] if Path(leg["out_dir"]).exists() else []
    d = Path(leg["results_dir"])
    return sorted(p for p in d.glob(f"{leg['stem']}.*")) if d.exists() else []


def seed_problems(expected, rows, key):
    """K4: every row's recorded seeds equal the planned ones (vision: both turns)."""
    problems = []
    for row in rows:
        want = expected.get(row.get(key))
        if want is None:
            continue  # membership reports it
        got = {k: row.get(k) for k in want if k != "turn2_seed"}
        if "turn2_seed" in want:
            got["turn2_seed"] = (row.get("turn2") or {}).get("seed")
        if got != want:
            problems.append(f"{row.get(key)}: seeds {got} != planned {want}")
    return problems


def qualify_problems(report, entry, arm, production_ref=None):
    """K3: the M1 leg's evidence — the planned predictor, the entry COMPLETED in the planned arm; P452: the report records
    exactly the planned production ref."""
    want_arm = "mtp_on" if arm == "on" else "mtp_off"
    problems = []
    if production_ref and report.get("production") != production_ref:
        problems.append(f"qualify production {report.get('production')!r} != planned {production_ref!r}")
    if report.get("predictor") != arm:
        problems.append(f"qualify predictor {report.get('predictor')!r} != {arm!r}")
    state = (report.get("entries") or {}).get(entry)
    if not state:
        return problems + [f"qualify report has no {entry}"]
    if state.get("status") != "COMPLETED":
        problems.append(f"qualify status {state.get('status')!r}")
    if state.get("arm") != want_arm:
        problems.append(f"qualify arm {state.get('arm')!r} != {want_arm!r}")
    return problems
