"""C360 / S26: the host environment an agentic leg can see and change, as one recorded fingerprint (spec s26-agent-env §1).

The agent's shell runs on the pinned agent PATH (`opencode_v2_core.SCAFFOLD_ENV_POLICY_V2`) and can change what is installed on
the shared host (Homebrew, global npm, /usr/local/bin) or in the operator's real HOME (the JVM ignores `$HOME`). `fingerprint()`
records exactly that, without running anything; `diff()` names every change. The Wave 2 sequencer and the tg2 positives compare
before and after; nothing is ever reverted (light: detect and fail closed).
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import shutil
from pathlib import Path

AGENT_PATH = "/opt/homebrew/bin:/usr/bin:/bin"          # = opencode_v2_core.SCAFFOLD_ENV_POLICY_V2["PATH"] (tested equal)
TOOLS = ("cargo", "rustc", "java", "javac", "gradle", "node", "npm", "g++", "clang++", "cmake", "make", "python3", "go", "docker")
CELLAR = Path("/opt/homebrew/Cellar")
BIN_DIRS = (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))
NPM_GLOBAL = Path("/opt/homebrew/lib/node_modules")
HOME_TOOLCHAINS = (".cargo", ".rustup", ".sdkman", ".gradle", ".m2", ".npm-global", "Library/Python")
TG2_PROPERTIES_LABEL = "tg2 gradle.properties"
SECTIONS = ("path", "tools", "cellar", "bin_dirs", "npm_global", "home_toolchains", "files")


def real_home() -> Path:
    """The account's home directory (the passwd entry, which is what the JVM reads), not `$HOME`."""
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return Path.home()


def _err(exc) -> str:
    return f"error: {type(exc).__name__}"


def portable(text, home=None) -> str:
    """`text` with the real home directory written as `~` (records and messages carry no home path)."""
    text = str(text)
    h = str(home if home is not None else real_home()).rstrip("/")
    if h and h != "/":
        if text == h:
            return "~"
        text = text.replace(h + "/", "~/")
    return text


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tool(name, path, home):
    try:
        exe = shutil.which(name, path=path)
        if exe is None:
            return "absent"
        real = os.path.realpath(exe)
        return {"path": portable(real, home), "sha256": _sha256_file(real)}
    except OSError as exc:
        return _err(exc)


def _names(directory):
    """Sorted entry names of `directory`; None when it does not exist; `error: …` when unreadable."""
    try:
        return sorted(p.name for p in Path(directory).iterdir())
    except FileNotFoundError:
        return None
    except OSError as exc:
        return _err(exc)


def _cellar(cellar):
    formulae = _names(cellar)
    if not isinstance(formulae, list):
        return formulae
    rows = []
    for formula in formulae:
        sub = Path(cellar) / formula
        if not sub.is_dir():
            continue
        versions = _names(sub)
        if isinstance(versions, list):
            rows += [f"{formula}/{v}" for v in versions]
        else:
            rows.append(f"{formula}/{versions}")
    return sorted(rows)


def _bin_dir(directory, home):
    names = _names(directory)
    if not isinstance(names, list):
        return names
    out = []
    for name in names:
        p = Path(directory) / name
        try:
            out.append(f"{name} -> {portable(os.readlink(p), home)}" if p.is_symlink() else name)
        except OSError as exc:
            out.append(f"{name} -> {_err(exc)}")
    return out


def _package_version(directory):
    try:
        doc = json.loads((Path(directory) / "package.json").read_text())
    except (OSError, ValueError) as exc:
        return _err(exc)
    version = doc.get("version") if isinstance(doc, dict) else None
    return version if isinstance(version, str) else "error: no version"


def _npm_global(root):
    names = _names(root)
    if not isinstance(names, list):
        return names
    out = {}
    for name in names:
        if name.startswith("."):
            continue
        p = Path(root) / name
        if name.startswith("@"):
            scoped = _names(p)
            if not isinstance(scoped, list):
                out[name] = scoped if scoped is not None else "error: FileNotFoundError"
                continue
            for sub in scoped:
                if not sub.startswith("."):
                    out[f"{name}/{sub}"] = _package_version(p / sub)
        elif p.is_dir():
            out[name] = _package_version(p)
    return out


def _present(path):
    try:
        return "present" if os.path.lexists(path) else "absent"
    except OSError as exc:  # pragma: no cover - lexists does not raise on macOS
        return _err(exc)


def _file(path):
    try:
        return _sha256_file(path)
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        return _err(exc)


def fingerprint(*, path=AGENT_PATH, cellar=CELLAR, bin_dirs=BIN_DIRS, npm_global=NPM_GLOBAL, home=None, files=()) -> dict:
    """{path, tools, cellar, bin_dirs, npm_global, home_toolchains, files}: JSON-native, deterministic for an unchanged host, no
    subprocess. An unreadable entry records `error: <ExceptionName>`; nothing raises. The real home is written as `~`."""
    home = Path(home) if home is not None else real_home()
    out = {"path": path}
    for key, build in (
            ("tools", lambda: {name: _tool(name, path, home) for name in TOOLS}),
            ("cellar", lambda: _cellar(cellar)),
            ("bin_dirs", lambda: {portable(d, home): _bin_dir(d, home) for d in bin_dirs}),
            ("npm_global", lambda: _npm_global(npm_global)),
            ("home_toolchains", lambda: {rel: _present(home / rel) for rel in HOME_TOOLCHAINS}),
            ("files", lambda: {str(label): _file(p) for label, p in files})):
        try:
            out[key] = build()
        except Exception as exc:  # noqa: BLE001  (a fingerprint never raises: the section records the failure)
            out[key] = _err(exc)
    return json.loads(json.dumps(out, sort_keys=True))


