#!/usr/bin/env python3
"""P201 post-leg blind web audit. Rows stay immutable; decisions are append-only."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from bench import answer_key, paths
from bench.opencode_common import _scrub_pii

PROMPT = Path(__file__).with_name('web_audit_prompt.md')
AUDITOR = 'codex:gpt-6-astra'
LABELS = ('docs', 'generic', 'solution', 'tests', 'unclear')


def parse_answer(text: str) -> dict:
    """Reject duplicate keys, extra material, multi-label and multi-line answers."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        result = json.loads(text, object_pairs_hook=unique)
        if (not isinstance(result, dict) or set(result) != {'label', 'reason'}
                or result['label'] not in LABELS
                or not isinstance(result['reason'], str) or not result['reason'].strip()
                or result['reason'].splitlines() != [result['reason']]):
            raise ValueError('invalid answer schema')
        return result
    except (ValueError, TypeError):
        return {'label': 'unclear', 'reason': 'Malformed auditor answer.'}


def codex_auditor(prompt: str, *, timeout: float = 180) -> str:
    """Prompt travels only on STDIN; subprocess timeout terminates a failed call."""
    root = paths.stack_workdir() / 'm61/tmp'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='web-auditor-', dir=root) as directory:
        output = Path(directory) / 'answer.json'
        subprocess.run(['codex', 'exec', '-m', 'gpt-6-astra', '-s', 'read-only',
                        '--skip-git-repo-check', '-o', str(output), '-'],
                       input=prompt, text=True, capture_output=True, check=True, timeout=timeout,
                       cwd=directory)
        return output.read_text(encoding='utf-8')


