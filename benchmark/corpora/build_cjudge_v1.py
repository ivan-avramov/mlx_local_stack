#!/usr/bin/env python3
"""Build benchmark/corpora/cjudge_v1.jsonl + cjudge_v1.provenance.json.

Corpus = 18 public prompts (lmarena-ai/arena-hard-auto, v0.1 question file, apache-2.0)
+ 22 domain prompts (verbatim from docs/judge-panel-c.md, dom-01..dom-22).

Public-prompt selection (three-stage, per docs/judge-panel-c.md "Corpus cjudge"):
  1. Filter by the source's own category label (the `cluster` field arena-hard-auto assigns
     each question) to a hand-verified POOL of 40 questions whose actual prompt text is
     software/system-design, ML/AI-research-or-explanation, planning, brainstorming, or
     critique -- and is NOT a coding task, NOT math, NOT creative writing/roleplay, English,
     text-only, <=1500 tokens. `cluster` is a per-item embedding-cluster label, not a coarse
     category, so cluster name alone is NOT a reliable filter (verified by reading every
     candidate's actual prompt text -- most `cluster` names in this corpus are misleading:
     e.g. "Machine Learning Evaluation" -> "show me how to cross validate with sklearn"
     is a coding task, excluded). One item ("Historical and Modern Housebuilding" cluster,
     uid 23aecfcf...) was excluded despite fitting the `critique` category because the prompt
     body quotes a real named student's coursework verbatim -- avoided as third-party PII in a
     public repo, unrelated to any quality concern about the item itself.
  2. Seeded random draw (seed 38) of 30 from that 40-item pool -- POOL below, in this file.
     Kept intact (not re-run) so the draw itself stays reproducible.
  3. Hand curation AFTER the draw (coordinator review, 2026-09-11): the first 30-item public
     draw read as too generic for role C (research/brainstorming/design IN A TECHNICAL
     SETTING) -- it included off-topic domains (triathlon training, climate policy) and
     generic templates (SWOT, debate, word associations) that don't exercise design/research
     judgment the way the role needs. EXCLUDED_AFTER_DRAW removes 12 of the 30, explicitly,
     with reasons -- the draw itself is untouched; only the post-draw curation step is new.
     dom-11..dom-22 (12 new domain prompts) were added to the spec to restore corpus size and
     lean the corpus further toward genuinely technical design/research tasks.

Run: HF_HUB_OFFLINE= PYTHONPATH=benchmark .venv-bench/bin/python benchmark/corpora/build_cjudge_v1.py
"""
import hashlib
import json
import random
import re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
OUT_JSONL = HERE / "cjudge_v1.jsonl"
OUT_PROV = HERE / "cjudge_v1.provenance.json"
SPEC_MD = REPO_ROOT / "docs" / "judge-panel-c.md"

SOURCE_REPO = "lmarena-ai/arena-hard-auto"
SOURCE_FILE = "data/arena-hard-v0.1/question.jsonl"
SOURCE_REVISION = "15f3746e21432264ce9b453999bde4f3c946d2e6"  # dataset commit sha, pinned
SOURCE_LICENSE = "apache-2.0"
SOURCE_TOTAL_QUESTIONS = 500
SELECTION_SEED = 38
POOL_SIZE = 40
DRAW_SIZE = 30
CURATED_PUBLIC_SIZE = 18

