"""P426 stack code round 1 K3 / K4: the leg planner — everything a Wave-1 leg depends on, derived from (axis, arm, block) and the
committed `benchmark/results/p426/ids.json` (`docs/specs/p426-fable-mtp-recert.md` §4–§5): the driver argv and cwd, every output
of the leg's stem (none may exist), the planned membership, the expected seeds per row and the expected request count.
"""

import difflib
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
DEFAULT_LEVER = "mtp"  # M76 B3: `mtp` = P426 as it stands; `kv` = the M76 KV lever (the section at the end)
BUILD_LABEL = re.compile(r"^[a-z][a-z0-9]{0,7}$")
EXPECTED_BUILDS = {  # in code, not in the record: a self-consistent record of another build is still refused
    "s2": dict(mlx_vlm="1c7c8fa166582ac1a1c23ae9063527b2b5215b11", mlx_serve="1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d",
               production_ref="b26fa7c9faf23bc3167db3419504ef0b2b82a8e6", mlx="0.32.4"),
    # M76 B3: the stage-3 base's gitlinks (89205085: fork 34a21208, M76 B2) and B0's production ref
    "s3": dict(mlx_vlm="34a212080d28953406ae446ab86505a964677a8d", mlx_serve="3b02e4cbd669b2f4ecb2cb8dabac4ef906e70afc",
               production_ref="f9bf743f284f45ce8d8a3c9902f0701de92c0931", mlx="0.32.4"),
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


def leg_name(axis, arm, sel, build=DEFAULT_BUILD, lever=DEFAULT_LEVER, tier=1):
    """`lever="kv"` (M76 B3): `kv_leg_name` on a KV build (`m76-<arm>-…`)."""
    if check_lever(lever) == "kv":
        check_kv_build(build)
        return kv_leg_name(axis, arm, sel, tier)
    return f"{axis}-{tune_prefix(build)}-{arm}-{'smoke' if sel == 'smoke' else f'b{sel}'}"


def frozen_path(workdir, build=DEFAULT_BUILD, lever=DEFAULT_LEVER):
    """The one frozen-build record of a label: `frozen.json` (S) or `frozen.<label>.json`; no other path is ever read.
    `lever="kv"` (M76 B3): `$STACK_WORKDIR/m76/p426/frozen.<label>.json`."""
    if check_lever(lever) == "kv":
        return kv_frozen_path(workdir, build)
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
             build=DEFAULT_BUILD, lever=DEFAULT_LEVER, tier=1, certified_by=None):
    if check_lever(lever) == "kv":  # M76 B3: the KV lever's own planner; `mtp` below is today's, unchanged
        return plan_leg_kv(repo, axis, arm, block, smoke=smoke, results_root=results_root, workdir=workdir,
                           reviewed_head=reviewed_head, production_ref=production_ref, build=build, tier=tier,
                           certified_by=certified_by)
    if tier != 1 or certified_by is not None:
        raise ValueError("tier / certified_by are KV-lever (M76) leg parameters")
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
    if "stems" in leg:  # M76 A5: one stem per runner (retrieval / reasoning)
        return sorted(p for s in leg["stems"] for p in d.glob(f"{s}.*")) if d.exists() else []
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


def qualify_problems(report, entry, arm, production_ref=None, lever=DEFAULT_LEVER):
    """K3: the M1 leg's evidence — the planned predictor, the entry COMPLETED in the planned arm; P452: the report records
    exactly the planned production ref. M76 (lever kv): every arm runs `--predictor on`; a TQ4 arm's report names the stage-2
    record it was certified by (B2)."""
    predictor = "on" if check_lever(lever) == "kv" else arm
    want_arm = "mtp_on" if predictor == "on" else "mtp_off"
    problems = []
    if lever == "kv" and arm != KV_REF:
        cert = report.get("certified_by")
        if not (isinstance(cert, dict) and cert.get("path") and re.fullmatch(r"[0-9a-f]{64}", str(cert.get("sha256")))):
            problems.append(f"qualify certified_by {cert!r}: a TQ4 arm's M1 is bound to its stage-2 record (B2)")
    if production_ref and report.get("production") != production_ref:
        problems.append(f"qualify production {report.get('production')!r} != planned {production_ref!r}")
    if report.get("predictor") != predictor:
        problems.append(f"qualify predictor {report.get('predictor')!r} != {predictor!r}")
    state = (report.get("entries") or {}).get(entry)
    if not state:
        return problems + [f"qualify report has no {entry}"]
    if state.get("status") != "COMPLETED":
        problems.append(f"qualify status {state.get('status')!r}")
    if state.get("arm") != want_arm:
        problems.append(f"qualify arm {state.get('arm')!r} != {want_arm!r}")
    return problems


