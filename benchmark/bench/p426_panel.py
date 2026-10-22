"""P426 B3 / C207: the two-family blind pairwise panel for the ON vs OFF comparisons (`docs/specs/p426-fable-mtp-recert.md` §7).

Judges come from the box's `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/judges.json` ({"box", "text": [2 judges],
"image": [2 judges]}, two different families each). Packets reuse `judge_pairwise.export_packets` with the axis's rubric; the
Claude judge is the Claude Code `blind-judge` agent run by the session on the exported batch directories; the Cursor judge is
`run_cursor_judge` (retries 0: a failure is a missing verdict, counted). `item_scores` + `length_adjusted` give the signal.
"""

import hashlib
import json
import math
import subprocess
from pathlib import Path

from bench import judge_pairwise as jp

OFF_TUNE, ON_TUNE = "p426-off", "p426-on"
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


def pairs(model, off_rows, on_rows, seed=426):
    """One blind ON vs OFF pair per item both arms hold (converged), balanced A / B slots (judge_pairwise)."""
    return jp.build_tune_pairs(model, OFF_TUNE, ON_TUNE, off_rows, on_rows, seed=seed)


def export(axis, the_pairs, judge_labels, task_prompts, out_dir, images=None, model_names=None):
    rubric = AXIS_RUBRIC[axis]
    names = list(model_names or {p["a_key"].split("@", 1)[0] for p in the_pairs})
    return jp.export_packets(
        the_pairs, judge_labels, task_prompts, names, str(out_dir), system=RUBRICS[rubric], attachments=images
    )


def run_cursor_judge(out_dir, judge, runner=subprocess.run, timeout_s=900):
    """Judge every packet of ``judge`` (a Cursor model) once: retries 0, an unparseable / failed answer writes no verdict
    (ingest counts it missing). Records the client version and model in ``<judge>/provenance.json``."""
    root = Path(out_dir) / judge["label"]
    version = runner(["cursor-agent", "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
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
            verdict.write_text(json.dumps({"choice": parsed["choice"], "rationale": parsed.get("rationale")}) + "\n")
            written += 1
        else:
            packet.with_name(f"{pkt}.failed.txt").write_text(out)
            failed += 1
    (root / "provenance.json").write_text(json.dumps(dict(judge, client_version=version), indent=1) + "\n")
    return {"written": written, "failed": failed, "client_version": version}


def item_scores(rows):
    """{item: {score, n, missing}}: ON 1 / tie 0.5 / OFF 0 per verdict (choices are in the SHOWN order: in BA the pair's b
    is shown as "A"), averaged over judges × orders; a missing / unparseable verdict is counted, never scored."""
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
        s["sum"] += 1.0 if f"@{ON_TUNE}::" in chosen else 0.0
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
