"""M76 B4b-1 (spec docs/specs/m76-b4b-tg2-runner.md v5, §1): the tg2 corpus — Rust / JavaScript / Java / C++ of the frozen M65
universe (`benchmark/m65/tg2_universe.json`, pinned by `schedules.TG2_UNIVERSE_SHA256`), materialised by `tg2_materialize`,
graded by `tg2_grade.grade_item` in the pinned `tg2-grader` image.

The work tree is read through ONE normalised view (`view_manifest`, H2): `tg2_grade`'s top-level build outputs
(`STRIP_TOP_LEVEL`, absent from the prepared tree) are omitted, and so is a Rust `Cargo.lock` the prepared tree does not hold
(`tg2_grade`'s compile step deletes and regenerates every lock, and its tamper check ignores a lock's content) — so the
language's own build / test commands neither tamper the item nor break the snapshot. `manifest`, `snapshot`, the tamper check
and `final_tree` all use that view; the snapshot is a copy of exactly the view's files in `<run>/grading-snap/` (G1: never
inside `grading-private`, which `tg2_grade` refuses as a work tree's parent)."""
from __future__ import annotations

import hashlib
import json
import posixpath
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from . import atomic_publish
from . import corpus_tg1
from . import structured_grade as sg
from . import tg2_grade as tg
from .corpus import Corpus, FinalTree, GradeOutcome, PreparedItem
from .token_turn_gate import TransportAbort

REPO = Path(__file__).resolve().parents[2]
DEFAULT_UNIVERSE = REPO / "benchmark/m65/tg2_universe.json"
DEFAULT_DRAW = REPO / "benchmark/m65/tg2_draw.json"
SCAFFOLD = "opencode-v2-web-tg2"
LANGS = ("rust", "javascript", "java", "cpp")
# Every scored outcome `tg2_grade` emits besides `parsed` / `tampered`: every leaf fails (a statement about the model's tree).
SCORED_ALL_FAILED = ("compile_failure", "timeout", "oom", "mem_kill", "crash", "storage_cap", "output_cap")
GRADER_TIMEOUT_SLACK_S = 300
# E1: the per-language helper sentence the prompt ends with.
HINTS = {
    "rust": "Helper modules may go under src/; you may add [dependencies] from the offline crates listed in OFFLINE_CRATES.md "
            "to Cargo.toml.",
    "java": "Helper classes may go only in the solution's package.",
    "javascript": "Helper .js files may go beside the solution.",
    "cpp": "Helper .h / .cpp files may go beside the solution.",
}
INJECT_ADDENDA = corpus_tg1.INJECT_ADDENDA          # tg1's three texts, byte-equal (tested)
inject_addendum_sha256 = corpus_tg1.inject_addendum_sha256


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha(path):
    return _sha_bytes(Path(path).read_bytes())


def _stripped_top(name, prepared):
    """True for a top-level entry `tg2_grade.strip_build_outputs` removes (a build output the prepared tree does not hold)."""
    tops = {p.split("/")[0].casefold() for p in prepared}
    return name.casefold() in tg.STRIP_TOP_LEVEL and name.casefold() not in tops


def view_manifest(work, prepared, lang):
    """The normalised view (H2): `structured_grade.manifest`'s walk (same exclusions; a symlink or a non-regular file raises
    ValueError) of the work tree minus the stripped top-level build outputs and, for Rust, every `Cargo.lock` outside the
    prepared tree; for javascript every `package-lock.json` outside it (S27 §7.2, any depth). `prepared` = the prepared-tree
    manifest."""
    root = Path(work)
    result = {}

    def walk(directory, top):
        for path in sorted(directory.iterdir()):
            if top and _stripped_top(path.name, prepared):
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError("symlink in snapshot")
            if stat.S_ISDIR(mode):
                if path.name not in sg.EXCLUDED:
                    walk(path, False)
            elif not stat.S_ISREG(mode):
                raise ValueError("non-regular input")
            elif not path.name.endswith(".pyc"):
                rel = path.relative_to(root).as_posix()
                if lang == "rust" and path.name.casefold() == "cargo.lock" and rel not in prepared:
                    continue
                if lang == "javascript" and path.name.casefold() == "package-lock.json" and rel not in prepared:
                    continue                    # S27 §7.2 (C368 (1)): the package manager's lock, as Rust's Cargo.lock
                result[rel] = _sha_bytes(path.read_bytes())

    walk(root, True)
    return result


