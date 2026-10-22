"""P426 B9: the committed ID sets of the Fable MTP re-certification (`docs/specs/p426-fable-mtp-recert.md` §3–§5).

`python -m bench.p426_ids` (from `benchmark/`) writes `benchmark/results/p426/ids.json`; the test pins it to a rebuild.
"""

import hashlib
import json
import random
import sys
from pathlib import Path

from bench.rowschema import sample_seed

ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
SEED = 426
SOURCES = {  # the M40 ON rows: the item sets the certification ran on
    "math500": f"benchmark/results/{ENTRY}/math500.m40on.jsonl",
    "cjudge": f"benchmark/results/{ENTRY}/cjudge.m40on.jsonl",
    "vision": f"benchmark/results/{ENTRY}/vision_gate.m40on.jsonl",
}
SIZES = {"math500": 100, "cjudge": 40, "vision": 20}
A4_BASE = 128000000  # run_reasoning: task seed = ctx * 1000 + trial
OUT = "benchmark/results/p426/ids.json"


def _source_ids(repo, axis):
    rows = [
        json.loads(line)
        for line in (Path(repo) / SOURCES[axis]).read_text().splitlines()
        if line.strip()
    ]
    found = [r["id"] for r in rows]
    if len(found) != len(set(found)) or len(found) != SIZES[axis]:
        raise ValueError(f"{axis}: {len(found)} ids ({len(set(found))} unique) != {SIZES[axis]}")
    return sorted(found)


def source_shas(repo):
    return {
        axis: hashlib.sha256((Path(repo) / path).read_bytes()).hexdigest()
        for axis, path in SOURCES.items()
    }


def build(repo):
    rng = random.Random(SEED)
    axes = {}
    for axis in SOURCES:
        found = _source_ids(repo, axis)
        order = list(found)
        rng.shuffle(order)
        half = len(order) // 2
        axes[axis] = dict(
            block1=sorted(order[:half]),
            block2=sorted(order[half:]),
            smoke=sorted(rng.sample(found, 5)),
        )
    tasks = list(range(A4_BASE, A4_BASE + 7))
    axes["reasoning"] = dict(
        block1=tasks[:3],
        block2=tasks[3:6],
        smoke=tasks[6:],
        request_seeds={str(t): sample_seed(f"reasoning:{t}", 0, SEED) for t in tasks},
    )
    return dict(entry=ENTRY, seed=SEED, axes=axes)


def main(argv=None):
    repo = Path(__file__).resolve().parents[2]
    out = repo / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(build(repo), sources_sha256=source_shas(repo))
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(out, hashlib.sha256(out.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