# ===================================================================================================== M76 B3: the lever
# `docs/specs/m76-b3-b5-p426-kv-lever.md`: `mtp` (default) = everything above, unchanged; `kv` = an arm pair that differs ONLY in
# `{kv_bits, tq4_attention}` (+ the arm's `# PROVISIONAL M76 arm <ARM>` note), both arms MTP ON, on build `s3`, named by the KV
# label (`n16`, `x`, `v`) under the `m76` namespace.
LEVERS = ("mtp", "kv")
MTP_KEYS = ("draft_kind", "draft_model", "mtp_verify_scan")
MTP_PINNED = {"draft_kind": "mtp", "draft_model": "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter",
              "mtp_verify_scan": "joint_v1"}
MTP_FLAGS = ("--draft-kind", "--draft-model", "--mtp-verify-scan")
KV_KEYS = ("kv_bits", "tq4_attention")
KV_FLAGS = ("--kv-bits", "--tq4-attention")
KV_ARMS = {"n16": {"kv_bits": 0, "tq4_attention": None},                 # the shipped native16 entry (the base)
           "x": {"kv_bits": 4, "tq4_attention": "m72_exact"},
           "v": {"kv_bits": 4, "tq4_attention": "m72_v1"}}
KV_ARM_NOTE = {"n16": None, "x": "# PROVISIONAL M76 arm X", "v": "# PROVISIONAL M76 arm V"}
KV_REF = "n16"
KV_PAIRS = (("n16", "x"), ("x", "v"), ("n16", "v"))                       # (reference, treatment): X − N16, V − X, V − N16
KV_BUILDS = ("s3",)
KV_NS = "m76"
M76_RESULTS = Path("benchmark") / "results" / "m76"
_NOTE_RE = re.compile(r"^\s*# PROVISIONAL M76 arm \S+\s*$")
_KV_LINE_RE = re.compile(r"^\s*(?:kv_bits|tq4_attention):")


A7_SESSIONS_MAX = 3      # the tg1 chain's paired sessions: s1 (1001), s2 (2002), s3 (3003, M76 only)


def kv_a7_sessions(report=None):
    """A7's paired tg1 sessions at its final look, from B7's committed plan (`bench.m76_rule.axis_plan("A7")`, erratum v1.2): the
    look's size is the number of sessions, s1 … s<k>. ValueError when the plan is absent or names another unit / count."""
    from bench import m76_rule

    look = m76_rule.axis_plan("A7", report=report)["looks"][-1]
    k = look.get("size")
    if look.get("unit") != "sessions" or not isinstance(k, int) or not 2 <= k <= A7_SESSIONS_MAX:
        raise ValueError(f"A7's plan names {k!r} {look.get('unit')} (the tg1 chain has s1 … s{A7_SESSIONS_MAX})")
    return tuple(f"s{i}" for i in range(1, k + 1))


def check_lever(lever):
    if lever not in LEVERS:
        raise ValueError(f"lever {lever!r} not in {LEVERS}")
    return lever


def arms_of(lever):
    return ARMS if check_lever(lever) == "mtp" else tuple(KV_ARMS)


def check_arm(lever, arm):
    if arm not in arms_of(lever):
        raise ValueError(f"arm {arm!r} not in {arms_of(lever)} (lever {lever})")
    return arm


def predictor_of(lever, arm):
    """The served predictor of an arm: under `kv` every arm is MTP ON."""
    return "mtp" if check_lever(lever) == "kv" or arm == "on" else "off"


def role_of(lever, arm):
    """The engagement role the P426 checks apply (`on`: drafter counters required; `off`: none allowed)."""
    return "on" if predictor_of(lever, arm) == "mtp" else "off"


def check_kv_pair(ref, test):
    if (ref, test) not in KV_PAIRS:
        raise ValueError(f"KV pair ({ref}, {test}) not in {KV_PAIRS} (reference, treatment)")
    return ref, test