def grade_outcome(result, entry, *, seq, boundary, final):
    """A `tg2_grade.Tg2Grade` as the corpus `GradeOutcome` (spec §1 "Grader mapping"): every graded outcome is `model`;
    `parsed` counts `result.failing(universe)` (a collected failure outside the universe counts, an extra passing leaf does
    not); every other scored outcome fails every leaf; `tampered` has no count. A `TransportAbort` never reaches here."""
    universe = set(entry["leaves"])
    phase = dict(seq=seq, boundary=boundary, final=bool(final), outcome=result.outcome)
    resources = dict(grader_mem_kill=result.outcome == "mem_kill", grader_oom=result.outcome == "oom")
    if result.outcome == "tampered":
        return GradeOutcome(failing=None, leaves=(), tampered=True, outcome="model", resources=resources, phases=(phase,),
                            reports=dict(result.artifacts))
    if result.outcome == "parsed":
        failing, leaves = result.failing(universe), tuple(sorted(universe & result.passing))
    elif result.outcome in SCORED_ALL_FAILED:
        failing, leaves = len(universe - set(result.optional)), ()
    else:
        raise TransportAbort(f"tg2 grader outcome {result.outcome!r} is not a scored outcome (never graded)")
    return GradeOutcome(failing=failing, leaves=leaves, tampered=False, outcome="model", resources=resources, phases=(phase,),
                        reports=dict(result.artifacts))


