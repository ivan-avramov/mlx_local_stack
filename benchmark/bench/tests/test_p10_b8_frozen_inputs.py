"""Regression coverage for the test-only M76 S3 registry provider."""
import json
from pathlib import Path
import subprocess

import pytest

from bench import p426_verify as verify


BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
ROWS = BENCH / "results"
FROZEN = ROWS / "m76/wave1/run/frozen.s3.json"
FIXTURE = Path(__file__).parent / "fixtures/m76_b3_fe/x_main_models.yaml"
X = "d4c44a9d0fc8a93a8ef1d9364650595d403edb9e"


def cli_args(tmp_path, repo=REPO):
    return ["all", "--lever", "kv", "--pair", "n16,x", "--results-root", str(ROWS / "m76"),
            "--rows-root", str(ROWS), "--repo", str(repo), "--out", str(tmp_path / "B8.json")]


def resolve(sha, arm):
    return (["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
            f"frozen stack_head_{arm} {sha} does not resolve")


def registry(sha, arm):
    return ["show", f"{sha}:main_models.yaml"], f"git show stack_head_{arm}:main_models.yaml"


@pytest.mark.parametrize("damage", ["bytes", "missing", "stack_head_x", "registry_x_sha"])
def test_damaged_frozen_input_refuses(damage, tmp_path, monkeypatch):
    from bench.tests.m76_b4b2_frozen_cli import main

    monkeypatch.setenv("MLX_BENCH_RESULTS", str(ROWS))
    target = FIXTURE if damage in ("bytes", "missing") else FROZEN
    replacement = tmp_path / target.name
    if damage == "bytes":
        replacement.write_bytes(target.read_bytes() + b"\n")
    elif damage != "missing":
        record = json.loads(target.read_bytes())
        record[damage] = "e" * len(record[damage])
        replacement.write_text(json.dumps(record))

    # Redirect reads without changing the shared checkout, including its frozen records.
    real_open = Path.open

    def open_input(path, *args, **kwargs):
        return real_open(replacement if path == target else path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_input)
    git_bytes = verify.git_bytes
    try:
        status = main(cli_args(tmp_path))
    except (verify.RefusalError, ValueError, OSError):
        pass
    else:
        assert status != 0
    assert verify.git_bytes is git_bytes
    assert not (tmp_path / "B8.json").exists()


def test_exact_registry_reads_and_real_git_delegation(tmp_path, monkeypatch):
    from bench.tests.m76_b4b2_frozen_cli import main

    n16 = json.loads(FROZEN.read_bytes())["stack_head_n16"]
    real_run = subprocess.run
    git_bytes = verify.git_bytes

    def inspect_provider(*unused):
        assert verify.git_bytes(REPO, *resolve(X, "x")).decode().strip() == X
        assert verify.git_bytes(REPO, *registry(X, "x")) == FIXTURE.read_bytes()

        queries = [(REPO, *resolve(n16, "n16")), (REPO, *registry(n16, "n16")),
                   (REPO, *resolve(X, "n16")), (REPO, *registry(X, "n16")),
                   (REPO, ["show", f"{X}:README.md"], registry(X, "x")[1]),
                   (tmp_path, *resolve(X, "x")), (tmp_path, *registry(X, "x"))]
        for top, args, what in queries:
            calls = []

            def observe(cmd, **kwargs):
                calls.append((cmd, kwargs.get("cwd")))
                return real_run(cmd, **kwargs)

            with monkeypatch.context() as scoped:
                scoped.setattr(subprocess, "run", observe)
                try:
                    verify.git_bytes(top, args, what)
                except verify.RefusalError:
                    pass  # The real command may refuse an absent object or worktree.
            assert (["git", *args], top) in calls
        return {}

    monkeypatch.setattr(verify, "verify_all_kv", inspect_provider)
    monkeypatch.setattr(verify, "a8_applies", lambda root: False)
    assert main(cli_args(tmp_path)) == 0
    assert verify.git_bytes is git_bytes


def test_git_provider_restored_on_exception(tmp_path, monkeypatch):
    from bench.tests.m76_b4b2_frozen_cli import main

    class Interrupt(Exception):
        pass

    def interrupt(*unused):
        assert verify.git_bytes(REPO, *registry(X, "x")) == FIXTURE.read_bytes()
        raise Interrupt

    git_bytes = verify.git_bytes
    monkeypatch.setattr(verify, "verify_all_kv", interrupt)
    with pytest.raises(Interrupt):
        main(cli_args(tmp_path))
    assert verify.git_bytes is git_bytes


def test_production_cli_refuses_an_absent_x_commit(tmp_path, monkeypatch, capsys):
    # Expose exactly the real N16 commit, root tree and registry blob. This also
    # tests production on developer checkouts that happen to retain X locally.
    repo = tmp_path / "published"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    n16 = json.loads(FROZEN.read_bytes())["stack_head_n16"]
    for kind, suffix in (("blob", ":main_models.yaml"), ("tree", "^{tree}"), ("commit", "")):
        contents = subprocess.check_output(["git", "cat-file", kind, n16 + suffix], cwd=REPO)
        subprocess.run(["git", "hash-object", "-w", "-t", kind, "--stdin"],
                       input=contents, check=True, capture_output=True, cwd=repo)
    monkeypatch.setenv("MLX_BENCH_RESULTS", str(ROWS))
    assert verify.main(cli_args(tmp_path, repo)) == 2
    assert f"frozen stack_head_x {X} does not resolve" in capsys.readouterr().err
    assert not (tmp_path / "B8.json").exists()
