"""M76 B3: P426 lever `kv` — registry delta, worker argv, predictor, build label `s3`, names / paths (spec v1.1 §Interfaces).

Real registry texts of the three M76 arms (fixtures/m76_b3_fe: N16 = `89205085`, X / V / XO = `origin/m76-f45-{x,v,xo}`) and the
real worker argv spelling of the F45 campaign. Class of each test is in the comment above it:
(a) reproduces a failure the specification fixes, (b) preserves an invariant, (c) exercises new behaviour.

Surface assumed (the spec names `lever`, not the signatures): an optional ``lever="mtp"|"kv"`` keyword (default ``"mtp"``) on
`p426_leg.registry_delta_problems`, `p426_leg.model_argv_problems`, `p426_plan.leg_name`, `p426_plan.plan_leg`,
`p426_plan.frozen_path`, `p426_harvest.wave1_dir`; `p426_plan.EXPECTED_BUILDS["s3"]`.
"""
from __future__ import annotations

import re

import pytest

from bench import p426_harvest, p426_leg, p426_plan
from bench.tests import test_m76_b3_fe_surface as G

ENTRY = G.ENTRY
ARMS = ("n16", "x", "v")
PAIRS = [("n16", "x"), ("x", "v"), ("n16", "v")]


def delta(a, b, **kw):
    return p426_leg.registry_delta_problems(G.text(a), G.text(b), ENTRY, lever="kv", **kw)


def mutate(text, old, new, count=1):
    assert text.count(old) >= 1, old
    return text.replace(old, new, count)


# ------------------------------------------------------------------------------------------------ registry delta
# (c) the kv delta of every stage-3 / stage-4 pair is accepted, in either argument order
@pytest.mark.parametrize("a,b", PAIRS)
def test_kv_delta_of_each_pair_is_accepted(a, b):
    assert delta(a, b) == []
    assert delta(b, a) == []


# (c) both arms carry the MTP keys, equal (the precondition the kv delta states)
@pytest.mark.parametrize("arm", ARMS)
def test_both_arms_are_predictor_mtp_in_the_real_texts(arm):
    entry = p426_leg._models(G.text(arm))[0][ENTRY]
    assert entry["draft_kind"] == "mtp"
    assert entry["draft_model"] == G.DRAFTER
    assert entry["mtp_verify_scan"] == "joint_v1"


# (c) an MTP key that differs between the arms is refused (XO = X with the three MTP lines commented out)
@pytest.mark.parametrize("a,b", [("x", "xo"), ("xo", "x"), ("n16", "xo")])
def test_kv_delta_refuses_a_differing_mtp_key(a, b):
    assert delta(a, b)


# (c) each MTP key changed alone is refused
@pytest.mark.parametrize("old,new", [
    ("mtp_verify_scan: joint_v1", "mtp_verify_scan: per_query"),
    ("draft_kind: mtp", "draft_kind: none"),
    (f"draft_model: {G.DRAFTER}", "draft_model: someone/else-drafter"),
])
def test_kv_delta_refuses_each_mtp_key_changed(old, new):
    bad = mutate(G.text("x"), old, new)
    assert p426_leg.registry_delta_problems(bad, G.text("n16"), ENTRY, lever="kv")


# (c) a non-KV key that differs is refused (several kinds: a number, a sampling default, the context size, a second model)
@pytest.mark.parametrize("old,new", [
    ("prefill_step_size: 512", "prefill_step_size: 1024"),
    ("max_kv_cache_size: 262144", "max_kv_cache_size: 131072"),
    ("temperature: 0.5", "temperature: 0.6"),
    ("kv_quant_scheme: turboquant", "kv_quant_scheme: uniform"),
])
def test_kv_delta_refuses_a_differing_non_kv_key(old, new):
    x = G.text("x")
    if old not in x:
        pytest.skip(f"{old!r} is not spelt so in the real X registry")
    assert p426_leg.registry_delta_problems(mutate(x, old, new), G.text("n16"), ENTRY, lever="kv")


