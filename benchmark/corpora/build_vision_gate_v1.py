#!/usr/bin/env python3
"""Build benchmark/corpora/vision_gate_v1.jsonl + vision_gate_v1.provenance.json.

M39 vision gate (operator re-scope, 2026-09-12): NOT a benchmark -- a pass/fail check that "a
model can do some vision". Corpus = 20 COCO val2017 images with their human reference captions,
drawn from `lmms-lab/COCO-Caption2017` (a parquet mirror of the official COCO 2017 captions
annotations used by lmms-eval). IMAGES ARE NEVER COPIED INTO THE REPO -- each row stores an
`image_ref` ({dataset, revision, split, index}) that the runner (`benchmark/vision_gate.py`)
resolves against the local HF datasets cache at run time, same pattern as
`bench/benchmarks.py::_visionqa_image_cache_path`.

License (recorded verbatim in the provenance file): COCO's caption ANNOTATIONS are CC BY 4.0.
COCO's IMAGES are each individually licensed by their original Flickr uploader under one of
eight Flickr license codes (COCO's own `license` column, 1-8 -- see `COCO_LICENSES` below); this
corpus stores the per-row code + resolved name/URL rather than asserting one blanket license.

Selection (seed 40): the val split (5000 rows, COCO val2017) is filtered to `height*width <=
MAX_PIXELS` (checked via the dataset's own `height`/`width` columns -- no image decode at all for
this step) and `len(answer) >= MIN_CAPTIONS`. Filtered candidate indices are shuffled once by
`random.Random(f"vision-gate-v1:{seed}")` (str-seeded, same convention as
`build_visionqa_v1.py`/`bench.benchmarks._load_gpqa`) and walked in that order. "Varied scenes" is
approximated (operator: "dedupe by first caption's first noun is fine") by a cheap heuristic --
the first non-stopword token of the first caption -- deduped so no two selected rows share that
token; the walk stops at 20. Every FINALLY SELECTED row's image is then forced through PIL
`.load()` as a real "does this image load" check.

Run: HF_HUB_OFFLINE= PYTHONPATH=benchmark .venv-bench/bin/python benchmark/corpora/build_vision_gate_v1.py
"""
import hashlib
import json
import random
import re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_JSONL = HERE / "vision_gate_v1.jsonl"
OUT_PROV = HERE / "vision_gate_v1.provenance.json"

REPO = "lmms-lab/COCO-Caption2017"
REVISION = "3bdd5827e243cc3084ac69a1111e69c3ab9193ff"
SPLIT = "val"
SELECTION_SEED = 40
N = 20
MAX_PIXELS = 2_000_000  # 2 MP
MIN_CAPTIONS = 4
CAPTIONS_PER_ROW = 5  # a handful of rows carry 6-7; truncate to 5 for a uniform row shape

# COCO's own per-image license code (its `license` column) -> (name, url). Original COCO
# `instances_val2017.json` / caption-annotation `licenses` block, reproduced here so a row's
# numeric code is human-legible without a second lookup.
COCO_LICENSES = {
    1: ("Attribution-NonCommercial-ShareAlike License", "https://creativecommons.org/licenses/by-nc-sa/2.0/"),
    2: ("Attribution-NonCommercial License", "https://creativecommons.org/licenses/by-nc/2.0/"),
    3: ("Attribution-NonCommercial-NoDerivs License", "https://creativecommons.org/licenses/by-nc-nd/2.0/"),
    4: ("Attribution License", "https://creativecommons.org/licenses/by/2.0/"),
    5: ("Attribution-ShareAlike License", "https://creativecommons.org/licenses/by-sa/2.0/"),
    6: ("Attribution-NoDerivs License", "https://creativecommons.org/licenses/by-nd/2.0/"),
    7: ("No known copyright restrictions", "http://flickr.com/commons/usage/"),
    8: ("United States Government Work", "http://www.usa.gov/copyright.shtml"),
}

# Cheap "is this the start of a real content word" filter for the diversity heuristic below --
# not a real POS tagger, just enough to skip past articles/quantifiers/copulas to something
# noun-ish. Operator: "dedupe by first caption's first noun is fine".
_LEADING_STOPWORDS = {
    "a", "an", "the", "this", "that", "these", "those", "some", "several", "many", "few",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "there", "is", "are", "it", "its",
}


def _first_noun_key(caption: str) -> str:
    """Approximate "subject" of a caption: the first word that isn't a leading stopword. Used
    only to spread the selection across different-looking scenes, not for correctness."""
    words = re.findall(r"[a-z']+", (caption or "").lower())
    for w in words:
        if w not in _LEADING_STOPWORDS:
            return w
    return words[0] if words else ""


