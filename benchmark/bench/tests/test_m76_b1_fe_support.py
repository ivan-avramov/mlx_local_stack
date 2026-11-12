"""M76 B1 (test-writer): shared fakes for the `f45` campaign tests — a fake box over the REAL committed `main_models.yaml` entry of
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. Formats are the ones the code emits: the `KV cache resolved:` line, the worker argv
as a list, the worker's `tq4_attention=<mode> self-test:` stderr line, the manifest's `tq4_route_counts_at_creation` and
`router_exit.tq4_route_counts_at_exit` blocks (`bench.provenance.tq4_route_counts`: {"mode", "route_counts", "source"}).

Nothing here assumes a name the specification does not give: arm registry texts come from the candidate's own `prepare`
(`prepared_texts`), the campaign is selected only through `--campaign f45` on the public CLI.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from bench import p426_harvest
from bench import p475_kv as K
from bench.tests.test_p475_impl_support import BASE, SERVE_LINK, VLM_LINK, FakeHandle, FakeOps, ladder_row

F45_PICK = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
F45_ARMS = ("N16", "X", "V", "XO")
F45_MODE = {"N16": "off", "X": "m72_exact", "V": "m72_v1", "XO": "m72_exact"}
F45_ON = {"N16": True, "X": True, "V": True, "XO": False}                  # predictor (MTP) ON
REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_REGISTRY = REPO_ROOT / "main_models.yaml"
GRID = (8192, 131072, 196608, 260096)
LEG_F45 = re.compile(r"f45-(n16|x|v|xo)-(b[1-9][0-9]*|smoke)\.a([1-9][0-9]*)")

# Errata v1.1: the rules apply to the EXIT snapshot's ABSOLUTE counters (a fresh worker per leg; the manifest's creation snapshot is
# taken after the ladder, so it equals the exit one on a real leg). A healthy leg: the arm's required counters > 0, every other
# counter (and every `fallback:*`) 0; the creation block (right mode) carries the same values.
ZERO_ROUTES = {"p2s": 0, "mma": 0, "d2": 0, "d2_verify": 0, "native:prefill": 0, "native:decode": 0, "native:verify": 0,
               "fallback:shape": 0}
GOOD_EXIT = {
    "X": {"p2s": 40, "d2_verify": 900, "native:prefill": 20, "native:verify": 950},
    "V": {"p2s": 40, "mma": 900, "native:prefill": 20, "native:verify": 950},
    "XO": {"p2s": 40, "d2": 1200, "native:prefill": 20, "native:decode": 1300},
}
# per arm: the counters that must be > 0 at exit, must be 0 at exit — fallback:* always 0 (spec "Mode proof", Errata v1.1)
MUST_GROW = {"X": ("p2s", "d2_verify", "native:prefill", "native:verify"),
             "V": ("p2s", "mma", "native:prefill", "native:verify"),
             "XO": ("p2s", "d2", "native:prefill", "native:decode")}
MUST_STAY = {"X": ("mma", "fallback:shape"), "V": ("d2_verify", "fallback:shape"),
             "XO": ("mma", "d2_verify", "native:verify", "fallback:shape")}


def real_text():
    return REAL_REGISTRY.read_text()


def entry_of(text, name=F45_PICK):
    return next(m for m in yaml.safe_load(text)["models"] if m["name"] == name)


def entry_lines(text, name=F45_PICK):
    """(lines of the file, start, end) of the `- name: <name>` entry (end = the next top-level list item or key)."""
    lines = text.splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if re.match(rf"^  - name:\s*{re.escape(name)}\s*(#.*)?$", ln))
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j]
        if s.strip() and not s.lstrip().startswith("#") and (len(s) - len(s.lstrip())) < 4:
            end = j
            break
    return lines, start, end


# ================================================================================================ worker argv, logs
def f45_worker_argv(text, model, wt):
    """The worker argv as mlx-serve builds it from the entry (flag order irrelevant to the tests: observed and expected both come
    from here): the existing flags plus `--tq4-attention` and `--mtp-verify-scan` when the entry carries them."""
    doc = yaml.safe_load(text)
    e = entry_of(text, model)
    cmd = [f"{wt}/.venv/bin/mlx_vlm.server", "--model", e["hf_path"], "--host", "127.0.0.1", "--port", str(doc["mlx_port"])]
    if e.get("max_kv_cache_size"):
        cmd += ["--max-kv-size", str(e["max_kv_cache_size"])]
    if e.get("kv_prealloc_tokens"):
        cmd += ["--kv-prealloc-tokens", str(e["kv_prealloc_tokens"])]
    if (e.get("kv_bits") or 0) > 0:
        cmd += ["--kv-bits", str(e["kv_bits"])]
    if e.get("kv_quant_scheme"):
        cmd += ["--kv-quant-scheme", e["kv_quant_scheme"]]
    if e.get("tq4_attention"):
        cmd += ["--tq4-attention", str(e["tq4_attention"])]
    if e.get("prefill_step_size"):
        cmd += ["--prefill-step-size", str(e["prefill_step_size"])]
    if e.get("generation_defaults"):
        cmd += ["--generation-defaults", json.dumps(e["generation_defaults"])]
    if e.get("draft_kind"):
        cmd += ["--draft-kind", e["draft_kind"]]
        if e.get("draft_model"):
            cmd += ["--draft-model", e["draft_model"]]
        if e.get("mtp_verify_scan"):
            cmd += ["--mtp-verify-scan", str(e["mtp_verify_scan"])]
    return cmd + ["--quantized-kv-start", str(e.get("quantized_kv_start", 0))]


def kv_log(arm, **over):
    native = arm == "N16"
    vals = dict(kv_bits=None if native else 4.0, kv_key_bits=None, kv_value_bits=None, kv_key_scheme=None, kv_value_scheme=None,
                kv_quant_scheme="turboquant", kv_group_size=64, quantized_kv_start=0, TQ_KV_QUANT_MODE="mse")
    vals.update(over)
    body = " ".join(f"{k}={v!r}" for k, v in vals.items())
    return f"2026-11-04 10:00:00,000 INFO mlx_vlm.server.app: KV cache resolved: {body}\n"


def selftest_line(mode):
    return f"2026-11-04 10:00:01,000 INFO mlx_vlm.server.generation: tq4_attention={mode} self-test: ok max_abs_err=1.2e-04\n"


def route_block(mode, counts):
    return {"mode": mode, "route_counts": counts, "source": "worker-health"}


def good_exit(arm, block=1):
    """The required (> 0) exit counters of a healthy leg: GOOD_EXIT × the block number (a smoke leg counts as block 1), so the legs
    of one arm are told apart in the recorded counters."""
    mult = block if isinstance(block, int) else 1
    return {k: v * mult for k, v in GOOD_EXIT[arm].items()}


def good_counts(arm, block=1):
    """(creation, exit) route counters of a healthy leg of `arm` (None, None for N16: no mode, no counters). Every counter is
    present; creation == exit (the manifest is gathered after the ladder)."""
    if arm == "N16":
        return None, None
    exit_ = dict(ZERO_ROUTES, **good_exit(arm, block))
    return dict(exit_), exit_


# ================================================================================================ the fake box
class F45Handle(FakeHandle):
    def load(self, model):
        self.ops.calls.append(("load", model))
        arm = self.ops.arm_of(self.wt)
        log = self.wt / "logs" / "mlx_vlm.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write("2026-11-04 09:59:59,000 INFO loading\n")
            f.write(self.ops.kv_line_for(arm))
            st = self.ops.selftest_for(arm)
            if st:
                f.write(st)
        self.ops.alive.add((200, 2.0))
        self.loaded = True
        argv = self.ops.worker_argv_override or f45_worker_argv(self.registry.read_text(), model, self.wt)
        return dict(pid=200, create_time=2.0, cmdline=list(argv))

    def expected_worker_argv(self, registry, model):
        return f45_worker_argv(Path(registry).read_text(), model, self.wt)

    def env_base(self):
        """What the router handle hands out: the fake's KV / TQ names plus the two MTP draft variables a shell could export."""
        return dict(super().env_base(), MLX_VLM_DRAFT_KIND="mtp", MLX_VLM_DRAFT_MODEL="caslca/inherited-drafter")