# (c) a key added outside {kv_bits, tq4_attention} is refused even when the KV delta is right
def test_kv_delta_refuses_an_added_extra_key():
    x = G.text("x")
    bad = mutate(x, "    tq4_attention: m72_exact\n", "    tq4_attention: m72_exact\n    surprise_key: 1\n")
    assert p426_leg.registry_delta_problems(bad, G.text("n16"), ENTRY, lever="kv")


# (c) another model's entry that differs is refused
def test_kv_delta_refuses_a_differing_other_model():
    n16 = G.text("n16")
    names = re.findall(r"^  - name: (.+)$", n16, flags=re.M)
    other = next(n for n in names if n != ENTRY)
    idx = n16.index(f"- name: {other}")
    nxt = n16.index("\n  - name:", idx) if "\n  - name:" in n16[idx:] else len(n16)
    block = n16[idx:nxt]
    m = re.search(r"^    (max_kv_cache_size|kv_bits): (\d+)", block, flags=re.M)
    if not m:
        pytest.skip("no numeric key in the other model's entry")
    bad_block = block.replace(m.group(0), m.group(0) + "7", 1)
    bad = n16[:idx] + bad_block + n16[nxt:]
    assert p426_leg.registry_delta_problems(G.text("x"), bad, ENTRY, lever="kv")


# (c) a text that is not YAML / has a duplicate key is refused (strict parse kept under kv)
def test_kv_delta_refuses_a_duplicate_key_and_non_yaml():
    x = G.text("x")
    dup = mutate(x, "    kv_bits: 4\n", "    kv_bits: 4\n    kv_bits: 4\n")
    assert p426_leg.registry_delta_problems(dup, G.text("n16"), ENTRY, lever="kv")
    assert p426_leg.registry_delta_problems("{", G.text("n16"), ENTRY, lever="kv")


# (c) only comment lines may be removed / added besides the KV lines
def test_kv_delta_refuses_a_removed_non_comment_line_that_is_not_kv():
    x = G.text("x")
    bad = mutate(x, "    attention_policy: fused_v1\n", "")
    if "attention_policy: fused_v1" not in x:
        pytest.skip("attention_policy not in the registry")
    assert p426_leg.registry_delta_problems(bad, G.text("n16"), ENTRY, lever="kv")


# (b) the default lever is mtp: a kv pair is NOT an mtp pair (the MTP rule still refuses it, byte for byte today's behaviour)
def test_default_lever_still_refuses_a_kv_pair():
    assert p426_leg.registry_delta_problems(G.text("x"), G.text("n16"), ENTRY)


# (c) the explicit `mtp` lever is the default
def test_explicit_mtp_lever_refuses_a_kv_pair_identically():
    assert p426_leg.registry_delta_problems(G.text("x"), G.text("n16"), ENTRY, lever="mtp") == \
        p426_leg.registry_delta_problems(G.text("x"), G.text("n16"), ENTRY)


# (b) an unknown lever is refused, not silently treated as mtp or kv
def test_unknown_lever_is_refused():
    with pytest.raises((ValueError, KeyError, SystemExit)):
        p426_leg.registry_delta_problems(G.text("x"), G.text("n16"), ENTRY, lever="bogus")


# ------------------------------------------------------------------------------------------------ worker argv
def argv_problems(arm, registry_arm, **kw):
    return p426_leg.model_argv_problems(" ".join(G.worker_argv(arm.upper())), G.text(registry_arm), ENTRY, lever="kv", **kw)


# (c) each arm's real argv matches its own registry text
@pytest.mark.parametrize("arm", ARMS)
def test_kv_argv_of_each_arm_matches_its_registry(arm):
    assert argv_problems(arm, arm) == []


