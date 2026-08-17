"""Paired suffix-ON / suffix-OFF analyser — the instrument for the one OFAT that decides the lever.

WHY IT IS NOT `compare.py`. `compare` pairs two MODELS on one bench. This pairs one model against
ITSELF under two serving paths, and it needs endpoints `compare` does not carry: per-item text
divergence, the completion-token distribution, and the continuous repetition measures already
persisted in `reasoning_stats`. It deliberately does not re-implement `compare`'s refusals; the
arms come from one model, one box, one session, one sampling config, with only `draft_kind` moved.

WHY THE ENDPOINTS ARE THESE ONES.

* `p_d`, THE DISCORDANT-PAIR RATE, IS MEASURED FIRST AND SIZES EVERYTHING ELSE. The campaign's
  standing figure — "628 matched items to resolve the <=5% gate" — comes from `stats.mde`'s DEFAULT
  `p_d=0.20`, which is a between-MODELS guess. Suffix ON vs OFF is the same weights, same prompt,
  same seeds, differing only by finite-precision noise in a batched verify, so its discordance
  should be far lower. At p_d=0.05 the gate needs 157 items; at 0.02 it needs 63. So the gate may be
  demonstrable on data we already half-own, and `accuracy()` reports n at the MEASURED p_d beside
  the default so the difference cannot be quoted away.

* ACCURACY IS IN, not out. An earlier framing of this OFAT excluded pass@1 as unresolvable. That is
  true only at p_d=0.20. Paired within-model it is the gate itself, and excluding it would measure
  proxies while leaving the actual question open.

* WALL-CLOCK SHARES ARE NOT A QUALITY ENDPOINT HERE, and are reported only under an explicit label.
  Suffix's documented purpose is a 2.41x speedup on VERBATIM text — exactly what a degenerate loop
  emits — so any wall-share metric moves mechanically when the lever moves, with no quality change
  whatsoever. Scoring the lever on `degenerate_wall_share` would manufacture a large effect that
  means nothing. Counts and token shares are the honest degeneracy endpoints.

* DEGENERACY IS REPORTED UNDER BOTH DEFINITIONS IN USE, because the corpus contains two and they
  differ by up to ~10x on the same rows. `grade.py` persists `degenerate_wall_share` over the EOS'd
  degenerate rows ONLY; the published scoreboard row uses every row with
  `nonconv_kind == degenerate_repetition`. Measured 2026-08-16 on
  `Ornith-1.0-35B-mlx-uniform-4bit` mbppplus: 0.0% narrow vs 63.1% broad. One number under that
  name is how the ambiguity spreads.

Validated against known positives in tests/test_suffix_ofat.py: an arm against itself must report
exact zeros, and a known perturbation must come back exactly.

  PYTHONPATH=benchmark .venv-bench/bin/python -m m1.suffix_ofat \\
      --model Ornith-1.0-35B-mlx-uniform-4bit --bench humanevalplus
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics as st
from pathlib import Path

from bench import stats

# The continuous repetition measures already persisted per row. Continuous endpoints carry far more
# information per item than a degeneracy FLAG: the binary rate is 2/100 on
# `Ornith-1.0-35B-mlx-uniform-4bit` humanevalplus, which no feasible n can resolve.
_REPETITION_KEYS = ("ngram8_unique", "ngram20_unique", "unique_line_ratio", "max_line_repeat")


def _key(r) -> tuple:
    return (r.get("id"), r.get("sample", 0))


def _sha(text) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()[:16]


def _paired_mean_ci(diffs: list[float], iters=10000, seed=0) -> dict:
    """Bootstrap CI for the MEAN of per-item differences, resampling ITEMS (the pairing is already
    in the differences). Returns exact zeros for an all-zero input rather than a jittered interval,
    so a self-comparison reads as identical instead of merely small."""
    if not diffs:
        return {"mean_diff": None, "lo": None, "hi": None, "n": 0}
    if all(d == 0 for d in diffs):
        return {"mean_diff": 0.0, "lo": 0.0, "hi": 0.0, "n": len(diffs)}
    rng = random.Random(seed)
    n = len(diffs)
    reps = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return {"mean_diff": st.mean(diffs), "median_diff": st.median(diffs),
            "lo": reps[int(0.025 * len(reps))], "hi": reps[min(len(reps) - 1, int(0.975 * len(reps)))],
            "n": n}


def accuracy(on_per_item: dict, off_per_item: dict, iters=10000, seed=0, margin=0.05) -> dict:
    """Paired accuracy delta PLUS the design numbers at the MEASURED discordance.

    `on_per_item` / `off_per_item` are {item_id: [score, ...]} as `compare._per_item` builds them.
    """
    shared = sorted(set(on_per_item) & set(off_per_item))
    if not shared:
        raise ValueError("accuracy: no shared items")
    disc = sum(1 for i in shared
               if (st.mean(on_per_item[i]) > 0.5) != (st.mean(off_per_item[i]) > 0.5))
    p_d = disc / len(shared)
    d = stats.paired_delta({i: on_per_item[i] for i in shared},
                           {i: off_per_item[i] for i in shared},
                           iters=iters, seed=seed, margin=margin)
    # p_d == 0 means no item flipped: there is nothing to power a test against, and mde/n_for are
    # undefined (a zero-variance paired design). Say so rather than dividing by it.
    out = {"p_d": p_d, "n_discordant": disc, "n_items": len(shared),
           "delta": d["delta"], "lo": d["lo"], "hi": d["hi"], "verdict": d["verdict"],
           "mde_at_default_pd": stats.mde(len(shared)),
           "gate_margin": margin}
    if p_d > 0:
        out["mde_at_measured_pd"] = stats.mde(len(shared), p_d=p_d)
        out["n_for_5pp_at_measured_pd"] = stats.n_for(margin, p_d=p_d)
    else:
        out["mde_at_measured_pd"] = 0.0
        out["n_for_5pp_at_measured_pd"] = 0
        out["note"] = ("p_d = 0: not one item's outcome flipped, so the lever moved no graded "
                       "outcome on this set. A powered test needs discordant pairs to exist.")
    return out


def analyse(on_rows: list[dict], off_rows: list[dict], iters=10000, seed=0) -> dict:
    """Every endpoint computable from the persisted rows alone (no grading, no model).

    ERROR STUBS ARE EXCLUDED FROM PAIRING AND NAMED (operator ruling 2026-08-17): a row whose
    request never completed (`error` set — no content, no tokens) is not a draw, and zero-coercing
    it charges the whole counterpart to the lever (Mbpp/430's `timed out` stub alone more than
    doubled a cell's token delta). A DNF — budget_hit / max_tokens / degenerate_repetition — IS a
    real draw and STAYS in every denominator: a model that converges on 1 of 100 items scores 1%,
    never 100%.
    """
    on_err = sorted(_key(r)[0] for r in on_rows if r.get("error"))
    off_err = sorted(_key(r)[0] for r in off_rows if r.get("error"))
    on = {_key(r): r for r in on_rows if not r.get("error")}
    off = {_key(r): r for r in off_rows if not r.get("error")}
    shared = sorted(set(on) & set(off))
    if not shared:
        raise ValueError("analyse: no paired items between the two arms")

    diverged = [k for k in shared if _sha(on[k].get("content")) != _sha(off[k].get("content"))]
    tok = _paired_mean_ci([(on[k].get("completion_tokens") or 0) - (off[k].get("completion_tokens") or 0)
                           for k in shared], iters=iters, seed=seed)

    rep = {}
    for key in _REPETITION_KEYS:
        diffs = []
        for k in shared:
            a = (on[k].get("reasoning_stats") or {}).get(key)
            b = (off[k].get("reasoning_stats") or {}).get(key)
            if a is not None and b is not None:
                diffs.append(a - b)
        if diffs:
            rep[key] = _paired_mean_ci(diffs, iters=iters, seed=seed)

    def _deg(rows):
        tot_w = sum(r.get("wall_s") or 0 for r in rows) or 0
        tot_t = sum(r.get("completion_tokens") or 0 for r in rows) or 0
        deg = [r for r in rows if r.get("nonconv_kind") == "degenerate_repetition"]
        return {"n_rows": len(rows), "n_degenerate_repetition": len(deg),
                "rate": len(deg) / len(rows) if rows else 0.0,
                # BROAD = every degenerate_repetition row (the published scoreboard's definition).
                "broad_wall_share": (sum(r.get("wall_s") or 0 for r in deg) / tot_w) if tot_w else 0.0,
                "broad_token_share": (sum(r.get("completion_tokens") or 0 for r in deg) / tot_t)
                                     if tot_t else 0.0}

    speed = {k: _paired_mean_ci([(on[i].get(k) or 0) - (off[i].get(k) or 0) for i in shared],
                                iters=iters, seed=seed) for k in ("decode_tps", "wall_s")}
    speed["note"] = ("EXPECTED MECHANICAL EFFECT of the lever, not evidence about quality. Suffix "
                     "accelerates verbatim text 2.41x, so every wall-clock and throughput figure "
                     "moves when it moves. Never score the gate on these.")

    return {
        "n_paired": len(shared),
        "excluded_error_rows": {"on": on_err, "off": off_err},
        "unpaired": {"on_only": [k[0] for k in sorted(set(on) - set(off))],
                     "off_only": [k[0] for k in sorted(set(off) - set(on))]},
        "divergence": {"rate": len(diverged) / len(shared),
                       "n_diverged": len(diverged),
                       "diverged_ids": [k[0] for k in diverged]},
        "tokens": tok,
        "repetition": rep,
        "degeneracy": {"on": _deg([on[k] for k in shared]), "off": _deg([off[k] for k in shared]),
                       "note": "counts and TOKEN shares are the quality-relevant degeneracy "
                               "endpoints; broad_wall_share is included because the published "
                               "scoreboard uses it, but it moves mechanically with the lever"},
        "speed": speed,
    }


def _rows(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--bench", required=True)
    ap.add_argument("--on", default=None, help="suffix-ON rows (default <bench>.suffixon.jsonl)")
    ap.add_argument("--off", default=None, help="suffix-OFF rows (default <bench>.jsonl)")
    ap.add_argument("--iters", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args(argv)

    from bench import paths
    root = paths.repo_root() / "benchmark/results" / a.model
    on_p = Path(a.on) if a.on else root / f"{a.bench}.suffixon.jsonl"
    off_p = Path(a.off) if a.off else root / f"{a.bench}.jsonl"
    for p in (on_p, off_p):
        if not p.exists():
            print(f"missing arm: {p}")
            return 2
    res = analyse(_rows(on_p), _rows(off_p), iters=a.iters)
    res["model"], res["bench"] = a.model, a.bench
    res["arms"] = {"on": str(on_p.name), "off": str(off_p.name)}

    print(f"\n=== suffix OFAT — {a.model} / {a.bench}   (ON={on_p.name}  OFF={off_p.name})")
    print(f"paired items: {res['n_paired']}"
          + (f"   DROPPED on-only={len(res['unpaired']['on_only'])} "
             f"off-only={len(res['unpaired']['off_only'])}"
             if res['unpaired']['on_only'] or res['unpaired']['off_only'] else ""))
    d = res["divergence"]
    print(f"\ntext divergence: {d['n_diverged']}/{res['n_paired']} = {d['rate']:.1%} of items "
          f"produced different text")
    t = res["tokens"]
    print(f"completion tokens (ON-OFF): mean {t['mean_diff']:+.1f} "
          f"CI [{t['lo']:+.1f},{t['hi']:+.1f}]")
    print("\nrepetition (ON-OFF; negative = ON is MORE repetitive):")
    for k, v in res["repetition"].items():
        print(f"  {k:20s} {v['mean_diff']:+.4f}  CI [{v['lo']:+.4f},{v['hi']:+.4f}]")
    dg = res["degeneracy"]
    print(f"\ndegeneracy      ON: {dg['on']['n_degenerate_repetition']}/{dg['on']['n_rows']} "
          f"(token share {dg['on']['broad_token_share']:.1%}, broad WALL share "
          f"{dg['on']['broad_wall_share']:.1%})")
    print(f"                OFF: {dg['off']['n_degenerate_repetition']}/{dg['off']['n_rows']} "
          f"(token share {dg['off']['broad_token_share']:.1%}, broad WALL share "
          f"{dg['off']['broad_wall_share']:.1%})")
    s = res["speed"]
    print(f"\nspeed (mechanical, NOT a quality endpoint): decode_tps {s['decode_tps']['mean_diff']:+.1f}"
          f"  wall_s {s['wall_s']['mean_diff']:+.1f}")
    print("\nACCURACY is not computed here — it needs the graded per-item results "
          "(grade_evalplus for the plus benches). Run accuracy() with those.")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=2))
        print(f"\njson -> {a.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