def pair_label(ref, test):
    check_kv_pair(ref, test)
    return f"{test.upper()} − {ref.upper()}"


def check_kv_build(build):
    if check_build(build) not in KV_BUILDS:
        raise ValueError(f"lever kv runs on build {KV_BUILDS} only, not {build!r}")
    if build not in EXPECTED_BUILDS:
        raise ValueError(f"build {build!r} has no expected build in code")
    return build


# C354: the Wave 1 kinds a KV build's stage planned; a dropped kind is B8 `not_run` with its ruling, never refused
KV_W1_KINDS = ("math500", "cjudge", "vision", "reasoning", "m1", "longctx")     # v1.1 F5: the one definition (B8 imports it)
KV_W1_DROPPED = {"s3": {"m1": "C352: M1 dropped from stage 3a (stage 1's matrix certifies memory)"}}


def kv_w1_dropped(build):
    """{kind: ruling} of the Wave 1 kinds build `build` dropped (ValueError on a non-KV build)."""
    return dict(KV_W1_DROPPED.get(check_kv_build(build), {}))


def kv_w1_kinds(build):
    """The Wave 1 kinds build `build` planned, in `KV_W1_KINDS` order (ValueError on a non-KV build)."""
    dropped = kv_w1_dropped(build)
    return tuple(k for k in KV_W1_KINDS if k not in dropped)


A5_TUNE_TAG = "lc"     # erratum v1.2: A5's own tune / stems (its `reasoning.*` files never share A4's tune)
KV_TIERED_AXES = ("math500", "longctx")     # v1.4: A5 has a tier 2 (its second look), as Math500


def kv_tune(arm, block, smoke, tier=1, axis=None):
    """`m76-<arm>-smoke` | `m76-<arm>-b<k>` | `m76-<arm>-t2-b<k>` (Math500 tier 2); A5 (`axis="longctx"`):
    `m76-<arm>-lc-smoke` | `m76-<arm>-lc-b<k>` | `m76-<arm>-lc-t2-b<k>` (A5 tier 2, v1.4)."""
    check_arm("kv", arm)
    tag = f"{A5_TUNE_TAG}-" if axis == "longctx" else ""
    if smoke:
        if tier != 1:
            raise ValueError("a smoke has no tier")
        return f"{KV_NS}-{arm}-{tag}smoke"
    if block not in (1, 2):
        raise ValueError(f"block {block!r} not in (1, 2)")
    if tier not in (1, 2):
        raise ValueError(f"tier {tier!r} not in (1, 2)")
    if tier == 2 and axis not in (None, *KV_TIERED_AXES):
        raise ValueError("only math500 and longctx have a tier 2")
    return f"{KV_NS}-{arm}-{tag}{'t2-' if tier == 2 else ''}b{block}"


def kv_leg_name(axis, arm, sel, tier=1):
    return f"{axis}-{kv_tune(arm, None if sel == 'smoke' else sel, sel == 'smoke', tier, axis=axis)}"


def kv_scratch(workdir):
    return Path(workdir) / KV_NS / "p426"


def kv_frozen_path(workdir, build):
    return kv_scratch(workdir) / f"frozen.{check_kv_build(build)}.json"


def kv_m1_out_dir(workdir, tune, build):
    return kv_scratch(workdir) / check_kv_build(build) / "m1" / tune


def _kv_state(entry):
    bits = entry.get("kv_bits")
    return {"kv_bits": 0 if bits in (None, 0) else bits, "tq4_attention": entry.get("tq4_attention")}


def kv_arm_of_entry(entry):
    """The KV label of a registry entry's state (None when it is no M76 arm)."""
    st = _kv_state(entry or {})
    return next((a for a, want in KV_ARMS.items() if st == want), None)


