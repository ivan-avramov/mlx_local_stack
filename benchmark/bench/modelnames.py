"""Model-reference checker: every model mention must be a COMPLETE registry name (O24).

THE RULE, STATED MECHANICALLY. AGENTS.md: when referring to a model, use its full registry name, in
prose and in writing. The mechanical core is an ALLOWLIST, not a blocklist:

    a token that looks like a model reference must EXACTLY equal a name we actually have.

WHY NOT A BLOCKLIST OF SHORTHANDS. The first version of this module was exactly that — eight regexes
for the five models in the campaign at the time. It was measured against twelve real violations and
caught ONE. It missed `the Lightning model`, `the A3B`, `the 35B`, `the uniform-4bit arm`,
`the Opus-Distill`, `the 6bit variant`, `gemma-4`, and — worst — bare `Qwen3.6-27B`, which is
AMBIGUOUS across four registry variants (`-MLX-8bit`, `-OptiQ-4bit`, `-UD-MLX-6bit`,
`-Opus-Distill-OptiQ-4bit`) and is therefore precisely the collision the rule exists to prevent. A
blocklist also gives a NEW model zero protection until someone remembers to extend it, which makes it
worthless exactly when a new candidate is under test and confusion is most likely.

HOW THE ALLOWLIST IS DERIVED (so it generalises with no edits):
  * legal names  = `main_models.yaml` model names + the task model + every `benchmark/results/*` dir
                   (result dirs are authoritative for arms we measured but never served, e.g. the
                   `-suffix` / `-kv16` variants).
  * fragments    = every hyphen-segment and every proper prefix of a legal name, computed at runtime.
                   `Qwen3.6-27B` is a proper prefix -> under-specified. `Ornith`, `Nemotron`, `OptiQ`,
                   `A3B` are segments -> shorthand. Add a model to the registry and its fragments are
                   covered on the next run.

WHAT THIS CANNOT DO, AND MUST NOT BE CLAIMED TO DO. It cannot catch a reference that shares no token
with any name: "the fast one", "the winner", "the runner-up", "the dense model", "the third
candidate". Deciding those denote a model is a semantic judgement, not a lexical one. So this hook
raises the floor; it does not implement the rule. AGENTS.md says so explicitly, and that wording
should stay.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

# A line that DOCUMENTS the rule must be able to name the forms it bans, or the rule could never be
# written down. Verbose so it cannot be typed by accident; greppable so misuse is auditable:
#   git grep -n allow-shorthand
ALLOW_MARKER = "allow-shorthand"

# Files whose PURPOSE is to define or test these patterns necessarily contain them: this module and
# its test. Exempting them by path beats sprinkling ~60 inline markers, which would bury the code.
# Verified the hard way — the first commit of this module was blocked by the module itself, 62 times.
EXEMPT_PATHS = (
    "benchmark/bench/modelnames.py",
    "benchmark/bench/tests/test_model_name_check.py",
)

# GENERATED configs are not prose. Their content is emitted from main_models.yaml, and their
# human-facing `display_name` labels ("NVIDIA Nemotron 3.5 Lightning 30B-A3B (candidate)") come from
# the registry's `presentation` block on purpose — they are UI labels, not identifiers, and cannot be
# "fixed" here without making the UI unreadable. Flagging them would mean no generated config could
# ever be committed. Kept in step with configgen by
# test_model_name_check.py::test_generated_paths_cover_every_configgen_target.
GENERATED_PATHS = (
    "opencode_config/opencode.json",
    "aider_config/aider.model.settings.yml",
    "aider_config/aider.model.metadata.json",
    "aider_config/aider.conf.yml",
    "vscode_config/chatLanguageModels.json",
    "zed_config/settings.snippet.jsonc",
    "openwebui-init/models_config.json",
    "benchmark/aider_bench.model.settings.yml",
    "benchmark/opencode_bench.json",
)

# Version/size-only fragments. `1.0` is a segment of a model name, but a bare `1.0` in a diff is
# overwhelmingly a number — `"temperature": 1.0` was flagged as a model shorthand, which would fire
# on essentially every sampling change in the repo. Sizes are still caught in PROSE by the
# attribute-for-instance rule below ("the 35B model"), where there is a determiner to disambiguate.
_VERSIONISH = re.compile(r"^\d+(?:\.\d+)*[Bb]?$", re.IGNORECASE)

# Namespaces/orgs are legal to write but are not model names; kept out of the "did you mean" list.
_NAMESPACES = {"mlx-community", "caslca", "nvidia", "google", "Qwen"}

# Fragments too generic to be a model reference on their own. Kept SMALL and justified: each is a
# word that occurs in ordinary technical prose about quantisation, packaging or architecture.
# NOTE these are excluded from the *fragment* rule only — a proper PREFIX of a real name is still
# flagged, because `Qwen3.6-27B` is never ordinary prose.
_GENERIC = {
    "mlx", "it", "bit", "4bit", "6bit", "8bit", "3bit", "kv", "kv3", "kv4", "kv16", "ud", "qat",
    "instruct", "base", "chat", "text", "vision", "suffix", "uniform", "mixed", "nvidia", "google",
    "qwen", "community", "mlx-community", "a", "b", "1", "0", "lite", "turbo", "v1", "v2",
}
# Architecture/quant CATEGORY words that are shorthand when used as "the X" to mean a model. This is
# a generic linguistic rule (a category standing in for an instance), not a per-model list.
#   (a) a bare category word standing in for a model: "the MoE", "the distill"
#   (b) a category ATTRIBUTE plus an instance noun: "the 6bit variant", "the qat model",
#       "the hybrid MoE candidate". This is a generic linguistic shape — an attribute used to pick
#       out an instance — so it needs no per-model list and covers models not yet registered.
# "the MoE architecture" is deliberately NOT matched: that discusses a class, not an instance.
_ATTR = r"(?:MoE|dense|hybrid|qat|optiq|distill|uniform|\d+ ?-?bit|\d+(?:\.\d+)?B|quant(?:ised|ized)?)"
_NOUN = r"(?:model|variant|arm|candidate|checkpoint|build|one)"
# A CLASS noun after the attribute means the sentence discusses the category itself, which is
# legitimate: "the MoE architecture", "the 4-bit quantization". Only an INSTANCE reading violates.
_CLASS = (r"(?:architectures?|quantis|quantiz|formats?|layers?|experts?|paths?|kernels?|schemes?|"
          r"routing|designs?|families|family|protocols?|encodings?|parameters?|params?)")
_CATEGORY_STANDINS = re.compile(
    rf"\bthe\s+(?:{_ATTR}\b(?![-/\w])(?!\s+{_CLASS})"        # (a) bare category word
    rf"|(?:\w+\s+)?{_ATTR}\s+{_NOUN}\b)", re.IGNORECASE)     # (b) attribute + instance noun

# Model-name-shaped token: alphanumeric run, optionally hyphen/dot joined. Deliberately greedy on
# hyphens so `Ornith-1.0-35B` is ONE token rather than three.
_TOKEN = re.compile(r"[A-Za-z0-9][\w.]*(?:-[\w.]+)*")


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    label: str
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.label} — {self.text.strip()[:84]}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@functools.lru_cache(maxsize=4)
def legal_names(root: str | None = None) -> frozenset[str]:
    """Full model names we actually have: the registry plus every measured result directory."""
    base = Path(root) if root else _repo_root()
    names: set[str] = set()
    reg = base / "main_models.yaml"
    if reg.exists():
        try:
            import yaml
            doc = yaml.safe_load(reg.read_text()) or {}
            for entry in doc.get("models") or []:
                if isinstance(entry, dict) and entry.get("name"):
                    names.add(str(entry["name"]))
            tm = doc.get("task_model")
            if isinstance(tm, dict) and tm.get("name"):
                names.add(str(tm["name"]))
        except Exception:
            pass                      # a broken registry must not break committing
    results = base / "benchmark" / "results"
    if results.is_dir():
        names.update(p.name for p in results.iterdir() if p.is_dir() and not p.name.startswith("_"))
    # A hub path is a legal way to write a model: `mlx-community/<name>`. Register the bare basename
    # too, and the namespace on its own, so tokenising `mlx-community/NVIDIA-...` into two tokens
    # does not flag the namespace as an under-specified name.
    for n in list(names):
        if "/" in n:
            names.add(n.split("/", 1)[1])
            names.add(n.split("/", 1)[0])
    names.update(_NAMESPACES)
    return frozenset(names)


@functools.lru_cache(maxsize=4)
def _index(root: str | None = None):
    """(allowed, prefixes, fragments) derived from the legal names."""
    allowed = legal_names(root)
    prefixes: set[str] = set()
    fragments: set[str] = set()
    for name in allowed:
        parts = name.replace("/", "-").split("-")
        for i in range(1, len(parts)):
            prefixes.add("-".join(parts[:i]).lower())
        # EVERY segment-aligned run, not just prefixes and single segments. A mid-name run like
        # `uniform-4bit`, `Opus-Distill`, `OptiQ-4bit` or `30B-A3B` is just as under-specified as a
        # prefix, and single-segment-only matching missed all four.
        for i in range(len(parts)):
            for j in range(i + 1, len(parts) + 1):
                run = parts[i:j]
                frag = "-".join(run).lower()
                # A single generic segment (`mlx`, `it`, `4bit`) is ordinary technical prose; a
                # MULTI-segment run is distinctive even when its pieces are generic.
                if len(run) == 1 and (frag in _GENERIC or len(frag) < 3 or frag.isdigit()
                                      or _VERSIONISH.match(frag)):
                    continue
                fragments.add(frag)
    prefixes -= {n.lower() for n in allowed}
    fragments -= {n.lower() for n in allowed}
    return allowed, frozenset(prefixes), frozenset(fragments)


def violations(text: str, *, path: str = "<text>", line: int = 0,
               root: str | None = None) -> list[Violation]:
    """Model references in one string that are not a complete registry name."""
    if ALLOW_MARKER in text:
        return []
    allowed, prefixes, fragments = _index(root)
    allowed_lower = {n.lower() for n in allowed}
    out: list[Violation] = []
    seen: set[str] = set()

    if _CATEGORY_STANDINS.search(text):
        m = _CATEGORY_STANDINS.search(text)
        out.append(Violation(path, line, f"category stand-in {m.group(0)!r} used for a model", text))

    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        low = tok.lower().strip(".")
        if low in seen or low in allowed_lower:
            continue
        # a longer allowed name containing this token as a substring means it is part of a full name
        # A single GENERIC segment is never an under-specified model name either, even when it
        # happens to prefix one: `mlx` prefixes `mlx-community`, so without this `/mlx start`,
        # `../mlx-vlm` and "mlx+pytest" are all flagged. The generic list applied only to the
        # fragment rule, which left the prefix rule firing on ordinary prose.
        if low in _GENERIC:
            continue
        if any(low in a and low != a for a in allowed_lower) and low in prefixes:
            # A prefix followed by a CLASS noun is a family reference, not an under-specified
            # instance: "the gemma-4 family" names a group of models on purpose and there is no
            # single full name to substitute. Same class-vs-instance distinction as the category
            # rule below, so it belongs here rather than being reworded around in every doc.
            rest = text[m.end():]
            if re.match(rf"\s+{_CLASS}", rest, re.IGNORECASE):
                continue
            out.append(Violation(path, line, f"under-specified model name {tok!r}", text))
            seen.add(low)
        elif low in fragments:
            out.append(Violation(path, line, f"model shorthand {tok!r}", text))
            seen.add(low)
    return out


def diff_violations(diff: str, *, root: str | None = None) -> list[Violation]:
    """Violations on ADDED lines of a unified diff, at their NEW-file line number.

    Only `+` content is checked: a commit that REMOVES a shorthand must never be blocked, or
    cleanup is impossible. `+++` headers begin with `+` but are not content.
    """
    out: list[Violation] = []
    path, new_line = "<unknown>", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:].strip()
            continue
        if raw.startswith(("--- ", "+++ ", "diff --git", "index ", "similarity ", "rename ",
                           "new file", "deleted file", "old mode", "new mode", "Binary ")):
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_line = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+"):
            # Result ROWS are model OUTPUT, not prose — a generated program may contain
            # any word ('static' blocked a real arm commit). Manifests/score .json in the
            # same tree are our own metadata and stay checked. bfcl_eval stores its rows
            # as result/**/*_result.json rather than .jsonl — same rule.
            is_result_rows = path.startswith("benchmark/results/") and (
                path.endswith(".jsonl")
                or ("/result/" in path and path.endswith("_result.json"))
            )
            if not is_result_rows and not path.endswith(EXEMPT_PATHS + GENERATED_PATHS):
                out.extend(violations(raw[1:], path=path, line=new_line, root=root))
            new_line += 1
        elif raw.startswith("-"):
            continue
        else:
            new_line += 1
    return out


# Attribution trailers name a person or a tool, never a campaign model — and one such name
# COLLIDES with a registry segment: `Claude Opus 5` contains `Opus`, a segment of
# `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Since a `Co-Authored-By:` trailer is mandatory on every
# commit in this repo, treating it as prose blocked EVERY commit, which is how it was found.
# Only these exact trailer keys are skipped, so the exemption cannot launder a reference in the body.
_ATTRIBUTION_TRAILERS = ("co-authored-by:", "signed-off-by:", "reported-by:", "reviewed-by:",
                         "acked-by:", "tested-by:", "suggested-by:")


def message_violations(msg: str, *, root: str | None = None) -> list[Violation]:
    """Violations in a commit message, ignoring git's comments, the `git commit -v` diff, and
    attribution trailers."""
    out: list[Violation] = []
    for i, raw in enumerate(msg.splitlines(), start=1):
        if raw.startswith("#"):
            if ">8" in raw:
                break
            continue
        if raw.lower().startswith(_ATTRIBUTION_TRAILERS):
            continue
        out.extend(violations(raw, path="COMMIT_MSG", line=i, root=root))
    return out


def _main(argv: list[str]) -> int:
    import subprocess
    import sys

    if "--commit-msg" in argv:
        p = argv[argv.index("--commit-msg") + 1]
        found = message_violations(Path(p).read_text(errors="replace"))
        where = "commit message"
    else:
        diff = subprocess.run(["git", "diff", "--cached", "--unified=0"],
                              capture_output=True, text=True).stdout
        found = diff_violations(diff)
        where = "staged changes"
    if not found:
        return 0
    print(f"\nAGENTS.md: a model reference must be a COMPLETE registry name. "
          f"{len(found)} in {where}:\n", file=sys.stderr)
    for v in found:
        print(f"  {v}", file=sys.stderr)
    print("\nComplete names currently known (registry + measured result dirs):", file=sys.stderr)
    for n in sorted(n for n in legal_names() if n not in _NAMESPACES and "/" not in n):
        print(f"  {n}", file=sys.stderr)
    print(f"\n(Only ADDED lines are checked. A line that must NAME a shorthand may carry "
          f"'{ALLOW_MARKER}'. Bypass once: git commit --no-verify)\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
