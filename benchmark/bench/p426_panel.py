"""P426 B3 / C207: the two-family blind pairwise panel for the ON vs OFF comparisons (`docs/specs/p426-fable-mtp-recert.md` §7).

Judges come from the box's `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/judges.json` ({"box", "text": [2 judges],
"image": [2 judges]}, two different families each). Packets reuse `judge_pairwise.export_packets` with the axis's rubric; the
Claude judge is the Claude Code `blind-judge` agent run by the session on the exported batch directories; the Cursor judge is
`run_cursor_judge` (retries 0: a failure is a missing verdict, counted). `item_scores` + `length_adjusted` give the signal.

P613 step 3 (`docs/specs/p613-step3-contract.md`): the A7 packets (`a7_select`, `a7_packet`), `freeze` / `check_frozen`.
CLI: `python -m bench.p426_panel a7-export --results-root … --b8 … --evidence-ref <sha> --repo <git top> --polyglot-root …
--universe … --judges <judges.json> --out <dir>`; `a7-cursor --out <dir> --judge <label>`; `a7-seal --out <dir> --judge
<label> --client-version <v>`. rc 0 / rc 2 + `REFUSED: <reason>`.
"""

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from bench import judge_pairwise as jp

OFF_TUNE, ON_TUNE = "p426-off", "p426-on"


def tunes(build="s"):
    """The OFF / ON panel tunes of a build label: `p426-off` / `p426-on` for S, `p426<label>-off` / `-on` otherwise."""
    from bench.p426_plan import tune_prefix

    prefix = tune_prefix(build)
    return f"{prefix}-off", f"{prefix}-on"
RUBRICS = {
    "cjudge": jp.RUBRIC_SYSTEM_PROMPT,
    "reasoning": (
        "You are judging two candidate responses that both reach the CORRECT final answer to the same problem. Judge ONLY "
        "the quality of the reasoning shown: soundness of each step, clarity and economy of the explanation, absence of "
        "errors or unjustified leaps that happen to land on the right answer. Ignore length except where it hurts clarity. "
        "The responses are labeled A and B; all identifying information has been removed. "
        'Reply with ONLY a JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No prose outside the JSON.'
    ),
    "vision": (
        "You are judging two descriptions of the SAME image (the image file is named in the prompt; look at it) against the "
        "human reference captions given in the prompt. Judge ONLY: accuracy (nothing described that is not in the image), "
        "coverage of what matters in the image, and precision. Penalize hallucinated objects, attributes or text heavily. "
        "Ignore length except where it hurts precision. The descriptions are labeled A and B; all identifying information "
        "has been removed. "
        'Reply with ONLY a JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No prose outside the JSON.'
    ),
    "code": (
        "You are judging two solutions to the same programming task; BOTH pass the task's tests. Judge ONLY code quality: "
        "clarity and readability, idiomatic use of the language, appropriate structure and naming, robustness beyond the "
        "tests, and absence of needless complexity. Ignore length except where it hurts clarity. The solutions are labeled A "
        "and B; all identifying information has been removed. "
        'Reply with ONLY a JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No prose outside the JSON.'
    ),
}
AXIS_RUBRIC = {"math500": "reasoning", "reasoning": "reasoning", "cjudge": "cjudge", "vision": "vision", "tg1": "code"}


def rubric_sha(rubric):
    return hashlib.sha256(RUBRICS[rubric].encode()).hexdigest()


def load_judges(path, modality):
    doc = json.loads(Path(path).read_text())
    if modality not in doc:
        raise ValueError(f"{path}: no {modality} judges configured")
    judges = doc[modality]
    if len(judges) != 2:
        raise ValueError(f"{path}: {modality} needs exactly two judges, found {len(judges)}")
    if len({j.get("family") for j in judges}) != 2:
        raise ValueError(f"{path}: {modality} judges must come from two different families (C166 / C206)")
    return judges


def pairs(model, off_rows, on_rows, seed=426, build="s"):
    """One blind ON vs OFF pair per item both arms hold (converged), balanced A / B slots (judge_pairwise)."""
    return jp.build_tune_pairs(model, *tunes(build), off_rows, on_rows, seed=seed)


TEXT_FIELD = {"math500": "content", "cjudge": "content", "reasoning": "content", "vision": "description", "tg1": "content"}
# K9: anything that could tell a judge which arm a response came from
LEAK_PATTERNS = (r"p426", r"\bmtp\b", r"drafter", r"draft_kind", r"joint_v1", r"caslca/", r"/Users/", r"/private/", r"/home/")


def select(axis, off, on, correct_off=None, correct_on=None):
    """K10: ``(items, excluded)`` — items ``(id, off_text, on_text)`` both arms hold, by the axis rule: math500 both correct
    (``correct_*`` sets from the grader), reasoning both strict draws (``score == 1``), cjudge / vision every item."""
    field = TEXT_FIELD[axis]
    items, excluded = [], {}
    for key in sorted(set(off) | set(on), key=str):
        if key not in off or key not in on:
            excluded.setdefault("missing in an arm", []).append(key)
            continue
        if axis == "math500" and not (key in (correct_off or ()) and key in (correct_on or ())):
            excluded.setdefault("not both correct", []).append(key)
            continue
        if axis == "reasoning" and not (off[key].get("score") == 1.0 and on[key].get("score") == 1.0):
            excluded.setdefault("not both correct", []).append(str(key))
            continue
        items.append((str(key), off[key].get(field) or "", on[key].get(field) or ""))
    return items, excluded


def make_pairs(model, items, seed=426, build="s"):
    """K10: one blind pair per selected item, A / B slots balanced (exactly half the items show ON as A), seeded."""
    off_tune, on_tune = tunes(build)
    key_off, key_on = f"{model}@{off_tune}", f"{model}@{on_tune}"
    flags = jp._balanced_flags(len(items), jp._sub_rng(seed, key_off, key_on))
    out = []
    for (item_id, off_text, on_text), on_first in zip(items, flags):
        (ka, ta), (kb, tb) = ((key_on, on_text), (key_off, off_text)) if on_first else ((key_off, off_text), (key_on, on_text))
        out.append({"pair_id": f"p426-{item_id}", "anchor_type": None, "item_id": item_id, "a_key": f"{ka}::{item_id}",
                    "b_key": f"{kb}::{item_id}", "a_text": ta, "b_text": tb, "expected": None})
    return out


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def leak_problems(out_dir, model_names):
    patterns = [re.compile(re.escape(m), re.I) for m in model_names] + [re.compile(p, re.I) for p in LEAK_PATTERNS]
    found = []
    for packet in sorted(Path(out_dir).glob("*/batch*/p*.md")):
        text = packet.read_text()
        for pat in patterns:
            if pat.search(text):
                found.append(f"{packet.parent.parent.name}/{packet.name}: {pat.pattern}")
    return found


def export(axis, the_pairs, judge_labels, task_prompts, out_dir, images=None, model_names=None):
    """Packets in a FRESH directory (K7), the axis rubric, images beside; refused on any identity leak (K9)."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"{out_dir} exists: packets are exported once into a fresh directory")
    rubric = AXIS_RUBRIC[axis]
    names = list(model_names or {p["a_key"].split("@", 1)[0] for p in the_pairs})
    rows = jp.export_packets(
        the_pairs, judge_labels, task_prompts, names, str(out_dir), system=RUBRICS[rubric], attachments=images
    )
    leaks = leak_problems(out_dir, names)
    if leaks:
        raise ValueError(f"packet leak (identity visible to a judge): {leaks[:5]}")
    return rows


def _attachment(packet):
    others = [p for p in packet.parent.glob(f"{packet.stem}.*") if p.suffix not in (".md", ".json", ".txt")]
    return _sha(others[0]) if others else None


def _seal(packet, choice, rationale, judge, client_version, prompt_sha, frozen_sha=None):
    doc = dict(choice=choice, rationale=rationale, judge=judge["label"], family=judge.get("family"),
               client=judge.get("client"), model=judge.get("model"), client_version=client_version,
               packet_sha=_sha(packet), attachment_sha=_attachment(packet), prompt_sha=prompt_sha)
    if frozen_sha is not None:                          # P613 step 3: bound to the frozen set (FROZEN.json sha256)
        doc["frozen_sha256"] = frozen_sha
    return doc


def seal_verdicts(out_dir, judge, client_version):
    """K7 / K8: bind each bare verdict the Claude ``blind-judge`` agent wrote to its packet + the judge's provenance."""
    manifest = {r["pkt"]: r for r in jp.load_manifest(str(out_dir)) if r["judge"] == judge["label"]}
    sealed = 0
    for pkt, row in manifest.items():
        packet = Path(row["path"])
        verdict = packet.with_name(f"{pkt}.verdict.json")
        if not verdict.exists():
            continue
        doc = json.loads(verdict.read_text())
        if "packet_sha" in doc:
            continue
        parsed = jp.parse_verdict(json.dumps(doc))
        verdict.write_text(json.dumps(_seal(packet, parsed["choice"], doc.get("rationale"), judge, client_version,
                                            row["prompt_sha"])) + "\n")
        sealed += 1
    return sealed


def ingest(out_dir):
    """K7 / K8: verdict rows carrying their provenance; a verdict not bound to its CURRENT packet (sha / attachment) is
    ``unbound`` and never admitted."""
    rows, report = [], {"missing": 0, "unbound": 0, "unparseable": 0}
    for m in jp.load_manifest(str(out_dir)):
        packet = Path(m["path"])
        verdict = packet.with_name(f"{m['pkt']}.verdict.json")
        if not verdict.exists():
            report["missing"] += 1
            continue
        try:
            doc = json.loads(verdict.read_text())
        except json.JSONDecodeError:
            report["unparseable"] += 1
            continue
        if doc.get("packet_sha") != _sha(packet) or doc.get("attachment_sha") != _attachment(packet):
            report["unbound"] += 1
            continue
        rows.append(dict(doc, item_id=m["item_id"], order=m["order"], a_key=m["a_key"], b_key=m["b_key"],
                         pair_id=m["pair_id"]))
    return rows, report


def admit(rows, judges):
    """K11: an item is scored only with exactly one valid verdict per (judge, order); incomplete / duplicated items are
    excluded and counted."""
    by = {}
    for r in rows:
        if r.get("choice") in ("A", "B", "tie"):
            by.setdefault(r["item_id"], []).append(r)
    need = {(j, o) for j in judges for o in jp.ORDERS}
    admitted, excluded = {}, {}
    for item in sorted(by, key=str):
        keys = [(r["judge"], r["order"]) for r in by[item]]
        if len(keys) != len(set(keys)):
            excluded.setdefault("duplicate", []).append(item)
        elif set(keys) != need:
            excluded.setdefault("incomplete", []).append(item)
        else:
            admitted[item] = by[item]
    return admitted, excluded


def run_cursor_judge(out_dir, judge, runner=subprocess.run, timeout_s=900, frozen_sha=None):
    """Judge every packet of ``judge`` (a Cursor model) once: retries 0, an unparseable / failed answer writes no verdict
    (ingest counts it missing). Records the client version and model in ``<judge>/provenance.json``.

    Retries 0 across invocations: ``<pkt>.attempt.json`` is written before each call; a packet with an attempt marker, a
    verdict or a failed marker is never called again. ``frozen_sha`` (P613 step 3) binds each verdict to FROZEN.json."""
    root = Path(out_dir) / judge["label"]
    pre = runner(["cursor-agent", "--version"], capture_output=True, text=True, timeout=60)
    version = (pre.stdout or "").strip()
    if pre.returncode != 0 or not version:  # K8: no verdict without a known client
        raise RuntimeError(f"cursor-agent version check failed (rc {pre.returncode}): {(pre.stderr or '')[:200]}")
    prompt_sha = {r["pkt"]: r["prompt_sha"] for r in jp.load_manifest(str(out_dir)) if r["judge"] == judge["label"]}
    written = failed = skipped = 0
    for packet in sorted(root.glob("batch*/p*.md")):
        pkt = packet.stem
        verdict = packet.with_name(f"{pkt}.verdict.json")
        attempt = packet.with_name(f"{pkt}.attempt.json")
        if verdict.exists() or attempt.exists() or packet.with_name(f"{pkt}.failed.txt").exists():
            skipped += 1
            continue
        attempt.write_text(json.dumps({"judge": judge["label"], "pkt": pkt, "client_version": version}) + "\n")
        cmd =["cursor-agent", "-p", "--output-format", "text", "--model", judge["model"], "--mode", "ask",
               "--sandbox", "enabled", "--force", "--trust", "--workspace", str(packet.parent),
               f"Read the file {pkt}.md in this workspace (and the image file it names, if any) and judge exactly as it "
               "instructs. Output ONLY the JSON verdict object, nothing else."]
        try:
            res = runner(cmd, capture_output=True, text=True, timeout=timeout_s)
            out, ok = res.stdout or "", res.returncode == 0
        except subprocess.TimeoutExpired:
            out, ok = "", False
        parsed = jp.parse_verdict(out)
        if ok and parsed["choice"] is not None:
            verdict.write_text(json.dumps(_seal(packet, parsed["choice"], parsed.get("rationale"), judge, version,
                                                prompt_sha.get(pkt), frozen_sha=frozen_sha)) + "\n")
            written += 1
        else:
            packet.with_name(f"{pkt}.failed.txt").write_text(out)
            failed += 1
    (root / "provenance.json").write_text(json.dumps(dict(judge, client_version=version), indent=1) + "\n")
    return {"written": written, "failed": failed, "skipped": skipped, "client_version": version}


