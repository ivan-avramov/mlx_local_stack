"""C249 scoresheet (C258): MTP ON vs OFF memory + decode on S′, generated from the source files — never hand-copied.

  .venv-bench/bin/python benchmark/results/c249/make_scoresheet.py --root "$STACK_WORKDIR"   # or an `evidence` checkout

Part 1: the twelve `qualify.py` arms (`p369/phase2/20261030-fd67082a-c249-*/report.json`, on the `evidence` branch).
Part 2: the math500 rows on `main` (`benchmark/results/<entry>/math500.c249-mtp{on,off}-20261030.jsonl`), paired by item;
ON / OFF decode = geometric mean of per-item ratios, 95% item bootstrap (10,000 resamples, seed 1355).
"""
import argparse
import hashlib
import json
import math
import random
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ENTRIES = {"uniform": "Qwen3.8-27B-mlx-uniform-4bit", "qwen36": "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
           "ornith": "Ornith-1.0-35B-mlx-uniform-4bit"}  # allow-shorthand: run-directory keys
P1 = "p369/phase2/20261030-fd67082a-c249-{key}-{n}-{arm}/report.json"
ORDER = ((1, "off"), (2, "on"), (3, "on"), (4, "off"))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def part1(root, key, name):
    arms, sources = [], []
    for n, arm in ORDER:
        rel = P1.format(key=key, n=n, arm=arm)
        doc = json.loads((root / rel).read_text())["entries"][name]
        assert doc["status"] == "COMPLETED", (rel, doc["status"])
        rec = doc["record"]
        arms.append(dict(replicate=n, arm=arm, prefill_peak_gb=rec["peaks"]["prefill"] / 1e9, decode_peak_gb=rec["peaks"]["decode"] / 1e9,
                         decode_tps=doc["rates"]["decode_tps"], prefill_tps=doc["rates"]["prefill_tps"],
                         prompt_tokens=rec["prompt"]["prepared"]["tokens"], generation_tokens=rec["generation_tokens"]))
        sources.append(dict(path=rel, branch="evidence", sha256=sha(root / rel)))

    def mean(arm, k):
        return st.mean(a[k] for a in arms if a["arm"] == arm)
    summary = {k: dict(off=mean("off", k), on=mean("on", k)) for k in ("prefill_peak_gb", "decode_peak_gb", "decode_tps", "prefill_tps")}
    summary["decode_on_vs_off"] = summary["decode_tps"]["on"] / summary["decode_tps"]["off"]
    summary["off_replicate_spread_tps"] = abs(arms[0]["decode_tps"] - arms[3]["decode_tps"])
    return dict(arms=arms, summary=summary, sources=sources)


def part2(name):
    rows, sources = {}, []
    for arm in ("on", "off"):
        rel = f"benchmark/results/{name}/math500.c249-mtp{arm}-20261030.jsonl"
        rows[arm] = {r["id"]: r for r in map(json.loads, (REPO / rel).read_text().splitlines())}
        sources.append(dict(path=rel, branch="main", sha256=sha(REPO / rel)))
    ids = sorted(set(rows["on"]) & set(rows["off"]))
    lr = [math.log(rows["on"][i]["decode_tps"] / rows["off"][i]["decode_tps"]) for i in ids]
    rng = random.Random(1355)
    boot = sorted(math.exp(st.mean(rng.choices(lr, k=len(lr)))) for _ in range(10000))

    def arm_stats(arm):
        rs = [rows[arm][i] for i in ids]
        tok = sum(r["completion_tokens"] for r in rs)
        drafts = [r.get("draft") or {} for r in rs]
        n = sum(d.get("draft_n") or 0 for d in drafts)
        return dict(token_weighted_decode_tps=tok / sum(r["completion_tokens"] / r["decode_tps"] for r in rs),
                    median_decode_tps=st.median(r["decode_tps"] for r in rs), mean_tokens=tok / len(rs),
                    max_tokens=max(r["completion_tokens"] for r in rs), converged=sum(bool(r.get("converged")) for r in rs),
                    draft_acceptance=(sum(d.get("draft_n_accepted") or 0 for d in drafts) / n) if n else None)
    identical = sum(rows["on"][i]["content_sha256"] == rows["off"][i]["content_sha256"]
                    and rows["on"][i]["reasoning_sha256"] == rows["off"][i]["reasoning_sha256"] for i in ids)
    return dict(items=len(ids), identical_outputs=identical, on=arm_stats("on"), off=arm_stats("off"),
                decode_ratio_geomean=math.exp(st.mean(lr)), decode_ratio_ci95=[boot[250], boot[9750]],
                decode_ratio_min=math.exp(min(lr)), decode_ratio_max=math.exp(max(lr)), sources=sources)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, help="$STACK_WORKDIR or an evidence-branch checkout (holds p369/phase2)")
    ap.add_argument("--out", default=str(Path(__file__).with_name("scoresheet.json")))
    a = ap.parse_args()
    root = Path(a.root)
    sheet = dict(decision="C249 / C258", generator="benchmark/results/c249/make_scoresheet.py",
                 entries={name: dict(at_256k=part1(root, key, name), normal_length=part2(name)) for key, name in ENTRIES.items()})
    Path(a.out).write_text(json.dumps(sheet, indent=1, sort_keys=True) + "\n")
    for name, e in sheet["entries"].items():
        p1, p2 = e["at_256k"]["summary"], e["normal_length"]
        print(f"{name}: normal {p2['decode_ratio_geomean']:.2f}x [{p2['decode_ratio_ci95'][0]:.2f}, {p2['decode_ratio_ci95'][1]:.2f}] "
              f"identical {p2['identical_outputs']}/{p2['items']}; 256K decode {p1['decode_tps']['off']:.2f} -> {p1['decode_tps']['on']:.2f} "
              f"({100 * (p1['decode_on_vs_off'] - 1):+.0f}%), prefill peak {p1['prefill_peak_gb']['off']:.2f} -> {p1['prefill_peak_gb']['on']:.2f} GB")


if __name__ == "__main__":
    main()
