"""Static import closure of a probe entry: the code identity of a process (P311-lite).

`python_closure(entry, repo)` walks the AST of the entry and of every repo-local module it imports (every `import` /
`from ... import`, module-level and function-level, relative imports resolved against the importer's package, parent
package `__init__` files included) and returns the files. No hand-kept module list: adding an import changes the
identity, removing one drops the file. Standard-library and third-party modules (no file under the repo roots) are
not part of it; the runtime toolchain is recorded separately (`bench.toolchain`).

`closure_sha256` hashes the closure plus a fixed list of non-Python inputs with the recipe `relpath + NUL + bytes`
over sorted relative paths (the `probe_code_sha256` recipe, kept)."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path


def roots(repo):
    repo = Path(repo)
    return [repo / "benchmark", repo]


def _module_file(parts, repo):
    """The file for dotted module `parts` under the first root that has it, else None."""
    for root in roots(repo):
        base = root.joinpath(*parts)
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
    return None


def _package_inits(parts, repo):
    """`__init__.py` of every proper parent package of dotted `parts` (executed when the module is imported)."""
    found = []
    for i in range(1, len(parts)):
        for root in roots(repo):
            init = root.joinpath(*parts[:i]) / "__init__.py"
            if init.is_file():
                found.append(init)
                break
    return found


def _importer_package(path, repo):
    path = Path(path).resolve()
    for root in roots(repo):
        root = root.resolve()
        if path.is_relative_to(root):
            parts = list(path.relative_to(root).parts[:-1])
            return parts
    return []


def import_edges(node, path, repo):
    """[(destination file, names this import binds in the importer)] for one Import / ImportFrom node.

    A `from pkg import name` yields the package (or module) edge and, when `pkg.name` is itself a module file, a
    second edge to that file. Parent package inits come with every edge."""
    edges = []

    def add(parts, bound):
        file = _module_file(parts, repo)
        if file is None:
            return None
        edges.extend((init, {"*"}) for init in _package_inits(parts, repo))
        edges.append((file, set(bound)))
        return file

    if isinstance(node, ast.Import):
        for alias in node.names:
            parts = alias.name.split(".")
            add(parts, {alias.asname or parts[0]})
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            package = _importer_package(path, repo)
            package = package[:len(package) - (node.level - 1)] if node.level > 1 else package
            base = package + (node.module.split(".") if node.module else [])
        else:
            base = node.module.split(".") if node.module else []
        names = {(a.asname or a.name) for a in node.names}
        if base:
            add(base, names)
        for alias in node.names:
            if alias.name == "*":
                continue
            sub = _module_file(base + [alias.name], repo)
            if sub is not None:
                edges.extend((init, {"*"}) for init in _package_inits(base + [alias.name], repo))
                edges.append((sub, {alias.asname or alias.name}))
    return edges


def python_closure(entry, repo):
    """Sorted repo-relative-ordered list of the files of the static import closure of `entry` (entry included)."""
    repo = Path(repo)
    entry = Path(entry)
    seen, todo = {}, [entry]
    while todo:
        path = todo.pop()
        key = path.resolve()
        if key in seen:
            continue
        seen[key] = path
        tree = ast.parse(path.read_bytes(), filename=str(path))     # SyntaxError propagates: fail closed
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for dest, _ in import_edges(node, path, repo):
                    if dest.resolve() not in seen:
                        todo.append(dest)
    repo_resolved = repo.resolve()
    return sorted((p for p in seen.values()), key=lambda p: p.resolve().relative_to(repo_resolved).as_posix())


def closure_sha256(entry, repo, data=()):
    """sha256 over the sorted (relpath NUL bytes) of the Python closure of `entry` (repo-relative) and `data`."""
    repo = Path(repo)
    repo_resolved = repo.resolve()
    rels = {p.resolve().relative_to(repo_resolved).as_posix() for p in python_closure(repo / entry, repo)}
    rels |= set(data)
    digest = hashlib.sha256()
    for rel in sorted(rels):
        digest.update(rel.encode() + b"\0")
        digest.update((repo / rel).read_bytes())
    return digest.hexdigest()


# ------------------------------------------------------------------ entry-rooted reachability (review L6)
def _top_level_units(tree):
    """(module-level statements, {qualname: node}) for the top-level functions, classes and methods of a module."""
    body, units = [], {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units[node.name] = node
        elif isinstance(node, ast.ClassDef):
            units[node.name] = node            # the class body (decorators, bases, attributes) runs with the class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    units[f"{node.name}.{item.name}"] = item
        else:
            body.append(node)
    return body, units


def _refs(nodes):
    """(ids, attrs, import nodes) syntactically inside `nodes` (nested functions included)."""
    ids, attrs, imports = set(), set(), []
    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Name):
                ids.add(node.id)
            elif isinstance(node, ast.Attribute):
                attrs.add(node.attr)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
    return ids, attrs, imports


def reachable_modules(entry, repo):
    """The repo modules whose BODY can execute when `entry` runs, by a conservative call-graph walk: a module executes
    when reached code imports it; a function-level import counts only when its function is reachable; a function is
    reachable when its name (or, for a method, its method name) is referenced by reached code, as a bare name or as an
    attribute of anything (calls through an injected object such as `p._sha_of` cannot be resolved, so any attribute
    name counts). Over-approximates reachability, so a module reported unreachable is dead on every path."""
    repo = Path(repo)
    parsed = {}

    def load(path):
        key = path.resolve()
        if key not in parsed:
            tree = ast.parse(path.read_bytes(), filename=str(path))
            body, units = _top_level_units(tree)
            parsed[key] = (path, body, units)
        return parsed[key]

    ids, attrs, executed, done_units = set(), set(), {}, set()
    pending = [Path(entry)]

    def run_nodes(path, nodes):
        i, a, imports = _refs(nodes)
        ids.update(i)
        attrs.update(a)
        for node in imports:
            for dest, _ in import_edges(node, path, repo):
                pending.append(dest)

    changed = True
    while changed or pending:
        changed = False
        while pending:
            path = pending.pop()
            key = path.resolve()
            if key in executed:
                continue
            _, body, _units = load(path)
            executed[key] = path
            run_nodes(path, body)
            changed = True
        for key, path in list(executed.items()):
            _, _body, units = load(path)
            for qual, node in units.items():
                if (key, qual) in done_units:
                    continue
                short = qual.split(".")[-1]
                is_method = "." in qual
                hit = (short in attrs or short in ids or (is_method and short.startswith("__"))
                       or (is_method and qual.split(".")[0] in ids))
                if path.resolve() == Path(entry).resolve():
                    hit = True                              # the entry's own functions are all roots
                if hit:
                    done_units.add((key, qual))
                    run_nodes(path, [node])
                    changed = True
    repo_resolved = repo.resolve()
    return sorted(p.resolve().relative_to(repo_resolved).as_posix() for p in executed.values())
