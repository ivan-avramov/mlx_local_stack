"""B2 (P426) credential classifier and secret gate primitives (spec 11.3, 16.2, C238; shared with the s9 harvest).

A credential VALUE lives only in memory, in the dict `credential_values` returns: it is never printed, logged, hashed or written
by this module, and no `Finding` or exception carries one (a finding is `(kind, start, end)`; kinds name a key, never a value).
The arm-equality receipt uses only `is_credential_key` (key names); the harvest uses the rest."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CREDENTIAL_PATTERN = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|AUTH", re.IGNORECASE)
# The committed non-secret allowlist: names that match the pattern but are configuration the stack defines. An `MLX_*` key is
# allowed by exact name only (`MLX_API_KEY` and `MLX_VLM_SERVER_API_KEY` ARE credentials); `KV_*` / `TQ_*` by prefix unless the
# rest of the name is itself a credential word.
NON_SECRET_KEYS = frozenset({
    "TOKENIZERS_PARALLELISM", "MLX_VLM_THINKING_START_TOKEN", "MLX_VLM_THINKING_END_TOKEN", "MLX_VLM_MAX_TOKENS",
    "MLX_VLM_TOKEN_QUEUE_TIMEOUT"})
# The `KV_*` / `TQ_*` names the stack defines, by exact name (found in `src/mlx-vlm`'s server `cli.py` / `runtime_config.py` /
# `generation.py` / `apc.py` / `turboquant.py` and the P369 `kvmanifest.py`): every other `KV_` / `TQ_` name that matches the
# credential pattern (`KV_API_KEY`, `TQ_TOKEN`, `TQ_KEY_BITS`) is a credential.
STACK_DEFINED_KV_TQ_NAMES = frozenset({
    "KV_BITS", "KV_GROUP_SIZE", "KV_KEY_BITS", "KV_VALUE_BITS", "KV_KEY_SCHEME", "KV_VALUE_SCHEME", "KV_QUANT_SCHEME",
    "KV_PREALLOC_TOKENS", "TQ_KV_QUANT_MODE", "TQ_PREFILL_IMPL", "TQ_FUSED_PREFILL", "TQ_DECODE_2PASS_LEGACY"})
MIN_EXACT_LEN = 12
PLACEHOLDERS = frozenset({"true", "false", "none", "null", "0", "1", "", "changeme"})
TOKEN_FILES = (".hftoken", ".cache/huggingface/token")        # relative to the home directory; the whole content is the value


class SecretsError(Exception):
    """A source that exists could not be read (the harvest refuses). The message names a source, never a value."""


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int


def is_credential_key(name) -> bool:
    name = str(name)
    if not CREDENTIAL_PATTERN.search(name):
        return False
    upper = name.upper()
    return not (upper in NON_SECRET_KEYS or upper in STACK_DEFINED_KV_TQ_NAMES)


def usable(value) -> bool:
    """True when `value` may be matched exactly: at least 12 characters and not a placeholder."""
    return isinstance(value, str) and len(value) >= MIN_EXACT_LEN and value.strip().lower() not in PLACEHOLDERS


# -- sources (in memory only)
def _expands(value: str) -> bool:
    """True when a shell would expand `value`: a `$` or a backtick outside single quotes and not backslash-escaped (inside double
    quotes both still expand). A trailing `# comment` is not scanned."""
    single = double = False
    i = 0
    while i < len(value):
        c = value[i]
        if single:
            single = c != "'"
        elif c == "\\":
            i += 1                                   # the next character is literal
        elif c == "'" and not double:
            single = True
        elif c == '"':
            double = not double
        elif c in "$`":
            return True
        elif c == "#" and not double and (i == 0 or value[i - 1].isspace()):
            return False
        i += 1
    return False


def parse_assignments(text: str) -> dict:
    """`[export] KEY=value` lines of a shell-style file (comments and anything else skipped): the value is the first token of
    `shlex.split(value, comments=True)` (quotes removed, a trailing `# comment` dropped). A credential-keyed line that does not
    parse raises `SecretsError` (naming the key, never the value); any other unparseable line is skipped."""
    import shlex
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, eq, value = line.partition("=")
        key = key.strip()
        if not eq or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if is_credential_key(key) and _expands(value):
            raise SecretsError(f"credential-keyed assignment {key} contains an unquoted `$` or backtick "
                               "(the shell would expand it: the value cannot be matched exactly)")
        try:
            tokens = shlex.split(value, comments=True)
        except ValueError:
            if is_credential_key(key):
                raise SecretsError(f"credential-keyed assignment {key} cannot be parsed (shell quoting)") from None
            continue
        out[key] = tokens[0] if tokens else ""
    return out


def read_source(path, label):
    """The text of an existing file, None when it is absent; an existing file that cannot be read is a `SecretsError`."""
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return None
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise SecretsError(f"credential source {label} exists but cannot be read ({type(exc).__name__})") from None


def credential_values(*, home, config_path, environ, env_files=()) -> dict:
    """{source-qualified key: value} of every usable credential value: credential-keyed assignments of the machine config, of
    each `env_files` entry (`<WT>/.env`) and of `environ`, plus the whole content of the token files under `home`. IN MEMORY
    ONLY; the caller must never print, log or hash the result."""
    found = {}

    def add(label, key, value):
        if usable(value):
            found[f"{label}:{key}"] = value
    for label, path in [("config", config_path)] + [(f"env_file{i}", p) for i, p in enumerate(env_files)]:
        text = read_source(path, label)
        for key, value in (parse_assignments(text) if text is not None else {}).items():
            if is_credential_key(key):
                add(label, key, value)
    for key, value in (environ or {}).items():
        if is_credential_key(key):
            add("environ", key, value)
    for rel in TOKEN_FILES:
        text = read_source(Path(home) / rel, f"file:{rel}")
        if text is not None:
            add("file", rel, text.strip())
    return found


def absent_sources(*, home, config_path, env_files=()) -> list:
    """Labels of the listed files that do not exist (recorded as absent, not an error)."""
    absent = []
    for label, path in [("config", config_path)] + [(f"env_file{i}", p) for i, p in enumerate(env_files)] + \
            [(f"file:{rel}", Path(home) / rel) for rel in TOKEN_FILES]:
        if not Path(path).exists() and not Path(path).is_symlink():
            absent.append(label)
    return absent


# -- scans
B = r"(?<![A-Za-z0-9_])"
FORMATS = (
    ("hf_token", re.compile(B + r"hf_[A-Za-z0-9]{20,}")),
    ("sk_key", re.compile(B + r"sk-[A-Za-z0-9_-]{16,}")),
    ("github_token", re.compile(B + r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("github_pat", re.compile(B + r"github_pat_[A-Za-z0-9_]{20,}")),
    ("aws_key_id", re.compile(B + r"AKIA[0-9A-Z]{16}(?![A-Za-z0-9])")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("bearer", re.compile(r"""Authorization["']?\s*[:=]\s*["']?Bearer\s+[A-Za-z0-9._~+/=-]{6,}""", re.IGNORECASE)),
)


def scan(text: str) -> list:
    """Credential-format findings of `text`, in order of position. A finding carries kind and offsets only."""
    hits = [Finding(kind, m.start(), m.end()) for kind, rx in FORMATS for m in rx.finditer(text)]
    return sorted(hits, key=lambda f: (f.start, f.end, f.kind))


def exact_hits(text: str, values: dict) -> list:
    """Occurrences of any usable value of `values` ({key: value}) in `text`; the finding's kind is `exact:<key>`."""
    hits = []
    for key, value in values.items():
        if not usable(value):
            continue
        at = text.find(value)
        while at != -1:
            hits.append(Finding(f"exact:{key}", at, at + len(value)))
            at = text.find(value, at + 1)
    return sorted(hits, key=lambda f: (f.start, f.end, f.kind))