class Tg2Corpus(Corpus):
    corpus_id = "tg2"
    languages = LANGS
    # what the shared core takes from the corpus (tg1 keeps the core's defaults)
    default_universe = DEFAULT_UNIVERSE
    inject_flag = "--tg2-inject"
    inject_root = "m65/inject"
    refusal = "tg2 supports eligible Rust/JavaScript/Java/C++ single-pass items only"
    stall_lang = "rust"
    docker_images = ("aider-benchmark", tg.IMAGE_TAG)       # the toolchain's grader image (`bench.toolchain`) and tg2's

    def __init__(self, universe_path=None, polyglot_root=None, polyglot_sha=None, draw_path=None):
        """`polyglot_root` / `polyglot_sha` may be callables (resolved lazily on every use, as in `Tg1Corpus`)."""
        self.universe_path = Path(universe_path or DEFAULT_UNIVERSE)
        self.draw_path = Path(draw_path or DEFAULT_DRAW)
        self._polyglot_root = polyglot_root if (polyglot_root is None or callable(polyglot_root)) else Path(polyglot_root)
        self._polyglot_sha = polyglot_sha
        self.universe = None
        self.universe_sha256 = None
        self._works = {}                                          # str(work) -> (prepared manifest, language)

    # -- universe
    def load_universe(self, path=None):
        """The frozen universe, verified by its recorded facts: the file hashes to its sidecar and to the pin
        `schedules.TG2_UNIVERSE_SHA256`; its grader / materializer versions are the code's; its image id and polyglot sha are the
        image pin's. (`m65.tg2_universe.load` also re-derives the freezer's code closure, which no longer matches the freeze at
        this baseline; the pin fixes the universe's content.)"""
        from . import schedules
        from . import tg2_materialize as mat
        if path is not None:
            self.universe_path = Path(path)
        p = self.universe_path
        try:
            raw = p.read_bytes()
            side = p.with_suffix(p.suffix + ".sha256").read_text().split()[0]
            doc = json.loads(raw)
        except (OSError, ValueError, IndexError) as exc:
            raise TransportAbort(f"invalid frozen tg2 universe: {type(exc).__name__}") from None
        sha = _sha_bytes(raw)
        problems = []
        if side != sha:
            problems.append("the file differs from its sha256 sidecar")
        if sha != schedules.TG2_UNIVERSE_SHA256:
            problems.append("it is not the pinned universe (TG2_UNIVERSE_SHA256)")
        if not isinstance(doc, dict) or not isinstance(doc.get("items"), dict):
            problems.append("no items")
        else:
            if doc.get("grader_version") != tg.VERSION:
                problems.append(f"grader version {doc.get('grader_version')!r} is not {tg.VERSION!r}")
            if doc.get("materializer_version") != mat.VERSION:
                problems.append(f"materializer version {doc.get('materializer_version')!r} is not {mat.VERSION!r}")
            if doc.get("image_id") != tg.pinned_image_id():
                problems.append("its image id is not the pinned tg2-grader image")
            if doc.get("polyglot_sha") != tg.image_record().get("polyglot_sha"):
                problems.append("its polyglot sha is not the image pin's")
        if problems:
            raise TransportAbort("invalid frozen tg2 universe: " + "; ".join(problems))
        self.universe, self.universe_sha256 = doc, sha
        return doc, sha

    def _loaded(self):
        if self.universe is None:
            self.load_universe()
        return self.universe

    @property
    def excluded(self):
        return frozenset(i for i, e in self._loaded()["items"].items() if e.get("status") != "valid")

    def items(self, lang):
        return sorted(i for i, e in self._loaded()["items"].items()
                      if i.split("/", 1)[0] == lang and e.get("status") == "valid")

    def needs_docker(self, lang):
        return True

    def grader_timeouts(self):
        """`grader_timeout_s[lang] = 2 x max(timeout_s) + 300` over the language's valid items (one grade's bound)."""
        out = {}
        for lang in LANGS:
            values = [e["timeout_s"] for i, e in self._loaded()["items"].items()
                      if i.split("/", 1)[0] == lang and e.get("status") == "valid"]
            if not values:
                raise TransportAbort(f"tg2 corpus: no valid {lang} item")
            out[lang] = 2 * max(values) + GRADER_TIMEOUT_SLACK_S
        return out

    def _root(self):
        if callable(self._polyglot_root):
            return Path(self._polyglot_root())
        if self._polyglot_root is None:
            from . import opencode_v2_core as core
            self._polyglot_root = core._polyglot_root()
        return Path(self._polyglot_root)

    def polyglot_root(self):
        """The pinned polyglot checkout the universe names (the corpus-root seam)."""
        return self._root()

    def source_root(self, lang):
        return self._root() / lang / "exercises/practice"

    def source_sha(self):
        sha = self._polyglot_sha
        if sha is None:
            from . import opencode_v2_core as core
            sha = core._polyglot_sha
        return sha(self._root())

    def inject_addendum_sha256(self, kind):
        return inject_addendum_sha256(kind)

    # -- the live checkout against the universe's recorded facts (change review L2)
    def verify_inputs(self, item):
        """The item's exercise directory (tests, stubs, `.meta`, `.docs`) hashes to the `inputs_sha256` the universe recorded
        (`m65.tg2_universe.inputs_sha256`); else TransportAbort."""
        from m65 import tg2_universe as tu
        lang, slug = item.split("/", 1)
        recorded = self._loaded()["items"][item].get("inputs_sha256")
        try:
            live = tu.inputs_sha256(self._root(), lang, slug)
        except OSError as exc:
            raise TransportAbort(f"tg2 corpus: {item}: the exercise cannot be read ({type(exc).__name__})") from None
        if not recorded or live != recorded:
            raise TransportAbort(f"tg2 corpus: {item}: the checkout's inputs_sha256 {live[:12]} is not the universe's "
                                 f"{str(recorded)[:12]} (the exercise changed)")

    def verify_source(self, item):
        """Before materialisation: the polyglot checkout is at the universe's `polyglot_sha` and the item's inputs are the
        recorded ones."""
        want, got = self._loaded().get("polyglot_sha"), self.source_sha()
        if not got or got != want:
            raise TransportAbort(f"tg2 corpus: the polyglot checkout is at {str(got)[:12]}, the universe's polyglot_sha is "
                                 f"{str(want)[:12]}")
        self.verify_inputs(item)

    # -- item
    def prepare(self, item, dest):
        from . import opencode_v2_core as core
        from . import tg2_materialize as mat
        lang, name = item.split("/", 1)
        if item not in self._loaded()["items"] or item in self.excluded:
            raise TransportAbort("item absent/refused in universe: " + item)
        self.verify_source(item)
        entry = {**self._loaded()["items"][item], "lang": lang, "id": item}
        work = Path(dest)
        try:
            mat.prepare_tree(self._root(), lang, name, work)
        except mat.FreezeError as exc:
            raise TransportAbort(f"tg2 prepare: {exc}") from None
        core._git_init_scratch(work)
        core._freeze_mtimes(work)
        if sg.manifest(work) != entry["prepared"]:
            raise TransportAbort("prepared exercise differs from frozen universe")
        solutions = tuple(entry["solutions"])
        prepared = PreparedItem(item_id=item, lang=lang, name=name, work=work, entry=entry, editable=solutions,
                                baseline={rel: _sha(work / rel) for rel in solutions},
                                protected=sg.protected_manifest(entry["prepared"], entry["solutions"]),
                                prepared=entry["prepared"], tests=tuple(entry["tests"]))
        self._works[str(work)] = (prepared.prepared, lang)      # `manifest(work)` (the core's change detector) reads its view
        return prepared

    def spec_text(self, lang, name):
        """`.docs/instructions.md`, then (blank line) `.docs/instructions.append.md` when present, from the SOURCE exercise (the
        materialised tree excludes `.docs`), after the checkout and the item's inputs verify against the universe's record
        (`verify_source`, verify round 2 V2)."""
        self.verify_source(f"{lang}/{name}")
        docs = self.source_root(lang) / name / ".docs"
        try:
            text = (docs / "instructions.md").read_text(encoding="utf-8")
            append = docs / "instructions.append.md"
            if append.is_file():
                text += "\n\n" + append.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise TransportAbort(f"tg2 prompt: the exercise specification is unreadable ({type(exc).__name__})") from None
        return text

    def prompt(self, prepared, inject=None):
        entry = prepared.entry
        prompt = (f"Implement the solution in {', '.join(entry['solutions'])} so that the tests in {', '.join(entry['tests'])} "
                  f"pass. The specification follows.\n\n{self.spec_text(prepared.lang, prepared.name)}\n\nDo NOT modify the "
                  "tests or the build files except as stated below. Do not create new files unless the specification requires "
                  f"them; {HINTS[prepared.lang]}")
        if inject and inject != corpus_tg1.INTERRUPT_KIND:          # S27 §4.5: the interrupt positive adds no prompt text
            if inject not in INJECT_ADDENDA:
                raise ValueError(f"unknown inject kind {inject!r}")
            prompt += " " + INJECT_ADDENDA[inject]
        return prompt

    # -- the normalised view, snapshot, tamper
    def manifest(self, work, prepared=None, lang=None):
        if prepared is None:
            prepared, lang = self._prepared_of(work)
        return view_manifest(work, prepared, lang)

    def _prepared_of(self, work):
        """(prepared manifest, language) of a work tree this corpus prepared (the core calls `manifest(work)` with the tree only)."""
        hit = self._works.get(str(Path(work)))
        if hit is None:
            raise ValueError("tg2 corpus: manifest of a tree this corpus did not prepare")
        return hit

    @contextmanager
    def snapshot(self, work, private, boundary):
        """A content-stable copy of exactly the view's files under `<run>/grading-snap/` (G1), or None."""
        base = Path(private).parent / "grading-snap"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="snapshot-", dir=base) as tmp:
            dest = Path(tmp) / "tree"
            accepted = None
            for _ in range(3):
                try:
                    a = self.manifest(work)
                    for rel in a:
                        target = dest / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(Path(work) / rel, target, follow_symlinks=False)
                    copied = sg.manifest(dest)
                    b = self.manifest(work)
                    if a == copied == b:
                        accepted = sg.Snapshot(dest, boundary, a)
                        break
                except (OSError, ValueError):
                    pass
                shutil.rmtree(dest, ignore_errors=True)
            yield accepted

    def tamper_reasons(self, snap, prepared):
        if snap is None:
            return ["the work tree could not be snapshotted (a symlink or an unreadable / non-regular entry)"]
        return tg.tamper_reasons(snap.path, prepared.protected, prepared.prepared, prepared.lang,
                                 solutions=list(prepared.editable),
                                 prepared_cargo_toml=prepared.entry.get("prepared_cargo_toml"), extra_crates=())

    def tampered(self, snap, prepared):
        return bool(self.tamper_reasons(snap, prepared))

    def grade(self, snap, prepared, private, guard, keep, seq, boundary, final):
        """E7 / G9: a missing snapshot or a protected-tree violation is `tampered` without the grader (a final one leaves its typed
        receipt); else `tg2_grade.grade_item` on the snapshot. `extra_crates` is empty for model runs."""
        entry = prepared.entry
        if self.tampered(snap, prepared):
            if final and keep is not None:
                sg.write_receipt(keep, seq, boundary, True, "tampered")
            return GradeOutcome(failing=None, leaves=(), tampered=True, outcome="model",
                                resources=dict(grader_mem_kill=False, grader_oom=False),
                                phases=(dict(seq=seq, boundary=boundary, final=bool(final), outcome="tampered"),), reports={})
        result = tg.grade_item(prepared.lang, snap.path, prepared.name, private, prepared=prepared.prepared,
                               solutions=entry["solutions"], prepared_cargo_toml=entry.get("prepared_cargo_toml"),
                               extra_crates=(), keep=keep, seq=seq, boundary=boundary, final=final, guard=guard,
                               timeout=entry["timeout_s"])
        return grade_outcome(result, entry, seq=seq, boundary=boundary, final=final)

    def changed(self, prepared):
        """The "untouched solution fails" rule: a declared editable path changed."""
        return any((prepared.work / rel).is_file() and _sha(prepared.work / rel) != prepared.baseline[rel]
                   for rel in prepared.editable)

    def accepted_files(self, prepared, view):
        """The declared solutions present in the view plus every new or changed file `tg2_grade`'s tamper check accepts (helpers,
        an accepted Cargo.toml) — the complement of what it rejects."""
        lang, prep, work = prepared.lang, prepared.prepared, Path(prepared.work)
        solutions = list(prepared.editable)
        out = [rel for rel in solutions if rel in view]
        solution_dirs = {posixpath.dirname(s) for s in solutions}
        existing = set()
        if lang == "java":
            solution_dirs = {posixpath.dirname(s) for s in solutions if s.endswith(".java")}
            for rel in prep:
                if rel.endswith(".java") and rel in view:
                    existing |= tg._java_fqns(work, rel)[1]
        for rel in sorted(view):
            if rel in solutions:
                continue
            if rel not in prep:
                if not (tg._denied(rel) or tg._new_file_reason(work, rel, lang, solution_dirs, existing)):
                    out.append(rel)
            elif view[rel] != prep[rel] and lang == "rust" and rel == "Cargo.toml":
                toml = prepared.entry.get("prepared_cargo_toml")
                if toml is not None and not tg.cargo_manifest_reasons(toml, (work / rel).read_text(errors="replace"), ()):
                    out.append(rel)
        return out

    def final_tree(self, prepared, dest):
        """E8: tg1's content-addressed layout (`objects/<sha>` + `manifest.json`) over `accepted_files`; `missing` lists the declared
        solutions absent."""
        dest = Path(dest)
        try:
            (dest / "objects").mkdir(parents=True)
        except FileExistsError:
            raise TransportAbort("final tree evidence is immutable: " + dest.name + " exists") from None
        try:
            view = self.manifest(prepared.work, prepared.prepared, prepared.lang)
        except (OSError, ValueError):
            view = {rel: None for rel in prepared.editable if (Path(prepared.work) / rel).is_file()
                    and not (Path(prepared.work) / rel).is_symlink()}
        files = {}
        missing = [rel for rel in prepared.editable if rel not in view]
        for rel in (self.accepted_files(prepared, view) if all(v is not None for v in view.values())
                    else [r for r in prepared.editable if r in view]):
            data = (Path(prepared.work) / rel).read_bytes()
            sha = _sha_bytes(data)
            files[rel] = sha
            try:
                atomic_publish.publish_exclusive(dest / "objects" / sha, data)
            except FileExistsError:
                pass
        manifest = dest / "manifest.json"
        raw = (json.dumps(dict(files=files, missing=missing), sort_keys=True, indent=1) + "\n").encode()
        atomic_publish.publish_exclusive(manifest, raw)
        return FinalTree(root=dest, files=files, missing=tuple(missing), manifest_sha256=_sha_bytes(raw), manifest_path=manifest)

    # -- identity
    def draw_sha256(self):
        from . import schedules
        try:
            sha = _sha(self.draw_path)
        except OSError:
            raise TransportAbort("tg2 corpus: the draw is unreadable") from None
        if sha != schedules.TG2_DRAW_SHA256:
            raise TransportAbort("tg2 corpus: the draw is not the pinned one (TG2_DRAW_SHA256)")
        return sha

    def identity(self):
        self._loaded()
        return dict(corpus_id=self.corpus_id, universe_sha256=self.universe_sha256, draw_sha256=self.draw_sha256(),
                    grader_version=tg.VERSION, grader_timeout_s=self.grader_timeouts(), image=tg.pinned_image_id(),
                    excluded=sorted(self.excluded))

