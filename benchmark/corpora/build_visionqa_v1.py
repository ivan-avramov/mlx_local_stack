#!/usr/bin/env python3
"""Build benchmark/corpora/visionqa_v1.jsonl + visionqa_v1.provenance.json (M39, docs/vision-smoke-m39.md).

Corpus = 40 visual-QA items, ids + gold answers committed here; IMAGES ARE NEVER COPIED INTO THE
REPO -- each row stores an `image_ref` ({dataset, revision, split, index}) that the loader
(`bench/benchmarks.py::_load_visionqa`) resolves against the local HF datasets cache at
generation time.

Sources (spec table, docs/vision-smoke-m39.md):
    ChartQA val         (HuggingFaceM4/ChartQA)             15  GPL-3.0 (ids-only storage)
    RICO ScreenQA-Short (rootsautomation/RICO-ScreenQA-Short) 10  CC BY 4.0
    AI2D                (lmms-lab/ai2d)                       10  CC BY-SA
    TextVQA val                                                5  CC BY 4.0

DEVIATION from the spec's literal `facebook/textvqa` repo id (recorded here + in the provenance
file, not silently swapped): the canonical `facebook/textvqa` loading script requires
`trust_remote_code=True` (arbitrary code execution) and downloads a ~20GB train+val image zip
from dl.fbaipublicfiles.com just to reach 5 items. `lmms-lab/textvqa` is a parquet mirror of the
IDENTICAL official TextVQA annotations (same license, same `val` split, same 10-reference answers,
`set_name=="val"` verified per row) used by the lmms-eval framework -- no custom code, no giant
zip. Substituted on that basis; flag for operator review if a byte-identical source is required.

Selection (seed 39, per source): each source's HF split is filtered to TEXT-ONLY candidates
(question <= 60 words, answer non-empty) using column-wise access (`ds["col"]`), which never
decodes the image column. The filtered pool is shuffled once by
`random.Random(f"visionqa-v1:{seed}:{source_kind}")` (str-seeded, same convention as
bench.benchmarks._load_gpqa's per-item seeding) and walked in that order: each candidate's image
is opened (PIL) only now, checked <= 2 MP (via `.size`, header-only -- no full raster decode) and
deduplicated (natural id when the source has one -- RICO `file_name`, TextVQA `image_id`; else a
sha256 of the raw pixel bytes for ChartQA/AI2D, which carry no per-row id). The walk stops at the
source's target count. Every FINALLY SELECTED row is then forced through `img.load()` as a real
"does this image load" check (cheap at n<=15 per source) before being written out.

Run: HF_HUB_OFFLINE= PYTHONPATH=benchmark .venv-bench/bin/python benchmark/corpora/build_visionqa_v1.py
"""
import hashlib
import json
import random
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_JSONL = HERE / "visionqa_v1.jsonl"
OUT_PROV = HERE / "visionqa_v1.provenance.json"

SELECTION_SEED = 39
MAX_QUESTION_WORDS = 60
MAX_PIXELS = 2_000_000  # 2 MP

SUFFIX = "\n\nAnswer with the final answer only, inside \\boxed{}."

# (source_kind, HF repo, license, split, target count, pinned revision)
SOURCES = [
    ("chartqa", "HuggingFaceM4/ChartQA", "GPL-3.0 (ids-only storage)", "val", 15,
     "b605b6e08b57faf4359aeb2fe6a3ca595f99b6c5"),
    ("screenqa", "rootsautomation/RICO-ScreenQA-Short", "CC BY 4.0", "test", 10,
     "d432b8e9e191447b4d04d99e2740838d7319dac5"),
    ("ai2d", "lmms-lab/ai2d", "CC BY-SA", "test", 10,
     "c83a9b9692933aff8349157c88a413df9d02c4e5"),
    # DEVIATION: facebook/textvqa (spec literal) -> lmms-lab/textvqa mirror, see module docstring.
    ("textvqa", "lmms-lab/textvqa", "CC BY 4.0", "validation", 5,
     "9c0699cd19768ac5ab97568f6b3cbac4c0062884"),
]

