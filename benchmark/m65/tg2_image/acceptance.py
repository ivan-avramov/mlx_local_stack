"""tg2 image acceptance: reference solutions graded with `--network none --pull=never` (no network available at all).

Covers every dependency family the image bakes: Rust crates (time, rand, anyhow + nested macros manifest), the three
Java Gradle closures (common JUnit/AssertJ, hangman RxJava, rest-api org.json; each from an empty writable Gradle
home, with the read-only dependency cache supplying artifacts), the JS bundle and C++ (Catch2 + Boost). Fails when any
item needs network, does not collect all-pass, or the no-network control does not hold."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from bench import tg2_grade as tg  # noqa: E402
from bench.tests import tg2_trees  # noqa: E402

ITEMS = [("rust", "gigasecond"), ("rust", "simple-cipher"), ("rust", "grep:stub"), ("rust", "macros"),
         ("java", "affine-cipher"), ("java", "hangman"), ("java", "rest-api"),
         ("javascript", "affine-cipher"), ("cpp", "gigasecond")]
NETWORK_TEXT = ("Could not resolve", "Could not GET", "UnknownHost", "Temporary failure in name resolution",
                "attempting to make an HTTP request", "ENOTFOUND", "Failed to download")


def container(image, script):
    cmd = ["docker", "run", "--rm", "--pull=never", "--network", "none", image, "bash", "-c", script]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def main(corpus):
    base = os.environ.get("STACK_WORKDIR")
    if not base:
        sys.exit("STACK_WORKDIR is required: trees must live outside $TMPDIR (P361)")
    root = Path(base) / "m65/test-tmp"
    root.mkdir(parents=True, exist_ok=True)
    image = tg.pinned_image_id()
    guard = tg.LocalDocker("mlxbench-tg2-accept")
    failures = []
    control = container(image, "getent hosts services.gradle.org || exit 0; echo RESOLVED")
    if "RESOLVED" in control.stdout:
        failures.append("no-network control failed: DNS resolved")
    home = container(image, "ls -A /root/.gradle")
    if home.stdout.split() != ["wrapper"]:
        failures.append("writable Gradle home must hold only wrapper/dists, found: " + home.stdout.strip())
    with tempfile.TemporaryDirectory(prefix="tg2-accept-", dir=root) as tmp:
        tmp = Path(tmp)
        for lang, slug in ITEMS:
            # `grep:stub`: the corpus grep reference needs `thiserror`, which its Cargo.toml does not declare, so it
            # cannot compile (a freeze exclusion); the untouched stub still proves the anyhow crate resolves offline.
            stub_only = slug.endswith(":stub")
            slug = slug.split(":")[0]
            private = tmp / "private"
            work = tg2_trees.stub_tree(corpus, lang, slug, tmp / lang / slug)
            if lang == "rust":
                tg.generate_cargo_locks(work, slug, private, guard=guard)
            prepared = tg2_trees.sg.manifest(work)
            if not stub_only:
                # fresh directory: overwriting a file a container already mounted can show the container a stale
                # (old-size) view on virtiofs, so the reference tree is never an in-place edit of the locked stub
                ref = tmp / (lang + "-ref") / slug
                shutil.copytree(work, ref)
                work = tg2_trees.apply_reference(corpus, lang, slug, ref)
            keep = tmp / "keep" / lang / slug
            result = tg.grade_item(lang, work, slug, private, prepared=prepared,
                                   solutions=tg2_trees.solutions(corpus, lang, slug), guard=guard, timeout=900,
                                   keep=keep, seq=0, boundary=0)
            raw = "".join(p.read_text(errors="replace") for p in (keep / "seq-0000").glob("*.std*"))
            for needle in NETWORK_TEXT:
                if needle in raw:
                    failures.append("%s/%s: network symptom in output: %s" % (lang, slug, needle))
            ok = result.outcome == "parsed" and result.collected and (stub_only or result.passing == result.collected)
            status = "PASS" if ok else "FAIL"
            slug = slug + (" (stub)" if stub_only else "")
            print("%s %-10s %-20s leaves=%d passing=%d outcome=%s" % (status, lang, slug, len(result.collected),
                                                                      len(result.passing), result.outcome))
            if not ok:
                failures.append("%s/%s: %s" % (lang, slug, result.outcome))
    leftovers = guard.leftover()
    if leftovers:
        failures.append("leftover containers: %s" % leftovers)
    if failures:
        print("ACCEPTANCE FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("ACCEPTANCE OK (image %s)" % image)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
