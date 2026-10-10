"""C92: publish the prepared C89 depth-evidence card updates to two owned HF repos.

Same guard pattern as the M44/C88 publisher: pin the parent commit to the audited
remote HEAD, add ONLY README.md + evaluation/C89-evidence-2026-09-14.json, verify the
published file set is the old set plus those two, verify every other file's signature
is byte-identical, read the two files back ANONYMOUSLY and compare bytes, then write a
receipt. Dry-run by default; --apply performs the commits.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path.home() / "ws" / "mlx_local_stack"
PREPARED = REPO_ROOT / "docs" / "huggingface-c89-prepared-2026-09-14.json"
EVIDENCE_NAME = "evaluation/C89-evidence-2026-09-14.json"
# Parents = the C88 publication revisions (docs/huggingface-c88-update-2026-09-14.json).
EXPECTED_PARENTS = {
    "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed": "f2b38a250db2b2f3d6a453bf62fef8a68db46b83",
    "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter": "41ee4495f0bf7f374333428823254b72de9509be",
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def require(ok, msg):
    if not ok:
        raise SystemExit("REFUSED: " + msg)


def signature(f):
    lf = getattr(f, "lfs", None)
    return {"size": f.size, "blob": f.blob_id, "lfs_sha256": getattr(lf, "sha256", None) if lf else None}


def load_plan():
    plan = json.loads(PREPARED.read_text())
    require(plan.get("status") == "PREPARED_NOT_PUBLISHED", "prepared manifest is not in PREPARED_NOT_PUBLISHED state")
    require(plan.get("model_artifacts_changed") is False, "manifest declares artifact changes; outside this publisher")
    entries = {}
    for f in plan["files"]:
        p = REPO_ROOT / f["path"]
        require(p.is_file(), f"missing {p}")
        require(sha(p.read_bytes()) == f["sha256"], f"prepared file drifted: {f['path']}")
        repo = "caslca/" + Path(f["path"]).parts[2]
        entries.setdefault(repo, {})[Path(f["path"]).name if Path(f["path"]).name == "README.md" else EVIDENCE_NAME] = p
    require(set(entries) == set(EXPECTED_PARENTS), f"repos in manifest {sorted(entries)} != expected")
    for repo, files in entries.items():
        require(set(files) == {"README.md", EVIDENCE_NAME}, f"{repo}: expected README + evidence, got {sorted(files)}")
        ev = json.loads(files[EVIDENCE_NAME].read_text())
        require(ev.get("repo_id") == repo, f"{repo}: evidence names a different repo {ev.get('repo_id')}")
        require(ev.get("result_commit") == plan["result_commit"], f"{repo}: evidence result_commit != manifest")
    return plan, entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--receipt", type=Path, default=REPO_ROOT / "docs" / "huggingface-c92-update-2026-09-20.json")
    ap.add_argument("--journal", type=Path, default=Path(__file__).with_name("journal.jsonl"))
    a = ap.parse_args()
    from huggingface_hub import HfApi, CommitOperationAdd, hf_hub_download

    plan, entries = load_plan()
    api = HfApi()
    anon = HfApi(token=False)

    def record(d):
        d["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with a.journal.open("a") as j:
            j.write(json.dumps(d) + "\n")

    results = []
    for repo, files in entries.items():
        old = api.model_info(repo, files_metadata=True, timeout=30)
        require(old.sha == EXPECTED_PARENTS[repo], f"{repo}: remote HEAD {old.sha} != audited parent; review first")
        before = {f.rfilename: signature(f) for f in old.siblings}
        payloads = {name: p.read_bytes() for name, p in files.items()}
        print(f"{repo}: parent {old.sha}, {len(before)} files; will write {sorted(payloads)} "
              f"({'README exists' if 'README.md' in before else 'README NEW'}, "
              f"{'evidence exists' if EVIDENCE_NAME in before else 'evidence NEW'})")
        if not a.apply:
            continue
        record({"repo_id": repo, "status": "dispatching", "parent_revision": old.sha,
                "planned_sha256": {k: sha(v) for k, v in payloads.items()}})
        result = api.create_commit(
            repo_id=repo, repo_type="model", revision="main", parent_commit=old.sha,
            operations=[CommitOperationAdd(path_in_repo=k, path_or_fileobj=v) for k, v in payloads.items()],
            commit_message="docs: add C89 depth-qualification evidence",
            commit_description=("C89: retrieval 25/25 through 128000 and chain-4 tracking 39/39 through 156000 on the "
                                "shipped native16/MTP-ON configuration; card and dated evidence only, weights/config/"
                                "tokenizer untouched."),
            num_threads=1)
        rev = result.oid
        record({"repo_id": repo, "status": "committed_verification_pending", "revision": rev, "commit_url": result.commit_url})
        new = api.model_info(repo, revision=rev, files_metadata=True, timeout=30)
        after = {f.rfilename: signature(f) for f in new.siblings}
        require(set(after) == set(before) | set(payloads), f"{repo}: unexpected file set change")
        for name, info in before.items():
            if name not in payloads:
                require(after.get(name) == info, f"{repo}: non-card artifact changed: {name}")
        for name, data in payloads.items():
            got = Path(hf_hub_download(repo, name, revision=rev, token=False, force_download=True)).read_bytes()
            require(got == data, f"{repo}: anonymous readback differs: {name}")
        require(api.model_info(repo, timeout=30).sha == rev, f"{repo}: HEAD moved during verification")
        done = {"repo_id": repo, "status": "verified_public", "revision": rev, "parent_revision": old.sha,
                "commit_url": result.commit_url, "published_sha256": {k: sha(v) for k, v in payloads.items()},
                "unchanged_files": len(set(before) - set(payloads))}
        record(done)
        results.append(done)
        print(f"{repo}: PUBLISHED {rev} verified; {done['unchanged_files']} other files unchanged")

    if a.apply:
        receipt = {"scope": "C92: C89 depth-evidence card/evidence update only; no model artifacts changed",
                   "as_of": time.strftime("%Y-%m-%d", time.gmtime()), "status": "published_and_verified",
                   "prepared_manifest": str(PREPARED.relative_to(REPO_ROOT)),
                   "prepared_manifest_sha256": sha(PREPARED.read_bytes()), "result_commit": plan["result_commit"],
                   "repositories": results}
        a.receipt.write_text(json.dumps(receipt, indent=1) + "\n")
        print("receipt:", a.receipt)
    else:
        print("dry run only; re-run with --apply to publish")


if __name__ == "__main__":
    sys.exit(main())
