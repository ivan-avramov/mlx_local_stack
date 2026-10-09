import json, os, random, re
from pathlib import Path
D = Path(__file__).parent; S = D / "solutions"; POLY = Path(os.path.expanduser("~/ws/mlx_local_stack_workdir/polyglot-benchmark"))
rep = json.load(open(D / "rebuild_report.json")); by = {(r["model"], r["s"], r["item"], r["arm"]): r for r in rep}
NAMES = ["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit", "Qwen", "Fable", "OptiQ", "opencode"]  # allow-shorthand
SYS = {
 "code": ("You are judging the quality of two candidate solutions to the same programming exercise. Both solutions pass the "
          "exercise's full test suite. Judge ONLY code quality beyond the tests: correctness on inputs the tests may not cover "
          "(edge cases, invalid input handling the specification asks for), readability and clarity, idiomatic use of the language, "
          "appropriate simplicity and structure, and maintainability. Ignore length except where it hurts clarity. The solutions are "
          "labeled A and B; all identifying information has been removed. "
          'Reply with ONLY a JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No prose outside the JSON.'),
 "msg": ("A coding agent was asked to implement a programming exercise so that its tests pass. You are shown, for two candidate "
         "runs, the final message the agent wrote to the user, with that run's final code as context. Judge ONLY the final message: "
         "accuracy of its claims about the code and the verification performed, usefulness to a developer reviewing the work, and "
         "clarity. Ignore length except where it hurts clarity or usefulness. Do not judge the code itself. The runs are labeled A and B; "
         "all identifying information has been removed. "
         'Reply with ONLY a JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No prose outside the JSON.')}
INSTR = ('Write your verdict to `{pkt}.verdict.json` in this SAME directory, as EXACTLY one JSON object: '
         '{{"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}}. No other content in that file, and do not open, read, or '
         'modify any other file.')
def scrub(t):
    for n in NAMES: t = re.sub(re.escape(n), "[redacted]", t, flags=re.I)
    return t
def task(item):
    lang, name = item.split("/"); d = POLY / lang / "exercises/practice" / name / ".docs"
    t = (d / "instructions.md").read_text() + ((d / "instructions.append.md").read_text() if (d / "instructions.append.md").exists() else "")
    return f"Language: {lang}. Exercise: {name}.\n\n{t}"
def side(r, kind):
    ext = "go" if r["item"].startswith("go/") else "py"
    code = (S / f"{r['key']}.{ext}").read_text()
    if kind == "code": return f"```{ext}\n{code}\n```"
    return f"### Final message\n{(S / (r['key'] + '.final.md')).read_text()}\n\n### Final code (context only)\n```{ext}\n{code}\n```"
pairs = []
for model in sorted({r["model"] for r in rep}):
    keys = sorted({(r["s"], r["item"]) for r in rep if r["model"] == model})
    flags = [True] * (len(keys) // 2) + [False] * (len(keys) - len(keys) // 2); random.Random(f"205|{model}").shuffle(flags)
    for (s, item), swap in zip(keys, flags):
        a, b = by[(model, s, item, "A")], by[(model, s, item, "B")]
        pairs.append(dict(pair_id=f"{model}|{s}|{item}", item=item, model=model, slot1=("B" if swap else "A"),
                          r1=(b if swap else a), r2=(a if swap else b)))
random.Random(205).shuffle(pairs)
JUDGES = ["claude-opus-5-5", "claude-sonnet-5-5", "codex-gpt-6-astra"]
man = []; c = 0
for kind in ("code", "msg"):
    for j in JUDGES:
        for order in ("AB", "BA"):
            for bi in range(0, len(pairs), 10):
                bd = D / "packets" / kind / j / f"batch_{order}{bi // 10}"; bd.mkdir(parents=True, exist_ok=True)
                for p in pairs[bi:bi + 10]:
                    pkt = f"p{c:04d}"; c += 1
                    first, second = (p["r1"], p["r2"]) if order == "AB" else (p["r2"], p["r1"])
                    user = (f"## Exercise\n{task(p['item'])}\n\n## Candidate A\n{scrub(side(first, kind))}\n\n## Candidate B\n"
                            f"{scrub(side(second, kind))}\n\nWhich is better? Reply with ONLY the JSON object.")
                    path = bd / f"{pkt}.md"; path.write_text(f"# SYSTEM\n{SYS[kind]}\n\n# USER\n{user}\n\n---\n{INSTR.format(pkt=pkt)}\n")
                    shown_A_arm = (p["slot1"] if order == "AB" else ("B" if p["slot1"] == "A" else "A"))
                    man.append(dict(pkt=pkt, kind=kind, judge=j, order=order, pair_id=p["pair_id"], item=p["item"], model=p["model"],
                                    shown_A_is_arm=shown_A_arm, path=str(path)))
(D / "manifest.private.jsonl").write_text("\n".join(json.dumps(m) for m in man) + "\n")
print(len(pairs), "pairs", len(man), "packets")