# Post-draw hand curation (2026-09-11, coordinator review): (uid, short label, reason).
# Applied to the 30-item seeded draw, never to the pool -- see module docstring stage 3.
EXCLUDED_AFTER_DRAW = [
    ("666658ee4de340a39236f34701446f6b", "triathlon",
     "triathlon training plan -- off-topic domain, not a technical design/research task"),
    ("1cf362fd353f4001a3a6fa23c6833ff0", "citation-list literature review",
     "invites fabricated citations -- a correctness trap, not a design task"),
    ("34690d250eab4d9f9077513f10859335", "SWOT",
     "generic business-analysis template, not a technical design/research task"),
    ("7956046cc15646909bd07c31d0ea0371", "word associations",
     "generic/mechanical brainstorm, doesn't exercise design/research judgment"),
    ("9cdabaf59302429689bf749b2b25ea23", "go meta",
     "gimmicky 'explain an explanation' framing, too generic for the role"),
    ("52b9f9d3ee4b4731bb0e82233fb7a68b", "climate strategy",
     "off-topic domain, generic policy prompt, not a technical design/research task"),
    ("1db228a5c59a41d995a2f1e80633766e", "Java outline",
     "generic learning-plan template, not a technical design/research task"),
    ("fdfea302ee4246689541d7e93e7774a2", "Windows PC",
     "generic sysadmin checklist, not a design/research task"),
    ("c35cf87039684c0db3bdfcbba45e2c69", "critic-role meta prompt",
     "a template instruction for how to give feedback, not a concrete design/research task"),
    ("ed3077a3443a4cf88233f5bc636e7394", "corporate-law pivot",
     "generic career/business prompt, not a technical design/research task"),
    ("188f0735e66a4af5a654ce3c6859f2a9", "debate",
     "generic argumentation exercise, not a technical design/research task"),
    ("26d316034bf44e07aa682d2c2b2751c4", "reflection assignment",
     "generic marketing-ethics reflection prompt, not a technical design/research task"),
]

# Hand-verified pool: (uid, category). See module docstring for the two-stage filter.
POOL = [
    ("1f07cf6d146d4038b2b93aaba3935ce0", "ML/AI research or explanation"),
    ("ed3077a3443a4cf88233f5bc636e7394", "planning"),
    ("90b29911b57848ec89fc7d8c15f27c88", "planning"),
    ("51139d7be0fe4a07bc2d577614ac4487", "planning"),
    ("5c5cb72f4d7b43caa476359c57e898de", "software/system design"),
    ("b253dc64bdd74f5c84882ae51e009ca6", "planning"),
    ("415899b5caf54fba97b3d86b2c8fe3a7", "critique"),
    ("fdfea302ee4246689541d7e93e7774a2", "software/system design"),
    ("188f0735e66a4af5a654ce3c6859f2a9", "brainstorming"),
    ("7956046cc15646909bd07c31d0ea0371", "brainstorming"),
    ("9cab7fd9dd9a43289eace75b5712300e", "brainstorming"),
    ("34690d250eab4d9f9077513f10859335", "critique"),
    ("b91d93746f4e41268b8f1da492b0f2d4", "critique"),
    ("9cdabaf59302429689bf749b2b25ea23", "ML/AI research or explanation"),
    ("1de1a9a531704c82beb10d1d050a8a40", "planning"),
    ("f51671c7ebc74e738f55c15b30622010", "software/system design"),
    ("0df741e684e4408694745a377b3b8e9d", "planning"),
    ("26d316034bf44e07aa682d2c2b2751c4", "brainstorming"),
    ("708512d0a7654dcabf815a4f24765a7d", "brainstorming"),
    ("1db228a5c59a41d995a2f1e80633766e", "planning"),
    ("ef1fe5ad746d4d8db235204f7421260d", "planning"),
    ("c35cf87039684c0db3bdfcbba45e2c69", "critique"),
    ("d35117b13c154c569c2665e696245bc4", "brainstorming"),
    ("a8219c1d829f49109d27e4aa78c72dc5", "planning"),
    ("1cf362fd353f4001a3a6fa23c6833ff0", "ML/AI research or explanation"),
    ("79a28856f6fa4759a5efc9df1ec14d37", "software/system design"),
    ("0e07d745af7e4ec9a2769b77e7ae8ca7", "ML/AI research or explanation"),
    ("ddcdd2879e674e07840a85c9f4d4a957", "software/system design"),
    ("2f51f04418354b3fb0818385285ec1fb", "software/system design"),
    ("c15bbb1710b445109f24fcd2c3d6ef60", "software/system design"),
    ("2a6d0b92fbb5448bb2f7540db9645674", "planning"),
    ("e7e76d4bcf0342308ca6153634000a4a", "planning"),
    ("a89e93c61470449389c17d1f0fcb8469", "software/system design"),
    ("52b9f9d3ee4b4731bb0e82233fb7a68b", "planning"),
    ("666658ee4de340a39236f34701446f6b", "planning"),
    ("c67189582cb34f088ff72251df940821", "planning"),
    ("4c960b9ee8744a98997f7bfde177d2d7", "critique"),
    ("5d3696b459d74604b4f2c41e91d99496", "ML/AI research or explanation"),
    ("8bd1aaae64784e349dc40a07369d54dc", "software/system design"),
    ("0dea89391d074b73a19c8e48ece8640c", "planning"),
]