# (c) the argv of another arm is refused against this registry (kv flag present / absent / other mode)
@pytest.mark.parametrize("arm,reg", [("n16", "x"), ("x", "n16"), ("x", "v"), ("v", "x"), ("n16", "v"), ("v", "n16")])
def test_kv_argv_of_another_arm_is_refused(arm, reg):
    assert argv_problems(arm, reg)


# (c) a stray flag value: `--kv-bits 8`, `--tq4-attention` on N16, a missing `--tq4-attention` on X
def test_kv_argv_refuses_wrong_kv_flags():
    x = G.worker_argv("X")
    cases = {
        "kv-bits 8": [("8" if a == "4" and x[i - 1] == "--kv-bits" else a) for i, a in enumerate(x)],
        "no mode": [a for i, a in enumerate(x) if a != "--tq4-attention" and x[i - 1] != "--tq4-attention"],
        "n16 + mode": G.worker_argv("N16") + ["--tq4-attention", "m72_exact"],
        "n16 + kv-bits": G.worker_argv("N16") + ["--kv-bits", "4"],
    }
    regs = {"kv-bits 8": "x", "no mode": "x", "n16 + mode": "n16", "n16 + kv-bits": "n16"}
    for label, argv in cases.items():
        assert p426_leg.model_argv_problems(" ".join(argv), G.text(regs[label]), ENTRY, lever="kv"), label


# (c) under kv an arm without MTP flags is refused although its registry is KV-consistent (both arms are MTP ON)
def test_kv_argv_refuses_a_worker_without_the_mtp_flags():
    assert p426_leg.model_argv_problems(" ".join(G.worker_argv("XO")), G.text("x"), ENTRY, lever="kv")


# (b) the default lever's argv check is today's: it does not look at the KV flags
def test_default_lever_argv_check_ignores_kv_flags():
    assert p426_leg.model_argv_problems(" ".join(G.worker_argv("X")), G.text("x"), ENTRY) == []


# (c) the explicit `mtp` lever is the default
def test_explicit_mtp_lever_argv_check_equals_the_default():
    assert p426_leg.model_argv_problems(" ".join(G.worker_argv("X")), G.text("x"), ENTRY, lever="mtp") == []


# ------------------------------------------------------------------------------------------------ build label s3
# (c) EXPECTED_BUILDS["s3"]: the stage-3 base's gitlinks, production ref f9bf743f…, mlx 0.32.4
def test_s3_pins():
    s3 = p426_plan.EXPECTED_BUILDS["s3"]
    assert re.fullmatch(r"[0-9a-f]{40}", s3["mlx_vlm"]) and re.fullmatch(r"[0-9a-f]{40}", s3["mlx_serve"])
    assert s3["production_ref"].startswith("f9bf743f") and re.fullmatch(r"[0-9a-f]{40}", s3["production_ref"])
    assert s3["mlx"] == "0.32.4"
    assert s3["mlx_vlm"] != p426_plan.EXPECTED_BUILDS["s2"]["mlx_vlm"]
    assert s3["mlx_serve"] != p426_plan.EXPECTED_BUILDS["s2"]["mlx_serve"]


