"""The M76 B3 registry fixtures are pinned, byte-for-byte copies of the arms' committed `main_models.yaml` (as `p426_off/`, P518 /
C246): sha256 in `SHA256SUMS`, and equal to the source revision whenever it is present in the repository (the arm branches are local
to the box that made them; N16's base is on `main`)."""

import hashlib
import subprocess

from bench import paths

FIX = paths.repo_root() / "benchmark" / "bench" / "tests" / "fixtures" / "m76_b3_fe"
SOURCES = {"n16": "89205085", "x": "ec114753", "v": "0795beb1", "xo": "b9e6b91e"}


def test_the_fixtures_match_their_pinned_sha256():
    pins = dict(reversed(line.split()) for line in (FIX / "SHA256SUMS").read_text().splitlines())
    assert set(pins) == {f"{a}_main_models.yaml" for a in SOURCES}
    for name, sha in pins.items():
        assert hashlib.sha256((FIX / name).read_bytes()).hexdigest() == sha, name


def test_the_fixtures_equal_their_source_revisions_when_present():
    root = paths.repo_root()
    for arm, rev in SOURCES.items():
        r = subprocess.run(["git", "-C", str(root), "show", f"{rev}:main_models.yaml"], capture_output=True)
        if r.returncode:  # the revision is not in this clone (a local arm branch): the sha pin above still holds
            continue
        assert r.stdout == (FIX / f"{arm}_main_models.yaml").read_bytes(), arm
