"""P426 T3 frozen tests — the local gate on S′ (spec §3 "The local gate on S′", §6, acceptance 5): `bench.local_gate` reads the
upstream ref from `.upstream-sync-ref` at the sha when present, else from `.github/workflows/upstream-parity.yml`; the audit
list is the fork's own `dev/ci.py` `AUDITS` at that sha (S′: nine, incl. `check_upstream_test_copies.py`), derived per sha.
Fixtures of both layouts; the runner is mocked, git runs for real on repositories in `tmp_path` (no network).

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

from bench import local_gate as G
from bench.tests import t3_frozen_support as T


def test_the_old_layout_keeps_the_workflow_ref_and_its_eight_audits(tmp_path):
    """[I] a fork sha in S's layout: PASS, parity ref from the workflow, eight audits (deletions `--strict`)."""
    repo, sha = T.old_layout(tmp_path / "mlx-vlm")
    assert G.current_parity("mlx-vlm", repo, sha) == T.OLD_REF
    doc, runner = T.gate_run(tmp_path, repo, sha)
    assert doc["verdict"] == "PASS" and doc["parity_ref"] == T.OLD_REF, doc["problems"]
    assert runner.audits() == [(n, T.OLD_REF, extra) for n, extra in T.OLD_AUDITS]


def test_the_s2_layout_reads_the_sync_ref(tmp_path):
    """[R] S′ has no parity workflow: today `current_parity` raises (no receipt for `c688e722`, acceptance 5 unattainable)."""
    repo, sha = T.s2_layout(tmp_path / "mlx-vlm")
    assert G.current_parity("mlx-vlm", repo, sha) == T.S2_REF


def test_the_s2_layout_passes_with_the_forks_nine_audits(tmp_path):
    """[R] a PASS receipt for an S′-layout sha: the nine audits of its `dev/ci.py`, in its order, each against its sync ref,
    with the fork's own extra arguments (deletions `--strict`)."""
    repo, sha = T.s2_layout(tmp_path / "mlx-vlm")
    doc, runner = T.gate_run(tmp_path, repo, sha)
    assert doc["verdict"] == "PASS" and doc["parity_ref"] == T.S2_REF, doc["problems"]
    assert runner.audits() == [(n, T.S2_REF, extra) for n, extra in T.S2_AUDITS]


def test_the_sync_ref_wins_over_a_workflow_at_the_same_sha(tmp_path):
    """[N] §3: `.upstream-sync-ref` when present, else the workflow."""
    repo = T.make_fork_repo(tmp_path / "mlx-vlm")
    sha = T.fork_commit(repo, workflow=T.OLD_WORKFLOW, ci=T.ci_py(T.S2_AUDITS), sync_ref=T.sync_ref_file("aaaa1111"))
    assert G.current_parity("mlx-vlm", repo, sha) == "aaaa1111"
    doc, runner = T.gate_run(tmp_path, repo, sha)
    assert doc["parity_ref"] == "aaaa1111" and {ref for _, ref, _ in runner.audits()} == {"aaaa1111"}


def test_audits_and_ref_are_derived_per_sha_not_from_the_live_tree(tmp_path):
    """[N] §3 "derived per sha, not a fixed tuple": one fork whose history crosses both layouts and a later `dev/ci.py` with
    a different list — each sha gates with its own list and ref, whatever the live checkout holds."""
    repo, old = T.old_layout(tmp_path / "mlx-vlm")
    s2 = T.fork_commit(repo, workflow=None, ci=(T.REPO / "src/mlx-vlm/dev/ci.py").read_text(),
                       sync_ref=(T.REPO / "src/mlx-vlm/.upstream-sync-ref").read_text(), msg="sync")
    later_audits = [("check_upstream_parity.py", ()), ("check_upstream_deletions.py", ("--strict", "--verbose")),
                    ("check_new_direction.py", ())]
    later = T.fork_commit(repo, ci=T.ci_py(later_audits), sync_ref=T.sync_ref_file("v0.9.9"), msg="later")
    for sha, ref, audits in ((old, T.OLD_REF, T.OLD_AUDITS), (s2, T.S2_REF, T.S2_AUDITS), (later, "v0.9.9", later_audits)):
        doc, runner = T.gate_run(tmp_path / sha[:8], repo, sha)
        assert doc["verdict"] == "PASS" and doc["parity_ref"] == ref, (sha, doc["problems"])
        assert runner.audits() == [(n, ref, tuple(extra)) for n, extra in audits], sha
