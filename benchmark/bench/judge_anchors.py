"""Anchor pairs for the role-C (M38) blind judge panel — `docs/judge-panel-c.md` "Anchors".

30 pairs (10 `degrade`, 10 `verbosity`, 10 `identity`), drawn seeded across the four contenders'
`cjudge.<tune>.jsonl` CONVERGED rows, mechanically transformed so each type has a known-correct
verdict (`expected`). These are mixed in blind with the real candidate pairs
(`judge_pairwise.build_candidate_pairs`) so the panel's reliability can be measured against
ground truth BEFORE any candidate ranking is trusted (`judge_gate.py`).

Row identity for the transform-source lookup is `model::item_id`, matching
`judge_pairwise.build_candidate_pairs`'s `a_key`/`b_key` convention.
"""
import json
import os
import random
import re

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

ANCHOR_TYPES = ("degrade", "verbosity", "identity")
N_PER_TYPE = 10

_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+.*$", re.MULTILINE)
_LIST_MARKER_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", re.MULTILINE)
_AUX_RE = re.compile(
    r"\b(is|are|was|were|am|be|been|being|has|have|had|do|does|did|"
    r"can|could|will|would|shall|should|may|might|must)\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_FILLERS = ("Furthermore, ", "In addition, ", "Moreover, ", "Building on this point, ",
            "To elaborate further, ", "It is also worth noting that ")
_MIN_NEGATE_WORDS = 6

# Regions the transforms must leave byte-for-byte alone: a fenced code block (```...```,
# optionally indented up to 3 spaces, matching CommonMark) or a contiguous run of GFM table
# rows (`| a | b |`, including the `|---|---|` separator row). Negating a "sentence" that is
# actually a line of code, or flattening a table into run-on prose, would corrupt content the
# transform isn't supposed to be touching at all — the anchor's mechanism is about PROSE
# structure, not code/data correctness.
_FENCE_LINE_RE = re.compile(r"^[ \t]{0,3}```")
_TABLE_ROW_RE = re.compile(r"^[ \t]*\|.*\|[ \t]*$")


def _protected_blocks(text):
    """Split `text` into an ordered list of `("prose"|"protected", [line, ...])` blocks. A
    fenced code block (open ``` to matching close ```) or a contiguous run of table-row lines
    becomes one "protected" block; everything else is grouped into "prose" blocks. Concatenating
    every block's lines with "\\n" reproduces `text` exactly (this function only classifies,
    never rewrites)."""
    lines = text.split("\n")
    blocks, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if _FENCE_LINE_RE.match(line):
            block = [line]
            i += 1
            while i < n and not _FENCE_LINE_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            if i < n:                      # the matching closing fence
                block.append(lines[i])
                i += 1
            blocks.append(("protected", block))
        elif _TABLE_ROW_RE.match(line):
            block = [line]
            i += 1
            while i < n and _TABLE_ROW_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            blocks.append(("protected", block))
        else:
            block = [line]
            i += 1
            while i < n and not _FENCE_LINE_RE.match(lines[i]) and not _TABLE_ROW_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            blocks.append(("prose", block))
    return blocks


