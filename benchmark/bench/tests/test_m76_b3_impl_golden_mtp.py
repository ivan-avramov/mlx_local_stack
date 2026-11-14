"""M76 B3 acceptance 2: `lever=mtp` (the default) is byte-identical to the P426 machinery before B3.

Golden, written and green on the unchanged code (baseline ce77b5b2): the Wave 1 plans (S and S′), the Wave 1 schedule and leg
argv, the Wave 2 leg argv (from the committed v8 base / amendment), the pair gate and its observed differences on the committed
Wave 2 receipts, the leg wrapper's registry / worker-argv checks on the committed S′ registries and receipts, and the regenerated
`benchmark/results/p426/{B8.json, SIGNALS.md, SIGNALS.json}` from the committed P426 evidence (byte for byte).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench import p426_leg as L
from bench import p426_plan as P
from bench import p426_receipt as pr
from bench import p426_wave1 as W1
from bench import p426_wave2 as W2

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
P426 = BENCH / "results" / "p426"
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
EVIDENCE_REF = "b6ec7819"
WD = Path("/wd-golden")

GOLDEN = {
    "plans": "84fbee0c9e66f95bcae41fb3b6558e61b98e5aa7cd123abbbda9b0c23763acbf",
    "wave1_argv": "f25d6db786250fce027dff0e0ace3818a96dd5bc132e70cad08ed12546616f36",
    "wave2_argv": "06b7ce6c7b881c139758bf5ff03b363ea7fe08e58ade60cc976709cbeebac77b",
    "pair_gate": "a27998907ff30568f6af526c8e9ac37c3d7a49ee3c534aba74bc501a590ccc97",
    "leg_checks": "51b5be7800f20d63109048623a3b6ba5154a7a1404756474650f0530ed1e8c05",
}


def test_mtp_pinned_signatures_unchanged():
    """Spec 16.7 / X8 signatures the B2 suites pin (they also need the fork's pins.json, absent from a copy without src/)."""
    import inspect

    from bench import p426_harvest as H
    assert list(inspect.signature(pr.pair_problems).parameters) == ["first", "second"]
    assert list(inspect.signature(pr.observed_differences).parameters) == ["first", "second"]
    assert list(inspect.signature(pr.write_dossier).parameters) == ["path", "pair", "off", "on", "differences", "verdict"]
    assert list(inspect.signature(H.publish_dossier).parameters) == ["path", "main_root", "evidence_stage", "scrub", "namespace"]
    assert list(inspect.signature(H.publish_run_files).parameters) == ["paths", "main_root", "scrub", "namespace"]
    assert list(inspect.signature(H.harvest).parameters) == ["name", "plan", "main_root", "receipts", "stdout", "log_slice",
                                                             "scrub", "build"]


def test_mtp_golden_is_meaningful():
    """The hashed facts are the passing ones (a golden of refusals would pin nothing useful)."""
    g, lc = pair_gate(), leg_checks()
    assert all(v["problems"] == [] and v["arms"] == ["off", "on"] and v["same"] for v in g.values())
    assert lc["delta"] == [] and lc["delta_strict"] and lc["reverse"]
    assert lc["math500-p426s2-on-b1"]["argv"] == [] and lc["math500-p426s2-off-b1"]["argv"] == []
    assert lc["math500-p426s2-on-b1"]["cross"] and lc["math500-p426s2-off-b1"]["cross"]


def _canon(obj):
    def norm(x):
        if isinstance(x, dict):
            return {str(k): norm(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [norm(v) for v in x]
        if isinstance(x, Path):
            x = str(x)
        if isinstance(x, str):
            return x.replace(str(REPO), "<REPO>").replace(str(WD), "<WD>")
        return x
    return json.dumps(norm(obj), sort_keys=True, default=str)


def _sha(obj):
    return hashlib.sha256(_canon(obj).encode()).hexdigest()


def _git_show(ref, path):
    return subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{path}"], capture_output=True, check=True).stdout


def plans():
    out = {}
    for build in ("s", "s2"):
        for axis in ("math500", "cjudge", "vision", "reasoning", "m1"):
            for arm in ("off", "on"):
                for sel in ("smoke", 1, 2):
                    leg = P.plan_leg(REPO, axis, arm, None if sel == "smoke" else sel, smoke=sel == "smoke", workdir=WD,
                                     reviewed_head="r" * 40, production_ref="p" * 40, build=build)
                    out[f"{build}/{axis}/{arm}/{sel}"] = leg
    return out


def wave1_argv():
    out = {"schedule": W1.schedule()}
    for build in ("s", "s2"):
        for leg in W1.schedule():
            out[f"{build}/{W1.leg_name(*leg, build=build)}"] = W1.leg_argv(
                WD / "wt", WD, WD / "overlay.yaml", WD / "receipts", *leg, build=build, stack_root_off=WD / "wt-off")
    return out


def wave2_argv():
    run = P426 / "wave2" / "run"
    out = {}
    for spec in (*W2.RUN_LEGS, *W2.MAKEUP_LEGS):
        record = run / ("v8_base.json" if spec["record"] == "v8" else "amendment.json")
        out[spec["name"]] = W2.leg_argv(spec, 1, worktrees={"off": WD / "off", "on": WD / "on"}, record_path=record,
                                        out_base=WD / "out", pair_receipt=WD / "first.json" if spec["role"] == "second" else None,
                                        occurrences=WD / "occ.jsonl" if spec["kind"] == "makeup" else None)
    out["predictor"] = W2.PREDICTOR
    return out


def pair_gate():
    out = {}
    for session in ("pilot", "s1", "s2", "reload"):
        off = json.loads((P426 / "wave2" / f"tg1-p426-off-{session}.a1" / "receipt.json").read_text())
        on = json.loads((P426 / "wave2" / f"tg1-p426-on-{session}.a1" / "receipt.json").read_text())
        out[session] = dict(problems=pr.pair_problems(off, on), reverse=pr.pair_problems(on, off),
                            differences=pr.observed_differences(off, on), arms=[pr.arm_of(off), pr.arm_of(on)],
                            same=pr.pair_problems(on, on))
    return out


def leg_checks():
    frozen = json.loads((P426 / "wave1.s2" / "run" / "frozen.s2.json").read_text())
    off_text = _git_show(frozen["stack_head_off"], "main_models.yaml").decode()
    on_text = _git_show(frozen["stack_head_on"], "main_models.yaml").decode()
    out = dict(delta=L.registry_delta_problems(on_text, off_text, ENTRY, allow_added_comments=True),
               delta_strict=L.registry_delta_problems(on_text, off_text, ENTRY),
               reverse=L.registry_delta_problems(off_text, on_text, ENTRY, allow_added_comments=True))
    for leg in ("math500-p426s2-off-b1", "math500-p426s2-on-b1", "vision-p426s2-on-b2", "reasoning-p426s2-off-b2"):
        receipt = json.loads((P426 / "wave1.s2" / leg / f"{leg}.receipt.json").read_text())
        cmd = receipt["worker"]["cmdline"].split(" ", 1)[1]
        text = on_text if "-on-" in leg else off_text
        out[leg] = dict(argv=L.model_argv_problems(cmd, text, ENTRY), cross=L.model_argv_problems(cmd, on_text if text is off_text else off_text, ENTRY),
                        log=L.log_problems([], "on", 0), eng=L.engagement_problems("on", [dict(id="a", draft=None)]))
    return out


COMPONENTS = dict(plans=plans, wave1_argv=wave1_argv, wave2_argv=wave2_argv, pair_gate=pair_gate, leg_checks=leg_checks)


@pytest.mark.parametrize("name", sorted(COMPONENTS))
def test_mtp_golden_component(name):
    assert _sha(COMPONENTS[name]()) == GOLDEN[name], f"{name}: {_sha(COMPONENTS[name]())}"


def _run(module, args):
    env = {"PYTHONPATH": str(BENCH), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "MLX_BENCH_RESULTS": str(BENCH / "results"), "HOME": str(BENCH / "results"), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull}
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=BENCH, capture_output=True, text=True,
                          timeout=3000, env=env)


def test_mtp_golden_committed_b8_and_signals_regenerate(tmp_path):
    try:
        subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{EVIDENCE_REF}^{{commit}}"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        pytest.skip(f"evidence commit {EVIDENCE_REF} is not in this repository's objects")
    rows = BENCH / "results"
    b8 = tmp_path / "B8.json"
    r = _run("bench.p426_verify", ["all", "--results-root", P426, "--rows-root", rows, "--repo", REPO, "--out", b8])
    assert r.returncode == 0, r.stderr[-1500:]
    assert b8.read_bytes() == (P426 / "B8.json").read_bytes()
    md, js = tmp_path / "SIGNALS.md", tmp_path / "SIGNALS.json"
    r = _run("bench.p426_signals", ["all", "--results-root", P426, "--rows-root", rows, "--b8", P426 / "B8.json", "--out-md", md,
                                    "--out-json", js, "--panel", P426 / "panel", "--evidence-ref", EVIDENCE_REF])
    assert r.returncode == 0, r.stderr[-1500:]
    assert md.read_bytes() == (P426 / "SIGNALS.md").read_bytes()
    assert js.read_bytes() == (P426 / "SIGNALS.json").read_bytes()
