"""M61 reference-contact detector and strict-report exclusion for audited agent rows."""
from __future__ import annotations

import hashlib
import json
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


def web_entries(row):
    """Yield stable per-list evidence indices, including unresolved legacy shell entries."""
    for kind in ('web_fetches', 'net_shell'):
        for index, entry in enumerate(row.get(kind, [])):
            yield kind, index, entry if isinstance(entry, dict) else {'command': entry}


def audit_record_key(record):
    return tuple(record.get(key) for key in ('row_id', 'sample', 'session_id', 'kind', 'index',
                                              'path', 'sha256', 'bytes', 'prompt_sha256', 'auditor'))


def load_audits(path):
    if path is None or not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def report_rows(rows, *, audit_sidecar=None, prompt_sha256=None) -> dict:
    """Single-session strict scores; unresolved/missing audits fail closed.

    Operator resolutions append the original record with operator_label/operator_reason.
    Only unclear/audit_error decisions can be resolved; solution/contact flags stay excluded.
    """
    if prompt_sha256 is None:
        prompt_sha256 = hashlib.sha256(
            (Path(__file__).resolve().parents[1] / 'web_audit_prompt.md').read_bytes()).hexdigest()
    audits = {audit_record_key(record): record for record in load_audits(audit_sidecar)}
    rows = list(rows)
    eligible, flagged, tests = [], 0, 0
    for row in rows:
        labels = []
        for kind, index, entry in web_entries(row):
            key = audit_record_key({'row_id': row['id'], 'sample': row.get('sample', 0),
                                    'session_id': row.get('session_id'), 'kind': kind, 'index': index,
                                    'path': entry.get('path'), 'sha256': entry.get('sha256'),
                                    'bytes': entry.get('bytes'), 'prompt_sha256': prompt_sha256,
                                    'auditor': 'codex:gpt-6-astra'})
            audit = audits.get(key, {})
            label = audit.get('label', 'unclear')
            if label in ('unclear', 'audit_error'):
                resolution = audit.get('operator_label')
                reason = audit.get('operator_reason')
                if (resolution in ('docs', 'generic', 'solution', 'tests')
                        and isinstance(reason, str) and reason.strip()
                        and reason.splitlines() == [reason]):
                    label = resolution
            labels.append(label)
        exclude = bool(row.get('answer_key_contact')) or any(
            label not in ('docs', 'generic', 'tests') for label in labels)
        flagged += int(exclude)
        tests += int('tests' in labels)
        if not exclude and not row.get('skipped'):
            eligible.append(row)
    items = {}
    for row in eligible:
        converged = not row.get('nonconv_kind') and row.get('stop_reason') in (None, 'completed')
        items.setdefault(row['id'], []).append(int(row.get('passed') is True and converged))
    scores = [sum(values) / len(values) for values in items.values()]
    return {'acc_strict': sum(scores) / len(scores) if scores else None,
            'strict_n': len(eligible), 'strict_items': items,
            'flagged: web contact': flagged, 'web contact: tests': tests,
            'flagged: answer-key contact': sum(bool(r.get('answer_key_contact')) for r in rows)}
