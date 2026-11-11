"""M72 1.3 real-model checks (designer instrument; spec `docs/specs/m72-1.3-tq4-production.md` A4 (a) / (b) / (c) and the A6
divergence diagnostic) for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, the candidate fork in-process (PYTHONPATH), one
fresh process per invocation.

  --check a4 --mode m72_v1|m72_exact --T 8192   (one T per process)
      Caches as served (`make_cache` + `maybe_quantize_kv_cache` kv_bits 4 turboquant + preallocation to 262,144; layer 63
      stays native16). Snapshot = twin mode-off prefills of T - 1 tokens (checked bit-identical on the last logits). Mode-off
      phase first (no stamps): greedy MTP OFF (A); for m72_exact also seeded MTP ON (G, mode absent: today's exact per-query
      verify). Then the server's load order (fused_v1, joint_v1 with the mode, require_policy_stamps, check_fp16_range,
      apply_to_model, self_test_model) and: (a) greedy MTP OFF from the twin (B) == A, tokens and logprobs; (b) a mode-on
      prefill's last logits vs mode-off's, max relative difference ≤ 2 × mode-off vs a native16 prefill of the same tokens;
      (c, m72_exact) greedy MTP ON (E) == A's tokens, seeded MTP ON (H) == G's tokens.
  --check diverge --mode m72_v1|m72_exact --prompts 10 --gen 1024
      Seeded-random code prompts (8,192–32,768 tokens of the fork + stack sources, chat template, thinking on), deployed
      sampling of the pick, seed 1000 + i per prompt, MTP ON, fresh served caches per prompt; tokens per prompt to --out.
  --compare a.json b.json   first differing token position per prompt.
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

MODEL = "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAFTER = "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter"
CAP = 262144
CHUNK = 512
KV = dict(kv_bits=4, kv_quant_scheme="turboquant", quantized_kv_start=0, kv_group_size=64, max_kv_size=CAP,
          kv_prealloc_tokens=CAP)
DEPLOYED = dict(temperature=0.5, top_p=0.95, top_k=20, min_p=0.0)  # params_for(..., profile="deployed"), recorded below
SEEDED = dict(temperature=0.8, top_p=0.95, top_k=20, min_p=0.0, seed=11)
GREEDY = dict(temperature=0.0)  # explicit: generate_step resolves temperature=None from the checkpoint's generation config


def corpus_ids(tok):
    import mlx_vlm

    roots = [Path(mlx_vlm.__file__).resolve().parent, Path(__file__).resolve().parents[1]]
    text = ""
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            text += f"\n# ==== {f.name} ====\n" + f.read_text(errors="replace")
    return tok.encode(text)


def served_caches(lm, native=False):
    from mlx_vlm.generate.common import maybe_preallocate_kv_cache, maybe_quantize_kv_cache
    from mlx_vlm.models.cache import PreallocKVCache

    caches = lm.make_cache()
    if native:
        for i, layer in enumerate(lm.layers):
            if not layer.is_linear:
                caches[i] = PreallocKVCache(prealloc_tokens=CAP)
        return caches
    maybe_quantize_kv_cache(caches, quantized_kv_start=0, kv_group_size=64, kv_bits=4, kv_quant_scheme="turboquant",
                            max_kv_size=CAP, kv_prealloc_tokens=CAP)
    maybe_preallocate_kv_cache(caches, kv_prealloc_tokens=CAP)
    return caches


def prefill(lm, caches, ids):
    import mlx.core as mx

    out = None
    for s in range(0, ids.shape[1], CHUNK):
        out = lm(ids[:, s : s + CHUNK], cache=caches)
        mx.eval(getattr(out, "logits", out))
    return getattr(out, "logits", out)[0, -1].astype(mx.float32)


def decode(model, caches, last, n, drafter=None, sampling=None):
    import mlx.core as mx
    from mlx_vlm.generate import ar

    extra = dict(draft_model=drafter, draft_kind="mtp") if drafter is not None else {}
    toks, lps = [], []
    for t, lp in ar.generate_step(last, model, None, None, max_tokens=n, prompt_cache=caches, prefill_step_size=CHUNK,
                                  **KV, **extra, **(sampling or GREEDY)):
        toks.append(int(t))
        lps.append(lp)
    return toks, lps


def stamp(model, mode):
    """The server's load order (`server/generation.py`) for a resolved mode."""
    from mlx_vlm import attention_policy as ap
    from mlx_vlm import mtp_verify_scan as mv
    from mlx_vlm import tq4_attention as t4

    t4.require_environment(mode, kv_bits=4, kv_quant_scheme="turboquant", attention_policy="fused_v1",
                           mtp_verify_scan="joint_v1")
    ap.apply_to_model(model, ap.FusedV1Policy())
    mv.require_environment(draft_kind="mtp", kv_bits=4, kv_quant_scheme="turboquant", tq4_mode=mode)
    mv.apply_to_model(model, mv.JointV1Policy())
    t4.require_policy_stamps(model)
    rng = t4.check_fp16_range(model)
    t4.apply_to_model(model, mode)
    st = t4.self_test_model(model, mode)
    return {"r1": {k: v for k, v in rng.items() if not isinstance(v, (list, dict))}, "self_test_cells": st.get("cells")}


