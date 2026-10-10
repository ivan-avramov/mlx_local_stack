#!/usr/bin/env python3
"""V1b: freeze reference leaf universes and untouched-stub baselines. No model calls."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench import structured_grade as sg, proc_guard as pg, paths
from bench.token_turn_gate import TransportAbort


def eligible(manifest):
    return sorted(
        {
            e["id"]
            for e in manifest["entries"]
            if e["id"].split("/")[0] in ("python", "go") and e["id"] != "go/counter"
        }
    )


def build(manifest, corpus, private, *, grader=sg.grade, expected_count=43):
    ids = eligible(manifest)
    if len(ids) != expected_count:
        raise TransportAbort(
            f"expected {expected_count} eligible items, got {len(ids)}"
        )
    result = {"grader_version": sg.VERSION, "items": {}}
    for item in ids:
        lang, name = item.split("/")
        src = Path(corpus) / lang / "exercises/practice" / name
        try:
            files = json.loads((src / ".meta/config.json").read_text())["files"]
            if (
                len(files["solution"]) != 1
                or len(files["example"]) != 1
                or len(files["test"]) < 1
            ):
                # files.test[0] is the official test (legacy `_solution_and_test`); later entries are helpers
                # (python/paasio: test_utils.py) and stay protected like every prepared file.
                raise ValueError(
                    "requires exactly one solution and example, and at least one test"
                )
            for rel in files["solution"] + files["example"] + files["test"]:
                if (
                    Path(rel).is_absolute()
                    or ".." in Path(rel).parts
                    or not (src / rel).is_file()
                ):
                    raise ValueError("invalid exercise file")
        except (OSError, KeyError, ValueError) as exc:
            raise TransportAbort(item + ": " + str(exc)) from exc
        with tempfile.TemporaryDirectory(prefix="universe-", dir=private) as tmp:
            root = Path(tmp)
            work = root / "tree"
            reports = root / "reports"
            reports.mkdir()
            shutil.copytree(src, work, ignore=shutil.ignore_patterns(".meta"))
            prepared = sg.manifest(work)
            # Reference and stub execute under the same H1/H2 guard, outside model-visible paths.
            with pg.ProcessGuard([root], item=item) as guard:
                stub = grader(lang, work, files["test"][0], reports, guard=guard)
                shutil.copyfile(src / files["example"][0], work / files["solution"][0])
                reference = grader(lang, work, files["test"][0], reports, guard=guard)
            if (
                reference.returncode != 0
                or not reference.collected
                or reference.passing != reference.collected
                or reference.grader_mem_kill
                or reference.grader_oom
            ):
                raise TransportAbort(
                    item + ": reference did not pass every collected test"
                )
            universe = reference.collected
            result["items"][item] = dict(
                leaves=sorted(universe),
                baseline_failing=stub.failing(universe),
                protected=sg.protected_manifest(prepared, files["solution"]),
                prepared=prepared,
                solution=files["solution"][0],
                test=files["test"][0],
                grader_version=sg.VERSION,
            )
    # JSON-native IDs make the returned object identical to its frozen representation.
    return json.loads(json.dumps(result))


def freeze(out, doc):
    out = Path(out)
    side = out.with_suffix(out.suffix + ".sha256")
    if out.exists() or side.exists():
        raise TransportAbort("frozen universe already exists")
    raw = (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode()
    pg.atomic_write(out, raw)
    pg.atomic_write(side, (hashlib.sha256(raw).hexdigest() + "\n").encode())


def load(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if path.with_suffix(path.suffix + ".sha256").read_text().strip() != sha:
            raise ValueError("sha256 differs")
        doc = json.loads(raw)
        if doc["grader_version"] != sg.VERSION or not isinstance(doc["items"], dict):
            raise ValueError("grader version")
        return doc, sha
    except (OSError, ValueError, KeyError) as exc:
        raise TransportAbort("invalid frozen universe: " + str(exc)) from exc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("replay_manifest.json"),
    )
    ap.add_argument(
        "--out", type=Path, default=Path(__file__).with_name("universe.json")
    )
    ap.add_argument("--corpus", type=Path)
    args = ap.parse_args(argv)
    from bench.opencode_common import _polyglot_root

    workdir = paths.stack_workdir().resolve()
    private = workdir / "m62/universe-private"
    private.mkdir(parents=True, exist_ok=True)
    try:
        doc = build(
            json.loads(args.manifest.read_text()),
            args.corpus or _polyglot_root(),
            private,
        )
        freeze(args.out, doc)
        print(f'PASS V1b: {len(doc["items"])} universes; sha256={load(args.out)[1]}')
        return 0
    except (TransportAbort, OSError, ValueError) as exc:
        print("FAIL V1b: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