TEXTVQA_SPEC_SOURCE = "facebook/textvqa"


def _words(s: str) -> int:
    return len((s or "").split())


def _image_hash(img) -> str:
    """Content identity for sources with no natural per-row id. Full raster decode, but only ever
    called on candidates actually walked (bounded by the target count + a few rejects/dupes)."""
    return hashlib.sha256(img.tobytes()).hexdigest()


def _candidates_chartqa(ds):
    queries, labels = ds["query"], ds["label"]
    out = []
    for i, (q, lab) in enumerate(zip(queries, labels)):
        q = (q or "").strip()
        ans = str((lab or [None])[0] or "").strip()
        if not q or not ans or _words(q) > MAX_QUESTION_WORDS:
            continue
        out.append({"index": i, "question": q, "answer": ans})
    return out


def _candidates_screenqa(ds):
    questions, gts, files = ds["question"], ds["ground_truth"], ds["file_name"]
    out = []
    for i, (q, gt, fn) in enumerate(zip(questions, gts, files)):
        q = (q or "").strip()
        gt = [a for a in (gt or []) if (a or "").strip()]
        if not q or not gt or _words(q) > MAX_QUESTION_WORDS:
            continue
        out.append({"index": i, "question": q, "answer": gt, "natural_id": fn})
    return out


def _candidates_ai2d(ds):
    questions, options, answers = ds["question"], ds["options"], ds["answer"]
    out = []
    for i, (q, opts, ans) in enumerate(zip(questions, options, answers)):
        q = (q or "").strip()
        try:
            idx = int(ans)
        except (TypeError, ValueError):
            continue
        if not q or not opts or not (0 <= idx < len(opts)) or not str(opts[idx]).strip():
            continue
        if _words(q) > MAX_QUESTION_WORDS:
            continue
        out.append({"index": i, "question": q, "choices": list(opts), "answer": "ABCD"[idx]})
    return out


def _candidates_textvqa(ds):
    questions, answers, image_ids = ds["question"], ds["answers"], ds["image_id"]
    out = []
    for i, (q, ans, iid) in enumerate(zip(questions, answers, image_ids)):
        q = (q or "").strip()
        ans = [a for a in (ans or []) if (a or "").strip()]
        if not q or len(ans) < 10 or _words(q) > MAX_QUESTION_WORDS:
            continue
        out.append({"index": i, "question": q, "answer": ans, "natural_id": iid})
    return out


_CANDIDATE_FNS = {
    "chartqa": _candidates_chartqa,
    "screenqa": _candidates_screenqa,
    "ai2d": _candidates_ai2d,
    "textvqa": _candidates_textvqa,
}


def _select(source_kind, ds, candidates, n, seed):
    idx = list(range(len(candidates)))
    random.Random(f"visionqa-v1:{seed}:{source_kind}").shuffle(idx)
    chosen, seen_images, rejected = [], set(), []
    for i in idx:
        if len(chosen) >= n:
            break
        c = candidates[i]
        row = ds[c["index"]]
        img = row["image"]
        w, h = img.size
        if w * h > MAX_PIXELS:
            rejected.append((c["index"], "over_2mp"))
            continue
        natural_id = c.get("natural_id")
        image_key = str(natural_id) if natural_id not in (None, "") else _image_hash(img)
        if image_key in seen_images:
            rejected.append((c["index"], "duplicate_image"))
            continue
        seen_images.add(image_key)
        fmt = (img.format or "PNG").upper()
        chosen.append({**c, "image_size": [w, h], "image_format": fmt})
    if len(chosen) < n:
        raise SystemExit(f"{source_kind}: only found {len(chosen)}/{n} eligible items "
                         f"after filtering ({len(candidates)} candidates, {len(rejected)} rejected)")
    return chosen, rejected


