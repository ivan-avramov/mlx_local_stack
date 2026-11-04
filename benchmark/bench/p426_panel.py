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
        data = _git_show(top, ref, f"{V.REPO_PREFIX}{stem}.final_tree/objects/{sha}")
        got = hashlib.sha256(data).hexdigest()
        if got != sha:
            raise _refusal(f"{att['name']} {rid}: final-tree object {rel} hashes to {got}, not its name {sha}")
        tree[rel] = data
    for rel in missing:
        _safe_rel(rel, f"{att['name']} {rid} final tree missing")
    published = f"{V.REPO_PREFIX}{stem}.events.jsonl"
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
    out = Path(out_dir)
    frozen = check_frozen(out)
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


def main(argv=None):
    import argparse
    import sys

    from bench import p426_verify as V

    ap = argparse.ArgumentParser(prog="python -m bench.p426_panel")
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
    args = ap.parse_args(argv)
    try:
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