DOM_CATEGORY = {
    "dom-01": "planning",
    "dom-02": "ML/AI research or explanation",
    "dom-03": "critique",
    "dom-04": "software/system design",
    "dom-05": "ML/AI research or explanation",
    "dom-06": "brainstorming",
    "dom-07": "ML/AI research or explanation",
    "dom-08": "planning",
    "dom-09": "critique",
    "dom-10": "software/system design",
    "dom-11": "software/system design",
    "dom-12": "ML/AI research or explanation",
    "dom-13": "software/system design",
    "dom-14": "critique",
    "dom-15": "planning",
    "dom-16": "software/system design",
    "dom-17": "software/system design",
    "dom-18": "planning",
    "dom-19": "software/system design",
    "dom-20": "critique",
    "dom-21": "ML/AI research or explanation",
    "dom-22": "planning",
}
DOMAIN_PROMPT_COUNT = 22


def _subsample_prefix(items: list, n: int, seed: int) -> list:
    """Same convention as bench.benchmarks._subsample: shuffle-once-by-seed, take prefix."""
    idx = list(range(len(items)))
    random.Random(seed).shuffle(idx)
    return [items[i] for i in idx[:n]]


def _load_domain_prompts() -> dict:
    """Parse the verbatim dom-01..dom-22 block out of docs/judge-panel-c.md, so this builder
    can never drift from the spec of record."""
    text = SPEC_MD.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^(dom-\d\d): (.+)$", text, flags=re.M):
        out[m.group(1)] = m.group(2).strip()
    if len(out) != DOMAIN_PROMPT_COUNT:
        raise SystemExit(f"expected {DOMAIN_PROMPT_COUNT} dom-* prompts in {SPEC_MD}, found {len(out)}")
    return out