def kv_registry_problems(text, entry, arm):
    """One arm's committed registry: its entry's KV state is the label's, the three MTP keys are ON at their pinned values, and
    the arm note is exactly the label's (N16: none) inside the entry."""
    from bench.p426_leg import _models, _same

    check_arm("kv", arm)
    try:
        models = _models(text)[0]
    except ValueError as exc:
        return [f"registry: {exc}"]
    e = models.get(entry)
    if e is None:
        return [f"{entry}: missing from the {arm} registry"]
    problems = []
    if _kv_state(e) != KV_ARMS[arm]:
        problems.append(f"{entry}: the {arm} registry's KV state {_kv_state(e)} is not {arm}'s {KV_ARMS[arm]}")
    for key, value in MTP_PINNED.items():
        if not _same(e.get(key), value):
            problems.append(f"{entry}: the {arm} registry {key} {e.get(key)!r} != MTP ON {value!r} (both arms MTP ON)")
    block = _entry_block(text, entry)
    lines = text.split("\n")
    notes = [i + 1 for i, line in enumerate(lines) if _NOTE_RE.match(line)]
    want = KV_ARM_NOTE[arm]
    inside = [n for n in notes if block and block[0] <= n <= block[1]]
    if want is None and notes:
        problems.append(f"the {arm} registry carries an M76 arm note (line {notes[0]})")
    if want is not None and (len(notes) != 1 or len(inside) != 1 or lines[inside[0] - 1].strip() != want):
        problems.append(f"the {arm} registry must carry exactly one `{want}` line inside {entry}")
    return problems


def kv_registry_delta_problems(a_text, b_text, entry, arm_a, arm_b):
    """B3: the two arms' registries are equal except that `entry` differs in `{kv_bits, tq4_attention}` (and the arm note):
    strict, type-aware; every other key (the MTP keys included) equal; the text delta is only KV key lines and arm notes."""
    from bench.p426_leg import _models, _same

    if arm_a == arm_b:
        return [f"the arms are one KV state ({arm_a})"]
    problems = [f"{arm_a}: {p}" for p in kv_registry_problems(a_text, entry, arm_a)]
    problems += [f"{arm_b}: {p}" for p in kv_registry_problems(b_text, entry, arm_b)]
    try:
        a, a_names, a_top = _models(a_text)
        b, b_names, b_top = _models(b_text)
    except ValueError as exc:
        return problems + [f"registry: {exc}"]
    if not _same(a_top, b_top):
        problems.append("top-level registry settings differ")
    if a_names != b_names:
        problems.append("the arms list different models")
    for name in sorted(set(a) | set(b), key=str):
        if name != entry and not _same(a.get(name), b.get(name)):
            problems.append(f"{name}: settings differ between the arms")
    ea, eb = a.get(entry), b.get(entry)
    if ea is None or eb is None:
        return problems + [f"{entry}: missing from an arm's registry"]
    for key in sorted(set(ea) | set(eb)):
        if key in KV_KEYS or _same(ea.get(key), eb.get(key)):
            continue
        what = "an MTP key" if key in MTP_KEYS else "a non-KV key"
        problems.append(f"{entry}: {key} differs between the arms ({what}; only {list(KV_KEYS)} may)")
    for d in difflib.ndiff(a_text.splitlines(), b_text.splitlines()):
        if d[:2] in ("- ", "+ ") and not (_KV_LINE_RE.match(d[2:]) or _NOTE_RE.match(d[2:])):
            problems.append(f"{entry}: the text delta changes a line that is neither a KV key nor the arm note: {d[2:].strip()!r}")
    return problems


def kv_argv(arm):
    """The worker flags of an arm's KV state: N16 none; a TQ4 arm `--kv-bits 4 --tq4-attention <mode>`."""
    st = KV_ARMS[check_arm("kv", arm)]
    return ((["--kv-bits", str(st["kv_bits"])] if st["kv_bits"] else [])
            + (["--tq4-attention", st["tq4_attention"]] if st["tq4_attention"] else []))


def strip_flags(tokens, flags):
    """(tokens without the `flag value` pairs of `flags`, {flag: [values]})."""
    rest, found, i = [], {f: [] for f in flags}, 0
    tokens = [str(t) for t in tokens]
    while i < len(tokens):
        if tokens[i] in flags:
            found[tokens[i]].append(tokens[i + 1] if i + 1 < len(tokens) else None)
            i += 2
        else:
            rest.append(tokens[i])
            i += 1
    return rest, found


