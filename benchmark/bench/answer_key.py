"""M61 reference-contact detector and strict-report exclusion for audited agent rows."""
from __future__ import annotations

from pathlib import Path


def normalize(text: str) -> list[str]:
    """Strip lines; omit blank, short and comment-only lines (including block comments)."""
    lines = []
    block_end = None
    for raw in text.splitlines():
        line = raw.strip()
        if block_end:
            if block_end in line:
                line = line.split(block_end, 1)[1].strip()
                block_end = None
            else:
                continue
        for start, end in (("/*", "*/"), ("<!--", "-->"), ('"""', '"""'), ("'''", "'''")):
            if line.startswith(start):
                rest = line[len(start):]
                if end in rest:
                    line = rest.split(end, 1)[1].strip()
                else:
                    block_end = end
                    line = ""
                break
        if len(line) >= 12 and not line.startswith(("//", "#", "--", ";")):
            lines.append(line)
    return lines


def _overlap(reference: list[str], observed: list[str]) -> tuple[int, int]:
    """Count covered reference positions and the longest contiguous shared line sequence."""
    seen = set(observed)
    matched = sum(line in seen for line in reference)
    previous = [0] * (len(reference) + 1)
    longest = 0
    for line in observed:
        current = [0]
        for i, ref in enumerate(reference):
            length = previous[i] + 1 if line == ref else 0
            current.append(length)
            longest = max(longest, length)
        previous = current
    return matched, longest


def contact(item_dir, texts) -> dict:
    """Check {source, text} records against recursive .meta/{example,exemplar,proof}* files."""
    item = Path(item_dir)
    references = sorted(p for p in (item / '.meta').rglob('*')
                        if p.is_file() and p.name.startswith(('example', 'exemplar', 'proof')))
    observed = [(entry['source'], normalize(entry['text'])) for entry in texts]
    evidence = []
    flag = False
    for path in references:
        reference = normalize(path.read_text(encoding='utf-8', errors='replace'))
        if not reference:
            continue
        for source, lines in observed:
            matched, run = _overlap(reference, lines)
            hit = run >= 5 or matched / len(reference) >= 0.4
            flag |= hit
            if matched:
                evidence.append({'reference': path.relative_to(item).as_posix(), 'source': source,
                                 'matched_lines': matched, 'reference_lines': len(reference),
                                 'run_length': run, 'flag': hit})
    return {'flag': flag, 'evidence': evidence}


def report_rows(rows) -> dict:
    """Single-session strict scores: exclude contact/skip rows, retain failed and DNF rows."""
    rows = list(rows)
    eligible = [r for r in rows if not r.get('answer_key_contact') and not r.get('skipped')]
    items = {}
    for row in eligible:
        converged = not row.get('nonconv_kind') and row.get('stop_reason') in (None, 'completed')
        items.setdefault(row['id'], []).append(int(row.get('passed') is True and converged))
    scores = [sum(values) / len(values) for values in items.values()]
    return {'acc_strict': sum(scores) / len(scores) if scores else None,
            'strict_n': len(eligible), 'strict_items': items,
            'flagged: answer-key contact': sum(bool(r.get('answer_key_contact')) for r in rows)}