def main():
    assert len(POOL) == POOL_SIZE == len(set(u for u, _ in POOL)), "pool must be 40 unique uids"

    from huggingface_hub import hf_hub_download
    path = hf_hub_download(SOURCE_REPO, SOURCE_FILE, repo_type="dataset", revision=SOURCE_REVISION)
    by_uid = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            by_uid[row["uid"]] = row

    missing = [u for u, _ in POOL if u not in by_uid]
    if missing:
        raise SystemExit(f"pool uids not found in source file: {missing}")

    drawn = _subsample_prefix(POOL, DRAW_SIZE, SELECTION_SEED)  # kept intact: the draw is reproducible

    excluded_uids = {u for u, _, _ in EXCLUDED_AFTER_DRAW}
    drawn_uids = {u for u, _ in drawn}
    missing_excl = excluded_uids - drawn_uids
    if missing_excl:
        raise SystemExit(f"EXCLUDED_AFTER_DRAW ids not in the seed-38 draw: {missing_excl}")
    curated = [(u, c) for u, c in drawn if u not in excluded_uids]
    if len(curated) != CURATED_PUBLIC_SIZE:
        raise SystemExit(f"expected {CURATED_PUBLIC_SIZE} public rows after curation, got {len(curated)}")

    rows = []
    for uid, category in curated:
        rows.append({
            "id": f"pub-{uid}",
            "source": SOURCE_REPO,
            "source_id": uid,
            "category": category,
            "prompt": by_uid[uid]["prompt"].strip(),
        })

    dom_prompts = _load_domain_prompts()
    for i in range(1, DOMAIN_PROMPT_COUNT + 1):
        did = f"dom-{i:02d}"
        rows.append({
            "id": did,
            "source": "operator-domain",
            "source_id": did,
            "category": DOM_CATEGORY[did],
            "prompt": dom_prompts[did],
        })

    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    sha256 = hashlib.sha256(OUT_JSONL.read_bytes()).hexdigest()
    from collections import Counter
    cat_counts = dict(Counter(r["category"] for r in rows))
    cat_counts_by_source = {
        "public (lmarena-ai/arena-hard-auto)": dict(Counter(r["category"] for r in rows if r["source"] == SOURCE_REPO)),
        "operator-domain": dict(Counter(r["category"] for r in rows if r["source"] == "operator-domain")),
    }

    provenance = {
        "corpus": "cjudge_v1",
        "rows": len(rows),
        "build_date": date.today().isoformat(),
        "public_prompts": {
            "count": CURATED_PUBLIC_SIZE,
            "source_repo": SOURCE_REPO,
            "source_file": SOURCE_FILE,
            "source_revision": SOURCE_REVISION,
            "license": SOURCE_LICENSE,
            "source_total_questions": SOURCE_TOTAL_QUESTIONS,
            "filter_rules": [
                "stage 1: filtered by the source's own per-question `cluster` label to a pool of "
                "40 questions, each individually verified by reading the actual prompt text against "
                "the category vocabulary (software/system design, ML/AI research or explanation, "
                "planning, brainstorming, critique) and the exclusions (coding tasks, math, creative "
                "writing/roleplay, non-English, non-self-contained, third-party PII)",
                "stage 2: seeded random draw (seed 38) of 30 from that 40-item pool, same "
                "shuffle-then-prefix convention as bench.benchmarks._subsample -- kept intact for "
                "reproducibility; the draw itself is never re-run",
                "stage 3: hand curation AFTER the draw (coordinator review, 2026-09-11): 12 of the "
                "30 drawn items were excluded as too generic/off-topic for role C (research, "
                "brainstorming and design IN A TECHNICAL SETTING) -- see excluded_after_draw. "
                "dom-11..dom-22 were added to the spec to restore corpus size with genuinely "
                "technical design/research prompts",
                "prompt <= 1500 tokens (Qwen3.6-27B-Opus-Distill-OptiQ-4bit tokenizer from the HF "
                "cache; max observed in the pool was 516 tokens)",
                "English, text-only, no images, no tool use, no attached code file > 40 lines",
            ],
            "pool_size": POOL_SIZE,
            "draw_size": DRAW_SIZE,
            "selection_seed": SELECTION_SEED,
            "excluded_by_hand_before_draw": [
                {"uid": "23aecfcf36524c279c3ec77a366ca65e", "cluster": "Historical and Modern Housebuilding",
                 "reason": "otherwise a fitting `critique` prompt (peer review of a research summary), "
                           "but the prompt body quotes a real named student's coursework verbatim -- "
                           "excluded as third-party PII in a public repo"},
            ],
            "excluded_after_draw": [
                {"uid": u, "label": label, "reason": reason}
                for u, label, reason in EXCLUDED_AFTER_DRAW
            ],
        },
        "domain_prompts": {
            "count": DOMAIN_PROMPT_COUNT,
            "source": "operator-domain",
            "spec": "docs/judge-panel-c.md, section 'Domain prompts' (verbatim, ids dom-01..dom-22; "
                    "dom-11..dom-22 added 2026-09-11)",
        },
        "category_counts": cat_counts,
        "category_counts_by_source": cat_counts_by_source,
        "sha256_cjudge_v1_jsonl": sha256,
        "reproduce": ("HF_HUB_OFFLINE= PYTHONPATH=benchmark .venv-bench/bin/python "
                      "benchmark/corpora/build_cjudge_v1.py"),
    }
    with open(OUT_PROV, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {OUT_JSONL} ({len(rows)} rows, sha256={sha256[:12]}...)")
    print(f"wrote {OUT_PROV}")
    print("category counts:", cat_counts)


if __name__ == "__main__":
    main()
