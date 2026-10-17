"""Stage the corpus manifests the tg2 image needs into ./ctx (build-time input; not committed).

Derives the three Java dependency closures (by build.gradle content), the one JS bundle (all package.json dependency
signatures must match) and every Rust Cargo.toml (plus the sources cargo needs to parse them)."""
import hashlib
import json
import shutil
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench import tg2_materialize as mat  # noqa: E402

LOCKS = Path(__file__).resolve().parent / "locks"


def context_digest(ctx):
    """sha256 over the sorted (relative path, content) pairs of a staged context tree."""
    h = hashlib.sha256()
    for path in sorted(p for p in Path(ctx).rglob("*") if p.is_file()):
        h.update(path.relative_to(ctx).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def main(corpus, ctx):
    corpus, ctx = Path(corpus), Path(ctx)
    shutil.rmtree(ctx, ignore_errors=True)
    # Java: group by build.gradle content; a closure's variant name comes from its dependency set.
    java = corpus / "java/exercises/practice"
    groups = {}
    for gradle in sorted(java.glob("*/build.gradle")):
        groups.setdefault(hashlib.sha256(gradle.read_bytes()).hexdigest(), []).append(gradle)
    if len(groups) != 3:
        sys.exit("expected 3 Java build.gradle closures, found %d" % len(groups))
    names = {"io.reactivex": "hangman", "org.json": "rest-api"}
    for digest, members in groups.items():
        text = members[0].read_text()
        variant = next((v for k, v in names.items() if k in text), "common")
        dest = ctx / "java" / variant
        shutil.copytree(members[0].parent / "gradle", dest / "gradle")
        shutil.copy(members[0].parent / "gradlew", dest / "gradlew")
        shutil.copy(members[0], dest / "build.gradle")
    if sorted(p.name for p in (ctx / "java").iterdir()) != ["common", "hangman", "rest-api"]:
        sys.exit("Java closure naming ambiguous")
    # JS: every package.json must carry identical dependency signatures.
    sigs = {}
    for pkg in sorted((corpus / "javascript/exercises/practice").glob("*/package.json")):
        doc = json.loads(pkg.read_text())
        sig = json.dumps({k: doc.get(k) for k in
                          ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "jest")},
                         sort_keys=True)
        sigs.setdefault(sig, []).append(pkg)
    if len(sigs) != 1:
        sys.exit("package.json dependency signatures differ: %d groups" % len(sigs))
    members = next(iter(sigs.values()))
    doc = json.loads(members[0].read_text())
    bundle = {"name": "tg2-js-bundle", "version": "1.0.0", "private": True,
              "devDependencies": doc["devDependencies"], "dependencies": doc.get("dependencies", {})}
    (ctx / "js").mkdir(parents=True)
    committed = json.loads((LOCKS / "js/package.json").read_text())
    if committed != bundle:
        sys.exit("corpus package.json devDependencies differ from the committed locks/js/package.json")
    shutil.copy(LOCKS / "js/package.json", ctx / "js/package.json")
    shutil.copy(LOCKS / "js/package-lock.json", ctx / "js/package-lock.json")
    # Rust: every manifest, with the full exercise dir minus docs (path dependencies and [[bin]] targets must exist).
    rust = corpus / "rust/exercises/practice"
    for ex in sorted(p for p in rust.iterdir() if (p / "Cargo.toml").is_file()):
        # the prepared manifest: the stub's dependencies united with `.meta/Cargo-example.toml`'s (P366)
        mat.prepare_tree(corpus, "rust", ex.name, ctx / "rust" / ex.name)
    for manifest in sorted((ctx / "rust").rglob("Cargo.toml")):
        committed = LOCKS / "rust" / manifest.parent.relative_to(ctx / "rust") / "Cargo.lock"
        if not committed.is_file():
            sys.exit("no committed Cargo.lock for %s" % manifest.relative_to(ctx))
        shutil.copy(committed, manifest.parent / "Cargo.lock")
    print("staged: %d java closures, %d package.json (1 signature), %d rust manifests" % (
        len(groups), len(members), len(list((ctx / "rust").rglob("Cargo.toml")))))


if __name__ == "__main__":
    main(*sys.argv[1:3])