def _select(ds, seed):
    heights, widths, answers = ds["height"], ds["width"], ds["answer"]
    candidates = [
        i for i in range(len(ds))
        if heights[i] * widths[i] <= MAX_PIXELS and len([a for a in (answers[i] or []) if (a or "").strip()]) >= MIN_CAPTIONS
    ]
    idx = list(candidates)
    random.Random(f"vision-gate-v1:{seed}").shuffle(idx)
    chosen, seen_keys, rejected_duplicate = [], set(), 0
    for i in idx:
        if len(chosen) >= N:
            break
        caps = [a.strip() for a in answers[i] if (a or "").strip()]
        key = _first_noun_key(caps[0])
        if key in seen_keys:
            rejected_duplicate += 1
            continue
        seen_keys.add(key)
        chosen.append({"index": i, "captions": caps[:CAPTIONS_PER_ROW], "first_noun_key": key})
    if len(chosen) < N:
        raise SystemExit(f"only found {len(chosen)}/{N} eligible rows "
                         f"({len(candidates)} candidates after filtering)")
    return chosen, len(candidates), rejected_duplicate


def main():
    from datasets import load_dataset

    ds = load_dataset(REPO, split=SPLIT, revision=REVISION)
    chosen, n_candidates, rejected_duplicate = _select(ds, SELECTION_SEED)

    rows = []
    for k, c in enumerate(chosen):
        row_ds = ds[c["index"]]
        img = row_ds["image"]
        img.load()  # real "does this image load" check, only on the final selection
        lic_id = int(row_ds["license"])
        lic_name, lic_url = COCO_LICENSES.get(lic_id, ("unknown", None))
        row = {
            "id": f"cocoval2017-{k:03d}",
            "image_ref": {"dataset": REPO, "revision": REVISION, "split": SPLIT,
                         "index": c["index"]},
            "captions": c["captions"],
            "meta": {
                "image_width": img.size[0], "image_height": img.size[1],
                "image_format": (img.format or "JPEG").upper(),
                "coco_image_id": row_ds["id"], "file_name": row_ds["file_name"],
                "coco_url": row_ds["coco_url"], "date_captured": row_ds["date_captured"],
                "license_id": lic_id, "license_name": lic_name, "license_url": lic_url,
                "first_noun_key": c["first_noun_key"],
            },
        }
        rows.append(row)

    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    sha256 = hashlib.sha256(OUT_JSONL.read_bytes()).hexdigest()
    provenance = {
        "corpus": "vision_gate_v1",
        "purpose": "pass/fail vision GATE (\"can this model do some vision\"), not a scored benchmark",
        "rows": len(rows),
        "build_date": date.today().isoformat(),
        "selection_seed": SELECTION_SEED,
        "source": {
            "repo": REPO, "revision": REVISION, "split": SPLIT,
            "note": ("parquet mirror of the official COCO 2017 caption annotations used by "
                     "lmms-eval; val split = COCO val2017 (5000 images)"),
        },
        "license": {
            "annotations": "CC BY 4.0",
            "images": ("Flickr terms; PER-IMAGE, not blanket -- COCO's own numeric `license` "
                      "code (1-8) is recorded per row in meta.license_id/name/url"),
            "coco_license_codes": {str(k): {"name": v[0], "url": v[1]}
                                   for k, v in COCO_LICENSES.items()},
        },
        "filters": [
            f"image <= {MAX_PIXELS} px (2 MP), from the dataset's own height/width columns "
            "(no image decode needed for this step)",
            f"at least {MIN_CAPTIONS} non-empty reference captions",
            "diversity heuristic: dedupe by the first caption's first non-stopword token "
            "(\"first noun\", approximated) -- no two selected rows share that token",
            "every FINAL selected row's image forced through PIL .load() as a real load check",
        ],
        "candidates_after_filtering": n_candidates,
        "rejected_duplicate_scene_key": rejected_duplicate,
        "captions_per_row": CAPTIONS_PER_ROW,
        "sha256_vision_gate_v1_jsonl": sha256,
        "reproduce": ("HF_HUB_OFFLINE= PYTHONPATH=benchmark .venv-bench/bin/python "
                      "benchmark/corpora/build_vision_gate_v1.py"),
    }
    with open(OUT_PROV, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {OUT_JSONL} ({len(rows)} rows, sha256={sha256[:12]}...)")
    print(f"wrote {OUT_PROV}")
    print("ids:", [r["id"] for r in rows])


if __name__ == "__main__":
    main()
