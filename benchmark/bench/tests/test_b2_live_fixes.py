"""B2 bugs found by the first live Wave-2 launch (session 13): P578 `ChainOps.worktree_state` read the submodule's HEAD."""
import subprocess

from bench import chain_ops as co


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout.strip()


def commit_repo(path, name):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    (path / f"{name}.txt").write_text(name)
    git(path, "add", ".")
    git(path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", name)
    return git(path, "rev-parse", "HEAD")


def test_worktree_state_reads_the_worktree_not_its_last_listed_submodule_P578(tmp_path, monkeypatch):
    wt = tmp_path / "wt"
    commit_repo(wt, "stack")
    vlm = commit_repo(wt / "src" / "mlx-vlm", "vlm")            # a nested repository at another commit, as a checked-out submodule
    serve = commit_repo(wt / "src" / "mlx-serve", "serve")
    for sha, rel in ((vlm, "src/mlx-vlm"), (serve, "src/mlx-serve")):
        git(wt, "update-index", "--add", "--cacheinfo", f"160000,{sha},{rel}")
    git(wt, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "gitlinks")
    head = git(wt, "rev-parse", "HEAD")
    (wt / "untracked-in-the-worktree.txt").write_text("dirty")
    monkeypatch.chdir(wt)                                         # the chain runs from its worktree
    ops = co.ChainOps(wt, tmp_path, tmp_path / "x.yaml", lambda m: None)
    st = ops.worktree_state(wt)
    assert st["head"] == head                                     # not the submodule's commit
    assert st["gitlinks"] == {"src/mlx-vlm": vlm, "src/mlx-serve": serve}
    assert st["clean"] is False                                   # the worktree's own status, not the submodule's