def item_scores(rows, build="s"):
    """{item: {score, n, missing}}: ON 1 / tie 0.5 / OFF 0 per verdict (choices are in the SHOWN order: in BA the pair's b
    is shown as "A"), averaged over judges × orders; a missing / unparseable verdict is counted, never scored."""
    on_tune = tunes(build)[1]
    out = {}
    for r in rows:
        s = out.setdefault(r["item_id"], {"sum": 0.0, "n": 0, "missing": 0})
        choice = r.get("choice")
        if choice not in ("A", "B", "tie"):
            s["missing"] += 1
            continue
        s["n"] += 1
        if choice == "tie":
            s["sum"] += 0.5
            continue
        shown = (r["a_key"], r["b_key"]) if r["order"] == "AB" else (r["b_key"], r["a_key"])
        chosen = shown[0] if choice == "A" else shown[1]
        s["sum"] += 1.0 if f"@{on_tune}::" in chosen else 0.0
    return {k: {"score": (v["sum"] / v["n"]) if v["n"] else None, "n": v["n"], "missing": v["missing"]}
            for k, v in out.items()}


def _fit(data):
    import numpy as np
    from scipy.optimize import minimize

    y = np.array([d["score"] for d in data], dtype=float)
    x = np.array([d["log_len_ratio"] for d in data], dtype=float)

    def nll(theta):
        z = theta[0] + theta[1] * x
        p = 1.0 / (1.0 + np.exp(-z))
        eps = 1e-12
        return -np.sum(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)) + 1e-6 * np.sum(theta**2)

    res = minimize(nll, np.zeros(2), method="L-BFGS-B")
    return float(res.x[0]), float(res.x[1])


def length_adjusted(data, n_boot=10000, seed=426):
    """C161: P(ON preferred at equal length) = sigmoid(beta) of score ~ beta + gamma * log(len_ON / len_OFF), with an
    item-cluster bootstrap 95 % interval (rows sharing an item resample together); raw = the plain mean score."""
    import numpy as np

    beta, gamma = _fit(data)
    clusters = {}
    for d in data:
        clusters.setdefault(d["item"], []).append(d)
    keys = sorted(clusters)
    rng = np.random.default_rng(seed)
    boot = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        sample = [d for i in pick for d in clusters[keys[i]]]
        b, _ = _fit(sample)
        boot.append(1.0 / (1.0 + math.exp(-b)))
    lo, hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    return {
        "raw": float(np.mean([d["score"] for d in data])),
        "adjusted": 1.0 / (1.0 + math.exp(-beta)),
        "gamma": gamma,
        "ci": (lo, hi),
        "n_items": len(keys),
        "n_boot": n_boot,
        "seed": seed,
    }


# ===================================================================================================== A7 (P613 step 3)
# `docs/specs/p613-step3-contract.md`: one blind packet per B8-accepted, both-pass, non-identical A7 item (session, id); the
# two final-tree diffs against the exercise start tree + the mechanical tool-use counts; frozen (FROZEN.json) before any
# verdict exists. Verdicts are sealed / ingested only against the frozen packets (`check_frozen`).
A7_BUILD = "s2"
A7_MODEL_LABEL = "entry"            # the make_pairs key prefix; never the registry name (no model name in any output)
A7_SESSIONS = ("s1", "s2")
A7_RUBRIC = "code"
A7_VERSION = "p613-step3"
A7_MODALITY = "text"
FROZEN_NAME = "FROZEN.json"
FROZEN_FIXED = ("README_JUDGE.md", "manifest.jsonl")     # + every manifest packet: the frozen set (nothing else)
WAVE1_PANEL_KINDS = ("math500", "cjudge", "vision", "reasoning")
WAVE1_ELIGIBLE_RULE = {
    "math500": "both execution-correct (lenient score 1.0 in both arms, regraded through bench.grade)",
    "cjudge": "every B8-accepted key", "vision": "every B8-accepted key",
    "reasoning": "both strict draws (score == 1.0 and budget_hit is False and finish_reason == 'stop' in both arms)"}
B8_REL = "benchmark/results/p426/B8.json"                # the production CLI reads only these committed files
UNIVERSE_REL = "benchmark/m62/universe.json"
_INSTRUCTIONS = ".docs/instructions.md"
_APPEND = ".docs/instructions.append.md"
_NO_NEWLINE = "\n\\ No newline at end of file\n"


def _refusal(msg):
    from bench.p426_verify import RefusalError

    return RefusalError(msg)


def _leak_names():
    from bench.p426_verify import ENTRY

    return [ENTRY, f"{ENTRY}-mtp-drafter", f"caslca/{ENTRY}"]


def _a7_context(results_root, b8):
    """B8 (`all` record) inputs re-verified, accepted paired sessions loaded through `p426_verify.load_attempt` (rows via
    `bench.chain_rows`)."""
    from bench import p426_signals as S
    from bench import p426_verify as V

    if not isinstance(b8, dict) or not isinstance(b8.get("axes"), dict) or not isinstance(b8["axes"].get("A7"), dict):
        raise _refusal("B8.json is not an `all` verifier record with axes.A7")
    a7 = b8["axes"]["A7"]
    root = Path(results_root)
    by_session = S._check_b8(root, a7)
    reader = V.Reader(root)
    atts = {}
    for s in A7_SESSIONS:
        rec = by_session[s]
        if rec.get("accepted"):
            atts[s] = {arm: V.load_attempt(reader, rec.get(arm), s, f"pair {s} {arm} {rec.get(arm)}")
                       for arm in ("off", "on")}
    S._covered(reader, a7["inputs"])
    return dict(root=root, by_session=by_session, atts=atts)


def _passed(att, rid):
    return (att["rows"].get(rid) or {}).get("passed") is True


def _a7_select(results_root, b8, ctx=None):
    """`a7_select` over a cached `_a7_context` (None: built here)."""
    part = _a7_partition(results_root, b8, ctx)
    items = [(s, rid) for s in A7_SESSIONS for rid in part[s]["items"]]
    excluded = {}
    for s in A7_SESSIONS:
        p = part[s]
        excluded[s] = {"identical": len(p["identical"]),
                       "one-arm-pass": {"n": len(p["one-arm-pass"]), "ids": list(p["one-arm-pass"])},
                       "neither-pass": {"n": len(p["neither-pass"]), "ids": list(p["neither-pass"])},
                       "rejected key": p["rejected key"]}
        if "rejected pair" in p:
            excluded[s]["rejected pair"] = p["rejected pair"]
    return items, excluded


def a7_select(results_root, b8):
    """``(items, excluded)``: items ``(session, id)`` = B8-accepted keys with ``passed is True`` in both arms and
    ``identical`` false; ``excluded[session]`` = {identical: n, one-arm-pass: {n, ids}, neither-pass: {n, ids},
    rejected key: n} (+ ``rejected pair`` reasons when B8 rejected the session)."""
    return _a7_select(results_root, b8)


def a7_partition(results_root, b8):
    """{session: {items, identical, one-arm-pass, neither-pass: [ids sorted], rejected key: n}} (the a7_select rule)."""
    return _a7_partition(results_root, b8)


def _a7_partition(results_root, b8, ctx=None):
    """`a7_partition` over a cached `_a7_context` (None: built here)."""
    ctx = ctx or _a7_context(results_root, b8)
    out = {}
    for s in A7_SESSIONS:
        rec = ctx["by_session"][s]
        ex = {"items": [], "identical": [], "one-arm-pass": [], "neither-pass": [],
              "rejected key": len(rec.get("keys_rejected") or [])}
        out[s] = ex
        if not rec.get("accepted"):
            ex["rejected pair"] = list(rec.get("reasons") or ["rejected"])
            continue
        keys = rec.get("keys")
        if not isinstance(keys, list):
            raise _refusal(f"B8.json pair {s} has no keys list")
        off, on = ctx["atts"][s]["off"], ctx["atts"][s]["on"]
        seen = set()
        for k in sorted(keys, key=lambda k: str(k.get("key") if isinstance(k, dict) else k)):
            key = k.get("key") if isinstance(k, dict) else None
            if not (isinstance(key, list) and len(key) == 2 and key[0] == s and isinstance(key[1], str)):
                raise _refusal(f"B8.json pair {s}: key {key!r} is not [{s!r}, <id>]")
            rid = key[1]
            if rid in seen:
                raise _refusal(f"B8.json pair {s}: key {rid} listed twice")
            seen.add(rid)
            p_off, p_on = _passed(off, rid), _passed(on, rid)
            if p_off and p_on:
                if k.get("identical") is True:
                    ex["identical"].append(rid)
                elif k.get("identical") is False:
                    ex["items"].append(rid)
                else:
                    raise _refusal(f"B8.json pair {s}: key {rid} has no boolean identical")
            else:
                ex["one-arm-pass" if (p_off or p_on) else "neither-pass"].append(rid)
    return out


def _git_show(top, ref, path):
    from bench import p426_verify as V

    return V.git_bytes(top, ["show", f"{ref}:{path}"], f"evidence {path}")


def _text(data, what):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise _refusal(f"{what} is not UTF-8") from None


def _lines(text):
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def _udiff(rel, old, new):
    import difflib

    a = _lines(_text(old, f"start file {rel}")) if old is not None else []
    b = _lines(_text(new, f"final-tree file {rel}")) if new is not None else []
    out = []
    for line in difflib.unified_diff(a, b, fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3):
        out.append(line if line.endswith("\n") else line + _NO_NEWLINE)
    return "".join(out)


def _safe_rel(rel, what):
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel or ".." in rel.split("/"):
        raise _refusal(f"{what}: {rel!r} is not a relative path inside the exercise")
    return rel


class _StartTree:
    """`$POLYGLOT_DIR/<lang>/exercises/practice/<name>/<rel>`; every file used must hash to `prepared[rel]`."""

    def __init__(self, polyglot_root, rid, entry):
        lang, name = rid.split("/", 1)
        self.dir = Path(polyglot_root) / lang / "exercises" / "practice" / name
        self.rid, self.prepared = rid, entry.get("prepared")
        if not isinstance(self.prepared, dict) or not self.prepared:
            raise _refusal(f"universe item {rid} has no prepared map")

    def read(self, rel):
        _safe_rel(rel, f"start tree {self.rid}")
        want = self.prepared.get(rel)
        if not isinstance(want, str):
            raise _refusal(f"start tree {self.rid}: {rel} is not in the universe prepared map")
        try:
            data = (self.dir / rel).read_bytes()
        except OSError:
            raise _refusal(f"start tree {self.rid}: {rel} is missing") from None
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise _refusal(f"start tree {self.rid}: {rel} sha256 {got} != universe prepared {want}")
        return data


def _a7_task(entry, start):
    parts = [_text(start.read(_INSTRUCTIONS), _INSTRUCTIONS).strip("\n")]
    if _APPEND in entry["prepared"]:
        parts.append(_text(start.read(_APPEND), _APPEND).strip("\n"))
    return ("### Task\n\n" + "\n\n".join(parts) + "\n\n"
            f"Solution file: `{entry['solution']}`. Test file: `{entry['test']}`.\n\n"
            "### Grader\n\nBoth solutions pass every test.")


def _run_id(row, rid):
    tree = row.get("final_tree") if isinstance(row, dict) else None
    mpath = tree.get("manifest") if isinstance(tree, dict) else None
    lang, _, item = rid.partition("/")
    if isinstance(mpath, str):
        p = Path(mpath)
        if p.name == "manifest.json" and p.parent.name == f"{lang}__{item}.final_tree" and "." in p.parent.parent.name:
            return p.parent.parent.name.rsplit(".", 1)[1]
    raise _refusal(f"row {rid}: final_tree.manifest names no run directory")