# --------------------------------------------------------------------------------- loading
def load_converged_rows(models, tune="m38", results_dir=RESULTS):
    """Read `<results_dir>/<model>/cjudge.<tune>.jsonl` for each model in `models`, tagging
    every row with its source `model`. Missing files are skipped (graceful-degrade — a model
    not yet generated must not crash the anchor build for the others). Rows without `converged`
    are kept as-is; callers filter (see `build_anchor_pairs`)."""
    rows = []
    for model in models:
        path = os.path.join(results_dir, model, f"cjudge.{tune}.jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                row.setdefault("model", model)
                rows.append(row)
    return rows


# ---------------------------------------------------------------------------- degrade transform
def _split_sections(text):
    """Split `text` into contiguous blocks at markdown heading lines. With no headings, split
    on blank-line paragraphs instead. Always returns >=1 non-empty section covering the text."""
    lines = text.split("\n")
    heading_idxs = [i for i, ln in enumerate(lines) if _HEADING_RE.match(ln)]
    if heading_idxs:
        bounds = heading_idxs + [len(lines)]
        sections = []
        if heading_idxs[0] > 0:
            sections.append("\n".join(lines[: heading_idxs[0]]))
        for i in range(len(heading_idxs)):
            sections.append("\n".join(lines[bounds[i]: bounds[i + 1]]))
        sections = [s for s in sections if s.strip()]
        return sections or [text]
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras or [text]


def _flatten(text):
    """Strip heading/list markers and collapse all whitespace into single spaces — a run-on
    paragraph with no structural markup left in it."""
    text = _HEADING_RE.sub(lambda m: re.sub(r"^[ \t]{0,3}#{1,6}[ \t]+", "", m.group(0)), text)
    text = _LIST_MARKER_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _negate_sentence(sentence):
    """Insert 'not' after the first auxiliary/copula. `degrade_text` only ever calls this on
    sentences `_is_negatable` already confirmed have one, so the "no aux" fallback below is
    unreachable from there — kept for any direct caller (and its own unit test) that wants the
    deterministic degenerate-case behavior rather than a KeyError."""
    m = _AUX_RE.search(sentence)
    if not m:
        return "It is not the case that " + sentence
    j = m.end()
    return sentence[:j] + " not" + sentence[j:]


def _is_negatable(sentence):
    """Eligible for negation: >= _MIN_NEGATE_WORDS words AND contains a copula/auxiliary. A
    short fragment ("Do 3.") or a sentence with no copula/auxiliary reads as an odd or
    ambiguous negation once "not" is inserted — restricting to longer, aux-bearing sentences
    keeps the negated anchor unambiguously false rather than just awkward."""
    return (len(sentence.split()) >= _MIN_NEGATE_WORDS) and bool(_AUX_RE.search(sentence))


def degrade_text(text, seed=38):
    """Original -> mechanically degraded copy: drop the final section (last heading block or
    last paragraph), flatten the PROSE of what remains into run-on prose (no headings/list
    markers) while leaving fenced code blocks and table rows completely untouched, then negate
    up to two eligible prose sentences (`_is_negatable`) chosen by `seed` (deterministic: same
    text+seed -> same output). Typically shorter than the input (a whole section is dropped),
    but NOT guaranteed shorter on a heading-less, single-paragraph answer with a large
    protected block — the mechanism is the dropped section + the negations, not raw length.
    """
    sections = _split_sections(text)
    if len(sections) > 1:
        sections = sections[:-1]
    body = "\n".join(sections)

    blocks = _protected_blocks(body)
    # Flatten each PROSE block independently (never merging across a protected block) and
    # collect (block_index, sentence_index) for every eligible sentence, so a chosen
    # negation can be written back into exactly the block/sentence it came from.
    block_sentences = [None] * len(blocks)
    eligible = []
    for bi, (kind, lines) in enumerate(blocks):
        if kind != "prose":
            continue
        flat = _flatten("\n".join(lines))
        sents = [s for s in _SENTENCE_SPLIT_RE.split(flat) if s.strip()]
        block_sentences[bi] = sents
        for si, s in enumerate(sents):
            if _is_negatable(s):
                eligible.append((bi, si))

    if eligible:
        rng = random.Random(seed)
        k = min(2, len(eligible))
        for bi, si in (eligible[i] for i in rng.sample(range(len(eligible)), k)):
            block_sentences[bi][si] = _negate_sentence(block_sentences[bi][si])

    out_parts = []
    for bi, (kind, lines) in enumerate(blocks):
        if kind == "protected":
            out_parts.append("\n".join(lines))
        else:
            sents = block_sentences[bi]
            if sents:
                out_parts.append(" ".join(sents))
    return "\n\n".join(p for p in out_parts if p != "")


# -------------------------------------------------------------------------- verbosity transform
def _starts_protected(paragraph):
    """True if the paragraph's FIRST line is a heading or a fence/table opener — prefixing
    filler text directly onto that line would corrupt the markup (`Furthermore, # Heading` is
    no longer a heading; `Furthermore, \\`\\`\\`python` is no longer a fence open)."""
    first_line = paragraph.split("\n", 1)[0]
    return bool(_HEADING_RE.match(first_line) or _FENCE_LINE_RE.match(first_line)
                or _TABLE_ROW_RE.match(first_line))


def verbosity_text(text, seed=38):
    """Original -> ~3x length copy (whitespace-token ratio ~2.5-3.5x): the original paragraphs,
    then two more seeded-filler duplicate passes over them (1 + 2 = 3x paragraph count). The
    filler is PREPENDED to a plain paragraph's own first line, but for a paragraph starting
    with a heading/fence/table line, the filler becomes its OWN paragraph immediately before
    it instead — the heading/fence/table marker is never pushed off column 0."""
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()] or [text]
    rng = random.Random(seed)
    out = list(paras)
    for _ in range(2):
        for p in paras:
            filler = rng.choice(_FILLERS)
            if _starts_protected(p):
                out.append(filler.strip() + "\n\n" + p)
            else:
                out.append(filler + p)
    return "\n\n".join(out)


