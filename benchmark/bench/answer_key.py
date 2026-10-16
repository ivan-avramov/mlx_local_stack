"""M61 reference-contact detector and strict-report exclusion for audited agent rows."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


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


def declared_auditors():
    """C158: the accepted P201 auditors in preference order, each with its version probe. codex gpt-6-astra is the
    pinned auditor; Cursor gpt-5.6-sol-high audits on boxes without codex (operator 2026-10-14). P299: the probe is
    provenance for NEW audits only (`web_audit.audit_rows` records it); scoring never calls it."""
    from web_audit import auditor_version
    from web_audit_cursor import AUDITOR as CURSOR, cursor_version
    return [('codex:gpt-6-astra', auditor_version), (CURSOR, cursor_version)]


LEGACY_INVENTORY = Path(__file__).with_name('legacy_audit_records.json')


def record_digest(record):
    """Canonical sha256 of one sidecar record (sort_keys JSON)."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def legacy_record_digests(inventory=None):
    """C163 review P1: the frozen set of pre-C163 sidecar records (no `context_sha256`) accepted as recorded.
    Any other record without a valid digest is not an audit."""
    path = Path(inventory) if inventory is not None else LEGACY_INVENTORY
    if not path.exists():
        return frozenset()
    return frozenset(json.loads(path.read_text())['records'])


def build_legacy_inventory(results_root):
    """{'records': [digest...]} of every digest-less record in every committed sidecar under results_root."""
    digests = []
    for sidecar in sorted(Path(results_root).rglob('*.webaudit.jsonl')):
        for record in load_audits(sidecar):
            if isinstance(record, dict) and record.get('context_sha256') is None:
                digests.append(record_digest(record))
    return {'records': sorted(set(digests))}


def _context_digest_ok(record):
    digest = record.get('context_sha256')
    if isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest):
        return True
    if digest is not None:
        return False
    # P309 review P1: an operator resolution is a copy of its legacy base plus the operator fields, so it is checked
    # against the inventory without them; accepted_audits still requires the exact genuine predecessor
    base = {k: v for k, v in record.items() if k not in ('operator_label', 'operator_reason')}
    return record_digest(base) in legacy_record_digests()


def _valid_audit(record, auditors):
    """C158/P298: a well-formed record of a declared auditor (allowed label, nonempty single-line reason, nonempty
    version and prompt sha). C163: a valid `context_sha256`, or a grandfathered legacy record (frozen inventory).
    Anything else is not an audit."""
    from web_audit import LABELS
    if not isinstance(record, dict):
        return False
    reason = record.get('reason')
    return (record.get('auditor') in auditors and record.get('label') in (*LABELS, 'audit_error')
            and isinstance(reason, str) and bool(reason.strip()) and reason.splitlines() == [reason]
            and isinstance(record.get('auditor_version'), str) and bool(record['auditor_version'])
            and isinstance(record.get('prompt_sha256'), str) and bool(record['prompt_sha256'])
            and _context_digest_ok(record))


def accepted_audits(records, auditors):
    """{key: record}: the latest well-formed genuine record per key (a retry replaces it); an operator resolution
    applies only on top of a preceding genuine unresolved (`unclear`/`audit_error`) record of the same key and label,
    as the documented procedure appends a copy of that record (C158/P298). Iteration order is sidecar order of the
    LAST write per key, so a later record of the same evidence (e.g. a retry under a newer CLI) follows an older one
    (P299)."""
    out = {}
    for record in records:
        if not _valid_audit(record, auditors):
            continue
        key = audit_record_key(record)
        if 'operator_label' in record or 'operator_reason' in record:
            base = out.get(key)
            op_reason = record.get('operator_reason')
            valid_resolution = (record.get('operator_label') in ('docs', 'generic', 'partial', 'solution', 'tests')
                                and isinstance(op_reason, str) and bool(op_reason.strip())
                                and op_reason.splitlines() == [op_reason])        # C158 review A7
            if (valid_resolution and base is not None and base['label'] in ('unclear', 'audit_error')
                    and record['label'] == base['label']):
                out.pop(key)
                out[key] = {**base, 'operator_label': record.get('operator_label'),
                            'operator_reason': record.get('operator_reason')}
            continue
        out.pop(key, None)
        out[key] = record
    return out


