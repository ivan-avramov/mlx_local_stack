"""What fraction of historical rows can the degenerate-loop audit actually SEE?

`reasoning_stats` arrived with harness v2 (2026-08-11). Rows written before that carry no trace
statistics, so `traces.is_degenerate` cannot judge them — and an audit reporting "0.0% degenerate"
while blind to most of the corpus is not evidence of absence. This measures the audit's coverage so
the negative result can be stated with the right scope.

  .venv-bench/bin/python benchmark/m1/stats_coverage.py     # from the repo root
"""
import json
from pathlib import Path

from bench import paths


def main() -> int:
    root = paths.default_results_root()
    tot = with_stats = 0
    per_bench: dict[str, tuple[int, int]] = {}
    for f in sorted(root.glob("*/*.jsonl")):
        for line in f.read_text(errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("error"):
                continue
            tot += 1
            has = bool(r.get("reasoning_stats"))
            with_stats += has
            n, h = per_bench.get(f.stem, (0, 0))
            per_bench[f.stem] = (n + 1, h + has)

    print("%-20s %8s %10s %9s" % ("bench", "rows", "w/ stats", "coverage"))
    for k, (n, h) in sorted(per_bench.items(), key=lambda x: -x[1][0]):
        print("%-20s %8d %10d %8.0f%%" % (k, n, h, 100 * h / max(n, 1)))
    cov = 100 * with_stats / max(tot, 1)
    print()
    print("TOTAL rows=%d  with reasoning_stats=%d  coverage=%.0f%%" % (tot, with_stats, cov))
    print("=> the loop audit can only judge that %.0f%%; the remainder is UNKNOWN, not clean." % cov)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