def kv_arm_argv_problems(tokens, arm, where="worker"):
    """One arm's worker argv: its KV flags exactly the label's, each MTP flag exactly once (MTP ON, joint_v1)."""
    _, kv = strip_flags(tokens, KV_FLAGS)
    flags = kv_argv(arm)
    want = {f: [] for f in KV_FLAGS}
    for f, v in zip(flags[0::2], flags[1::2]):
        want[f] = [v]
    problems = [f"argv.{where}: {arm} {f} {kv[f]} != the arm's {want[f]}" for f in KV_FLAGS if kv[f] != want[f]]
    _, mtp = strip_flags(tokens, MTP_FLAGS)
    for f in MTP_FLAGS:
        if len(mtp[f]) != 1 or mtp[f][0] is None:
            problems.append(f"argv.{where}: {arm} carries {f} x{len(mtp[f])} (MTP ON: exactly once)")
    for f, v in (("--draft-kind", "mtp"), ("--mtp-verify-scan", "joint_v1"), ("--draft-model", MTP_PINNED["draft_model"])):
        if mtp[f] and mtp[f] != [v]:
            problems.append(f"argv.{where}: {arm} {f} {mtp[f]} != [{v!r}]")
    return problems


def kv_argv_problems(a_tokens, b_tokens, arm_a, arm_b, where="worker"):
    """B3: two arms' worker argvs differ by exactly `--kv-bits <b>` / `--tq4-attention <mode>` (present / absent), every other
    token equal in order; both MTP ON."""
    if arm_a == arm_b:
        return [f"argv.{where}: the arms are one KV state ({arm_a})"]
    problems = kv_arm_argv_problems(a_tokens, arm_a, where) + kv_arm_argv_problems(b_tokens, arm_b, where)
    if strip_flags(a_tokens, KV_FLAGS)[0] != strip_flags(b_tokens, KV_FLAGS)[0]:
        problems.append(f"argv.{where}: the arms differ beyond {list(KV_FLAGS)}")
    return problems