class F45Ops(FakeOps):
    """`FakeOps` with the f45 arms: real registry entry, f45 worker argv / KV line / self-test line, and a driver that writes the
    ladder rows plus a manifest carrying the TQ4 route-counter blocks."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.wd, self.repo = self.tmp / "wd", self.tmp / "repo"
        (self.repo / "benchmark" / "results").mkdir(parents=True, exist_ok=True)
        self.wd.mkdir(parents=True, exist_ok=True)
        self.base_text = real_text()
        self.selftest = {}               # arm -> line text (or None for no line); absent = the arm's healthy line
        self.kv_over_arm = {}            # arm -> dict of KV line field overrides
        self.manifest_edit = {}          # arm -> f(manifest dict) mutating it
        self.metric = lambda arm, block, ctx: {}

    # -- world
    def add_arm(self, cfg, arm, text):
        self.cfg = cfg
        head = BASE if arm == "N16" else f"{F45_ARMS.index(arm) + 1:x}" * 40
        rec = dict(head=head, branch_tip=head, parent=BASE, clean=True, files=[] if arm == "N16" else [K.REGISTRY], text=text,
                   gitlinks={"src/mlx-vlm": VLM_LINK, "src/mlx-serve": SERVE_LINK})
        self.arms[arm] = rec
        wt = cfg.worktree(arm)
        wt.mkdir(parents=True, exist_ok=True)
        (wt / K.REGISTRY).write_text(text)
        (wt / "benchmark").mkdir(exist_ok=True)
        from bench.tests.test_p475_impl_support import install_instrument
        for root in (cfg.repo, wt):
            install_instrument(root)
        return rec

    def add_all(self, cfg, texts, preflight=True):
        for arm in F45_ARMS:
            self.add_arm(cfg, arm, texts[arm])
            if preflight:
                # Errata v1.1: non-u4 preflight / engagement records carry `campaign` (a record without it reads as u4)
                K._atomic_json(cfg.preflight_record(arm),
                               dict(arm=arm, status="PASS", attempts=[], base=cfg.base, campaign="f45"))
                if F45_ON[arm]:
                    K._atomic_json(cfg.preflight_record(arm, "engagement"),
                                   dict(arm=arm, kind="engagement", status="PASS", attempts=[], base=cfg.base, campaign="f45"))

    # -- formats
    def kv_line_for(self, arm):
        return kv_log(arm, **self.kv_over_arm.get(arm, {}))

    def selftest_for(self, arm):
        if arm in self.selftest:
            return self.selftest[arm]
        return None if arm == "N16" else selftest_line(F45_MODE[arm])

    def manifest_for(self, arm, block=1):
        creation, exit_ = good_counts(arm, block)
        man = dict(runtime=dict(probe="capacity_ladder"), router=dict(pid=100), router_exit=dict(pid=100, verified_at="exit"))
        if arm != "N16":
            man["tq4_route_counts_at_creation"] = route_block(F45_MODE[arm], creation)
            man["router_exit"]["tq4_route_counts_at_exit"] = route_block(F45_MODE[arm], exit_)
        if arm in self.manifest_edit:
            self.manifest_edit[arm](man)
        return man

    # -- Ops
    def git(self, wt, *args):
        if args[:1] == ("show",) and str(args[1]).startswith(BASE):
            self.calls.append(("git", str(wt), args))
            return self.base_text
        return super().git(wt, *args)

    def stack(self, wt, registry, predictor):
        self.calls.append(("stack", str(wt), str(registry), predictor))
        return F45Handle(self, wt, registry, predictor)

    def scrub(self):
        return p426_harvest.Scrub(workdir=self.wd, repo=self.repo, home=self.tmp / "home", user="p475fakeuser",
                                  hosts=("p475fakehost",))

    def _leg(self):
        tag = self._current["argv"][self._current["argv"].index("--out-tag") + 1]
        return LEG_F45.search(tag).group(0)

    def wait(self, proc, timeout):
        if (proc["pid"], proc["create_time"]) not in self.alive:
            return 0
        leg = self._leg()
        script = self.leg_script.get(leg, {})
        if self.driver_hangs or script.get("hang"):
            self.t += timeout if timeout else 0
            return None
        self.t += script.get("seconds", self.driver_seconds)
        m = LEG_F45.fullmatch(leg)
        arm = {"n16": "N16", "x": "X", "v": "V", "xo": "XO"}[m.group(1)]
        block = "smoke" if m.group(2) == "smoke" else int(m.group(2)[1:])
        argv = self._current["argv"]
        grid = [int(x) for x in argv[argv.index("--grid") + 1].split(",")]
        tag = argv[argv.index("--out-tag") + 1]
        out = Path(argv[argv.index("--out-dir") + 1])
        prefix = self._current["env"]["MLX_BENCH_SESSION_PREFIX"]
        out.mkdir(parents=True, exist_ok=True)
        pred = "on" if F45_ON[arm] else "off"
        with (out / f"capacity_ladder.{tag}.jsonl").open("w") as f:
            for ctx in grid:
                row = ladder_row(ctx, pred, prefix, **self.metric(arm, block, ctx))
                row.update(self.row_over)
                row.update(script.get("row_over", {}))
                f.write(json.dumps(row) + "\n")
        (out / f"capacity_ladder.{tag}.manifest.json").write_text(json.dumps(self.manifest_for(arm, block)))
        self.alive.discard((proc["pid"], proc["create_time"]))
        return script.get("driver_rc", self.driver_rc)

    def run(self, argv, cwd, env, timeout):
        cp = super().run(argv, cwd, env, timeout)
        if "--engagement-only" in argv:                     # the fork's P658 (a) report fields
            out = Path(argv[argv.index("--out") + 1]) / "report.json"
            doc = json.loads(out.read_text())
            doc.update(predictor="on", engagement_only=True, certifies=False)
            out.write_text(json.dumps(doc))
        return cp

    # -- inspection
    def spawned_legs(self):
        return [LEG_F45.search(s["argv"][s["argv"].index("--out-tag") + 1]).group(0) for s in self.spawned]


# ================================================================================================ prepare (public entry) fake
class PrepOps:
    """Just enough git / uv for `main(["prepare"])`: records what `prepare` commits per arm branch."""

    def __init__(self, base_text, base=BASE):
        self.base_text, self.base = base_text, base
        self.calls = []
        self.branches, self.heads, self.wt_branch, self.commits = {}, {}, {}, {}

    def worktree_state(self, wt):
        return dict(head=self.heads[str(wt)], clean=True,
                    gitlinks={"src/mlx-vlm": VLM_LINK, "src/mlx-serve": SERVE_LINK})

    def git(self, wt, *args):
        a = [str(x) for x in args]
        self.calls.append((str(wt), tuple(a)))
        rest = [x for x in a[1:] if not x.startswith("-")]
        if a[0] == "rev-parse":
            if rest and rest[-1].endswith("^{commit}"):
                return self.base + "\n"
            ref = rest[-1] if rest else "HEAD"
            if ref.endswith("^"):
                return self.base + "\n"
            if ref.startswith("refs/heads/"):
                br = ref[len("refs/heads/"):]
                if br in self.branches:
                    return self.branches[br] + "\n"
                raise RuntimeError("no such branch")
            if ref == "HEAD":
                return self.heads.get(str(wt), self.base) + "\n"
        if a[:2] == ["worktree", "add"]:
            if "-b" in a:
                br, path = a[a.index("-b") + 1], a[a.index("-b") + 2]
                self.branches[br] = self.base
            else:
                path, br = a[2], a[3]
            Path(path).mkdir(parents=True, exist_ok=True)
            self.heads[path], self.wt_branch[path] = self.branches[br], br
            return ""
        if a[0] == "commit":
            text = (Path(wt) / K.REGISTRY).read_text()
            sha = hashlib.sha1(text.encode()).hexdigest()
            self.commits[sha] = text
            self.branches[self.wt_branch[str(wt)]] = self.heads[str(wt)] = sha
            return ""
        if a[0] == "show":
            ref = a[1].split(":", 1)[0]
            return self.base_text if ref == self.base else self.commits[ref]
        if a[0] == "diff":
            return "" if self.heads[str(wt)] == self.base else f"{K.REGISTRY}\n"
        if a[0] == "ls-tree":
            return f"160000 commit {VLM_LINK}\tsrc/mlx-vlm\n160000 commit {SERVE_LINK}\tsrc/mlx-serve\n"
        return ""

    def run(self, argv, cwd, env, timeout):
        argv = [str(x) for x in argv]
        self.calls.append((str(cwd), tuple(argv)))
        if argv[:2] == ["uv", "sync"]:
            (Path(cwd) / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
            (Path(cwd) / ".venv" / "bin" / "python").write_text("")
        elif "venv" in argv:
            target = Path(argv[-1])
            (target / "bin").mkdir(parents=True, exist_ok=True)
            (target / "bin" / "python").write_text("")
        return subprocess.CompletedProcess(argv, 0, "", "")

    # -- results
    def committed(self, branch):
        return self.commits.get(self.branches.get(branch))


def prepare_f45(tmp_path, base_text=None, campaign="f45"):
    """(rc, ops, workdir) of `main(--campaign <campaign> prepare)` on a fresh workdir over `base_text` (default: the real file)."""
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    wd.mkdir(parents=True, exist_ok=True)
    ops = PrepOps(base_text if base_text is not None else real_text())
    rc = K.main(["--workdir", str(wd), "--repo", str(repo), "--base", BASE, "--campaign", campaign, "prepare"], ops=ops)
    return rc, ops, wd


@pytest.fixture(scope="session")
def prepared_texts(tmp_path_factory):
    """{arm: committed registry text} as the candidate's `prepare --campaign f45` commits them (N16: the base itself)."""
    tmp = tmp_path_factory.mktemp("f45-prepared")
    rc, ops, wd = prepare_f45(tmp)
    assert rc == 0, "prepare --campaign f45 did not succeed on the real registry"
    out = {}
    for arm in F45_ARMS:
        br = f"m76-f45-{arm.lower()}"
        out[arm] = ops.committed(br) if arm != "N16" else ops.base_text
        assert out[arm] is not None, f"no commit on branch {br}"
    return out