def _go_code(text: str) -> str:
    # Omit strings and comments before looking for declarations.
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|`[^`]*`', '', text)


def public_identifiers(item_dir: Path, language: str) -> list[str]:
    """Read solution stubs only, excluding tests and .meta references."""
    extension = {'python': '.py', 'go': '.go'}.get(language)
    if extension is None:
        return []
    config = item_dir / '.meta/config.json'
    if config.is_file():
        files = [item_dir / name for name in json.loads(config.read_text())['files']['solution']]
    else:
        files = [p for p in sorted(item_dir.glob('*' + extension))
                 if not p.stem.startswith('test_') and not p.stem.endswith('_test')]
    if not files:
        raise ValueError('missing solution stub')
    names = set()
    for path in files:
        if not path.resolve().is_relative_to(item_dir.resolve()) or '.meta' in path.relative_to(item_dir).parts:
            raise ValueError('invalid solution stub path')
        text = path.read_text(encoding='utf-8')
        if language == 'python':
            names.update(node.name for node in ast.parse(text).body
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                         and not node.name.startswith('_'))
        else:
            code = _go_code(text)
            names.update(re.findall(r'(?m)^\s*func\s+(?:\([^\n]*?\)\s*)?([A-Z]\w*)\b', code))
            names.update(re.findall(r'(?m)^\s*type\s+([A-Z]\w*)\b', code))
            for group in re.findall(r'(?ms)^\s*type\s*\((.*?)^\s*\)', code):
                names.update(re.findall(r'(?m)^\s*([A-Z]\w*)\s+', group))
    return sorted(names)


def preflag(text: str, language: str, identifiers: list[str]) -> bool:
    """Priority heuristic: language code plus three distinct whole identifiers."""
    if language == 'go':
        in_language = bool(re.search(r'(?m)^\s*(package\s+\w+|func\s+|type\s+)', _go_code(text)))
    elif language == 'python':
        candidates = [text] + re.findall(r'```(?:python|py)?\s*\n(.*?)```', text, re.S)
        in_language = False
        for candidate in candidates:
            try:
                tree = ast.parse(candidate)
            except SyntaxError:
                continue
            if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                     ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
                in_language = True
                break
    else:
        in_language = False
    return in_language and sum(bool(re.search(r'\b' + re.escape(name) + r'\b', text))
                               for name in set(identifiers)) >= 3


def _read_evidence(entry: dict) -> str:
    value = entry['path']
    prefix = '$STACK_WORKDIR/'
    if not value.startswith(prefix):
        raise ValueError('nonportable evidence path')
    root = paths.stack_workdir().resolve()
    path = (root / value[len(prefix):]).resolve()
    if not path.is_relative_to(root / 'opencode_transcripts'):
        raise ValueError('evidence outside transcript area')
    data = path.read_bytes()
    if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise ValueError('evidence hash or byte count mismatch')
    return data.decode('utf-8')


def audit_rows(rows_path, *, polyglot_root=None, auditor=None, prompt_file=PROMPT) -> Path:
    """One call per evidence entry; unchanged prompt/evidence keys are never re-audited."""
    rows_path = Path(rows_path)
    sidecar = Path(str(rows_path) + '.webaudit.jsonl')
    refusal = paths.confine_path(sidecar, what='audit sidecar')
    if refusal:
        raise ValueError(refusal)
    root = Path(polyglot_root) if polyglot_root is not None else Path(
        os.environ.get('POLYGLOT_DIR') or paths.stack_workdir() / 'polyglot-benchmark')
    template = Path(prompt_file).read_bytes()
    prompt_sha = hashlib.sha256(template).hexdigest()
    existing = answer_key.load_audits(sidecar)
    done = {answer_key.audit_record_key(record) for record in existing}
    call = auditor if auditor is not None else codex_auditor
    pending = []
    for line in rows_path.read_text().splitlines():
        row = json.loads(line)
        for kind, index, entry in answer_key.web_entries(row):
            record = {'row_id': row['id'], 'sample': row.get('sample', 0),
                      'session_id': row.get('session_id'), 'kind': kind, 'index': index,
                      'path': entry.get('path'), 'sha256': entry.get('sha256'),
                      'bytes': entry.get('bytes'), 'auditor': AUDITOR, 'prompt_sha256': prompt_sha,
                      'preflag': False}
            key = answer_key.audit_record_key(record)
            if key in done:
                continue
            done.add(key)
            try:
                language, name = row['id'].split('/', 1)
                if '/' in name or name in ('.', '..') or language in ('.', '..'):
                    raise ValueError('invalid item id')
                identifiers = public_identifiers(root / language / 'exercises/practice' / name, language)
                text = _read_evidence(entry)
                record['preflag'] = preflag(text, language, identifiers)
                payload = {'item': name, 'language': language, 'public_identifiers': identifiers,
                           'url': entry.get('url'), 'command': entry.get('command'),
                           'status': entry.get('status'), 'text': text[:6000]}
                prompt = template.decode('utf-8') + '\nINPUT_JSON\n' + json.dumps(payload, ensure_ascii=False)
            except (OSError, ValueError, KeyError, TypeError, SyntaxError) as exc:
                record.update(label='audit_error', reason=f'Evidence/stub failure: {type(exc).__name__}.')
                prompt = None
            pending.append((record, prompt))
    # Review likely solutions first; priority never overrides the blind auditor's label.
    pending.sort(key=lambda pair: not pair[0]['preflag'])
    with sidecar.open('a', encoding='utf-8') as stream:
        for record, prompt in pending:
            if prompt is not None:
                try:
                    record.update(parse_answer(call(prompt)))
                except (OSError, subprocess.SubprocessError) as exc:
                    record.update(label='audit_error', reason=f'Auditor failed: {type(exc).__name__}.')
            stream.write(_scrub_pii(json.dumps(record, ensure_ascii=False)) + '\n')
            stream.flush()
    return sidecar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rows', type=Path)
    parser.add_argument('--polyglot-root', type=Path)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    sidecar = audit_rows(args.rows, polyglot_root=args.polyglot_root,
                         auditor=lambda prompt: codex_auditor(prompt, timeout=args.timeout))
    print(sidecar)


if __name__ == '__main__':
    main()