def kv_record_problems(record, build, arms):
    """The KV frozen record (`$STACK_WORKDIR/m76/p426/frozen.<label>.json`) against its expected build: `lever` kv, the arm list
    (always holding the base `n16`), per arm its clean commit, registry sha and venv versions; the arms are distinct commits."""
    problems = []
    try:
        check_kv_build(build)
    except ValueError as exc:
        return [str(exc)]
    expected = EXPECTED_BUILDS[build]
    if record.get("build") != build:
        problems.append(f"record build {record.get('build')!r} != {build!r}")
    if record.get("lever") != "kv":
        problems.append(f"record lever {record.get('lever')!r} != 'kv'")
    have = record.get("arms")
    if not isinstance(have, list) or KV_REF not in have or not set(have) <= set(KV_ARMS) or len(set(have)) != len(have):
        return problems + [f"record arms {have!r}: a list of distinct {list(KV_ARMS)} holding {KV_REF!r}"]
    missing = [a for a in arms if a not in have]
    if missing:
        problems.append(f"record arms {have} lack {missing}")
    for key in ("mlx_vlm", "mlx_serve", "production_ref"):
        if record.get(key) != expected[key]:
            problems.append(f"{key}: record {record.get(key)!r} != expected {expected[key]!r} for build {build}")
    for arm in have:
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get(f"stack_head_{arm}"))):
            problems.append(f"stack_head_{arm}: {record.get(f'stack_head_{arm}')!r} is not a commit")
        if record.get(f"stack_clean_{arm}") is not True:
            problems.append(f"stack_clean_{arm}: the {arm} tree was not recorded clean")
        if not re.fullmatch(r"[0-9a-f]{64}", str(record.get(f"registry_{arm}_sha"))):
            problems.append(f"registry_{arm}_sha missing")
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
    heads = [record.get(f"stack_head_{a}") for a in have]
    if len(set(heads)) != len(heads):
        problems.append("two arms share a stack head (each arm is its own commit)")
    for key in ("uv_lock_sha256", "bench_lock_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(record.get(key))):
            problems.append(f"{key} missing")
    return problems


def kv_arm_commit_problems(record, arm, root, entry):
    """The live arm worktree (T3 §4 arms as commits, C218): N16 is the recorded base; a TQ4 arm is the base plus ONE commit that
    changes exactly `main_models.yaml` (content only) whose text is the base's with the KV delta (`kv_registry_delta_problems`)."""
    root = Path(root)
    base = record.get(f"stack_head_{KV_REF}")
    try:
        own = (root / REGISTRY).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{arm}: {REGISTRY} unreadable ({type(exc).__name__})"]
    if arm == KV_REF:
        return [f"{arm}: {p}" for p in kv_registry_problems(own, entry, arm)]
    head = _git(root, "rev-parse", "HEAD")
    problems = []
    if _git(root, "rev-parse", "HEAD^") != base or _git(root, "rev-list", "--count", f"{base}..{head}") != "1":
        problems.append(f"{arm}: HEAD is not the {KV_REF} commit {str(base)[:12]} plus exactly one commit")
    raw = subprocess.run(["git", "-C", str(root), "diff", "--raw", "--no-renames", "-z", str(base), head],
                         capture_output=True, text=True, timeout=60).stdout.split("\0")
    changed = {path: meta for meta, path in zip(raw[0::2], raw[1::2]) if meta.startswith(":")}
    if set(changed) != {REGISTRY}:
        problems.append(f"{arm}: the arm commit changes {sorted(changed)}, not exactly [{REGISTRY!r}]")
    for path, meta in changed.items():
        old_mode, new_mode, _, _, status = meta[1:].split()
        if status != "M" or old_mode != new_mode or new_mode != "100644":
            problems.append(f"{path}: status {status} mode {old_mode} -> {new_mode} (a content-only change of a regular file)")
    base_text = subprocess.run(["git", "-C", str(root), "show", f"{base}:{REGISTRY}"], capture_output=True,
                               timeout=60).stdout.decode("utf-8", errors="replace")
    return problems + kv_registry_delta_problems(base_text, own, entry, KV_REF, arm)


def kv_pair_commit_problems(ref_root, test_root, pair, entry):
    """Two KV arm worktrees without a frozen record (the Wave 2 freeze): the N16 base is the reference's HEAD (pair from N16) or
    its parent (V vs X: siblings on the base); every TQ4 arm is that base plus one registry commit with the KV delta; the two arms'
    registries differ by exactly the KV delta."""
    ref, test = check_kv_pair(*pair)
    roots = {ref: Path(ref_root), test: Path(test_root)}
    base = _git(roots[ref], "rev-parse", "HEAD" if ref == KV_REF else "HEAD^")
    problems = []
    for arm in (ref, test):
        problems += kv_arm_commit_problems({f"stack_head_{KV_REF}": base}, arm, roots[arm], entry)
    try:
        texts = {arm: (roots[arm] / REGISTRY).read_bytes().decode("utf-8") for arm in (ref, test)}
    except (OSError, UnicodeDecodeError) as exc:
        return problems + [f"{REGISTRY} unreadable ({type(exc).__name__})"]
    return problems + kv_registry_delta_problems(texts[ref], texts[test], entry, ref, test)


def kv_arm_problems(record, arm, root):
    """The live worktree of one KV arm against the record (heads, cleanliness, submodules, registry sha, locks, venvs)."""
    state, want = arm_state(root), build_pins(record, arm)
    return [f"{arm} worktree {k}: {state.get(k)!r} != recorded {want.get(k)!r}" for k in want if state.get(k) != want.get(k)]


def load_m76_ids(repo, text=None):
    from bench import m76_ids

    return m76_ids.load(repo, text)


def _kv_selection(ids, axis, block, smoke, tier):
    ax = ids["axes"][axis]
    if tier == 2:
        if axis not in KV_TIERED_AXES:
            raise ValueError("only math500 and longctx have a tier 2")
        if smoke or not isinstance(ax.get("tier2"), dict):
            raise ValueError(f"{axis} has no tier 2 in m76/ids.json (a one-look plan) or a tier-2 smoke was asked")
        return list(ax["tier2"][f"block{block}"])
    return list(ax["smoke" if smoke else f"block{block}"])


def plan_leg_kv(repo, axis, arm, block, smoke=False, results_root=None, workdir=None, reviewed_head=None, production_ref=None,
                build="s3", tier=1, certified_by=None):
    """B3 / B5: one KV-lever Wave 1 leg from `benchmark/results/m76/ids.json` (the planned membership, seeds, requests)."""
    from bench import m76_ids

    repo = Path(repo)
    check_kv_build(build)
    check_arm("kv", arm)
    ids = load_m76_ids(repo)
    entry = ids["entry"]
    tune = kv_tune(arm, block, smoke, tier, axis=axis)
    if axis == "m1":
        if tier != 1:
            raise ValueError("an m1 leg has no tier")
        if not workdir or not reviewed_head or not production_ref:
            raise ValueError("an m1 leg needs the workdir, the frozen build's reviewed head and its production ref")
        if arm != KV_REF and not certified_by:
            raise ValueError(f"the {arm} m1 leg binds qualify to its stage-2 record (--certified-by, M76 B2)")
        if arm == KV_REF and certified_by:
            raise ValueError(f"the {KV_REF} m1 leg has no KV delta to certify (no --certified-by)")
        out_dir = kv_m1_out_dir(workdir, tune, build)
        fork = repo / "src" / "mlx-vlm"
        argv = [str(repo / ".venv" / "bin" / "python"), str(fork / "dev" / "p369_phase2" / "qualify.py"),
                "--stack-root", str(repo), "--fork-root", str(fork), "--out", str(out_dir),
                "--reviewed-head", reviewed_head, "--entry", entry, "--predictor", "on", "--production-ref", production_ref]
        if arm != KV_REF:
            argv += ["--kv-arm", "--certified-by", str(certified_by)]
        return dict(axis=axis, arm=arm, block=block, smoke=smoke, tier=tier, tune=tune, entry=entry, kind="qualify",
                    cwd=str(repo), out_dir=out_dir, rows_path=None, planned=[], row_key=None, expected_requests=0,
                    expected_extra=0, seeds={}, stem=None, lever="kv", driver_argv=argv)
    if axis not in ids["axes"]:
        raise ValueError(f"unknown axis {axis!r}")
    if tier != 1 and axis not in KV_TIERED_AXES:
        raise ValueError("only math500 and longctx have a tier 2")
    results = Path(results_root) if results_root else repo / "benchmark" / "results"
    out_dir = results / entry
    py = str(repo / ".venv-bench" / "bin" / "python")
    leg = dict(axis=axis, arm=arm, block=block, smoke=smoke, tier=tier, tune=tune, entry=entry, cwd=str(repo),
               results_dir=out_dir, lever="kv")
    if axis == "longctx":
        lc = ids["axes"]["longctx"]
        problems = m76_ids.budget_problems(lc)
        if problems:  # B5: every item's prompt bound + resolved budget checked offline before the leg
            raise ValueError("A5 token budget: " + "; ".join(problems)[:600])
        by_id = {i["id"]: i for i in lc["items"] + lc["smoke_items"]}
        items = [by_id[i] for i in _kv_selection(ids, axis, block, smoke, tier)]
        argvs, rows = [], {}
        for it in items:
            tag = f"{tune}.{it['id']}"
            head = ["--model", entry, "--grid", str(it["rung"]), "--samples", "1"]
            # deployed sampling verbatim: the server resolves max_tokens = min(deployed, 262,144 − prompt tokens); the item's
            # frozen prompt tokens / resolved budget (`m76_ids`) are what B8 checks each row against (erratum v1.2)
            tail = ["--sampling-profile", "deployed", "--out-tag", tag, "--task-seed-base", str(it["task_seed"]),
                    "--request-seed-base", str(it["request_seed"])]
            if it["task"] == "retrieval":
                argvs.append([py, "-m", "bench.run_retrieval", *head, *tail])
                rows[it["id"]] = out_dir / f"retrieval.{tag}.json"
            else:
                argvs.append([py, "-m", "bench.run_reasoning", *head, "--chain-len", str(lc["chain_len"]), *tail])
                rows[it["id"]] = out_dir / f"reasoning.{tag}.partial.jsonl"
        leg.update(driver_argv=argvs[0] if argvs else [], driver_argvs=argvs, cwd=str(repo / "benchmark"),
                   rows_path=None, rows_paths=rows, items={i["id"]: i for i in items}, planned=[i["id"] for i in items],
                   row_key="id", expected_requests=2 * len(items), expected_extra=len(items),
                   seeds={i["id"]: {"sampler_seed": m76_ids.row_sampler_seed(i)} for i in items},
                   budget=lc["budget"], stems=[f"retrieval.{tune}", f"reasoning.{tune}"], stem=f"longctx.{tune}",
                   kind="longctx")
        return leg
    sel = _kv_selection(ids, axis, block, smoke, tier)
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
            expected_requests=len(tasks) + 1, expected_extra=1,
            seeds={t: {"sampler_seed": ids["axes"]["reasoning"]["request_seeds"][str(t)]} for t in tasks},
        )
    else:
        raise ValueError(f"axis {axis!r} has no Wave-1 leg")
    leg["stem"] = stem
    leg["kind"] = {"math500": "rows", "cjudge": "rows"}.get(axis, axis)
    return leg