def maxrel(a, b):
    import mlx.core as mx

    return float(mx.max(mx.abs(a - b)) / mx.max(mx.abs(b)))


def lp_identical(x, y):
    import mlx.core as mx

    return len(x) == len(y) and all(bool(mx.array_equal(a, b)) for a, b in zip(x, y))


def check_a4(a):
    import mlx.core as mx
    from mlx_vlm import tq4_fast
    from mlx_vlm.speculative.drafters import load_drafter
    from mlx_vlm.utils import load

    model, processor = load(MODEL)
    tok = getattr(processor, "tokenizer", processor)
    lm = model.language_model
    drafter = load_drafter(DRAFTER, kind="mtp")[0] if a.mode == "m72_exact" else None
    ids_all = corpus_ids(tok)
    n = 256 if a.mode == "m72_exact" else 64
    rows = []
    for T in [a.T]:  # one T per process: the mode is stamped mid-run, so the next snapshot would not be mode-off
        ids = mx.array(ids_all[: T - 1])[None]
        last = mx.array(ids_all[T - 1 : T])[None]  # generate_step takes (1, L) ids
        names = ["A", "A2", "B"] + (["G", "E0", "E", "H"] if a.mode == "m72_exact" else [])
        caches, logits = {}, {}
        for k in names:  # mode-off prefills (the snapshot): the mode is not stamped yet
            caches[k] = served_caches(lm)
            logits[k] = prefill(lm, caches[k], ids)
        snap_ok = all(bool(mx.array_equal(logits["A"], logits[k])) for k in names)
        tA, lA = decode(model, caches["A"], last, n)
        tA2, lA2 = decode(model, caches["A2"], last, n)  # determinism control (mode off twice)
        if a.mode == "m72_exact":
            tG, _ = decode(model, caches["G"], last, n, drafter, SEEDED)
            tE0, _ = decode(model, caches["E0"], last, n, drafter)  # control: mode-absent greedy MTP ON
        rec = stamp(model, a.mode)
        c0 = tq4_fast.route_counts()
        tB, lB = decode(model, caches["B"], last, n)
        row = {"T": T, "n": n, "snapshot_bit_identical": snap_ok,
               "control_mode_off_repeat_identical": tA == tA2 and lp_identical(lA, lA2), "a_tokens_identical": tA == tB,
               "a_logprobs_identical": lp_identical(lA, lB), "load": rec}
        if a.mode == "m72_exact":
            tE, _ = decode(model, caches["E"], last, n, drafter)
            tH, _ = decode(model, caches["H"], last, n, drafter, SEEDED)
            row.update(c_control_mode_absent_greedy_on_equals_off=tE0 == tA, c_greedy_mtp_on_equals_mode_absent_on=tE == tE0,
                       c_greedy_mtp_on_equals_off=tE == tA, c_seeded_equals_mode_absent=tH == tG,
                       c_first_diff_greedy=next((i for i, (x, y) in enumerate(zip(tE, tA)) if x != y), None),
                       c_first_diff_seeded=next((i for i, (x, y) in enumerate(zip(tH, tG)) if x != y), None))
        for k in names:
            del caches[k]
        mx.clear_cache()
        on = prefill(lm, served_caches(lm), ids)  # (b) mode-on prefill
        mx.clear_cache()
        n16 = prefill(lm, served_caches(lm, native=True), ids)
        mx.clear_cache()
        r_on_off, r_off_n16 = maxrel(on, logits["A"]), maxrel(logits["A"], n16)
        row.update(b_rel_on_vs_off=r_on_off, b_rel_off_vs_native16=r_off_n16, b_pass=r_on_off <= 2 * r_off_n16,
                   route_counts_delta={k: v - c0.get(k, 0) for k, v in tq4_fast.route_counts().items() if v != c0.get(k, 0)})
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "load"}), flush=True)
    return {"check": "a4", "mode": a.mode, "rows": rows}


