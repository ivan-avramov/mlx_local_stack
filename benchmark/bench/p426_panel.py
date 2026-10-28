"""P426 B3 / C207: the two-family blind pairwise panel for the ON vs OFF comparisons (`docs/specs/p426-fable-mtp-recert.md` §7).

Judges come from the box's `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/judges.json` ({"box", "text": [2 judges],
"image": [2 judges]}, two different families each). Packets reuse `judge_pairwise.export_packets` with the axis's rubric; the
Claude judge is the Claude Code `blind-judge` agent run by the session on the exported batch directories; the Cursor judge is
`run_cursor_judge` (retries 0: a failure is a missing verdict, counted). `item_scores` + `length_adjusted` give the signal.
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


def _seal(packet, choice, rationale, judge, client_version, prompt_sha):
    return dict(choice=choice, rationale=rationale, judge=judge["label"], family=judge.get("family"),
                client=judge.get("client"), model=judge.get("model"), client_version=client_version,
                packet_sha=_sha(packet), attachment_sha=_attachment(packet), prompt_sha=prompt_sha)


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


def run_cursor_judge(out_dir, judge, runner=subprocess.run, timeout_s=900):
    """Judge every packet of ``judge`` (a Cursor model) once: retries 0, an unparseable / failed answer writes no verdict
    (ingest counts it missing). Records the client version and model in ``<judge>/provenance.json``."""
    root = Path(out_dir) / judge["label"]
    pre = runner(["cursor-agent", "--version"], capture_output=True, text=True, timeout=60)
    version = (pre.stdout or "").strip()
    if pre.returncode != 0 or not version:  # K8: no verdict without a known client
        raise RuntimeError(f"cursor-agent version check failed (rc {pre.returncode}): {(pre.stderr or '')[:200]}")
    prompt_sha = {r["pkt"]: r["prompt_sha"] for r in jp.load_manifest(str(out_dir)) if r["judge"] == judge["label"]}
    written = failed = 0
    for packet in sorted(root.glob("batch*/p*.md")):
        pkt = packet.stem
        verdict = packet.with_name(f"{pkt}.verdict.json")
        if verdict.exists():
            continue
        cmd = ["cursor-agent", "-p", "--output-format", "text", "--model", judge["model"], "--mode", "ask",
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
                                                prompt_sha.get(pkt))) + "\n")
            written += 1
        else:
            packet.with_name(f"{pkt}.failed.txt").write_text(out)
            failed += 1
    (root / "provenance.json").write_text(json.dumps(dict(judge, client_version=version), indent=1) + "\n")
    return {"written": written, "failed": failed, "client_version": version}


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