def _verify_loads(ds, c):
    """Real 'does this image load' check -- forced full decode, only on the FINAL selection."""
    img = ds[c["index"]]["image"]
    img.load()
    return img


def _to_float(s):
    try:
        return float(str(s).replace("%", "").replace("$", "").replace(",", ""))
    except ValueError:
        return None


def main():
    from datasets import load_dataset

    all_rows, counts, rejected_counts = [], {}, {}
    for source_kind, repo, license_, split, n, revision in SOURCES:
        ds = load_dataset(repo, split=split, revision=revision)
        candidates = _CANDIDATE_FNS[source_kind](ds)
        chosen, rejected = _select(source_kind, ds, candidates, n, SELECTION_SEED)
        counts[source_kind] = len(chosen)
        rejected_counts[source_kind] = dict(Counter(reason for _, reason in rejected))

        for k, c in enumerate(chosen):
            img = _verify_loads(ds, c)
            row_id = f"{source_kind}-{k:03d}"
            row = {
                "id": row_id,
                "source": repo,
                "source_kind": source_kind,
                "source_id": str(c.get("natural_id", c["index"])),
                "image_ref": {"dataset": repo, "revision": revision, "split": split,
                             "index": c["index"]},
                "question": c["question"],
                "answer": c["answer"],
                "choices": c.get("choices"),
                "meta": {
                    "image_width": img.size[0], "image_height": img.size[1],
                    "image_format": c["image_format"], "question_words": _words(c["question"]),
                    "license": license_,
                },
            }
            if source_kind == "chartqa":
                row["answer_numeric"] = _to_float(c["answer"]) is not None
            all_rows.append(row)

    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    sha256 = hashlib.sha256(OUT_JSONL.read_bytes()).hexdigest()
    provenance = {
        "corpus": "visionqa_v1",
        "rows": len(all_rows),
        "build_date": date.today().isoformat(),
        "selection_seed": SELECTION_SEED,
        "filters": [
            f"question <= {MAX_QUESTION_WORDS} words",
            "answer non-empty (>=10 references kept for TextVQA)",
            f"image <= {MAX_PIXELS} px (2 MP), checked via PIL .size (header-only, no full decode)",
            "no duplicate images within a source (natural id when the source has one -- RICO "
            "file_name, TextVQA image_id -- else sha256 of the decoded pixel bytes for "
            "ChartQA/AI2D, which carry no per-row id)",
            "every FINAL selected row's image forced through PIL .load() as a real load check",
        ],
        "sources": [
            {"source_kind": k, "repo": repo, "license": lic, "split": split,
             "revision": rev, "n": counts[k], "rejected": rejected_counts[k]}
            for k, repo, lic, split, _, rev in SOURCES
        ],
        "deviation_textvqa": {
            "spec_source": TEXTVQA_SPEC_SOURCE,
            "used_source": "lmms-lab/textvqa",
            "reason": ("facebook/textvqa requires trust_remote_code=True (arbitrary script "
                      "execution) and its loader downloads a ~20GB train+val image zip from "
                      "dl.fbaipublicfiles.com; lmms-lab/textvqa is a parquet mirror of the "
                      "identical official annotations (same license, same val split via "
                      "set_name=='val', same 10 references/question), no custom code, no zip."),
        },
        "sha256_visionqa_v1_jsonl": sha256,
        "reproduce": ("HF_HUB_OFFLINE= PYTHONPATH=benchmark .venv-bench/bin/python "
                      "benchmark/corpora/build_visionqa_v1.py"),
    }
    with open(OUT_PROV, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {OUT_JSONL} ({len(all_rows)} rows, sha256={sha256[:12]}...)")
    print(f"wrote {OUT_PROV}")
    print("counts:", counts)
    print("rejected:", rejected_counts)


if __name__ == "__main__":
    main()