# ------------------------------------------------------------------------------ pair assembly
def _balanced_flags(n, rng):
    """n//2 True + the remainder False, order shuffled by `rng` — exactly balanced A/B
    placement within a group of n pairs, still seed-dependent (not a fixed alternation)."""
    half = n // 2
    flags = [True] * half + [False] * (n - half)
    rng.shuffle(flags)
    return flags


def build_anchor_pairs(rows, seed=38):
    """30 anchor pairs (10 `degrade`, 10 `verbosity`, 10 `identity`) drawn from CONVERGED `rows`
    (each a generation row carrying `id`, `model`, `content`, `converged`), seeded by `seed`.

    Raises ValueError if fewer than 30 converged rows are available (the anchor set is fixed
    size; silently shrinking it would change the reliability gate's statistical power without
    anyone deciding that).
    """
    pool = [r for r in rows if r.get("converged")]
    if len(pool) < N_PER_TYPE * len(ANCHOR_TYPES):
        raise ValueError(
            f"judge_anchors: need >= {N_PER_TYPE * len(ANCHOR_TYPES)} converged rows, "
            f"got {len(pool)}")
    pool_sorted = sorted(pool, key=lambda r: (str(r.get("model")), str(r.get("id"))))
    rng = random.Random(seed)
    chosen = rng.sample(pool_sorted, N_PER_TYPE * len(ANCHOR_TYPES))
    groups = {
        "degrade": chosen[0:N_PER_TYPE],
        "verbosity": chosen[N_PER_TYPE:2 * N_PER_TYPE],
        "identity": chosen[2 * N_PER_TYPE:3 * N_PER_TYPE],
    }
    ab_rng = random.Random(seed + 1)
    pairs = []
    for anchor_type, group_rows in groups.items():
        flags = _balanced_flags(len(group_rows), ab_rng)  # True == original lands in slot A
        for i, (row, orig_is_a) in enumerate(zip(group_rows, flags)):
            item_id = row.get("id")
            model = row.get("model")
            original = row.get("content", "") or ""
            if anchor_type == "degrade":
                transformed = degrade_text(original, seed=seed + i)
                expected_slot = "A" if orig_is_a else "B"  # original (undegraded) wins
            elif anchor_type == "verbosity":
                transformed = verbosity_text(original, seed=seed + i)
                expected_slot = "A" if orig_is_a else "B"  # shorter (original) preferred
            else:  # identity
                transformed = original
                expected_slot = "tie"
            orig_key = f"{model}::{item_id}::orig"
            xform_key = f"{model}::{item_id}::{anchor_type}"
            if orig_is_a:
                a_text, b_text, a_key, b_key = original, transformed, orig_key, xform_key
            else:
                a_text, b_text, a_key, b_key = transformed, original, xform_key, orig_key
            pairs.append({
                "pair_id": f"anchor-{anchor_type}-{i:02d}",
                "anchor_type": anchor_type,
                "item_id": item_id,
                "a_key": a_key,
                "b_key": b_key,
                "a_text": a_text,
                "b_text": b_text,
                "expected": expected_slot,
            })
    return pairs


def write_pairs(pairs, path):
    """Append-free JSONL dump (one full rebuild — the anchor set is small and deterministic,
    so there is no resume concern here, unlike verdicts.jsonl)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Build the M38 judge-panel anchor pairs.")
    ap.add_argument("--models", required=True, nargs="+")
    ap.add_argument("--tune", default="m38")
    ap.add_argument("--results-dir", default=RESULTS)
    ap.add_argument("--seed", type=int, default=38)
    ap.add_argument("--out", default=os.path.join(RESULTS, "judge_c_v1", "pairs.jsonl"))
    args = ap.parse_args(argv)

    rows = load_converged_rows(args.models, tune=args.tune, results_dir=args.results_dir)
    pairs = build_anchor_pairs(rows, seed=args.seed)
    write_pairs(pairs, args.out)
    print(f"[judge_anchors] wrote {len(pairs)} anchor pairs -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