# ================================================================================================ a world with a CLI
class World:
    def __init__(self, tmp_path, texts):
        self.ops = F45Ops(tmp_path)
        self.wd, self.repo = self.ops.wd, self.ops.repo
        self.tmp = tmp_path
        self.texts = texts
        self.cfg = self.config("run")
        self.ops.add_all(self.cfg, texts)

    def argv(self, cmd, *extra, campaign="f45", top=()):
        base = ["--workdir", str(self.wd), "--repo", str(self.repo), "--base", BASE]
        if campaign is not None:
            base += ["--campaign", campaign]
        return [*base, *top, cmd, *map(str, extra)]

    def config(self, cmd="run", *extra, campaign="f45", top=()):
        return K.config_from_args(K.parse_args(self.argv(cmd, *extra, campaign=campaign, top=top)), self.ops)

    def main(self, cmd, *extra, campaign="f45", top=()):
        return K.main(self.argv(cmd, *extra, campaign=campaign, top=top), ops=self.ops)

    def leg(self, arm, block=1, attempt=1):
        return f"f45-{arm.lower()}-b{block}.a{attempt}"

    def run_leg(self, arm, block=1, attempt=1):
        name = self.leg(arm, block, attempt)
        return name, K.run_leg(name, arm, self.ops, self.cfg)

    # f45 on-disk roots (spec table): scratch `$STACK_WORKDIR/m76/p475`, results `benchmark/results/m76/matrix`
    @property
    def scratch(self):
        return self.wd / "m76" / "p475"

    @property
    def results(self):
        return self.repo / "benchmark" / "results" / "m76" / "matrix"

    def matrix_text(self, partial=None):
        canon = self.results / f"MATRIX.{F45_PICK}.md"
        part = self.results / f"MATRIX.{F45_PICK}.PARTIAL.md"
        if partial is None:
            partial = not canon.exists()
        return (part if partial else canon).read_text()


