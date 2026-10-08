"""M61 reference-contact detector and strict-report exclusion for audited agent rows."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit


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
                                              'path', 'sha256', 'bytes', 'prompt_sha256', 'auditor',
                                              'auditor_version'))


def needs_web_audit(row):
    """Recognize audited scaffolds and evidence even on rows with a legacy label."""
    return (str(row.get('scaffold', '')).startswith('opencode-v2-web') or any(
        key in row for key in ('web_fetches', 'net_shell', 'web_denied', 'subagent_calls',
                               'answer_key_contact', 'answer_key_evidence',
                               'web_audit_error', 'web_audit_incomplete', 'audit_error')))


WEB_REPORT_REFUSAL = ('web-audit rows require answer_key.report_rows with the leg audit sidecar '
                      'for exclusions and separate web-contact counts; this reporter cannot '
                      'preserve those audit/session semantics')


def load_audits(path):
    if path is None or not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def deny_patterns_for(urls):
    """Stable P202 URL/repository prefixes, retaining fetched and canonical casing."""
    patterns = []
    for url in urls:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
            raise ValueError('deny URL must be HTTP(S) with a host')
        patterns.append(url)
        # URL hosts are case insensitive; paths ordinarily are not.
        for host in dict.fromkeys((parsed.netloc, parsed.netloc.lower())):
            clean = urlunsplit((parsed.scheme, host, parsed.path, '', ''))
            patterns.append(clean)
            parts = parsed.path.strip('/').split('/')
            if parsed.hostname in ('github.com', 'gitlab.com', 'raw.githubusercontent.com') and len(parts) >= 2:
                owner_repo = '/'.join(parts[:2]).removesuffix('.git')
                page_host = 'github.com' if parsed.hostname == 'raw.githubusercontent.com' else host
                for repo in dict.fromkeys((owner_repo, owner_repo.lower())):
                    patterns.append(f'https://{host}/{repo}/*')
                    patterns.append(f'https://{page_host}/{repo}/*')
                    patterns.append(f'https://raw.githubusercontent.com/{repo}/*')
            else:
                parent = parsed.path.rsplit('/', 1)[0] + '/'
                patterns.append(urlunsplit((parsed.scheme, host, parent + '*', '', '')))
    return list(dict.fromkeys(patterns))


def item_key(row):
    """One model/item/sample in one leg; callers must not pool independent legs."""
    return row.get('model'), row['id'], row.get('sample', 0)


def audit_states(rows, *, audit_sidecar=None, prompt_sha256=None):
    """Resolve current audit labels once for scoring, resume and runner decisions."""
    if prompt_sha256 is None:
        prompt_sha256 = hashlib.sha256(
            (Path(__file__).resolve().parents[1] / 'web_audit_prompt.md').read_bytes()).hexdigest()
    audits = {audit_record_key(record)[:-1]: record for record in load_audits(audit_sidecar)}
    states = []
    for row in rows:
        labels, urls = [], []
        incomplete = bool(row.get('web_audit_incomplete') or row.get('web_audit_error') or row.get('audit_error'))
        contact_sources = {e['source'] for e in row.get('answer_key_evidence', [])
                           if e.get('flag') and e.get('source')}
        forced = bool(row.get('answer_key_contact') or incomplete)
        unknown_source = incomplete or (row.get('answer_key_contact') and not contact_sources)
        for kind, index, entry in web_entries(row):
            key = audit_record_key({'row_id': row['id'], 'sample': row.get('sample', 0),
                                    'session_id': row.get('session_id'), 'kind': kind, 'index': index,
                                    'path': entry.get('path'), 'sha256': entry.get('sha256'),
                                    'bytes': entry.get('bytes'), 'prompt_sha256': prompt_sha256,
                                    'auditor': 'codex:gpt-6-astra'})[:-1]
            audit = audits.get(key, {})
            label = audit.get('label', 'unclear')
            if label in ('unclear', 'audit_error'):
                resolution = audit.get('operator_label')
                reason = audit.get('operator_reason')
                if (resolution in ('docs', 'generic', 'partial', 'solution', 'tests')
                        and isinstance(reason, str) and reason.strip()
                        and reason.splitlines() == [reason]):
                    label = resolution
            labels.append(label)
            contact_source = entry.get('url') in contact_sources or entry.get('command') in contact_sources
            if unknown_source or contact_source or label not in ('docs', 'generic', 'partial', 'tests'):
                if entry.get('url'):
                    urls.append(entry['url'])
                urls.extend(re.findall(r"https?://[^\s\"'<>]+", entry.get('command', ''), re.I))
        if forced:
            for evidence in row.get('answer_key_evidence', []):
                if evidence.get('flag'):
                    urls.extend(re.findall(r"https?://[^\s\"'<>]+", evidence.get('source', ''), re.I))
        states.append({'row': row, 'labels': labels, 'urls': list(dict.fromkeys(urls)),
                       'cheat': forced or any(label not in ('docs', 'generic', 'partial', 'tests')
                                              for label in labels)})
    return states


def report_rows(rows, *, audit_sidecar=None, prompt_sha256=None) -> dict:
    """Score one leg: latest non-cheat per item; exhausted cheating is a strict FAIL.

    Pending cheats remain unscored until re-run. Counts describe all attempts; scored_rows
    are copies and never rewrite the append-only evidence. Never pool independent legs.
    """
    states = audit_states(rows, audit_sidecar=audit_sidecar, prompt_sha256=prompt_sha256)
    groups, per_model = {}, {}
    for state in states:
        row = state['row']
        groups.setdefault(item_key(row), []).append(state)
        counts = per_model.setdefault(row.get('model'), dict(cheat_attempts=0, reruns=0,
                                                           unresolved=0, partial_lookups=0))
        counts['cheat_attempts'] += int(state['cheat'])
        counts['reruns'] += int(bool(row.get('rerun_index', 0)))
        counts['partial_lookups'] += state['labels'].count('partial')
    scored = []
    for attempts in groups.values():
        clean = [s['row'] for s in attempts if not s['cheat']]
        latest = attempts[-1]['row']
        if clean:
            chosen = dict(clean[-1])
        elif latest.get('rerun_index', 0) == 2:
            chosen = dict(latest, passed=False, acc=0, cheat_unresolved=True, skipped=False)
            per_model[latest.get('model')]['unresolved'] += 1
        else:
            continue
        if not chosen.get('skipped'):
            scored.append(chosen)
    items, scores = {}, []
    for row in scored:
        converged = not row.get('nonconv_kind') and row.get('stop_reason') in (None, 'completed')
        score = int(row.get('passed') is True and converged)
        items.setdefault(row['id'], []).append(score)
        scores.append(score)
    return {'acc_strict': sum(scores) / len(scores) if scores else None,
            'strict_n': len(scored), 'strict_items': items, 'scored_rows': scored,
            'per_model': per_model,
            'flagged: web contact': sum(s['cheat'] for s in states),
            'web contact: tests': sum('tests' in s['labels'] for s in states),
            'web contact: partial': sum(s['labels'].count('partial') for s in states),
            'flagged: answer-key contact': sum(bool(s['row'].get('answer_key_contact')) for s in states)}
