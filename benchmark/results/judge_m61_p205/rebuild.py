"""P205 step 1: rebuild each A/B episode's final solution by replaying write/edit calls onto the corpus stub; re-test."""
import json, glob, os, re, shutil, subprocess, tempfile
from pathlib import Path
W = Path(os.path.expanduser("~/ws/mlx_local_stack_workdir")); AB = W / "m61/ab"; OUT = W / "m61/p205/solutions"
POLY = W / "polyglot-benchmark"; PY = Path(os.path.expanduser("~/ws/mlx_local_stack/.venv-bench/bin/python"))
SOL = {"python": "{n}.py", "go": "{n}.go"}
OUT.mkdir(parents=True, exist_ok=True); report = []
for f in sorted(AB.glob("*.m61ab.*.jsonl")):
    model, rest = f.stem.split(".m61ab.")
    s, arm = rest.split(".")[:2]
    for l in open(f):
        r = json.loads(l); lang, name = r["id"].split("/")
        src = POLY / lang / "exercises/practice" / name
        solname = SOL[lang].format(n=name.replace("-", "_"))
        cur = (src / solname).read_text(); t = json.load(open(r["transcript_path"].replace("$STACK_WORKDIR", str(W))))
        n_w = n_e = 0; other = set(); final = ""
        for m in t["messages"]:
            if m.get("type") != "assistant": continue
            txt = "".join(x.get("text") or "" for x in m.get("content", []) if x.get("type") == "text")
            if txt.strip(): final = txt
            for x in m.get("content", []):
                if x.get("type") != "tool" or x["name"] not in ("write", "edit"): continue
                st = x.get("state") or {}; inp = st.get("input") or {}
                if st.get("status") != "completed": continue
                if os.path.basename(inp["path"]) != solname: other.add(os.path.basename(inp["path"])); continue
                if x["name"] == "write": cur = inp["content"]; n_w += 1
                else:
                    assert cur.count(inp["oldString"]) >= 1, (f, r["id"], "oldString missing")
                    cur = cur.replace(inp["oldString"], inp["newString"], 1); n_e += 1
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / name; shutil.copytree(src, work, ignore=shutil.ignore_patterns(".meta")); (work / solname).write_text(cur)
            cmd = [str(PY), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"] if lang == "python" else ["go", "test", "./..."]
            p = subprocess.run(["nice", "-n", "15"] + cmd, cwd=work, capture_output=True, text=True, timeout=300,
                               env={**os.environ, "GOFLAGS": "-count=1"})
        key = f"{model}.{s}.{arm}.{lang}__{name}"
        (OUT / f"{key}.{solname.split('.')[-1]}").write_text(cur); (OUT / f"{key}.final.md").write_text(final)
        report.append(dict(key=key, model=model, s=s, arm=arm, item=r["id"], writes=n_w, edits=n_e, other_files=sorted(other),
                           retest_pass=p.returncode == 0, row_passed=r["passed"], final_chars=len(final), sol_lines=cur.count("\n")))
        print(key, "writes", n_w, "edits", n_e, "other", sorted(other), "retest", p.returncode == 0)
json.dump(report, open(OUT.parent / "rebuild_report.json", "w"), indent=1)
print("ALL RETEST PASS" if all(x["retest_pass"] for x in report) else "SOME FAIL", len(report))