@pytest.fixture
def world(tmp_path, prepared_texts):
    return World(tmp_path, prepared_texts)


def find_dicts(obj, keys):
    """Every nested dict of `obj` that holds all of `keys` (name-agnostic lookup of a recorded block)."""
    found = []
    if isinstance(obj, dict):
        if all(k in obj for k in keys):
            found.append(obj)
        for v in obj.values():
            found += find_dicts(v, keys)
    elif isinstance(obj, list):
        for v in obj:
            found += find_dicts(v, keys)
    return found


def cli(argv, ops):
    """`main(argv, ops)` -> its exit code; an argparse refusal (SystemExit) as its code."""
    try:
        return K.main(argv, ops=ops)
    except SystemExit as exc:
        return exc.code


def resign(dossier):
    """Recompute the dossier's SCRUB_MANIFEST shas after a deliberate edit (only semantic validation may then refuse it)."""
    man_path = dossier / "SCRUB_MANIFEST.json"
    man = json.loads(man_path.read_text())
    for name in list(man["files"]):
        p = dossier / name
        if p.exists():
            man["files"][name]["published_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    man_path.write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")


def deep(obj):
    return copy.deepcopy(obj)


# ------------------------------------------------------------------------------------------------ self-check of the fake box
def test_the_real_entry_is_the_one_the_specification_edits():
    """(b) The committed entry carries what the f45 edits touch: kv_bits 0 with a trailing comment, no tq4_attention, the MTP lines."""
    text = real_text()
    e = entry_of(text)
    assert e["kv_bits"] == 0 and "tq4_attention" not in e
    assert e["draft_kind"] == "mtp" and e["draft_model"] and e["mtp_verify_scan"] == "joint_v1"
    lines, start, end = entry_lines(text)
    assert any(re.match(r"^    kv_bits: 0\s+#", ln) for ln in lines[start:end])
