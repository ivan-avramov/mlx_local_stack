"""
Build-time inliner for OWU profile filters.

OWU functions are single-file Python blobs; they cannot import this
package's modules at runtime. Profile filters keep a marker block that
this module replaces with rendered constants from `_family_defaults.py`
before the filter source is uploaded.

Usage:

    from _splicer import inline_family_defaults
    payload = inline_family_defaults(open("profile_casual.py").read())
    requests.post(..., json={"content": payload, ...})

The marker syntax inside a profile filter is:

    # >>> FAMILY_DEFAULTS
    _FAMILY_DETECTION = []
    # <<< FAMILY_DEFAULTS

Everything from the opening marker line through the closing marker line
(inclusive) is replaced. The on-disk placeholder is intentionally an
empty list so that an unspliced upload fails fast at family detection
rather than silently routing requests with stale rules.
"""

from __future__ import annotations

import re

from _family_defaults import FAMILY_DETECTION

_BEGIN = "# >>> FAMILY_DEFAULTS"
_END = "# <<< FAMILY_DEFAULTS"

_BLOCK_PATTERN = re.compile(
    r"# >>> FAMILY_DEFAULTS\b.*?# <<< FAMILY_DEFAULTS[^\n]*",
    re.DOTALL,
)


def _render_block() -> str:
    lines = [
        "# >>> FAMILY_DEFAULTS — auto-inlined by openwebui-init/_splicer.py",
        "# Edit openwebui-init/_family_defaults.py to change family routing.",
        "_FAMILY_DETECTION = [",
    ]
    for substring, family_id in FAMILY_DETECTION:
        lines.append(f"    ({substring!r}, {family_id!r}),")
    lines.append("]")
    lines.append("# <<< FAMILY_DEFAULTS")
    return "\n".join(lines)


def inline_family_defaults(source: str) -> str:
    if _BEGIN not in source or _END not in source:
        raise ValueError(
            f"Source is missing FAMILY_DEFAULTS markers "
            f"({_BEGIN!r} ... {_END!r}). Splicer cannot run."
        )
    rendered = _render_block()
    spliced, n = _BLOCK_PATTERN.subn(rendered, source, count=1)
    if n != 1:
        raise ValueError(
            "FAMILY_DEFAULTS markers found but block could not be replaced. "
            "Check the closing marker appears after the opening marker."
        )
    return spliced