def latest_by_evidence(audits):
    """{(evidence_key, auditor): record}: per evidence and auditor, the latest accepted record whatever its recorded
    `auditor_version` (P299: a recorded audit is valid for the record; the installed CLI version never gates it)."""
    out = {}
    for record in audits.values():
        out[(evidence_key(record), record.get('auditor'))] = record
    return out


EVIDENCE_KEY_FIELDS = ('row_id', 'sample', 'session_id', 'kind', 'index', 'path', 'sha256', 'bytes', 'prompt_sha256',
                       'context_sha256')
CONTEXT_FIELDS = ('url', 'command', 'status')


def context_sha256(entry):
    """C163: digest of the fetch context the auditor is shown besides the content (url, command, status; absent ==
    null). Part of the audit identity, so an edited context never inherits a label."""
    payload = {key: entry.get(key) for key in CONTEXT_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def evidence_key(record):
    """Identity of one audited fetch under one prompt: the row, the tool-list slot, the evidence bytes and the
    fetch context (C163; `context_sha256` is None only on grandfathered legacy records, which apply to the row as
    it is now and are counted as `legacy_audits`)."""
    return tuple(record.get(key) for key in EVIDENCE_KEY_FIELDS)


def legacy_key(key):
    """The evidence key with the context digest removed: how a legacy record (no digest) is matched."""
    return key[:-1] + (None,)


def audit_record_key(record):
    return evidence_key(record) + tuple(record.get(key) for key in ('auditor', 'auditor_version'))


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


class AuditMissing(ValueError):
    """A latest attempt has evidence without a current audit."""


def _strip_url_tail(url):
    url = re.split(r'&&|[|;`)><,\s]|\$\(', url, maxsplit=1)[0]
    url = url.removeprefix('git+').rstrip(")]},;:.'\"")
    # Strip transport refs only after the authority, retaining credential checks.
    return re.sub(r'(https?://[^/]+/[^?#]*)@[^?#]+$', r'\1', url, flags=re.I)


def _source_urls(text):
    return [_strip_url_tail(url) for url in re.findall(
        r"https?://(?:(?!&&|\$\()[^\s\"'<>|;`,)])+", text, re.I)]


def deny_patterns_for(urls, *, dropped_urls=None):
    """Bound URL-derived wildcards to a repository or a concrete page/path.

    opencode's '?' is a wildcard with no literal escape. Do not emit root '?*'
    or bare repository-prefix '*' rules: both also match sibling repositories.
    """
    patterns = []
    for url in urls:
        try:
            parsed = urlsplit(_strip_url_tail(url))
            parts = [part for part in parsed.path.split('/') if part]
            host = (parsed.hostname or '').lower()
            canonical = host.removeprefix('www.')
            port = parsed.port
            netloc = host if port is None or (parsed.scheme.lower(), port) in (
                ('https', 443), ('http', 80)) else f'{host}:{port}'
            domains = tuple(dict.fromkeys((parsed.netloc, netloc, netloc.removeprefix('www.'))))
            repo_host = canonical in ('github.com', 'gitlab.com', 'raw.githubusercontent.com')
            if (parsed.scheme.lower() not in ('http', 'https') or not host
                    or parsed.username or parsed.password or not parts
                    or '*' in url or any(c in unquote(parsed.netloc + parsed.path) for c in '*?')
                    or (repo_host and len(parts) < 2)):
                raise ValueError('unsafe or unbounded deny URL')
        except (ValueError, TypeError, AttributeError):
            if dropped_urls is not None:
                dropped_urls.append(url)
            continue
        if repo_host:
            # GitLab uses /-/ before routes; everything before it is the project,
            # including nested groups. Plain project/clone URLs keep the full path.
            project_parts = parts[:2]
            if canonical == 'gitlab.com':
                project_parts = parts[:parts.index('-')] if '-' in parts else parts
            project = '/'.join(project_parts).removesuffix('.git')
            if len(project_parts) < 2 or not project.split('/')[-1]:
                if dropped_urls is not None:
                    dropped_urls.append(url)
                continue
            for variant in dict.fromkeys((project, project.lower())):
                domain = 'gitlab.com' if canonical == 'gitlab.com' else 'github.com'
                bases = [f'{domain}/{variant}', f'{domain}:{variant}']
                bases.extend(f'{name}/{variant}' for name in domains)
                for base in bases:
                    patterns.extend('*' + base + suffix for suffix in ('', '/*', '.git*', '#*'))
                if canonical != 'gitlab.com':
                    patterns.append(f'*raw.githubusercontent.com/{variant}/*')
                    patterns.extend(f'*api.github.com/repos/{variant}' + suffix for suffix in ('', '/*', '.git*', '#*'))
                    patterns.extend(f'*cdn.jsdelivr.net/gh/{variant}' + suffix for suffix in ('', '/*', '.git*', '@*', '#*'))
        else:
            for domain in domains:
                for path in dict.fromkeys((parsed.path, parsed.path.lower())):
                    base = '*' + domain + path.rstrip('/')
                    patterns.extend(base + suffix for suffix in ('', '/', '#*', '/#*'))
                    if len(parts) >= 3:
                        patterns.append(base + '/*')
    return list(dict.fromkeys(patterns))


def shell_deny_patterns(patterns):
    """Match whole shell nodes; keep exact URLs bounded at token ends."""
    result = []
    boundaries = (' ', '\t', '\n', '"', "'", ';', '|', '&', ')', '>', '<', ',', '`', '$(', '@')
    for pattern in patterns:
        pattern = '*' + pattern.lstrip('*')
        result.append(pattern)
        if not pattern.endswith('*'):
            result.extend(pattern + boundary + '*' for boundary in boundaries)
        github = re.fullmatch(r'\*github\.com/([^/]+)/([^/*?#]+)', pattern)
        if github:
            project = '/'.join(github.groups())
            for command in (f'*gh repo clone {project}', f'*gh api repos/{project}'):
                result.append(command)
                result.extend(command + boundary + '*' for boundary in (*boundaries, '/'))
    return list(dict.fromkeys(result))


def rerun_plan(state):
    """Share operator-review and deny decisions between reporting and execution."""
    dropped = []
    patterns = deny_patterns_for(state['urls'], dropped_urls=dropped)
    needs_operator = bool(state['unknown_source'] or dropped or not patterns)
    combined = list(dict.fromkeys(state['row'].get('extra_deny', []) + patterns))
    return {'extra_deny': [] if state['unknown_source'] else combined,
            'dropped_urls': dropped, 'needs_operator': needs_operator}


def require_audits(states):
    for state in states:
        if 'missing' in state['labels']:
            raise AuditMissing('audit first: missing/stale audit for ' + state['row']['id'])


def item_key(row):
    """One model/item/sample in one leg; callers must not pool independent legs."""
    return row.get('model'), row['id'], row.get('sample', 0)


def audit_states(rows, *, audit_sidecar=None, prompt_sha256=None):
    """Resolve current audit labels once for scoring, resume and runner decisions."""
    if prompt_sha256 is None:
        prompt_sha256 = hashlib.sha256(
            (Path(__file__).resolve().parents[1] / 'web_audit_prompt.md').read_bytes()).hexdigest()
    from web_audit import LABELS
    rows = list(rows)
    auditors = [name for name, _ in declared_auditors()]     # preference order; P299: no version probe in scoring
    audits = latest_by_evidence(accepted_audits(load_audits(audit_sidecar), set(auditors)))
    states = []
    for row in rows:
        labels, urls = [], []
        legacy = 0
        incomplete = bool(row.get('web_audit_incomplete') or row.get('web_audit_error') or row.get('audit_error'))
        contact_evidence = [e for e in row.get('answer_key_evidence', []) if e.get('flag')]
        contact_sources = {(e.get('source') or '') for e in contact_evidence}
        forced = bool(row.get('answer_key_contact') or incomplete)
        unknown_source = incomplete or bool(row.get('answer_key_contact') and (
            not contact_sources or any(not re.search(r'https?://', source, re.I) for source in contact_sources)))
        for kind, index, entry in web_entries(row):
            audit = {}
            evidence = evidence_key({'row_id': row['id'], 'sample': row.get('sample', 0),
                                     'session_id': row.get('session_id'), 'kind': kind, 'index': index,
                                     'path': entry.get('path'), 'sha256': entry.get('sha256'),
                                     'bytes': entry.get('bytes'), 'prompt_sha256': prompt_sha256,
                                     'context_sha256': context_sha256(entry)})
            for name in auditors:     # declared order: the first auditor with a recorded audit wins
                if (evidence, name) in audits:
                    audit = audits[(evidence, name)]
                    break
                if (legacy_key(evidence), name) in audits:      # C163: a pre-digest record, counted below
                    audit = audits[(legacy_key(evidence), name)]
                    legacy += 1
                    break
            label = audit.get('label', 'missing')
            if label not in (*LABELS, 'audit_error'):
                label = 'missing'
            if label in ('unclear', 'audit_error'):
                resolution = audit.get('operator_label')
                reason = audit.get('operator_reason')
                if (resolution in ('docs', 'generic', 'partial', 'solution', 'tests')
                        and isinstance(reason, str) and reason.strip()
                        and reason.splitlines() == [reason]):
                    label = resolution
            labels.append(label)
            contact_source = entry.get('url') in contact_sources or entry.get('command') in contact_sources
            if contact_source or label in ('solution', 'unclear', 'audit_error'):
                sources = ([entry['url']] if entry.get('url') else [])
                sources.extend(_source_urls(entry.get('command', '')))
                unknown_source |= not sources
                urls.extend(sources)
        if forced:
            for evidence in row.get('answer_key_evidence', []):
                if evidence.get('flag'):
                    urls.extend(_source_urls(evidence.get('source') or ''))
        states.append({'row': row, 'labels': labels, 'legacy_audits': legacy,
                       'urls': [] if unknown_source else list(dict.fromkeys(_strip_url_tail(url) for url in urls)),
                       'unknown_source': bool(unknown_source),
                       'rerun_eligible': str(row.get('scaffold', '')).startswith('opencode-v2-web'),
                       'cheat': forced or any(label in ('solution', 'unclear', 'audit_error')
                                              for label in labels)})
    return states


def report_rows(rows, *, audit_sidecar=None, prompt_sha256=None) -> dict:
    """Score one leg: latest non-cheat per item; exhausted cheating is a strict FAIL.

    Missing audits and operator-review items are provisional. Non-web cheats count as
    cheat_review. Counts describe all attempts; scored_rows are copies and never rewrite
    the append-only evidence. Never pool independent legs.
    """
    states = audit_states(rows, audit_sidecar=audit_sidecar, prompt_sha256=prompt_sha256)
    groups, per_model = {}, {}
    for state in states:
        row = state['row']
        groups.setdefault(item_key(row), []).append(state)
        counts = per_model.setdefault(row.get('model'), dict(cheat_attempts=0, reruns=0,
                                                           unresolved=0, partial_lookups=0,
                                                           pending_reruns=0, missing_audits=0,
                                                           cheat_review=0, legacy_audits=0, provisional=False))
        counts['legacy_audits'] += state['legacy_audits']
        counts['cheat_attempts'] += int(state['cheat'])
        counts['reruns'] += int(bool(row.get('rerun_index', 0)))
        counts['partial_lookups'] += state['labels'].count('partial')
        counts['missing_audits'] += state['labels'].count('missing')
        counts['provisional'] |= 'missing' in state['labels']
    scored = []
    for attempts in groups.values():
        latest_state = attempts[-1]
        latest = latest_state['row']
        counts = per_model[latest.get('model')]
        if latest_state['cheat'] and (not latest_state['rerun_eligible']
                                      or rerun_plan(latest_state)['needs_operator']):
            counts['cheat_review'] += 1
            counts['provisional'] = True
            continue
        missing = latest_state['labels'].count('missing')
        if missing:
            counts['provisional'] = True
            continue
        if latest_state['cheat']:
            if latest.get('rerun_index', 0) < 2:
                counts['pending_reruns'] += 1
                counts['provisional'] = True
        clean = [s['row'] for s in attempts if not s['cheat'] and 'missing' not in s['labels']]
        if clean:
            chosen = dict(clean[-1])
        elif latest.get('rerun_index', 0) == 2:
            chosen = dict(latest, passed=False, acc=0, cheat_unresolved=True, skipped=False)
            counts['unresolved'] += 1
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
            'provisional': any(c['provisional'] for c in per_model.values()),
            **{key: sum(c[key] for c in per_model.values())
               for key in ('missing_audits', 'pending_reruns', 'cheat_review', 'legacy_audits')},
            'flagged: web contact': sum(s['cheat'] for s in states),
            'web contact: tests': sum('tests' in s['labels'] for s in states),
            'web contact: partial': sum(s['labels'].count('partial') for s in states),
            'flagged: answer-key contact': sum(bool(s['row'].get('answer_key_contact')) for s in states)}
