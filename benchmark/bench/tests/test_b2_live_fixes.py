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


# ---- P579 / P580 (C263): the interpreter inventory on real venvs -------------------------------------------------------------
import base64
import hashlib

import pytest


def b64(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def dist(site, name, files, version="1.0"):
    """A non-editable distribution: `files` {rel-to-site: bytes written} and RECORD rows for each (path, digest of the given
    bytes, or the explicit digest when the value is a (bytes-on-disk, bytes-recorded) pair)."""
    info = site / f"{name}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n\n")
    rows = []
    for rel, data in files.items():
        disk, recorded = data if isinstance(data, tuple) else (data, data)
        if disk is not None:
            f = (site / rel).resolve() if rel.startswith("..") else site / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(disk)
        rows.append(f"{rel},{b64(recorded)},{len(recorded)}")
    rows.append(f"{info.name}/RECORD,,")
    (info / "RECORD").write_text("\n".join(rows) + "\n")


def venv_site(root):
    site = root / "v" / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    return site


def ops_for(root):
    return co.ChainOps(root, root, root / "x.yaml", lambda m: None)


def test_a_file_two_distributions_own_passes_on_the_claimant_whose_bytes_it_holds_P579(tmp_path):
    site = venv_site(tmp_path)
    dist(site, "opencv-python", {"cv2/cv2.abi3.so": (None, b"full build"), "cv2/__init__.py": b"x"})
    dist(site, "opencv-python-headless", {"cv2/cv2.abi3.so": b"headless build"})     # installed last: its bytes on disk
    inv = ops_for(tmp_path).interpreter_inventory(1, site_packages=site)
    assert set(inv) == {"path", "inventory_sha256", "editables"}         # spec 16.2's interface unchanged
    (site / "cv2/cv2.abi3.so").write_bytes(b"full build")                # the other claimant's bytes: still valid, a different digest
    assert ops_for(tmp_path).interpreter_inventory(1, site_packages=site)["inventory_sha256"] != inv["inventory_sha256"]


def test_a_shared_file_matching_no_claimant_is_still_systemic_P579(tmp_path):
    site = venv_site(tmp_path)
    dist(site, "opencv-python", {"cv2/cv2.abi3.so": (None, b"full build")})
    dist(site, "opencv-python-headless", {"cv2/cv2.abi3.so": (b"tampered", b"headless build")})
    with pytest.raises(co.ChainAbort, match="cv2.abi3.so differs"):
        ops_for(tmp_path).interpreter_inventory(1, site_packages=site)


def two_worktrees(tmp_path, tweak=b""):
    out = []
    for name in ("off", "on"):
        wt = tmp_path / f"stack-p426-{name}"
        site = venv_site(wt)
        script = b"#!" + str(wt / "v" / "bin" / "python").encode() + b"\nfrom tool import main\nmain()\n" + (tweak if name == "on" else b"")
        dist(site, "tool", {"tool/__init__.py": b"def main(): pass\n", "../../../bin/tool": script})
        out.append(ops_for(wt).interpreter_inventory(1, site_packages=site))
    return out


def test_console_scripts_that_differ_only_by_their_worktree_shebang_inventory_equal_P580(tmp_path):
    off, on = two_worktrees(tmp_path)
    assert off["inventory_sha256"] == on["inventory_sha256"]


def test_any_other_difference_in_a_console_script_still_differs_P580(tmp_path):
    off, on = two_worktrees(tmp_path, tweak=b"# edited\n")
    assert off["inventory_sha256"] != on["inventory_sha256"]