def fingerprint_for_run(*, workdir=None, **kw) -> dict:
    """The box call: the defaults plus the tg2 Gradle home's `gradle.properties` (`bench.tg2_gradle_home`)."""
    from . import tg2_gradle_home
    try:
        props = tg2_gradle_home.folder(workdir) / "gradle.properties"
    except Exception as exc:  # noqa: BLE001  (no $STACK_WORKDIR: recorded, never raised)
        return dict(fingerprint(**kw), files={TG2_PROPERTIES_LABEL: _err(exc)})
    return fingerprint(files=((TG2_PROPERTIES_LABEL, props),), **kw)


# ----------------------------------------------------------------------------------------------- diff
def _short(value):
    if isinstance(value, dict) and set(value) == {"path", "sha256"}:
        return f"{value['path']} (sha256 {str(value['sha256'])[:12]})"
    if value is None:
        return "absent"
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def _list_rows(label, a, b):
    if isinstance(a, list) and isinstance(b, list):
        return ([f"{label}: added {x}" for x in sorted(set(b) - set(a))]
                + [f"{label}: removed {x}" for x in sorted(set(a) - set(b))])
    return [] if a == b else [f"{label}: {_short(a)} -> {_short(b)}"]


def _entry_map(entries):
    out = {}
    for e in entries:
        name, sep, target = e.partition(" -> ")
        out[name] = target if sep else None
    return out


def _bin_rows(label, a, b):
    if not (isinstance(a, list) and isinstance(b, list)):
        return [] if a == b else [f"{label}: {_short(a)} -> {_short(b)}"]
    ma, mb = _entry_map(a), _entry_map(b)
    out = []
    for name in sorted(set(ma) | set(mb)):
        if name not in ma:
            out.append(f"{label}: added {name}" + (f" -> {mb[name]}" if mb[name] is not None else ""))
        elif name not in mb:
            out.append(f"{label}: removed {name}" + (f" -> {ma[name]}" if ma[name] is not None else ""))
        elif ma[name] != mb[name]:
            out.append(f"{label}: {name}: {_short(ma[name]) if ma[name] is not None else 'file'} -> "
                       f"{_short(mb[name]) if mb[name] is not None else 'file'}")
    return out


def _dict_rows(prefix, a, b, fmt):
    a, b = (a if isinstance(a, dict) else {}), (b if isinstance(b, dict) else {})
    return [fmt(k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def diff(before, after) -> list:
    """Every change from `before` to `after`, human-readable; `[]` iff the two fingerprints are equal."""
    before, after = (before if isinstance(before, dict) else {}), (after if isinstance(after, dict) else {})
    out = []
    if before.get("path") != after.get("path"):
        out.append(f"agent PATH: {before.get('path')} -> {after.get('path')}")
    for key, prefix, fmt in (
            ("tools", "tool", lambda k, a, b: f"tool {k}: {_short(a)} -> {_short(b)}"),
            ("home_toolchains", "~", lambda k, a, b: f"~/{k}: {_short(a)} -> {_short(b)}"),
            ("files", "file", lambda k, a, b: f"file {k}: {_short(a)[:64]} -> {_short(b)[:64]}")):
        a, b = before.get(key), after.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            out += _dict_rows(prefix, a, b, fmt)
        elif a != b:
            out.append(f"{key}: {_short(a)} -> {_short(b)}")
    out += _list_rows("Homebrew Cellar", before.get("cellar"), after.get("cellar"))
    a, b = before.get("bin_dirs"), after.get("bin_dirs")
    if isinstance(a, dict) and isinstance(b, dict):
        for d in sorted(set(a) | set(b)):
            out += _bin_rows(d, a.get(d), b.get(d))
    elif a != b:
        out.append(f"bin_dirs: {_short(a)} -> {_short(b)}")
    a, b = before.get("npm_global"), after.get("npm_global")
    if isinstance(a, dict) and isinstance(b, dict):
        out += _dict_rows("npm -g", a, b, lambda k, x, y: f"npm -g {k}: {_short(x)} -> {_short(y)}")
    elif a != b:
        out.append(f"npm -g ({NPM_GLOBAL.name}): {_short(a) if not isinstance(a, dict) else 'present'} -> "
                   f"{_short(b) if not isinstance(b, dict) else 'present'}")
        out += _dict_rows("npm -g", a, b, lambda k, x, y: f"npm -g {k}: {_short(x)} -> {_short(y)}")
    for key in sorted((set(before) | set(after)) - set(SECTIONS)):
        if before.get(key) != after.get(key):
            out.append(f"{key}: {_short(before.get(key))} -> {_short(after.get(key))}")
    if not out and before != after:                      # never `[]` for unequal fingerprints
        out.append("the host fingerprint differs (unclassified change)")
    return out
