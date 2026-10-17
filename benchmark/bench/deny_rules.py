"""Carrier shell deny rules (generation: they are written into the opencode carrier). Moved verbatim from
`answer_key` by P311-lite so the generation identity does not include the scoring module."""
from __future__ import annotations

import re


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