def check_diverge(a):
    import mlx.core as mx
    from mlx_vlm import tq4_fast
    from mlx_vlm.speculative.drafters import load_drafter
    from mlx_vlm.utils import load

    model, processor = load(MODEL)
    tok = getattr(processor, "tokenizer", processor)
    drafter = load_drafter(DRAFTER, kind="mtp")[0]
    rec = stamp(model, a.mode)
    ids_all = corpus_ids(tok)
    rng = random.Random(321)
    out = []
    for i in range(a.prompts):
        L = rng.randint(8192, 32768)
        off = rng.randint(0, len(ids_all) - L - 1)
        code = tok.decode(ids_all[off : off + L])
        msgs = [{"role": "user", "content": "Here is some code:\n\n" + code + "\n\nExplain what this code does and identify any bugs."}]
        prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, enable_thinking=True)
        pids = mx.array(tok.encode(prompt))[None]  # (1, L)
        seed = 1000 + i
        c0 = tq4_fast.route_counts()
        t0 = time.perf_counter()
        toks = []
        from mlx_vlm.generate import ar

        for t, _ in ar.generate_step(pids, model, None, None, max_tokens=a.gen, prefill_step_size=CHUNK, draft_model=drafter,
                                     draft_kind="mtp", seed=seed, **KV, **DEPLOYED):
            toks.append(int(t))
        dt = time.perf_counter() - t0
        delta = {k: v - c0.get(k, 0) for k, v in tq4_fast.route_counts().items() if v != c0.get(k, 0)}
        out.append({"i": i, "seed": seed, "prompt_tokens": int(pids.shape[1]), "code_tokens": L, "tokens": toks,
                    "seconds": round(dt, 1), "route_counts_delta": delta})
        print(json.dumps({k: v for k, v in out[-1].items() if k != "tokens"}), flush=True)
        mx.clear_cache()
    return {"check": "diverge", "mode": a.mode, "sampling": DEPLOYED, "load": rec, "prompts": out}


def compare(paths):
    a, b = (json.loads(Path(p).read_text()) for p in paths)
    res = []
    for x, y in zip(a["prompts"], b["prompts"]):
        assert x["seed"] == y["seed"] and x["prompt_tokens"] == y["prompt_tokens"]
        first = next((i for i, (s, t) in enumerate(zip(x["tokens"], y["tokens"])) if s != t), None)
        if first is None and len(x["tokens"]) != len(y["tokens"]):
            first = min(len(x["tokens"]), len(y["tokens"]))
        res.append({"i": x["i"], "prompt_tokens": x["prompt_tokens"], "first_diff": first,
                    "len": [len(x["tokens"]), len(y["tokens"])]})
    return {"modes": [a["mode"], b["mode"]], "per_prompt": res,
            "identical": sum(r["first_diff"] is None for r in res)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", choices=("a4", "diverge"))
    ap.add_argument("--mode", choices=("m72_v1", "m72_exact"))
    ap.add_argument("--T", type=int, default=8192)
    ap.add_argument("--prompts", type=int, default=10)
    ap.add_argument("--gen", type=int, default=1024)
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.compare:
        print(json.dumps(compare(a.compare), indent=1))
        return 0
    if a.out and Path(a.out).exists():
        print(f"refusing: {a.out} exists", file=sys.stderr)
        return 10
    import mlx.core as mx

    res = check_a4(a) if a.check == "a4" else check_diverge(a)
    res["meta"] = {"model": MODEL, "drafter": DRAFTER, "capacity": CAP, "mlx": mx.__version__,
                   "pythonpath_fork": os.environ.get("PYTHONPATH", "").split(":")[0].rsplit("/", 2)[-2:],
                   "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    Path(a.out).write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
