"""Synthetic Wave 1 (S' build, `wave1.s2`) results tree + tiny git repo for the P613 step-2 tests.

Layout and field names copy the committed data (the format reference):

    <base>/repo/                                  a git work tree (the `repo` argument); only code / registry files are committed
        benchmark/results/                        `rows_root` (also `bench.generate.RESULTS`, monkeypatched)
            p426/                                 `results_root`
                ids.json
                wave1.s2/run/frozen.s2.json
                wave1.s2/<kind>-p426s2-<arm>-<block>/{<leg>.receipt.json, SCRUB_MANIFEST.json, leg.stdout, <leg>.log}
                wave1.s2/m1-.../m1/{report.json, <ENTRY>/{result,job}.json}
                wave1.s2/<kind>-p426s2-<arm>-smoke/   (excluded; listed in coverage)   wave1.s2/archive/<attempt>/ (superseded)
                wave1/ (the S build, excluded)
            <ENTRY>/<bench>.<tune>.{jsonl,json,manifest.json,score.json}

`with_a7=True` also builds the step-1 A7 world (`bench.tests.p613.a7world`) under the same `p426/`, its v8 commits pointing at real
commits of the tiny repo, so `verify_all` / `compute_all` run end to end.

Nothing here reads the real data. Git commits use fixed identities and dates, so two worlds with the same spec have the same shas.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

from bench.tests.p613 import a7world

ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAFTER = f"caslca/{ENTRY}-mtp-drafter"
ARMS = ("off", "on")
BLOCKS = ("b1", "b2")
KINDS = ("math500", "cjudge", "vision", "reasoning", "m1")
BENCH_OF = {"math500": "math500", "cjudge": "cjudge", "vision": "vision_gate", "reasoning": "reasoning"}
WT = "$STACK_WORKDIR/worktrees"
RATE = {"off": 20.0, "on": 30.0}
NONCONV = {"completion_tokens": 81920, "converged": False, "nonconv_kind": "budget_hit"}   # a budget hit (finish stop)
M1_PEAKS = {("off", "b1"): (37658578482, 37557075522, 37935199774), ("off", "b2"): (37658578482, 37557075522, 37935199774),
            ("on", "b1"): (37972876142, 37926799772, 38251713408), ("on", "b2"): (37972876142, 37926799772, 38251715456)}
M1_RATES = {("off", "b1"): 13.361, ("off", "b2"): 13.412, ("on", "b1"): 16.019, ("on", "b2"): 16.041}
M1_PEAK_KEYS = ("prefill", "decode", "retire")


def dumps(doc) -> str:
    return json.dumps(doc, sort_keys=True, indent=1) + "\n"


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_text(s: str) -> str:
    return sha_bytes(s.encode("utf-8"))


def leg_name(kind, arm, block):
    return f"{kind}-p426s2-{arm}-{block}"


def tune_of(arm, block):
    return f"p426s2-{arm}-{block}"


def sampler_seed(kind, key) -> int:
    return int(sha_text(f"{kind}|{key}")[:8], 16)


def draft(arm, n=100, acc=80):
    if arm == "off":
        return {"draft_kind": None, "draft_rounds": None, "draft_n": None, "draft_n_accepted": None}
    return {"draft_kind": "mtp", "draft_rounds": n // 2, "draft_n": n, "draft_n_accepted": acc}


def default_ids(n_math=5):
    seeds = {str(s): 7_000_000 + (s - 128000000) * 11 for s in range(128000000, 128000010)}
    return {
        "math500": {"block1": [f"test/algebra/{i}.json" for i in range(1, n_math + 1)],
                    "block2": [f"test/algebra/{i}.json" for i in range(n_math + 1, 2 * n_math + 1)],
                    "smoke": ["test/algebra/900.json"]},
        "cjudge": {"block1": ["dom-01", "dom-02", "pub-aaa"], "block2": ["dom-03", "dom-04", "pub-bbb"], "smoke": ["dom-90"]},
        "vision": {"block1": ["cocoval2017-000", "cocoval2017-001"], "block2": ["cocoval2017-002", "cocoval2017-003"],
                   "smoke": ["cocoval2017-090"]},
        "reasoning": {"block1": [128000000, 128000001], "block2": [128000002, 128000003], "smoke": [128000009],
                      "request_seeds": seeds},
    }


# ---------------------------------------------------------------------------------------------------------- git repo
def registry_text(draft_kind="none", other="a", glob="10800", entry_rev="r1"):
    return (f"mlx_port: 8091\nmanager_port: 8000\ninactivity_timeout_seconds: {glob}\nmodels:\n"
            f"  - name: {ENTRY}\n    draft_kind: {draft_kind}\n    revision: {entry_rev}\n"
            f"  - name: Some-Other-Model\n    note: {other}\n")


BASE_CODE = {
    "benchmark/run.py": "from bench import helper\n",
    "benchmark/vision_gate.py": "import bench.helper\n",
    "benchmark/bench/__init__.py": "",
    "benchmark/bench/helper.py": "VALUE = 1\n",
    "benchmark/bench/run_reasoning.py": "from bench import helper\n",
    "benchmark/bench/unrelated.py": "X = 1\n",
    "docs/note.md": "note v1\n",
}
GITLINKS = {"src/mlx-vlm": "1c7c8fa166582ac1a1c23ae9063527b2b5215b11", "src/mlx-serve": "1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d"}


def git(repo, *args, check=True):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(repo), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_AUTHOR_DATE": "2026-11-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-11-01T00:00:00Z"}
    r = subprocess.run(["git", "-c", "commit.gpgsign=false", *map(str, args)], cwd=repo, capture_output=True, text=True,
                       env=env, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


def commit_tree(repo, files, gitlinks, msg):
    """Commit exactly `files` ({relpath: text | None (delete)}) and `gitlinks` ({path: sha}); the rest of the tree stays out."""
    repo = Path(repo)
    for rel, text in files.items():
        p = repo / rel
        if text is None:
            if p.exists():
                p.unlink()
            git(repo, "rm", "-q", "--cached", "--ignore-unmatch", "--", rel)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        git(repo, "add", "--", rel)
    for path, sha in gitlinks.items():
        git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},{path}")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


# -------------------------------------------------------------------------------------------------------- argv helpers
def worker_flags(arm):
    gd = json.dumps({"temperature": 0.5, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0,
                     "max_tokens": 102400, "thinking_budget": 81920, "enable_thinking": True, "reasoning_effort": "medium"})
    flags = [("--model", f"caslca/{ENTRY}"), ("--host", "127.0.0.1"), ("--port", "8091"), ("--max-kv-size", "262144"),
             ("--kv-prealloc-tokens", "262144"), ("--cache-session-shrink", "on"), ("--attention-policy", "fused_v1"),
             ("--lazy-prompt-embeddings", None)]
    if arm == "on":
        flags.append(("--mtp-verify-scan", "joint_v1"))
    flags += [("--kv-quant-scheme", "turboquant"), ("--prefill-step-size", "512"), ("--generation-defaults", gd)]
    if arm == "on":
        flags += [("--draft-kind", "mtp"), ("--draft-model", DRAFTER)]
    flags += [("--quantized-kv-start", "0"), ("--memory-limit-frac", "0.85")]
    return flags


def render_cmdline(arm, pid, flags):
    head = f"{pid} {WT}/stack-p426-s2-{arm}/.venv/bin/python {WT}/stack-p426-s2-{arm}/.venv/bin/mlx_vlm.server"
    return head + "".join(f" {f}" if v is None else f" {f} {v}" for f, v in flags)


def flat_argv(flags):
    return [x for f, v in flags for x in ((f,) if v is None else (f, v))]


def wall_seconds(kind, arm, block):
    return 1000 * (KINDS.index(kind) + 1) + (111 if arm == "on" else 0) + (7 if block == "b2" else 0)


def _hms(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"2026-10-28 {4 + h:02d}:{m:02d}:{s:02d}"


# ----------------------------------------------------------------------------------------------------------- the world
class Wave1World:
    def __init__(self, base, mp, *, n_math=5, ids=None, rows=None, legs=None, frozen=None, w2=None, w2_gitlinks=None,
                 w1_off=None, with_a7=False, a7=None, smoke=True, s_build=True):
        self.base = Path(base)
        self.repo = self.base / "repo"
        self.rows_root = self.repo / "benchmark" / "results"
        self.p426 = self.rows_root / "p426"
        self.w1 = self.p426 / "wave1.s2"
        self.edir = self.rows_root / ENTRY
        self.ids = default_ids(n_math)
        for k, v in (ids or {}).items():
            self.ids[k] = v
        self.rows_spec = rows or {}          # {(kind, arm, block): {key: patch}}  (m1: nested overrides of `qualify`)
        self.legs_spec = legs or {}          # {(kind, arm, block): receipt patch (shallow)}
        self.flags = {}                      # {(kind, arm, block): worker flag list}
        self.scrub_files = {}
        self.p426.mkdir(parents=True, exist_ok=True)
        self.commits = self._init_repo(w1_off or {}, w2 or {}, w2_gitlinks or {})
        self.registry_sha = {}
        for arm in ARMS:     # the blob bytes, as the contract does (sha256 of `git show <head>:main_models.yaml`)
            blob = subprocess.run(["git", "show", f"{self.commits['w1_' + arm]}:main_models.yaml"], cwd=self.repo,
                                  capture_output=True, check=True).stdout
            self.registry_sha[arm] = sha_bytes(blob)
        self.frozen = {"build": "s2", "stack_head_off": self.commits["w1_off"], "stack_head_on": self.commits["w1_on"],
                       "stack_clean_off": True, "stack_clean_on": True, "mlx_vlm": GITLINKS["src/mlx-vlm"],
                       "mlx_serve": GITLINKS["src/mlx-serve"], "production_ref": "b2" * 20,
                       "registry_off_sha": self.registry_sha["off"], "registry_on_sha": self.registry_sha["on"],
                       "uv_lock_sha256": "74" * 32, "bench_lock_sha256": "46" * 32,
                       "venvs": {"off": {".venv": {"mlx": "0.32.4"}}, "on": {".venv": {"mlx": "0.32.4"}}}}
        self.frozen.update(frozen or {})
        mp.setattr(a7world, "OFF_COMMIT", self.commits["w2_off"])
        mp.setattr(a7world, "ON_COMMIT", self.commits["w1_on"])
        self.a7 = a7world.World(self.base, **(a7 or {})) if with_a7 else None
        from bench import generate
        mp.setattr(generate, "RESULTS", self.rows_root)
        self._build(smoke=smoke, s_build=s_build)

    # --------------------------------------------------------------------------------------------------- git
    def _init_repo(self, w1_off, w2, w2_gitlinks):
        self.repo.mkdir(parents=True, exist_ok=True)
        git(self.repo, "init", "-q")
        base = dict(BASE_CODE)
        base["main_models.yaml"] = registry_text()
        base.update(w1_off)
        c1 = commit_tree(self.repo, base, GITLINKS, "wave1 off")
        c2 = commit_tree(self.repo, {"main_models.yaml": registry_text(draft_kind="mtp")}, {}, "wave1 on")
        w2files = {"main_models.yaml": base["main_models.yaml"]}
        w2files.update(w2)
        c3 = commit_tree(self.repo, w2files, w2_gitlinks, "wave2 off")
        return {"w1_off": c1, "w1_on": c2, "w2_off": c3}

    # --------------------------------------------------------------------------------------------------- paths
    def leg_dir(self, kind, arm, block):
        return self.w1 / leg_name(kind, arm, block)

    def path_of(self, kind, arm, block, what):
        t, b = tune_of(arm, block), BENCH_OF.get(kind)
        d = self.leg_dir(kind, arm, block)
        m1 = d / "m1" / ENTRY
        table = {"receipt": d / f"{leg_name(kind, arm, block)}.receipt.json", "scrub": d / "SCRUB_MANIFEST.json",
                 "stdout": d / "leg.stdout", "log": d / f"{leg_name(kind, arm, block)}.log", "legdir": d,
                 "result": m1 / "result.json", "job": m1 / "job.json", "report": d / "m1" / "report.json"}
        if b:
            ext = "json" if kind == "reasoning" else "jsonl"
            table.update(rows=self.edir / f"{b}.{t}.{ext}", manifest=self.edir / f"{b}.{t}.manifest.json",
                         score=self.edir / f"{b}.{t}.score.json", summary=self.edir / f"{b}.{t}.summary.json")
        return table[what]

    def rel(self, path):
        return Path(path).relative_to(self.rows_root).as_posix()

    # --------------------------------------------------------------------------------------------------- rows
    def _patch(self, kind, arm, block, key, row):
        patch = copy.deepcopy((self.rows_spec.get((kind, arm, block)) or {}).get(key, {}))
        ok = patch.pop("ok", None)
        if ok is not None and kind == "math500":
            row["content"] = f"Work for {row['id']}. The answer is \\boxed{{{'7' if ok else '8'}}}."
        row.update(patch)
        return row

    def _finish(self, row, patch_has):
        if "content" in row and row.get("content_sha256") is not None and "content_sha256" not in patch_has:
            row["content_sha256"] = sha_text(row["content"])
        return row

    def make_math(self, arm, block, rid):
        row = {"id": rid, "sample": 0, "schema_version": 2, "sampler_seed": sampler_seed("math500", rid), "seed_base": 0,
               "bench": "math500", "model": ENTRY, "recovery": None, "answer_gold": "7", "options": None,
               "content": f"Work for {rid}. The answer is \\boxed{{7}}.", "completion_tokens": 1000, "prompt_tokens": 99,
               "decode_tps": RATE[arm], "finish_reason": "stop", "wall_s": 20.0, "thinking_budget": 81920,
               "draft": draft(arm), "converged": True, "nonconv_kind": None, "content_sha256": "x"}
        spec = (self.rows_spec.get(("math500", arm, block)) or {}).get(rid, {})
        row = self._patch("math500", arm, block, rid, row)
        return self._finish(row, spec)

    def make_cjudge(self, arm, block, rid):
        row = {"id": rid, "sample": 0, "schema_version": 2, "sampler_seed": sampler_seed("cjudge", rid), "seed_base": 0,
               "bench": "cjudge", "model": ENTRY, "recovery": None, "answer_gold": None, "options": None,
               "content": f"# Essay for {rid}", "completion_tokens": 2000, "prompt_tokens": 32, "decode_tps": RATE[arm],
               "finish_reason": "stop", "wall_s": 61.6, "thinking_budget": 81920, "draft": draft(arm, 100, 75),
               "converged": True, "nonconv_kind": None, "content_sha256": "x"}
        spec = (self.rows_spec.get(("cjudge", arm, block)) or {}).get(rid, {})
        row = self._patch("cjudge", arm, block, rid, row)
        return self._finish(row, spec)

    def make_vision(self, arm, block, rid):
        seed = sampler_seed("vision", rid)
        row = {"id": rid, "image_ref": {"dataset": "x", "index": 1}, "image_sha256": sha_text(f"img|{rid}"),
               "session_id": f"p426-vision-{arm}-{rid}", "seed": seed, "description": f"A picture of {rid}.",
               "prompt_tokens": 238, "completion_tokens": 432, "wall_s": 10.1, "decode_tps": RATE[arm],
               "finish_reason": "stop", "converged": True, "draft": draft(arm, 100, 72), "verdict": "PASS",
               "verdict_raw": "PASS", "turn2": {"prompt_tokens": 672, "completion_tokens": 162, "wall_s": 4.9,
                                                  "finish_reason": "stop", "converged": True, "draft": draft(arm, 100, 40),
                                                  "seed": seed + 1, "session_id": f"p426-vision-{arm}-{rid}-t2"}}
        return self._patch("vision", arm, block, rid, row)

    def make_reasoning_row(self, arm, block, trial, task_seed):
        row = {"trial": trial, "seed": task_seed, "sampler_seed": self.ids["reasoning"]["request_seeds"][str(task_seed)],
               "session_id": f"p426-reasoning-{arm}-{task_seed}", "content": f"Tracing the variables for {task_seed}.",
               "score": 1.0, "completion_tokens": 304, "finish_reason": "stop", "budget_hit": False,
               "decode_tps": RATE[arm], "wall_s": 240.7, "prompt_tokens": 127714, "prefill_s": 229.9, "prefill_tps": 555,
               "draft": draft(arm, 200, 180)}
        return self._patch("reasoning", arm, block, task_seed, row)

    # --------------------------------------------------------------------------------------------------- manifests
    def manifest_doc(self, kind, arm, block):
        reg = self.frozen[f"registry_{arm}_sha"]
        return {"model": ENTRY, "box": "m5max-128", "timestamp": 1793186880,
                "kv": {"hf_path": f"caslca/{ENTRY}", "kv_bits": 0, "kv_quant_scheme": "turboquant", "quantized_kv_start": 0,
                       "prefill_step_size": 512, "max_kv_cache_size": 262144, "kv_prealloc_tokens": 262144,
                       "cache_session_shrink": True},
                "sampling": {"temperature": 0.5, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0,
                             "max_tokens": 102400, "thinking_budget": 81920, "enable_thinking": True,
                             "reasoning_effort": "medium"},
                "runtime": {"draft_kind": "mtp" if arm == "on" else None, "mtp_verify_scan": "joint_v1" if arm == "on" else None},
                "sampling_profile": "deployed", "registry": {"sha256": reg, "dirty": False},
                "router": {"pid": 95847 if arm == "on" else 41234, "config_sha256": reg}, "tune": tune_of(arm, block)}

    # --------------------------------------------------------------------------------------------------- build
    def _write(self, path, text):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)

    def _build(self, smoke, s_build):
        self.p426.mkdir(parents=True, exist_ok=True)
        axes = {k: v for k, v in self.ids.items()}
        self._write(self.p426 / "ids.json", dumps({"entry": ENTRY, "seed": 426, "axes": axes, "sources_sha256": {}}))
        (self.w1 / "run").mkdir(parents=True, exist_ok=True)
        self._write(self.w1 / "run" / "frozen.s2.json", dumps(self.frozen))
        self.frozen_sha = sha_bytes((self.w1 / "run" / "frozen.s2.json").read_bytes())
        for kind in KINDS:
            for block in BLOCKS:
                for arm in ARMS:
                    self._build_leg(kind, arm, block)
        for kind in KINDS:
            for block in BLOCKS:
                for arm in ARMS:
                    self.rescrub(kind, arm, block)
        if smoke:
            self._build_excluded()
        if s_build:
            self._build_s_build()

    def _rows_for(self, kind, arm, block):
        key = {"math500": "math500", "cjudge": "cjudge", "vision": "vision"}[kind]
        ids = self.ids[key]["block1" if block == "b1" else "block2"]
        make = {"math500": self.make_math, "cjudge": self.make_cjudge, "vision": self.make_vision}[kind]
        return [make(arm, block, rid) for rid in ids]

    def _write_rows(self, kind, arm, block, rows):
        self._write(self.path_of(kind, arm, block, "rows"), "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))

    def reasoning_doc(self, arm, block, rows):
        acc_n = sum((r["draft"] or {}).get("draft_n") or 0 for r in rows)
        acc_a = sum((r["draft"] or {}).get("draft_n_accepted") or 0 for r in rows)
        rec = {"ctx": 128000, "accuracy": sum(r["score"] for r in rows) / len(rows), "samples": len(rows), "chain_len": 4,
               "errors": 0, "budget_hits": sum(1 for r in rows if r["budget_hit"]), "early_stop": False, "rows": rows,
               "acceptance_pooled": round(acc_a / acc_n, 4) if acc_n else None}
        return {"model": ENTRY, "axis": "reasoning", "task": "vartrack", "threshold": 0.85, "grid": [128000],
                "params": {"temperature": 0.5, "max_tokens": 102400, "thinking_budget": 81920}, "records": [rec],
                "reasoning_effective_ctx": 128000}

    def _build_leg(self, kind, arm, block):
        d = self.leg_dir(kind, arm, block)
        d.mkdir(parents=True, exist_ok=True)
        files = []
        if kind == "m1":
            files += self._build_m1(arm, block)
            n_rows = 1
        elif kind == "reasoning":
            seeds = self.ids["reasoning"]["block1" if block == "b1" else "block2"]
            rows = [self.make_reasoning_row(arm, block, i, s) for i, s in enumerate(seeds)]
            self._write(self.path_of(kind, arm, block, "rows"), dumps(self.reasoning_doc(arm, block, rows)))
            self._write(self.path_of(kind, arm, block, "manifest"), dumps(self.manifest_doc(kind, arm, block)))
            files += [self.path_of(kind, arm, block, w) for w in ("rows", "manifest")]
            n_rows = len(rows)
        else:
            rows = self._rows_for(kind, arm, block)
            self._write_rows(kind, arm, block, rows)
            self._write(self.path_of(kind, arm, block, "manifest"), dumps(self.manifest_doc(kind, arm, block)))
            files += [self.path_of(kind, arm, block, w) for w in ("rows", "manifest")]
            if kind == "math500":
                self.regrade(arm, block)
                files.append(self.path_of(kind, arm, block, "score"))
            if kind == "vision":
                self._write(self.path_of(kind, arm, block, "summary"), dumps({"n": len(rows)}))
                files.append(self.path_of(kind, arm, block, "summary"))
            n_rows = len(rows)
        self._write(self.path_of(kind, arm, block, "stdout"), f"stdout {leg_name(kind, arm, block)}\n")
        self._write(self.path_of(kind, arm, block, "log"), f"log {leg_name(kind, arm, block)}\n")
        files += [self.path_of(kind, arm, block, w) for w in ("stdout", "log")]
        self._write_receipt(kind, arm, block, n_rows)
        files.append(self.path_of(kind, arm, block, "receipt"))
        self.scrub_files[(kind, arm, block)] = [self.rel(f) for f in files]

    def _write_receipt(self, kind, arm, block, n_rows):
        name = leg_name(kind, arm, block)
        pins = dict(self.frozen, frozen_sha=self.frozen_sha)
        state = {"stack_head": self.frozen[f"stack_head_{arm}"], "stack_clean": True, "mlx_vlm": self.frozen["mlx_vlm"],
                 "mlx_serve": self.frozen["mlx_serve"], "frozen_sha": self.frozen_sha,
                 "uv_lock_sha256": self.frozen["uv_lock_sha256"], "bench_lock_sha256": self.frozen["bench_lock_sha256"]}
        secs = wall_seconds(kind, arm, block)
        rec = {"name": name, "arm": arm, "kind": "qualify" if kind == "m1" else kind, "model": ENTRY, "problems": [],
               "speed_problems": [], "pins": pins, "state": state, "pre_state": {"watts": 140, "volts": 28.0},
               "started": "2026-10-28 04:00:00", "ended": _hms(secs), "verdict": "VALID", "speed_valid": True}
        if kind == "m1":
            rec["report"] = {"predictor": arm, "entries": {ENTRY: {"status": "COMPLETED"}}}
            rec["overlay"] = {"file": f"overlay-{ENTRY}.yaml", "sha256": self.frozen[f"registry_{arm}_sha"]}
        else:
            self.flags[(kind, arm, block)] = worker_flags(arm)
            pid = 95861 if arm == "on" else 41234
            rec["router_pid"] = pid - 14
            rec["worker"] = {"pid": pid, "create_time": 1793186853.1, "cmdline": render_cmdline(arm, pid, self.flags[(kind, arm, block)])}
            rec["log"] = {"started": n_rows, "completed": n_rows, "failed": 0, "overlapping": 0}
        rec.update(copy.deepcopy(self.legs_spec.get((kind, arm, block), {})))
        self._write(self.path_of(kind, arm, block, "receipt"), dumps(rec))

    def _build_m1(self, arm, block):
        peaks = dict(zip(M1_PEAK_KEYS, M1_PEAKS[(arm, block)]))
        qualify = {"backend": "cached_session", "boundary_seen": True, "finish_reason": "stop", "generate_seed": 7,
                   "generation_tokens": 637, "peaks": peaks,
                   "prompt": {"prepared": {"sha256": "4e" * 32, "tokens": 260096}, "sized": {"sha256": "4e" * 32, "tokens": 260096}},
                   "rates": {"decode_tps": M1_RATES[(arm, block)], "prefill_tps": 383.5}}
        for k, v in copy.deepcopy(self.rows_spec.get(("m1", arm, block)) or {}).items():
            if isinstance(v, dict) and isinstance(qualify.get(k), dict):
                qualify[k].update(v)
            else:
                qualify[k] = v
        result = {"status": "ok", "mode": "qualify", "job": f"{ENTRY}/qualify",
                  "served": {"draft_kind": "mtp" if arm == "on" else None, "drafter_loaded": arm == "on",
                             "verify_policy": "joint_v1" if arm == "on" else None,
                             "kv": {"kv_quant_scheme": "turboquant", "quantized_kv_start": 0}, "session_max": 1,
                             "session_max_env": "1", "apc_manager": False},
                  "snapshots": {"--model": "1dd70b36b8a800568576ad12fdeef3c7d3c2dc61"},
                  "requests": [{"name": "qualify", "qualify": qualify}]}
        if arm == "on":
            result["snapshots"]["--draft-model"] = "0caad904fdd7706310f42f342226e7ae9b2d55dc"
        self.flags[("m1", arm, block)] = worker_flags(arm)
        job = {"name": f"{ENTRY}/qualify", "mode": "qualify", "argv": flat_argv(self.flags[("m1", arm, block)]),
               "expect": {"drafter": arm == "on"}}
        report = {"predictor": arm, "entries": {ENTRY: {"status": "COMPLETED"}}, "reviewed_head": GITLINKS["src/mlx-vlm"],
                  "registry_sha256": self.frozen[f"registry_{arm}_sha"], "production": "b2" * 20,
                  "versions": {"mlx": "0.32.4"}, "end_problems": []}
        self._write(self.path_of("m1", arm, block, "result"), dumps(result))
        self._write(self.path_of("m1", arm, block, "job"), dumps(job))
        self._write(self.path_of("m1", arm, block, "report"), dumps(report))
        return [self.path_of("m1", arm, block, w) for w in ("result", "job", "report")]

    def _build_excluded(self):
        for kind in KINDS:
            for arm in ARMS:
                d = self.w1 / f"{kind}-p426s2-{arm}-smoke"
                d.mkdir(parents=True, exist_ok=True)
                self._write(d / f"{kind}-p426s2-{arm}-smoke.receipt.json",
                            dumps({"name": f"{kind}-p426s2-{arm}-smoke", "arm": arm, "verdict": "VALID", "problems": []}))
                if kind in BENCH_OF:
                    t = f"p426s2-{arm}-smoke"
                    self._write(self.edir / f"{BENCH_OF[kind]}.{t}.jsonl", json.dumps({"id": "smoke-row", "sampler_seed": 1}) + "\n")
        (self.w1 / "archive" / "m1-p426s2-off-smoke.attempt1-fork-venv").mkdir(parents=True, exist_ok=True)
        self._write(self.w1 / "archive" / "m1-p426s2-off-smoke.attempt1-fork-venv" / "x.log", "old\n")

    def _build_s_build(self):
        d = self.p426 / "wave1"
        d.mkdir(parents=True, exist_ok=True)
        self._write(d / "README.txt", "the S build, never pooled with S'\n")
        for arm in ARMS:
            self._write(self.edir / f"math500.p426-{arm}-b1.jsonl", json.dumps({"id": "s-build-row", "sampler_seed": 2}) + "\n")

    # --------------------------------------------------------------------------------------------------- mutation API
    def rescrub(self, kind, arm, block):
        files = {}
        for rel in self.scrub_files[(kind, arm, block)]:
            p = self.rows_root / rel
            if not p.exists():
                continue
            sha = sha_bytes(p.read_bytes())
            files[f"benchmark/results/{rel}"] = {"original_sha256": sha, "published_sha256": sha, "scrubbed_sha256": sha,
                                                 "source": None}
        self._write(self.path_of(kind, arm, block, "scrub"), dumps({"files": files}))

    def regrade(self, arm, block):
        from bench import grade
        score = grade.grade("math500", ENTRY, tune=tune_of(arm, block))
        score = {k: v for k, v in score.items() if k not in ("items", "strict_items")}
        self._write(self.path_of("math500", arm, block, "score"), dumps(score))

    def read_rows(self, kind, arm, block):
        p = self.path_of(kind, arm, block, "rows")
        if kind == "reasoning":
            return json.loads(p.read_text())["records"][0]["rows"]
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

    def edit_rows(self, kind, arm, block, fn, *, rescrub=True, rescore=True):
        """fn(list_of_rows) -> list | None, applied to the leg's rows; a `content` change recomputes `content_sha256` unless
        the row's sha was edited too. math500 `score.json` is regraded (rescore) and the leg re-scrubbed (rescrub)."""
        rows = copy.deepcopy(self.read_rows(kind, arm, block))
        before = {id(r): dict(r) for r in rows}
        out = fn(rows)
        rows = out if isinstance(out, list) and all(isinstance(r, dict) for r in out) else rows
        for r in rows:
            old = before.get(id(r))
            if (old is not None and "content" in r and r.get("content_sha256") is not None and old.get("content") != r["content"]
                    and old.get("content_sha256") == r.get("content_sha256")):
                r["content_sha256"] = sha_text(r["content"])
        if kind == "reasoning":
            doc = json.loads(self.path_of(kind, arm, block, "rows").read_text())
            seeds = [r["seed"] for r in rows]
            doc = self.reasoning_doc(arm, block, rows)
            self._write(self.path_of(kind, arm, block, "rows"), dumps(doc))
            assert seeds
        else:
            self._write_rows(kind, arm, block, rows)
            if kind == "math500" and rescore:
                self.regrade(arm, block)
        if rescrub:
            self.rescrub(kind, arm, block)

    def edit_json(self, kind, arm, block, what, fn, *, rescrub=True):
        p = self.path_of(kind, arm, block, what)
        doc = json.loads(p.read_text())
        out = fn(doc)
        self._write(p, dumps(doc if out is None else out))
        if rescrub:
            self.rescrub(kind, arm, block)

    def edit_receipt(self, kind, arm, block, fn, *, rescrub=True):
        self.edit_json(kind, arm, block, "receipt", fn, rescrub=rescrub)

    def set_flags(self, kind, arm, block, fn, *, rescrub=True):
        """fn(list of (flag, value|None)) -> list: rewrites the worker cmdline (router legs) or `job.json` argv (M1)."""
        flags = fn(list(self.flags[(kind, arm, block)]))
        self.flags[(kind, arm, block)] = flags
        if kind == "m1":
            self.edit_json(kind, arm, block, "job", lambda d: d.update(argv=flat_argv(flags)), rescrub=rescrub)
        else:
            def edit(d):
                d["worker"]["cmdline"] = render_cmdline(arm, d["worker"]["pid"], flags)
            self.edit_receipt(kind, arm, block, edit, rescrub=rescrub)

    def edit_ids(self, fn):
        p = self.p426 / "ids.json"
        doc = json.loads(p.read_text())
        out = fn(doc)
        self._write(p, dumps(doc if out is None else out))