# (c) the fork gitlink of s3 is `34a21208…` or a later commit: it is a commit in this checkout's fork history when present
def test_s3_fork_gitlink_is_34a21208_or_later():
    import subprocess

    fork = G.REPO / "src" / "mlx-vlm"
    sha = p426_plan.EXPECTED_BUILDS["s3"]["mlx_vlm"]
    if subprocess.run(["git", "-C", str(fork), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode:
        pytest.skip("the fork object store lacks the s3 commit")
    base = "34a21208"
    if subprocess.run(["git", "-C", str(fork), "cat-file", "-e", f"{base}^{{commit}}"], capture_output=True).returncode:
        pytest.skip("the fork object store lacks 34a21208")
    assert subprocess.run(["git", "-C", str(fork), "merge-base", "--is-ancestor", base, sha]).returncode == 0


# (b) the s and s2 pins are untouched
def test_s2_pins_unchanged_and_s_has_none():
    assert p426_plan.EXPECTED_BUILDS["s2"] == dict(
        mlx_vlm="1c7c8fa166582ac1a1c23ae9063527b2b5215b11", mlx_serve="1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d",
        production_ref="b26fa7c9faf23bc3167db3419504ef0b2b82a8e6", mlx="0.32.4")
    assert "s" not in p426_plan.EXPECTED_BUILDS


# (c) the labels with an expected build are exactly s2 and s3
def test_expected_build_labels_are_s2_and_s3():
    assert set(p426_plan.EXPECTED_BUILDS) == {"s2", "s3"}


# (c) the label grammar admits s3
def test_s3_is_a_valid_label():
    assert p426_plan.check_build("s3") == "s3"
    assert not p426_plan.is_s("s3")


# (c) a frozen record that carries the s2 build is refused under s3 (the expected build is in code), and the converse
def _record(build, expected):
    venv = {pkg: ("0.32.4" if pkg in ("mlx", "mlx-metal") else "1.0") for pkg in p426_plan.VENV_PACKAGES}
    rec = dict(build=build, mlx_vlm=expected["mlx_vlm"], mlx_serve=expected["mlx_serve"],
               production_ref=expected["production_ref"], uv_lock_sha256="a" * 64, bench_lock_sha256="b" * 64)
    for i, arm in enumerate(p426_plan.ARMS):
        rec.update({f"stack_head_{arm}": f"{i + 1:x}" * 40, f"stack_clean_{arm}": True, f"registry_{arm}_sha": "c" * 64})
    rec["venvs"] = {arm: {v: dict(venv) for v in p426_plan.VENVS} for arm in p426_plan.ARMS}
    return rec


def test_record_of_s2_pins_is_refused_under_s3_and_vice_versa():
    s2, s3 = p426_plan.EXPECTED_BUILDS["s2"], p426_plan.EXPECTED_BUILDS["s3"]
    assert p426_plan.record_problems(_record("s2", s2), "s2") == []             # (b) the s2 path is unchanged
    bad = p426_plan.record_problems(_record("s3", s2), "s3")
    assert any("mlx_vlm" in p for p in bad) and any("mlx_serve" in p for p in bad) and any("production_ref" in p for p in bad)
    assert any("mlx_vlm" in p for p in p426_plan.record_problems(_record("s2", s3), "s2"))


# ------------------------------------------------------------------------------------------------ names and paths
# (c) kv arms are named by their KV label in the leg / tune names: `m76-<arm>-b<k>`; never the p426 names
@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("axis", ["math500", "cjudge", "vision", "reasoning", "longctx"])
def test_kv_leg_names_carry_the_m76_tune(axis, arm):
    tag = "lc-" if axis == "longctx" else ""        # AMENDED (delivery 4, erratum v1.2 item 4): A5's tune is m76-<arm>-lc-b<k>
    assert p426_plan.leg_name(axis, arm, 1, "s3", lever="kv") == f"{axis}-m76-{arm}-{tag}b1"
    assert p426_plan.leg_name(axis, arm, 2, "s3", lever="kv") == f"{axis}-m76-{arm}-{tag}b2"
    assert p426_plan.leg_name(axis, arm, "smoke", "s3", lever="kv") == f"{axis}-m76-{arm}-{tag}smoke"


# (b) the default lever's names are today's
def test_mtp_leg_names_unchanged():
    assert p426_plan.leg_name("math500", "on", 1) == "math500-p426-on-b1"
    assert p426_plan.leg_name("math500", "off", 2, "s2") == "math500-p426s2-off-b2"
    assert p426_plan.leg_name("m1", "on", "smoke", "s2") == "m1-p426s2-on-smoke"


# (c) the explicit `mtp` lever names the same legs
def test_explicit_mtp_lever_leg_names_equal_the_default():
    assert p426_plan.leg_name("m1", "on", "smoke", "s2", lever="mtp") == "m1-p426s2-on-smoke"


# (c) kv names never contain p426 (not even through the build label)
def test_kv_names_never_use_the_p426_names():
    for arm in ARMS:
        assert "p426" not in p426_plan.leg_name("math500", arm, 1, "s3", lever="kv")


# (c) scratch lives under $STACK_WORKDIR/m76/p426/
def test_kv_frozen_record_and_scratch_are_under_m76(tmp_path):
    path = p426_plan.frozen_path(tmp_path, "s3", lever="kv")
    assert tmp_path / "m76" / "p426" in path.parents
    assert "p426s2" not in str(path)


# (b) the mtp frozen path is today's
def test_mtp_frozen_path_unchanged(tmp_path):
    assert p426_plan.frozen_path(tmp_path, "s2") == tmp_path / "p426" / "frozen.s2.json"
    assert p426_plan.frozen_path(tmp_path, "s") == tmp_path / "p426" / "frozen.json"


# (c) harvested dossiers live under benchmark/results/m76/wave1
def test_kv_dossiers_are_under_results_m76():
    d = p426_harvest.wave1_dir("s3", lever="kv")
    assert str(d).replace("\\", "/").endswith("results/m76/wave1")


# (b) the mtp dossier dirs are today's
def test_mtp_dossier_dirs_unchanged():
    assert str(p426_harvest.wave1_dir("s2")).endswith("results/p426/wave1.s2")
    assert str(p426_harvest.wave1_dir("s")).endswith("results/p426/wave1")


# (c) plan_leg under kv: tune m76-<arm>-b<k>, results under results/m76, scratch under m76/p426, entry unchanged
@pytest.mark.parametrize("arm", ["n16", "x"])
def test_plan_leg_kv_names_and_paths(arm, tmp_path):
    leg = p426_plan.plan_leg(G.REPO, "math500", arm, 1, workdir=str(tmp_path), reviewed_head="a" * 40, production_ref="b" * 40,
                             build="s3", lever="kv")
    assert leg["tune"] == f"m76-{arm}-b1"
    assert leg["entry"] == ENTRY
    argv = leg["driver_argv"]
    assert argv[argv.index("--tune") + 1] == f"m76-{arm}-b1"
    assert argv[argv.index("--sampling-profile") + 1] == "deployed"
    assert "p426" not in " ".join(argv)


# (c) the M1 leg under kv: both arms --predictor on; the out dir is under m76/p426
@pytest.mark.parametrize("arm", ["n16", "x", "v"])
def test_plan_leg_kv_m1_predictor_on_for_every_arm(arm, tmp_path):
    # AMENDED (delivery 6): a TQ4 arm's M1 leg needs its stage-2 record (`--certified-by`, B2 / erratum v1.2); V (stage 4) is refused
    from bench import p426_wave1

    if arm == "v":
        legs = p426_wave1.schedule(axes=("m1",), lever="kv", arms=("x", "v"))
        assert p426_wave1.preflight_kv(("x", "v"), legs, {})                    # the v1.2 refusal, before any leg
        with pytest.raises(ValueError):
            p426_plan.plan_leg(G.REPO, "m1", "v", 1, workdir=str(tmp_path), reviewed_head="a" * 40, production_ref="b" * 40,
                               build="s3", lever="kv")                          # no --certified-by: refused
        return
    cert = None
    if arm == "x":
        cert = tmp_path / "stage2.json"
        cert.write_text("{}")
    leg = p426_plan.plan_leg(G.REPO, "m1", arm, 1, workdir=str(tmp_path), reviewed_head="a" * 40, production_ref="b" * 40,
                             build="s3", lever="kv", certified_by=str(cert) if cert else None)
    argv = leg["driver_argv"]
    if arm == "x":
        assert argv[argv.index("--certified-by") + 1] == str(cert)
    assert argv[argv.index("--predictor") + 1] == "on"
    assert tmp_path / "m76" / "p426" in leg["out_dir"].parents