def _a7_final_tree(ctx, att, row, rid, b8_sha, top, ref):
    """({rel: bytes}, [missing rels], events bytes) — manifest from `main` (sha == row == B8), objects and the events
    file from the evidence ref (each object hashes to its name, the events file to `evidence_sha256.events`)."""
    from bench import p426_verify as V

    lang, _, item = rid.partition("/")
    prefix = ctx.get("prefix", V.REPO_PREFIX)        # M76 (lever kv): the KV harvest prefix
    run = _run_id(row, rid)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", run):
        raise _refusal(f"row {rid}: run id {run!r} is not a plain name")
    stem = f"{V.WAVE}/{att['name']}/evidence/{run}/{lang}__{item}"
    mpath = ctx["root"] / f"{stem}.final_tree" / "manifest.json"
    try:
        mbytes = mpath.read_bytes()
    except OSError:
        raise _refusal(f"{att['name']} {rid}: final-tree manifest is missing") from None
    msha = hashlib.sha256(mbytes).hexdigest()
    row_sha = (row.get("final_tree") or {}).get("manifest_sha256")
    if msha != row_sha or msha != b8_sha:
        raise _refusal(f"{att['name']} {rid}: final-tree manifest sha256 {msha} != row {row_sha} / B8 {b8_sha}")
    try:
        manifest = json.loads(mbytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _refusal(f"{att['name']} {rid}: final-tree manifest is unreadable JSON") from None
    files = manifest.get("files") if isinstance(manifest, dict) else None
    missing = manifest.get("missing", []) if isinstance(manifest, dict) else None
    if not isinstance(files, dict) or not isinstance(missing, list):
        raise _refusal(f"{att['name']} {rid}: final-tree manifest has no files map / missing list")
    tree = {}
    for rel, sha in sorted(files.items()):
        _safe_rel(rel, f"{att['name']} {rid} final tree")
        if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
            raise _refusal(f"{att['name']} {rid}: final-tree object name {sha!r} is not a sha256")
        data = _git_show(top, ref, f"{prefix}{stem}.final_tree/objects/{sha}")
        got = hashlib.sha256(data).hexdigest()
        if got != sha:
            raise _refusal(f"{att['name']} {rid}: final-tree object {rel} hashes to {got}, not its name {sha}")
        tree[rel] = data
    for rel in missing:
        _safe_rel(rel, f"{att['name']} {rid} final tree missing")
    published = f"{prefix}{stem}.events.jsonl"
    events = _git_show(top, ref, published)
    ev_sha = row.get("evidence_sha256")
    want = ev_sha.get("events") if isinstance(ev_sha, dict) else None
    got = hashlib.sha256(events).hexdigest()
    if got != want:
        # The evidence branch holds the SCRUBBED events file: the row's sha is the raw file's. Bound through the
        # attempt's (B8-verified, self-hashed) HARVEST.json: raw sha == row, published sha == these bytes.
        recs = [f for f in (att["harvest"].get("files") or []) if isinstance(f, dict) and f.get("published") == published
                and f.get("destination") == "evidence"]
        if len(recs) != 1 or recs[0].get("sha256") != want or recs[0].get("published_sha256") != got:
            raise _refusal(f"{att['name']} {rid}: events file sha256 {got} != row evidence_sha256.events {want} and no "
                           "single HARVEST record binds the published (scrubbed) bytes to that raw sha")
    return tree, sorted(set(missing) - set(tree)), events


def _a7_diff(entry, tree, missing, start, where):
    """Unified diffs (sorted by path) of every final-tree file that differs from the start tree or is new (+ files the
    manifest lists missing); a protected test file that differs refuses."""
    protected = set(entry.get("protected") or {}) | {entry["test"]}
    prepared = entry["prepared"]
    out = []
    for rel in sorted(set(tree) | set(missing)):
        new = tree.get(rel)
        old = start.read(rel) if rel in prepared else None
        if new == old:
            continue
        if rel in protected:
            raise _refusal(f"{where}: protected test file {rel} differs from the start tree")
        out.append(_udiff(rel, old, new))
    return "".join(out)


def _a7_tools(events, where):
    counts = {}
    for n, line in enumerate(_text(events, f"{where} events").split("\n"), 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            raise _refusal(f"{where}: events line {n} is not JSON") from None
        if isinstance(ev, dict) and ev.get("type") == "tool_use":
            tool = ev["part"].get("tool") if isinstance(ev.get("part"), dict) else None
            if not isinstance(tool, str) or not tool:
                raise _refusal(f"{where}: events line {n} is a tool_use with no part.tool")
            counts[tool] = counts.get(tool, 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"


def _fence(text):
    runs = [len(m) for m in re.findall(r"`+", text)]
    return "`" * max(3, max(runs, default=0) + 1)


def _a7_response(diff, tools):
    f = _fence(diff)
    return (f"### Solution (unified diff against the exercise start tree)\n\n{f}diff\n{diff}{f}\n\n"
            f"### Tool use (tool-call names and counts)\n\n{tools}")


def _load_universe(universe_path):
    try:
        doc = json.loads(Path(universe_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise _refusal("universe file is missing or unreadable") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), dict):
        raise _refusal("universe file has no items map")
    return doc["items"]


def a7_packet(results_root, b8, item, evidence_ref, polyglot_root, universe_path, repo):
    """{"task", "off", "on", "len_off", "len_on"} for one (session, id); len_* = characters of that arm's diff (the
    packet carries that diff verbatim: no rewriting)."""
    from bench import p426_verify as V

    top = V.repo_top(repo)
    return _a7_packet(_a7_context(results_root, b8), item, polyglot_root, universe_path,
                      (top, V.resolve_commit(top, evidence_ref, "--evidence-ref")))


def _a7_packet(ctx, item, polyglot_root, universe_path, top_ref):
    session, rid = item
    if session not in ctx["atts"]:
        raise _refusal(f"A7 item {session}/{rid}: session {session} is not a B8-accepted pair")
    keys = {tuple(k["key"]): k for k in ctx["by_session"][session].get("keys") or []
            if isinstance(k, dict) and isinstance(k.get("key"), list)}
    krec = keys.get((session, rid))
    if krec is None:
        raise _refusal(f"A7 item {session}/{rid} is not a B8-accepted key")
    entry = _load_universe(universe_path).get(rid)
    if not isinstance(entry, dict) or not all(isinstance(entry.get(f), str) for f in ("solution", "test")):
        raise _refusal(f"universe has no entry (solution / test) for {rid}")
    start = _StartTree(polyglot_root, rid, entry)
    top, ref = top_ref
    out = {"task": _a7_task(entry, start)}
    for arm in ("off", "on"):
        att = ctx["atts"][session][arm]
        row = att["rows"].get(rid)
        where = f"{att['name']} {rid}"
        if row is None or row.get("passed") is not True:
            raise _refusal(f"{where}: not a passing row (A7 packets are both-pass)")
        tree, missing, events = _a7_final_tree(ctx, att, row, rid, krec.get(f"{arm}_manifest_sha256"), top, ref)
        diff = _a7_diff(entry, tree, missing, start, where)
        if not diff:
            raise _refusal(f"{where}: the final tree does not differ from the start tree (empty diff)")
        out[arm] = _a7_response(diff, _a7_tools(events, where))
        out[f"len_{arm}"] = len(diff)
    return out


def _strict_draw(row):
    """The A4 strict-draw predicate (`p426_signals_wave1` A4): score 1.0, no budget hit, finish_reason stop."""
    row = row or {}
    return row.get("score") == 1.0 and row.get("budget_hit") is False and row.get("finish_reason") == "stop"


def _w1_eligible_fn(W, kind, block, ids, legs):
    """The E3 panel-eligibility predicate of one accepted Wave 1 pair (item id -> (eligible, one arm only))."""
    if kind == "math500":
        planned = ids["math500"][block]
        le = {arm: W._a1_arm(legs[(kind, block, arm)], planned)[1] for arm in ("off", "on")}
        ok = {arm: (lambda x, s=le[arm]: s.get(x) == 1.0) for arm in ("off", "on")}
    elif kind == "reasoning":
        rows = {arm: W._row_map(legs[(kind, block, arm)]) for arm in ("off", "on")}
        ok = {arm: (lambda x, r=rows[arm]: _strict_draw(r.get(json.dumps(x)))) for arm in ("off", "on")}
    else:
        return lambda x: (True, False)
    return lambda x: (ok["off"](x) and ok["on"](x), ok["off"](x) != ok["on"](x))


def wave1_eligibility(rows_root, b8):
    """E3: the panel-eligible Wave 1 keys over the B8-accepted pairs — A1 both correct, A2 / A3 every key, A4 both strict
    draws (`WAVE1_ELIGIBLE_RULE`); keys recomputed and required equal to B8's, every input read covered by B8.json. An
    eligible key must be C217-identical (a non-identical one needs a packet the step-3 contract does not define: refused);
    the others are "not both correct", excluded and counted."""
    from bench import p426_signals_wave1 as W
    from bench import p426_verify as V

    if not isinstance(b8, dict) or not isinstance(b8.get("axes"), dict) or not isinstance(b8.get("inputs"), dict):
        raise _refusal("B8.json is not an `all` verifier record")
    rows_root = Path(rows_root)
    V.check_roots(rows_root / "p426", rows_root)                 # A1 regrades through bench.grade
    rec_by = W._check_b8_pairs(b8["axes"].get("wave1"))
    reader = V.Reader(rows_root, confine=True)
    ids = V.load_ids(reader)
    per_axis, per_pair = {}, {}
    for kind in WAVE1_PANEL_KINDS:
        ax = V.W1_AXIS[kind]
        acc = per_axis.setdefault(ax, dict(rule=WAVE1_ELIGIBLE_RULE[kind], keys=0, eligible=0, identical=0,
                                           not_both_correct=0, not_both_correct_keys=[], one_arm_correct=0,
                                           pairs_rejected=[]))
        for block in V.W1_BLOCKS:
            rec = rec_by[(kind, block)]
            if not rec.get("accepted"):
                acc["pairs_rejected"].append(block)
                continue
            legs = {(kind, block, arm): V.load_w1_leg(reader, kind, arm, block) for arm in ("off", "on")}
            W._accepted_keys(kind, block, rec, ids, legs)          # B8's keys, recomputed
            fn = _w1_eligible_fn(W, kind, block, ids, legs)
            pp = dict(keys=0, eligible=0, identical=0, not_both_correct=0)
            for k in rec["keys"]:
                key = k["key"]
                eligible, one_arm = fn(key[1])
                pp["keys"] += 1
                if not eligible:
                    pp["not_both_correct"] += 1
                    acc["not_both_correct_keys"].append(key)
                    acc["one_arm_correct"] += int(one_arm)
                    continue
                if k.get("identical") is not True:
                    raise _refusal(f"Wave 1 {kind} {block} key {key}: panel-eligible and not identical; non-identical "
                                   "Wave 1 keys need packets (not in the step-3 contract)")
                pp["eligible"] += 1
                pp["identical"] += 1
            per_pair[f"{kind}/{block}"] = pp
            for f in ("keys", "eligible", "identical", "not_both_correct"):
                acc[f] += pp[f]
    for rel, sha in sorted(reader.inputs.items()):
        if b8["inputs"].get(rel) != sha:
            raise _refusal(f"input {rel} is not covered by B8.json (B8 {b8['inputs'].get(rel)!r}, now {sha})")
    tot = {f: sum(a[f] for a in per_axis.values()) for f in ("keys", "eligible", "identical", "not_both_correct")}
    return dict(tot, per_axis=per_axis, per_pair=dict(sorted(per_pair.items())))


# ------------------------------------------------------------------------------------------------- packets (fix 6)
def _a7_leaks(text):
    """Every identity hit in a packet text: the model names, `LEAK_PATTERNS`, the family tokens and template tags of
    `judge_pairwise` (case-insensitive). Nothing is redacted: a hit refuses the export."""
    lowered = text.lower()
    hits = [n for n in _leak_names() if n.lower() in lowered]
    hits += [p for p in LEAK_PATTERNS if re.search(p, text, re.I)]
    if jp._FAMILY_RE.search(text):
        hits.append("family-token")
    if jp._TEMPLATE_TAG_RE.search(text):
        hits.append("template-tag")
    return hits


def _a7_write_packets(the_pairs, judge_labels, prompts, out_dir, batch_size=10):
    """`judge_pairwise.export_packets`' layout (ids, batches, packet markdown, README_JUDGE.md, manifest.jsonl) with the
    solution texts VERBATIM (no `strip_model_names`) and out_dir-relative manifest paths; any leak in any packet refuses
    before a file is written."""
    system = RUBRICS[A7_RUBRIC]
    prompt_sha = rubric_sha(A7_RUBRIC)
    total = len(judge_labels) * len(the_pairs) * 2
    width = max(4, len(str(max(total - 1, 0))))
    counter = 0
    texts, rows = [], []
    for label in judge_labels:
        batches = (jp._order_batches([(p, "AB") for p in the_pairs], batch_size)
                   + jp._order_batches([(p, "BA") for p in the_pairs], batch_size))
        for bi, batch in enumerate(batches):
            for pair, order in batch:
                pkt = jp._pkt_id(counter, width)
                counter += 1
                first, second = (pair["a_text"], pair["b_text"]) if order == "AB" else (pair["b_text"], pair["a_text"])
                user = jp.build_user_prompt(prompts.get(pair["item_id"], ""), first, second)
                rel = f"{label}/batch{bi:02d}/{pkt}.md"
                texts.append((rel, jp.build_packet_markdown(system, user, pkt)))
                rows.append({"pkt": pkt, "judge": label, "pair_id": pair["pair_id"], "order": order,
                             "anchor_type": pair.get("anchor_type"), "expected": pair.get("expected"),
                             "item_id": pair["item_id"], "a_key": pair["a_key"], "b_key": pair["b_key"],
                             "prompt_sha": prompt_sha, "path": rel})
    leaks = [f"{rel}: {hit}" for rel, text in texts for hit in _a7_leaks(text)]
    if leaks:
        raise _refusal(f"packet export refused: packet leak (identity visible to a judge): {leaks[:5]}")
    out = Path(out_dir)
    for rel, text in texts:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text, encoding="utf-8")
    (out / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (out / "README_JUDGE.md").write_text(jp._judge_readme_text(), encoding="utf-8")
    return rows


# ---------------------------------------------------------------------------------------------- freeze (fixes 3, 11)
def _read_manifest(out):
    try:
        lines = (Path(out) / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
    except (OSError, UnicodeDecodeError, ValueError):
        raise _refusal("panel: manifest.jsonl is missing or unreadable") from None
    if not all(isinstance(r, dict) for r in rows):
        raise _refusal("panel: manifest.jsonl holds a non-object row")
    return rows


def _frozen_set(out, rows):
    """{rel} = README_JUDGE.md, manifest.jsonl and every manifest packet; a `*/batch*/p*.md` outside it refuses."""
    paths = [r.get("path") for r in rows]
    for rel in paths:
        _safe_rel(rel, "panel manifest packet path")
    stray = sorted(p.relative_to(out).as_posix() for p in out.glob("*/batch*/p*.md")
                   if p.relative_to(out).as_posix() not in set(paths))
    if stray:
        raise _refusal(f"panel: packet {stray[0]} is not in manifest.jsonl")
    return sorted(set(FROZEN_FIXED) | set(paths))


def freeze(out_dir, packets_meta, judges, rubric):
    """Writes ``<out_dir>/FROZEN.json``: the frozen set (README_JUDGE.md, manifest.jsonl, every manifest packet; sha256),
    the items (session, id, ON slot, judged lengths), the judges, the rubric sha, evidence ref, B8 sha, counts. Refuses
    when any verdict file already exists. Other files in ``out_dir`` are not frozen (and ignored)."""
    out = Path(out_dir)
    if any(out.rglob("*.verdict.json")):
        raise _refusal(f"freeze: a verdict file already exists in {out.name}: the packet set is frozen before any verdict")
    if (out / FROZEN_NAME).exists():
        raise _refusal(f"freeze: {FROZEN_NAME} already exists")
    rows = _read_manifest(out)
    files = {}
    for rel in _frozen_set(out, rows):
        if not (out / rel).is_file():
            raise _refusal(f"freeze: {rel} is missing")
        files[rel] = _sha(out / rel)
    items = list(packets_meta.get("items") or [])
    judges_rec = [{k: j.get(k) for k in ("label", "family", "client", "model")} for j in judges]
    excluded = packets_meta.get("excluded") or {}
    wave1 = packets_meta.get("wave1") or {}
    counts = dict(items=len(items), packet_files=len(rows),
                  planned_verdicts=len(items) * len(judges) * len(jp.ORDERS),
                  items_per_session={s: sum(1 for i in items if i.get("session") == s) for s in A7_SESSIONS},
                  wave1_keys=wave1.get("keys"), wave1_eligible=wave1.get("eligible"),
                  wave1_identical=wave1.get("identical"), wave1_not_both_correct=wave1.get("not_both_correct"),
                  a7_excluded={s: {k: (v["n"] if isinstance(v, dict) else len(v) if isinstance(v, list) else v)
                                   for k, v in ex.items()} for s, ex in sorted(excluded.items())})
    doc = dict(packets_meta, version=A7_VERSION, rubric=rubric, rubric_sha256=rubric_sha(rubric), judges=judges_rec,
               files=files, counts=counts)
    path = out / FROZEN_NAME
    path.write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return path


def _check_manifest(doc, rows):
    """FROZEN.json (items, ON slots, judges, rubric, counts) against manifest.jsonl, row by row."""
    def bad(msg):
        return _refusal(f"panel: {FROZEN_NAME} and manifest.jsonl disagree: {msg}")

    judges = doc.get("judges")
    if not (isinstance(judges, list) and judges and all(
            isinstance(j, dict) and all(isinstance(j.get(k), str) and j.get(k) for k in ("label", "family", "client",
                                                                                          "model")) for j in judges)):
        raise bad("judges are not a list of {label, family, client, model}")
    labels = [j["label"] for j in judges]
    if len(set(labels)) != len(labels):
        raise bad("a judge label is listed twice")
    if doc.get("rubric") not in RUBRICS or doc.get("rubric_sha256") != rubric_sha(doc["rubric"]):
        raise bad("rubric / rubric_sha256 is not a known rubric")
    if doc.get("build") != A7_BUILD:
        raise bad(f"build {doc.get('build')!r} != {A7_BUILD!r}")
    off_tune, on_tune = tunes(A7_BUILD)
    items = doc.get("items")
    if not isinstance(items, list):
        raise bad("no items list")
    meta = {}
    for it in items:
        if not (isinstance(it, dict) and it.get("session") in A7_SESSIONS and isinstance(it.get("id"), str)
                and it.get("item") == f"{it.get('session')}/{it.get('id')}" and it.get("on_slot") in ("A", "B")
                and all(isinstance(it.get(f), int) and not isinstance(it.get(f), bool) and it[f] > 0
                        for f in ("len_off", "len_on"))):
            raise bad(f"item {it!r} is malformed")
        if it["item"] in meta:
            raise bad(f"item {it['item']} is listed twice")
        meta[it["item"]] = it
    seen, pkts = {}, set()
    for r in rows:
        item = r.get("item_id")
        if item not in meta:
            raise bad(f"manifest item {item!r} is not a frozen item")
        if r.get("judge") not in labels or r.get("order") not in jp.ORDERS:
            raise bad(f"manifest row {r.get('pkt')!r}: judge / order {r.get('judge')!r} / {r.get('order')!r}")
        pkt = r.get("pkt")
        if not (isinstance(pkt, str) and re.fullmatch(r"p\d+", pkt)) or pkt in pkts:
            raise bad(f"manifest packet id {pkt!r} is malformed or repeated")
        pkts.add(pkt)
        if not (isinstance(r.get("path"), str) and re.fullmatch(re.escape(r["judge"]) + r"/batch\d{2}/" + pkt + r"\.md",
                                                               r["path"])):
            raise bad(f"manifest packet {pkt}: path {r.get('path')!r} is not <judge>/batchNN/{pkt}.md")
        if r.get("prompt_sha") != doc["rubric_sha256"]:
            raise bad(f"manifest packet {pkt}: prompt_sha != the frozen rubric sha")
        k_on, k_off = f"{A7_MODEL_LABEL}@{on_tune}::{item}", f"{A7_MODEL_LABEL}@{off_tune}::{item}"
        want = (k_on, k_off) if meta[item]["on_slot"] == "A" else (k_off, k_on)
        if (r.get("a_key"), r.get("b_key")) != want or r.get("pair_id") != f"p426-{item}":
            raise bad(f"manifest packet {pkt}: keys / pair id disagree with the frozen ON slot of {item}")
        slot = (r["judge"], r["order"])
        if slot in seen.setdefault(item, set()):
            raise bad(f"item {item}: judge x order {slot} is listed twice")
        seen[item].add(slot)
    need = {(j, o) for j in labels for o in jp.ORDERS}
    for item in meta:
        if seen.get(item, set()) != need:
            raise bad(f"item {item}: manifest judge x order slots != every frozen judge x both orders")
    counts = doc.get("counts") if isinstance(doc.get("counts"), dict) else {}
    if counts.get("items") != len(items) or counts.get("planned_verdicts") != len(rows) or \
            counts.get("packet_files") != len(rows):
        raise bad("counts (items / planned verdicts / packet files) != the manifest")


def check_frozen(out_dir):
    """FROZEN.json present; the frozen set exactly README_JUDGE.md + manifest.jsonl + every manifest packet, each
    unchanged; FROZEN cross-checked against the manifest (items, slots, judges); no packet outside the manifest; else
    RefusalError. Other files (verdicts, markers, provenance) are ignored. Returns FROZEN."""
    out = Path(out_dir)
    try:
        doc = json.loads((out / FROZEN_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise _refusal(f"panel: {FROZEN_NAME} is missing or unreadable") from None
    files = doc.get("files") if isinstance(doc, dict) else None
    if not isinstance(files, dict) or "manifest.jsonl" not in files:
        raise _refusal(f"panel: {FROZEN_NAME} lists no frozen files / manifest")
    for rel, sha in sorted(files.items()):
        _safe_rel(rel, "panel frozen file")
        p = out / rel
        if not p.is_file():
            raise _refusal(f"panel: frozen file {rel} is missing")
        got = _sha(p)
        if got != sha:
            raise _refusal(f"panel: frozen file {rel} changed (sha256 {got} != frozen {sha})")
    rows = _read_manifest(out)
    want = _frozen_set(out, rows)
    if sorted(files) != want:
        extra, missing = sorted(set(files) - set(want)), sorted(set(want) - set(files))
        raise _refusal(f"panel: the frozen file set != README_JUDGE.md + manifest.jsonl + the manifest packets "
                       f"(extra {extra[:3]}, not frozen {missing[:3]})")
    _check_manifest(doc, rows)
    return doc


# ------------------------------------------------------------------------------------------------------------ export
def a7_export(results_root, b8_path, evidence_ref, repo, polyglot_root, universe_path, judges_path, out_dir):
    """Packets + manifest + FROZEN.json into a fresh ``out_dir`` (built beside it, renamed on success). Returns FROZEN.
    Low-level (injectable paths); the CLI first requires the committed B8.json / universe (`_committed_input`)."""
    import os
    import shutil

    from bench import p426_verify as V

    out = Path(out_dir)
    if out.exists():
        raise _refusal(f"{out.name} exists: packets are exported once into a fresh directory")
    if not out.parent.is_dir():
        raise _refusal(f"the parent directory of {out.name} is missing")
    try:
        b8_bytes = Path(b8_path).read_bytes()
        b8 = json.loads(b8_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise _refusal("B8.json is missing or unreadable") from None
    try:
        judges = load_judges(judges_path, A7_MODALITY)
    except OSError:
        raise _refusal("judges file is missing or unreadable") from None
    except ValueError as exc:
        raise _refusal(f"judges: {exc}") from None
    for j in judges:
        if not all(isinstance(j.get(k), str) and j.get(k) for k in ("label", "family", "client", "model")):
            raise _refusal("judges: every judge needs label, family, client and model")
        _safe_rel(j["label"], "judge label")
    ctx = _a7_context(results_root, b8)
    wave1 = wave1_eligibility(Path(results_root).parent, b8)
    items, excluded = _a7_select(results_root, b8, ctx)
    top = V.repo_top(repo)
    top_ref = (top, V.resolve_commit(top, evidence_ref, "--evidence-ref"))
    try:
        universe_sha = hashlib.sha256(Path(universe_path).read_bytes()).hexdigest()
    except OSError:
        raise _refusal("universe file is missing or unreadable") from None
    packets = {it: _a7_packet(ctx, it, polyglot_root, universe_path, top_ref) for it in items}
    the_pairs, prompts, meta_items = [], {}, []
    on_tune = tunes(A7_BUILD)[1]
    for s in A7_SESSIONS:          # slots balanced within each session (each session is its own family member)
        sel = [(f"{s}/{rid}", packets[(s, rid)]["off"], packets[(s, rid)]["on"]) for (ss, rid) in items if ss == s]
        made = make_pairs(A7_MODEL_LABEL, sel, build=A7_BUILD)
        the_pairs += made
        for p in made:
            rid = p["item_id"].split("/", 1)[1]
            pk = packets[(s, rid)]
            prompts[p["item_id"]] = pk["task"]
            meta_items.append(dict(item=p["item_id"], session=s, id=rid,
                                   on_slot="A" if f"@{on_tune}::" in p["a_key"] else "B",
                                   len_off=pk["len_off"], len_on=pk["len_on"]))
    partial = out.parent / f".{out.name}.partial"
    if partial.exists():
        raise _refusal(f"a partial export .{out.name}.partial exists; inspect and remove it first")
    try:
        partial.mkdir()
        _a7_write_packets(the_pairs, [j["label"] for j in judges], prompts, partial)
        meta = dict(items=meta_items, evidence_ref=top_ref[1], b8_sha256=hashlib.sha256(b8_bytes).hexdigest(),
                    universe_sha256=universe_sha, build=A7_BUILD, excluded=excluded, wave1=wave1)
        freeze(partial, meta, judges, A7_RUBRIC)
        os.rename(partial, out)
    except BaseException:
        if partial.exists():
            shutil.rmtree(partial)
        raise
    return check_frozen(out)


def _committed_input(top, path, rel, flag):
    """Fix 7: ``path`` must be ``<repo top>/<rel>`` and its bytes equal ``git show HEAD:<rel>``."""
    from bench import p426_verify as V

    try:
        got, want = Path(path).resolve(), (Path(top) / rel).resolve()
    except OSError:
        raise _refusal(f"{flag} is unresolvable") from None
    if got != want:
        raise _refusal(f"{flag} must be the committed {rel} of --repo")
    try:
        data = got.read_bytes()
    except OSError:
        raise _refusal(f"{flag} {rel} is missing or unreadable") from None
    if data != V.git_bytes(top, ["show", f"HEAD:{rel}"], f"{flag} {rel} at HEAD"):
        raise _refusal(f"{flag} {rel} differs from its committed bytes at HEAD")
    return got


# ---------------------------------------------------------------------------------------- verdicts (fixes 3, 4, 5, 8)
def frozen_judge(frozen, label):
    for j in frozen.get("judges") or []:
        if j.get("label") == label:
            return j
    raise _refusal(f"judge {label!r} is not in {FROZEN_NAME}")


def _expected_seal(frozen, judge, fsha):
    """The provenance a verdict of ``judge`` must carry: from FROZEN's judge list (+ the batch directory = the judge)."""
    return dict(judge=judge["label"], family=judge["family"], client=judge["client"], model=judge["model"],
                prompt_sha=frozen["rubric_sha256"], frozen_sha256=fsha)


def _verdict_problem(doc, packet, frozen, judge, fsha):
    """None for a sealed verdict bound to this packet and FROZEN with FROZEN's provenance; else (kind, reason). A
    verdict bound to ANOTHER FROZEN.json refuses (RefusalError)."""
    bound = doc.get("frozen_sha256")
    if bound is not None and bound != fsha:
        raise _refusal(f"panel: verdict {packet.stem} ({judge['label']}) is bound to another {FROZEN_NAME} "
                       f"({bound} != {fsha})")
    if doc.get("packet_sha") != _sha(packet) or doc.get("attachment_sha") != _attachment(packet):
        return "unbound", "packet / attachment sha != the frozen packet"
    want = _expected_seal(frozen, judge, fsha)
    wrong = sorted(k for k, v in want.items() if doc.get(k) != v)
    cv = doc.get("client_version")
    if wrong or not (isinstance(cv, str) and cv.strip()):
        return "rejected", f"provenance disagrees with {FROZEN_NAME}: {wrong or ['client_version']}"
    if doc.get("choice") not in ("A", "B", "tie"):
        return "unparseable", f"choice {doc.get('choice')!r}"
    return None


def a7_ingest(out_dir):
    """(FROZEN, verdict rows, report). Each manifest packet: a failed marker → failed; no verdict → missing; unreadable /
    invalid choice → unparseable; bare (never sealed) → unsealed; not bound to the current packet → unbound; provenance
    != FROZEN's judge (label / family / model / client / prompt sha / FROZEN sha) → rejected; bound to another FROZEN →
    refusal. Row provenance comes from FROZEN, never from the verdict (except its client_version)."""
    out = Path(out_dir)
    frozen = check_frozen(out)
    fsha = _sha(out / FROZEN_NAME)
    judges = {j["label"]: j for j in frozen["judges"]}
    rows = []
    report = dict(missing=0, failed=0, unsealed=0, unbound=0, rejected=0, unparseable=0)
    for m in _read_manifest(out):
        packet = out / m["path"]
        verdict = packet.with_name(f"{m['pkt']}.verdict.json")
        if packet.with_name(f"{m['pkt']}.failed.txt").exists():
            report["failed"] += 1
            continue
        if not verdict.exists():
            report["missing"] += 1
            continue
        try:
            doc = json.loads(verdict.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ValueError):
            report["unparseable"] += 1
            continue
        if not isinstance(doc, dict):
            report["unparseable"] += 1
            continue
        if "packet_sha" not in doc:
            report["unsealed"] += 1
            continue
        judge = judges[m["judge"]]
        problem = _verdict_problem(doc, packet, frozen, judge, fsha)
        if problem is not None:
            report[problem[0]] += 1
            continue
        rows.append(dict(_expected_seal(frozen, judge, fsha), choice=doc["choice"], rationale=doc.get("rationale"),
                         client_version=doc["client_version"].strip(), packet_sha=doc["packet_sha"],
                         attachment_sha=doc.get("attachment_sha"), item_id=m["item_id"], order=m["order"],
                         a_key=m["a_key"], b_key=m["b_key"], pair_id=m["pair_id"], pkt=m["pkt"]))
    return frozen, rows, report


CLAUDE_JUDGE_CLIENT = "claude-code:blind-judge"     # the only client `a7-seal` seals (the Cursor judge runs via a7-cursor)


def _fail_marker(packet, reason, raw):
    packet.with_name(f"{packet.stem}.failed.txt").write_bytes(f"{reason}\n".encode() + raw)


def a7_seal(out_dir, label, client_version):
    """Seal the frozen judge ``label``'s bare verdicts (only a judge whose FROZEN client is ``claude-code:blind-judge``;
    any other refuses): each file alone. Bare (no ``packet_sha``) → normalised from its choice / rationale only,
    provenance from FROZEN, bound to the packet and FROZEN sha. Malformed JSON, an invalid choice, or a pre-sealed verdict
    that disagrees with FROZEN → a permanent ``<pkt>.failed.txt`` (counted missing; the verdict is never sealed or
    ingested); so does a pre-sealed verdict whose ``client_version`` != the CLI value. A correct sealed verdict is left
    as is."""
    return _seal_frozen(out_dir, check_frozen(Path(out_dir)), label, client_version)


def _seal_frozen(out_dir, frozen, label, client_version):
    """`a7_seal`'s rule against an already-checked FROZEN (shared with the KV members' `kv_seal`)."""
    out = Path(out_dir)
    judge = frozen_judge(frozen, label)
    if judge.get("client") != CLAUDE_JUDGE_CLIENT:
        raise _refusal(f"a7-seal seals only a {CLAUDE_JUDGE_CLIENT} judge; {label!r} is {judge.get('client')!r}")
    if not isinstance(client_version, str) or not client_version.strip():
        raise _refusal("a7-seal needs a non-empty --client-version")
    client_version = client_version.strip()
    fsha = _sha(out / FROZEN_NAME)
    res = dict(sealed=0, already=0, failed=0, missing=0)
    for m in _read_manifest(out):
        if m["judge"] != label:
            continue
        packet = out / m["path"]
        verdict = packet.with_name(f"{m['pkt']}.verdict.json")
        if packet.with_name(f"{m['pkt']}.failed.txt").exists():
            res["failed"] += 1
            continue
        if not verdict.exists():
            res["missing"] += 1
            continue
        raw = verdict.read_bytes()
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            doc = None
        if not isinstance(doc, dict):
            _fail_marker(packet, "a7-seal: verdict is not a JSON object", raw)
            res["failed"] += 1
            continue
        if "packet_sha" in doc:
            problem = _verdict_problem(doc, packet, frozen, judge, fsha)
            if problem is None and doc["client_version"] != client_version:
                problem = "rejected", f"client_version {doc['client_version']!r} != --client-version {client_version!r}"
            if problem is None:
                res["already"] += 1
            else:
                _fail_marker(packet, f"a7-seal: pre-sealed verdict {problem[0]}: {problem[1]}", raw)
                res["failed"] += 1
            continue
        choice = jp.parse_verdict(json.dumps({"choice": doc.get("choice")}))["choice"]
        if choice is None:
            _fail_marker(packet, f"a7-seal: invalid choice {doc.get('choice')!r}", raw)
            res["failed"] += 1
            continue
        rationale = doc.get("rationale") if isinstance(doc.get("rationale"), str) else None
        verdict.write_text(json.dumps(_seal(packet, choice, rationale, judge, client_version,
                                            frozen["rubric_sha256"], frozen_sha=fsha)) + "\n")
        res["sealed"] += 1
    return res


def a7_cursor(out_dir, label, runner=subprocess.run):
    """`run_cursor_judge` (retries 0 across invocations) for the frozen cursor-agent judge ``label``; verdicts bound to
    FROZEN.json's sha."""
    out = Path(out_dir)
    frozen = check_frozen(out)
    judge = frozen_judge(frozen, label)
    if judge.get("client") != "cursor-agent":
        raise _refusal(f"judge {label!r} is not a cursor-agent judge")
    return run_cursor_judge(out.resolve(), judge, runner=runner, frozen_sha=_sha(out / FROZEN_NAME))


# ===================================================================================================== M76 B3: lever kv
# The KV pair's panel (C161 / C206; spec v1.2 erratum "Panel, end to end"): per member one directory
# `<out>/<member>/` exported once (packets + manifest), FROZEN (bound to the B8 record's sha and every packet's sha) before any
# verdict, judged (Cursor judge: `kv-cursor`; Claude judge: the blind-judge agent, then `kv-seal`) and ingested only against the
# frozen packets. Members: A1 both correct, A2 / A3 every key, A4 both strict draws, A5 the chain-4 both-strict items (retrieval
# both-correct answers are the same five codes: excluded, stated), A7-<session> both-pass items per planned session; identical
# keys are counted (score 0.5), never judged. Two judge families are required; a single-family set is refused unless the operator
# labels it (C166 / C206), and the label is frozen and printed beside every member.
KV_PANEL_BUILD = "s3"
KV_PANEL_VERSION = "m76-b3-panel"
# S26-P17b: under the KV lever a leak is what reveals the ARM or the BOX. Both KV arms are one registry entry with MTP ON, so the MTP
# lever's arm markers (mtp, drafter, draft_kind, joint_v1) and generic path prefixes (/Users/, /home/, /private/: an API route or an
# example path in an answer) are content; the box itself is caught by `_box_identity` (its real home path and username).
KV_LEAK_PATTERNS = (r"p426", r"caslca/", r"\bm76\b", r"\btq4", r"kv_bits", r"m72_", r"\bn16\b")
KV_WAVE1_MEMBERS = ("A1", "A2", "A3", "A4", "A5")
KV_MEMBER_KIND = {"A1": "math500", "A2": "cjudge", "A3": "vision", "A4": "reasoning", "A5": "longctx"}
KV_MEMBER_RUBRIC = {"A1": "reasoning", "A2": "cjudge", "A3": "vision", "A4": "reasoning", "A5": "reasoning"}
KV_TEXT_FIELD = dict(TEXT_FIELD, longctx="content")
KV_MODEL_LABEL = "entry"            # the pair-key prefix; never the registry name
KV_A5_RULE = ("chain-4 items both strict (exact AND converged at the row's own resolved budget); retrieval items are excluded: a "
              "both-correct retrieval pair is the same five codes in both arms (nothing to judge)")


def kv_members(sessions=None):
    """The KV panel family: A1 … A5 and one A7 member per planned tg1 session (`p426_plan.kv_a7_sessions`)."""
    from bench.p426_plan import kv_a7_sessions

    return KV_WAVE1_MEMBERS + tuple(f"A7-{s}" for s in (sessions if sessions is not None else kv_a7_sessions()))


def kv_rubric(member):
    return "code" if member.startswith("A7-") else KV_MEMBER_RUBRIC[member]


def kv_tunes(ref, test):
    from bench.p426_plan import KV_NS, check_kv_pair

    check_kv_pair(ref, test)
    return f"{KV_NS}-{ref}", f"{KV_NS}-{test}"


def kv_select(axis, ref, test, correct_ref=None, correct_test=None):
    """`(items, excluded)`: items `(id, ref_text, test_text)` both arms hold, by the axis rule — math500 both correct, reasoning
    both strict draws, longctx the chain-4 items both strict (`p426_signals.a5_strict`), cjudge / vision every item."""
    from bench.p426_signals import a5_strict

    field = KV_TEXT_FIELD[axis]
    items, excluded = [], {}
    for key in sorted(set(ref) | set(test), key=str):
        if key not in ref or key not in test:
            excluded.setdefault("missing in an arm", []).append(key)
            continue
        if axis == "math500" and not (key in (correct_ref or ()) and key in (correct_test or ())):
            excluded.setdefault("not both correct", []).append(key)
            continue
        if axis == "reasoning" and not (_strict_draw(ref[key]) and _strict_draw(test[key])):
            excluded.setdefault("not both correct", []).append(str(key))
            continue
        if axis == "longctx":
            if ref[key].get("task") == "retrieval":
                excluded.setdefault("retrieval (identical codes when both correct)", []).append(key)
                continue
            if not (a5_strict(ref[key]) and a5_strict(test[key])):
                excluded.setdefault("not both correct", []).append(key)
                continue
        items.append((str(key), ref[key].get(field) or "", test[key].get(field) or ""))
    return items, excluded


def kv_make_pairs(items, ref, test, seed=426, model=KV_MODEL_LABEL):
    """One blind pair per selected item, A / B slots balanced (exactly half show the treatment as A), seeded."""
    ref_tune, test_tune = kv_tunes(ref, test)
    key_ref, key_test = f"{model}@{ref_tune}", f"{model}@{test_tune}"
    flags = jp._balanced_flags(len(items), jp._sub_rng(seed, key_ref, key_test))
    out = []
    for (item_id, ref_text, test_text), test_first in zip(items, flags):
        (ka, ta), (kb, tb) = ((key_test, test_text), (key_ref, ref_text)) if test_first else ((key_ref, ref_text), (key_test, test_text))
        out.append({"pair_id": f"m76-{item_id}", "anchor_type": None, "item_id": item_id, "a_key": f"{ka}::{item_id}",
                    "b_key": f"{kb}::{item_id}", "a_text": ta, "b_text": tb, "expected": None})
    return out


def kv_item_scores(rows, ref, test):
    """{item: {score, n, missing}}: treatment 1 / tie 0.5 / reference 0 per verdict (choices in the SHOWN order), averaged."""
    test_tune = kv_tunes(ref, test)[1]
    out = {}
    for r in rows:
        s = out.setdefault(r["item_id"], {"sum": 0.0, "n": 0, "missing": 0})
        choice = r.get("choice")
        if choice not in ("A", "B", "tie"):
            s["missing"] += 1
            continue
        s["n"] += 1
        if choice == "tie":
            s["sum"] += 0.5
            continue
        shown = (r["a_key"], r["b_key"]) if r["order"] == "AB" else (r["b_key"], r["a_key"])
        s["sum"] += 1.0 if f"@{test_tune}::" in (shown[0] if choice == "A" else shown[1]) else 0.0
    return {k: {"score": (v["sum"] / v["n"]) if v["n"] else None, "n": v["n"], "missing": v["missing"]} for k, v in out.items()}


def kv_judges(path, modality, single_family_label=None):
    """`(judges, single_family)`: the box's two judges of `modality` from two families; a single-family set (or one judge) is
    refused unless the operator labels it (`single_family_label`, C166 / C206) — then `single_family` = {label, family}."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise _refusal("judges file is missing or unreadable") from None
    judges = doc.get(modality) if isinstance(doc, dict) else None
    if not isinstance(judges, list) or not judges:
        raise _refusal(f"judges: no {modality} judges configured")
    for j in judges:
        if not (isinstance(j, dict) and all(isinstance(j.get(k), str) and j.get(k) for k in ("label", "family", "client", "model"))):
            raise _refusal("judges: every judge needs label, family, client and model")
        _safe_rel(j["label"], "judge label")
    if len({j["label"] for j in judges}) != len(judges):
        raise _refusal("judges: a judge label is listed twice")
    families = {j["family"] for j in judges}
    if len(judges) == 2 and len(families) == 2:
        return judges, None
    label = (single_family_label or "").strip()
    if not label:
        raise _refusal(f"judges: {modality} needs two judges from two different families (C166 / C206); a single-family "
                       "set needs the operator's label (--single-family-label)")
    if len(judges) > 2:
        raise _refusal(f"judges: {modality} lists {len(judges)} judges (one or two)")
    return judges, dict(label=label, families=sorted(families))


def _box_identity():
    """S26-P17b: this machine's real home path and username (read at run time, never written down)."""
    import getpass

    return str(Path.home()), getpass.getuser()


def _kv_leaks(text, extra_names=()):
    lowered = text.lower()
    hits = [n for n in list(_leak_names()) + list(extra_names) if n.lower() in lowered]
    hits += [p for p in KV_LEAK_PATTERNS if re.search(p, text, re.I)]
    home, user = _box_identity()
    if home in text:
        hits.append("box-home")
    if user and re.search(r"(?<![\w.-])" + re.escape(user) + r"(?![\w-])", text):
        hits.append("box-user")
    # S26-P17: no `family-token` check under the KV lever — both arms are ONE registry entry (they differ only in the KV mode),
    # so a model-family token in an answer (a topic: "Qwen2.5", "NVIDIA") cannot tell a judge which arm wrote it; excluding such  # allow-shorthand: quotes model output
    # items would select on the arms' outputs. The KV / arm identifiers above, registry names and template tags still refuse.
    if jp._TEMPLATE_TAG_RE.search(text):
        hits.append("template-tag")
    return hits


def _kv_write_packets(the_pairs, judge_labels, prompts, out_dir, rubric, attachments=None, batch_size=10):
    """`_a7_write_packets`' layout (out_dir-relative manifest paths, texts verbatim) with the member's rubric and the KV leak
    patterns; an attachment (A3: the image) is copied beside each packet; any leak refuses before a file is written."""
    import shutil

    system = RUBRICS[rubric]
    prompt_sha = rubric_sha(rubric)
    total = len(judge_labels) * len(the_pairs) * 2
    width = max(4, len(str(max(total - 1, 0))))
    counter = 0
    texts, rows, copies = [], [], []
    for label in judge_labels:
        batches = (jp._order_batches([(p, "AB") for p in the_pairs], batch_size)
                   + jp._order_batches([(p, "BA") for p in the_pairs], batch_size))
        for bi, batch in enumerate(batches):
            for pair, order in batch:
                pkt = jp._pkt_id(counter, width)
                counter += 1
                first, second = (pair["a_text"], pair["b_text"]) if order == "AB" else (pair["b_text"], pair["a_text"])
                prompt = prompts.get(pair["item_id"])
                if not isinstance(prompt, str) or not prompt.strip():
                    raise _refusal(f"packet export refused: no task prompt for item {pair['item_id']}")
                rel = f"{label}/batch{bi:02d}/{pkt}.md"
                att = (attachments or {}).get(pair["item_id"])
                if att is not None:
                    src = Path(att)
                    if not src.is_file():
                        raise _refusal(f"packet export refused: attachment for {pair['item_id']} is missing")
                    copies.append((src, f"{label}/batch{bi:02d}/{pkt}{src.suffix}"))
                    prompt = prompt + f"\n\n(The image is the file {pkt}{src.suffix} beside this packet.)"
                texts.append((rel, jp.build_packet_markdown(system, jp.build_user_prompt(prompt, first, second), pkt)))
                rows.append({"pkt": pkt, "judge": label, "pair_id": pair["pair_id"], "order": order, "anchor_type": None,
                             "expected": None, "item_id": pair["item_id"], "a_key": pair["a_key"], "b_key": pair["b_key"],
                             "prompt_sha": prompt_sha, "path": rel})
    leaks = [f"{rel}: {hit}" for rel, text in texts for hit in _kv_leaks(text)]
    if leaks:
        raise _refusal(f"packet export refused: packet leak (identity visible to a judge): {leaks[:5]}")
    out = Path(out_dir)
    for rel, text in texts:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text, encoding="utf-8")
    for src, rel in copies:
        shutil.copyfile(src, out / rel)
    (out / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (out / "README_JUDGE.md").write_text(jp._judge_readme_text(), encoding="utf-8")
    return rows


# ------------------------------------------------------------------------------------- packet inputs (erratum v1.3)
KV_INPUT_SOURCE = {"A1": "math500 problem (bench.benchmarks math500)", "A2": "cjudge prompt (bench.benchmarks cjudge)",
                   "A3": "vision_gate turn-1 question + corpus image (vision_gate)",
                   "A4": "vartrack question of the task seed (bench.reasoning; never the context)",
                   "A5": "vartrack question of the item's task seed (bench.reasoning; never the context)",
                   "A7": "polyglot start-tree task (_a7_packet)"}


class KVInputSources:
    """The benchmark inputs the packets are derived from (lazy imports; a test substitutes its own)."""

    def __init__(self):
        self._cache, self._ds = {}, {}

    def _memo(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def math500(self):
        from bench import benchmarks

        return self._memo("math500", lambda: {it["id"]: it["prompt"] for it in benchmarks.load("math500")})

    def cjudge(self):
        from bench import benchmarks

        return self._memo("cjudge", lambda: {it["id"]: it["prompt"] for it in benchmarks.load("cjudge")})

    def vision_rows(self):
        import vision_gate

        return self._memo("vision", lambda: {r["id"]: r for r in vision_gate.load_corpus(vision_gate.DEFAULT_CORPUS)})

    def vision_question(self):
        import vision_gate

        return vision_gate.TURN1_TEXT

    def resolve_image(self, row):
        import vision_gate

        return vision_gate.resolve_image(row, self._ds)

    def vartrack_question(self, seed, chain_len):
        from bench.reasoning import build_vartrack

        return build_vartrack(1, 1.0, chain_len=chain_len, seed=seed)[2]


def _input_sha(member, item, prompt_sha, attachment_sha):
    doc = dict(member=member, item=str(item), prompt_sha256=prompt_sha, attachment_sha256=attachment_sha)
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _input_record(member, item, prompt, source, attachment=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise _refusal(f"{member} {item}: the benchmark input is empty")
    psha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    asha = _sha(attachment) if attachment is not None else None
    return dict(item=str(item), source=source, prompt=prompt, prompt_sha256=psha, attachment_sha256=asha,
                attachment_suffix=Path(attachment).suffix if attachment is not None else None,
                input_sha256=_input_sha(member, item, psha, asha))


def kv_member_inputs(member, item_ids, ids, sources, arm_rows=None):
    """{item: (input record, attachment path | None)} of a Wave 1 member, derived from the benchmark inputs of the items B8
    covers (A1 the Math500 problem, A2 the cjudge prompt, A3 the vision_gate question + the corpus image, which must be the one
    both arms' rows record, A4 / A5 the vartrack question only); an item without its input refuses."""
    out = {}
    src = KV_INPUT_SOURCE[member]
    lc = ids.get("longctx_items") or {}
    for item in item_ids:
        att = None
        if member == "A1":
            prompt = sources.math500().get(item)
        elif member == "A2":
            prompt = sources.cjudge().get(item)
        elif member == "A3":
            row = sources.vision_rows().get(item)
            if row is None:
                raise _refusal(f"A3 {item}: not a vision_gate corpus item")
            att = Path(sources.resolve_image(row))
            if not att.is_file():
                raise _refusal(f"A3 {item}: the corpus image does not resolve")
            got = _sha(att)
            seen = {arm: (r or {}).get("image_sha256") for arm, r in ((arm_rows or {}).get(item) or {}).items()}
            if len(seen) != 2 or any(v != got for v in seen.values()):
                raise _refusal(f"A3 {item}: the corpus image sha {got} is not the one both arms' rows record ({seen})")
            prompt = sources.vision_question()
        elif member == "A4":
            try:
                seed = int(item)
            except (TypeError, ValueError):
                raise _refusal(f"A4 {item}: not a task seed") from None
            prompt = sources.vartrack_question(seed, 4)
        elif member == "A5":
            it = lc.get(item)
            if it is None or it.get("task") != "reasoning":
                raise _refusal(f"A5 {item}: not a chain-4 item of m76/ids.json")
            prompt = sources.vartrack_question(it["task_seed"], ids.get("longctx_chain_len") or 4)
        else:
            raise _refusal(f"{member}: no benchmark input rule")
        if prompt is None:
            raise _refusal(f"{member} {item}: no benchmark input for the item (not in {src})")
        out[str(item)] = (_input_record(member, item, prompt, src, att), att)
    return out


def kv_validate_prompts(member, given, inputs):
    """A caller's `--prompts` entries for `member`: every entry names an item of the member and its sha equals the derived
    input's; else refused (never used in a packet)."""
    for item, text in sorted((given or {}).items()):
        rec = inputs.get(str(item))
        if rec is None:
            raise _refusal(f"--prompts {member} {item}: not an item this member judges")
        if not isinstance(text, str) or hashlib.sha256(text.encode("utf-8")).hexdigest() != rec[0]["prompt_sha256"]:
            raise _refusal(f"--prompts {member} {item}: != the benchmark input (sha {rec[0]['prompt_sha256']})")


def _kv_check_inputs(doc, rows, out, name):
    """FROZEN `inputs`: one record per frozen item, keyed by and naming its item id, self-consistent shas; every packet of the item
    carries the prompt verbatim and exactly its attachment."""
    def bad(msg):
        return _refusal(f"panel {name}: packet inputs: {msg}")

    inputs = doc.get("inputs")
    items = {it["item"] for it in doc.get("items") or []}
    if not isinstance(inputs, dict) or set(inputs) != items:
        raise bad("FROZEN.json has no per-item input record for every frozen item")
    member = doc.get("member")
    for item, rec in inputs.items():
        if not isinstance(rec, dict) or rec.get("item") != item or not isinstance(rec.get("prompt"), str):
            raise bad(f"{item}: malformed or keyed to another item")
        psha = hashlib.sha256(rec["prompt"].encode("utf-8")).hexdigest()
        if rec.get("prompt_sha256") != psha or rec.get("input_sha256") != _input_sha(member, item, psha, rec.get("attachment_sha256")):
            raise bad(f"{item}: input sha != its prompt / attachment")
    for r in rows:
        rec = inputs[r["item_id"]]
        packet = out / r["path"]
        if rec["prompt"] not in packet.read_text(encoding="utf-8"):
            raise bad(f"{r['pkt']}: the packet does not carry the frozen input of {r['item_id']}")
        atts = [p for p in packet.parent.glob(f"{packet.stem}.*") if p.suffix not in (".md", ".json", ".txt")]
        want = rec.get("attachment_sha256")
        if (want is None and atts) or (want is not None and (len(atts) != 1 or _sha(atts[0]) != want)):
            raise bad(f"{r['pkt']}: the attachment != the frozen input of {r['item_id']}")


def kv_freeze(out_dir, meta, judges, rubric, single_family=None):
    """`<member>/FROZEN.json` before any verdict: the frozen set (README, manifest, every packet and attachment; sha256), the
    member, pair, B8 sha, items (treatment slot, judged lengths), identical / excluded counts, the judges (+ the operator's
    single-family label when given), the rubric sha."""
    out = Path(out_dir)
    if any(out.rglob("*.verdict.json")):
        raise _refusal(f"freeze: a verdict file already exists in {out.name}: the packet set is frozen before any verdict")
    if (out / FROZEN_NAME).exists():
        raise _refusal(f"freeze: {FROZEN_NAME} already exists")
    rows = _read_manifest(out)
    files = {rel: _sha(out / rel) for rel in _kv_frozen_set(out, rows)}
    items = list(meta.get("items") or [])
    judges_rec = [{k: j.get(k) for k in ("label", "family", "client", "model")} for j in judges]
    counts = dict(items=len(items), packet_files=len(rows), planned_verdicts=len(items) * len(judges) * len(jp.ORDERS),
                  identical=len(meta.get("identical") or []),
                  excluded={k: len(v) for k, v in sorted((meta.get("excluded") or {}).items())})
    doc = dict(meta, version=KV_PANEL_VERSION, lever="kv", build=KV_PANEL_BUILD, rubric=rubric, rubric_sha256=rubric_sha(rubric),
               judges=judges_rec, single_family=single_family, files=files, counts=counts)
    (out / FROZEN_NAME).write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return out / FROZEN_NAME


def _kv_frozen_set(out, rows):
    """README_JUDGE.md, manifest.jsonl, every manifest packet and its attachments (`<pkt>.<ext>` beside it, not a verdict /
    marker); a packet outside the manifest refuses."""
    paths = _frozen_set(out, rows)
    extra = []
    for r in rows:
        packet = out / r["path"]
        for p in packet.parent.glob(f"{packet.stem}.*"):
            if p.suffix not in (".md", ".json", ".txt"):
                extra.append(p.relative_to(out).as_posix())
    return sorted(set(paths) | set(extra))


def kv_check_frozen(out_dir):
    """A KV member's FROZEN.json: present, every frozen file unchanged, the frozen set exactly the manifest's, the manifest's
    rows consistent with the frozen items (treatment slot, keys, judges x both orders), the KV pair / build / rubric; else
    RefusalError. Returns FROZEN."""
    out = Path(out_dir)
    try:
        doc = json.loads((out / FROZEN_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise _refusal(f"panel {out.name}: {FROZEN_NAME} is missing or unreadable") from None
    files = doc.get("files") if isinstance(doc, dict) else None
    if not isinstance(files, dict) or "manifest.jsonl" not in files:
        raise _refusal(f"panel {out.name}: {FROZEN_NAME} lists no frozen files / manifest")
    for rel, sha in sorted(files.items()):
        _safe_rel(rel, "panel frozen file")
        if not (out / rel).is_file():
            raise _refusal(f"panel {out.name}: frozen file {rel} is missing")
        if _sha(out / rel) != sha:
            raise _refusal(f"panel {out.name}: frozen file {rel} changed")
    rows = _read_manifest(out)
    if sorted(files) != _kv_frozen_set(out, rows):
        raise _refusal(f"panel {out.name}: the frozen file set != README + manifest + the manifest packets / attachments")
    _kv_check_manifest(doc, rows, out.name)
    _kv_check_inputs(doc, rows, out, out.name)
    return doc


def _kv_check_manifest(doc, rows, name):
    def bad(msg):
        return _refusal(f"panel {name}: {FROZEN_NAME} and manifest.jsonl disagree: {msg}")

    from bench.p426_plan import check_kv_pair

    if doc.get("lever") != "kv" or doc.get("build") != KV_PANEL_BUILD or doc.get("version") != KV_PANEL_VERSION:
        raise bad("not a KV panel record (lever / build / version)")
    try:
        ref, test = check_kv_pair(*(doc.get("pair") or ()))
    except (TypeError, ValueError):
        raise bad(f"pair {doc.get('pair')!r}") from None
    if doc.get("member") != name or doc.get("rubric") != kv_rubric(name) or doc.get("rubric_sha256") != rubric_sha(doc["rubric"]):
        raise bad("member / rubric is not this member's")
    if not re.fullmatch(r"[0-9a-f]{64}", str(doc.get("b8_sha256"))):
        raise bad("no B8 sha256")
    judges = doc.get("judges")
    if not (isinstance(judges, list) and judges and all(isinstance(j, dict) and all(
            isinstance(j.get(k), str) and j.get(k) for k in ("label", "family", "client", "model")) for j in judges)):
        raise bad("judges are not a list of {label, family, client, model}")
    labels = [j["label"] for j in judges]
    two = len(judges) == 2 and len({j["family"] for j in judges}) == 2
    sf = doc.get("single_family")
    if not two and not (isinstance(sf, dict) and isinstance(sf.get("label"), str) and sf["label"].strip()):
        raise bad("a single-family judge set without the operator's label (C166 / C206)")
    ref_tune, test_tune = kv_tunes(ref, test)
    meta = {}
    for it in doc.get("items") or []:
        if not (isinstance(it, dict) and isinstance(it.get("item"), str) and it.get("test_slot") in ("A", "B")
                and all(isinstance(it.get(f), int) and not isinstance(it.get(f), bool) and it[f] >= 0 for f in ("len_ref", "len_test"))):
            raise bad(f"item {it!r} is malformed")
        if it["item"] in meta:
            raise bad(f"item {it['item']} is listed twice")
        meta[it["item"]] = it
    seen, pkts = {}, set()
    for r in rows:
        item = r.get("item_id")
        if item not in meta or r.get("judge") not in labels or r.get("order") not in jp.ORDERS:
            raise bad(f"manifest row {r.get('pkt')!r}: item / judge / order")
        pkt = r.get("pkt")
        if not (isinstance(pkt, str) and re.fullmatch(r"p\d+", pkt)) or pkt in pkts:
            raise bad(f"manifest packet id {pkt!r} is malformed or repeated")
        pkts.add(pkt)
        if not (isinstance(r.get("path"), str) and re.fullmatch(re.escape(r["judge"]) + r"/batch\d{2}/" + pkt + r"\.md", r["path"])):
            raise bad(f"manifest packet {pkt}: path {r.get('path')!r}")
        if r.get("prompt_sha") != doc["rubric_sha256"]:
            raise bad(f"manifest packet {pkt}: prompt_sha != the frozen rubric sha")
        kt, kr = f"{KV_MODEL_LABEL}@{test_tune}::{item}", f"{KV_MODEL_LABEL}@{ref_tune}::{item}"
        want = (kt, kr) if meta[item]["test_slot"] == "A" else (kr, kt)
        if (r.get("a_key"), r.get("b_key")) != want or r.get("pair_id") != f"m76-{item}":
            raise bad(f"manifest packet {pkt}: keys / pair id disagree with the frozen treatment slot of {item}")
        slot = (r["judge"], r["order"])
        if slot in seen.setdefault(item, set()):
            raise bad(f"item {item}: judge x order {slot} is listed twice")
        seen[item].add(slot)
    need = {(j, o) for j in labels for o in jp.ORDERS}
    for item in meta:
        if seen.get(item, set()) != need:
            raise bad(f"item {item}: manifest judge x order slots != every frozen judge x both orders")
    counts = doc.get("counts") if isinstance(doc.get("counts"), dict) else {}
    if counts.get("items") != len(meta) or counts.get("packet_files") != len(rows) or counts.get("planned_verdicts") != len(rows):
        raise bad("counts (items / packet files / planned verdicts) != the manifest")


def _ingest_frozen(out_dir, frozen):
    """`a7_ingest`'s rule against an already-checked FROZEN (rows' provenance from FROZEN; any problem counted, never admitted)."""
    out = Path(out_dir)
    fsha = _sha(out / FROZEN_NAME)
    judges = {j["label"]: j for j in frozen["judges"]}
    rows, report = [], dict(missing=0, failed=0, unsealed=0, unbound=0, rejected=0, unparseable=0)
    for m in _read_manifest(out):
        packet = out / m["path"]
        verdict = packet.with_name(f"{m['pkt']}.verdict.json")
        if packet.with_name(f"{m['pkt']}.failed.txt").exists():
            report["failed"] += 1
            continue
        if not verdict.exists():
            report["missing"] += 1
            continue
        try:
            doc = json.loads(verdict.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ValueError):
            doc = None
        if not isinstance(doc, dict):
            report["unparseable"] += 1
            continue
        if "packet_sha" not in doc:
            report["unsealed"] += 1
            continue
        judge = judges[m["judge"]]
        problem = _verdict_problem(doc, packet, frozen, judge, fsha)
        if problem is not None:
            report[problem[0]] += 1
            continue
        rows.append(dict(_expected_seal(frozen, judge, fsha), choice=doc["choice"], rationale=doc.get("rationale"),
                         client_version=doc["client_version"].strip(), packet_sha=doc["packet_sha"],
                         attachment_sha=doc.get("attachment_sha"), item_id=m["item_id"], order=m["order"],
                         a_key=m["a_key"], b_key=m["b_key"], pair_id=m["pair_id"], pkt=m["pkt"]))
    return rows, report


def kv_ingest(out_dir):
    """(FROZEN, admissible verdict rows, report) of one KV member (`a7_ingest`'s rule over `kv_check_frozen`)."""
    frozen = kv_check_frozen(out_dir)
    rows, report = _ingest_frozen(out_dir, frozen)
    return frozen, rows, report


def kv_seal(out_dir, label, client_version):
    """`a7-seal` for a KV member: the frozen Claude blind-judge's bare verdicts sealed against the member's FROZEN (its packets
    and sha); anything else is a permanent failed marker."""
    return _seal_frozen(out_dir, kv_check_frozen(out_dir), label, client_version)


def kv_cursor(out_dir, label, runner=subprocess.run):
    """`a7-cursor` for a KV member (retries 0; verdicts bound to the member's FROZEN sha)."""
    out = Path(out_dir)
    judge = frozen_judge(kv_check_frozen(out), label)
    if judge.get("client") != "cursor-agent":
        raise _refusal(f"judge {label!r} is not a cursor-agent judge")
    return run_cursor_judge(out.resolve(), judge, runner=runner, frozen_sha=_sha(out / FROZEN_NAME))


def _kv_b8(b8_path):
    try:
        data = Path(b8_path).read_bytes()
        b8 = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise _refusal("B8.json is missing or unreadable") from None
    if not isinstance(b8, dict) or b8.get("lever") != "kv" or not isinstance(b8.get("axes"), dict):
        raise _refusal("B8.json is not a lever-kv verifier record")
    return b8, hashlib.sha256(data).hexdigest()


def _rejected_pair_keys(rec):
    """Every planned key of a rejected pair, accepted and rejected (erratum v1.3), deduplicated in first-seen order."""
    out = []
    for k in list(rec.get("keys") or []) + list(rec.get("keys_rejected") or []):
        key = k.get("key") if isinstance(k, dict) else None
        item = str(key[1]) if isinstance(key, list) and len(key) > 1 else None
        if item is not None and item not in out:
            out.append(item)
    return out


def kv_wave1_select(rows_root, b8, member, capture=None):
    """`(items, excluded, identical)` of a Wave 1 member over its B8-accepted pairs: the eligible, non-identical keys with both
    arms' texts (`kv_select`); identical eligible keys are counted (score 0.5), never judged; a rejected pair's keys (accepted
    and rejected) are excluded (`rejected pair <block>`). `capture` (a dict) receives `ids` and the selected items' rows per
    arm (`rows` {item: {arm: row}})."""
    from bench import p426_signals_wave1 as W
    from bench import p426_verify as V

    kind = KV_MEMBER_KIND[member]
    ref, test = b8["pair"]
    reader = V.Reader(rows_root, confine=True)
    ids = V.load_kv_ids(reader)
    items, excluded, identical = [], {}, []
    captured = {}
    for rec in (b8["axes"].get("wave1") or {}).get("pairs") or []:
        if rec.get("kind") != kind:
            continue
        label = rec["block"]
        if not rec.get("accepted"):
            excluded.setdefault(f"rejected pair {label}", []).extend(_rejected_pair_keys(rec))
            continue
        legs = {arm: V.load_kv_leg(reader, kind, arm, label, ids) for arm in (ref, test)}
        rows = {arm: {r["id"]: r["row"] for r in legs[arm]["rows"]} for arm in (ref, test)}
        keys = {k["key"][1]: k for k in rec["keys"]}
        rows = {arm: {x: r for x, r in rows[arm].items() if x in keys} for arm in (ref, test)}
        correct = {}
        if kind == "math500":
            planned = ids["math500"][label]
            correct = {arm: {x for x, s in W._a1_arm(legs[arm], planned)[1].items() if s == 1.0} for arm in (ref, test)}
        sel, ex = kv_select(kind, rows[ref], rows[test], correct.get(ref), correct.get(test))
        for k, v in ex.items():
            excluded.setdefault(k, []).extend(str(x) for x in v)
        for item_id, rt, tt in sel:
            key = next(x for x in keys if str(x) == item_id)
            if keys[key].get("identical"):
                identical.append(item_id)
            else:
                items.append((item_id, rt, tt))
                captured[item_id] = {arm: rows[arm].get(key) for arm in (ref, test)}
    if capture is not None:
        capture.update(ids=ids, rows=captured)
    return items, excluded, identical


def kv_a7_context(results_root, b8):
    """The `_a7_packet` context of a KV A7 record (reference = `off`, treatment = `on` slots; KV harvest prefix), the
    accepted planned sessions only."""
    from bench import p426_verify as V

    a7 = b8["axes"].get("A7")
    if not isinstance(a7, dict):
        raise _refusal("B8.json has no axes.A7 (no Wave 2 record)")
    ref, test = b8["pair"]
    reader = V.Reader(Path(results_root))
    by_session, atts = {}, {}
    for p in a7.get("pairs") or []:
        s = p.get("pair")
        keys = [dict(key=k["key"], identical=k["identical"], off_manifest_sha256=(k.get("manifest_sha256") or {}).get(ref),
                     on_manifest_sha256=(k.get("manifest_sha256") or {}).get(test)) for k in p.get("keys") or []]
        by_session[s] = dict(p, keys=keys)
        if p.get("accepted") and s in (a7.get("sessions") or []):
            atts[s] = {slot: V._kv_load_attempt(reader, p["attempts"][arm], s, f"A7 {s} {arm}")
                       for slot, arm in (("off", ref), ("on", test))}
    return dict(root=Path(results_root), by_session=by_session, atts=atts, prefix=V.KV_REPO_PREFIX)


def kv_export(rows_root, b8_path, judges_path, out_dir, prompts=None, *, members=None, images=None, single_family_label=None,
              a7_inputs=None, sources=None):
    """Per member a fresh `<out_dir>/<member>/` (built as `.<member>.partial`, renamed on success): packets, manifest and
    FROZEN.json bound to B8.json's sha. Every packet input is derived by the tool (erratum v1.3): Wave 1 from the benchmark
    inputs of the items B8 covers (`kv_member_inputs`, `sources` = `KVInputSources()` by default), A7 from the polyglot start
    tree; each item's input record (prompt, sha256s) is frozen in FROZEN.json `inputs`. `prompts` ({member: {item: prompt}})
    and `images` ({item: image path}, A3) are only validated against the derived inputs, never used. `a7_inputs` = {results_root,
    evidence_ref, repo, polyglot_root, universe} for the A7 members. Returns {member: FROZEN}."""
    import os
    import shutil

    sources = sources if sources is not None else KVInputSources()
    b8, b8_sha = _kv_b8(b8_path)
    ref, test = b8["pair"]
    out = Path(out_dir)
    if not out.is_dir():
        raise _refusal(f"{out} is not a directory (the panel root)")
    members = tuple(members) if members is not None else kv_members()
    unknown = [m for m in members if m not in kv_members()]
    if unknown:
        raise _refusal(f"members {unknown} are not in the KV family {list(kv_members())}")
    done = {}
    for member in members:
        dest, partial = out / member, out / f".{member}.partial"
        if dest.exists() or partial.exists():
            raise _refusal(f"{member} exists (or a partial export): packets are exported once into a fresh directory")
        judges, single = kv_judges(judges_path, "image" if member == "A3" else "text", single_family_label)
        if member.startswith("A7-"):
            if not a7_inputs:
                raise _refusal(f"{member}: the A7 packets need --results-root / --evidence-ref / --repo / --polyglot-root / "
                               "--universe")
            from bench import p426_verify as V

            session = member.split("-", 1)[1]
            ctx = kv_a7_context(a7_inputs["results_root"], b8)
            if session not in ctx["atts"]:
                raise _refusal(f"{member}: session {session} is not a B8-accepted planned session")
            top = V.repo_top(a7_inputs["repo"])
            top_ref = (top, V.resolve_commit(top, a7_inputs["evidence_ref"], "--evidence-ref"))
            rec = ctx["by_session"][session]
            identical = [k["key"][1] for k in rec["keys"] if k.get("identical") and all(
                _passed(ctx["atts"][session][slot], k["key"][1]) for slot in ("off", "on"))]
            sel_ids = [k["key"][1] for k in rec["keys"] if not k.get("identical") and all(
                _passed(ctx["atts"][session][slot], k["key"][1]) for slot in ("off", "on"))]
            excluded = {"not both pass": [k["key"][1] for k in rec["keys"] if not all(
                _passed(ctx["atts"][session][slot], k["key"][1]) for slot in ("off", "on"))]}
            packets = {rid: _kv_a7_packet(ctx, (session, rid), a7_inputs, top_ref) for rid in sel_ids}
            items = [(rid, packets[rid]["off"], packets[rid]["on"]) for rid in sel_ids]
            inputs = {rid: (_input_record(member, rid, packets[rid]["task"], KV_INPUT_SOURCE["A7"]), None) for rid in sel_ids}
            lengths = {rid: (packets[rid]["len_off"], packets[rid]["len_on"]) for rid in sel_ids}
        else:
            cap = {}
            items, excluded, identical = kv_wave1_select(rows_root, b8, member, capture=cap)
            inputs = kv_member_inputs(member, [i for i, _rt, _tt in items], cap["ids"], sources, cap["rows"])
            lengths = {i: (len(rt), len(tt)) for i, rt, tt in items}
        kv_validate_prompts(member, (prompts or {}).get(member), inputs)
        if member == "A3":
            for item, path in sorted((images or {}).items()):
                rec = inputs.get(str(item))
                if rec is None or not Path(path).is_file() or _sha(path) != rec[0]["attachment_sha256"]:
                    raise _refusal(f"--images {item}: not this member's item, or != the corpus image both arms saw")
        member_prompts = {i: rec["prompt"] for i, (rec, _a) in inputs.items()}
        attachments = {i: a for i, (_rec, a) in inputs.items() if a is not None}
        if member == "A5":
            excluded = dict(excluded, rule=[KV_A5_RULE])
        the_pairs = kv_make_pairs(items, ref, test)
        test_tune = kv_tunes(ref, test)[1]
        meta = dict(member=member, pair=[ref, test], b8_sha256=b8_sha, identical=sorted(identical), excluded=excluded,
                    items=[dict(item=p["item_id"], test_slot="A" if f"@{test_tune}::" in p["a_key"] else "B",
                                len_ref=lengths[p["item_id"]][0], len_test=lengths[p["item_id"]][1]) for p in the_pairs],
                    inputs={i: rec for i, (rec, _a) in sorted(inputs.items())})
        try:
            partial.mkdir()
            _kv_write_packets(the_pairs, [j["label"] for j in judges], member_prompts, partial, kv_rubric(member),
                              attachments=attachments or None)
            kv_freeze(partial, meta, judges, kv_rubric(member), single_family=single)
            os.rename(partial, dest)
        except BaseException:
            if partial.exists():
                shutil.rmtree(partial)
            raise
        done[member] = kv_check_frozen(dest)
    return done


def _kv_a7_packet(ctx, item, a7_inputs, top_ref):
    """`_a7_packet` over the KV context (`ctx["prefix"]`: the KV harvest prefix)."""
    return _a7_packet(ctx, item, a7_inputs["polyglot_root"], a7_inputs["universe"], top_ref)


def kv_panel_members(panel_dir, ref, test, b8_sha256, sessions=None):
    """{member: {judged, identical, vector, mean, excluded, report, length_adjusted, single_family}} of every member directory:
    each FROZEN re-checked (`kv_check_frozen`) and bound to THIS B8 record and pair; verdicts admitted only through the frozen
    packets with one valid verdict per frozen judge x order; the vector = admitted scores − 0.5 plus 0 per identical item."""
    panel_dir = Path(panel_dir)
    out = {}
    for member in kv_members(sessions):
        d = panel_dir / member
        if not d.is_dir():
            continue
        frozen, rows, report = kv_ingest(d)
        if frozen.get("b8_sha256") != b8_sha256:
            raise _refusal(f"panel {member}: FROZEN.json is bound to another B8 record ({frozen.get('b8_sha256')} != {b8_sha256})")
        if list(frozen.get("pair") or ()) != [ref, test]:
            raise _refusal(f"panel {member}: FROZEN.json is the pair {frozen.get('pair')}, not {[ref, test]}")
        admitted, excluded = admit(rows, [j["label"] for j in frozen["judges"]])
        scores = kv_item_scores([r for it in sorted(admitted) for r in admitted[it]], ref, test)
        identical = frozen.get("identical") or []
        vector = [scores[it]["score"] - 0.5 for it in sorted(admitted)] + [0.0] * len(identical)
        la = None
        meta = {it["item"]: it for it in frozen.get("items") or []}
        data = [dict(item=it, score=kv_item_scores([r], ref, test)[it]["score"],
                     log_len_ratio=math.log(meta[it]["len_test"] / meta[it]["len_ref"]))
                for it in sorted(admitted) for r in admitted[it] if meta[it]["len_ref"] > 0 and meta[it]["len_test"] > 0]
        if data:
            res = length_adjusted(data)
            la = dict(res, ci=list(res["ci"]))
        out[member] = dict(judged=len(admitted), identical=len(identical), vector=vector,
                           mean=(0.5 + sum(vector) / len(vector)) if vector else None, excluded=excluded, report=report,
                           length_adjusted=la, single_family=frozen.get("single_family"),
                           frozen_sha256=_sha(d / FROZEN_NAME), planned_items=len(meta),
                           planned_verdicts=len(_read_manifest(d)),
                           admitted_verdicts=sum(len(admitted[it]) for it in admitted))
    return out


def kv_expected_members(b8, sessions=None):
    """The members a lever-kv B8 record expects (erratum v1.3): each Wave 1 member with at least one B8-accepted pair of its
    kind, and `A7-<session>` for every planned session B8 accepted."""
    w1 = [p for p in (b8.get("axes", {}).get("wave1") or {}).get("pairs") or [] if p.get("accepted")]
    kinds = {p.get("kind") for p in w1}
    out = [m for m in KV_WAVE1_MEMBERS if KV_MEMBER_KIND[m] in kinds]
    a7 = b8.get("axes", {}).get("A7")
    if isinstance(a7, dict):
        acc = {p.get("pair") for p in a7.get("pairs") or [] if p.get("accepted")}
        planned = list(a7.get("sessions") or []) if sessions is None else list(sessions)
        out += [f"A7-{s}" for s in planned if s in acc]
    return out


def kv_panel_completeness(members, expected):
    """`{complete, missing_members, incomplete}`: every expected member present, and in each member every frozen judge x order
    verdict slot admitted (no missing / failed / unsealed / unbound / rejected / unparseable verdict, every frozen item
    admitted)."""
    missing = [m for m in expected if m not in members]
    incomplete = {}
    for m, rec in sorted(members.items()):
        bad = {k: v for k, v in sorted((rec.get("report") or {}).items()) if v}
        if rec.get("admitted_verdicts") != rec.get("planned_verdicts") or rec.get("judged") != rec.get("planned_items"):
            bad.update(admitted_verdicts=rec.get("admitted_verdicts"), planned_verdicts=rec.get("planned_verdicts"),
                       judged=rec.get("judged"), planned_items=rec.get("planned_items"))
        if bad:
            incomplete[m] = bad
    return dict(complete=not missing and not incomplete, missing_members=missing, incomplete=incomplete,
                expected=list(expected))


def kv_wave1_eligibility(rows_root, b8):
    """Per Wave 1 member: eligible keys (to judge), identical (counted 0.5) and the excluded keys by reason."""
    out = {}
    for member in KV_WAVE1_MEMBERS:
        items, excluded, identical = kv_wave1_select(rows_root, b8, member)
        out[member] = dict(packets=[i for i, _r, _t in items], identical=identical,
                           excluded={k: len(v) for k, v in excluded.items()})
    return out


def main(argv=None):
    import argparse
    import sys

    from bench import p426_verify as V

    ap = argparse.ArgumentParser(prog="python -m bench.p426_panel")
    ap.add_argument("--lever", default="mtp", choices=("mtp", "kv"),
                    help="M76 B3: mtp (default) = the P426 a7-* commands; kv = the M76 KV panel (kv-* commands)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("a7-export")
    for flag in ("--results-root", "--b8", "--evidence-ref", "--repo", "--polyglot-root", "--universe", "--judges",
                 "--out"):
        ex.add_argument(flag, required=True)
    cu = sub.add_parser("a7-cursor")
    cu.add_argument("--out", required=True)
    cu.add_argument("--judge", required=True)
    se = sub.add_parser("a7-seal")
    se.add_argument("--out", required=True)
    se.add_argument("--judge", required=True)
    se.add_argument("--client-version", required=True)
    ke = sub.add_parser("kv-eligibility", help="--lever kv: the panel-eligible keys of a lever-kv B8 (per Wave 1 member)")
    ke.add_argument("--rows-root", required=True)
    ke.add_argument("--b8", required=True)
    kx = sub.add_parser("kv-export", help="--lever kv: packets + FROZEN.json per member (bound to B8.json and every packet)")
    for flag in ("--rows-root", "--b8", "--judges", "--out"):
        kx.add_argument(flag, required=True)
    kx.add_argument("--prompts", default=None, help="optional JSON {member: {item: task prompt}}: validated against the inputs "
                                                    "the tool derives (never used in a packet)")
    kx.add_argument("--images", default=None, help="optional JSON {item: image path} (A3): validated, never used")
    kx.add_argument("--members", default=None, help="comma list (default: the whole KV family)")
    kx.add_argument("--single-family-label", default=None, help="the operator's label admitting a single-family judge set")
    for flag in ("--results-root", "--evidence-ref", "--repo", "--polyglot-root", "--universe"):
        kx.add_argument(flag, default=None, help="A7 members")
    kc = sub.add_parser("kv-cursor", help="--lever kv: the frozen cursor-agent judge of one member directory")
    kc.add_argument("--out", required=True)
    kc.add_argument("--judge", required=True)
    ks = sub.add_parser("kv-seal", help="--lever kv: seal the Claude blind-judge verdicts of one member directory")
    ks.add_argument("--out", required=True)
    ks.add_argument("--judge", required=True)
    ks.add_argument("--client-version", required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd.startswith("kv-") != (args.lever == "kv"):
            raise V.RefusalError(f"{args.cmd} is a lever {'kv' if args.cmd.startswith('kv-') else 'mtp'} command "
                                 f"(--lever {args.lever})")
        if args.cmd == "kv-eligibility":
            b8, _sha256 = _kv_b8(args.b8)
            V.kv_check_roots(args.rows_root)
            print(json.dumps(kv_wave1_eligibility(args.rows_root, b8), sort_keys=True, indent=1))
            return 0
        if args.cmd == "kv-export":
            V.kv_check_roots(args.rows_root)

            def _json(path, what):
                if path is None:
                    return None
                try:
                    return json.loads(Path(path).read_text())
                except (OSError, ValueError):
                    raise V.RefusalError(f"{what} is missing or unreadable") from None
            a7 = {k: getattr(args, k) for k in ("results_root", "evidence_ref", "repo", "polyglot_root", "universe")}
            done = kv_export(args.rows_root, args.b8, args.judges, args.out, _json(args.prompts, "--prompts"),
                             members=tuple(m for m in args.members.split(",") if m) if args.members else None,
                             images=_json(args.images, "--images"), single_family_label=args.single_family_label,
                             a7_inputs=a7 if all(a7.values()) else None)
            print(json.dumps({m: f["counts"] for m, f in done.items()}, sort_keys=True))
            return 0
        if args.cmd == "kv-cursor":
            print(json.dumps(kv_cursor(args.out, args.judge), sort_keys=True))
            return 0
        if args.cmd == "kv-seal":
            print(json.dumps(kv_seal(args.out, args.judge, args.client_version), sort_keys=True))
            return 0
        if args.cmd == "a7-export":
            top = V.repo_top(args.repo)
            b8_path = _committed_input(top, args.b8, B8_REL, "--b8")
            universe = _committed_input(top, args.universe, UNIVERSE_REL, "--universe")
            doc = a7_export(args.results_root, b8_path, args.evidence_ref, args.repo, args.polyglot_root,
                            universe, args.judges, args.out)
            c = doc["counts"]
            print(f"frozen: {c['items']} items {c['items_per_session']}, {c['packet_files']} packet files, "
                  f"{c['planned_verdicts']} planned verdicts; Wave 1 eligible {c['wave1_eligible']} / {c['wave1_keys']} "
                  f"keys, identical {c['wave1_identical']}, not both correct {c['wave1_not_both_correct']}; "
                  f"A7 excluded {c['a7_excluded']}")
        elif args.cmd == "a7-cursor":
            print(json.dumps(a7_cursor(args.out, args.judge), sort_keys=True))
        else:
            print(json.dumps(a7_seal(args.out, args.judge, args.client_version), sort_keys=True))
    except V.RefusalError as exc:
        print(f"REFUSED: {V._one_line(exc)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(main())
